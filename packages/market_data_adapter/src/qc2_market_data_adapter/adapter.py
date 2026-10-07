"""Deterministic Alpaca stock-bar and corporate-action acquisition."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

from qc2_contracts.catalog import AUTHORITY_OVERRIDES, CONTENT_ADDRESSED
from qc2_contracts.runtime import (
    CONTRACTS,
    ContractValidationError,
    artifact_inventory_hash,
    canonical_json_bytes,
    validate_contract,
    validate_contract_collection,
    verify_content_hash,
)

from .errors import MarketDataError
from .models import (
    CorporateActionVersion,
    DataAnomaly,
    MarketDataRequest,
    MarketDataResult,
    RateLimitObservation,
    SanitizedRequestEvidence,
    SplitAdjustedBar,
    RetryPolicy,
)
from .storage import ContentAddressedStore, StoredArtifact
from .transport import AlpacaTransport, HttpResponse

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
_BAR_PATH = "/v2/stocks/bars"
_ACTION_PATH = "/v1/corporate-actions"
_PROVIDER_ACTION_TYPES = (
    "reverse_split",
    "forward_split",
    "unit_split",
    "cash_dividend",
    "stock_dividend",
    "spin_off",
    "cash_merger",
    "stock_merger",
    "stock_and_cash_merger",
    "redemption",
    "name_change",
    "worthless_removal",
    "rights_distribution",
    "partial_call",
    "reorganization",
    "capital_gains_distribution",
)
_ACTION_GROUPS = {
    "forward_splits": ("SPLIT", True),
    "reverse_splits": ("REVERSE_SPLIT", True),
    "unit_splits": ("OTHER_REVIEW_REQUIRED", False),
    "cash_dividends": ("DIVIDEND", False),
    "stock_dividends": ("DIVIDEND", False),
    "capital_gains_distributions": ("DISTRIBUTION", False),
    "cash_mergers": ("CASH_MERGER", False),
    "stock_mergers": ("STOCK_MERGER", False),
    "spin_offs": ("SPINOFF", False),
    "stock_and_cash_mergers": ("OTHER_REVIEW_REQUIRED", False),
    "redemptions": ("OTHER_REVIEW_REQUIRED", False),
    "name_changes": ("OTHER_REVIEW_REQUIRED", False),
    "worthless_removals": ("DELISTING", False),
    "rights_distributions": ("DISTRIBUTION", False),
    "partial_calls": ("OTHER_REVIEW_REQUIRED", False),
    "reorganizations": ("OTHER_REVIEW_REQUIRED", False),
}
_SAFE_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "content-length",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "retry-after",
        "x-request-id",
    }
)
_UNSUPPORTED_PRICE_BASIS_ACTIONS = frozenset(
    {
        "CASH_MERGER",
        "STOCK_MERGER",
        "SPINOFF",
        "DISTRIBUTION",
        "DELISTING",
        "OTHER_REVIEW_REQUIRED",
    }
)


@dataclass(frozen=True)
class _FetchedRow:
    group: str
    symbol: str
    value: Mapping[str, Any]
    receipt_ref: Mapping[str, Any]
    observed_at: str


@dataclass
class _FetchResult:
    rows: list[_FetchedRow] = field(default_factory=list)
    request_manifests: list[Mapping[str, Any]] = field(default_factory=list)
    raw_receipts: list[Mapping[str, Any]] = field(default_factory=list)
    request_evidence: list[SanitizedRequestEvidence] = field(default_factory=list)
    rate_limits: list[RateLimitObservation] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    terminal_token_verified: bool = False


@dataclass(frozen=True)
class _BarObservation:
    symbol: str
    session_id: str
    values: tuple[Decimal, Decimal, Decimal, Decimal, Decimal]
    fingerprint: str
    receipt_ref: Mapping[str, Any]
    observed_at: str
    source_timestamp: str


@dataclass(frozen=True)
class _ActionObservation:
    provider_action_id: str
    symbol: str
    action_type: str
    is_split: bool
    effective_session: str
    processing_session: str | None
    observed_at: str
    terms_hash: str
    core_terms_hash: str
    receipt_ref: Mapping[str, Any]
    new_rate: Decimal | None
    old_rate: Decimal | None
    certainty: str


class AlpacaMarketDataAdapter:
    """Single-feed adapter with no implicit provider, feed, or data fallback.

    The transport, durable byte store, clock, sleeper, and ID source are all
    injected. Tests can therefore exercise the exact acquisition path offline.
    """

    def __init__(
        self,
        *,
        transport: AlpacaTransport,
        store: ContentAddressedStore,
        clock: Callable[[], datetime],
        sleeper: Callable[[float], None],
        id_factory: Callable[[], str],
    ) -> None:
        self._transport = transport
        self._store = store
        self._clock = clock
        self._sleeper = sleeper
        self._id_factory = id_factory

    def acquire(self, request: MarketDataRequest) -> MarketDataResult:
        self._validate_request(request)

        bar_fetch = self._fetch_pages(
            request=request,
            operation="stock_bars",
            path=_BAR_PATH,
            base_params={
                "adjustment": "raw",
                "asof": request.asof,
                "end": request.end,
                "feed": request.feed.lower(),
                "limit": str(request.page_limit),
                "sort": "asc",
                "start": request.start,
                "symbols": ",".join(sorted(request.expected_sessions_by_symbol)),
                "timeframe": "1Day",
            },
            extractor=self._extract_bar_rows,
        )
        action_fetch = self._fetch_pages(
            request=request,
            operation="corporate_actions",
            path=_ACTION_PATH,
            base_params={
                "data_quality": "all",
                "end": request.action_process_end,
                "limit": str(min(request.page_limit, 1000)),
                "region": "us",
                "sort": "asc",
                "start": request.action_process_start,
                "symbols": ",".join(sorted(request.expected_sessions_by_symbol)),
                "types": ",".join(_PROVIDER_ACTION_TYPES),
            },
            extractor=self._extract_action_rows,
        )

        failures = list(dict.fromkeys(bar_fetch.failures + action_fetch.failures))
        raw_receipts = bar_fetch.raw_receipts + action_fetch.raw_receipts
        requests = bar_fetch.request_manifests + action_fetch.request_manifests
        evidence = bar_fetch.request_evidence + action_fetch.request_evidence
        rate_limits = bar_fetch.rate_limits + action_fetch.rate_limits
        artifacts = bar_fetch.artifacts + action_fetch.artifacts
        anomalies: list[DataAnomaly] = []

        bars, quarantines, bar_anomalies, bar_failures = self._normalize_bars(
            request, bar_fetch.rows
        )
        anomalies.extend(bar_anomalies)
        failures.extend(bar_failures)

        action_versions, action_anomalies, action_failures = self._normalize_actions(
            request, action_fetch.rows
        )
        anomalies.extend(action_anomalies)
        failures.extend(action_failures)

        adjustments, adjusted_bars, adjustment_failures = self._split_adjusted_views(
            request,
            bars,
            action_versions,
            action_fetch.terminal_token_verified,
            action_failures,
        )
        failures.extend(adjustment_failures)

        missing_symbols = tuple(
            sorted(
                symbol
                for symbol, expected in request.expected_sessions_by_symbol.items()
                if any(
                    not any(
                        bar["instrument_ref"]["target_id"]
                        == self._instrument_id_by_symbol(request)[symbol]
                        and bar["session_id"] == session
                        and bar["bar_status"] == "FINAL"
                        for bar in bars
                    )
                    for session in expected
                )
            )
        )
        if missing_symbols:
            failures.append("requested_symbol_coverage_missing")

        all_generated: list[tuple[str, Mapping[str, Any]]] = []
        all_generated.extend(("RequestManifest", value) for value in requests)
        all_generated.extend(("RawReceipt", value) for value in raw_receipts)
        all_generated.extend(("DailyBar", value) for value in bars)
        all_generated.extend(("QuarantineCase", value) for value in quarantines)
        supporting_keys = {
            (name, _plain(value).get("id"))
            for name, value in request.supporting_objects
        }
        all_generated.extend(
            ("CorporateActionRecord", value.contract)
            for value in action_versions
            if ("CorporateActionRecord", value.contract["id"]) not in supporting_keys
        )
        all_generated.extend(("AdjustmentManifest", value) for value in adjustments)

        for name, contract in all_generated:
            self._store_contract_artifact(name, contract, artifacts)
        self._store_request_dependencies(request, artifacts)
        for anomaly in anomalies:
            body = canonical_json_bytes(
                {
                    "details_hash": anomaly.details_hash,
                    "raw_receipt_refs": _plain(anomaly.raw_receipt_refs),
                    "reason_code": anomaly.reason_code,
                    "session_id": anomaly.session_id,
                    "symbol": anomaly.symbol,
                }
            )
            self._store_artifact(
                f"anomalies/{hashlib.sha256(body).hexdigest()}.json",
                body,
                "application/json",
                "qc2.market_data.observation_anomaly.v1",
                "1",
                artifacts,
            )
        for version in action_versions:
            body = canonical_json_bytes(
                {
                    "core_terms_hash": version.core_terms_hash,
                    "observed_at": version.observed_at,
                    "provider_action_id": version.provider_action_id,
                    "record_ref": _reference("CorporateActionRecord", version.contract),
                    "split_new_rate": _format_decimal(version.split_new_rate)
                    if version.split_new_rate is not None
                    else None,
                    "split_old_rate": _format_decimal(version.split_old_rate)
                    if version.split_old_rate is not None
                    else None,
                    "terms_hash": version.terms_hash,
                }
            )
            self._store_artifact(
                "action-versions/"
                f"{hashlib.sha256(version.provider_action_id.encode('utf-8')).hexdigest()[:16]}"
                f"-{version.terms_hash}.json",
                body,
                "application/json",
                "qc2.market_data.corporate_action_version.v1",
                "1",
                artifacts,
            )
        for adjusted in adjusted_bars:
            body = canonical_json_bytes(_plain(adjusted))
            digest = hashlib.sha256(body).hexdigest()
            self._store_artifact(
                f"adjusted/{digest}.json",
                body,
                "application/json",
                "qc2.market_data.split_adjusted_bar.v1",
                "1",
                artifacts,
            )

        expected_count = sum(
            len(sessions) for sessions in request.expected_sessions_by_symbol.values()
        )
        eligible_count = sum(
            1
            for bar in bars
            if bar["bar_status"] == "FINAL"
        )
        coverage = _format_probability(eligible_count, expected_count)
        if (
            failures
            or eligible_count != expected_count
            or any(bar["bar_status"] != "FINAL" for bar in bars)
        ):
            completeness = "PARTIAL" if eligible_count > 0 else "FAILED"
        else:
            completeness = "COMPLETE"

        data_bundle = self._contract(
            "DataBundle",
            request,
            {
                "census_ref": _reference("CandidateCensus", request.candidate_census),
                "request_refs": [
                    _reference("RequestManifest", value) for value in requests
                ],
                "raw_receipt_refs": [
                    _reference("RawReceipt", value) for value in raw_receipts
                ],
                "bar_refs": [_reference("DailyBar", value) for value in bars],
                "history_start": request.start,
                "history_end": request.end,
                "coverage": coverage,
                "completeness": completeness,
                "content_inventory_hash": artifact_inventory_hash(artifacts),
                "source_refs": self._bundle_source_refs(
                    request, action_versions, adjustments, quarantines
                ),
            },
        )
        all_generated.append(("DataBundle", data_bundle))

        supporting = [(name, _plain(value)) for name, value in request.supporting_objects]
        supporting.extend(
            ("CorporateActionRecord", _plain(value.contract))
            for value in request.known_action_versions
        )
        try:
            validate_contract_collection(
                supporting
                + [(name, _plain(value)) for name, value in all_generated]
            )
        except ContractValidationError:
            raise MarketDataError("generated_contract_reference_validation_failed") from None

        self._store_contract_artifact("DataBundle", data_bundle, artifacts, include=False)
        return MarketDataResult(
            data_bundle=data_bundle,
            artifact_inventory=tuple(artifacts),
            bar_semantics_manifest=request.bar_semantics_manifest,
            request_manifests=tuple(requests),
            raw_receipts=tuple(raw_receipts),
            daily_bars=tuple(bars),
            quarantine_cases=tuple(quarantines),
            corporate_action_records=tuple(value.contract for value in action_versions),
            corporate_action_versions=tuple(action_versions),
            adjustment_manifests=tuple(adjustments),
            split_adjusted_bars=tuple(adjusted_bars),
            data_anomalies=tuple(anomalies),
            request_evidence=tuple(evidence),
            rate_limit_observations=tuple(rate_limits),
            missing_symbols=missing_symbols,
            failure_codes=tuple(dict.fromkeys(failures)),
        )

    def _validate_request(self, request: MarketDataRequest) -> None:
        if not isinstance(request, MarketDataRequest):
            raise MarketDataError("market_data_request_required")
        if (
            request.provider != "alpaca"
            or request.feed not in {"SIP", "IEX"}
            or request.adjustment != "RAW"
            or request.timeframe != "1DAY"
            or request.currency != "USD"
            or request.mapping_policy != "ALPACA_ASOF"
        ):
            raise MarketDataError("pinned_market_data_policy_invalid")
        start, end, asof = (
            _parse_date(request.start, "start"),
            _parse_date(request.end, "end"),
            _parse_date(request.asof, "asof"),
        )
        if start > end or end > asof:
            raise MarketDataError("requested_session_range_invalid")
        cutoff = _parse_utc(request.cutoff, "cutoff")
        deadline = _parse_utc(request.session_deadline_at, "session_deadline_at")
        now = _parse_utc(self._clock(), "clock")
        if deadline <= now:
            raise MarketDataError("session_deadline_passed")
        if deadline - now > timedelta(days=1):
            raise MarketDataError("session_deadline_out_of_bounds")
        if (
            isinstance(request.page_limit, bool)
            or not isinstance(request.page_limit, int)
            or not 1 <= request.page_limit <= 10000
        ):
            raise MarketDataError("page_limit_out_of_supported_range")
        policy = request.retry_policy
        if not isinstance(policy, RetryPolicy):
            raise MarketDataError("retry_policy_invalid")
        retry_numbers = (
            policy.maximum_total_wait_seconds,
            policy.fallback_initial_delay_seconds,
            policy.fallback_maximum_delay_seconds,
        )
        if (
            isinstance(policy.maximum_attempts, bool)
            or not isinstance(policy.maximum_attempts, int)
            or policy.maximum_attempts < 1
            or isinstance(policy.maximum_pages, bool)
            or not isinstance(policy.maximum_pages, int)
            or not 1 <= policy.maximum_pages <= 1000
            or any(
                not isinstance(value, Decimal) or not value.is_finite()
                for value in retry_numbers
            )
            or policy.maximum_attempts > 8
            or policy.maximum_total_wait_seconds < 0
            or policy.maximum_total_wait_seconds > Decimal(3600)
            or policy.fallback_initial_delay_seconds < 0
            or policy.fallback_maximum_delay_seconds > Decimal(300)
            or policy.fallback_maximum_delay_seconds
            < policy.fallback_initial_delay_seconds
        ):
            raise MarketDataError("retry_policy_invalid")

        calendar = _plain(request.calendar_manifest)
        census = _plain(request.candidate_census)
        semantics = _plain(request.bar_semantics_manifest)
        try:
            validate_contract("CalendarManifest", calendar)
            verify_content_hash("CalendarManifest", calendar)
            validate_contract("CandidateCensus", census)
            validate_contract("BarSemanticsManifest", semantics)
        except ContractValidationError:
            raise MarketDataError("pinned_market_data_contract_invalid") from None
        if calendar["timezone"] != "America/New_York":
            raise MarketDataError("calendar_timezone_invalid")
        sessions = tuple(calendar["sessions"])
        if (
            tuple(sorted(set(sessions))) != sessions
            or request.start not in sessions
            or request.end not in sessions
            or request.asof not in sessions
            or census["session_id"] != request.asof
        ):
            raise MarketDataError("calendar_or_asof_session_invalid")
        if (
            semantics["provider"] != "alpaca"
            or semantics["feed"] != request.feed
            or semantics["timeframe"] != request.timeframe
            or semantics["interval_timezone"] != "America/New_York"
            or not semantics["revision_policy"].strip()
            or not semantics["finalization_rule"].strip()
        ):
            raise MarketDataError("bar_semantics_manifest_mismatch")
        meanings = " ".join(semantics["field_meanings"]).casefold()
        if (
            "volume" not in meanings
            or "auction" not in meanings
            or "extended" not in meanings
            or (request.feed == "IEX" and "iex" not in meanings)
        ):
            raise MarketDataError("bar_semantics_field_meanings_incomplete")
        if cutoff.date() < start:
            raise MarketDataError("data_cutoff_precedes_history")
        if (
            _parse_date(request.action_process_start, "action_process_start")
            > _parse_date(request.action_process_end, "action_process_end")
            or _parse_date(request.action_process_end, "action_process_end") > asof
        ):
            raise MarketDataError("corporate_action_process_range_invalid")

        instrument_by_id: dict[str, Mapping[str, Any]] = {}
        for instrument in request.instrument_records:
            value = _plain(instrument)
            try:
                validate_contract("Instrument", value)
            except ContractValidationError:
                raise MarketDataError("instrument_contract_invalid") from None
            if value["id"] in instrument_by_id:
                raise MarketDataError("instrument_id_duplicate")
            instrument_by_id[value["id"]] = value
        if not instrument_by_id:
            raise MarketDataError("instrument_bindings_empty")

        assignments: dict[str, Mapping[str, Any]] = {}
        symbol_instrument_ids: dict[str, str] = {}
        for assignment in request.symbol_assignments:
            value = _plain(assignment)
            try:
                validate_contract("SymbolAssignment", value)
            except ContractValidationError:
                raise MarketDataError("symbol_assignment_invalid") from None
            symbol = value["symbol"]
            instrument_id = value["instrument_ref"]["target_id"]
            if (
                symbol in assignments
                or instrument_id not in instrument_by_id
                or value["currency"] != request.currency
                or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,19}", symbol)
            ):
                raise MarketDataError("symbol_assignment_binding_invalid")
            if not (
                _parse_date(value["effective_from"], "effective_from") <= asof
                and (
                    value["effective_to"] is None
                    or asof < _parse_date(value["effective_to"], "effective_to")
                )
                and _parse_utc(value["known_from"], "known_from") <= cutoff
                and (
                    value["known_to"] is None
                    or cutoff < _parse_utc(value["known_to"], "known_to")
                )
            ):
                raise MarketDataError("symbol_assignment_not_known_at_asof")
            assignments[symbol] = value
            symbol_instrument_ids[symbol] = instrument_id
        if set(assignments) != set(request.expected_sessions_by_symbol):
            raise MarketDataError("expected_symbol_inventory_mismatch")

        census_ids = {
            item["target_id"] for item in census["instrument_refs"]
        }
        if census_ids != set(instrument_by_id):
            raise MarketDataError("candidate_census_instrument_mismatch")
        all_expected_sessions: set[str] = set()
        for symbol, required_sessions in request.expected_sessions_by_symbol.items():
            if (
                not required_sessions
                or tuple(sorted(set(required_sessions))) != required_sessions
                or any(
                    session not in sessions
                    or not request.start <= session <= request.end
                    for session in required_sessions
                )
            ):
                raise MarketDataError("expected_session_inventory_invalid")
            all_expected_sessions.update(required_sessions)
        if set(request.finalization_deadlines) != all_expected_sessions:
            raise MarketDataError("finalization_deadline_inventory_mismatch")
        for session, value in request.finalization_deadlines.items():
            _parse_date(session, "finalization_session")
            _parse_utc(value, "finalization_deadline")
        if (
            _parse_date(request.action_process_end, "action_process_end")
            > _parse_utc(request.cutoff, "cutoff").astimezone(NEW_YORK).date()
        ):
            raise MarketDataError("corporate_action_process_end_after_cutoff")

        required_inputs = [
            ("CalendarManifest", calendar),
            ("CandidateCensus", census),
            ("BarSemanticsManifest", semantics),
            *(("Instrument", _plain(value)) for value in request.instrument_records),
            *(("SymbolAssignment", _plain(value)) for value in request.symbol_assignments),
        ]
        provided = {
            (name, _plain(value).get("id")): _plain(value)
            for name, value in request.supporting_objects
        }
        for name, value in required_inputs:
            if provided.get((name, value["id"])) != value:
                raise MarketDataError("supporting_reference_closure_missing")
        for version in request.known_action_versions:
            try:
                validate_contract("CorporateActionRecord", _plain(version.contract))
            except ContractValidationError:
                raise MarketDataError("known_corporate_action_invalid") from None
            if version.contract["terms_hash"] != version.terms_hash:
                raise MarketDataError("known_corporate_action_version_mismatch")
            if provided.get(
                ("CorporateActionRecord", version.contract["id"])
            ) != _plain(version.contract):
                raise MarketDataError("known_corporate_action_reference_closure_missing")
        if request.quarantine_evidence_ref is not None:
            evidence_id = request.quarantine_evidence_ref.get("target_id")
            evidence = provided.get(("EvidenceEvent", evidence_id))
            if evidence is None:
                raise MarketDataError("quarantine_evidence_contract_missing")
            try:
                validate_contract("EvidenceEvent", evidence)
                verify_content_hash("EvidenceEvent", evidence)
            except ContractValidationError:
                raise MarketDataError("quarantine_evidence_contract_invalid") from None
            if _plain(request.quarantine_evidence_ref) != _reference(
                "EvidenceEvent", evidence
            ):
                raise MarketDataError("quarantine_evidence_reference_hash_mismatch")
        try:
            validate_contract_collection(
                [(name, _plain(value)) for name, value in request.supporting_objects]
            )
        except ContractValidationError:
            raise MarketDataError("supporting_reference_closure_invalid") from None

    def _fetch_pages(
        self,
        *,
        request: MarketDataRequest,
        operation: str,
        path: str,
        base_params: Mapping[str, str],
        extractor: Callable[
            [Mapping[str, Any], Mapping[str, Any], str],
            list[_FetchedRow],
        ],
    ) -> _FetchResult:
        result = _FetchResult()
        token: str | None = None
        seen_tokens: set[str] = set()
        seen_pages: set[str] = set()
        page_count = 0
        while True:
            if page_count >= request.retry_policy.maximum_pages:
                result.failures.append("pagination_page_limit_exceeded")
                break
            params = dict(base_params)
            if token is not None:
                params["page_token"] = token
            manifest, request_evidence, request_hash = self._create_request_manifest(
                request, operation, path, params
            )
            result.request_manifests.append(manifest)
            result.request_evidence.append(request_evidence)
            stored_request = self._store.put(
                f"requests/{request_hash}.json",
                canonical_json_bytes(request_evidence.descriptor),
                "application/json",
            )
            self._add_artifact(
                stored_request,
                "qc2.market_data.sanitized_request.v1",
                "1",
                result.artifacts,
            )

            successful_response: tuple[HttpResponse, Mapping[str, Any], str] | None = None
            total_wait = Decimal(0)
            for attempt in range(1, request.retry_policy.maximum_attempts + 1):
                if _parse_utc(self._clock(), "clock") >= _parse_utc(
                    request.session_deadline_at, "session_deadline_at"
                ):
                    result.failures.append("session_deadline_exceeded")
                    break
                try:
                    response = self._transport.get(path, params)
                except MarketDataError as exc:
                    result.failures.append(exc.code)
                    break
                except Exception:
                    result.failures.append("transport_error")
                    break
                received_at = _format_utc(_parse_utc(self._clock(), "clock"))
                if not isinstance(response.body, bytes):
                    result.failures.append("response_body_type_invalid")
                    break
                receipt = self._create_raw_receipt(
                    request, manifest, response, received_at, result
                )
                result.raw_receipts.append(receipt)
                headers = _normalized_headers(response.headers)
                content_type = headers.get("content-type")
                media_type = (
                    content_type.split(";", 1)[0].strip().lower()
                    if content_type
                    else "application/octet-stream"
                )
                if "content-length" in headers:
                    try:
                        declared_length = int(headers["content-length"])
                    except ValueError:
                        result.failures.append("response_content_length_invalid")
                        declared_length = -1
                    if declared_length != len(response.body):
                        result.failures.append("response_truncated")
                        self._store_response_metadata(
                            request_hash,
                            attempt,
                            response,
                            received_at,
                            None,
                            result,
                        )
                        break

                delay: Decimal | None = None
                if response.status_code == 429 and attempt < request.retry_policy.maximum_attempts:
                    try:
                        delay = self._retry_delay(
                            request,
                            headers,
                            attempt,
                            total_wait,
                            received_at,
                        )
                    except MarketDataError as exc:
                        result.failures.append(exc.code)
                self._observe_rate_limit(
                    request_hash,
                    response,
                    headers,
                    delay,
                    result,
                )
                self._store_response_metadata(
                    request_hash, attempt, response, received_at, delay, result
                )

                if response.status_code == 429:
                    if attempt >= request.retry_policy.maximum_attempts:
                        result.failures.append("rate_limit_retry_exhausted")
                        break
                    if delay is None:
                        if not result.failures or result.failures[-1] not in {
                            "rate_limit_header_invalid",
                            "rate_limit_wait_exceeds_policy",
                            "session_deadline_exceeded",
                        }:
                            result.failures.append("rate_limit_retry_unavailable")
                        break
                    total_wait += delay
                    try:
                        self._sleeper(float(delay))
                    except Exception:
                        result.failures.append("retry_wait_failed")
                        break
                    continue

                if response.status_code == 403:
                    result.failures.append("alpaca_forbidden")
                    break
                if response.status_code == 401:
                    result.failures.append("alpaca_unauthorized")
                    break
                if response.status_code != 200:
                    result.failures.append(f"alpaca_http_{response.status_code}")
                    break
                if content_type is None:
                    result.failures.append("response_content_type_missing")
                    break
                if media_type != "application/json":
                    result.failures.append("response_content_type_unsupported")
                    break
                if request.evidence_class in {
                    "FORWARD_OPERATIONAL",
                    "FORWARD_SEALED",
                } and _parse_utc(received_at, "received_at") > _parse_utc(
                    request.cutoff, "cutoff"
                ):
                    result.failures.append("response_received_after_cutoff")
                    break
                try:
                    document = _strict_provider_json(response.body)
                except MarketDataError as exc:
                    result.failures.append(exc.code)
                    break
                if not isinstance(document, Mapping):
                    result.failures.append("provider_response_root_invalid")
                    break
                if "next_page_token" not in document:
                    result.failures.append("pagination_terminal_token_missing")
                    break
                digest = hashlib.sha256(response.body).hexdigest()
                if digest in seen_pages:
                    result.failures.append("duplicate_response_page")
                    break
                seen_pages.add(digest)
                try:
                    page_rows = extractor(document, _reference("RawReceipt", receipt), received_at)
                except MarketDataError as exc:
                    result.failures.append(exc.code)
                    break
                result.rows.extend(page_rows)
                successful_response = (
                    response,
                    document,
                    received_at,
                )
                break

            if successful_response is None:
                break
            page_count += 1
            next_token = successful_response[1]["next_page_token"]
            if next_token is None:
                result.terminal_token_verified = True
                break
            if not isinstance(next_token, str) or not next_token:
                result.failures.append("pagination_token_invalid")
                break
            if next_token in seen_tokens:
                result.failures.append("repeated_page_token")
                break
            seen_tokens.add(next_token)
            token = next_token
        return result

    def _create_request_manifest(
        self,
        request: MarketDataRequest,
        operation: str,
        path: str,
        params: Mapping[str, str],
    ) -> tuple[Mapping[str, Any], SanitizedRequestEvidence, str]:
        descriptor = {
            "adjustment": request.adjustment,
            "asof": request.asof,
            "cutoff": request.cutoff,
            "deadline_at": request.session_deadline_at,
            "feed": request.feed,
            "mapping_policy": request.mapping_policy,
            "method": "GET",
            "operation": operation,
            "page_limit": request.page_limit,
            "path": path,
            "provider": request.provider,
            "query": dict(sorted(params.items())),
            "retry_policy": {
                "fallback_initial_delay_seconds": _format_decimal(
                    request.retry_policy.fallback_initial_delay_seconds
                ),
                "fallback_maximum_delay_seconds": _format_decimal(
                    request.retry_policy.fallback_maximum_delay_seconds
                ),
                "maximum_attempts": request.retry_policy.maximum_attempts,
                "maximum_pages": request.retry_policy.maximum_pages,
                "maximum_total_wait_seconds": _format_decimal(
                    request.retry_policy.maximum_total_wait_seconds
                ),
            },
            "timeframe": request.timeframe,
        }
        descriptor_bytes = canonical_json_bytes(descriptor)
        request_hash = hashlib.sha256(descriptor_bytes).hexdigest()
        manifest = self._contract(
            "RequestManifest",
            request,
            {
                "provider": request.provider,
                "feed": request.feed,
                "adjustment": request.adjustment,
                "timeframe": request.timeframe,
                "currency": request.currency,
                "calendar_ref": _reference("CalendarManifest", request.calendar_manifest),
                "bar_semantics_ref": _reference(
                    "BarSemanticsManifest", request.bar_semantics_manifest
                ),
                "cutoff": request.cutoff,
                "sanitized_request_hash": request_hash,
            },
        )
        stored = self._store.put(
            f"requests/{request_hash}.json", descriptor_bytes, "application/json"
        )
        evidence = SanitizedRequestEvidence(
            request_ref=_reference("RequestManifest", manifest),
            request_hash=request_hash,
            storage_ref=stored.storage_ref,
            descriptor=descriptor,
        )
        return manifest, evidence, request_hash

    def _create_raw_receipt(
        self,
        request: MarketDataRequest,
        manifest: Mapping[str, Any],
        response: HttpResponse,
        received_at: str,
        result: _FetchResult,
    ) -> Mapping[str, Any]:
        headers = _normalized_headers(response.headers)
        content_type = headers.get("content-type")
        media_type = (
            content_type.split(";", 1)[0].strip().lower()
            if content_type
            else "application/octet-stream"
        )
        digest = hashlib.sha256(response.body).hexdigest()
        stored = self._store.put(f"raw/{digest}.bin", response.body, media_type)
        self._add_artifact(
            stored,
            f"urn:qc2:provider:alpaca.{_path_family(manifest)}.raw.v1",
            "1",
            result.artifacts,
        )
        return self._contract(
            "RawReceipt",
            request,
            {
                "request_ref": _reference("RequestManifest", manifest),
                "provider": request.provider,
                "received_at": received_at,
                "media_type": media_type,
                "byte_length": len(response.body),
                "raw_sha256": digest,
                "storage_ref": stored.storage_ref,
            },
        )

    def _store_response_metadata(
        self,
        request_hash: str,
        attempt: int,
        response: HttpResponse,
        received_at: str,
        delay: Decimal | None,
        result: _FetchResult,
    ) -> None:
        headers = {
            key: value
            for key, value in _normalized_headers(response.headers).items()
            if key in _SAFE_RESPONSE_HEADERS
        }
        body = canonical_json_bytes(
            {
                "attempt": attempt,
                "headers": headers,
                "received_at": received_at,
                "request_hash": request_hash,
                "retry_delay_seconds": _format_decimal(delay)
                if delay is not None
                else None,
                "status_code": response.status_code,
            }
        )
        stored = self._store.put(
            f"transport-meta/{request_hash}/{attempt}-{hashlib.sha256(body).hexdigest()}.json",
            body,
            "application/json",
        )
        self._add_artifact(
            stored,
            "qc2.market_data.transport_response_metadata.v1",
            "1",
            result.artifacts,
        )

    def _retry_delay(
        self,
        request: MarketDataRequest,
        headers: Mapping[str, str],
        attempt: int,
        total_wait: Decimal,
        received_at: str,
    ) -> Decimal:
        raw_retry_after = headers.get("retry-after")
        raw_reset = headers.get("x-ratelimit-reset")
        delay: Decimal
        if raw_retry_after is not None:
            try:
                delay = Decimal(raw_retry_after)
            except InvalidOperation:
                try:
                    target = parsedate_to_datetime(raw_retry_after)
                    if target.tzinfo is None:
                        raise ValueError
                    delay = Decimal(
                        str(
                            max(
                                0,
                                target.astimezone(UTC).timestamp()
                                - _parse_utc(received_at, "received_at").timestamp(),
                            )
                        )
                    )
                except (TypeError, ValueError, OverflowError):
                    raise MarketDataError("rate_limit_header_invalid") from None
        elif raw_reset is not None:
            try:
                reset = Decimal(raw_reset)
                delay = max(
                    Decimal(0),
                    reset
                    - Decimal(
                        str(_parse_utc(received_at, "received_at").timestamp())
                    ),
                )
            except InvalidOperation:
                raise MarketDataError("rate_limit_header_invalid") from None
        else:
            delay = min(
                request.retry_policy.fallback_initial_delay_seconds
                * (Decimal(2) ** (attempt - 1)),
                request.retry_policy.fallback_maximum_delay_seconds,
            )
        if not delay.is_finite() or delay < 0:
            raise MarketDataError("rate_limit_header_invalid")
        deadline_remaining = Decimal(
            str(
                (
                    _parse_utc(request.session_deadline_at, "session_deadline_at")
                    - _parse_utc(received_at, "received_at")
                ).total_seconds()
            )
        )
        if (
            total_wait + delay > request.retry_policy.maximum_total_wait_seconds
            or delay > deadline_remaining
        ):
            raise MarketDataError("rate_limit_wait_exceeds_policy")
        return delay

    def _observe_rate_limit(
        self,
        request_hash: str,
        response: HttpResponse,
        headers: Mapping[str, str],
        delay: Decimal | None,
        result: _FetchResult,
    ) -> None:
        if any(
            key in headers
            for key in (
                "x-ratelimit-limit",
                "x-ratelimit-remaining",
                "x-ratelimit-reset",
                "retry-after",
            )
        ) or response.status_code == 429:
            result.rate_limits.append(
                RateLimitObservation(
                    request_hash=request_hash,
                    status_code=response.status_code,
                    limit=headers.get("x-ratelimit-limit"),
                    remaining=headers.get("x-ratelimit-remaining"),
                    reset_epoch=headers.get("x-ratelimit-reset"),
                    retry_after=headers.get("retry-after"),
                    retry_delay_seconds=_format_decimal(delay)
                    if delay is not None
                    else None,
                )
            )

    def _extract_bar_rows(
        self,
        document: Mapping[str, Any],
        receipt_ref: Mapping[str, Any],
        received_at: str,
    ) -> list[_FetchedRow]:
        bars = document.get("bars")
        if not isinstance(bars, Mapping):
            raise MarketDataError("bar_page_shape_invalid")
        output: list[_FetchedRow] = []
        for symbol, values in bars.items():
            if not isinstance(symbol, str) or not isinstance(values, list):
                raise MarketDataError("bar_symbol_page_shape_invalid")
            for value in values:
                if not isinstance(value, Mapping):
                    raise MarketDataError("bar_observation_shape_invalid")
                output.append(
                    _FetchedRow(
                        group="bars",
                        symbol=symbol,
                        value=value,
                        receipt_ref=receipt_ref,
                        observed_at=received_at,
                    )
                )
        return output

    def _extract_action_rows(
        self,
        document: Mapping[str, Any],
        receipt_ref: Mapping[str, Any],
        received_at: str,
    ) -> list[_FetchedRow]:
        actions = document.get("corporate_actions")
        if not isinstance(actions, Mapping):
            raise MarketDataError("corporate_action_page_shape_invalid")
        unknown_groups = set(actions) - set(_ACTION_GROUPS)
        if unknown_groups:
            raise MarketDataError("corporate_action_group_unknown")
        output: list[_FetchedRow] = []
        for group, values in actions.items():
            if not isinstance(values, list):
                raise MarketDataError("corporate_action_group_shape_invalid")
            for value in values:
                if not isinstance(value, Mapping):
                    raise MarketDataError("corporate_action_observation_shape_invalid")
                symbol = (
                    value.get("symbol")
                    or value.get("acquiree_symbol")
                    or value.get("old_symbol")
                    or ""
                )
                output.append(
                    _FetchedRow(
                        group=group,
                        symbol=str(symbol),
                        value=value,
                        receipt_ref=receipt_ref,
                        observed_at=received_at,
                    )
                )
        return output

    def _normalize_bars(
        self,
        request: MarketDataRequest,
        rows: list[_FetchedRow],
    ) -> tuple[
        list[Mapping[str, Any]],
        list[Mapping[str, Any]],
        list[DataAnomaly],
        list[str],
    ]:
        observations: dict[tuple[str, str], list[_BarObservation]] = defaultdict(list)
        failures: list[str] = []
        anomalies: list[DataAnomaly] = []
        instrument_ids = self._instrument_id_by_symbol(request)
        for row in rows:
            if row.symbol not in instrument_ids:
                failures.append("unexpected_provider_symbol")
                anomalies.append(
                    self._anomaly(
                        "unexpected_provider_symbol",
                        row.symbol,
                        None,
                        [row.receipt_ref],
                        row.value,
                    )
                )
                continue
            try:
                source_timestamp = _required_string(row.value, "t")
                timestamp = _parse_utc(source_timestamp, "bar_timestamp")
                local_timestamp = timestamp.astimezone(NEW_YORK)
                if (
                    local_timestamp.hour
                    or local_timestamp.minute
                    or local_timestamp.second
                    or local_timestamp.microsecond
                ):
                    raise MarketDataError("bar_timestamp_precision_invalid")
                session_id = local_timestamp.date().isoformat()
                if not request.start <= session_id <= request.end:
                    raise MarketDataError("bar_outside_requested_range")
                if session_id not in request.expected_sessions_by_symbol[row.symbol]:
                    raise MarketDataError("bar_outside_expected_sessions")
                values = (
                    _decimal_value(row.value.get("o"), "open"),
                    _decimal_value(row.value.get("h"), "high"),
                    _decimal_value(row.value.get("l"), "low"),
                    _decimal_value(row.value.get("c"), "close"),
                    _decimal_value(row.value.get("v"), "volume"),
                )
                opening, high, low, close, volume = values
                if any(not value.is_finite() for value in values):
                    raise MarketDataError("bar_numeric_value_non_finite")
                if min(opening, high, low, close) <= 0:
                    raise MarketDataError("bar_price_not_positive")
                if volume < 0:
                    raise MarketDataError("bar_volume_negative")
                if low > min(opening, close) or high < max(opening, close) or low > high:
                    raise MarketDataError("invalid_ohlc_ordering")
                fingerprint_body = canonical_json_bytes(
                    {
                        "close": _format_decimal(close),
                        "high": _format_decimal(high),
                        "low": _format_decimal(low),
                        "open": _format_decimal(opening),
                        "session_id": session_id,
                        "symbol": row.symbol,
                        "volume": _format_decimal(volume),
                    }
                )
                fingerprint = hashlib.sha256(fingerprint_body).hexdigest()
                observations[(row.symbol, session_id)].append(
                    _BarObservation(
                        symbol=row.symbol,
                        session_id=session_id,
                        values=values,
                        fingerprint=fingerprint,
                        receipt_ref=row.receipt_ref,
                        observed_at=row.observed_at,
                        source_timestamp=source_timestamp,
                    )
                )
            except (MarketDataError, ContractValidationError) as exc:
                reason = exc.code if isinstance(exc, MarketDataError) else "bar_value_invalid"
                failures.append(reason)
                anomalies.append(
                    self._anomaly(
                        reason,
                        row.symbol,
                        None,
                        [row.receipt_ref],
                        row.value,
                    )
                )

        bars: list[Mapping[str, Any]] = []
        quarantines: list[Mapping[str, Any]] = []
        for (symbol, session_id), candidates in sorted(observations.items()):
            fingerprints = {candidate.fingerprint for candidate in candidates}
            duplicate_receipts = _unique_refs(
                candidate.receipt_ref for candidate in candidates
            )
            conflict = len(fingerprints) > 1
            if len(candidates) > 1:
                reason = (
                    "conflicting_duplicate_bar"
                    if conflict
                    else "duplicate_bar_observation"
                )
                anomalies.append(
                    self._anomaly(
                        reason,
                        symbol,
                        session_id,
                        duplicate_receipts,
                        sorted(fingerprints),
                    )
                )
                failures.append(reason)
            chosen = min(candidates, key=lambda candidate: candidate.fingerprint)
            opening, high, low, close, volume = chosen.values
            finalization_deadline = _parse_utc(
                request.finalization_deadlines[session_id],
                "finalization_deadline",
            )
            is_final = _parse_utc(request.cutoff, "cutoff") >= finalization_deadline
            status = "QUARANTINED" if conflict else ("FINAL" if is_final else "PROVISIONAL")
            bar = self._contract(
                "DailyBar",
                request,
                {
                    "instrument_ref": _reference(
                        "Instrument", self._instrument_by_id(request)[instrument_ids[symbol]]
                    ),
                    "session_id": session_id,
                    "feed": request.feed,
                    "currency": request.currency,
                    "open_price": _format_decimal(opening),
                    "high_price": _format_decimal(high),
                    "low_price": _format_decimal(low),
                    "close_price": _format_decimal(close),
                    "volume": _format_decimal(volume),
                    "observed_at": max(candidate.observed_at for candidate in candidates),
                    "finalized_at": _format_utc(finalization_deadline) if is_final else None,
                    "bar_status": status,
                    "source_refs": duplicate_receipts,
                },
            )
            try:
                validate_contract("DailyBar", _plain(bar))
            except ContractValidationError:
                failures.append("normalized_daily_bar_invalid")
                anomalies.append(
                    self._anomaly(
                        "normalized_daily_bar_invalid",
                        symbol,
                        session_id,
                        duplicate_receipts,
                        _plain(bar),
                    )
                )
                continue
            bars.append(bar)
            if conflict:
                if request.quarantine_evidence_ref is None:
                    failures.append("quarantine_evidence_ref_required")
                else:
                    quarantines.append(
                        self._contract(
                            "QuarantineCase",
                            request,
                            {
                                "instrument_ref": _reference(
                                    "Instrument",
                                    self._instrument_by_id(request)[instrument_ids[symbol]],
                                ),
                                "observation_ref": _reference("DailyBar", bar),
                                "rule_id": "unique_bar_key",
                                "reason_code": "conflicting_duplicate_bar",
                                "observed_at": max(
                                    candidate.observed_at for candidate in candidates
                                ),
                                "disposition": "PENDING_REVIEW",
                                "evidence_ref": _plain(request.quarantine_evidence_ref),
                                "source_refs": duplicate_receipts,
                            },
                        )
                    )
        return bars, quarantines, anomalies, failures

    def _normalize_actions(
        self,
        request: MarketDataRequest,
        rows: list[_FetchedRow],
    ) -> tuple[list[CorporateActionVersion], list[DataAnomaly], list[str]]:
        failures: list[str] = []
        anomalies: list[DataAnomaly] = []
        instruments = self._instrument_id_by_symbol(request)
        preliminary: list[_ActionObservation] = []
        for row in rows:
            if row.symbol not in instruments:
                failures.append("corporate_action_symbol_unmapped")
                anomalies.append(
                    self._anomaly(
                        "corporate_action_symbol_unmapped",
                        row.symbol,
                        None,
                        [row.receipt_ref],
                        row.value,
                    )
                )
                continue
            action_type, is_split = _ACTION_GROUPS[row.group]
            provider_action_id = row.value.get("id")
            if not isinstance(provider_action_id, str) or not provider_action_id:
                failures.append("corporate_action_id_missing")
                anomalies.append(
                    self._anomaly(
                        "corporate_action_id_missing",
                        row.symbol,
                        None,
                        [row.receipt_ref],
                        row.value,
                    )
                )
                continue
            effective_value = row.value.get("ex_date", row.value.get("effective_date"))
            try:
                effective_session = _parse_date(effective_value, "corporate_action_effective_date").isoformat()
            except MarketDataError as exc:
                failures.append(exc.code)
                anomalies.append(
                    self._anomaly(
                        exc.code,
                        row.symbol,
                        None,
                        [row.receipt_ref],
                        row.value,
                    )
                )
                continue
            processing_session: str | None = None
            if row.value.get("process_date") is not None:
                try:
                    processing_session = _parse_date(
                        row.value["process_date"], "corporate_action_process_date"
                    ).isoformat()
                except MarketDataError as exc:
                    failures.append(exc.code)
                    anomalies.append(
                        self._anomaly(
                            exc.code,
                            row.symbol,
                            effective_session,
                            [row.receipt_ref],
                            row.value,
                        )
                    )
                    continue
            new_rate: Decimal | None = None
            old_rate: Decimal | None = None
            certainty = "UNCERTAIN"
            if is_split:
                try:
                    new_rate = _decimal_value(row.value.get("new_rate"), "new_rate")
                    old_rate = _decimal_value(row.value.get("old_rate"), "old_rate")
                    if new_rate <= 0 or old_rate <= 0:
                        raise MarketDataError("corporate_action_split_rate_invalid")
                    ratio = new_rate / old_rate
                    expected_direction = (
                        ratio > 1 if action_type == "SPLIT" else ratio < 1
                    )
                    if not expected_direction:
                        raise MarketDataError("corporate_action_split_direction_invalid")
                    certainty = "VERIFIED"
                except (MarketDataError, InvalidOperation) as exc:
                    code = (
                        exc.code
                        if isinstance(exc, MarketDataError)
                        else "corporate_action_split_rate_invalid"
                    )
                    failures.append(code)
                    certainty = "UNCERTAIN"
                    new_rate = None
                    old_rate = None
            terms_hash = hashlib.sha256(
                canonical_json_bytes(_hash_material(row.value))
            ).hexdigest()
            core_terms_hash = terms_hash
            preliminary.append(
                _ActionObservation(
                    provider_action_id=provider_action_id,
                    symbol=row.symbol,
                    action_type=action_type,
                    is_split=is_split,
                    effective_session=effective_session,
                    processing_session=processing_session,
                    observed_at=row.observed_at,
                    terms_hash=terms_hash,
                    core_terms_hash=core_terms_hash,
                    receipt_ref=row.receipt_ref,
                    new_rate=new_rate,
                    old_rate=old_rate,
                    certainty=certainty,
                )
            )

        known_by_key = {
            (version.provider_action_id, version.terms_hash): version
            for version in request.known_action_versions
        }
        core_hashes: dict[str, set[str]] = defaultdict(set)
        for version in request.known_action_versions:
            core_hashes[version.provider_action_id].add(version.core_terms_hash)
        for observation in preliminary:
            core_hashes[observation.provider_action_id].add(observation.core_terms_hash)

        unique_observations: dict[tuple[str, str], _ActionObservation] = {}
        for observation in preliminary:
            key = (observation.provider_action_id, observation.terms_hash)
            unique_observations.setdefault(key, observation)
        versions = list(request.known_action_versions)
        for key, observation in sorted(unique_observations.items()):
            if key in known_by_key:
                continue
            conflicted = len(core_hashes[observation.provider_action_id]) > 1
            uncertainty = (
                "CONFLICTED"
                if conflicted
                else observation.certainty
                if observation.is_split
                else "UNCERTAIN"
            )
            instrument = self._instrument_by_id(request)[instruments[observation.symbol]]
            record = self._contract(
                "CorporateActionRecord",
                request,
                {
                    "instrument_ref": _reference("Instrument", instrument),
                    "action_type": observation.action_type,
                    "effective_session": observation.effective_session,
                    "observed_at": observation.observed_at,
                    "processing_session": observation.processing_session,
                    "terms_hash": observation.terms_hash,
                    "uncertainty": uncertainty,
                    "source_refs": [observation.receipt_ref],
                },
            )
            versions.append(
                CorporateActionVersion(
                    provider_action_id=observation.provider_action_id,
                    terms_hash=observation.terms_hash,
                    observed_at=observation.observed_at,
                    contract=record,
                    core_terms_hash=observation.core_terms_hash,
                    split_new_rate=observation.new_rate,
                    split_old_rate=observation.old_rate,
                )
            )
        versions.sort(
            key=lambda value: (
                value.provider_action_id,
                value.observed_at,
                value.terms_hash,
            )
        )
        return versions, anomalies, failures

    def _split_adjusted_views(
        self,
        request: MarketDataRequest,
        bars: list[Mapping[str, Any]],
        versions: list[CorporateActionVersion],
        action_pages_terminal: bool,
        action_failures: list[str],
    ) -> tuple[list[Mapping[str, Any]], list[SplitAdjustedBar], list[str]]:
        adjustments: list[Mapping[str, Any]] = []
        views: list[SplitAdjustedBar] = []
        failures: list[str] = []
        if not action_pages_terminal:
            return adjustments, views, ["corporate_action_pagination_incomplete"]
        if action_failures:
            return adjustments, views, ["corporate_action_coverage_uncertain"]

        basis_session = request.candidate_census["session_id"]
        cutoff = _parse_utc(request.cutoff, "cutoff")
        for bar in bars:
            if bar["bar_status"] != "FINAL":
                continue
            instrument_id = bar["instrument_ref"]["target_id"]
            candidate_versions = [
                version
                for version in versions
                if version.contract["instrument_ref"]["target_id"] == instrument_id
                and bar["session_id"] < version.contract["effective_session"] <= basis_session
            ]
            available = [
                version
                for version in candidate_versions
                if _parse_utc(version.observed_at, "action_observed_at") <= cutoff
            ]
            future_only = [
                version for version in candidate_versions if version not in available
            ]
            if future_only:
                failures.append("corporate_action_version_after_cutoff")
            eligible_splits = [
                version
                for version in available
                if version.contract["action_type"] in {"SPLIT", "REVERSE_SPLIT"}
            ]
            if any(version.contract["uncertainty"] == "CONFLICTED" for version in eligible_splits):
                failures.append("corporate_action_review_required")
                continue
            if any(
                version.contract["action_type"] in _UNSUPPORTED_PRICE_BASIS_ACTIONS
                and version.contract["uncertainty"] != "CONFLICTED"
                for version in available
            ):
                failures.append("corporate_action_review_required")
                continue
            if any(
                version.contract["uncertainty"] != "VERIFIED"
                for version in eligible_splits
            ):
                failures.append("corporate_action_split_uncertain")
                continue
            price_factor = Decimal(1)
            volume_factor = Decimal(1)
            for version in eligible_splits:
                if version.split_new_rate is None or version.split_old_rate is None:
                    failures.append("corporate_action_split_terms_missing")
                    continue
                price_factor *= version.split_old_rate / version.split_new_rate
                volume_factor *= version.split_new_rate / version.split_old_rate
            action_refs = [
                _reference("CorporateActionRecord", value.contract)
                for value in available
            ]
            availability_time = (
                max(
                    (_parse_utc(value.observed_at, "action_observed_at") for value in available),
                    default=cutoff,
                )
            )
            manifest = self._contract(
                "AdjustmentManifest",
                request,
                {
                    "basis_session": basis_session,
                    "action_refs": action_refs,
                    "price_factor": _format_decimal(price_factor),
                    "volume_factor": _format_decimal(volume_factor),
                    "methodology_version": 1,
                    "available_at": _format_utc(availability_time),
                    "source_refs": [
                        _reference("DailyBar", bar),
                        *action_refs,
                    ],
                },
            )
            adjusted = SplitAdjustedBar(
                raw_bar_ref=_reference("DailyBar", bar),
                adjustment_manifest_ref=_reference("AdjustmentManifest", manifest),
                basis_session=basis_session,
                open_price=_format_decimal(Decimal(bar["open_price"]) * price_factor),
                high_price=_format_decimal(Decimal(bar["high_price"]) * price_factor),
                low_price=_format_decimal(Decimal(bar["low_price"]) * price_factor),
                close_price=_format_decimal(Decimal(bar["close_price"]) * price_factor),
                volume=_format_decimal(Decimal(bar["volume"]) * volume_factor),
                adjustment_status=(
                    "FUTURE_ACTION_VERSION_EXCLUDED"
                    if future_only
                    else "KNOWN_ACTIONS_ONLY"
                    if available
                    else "ACTION_ABSENCE_UNVERIFIED"
                ),
            )
            adjustments.append(manifest)
            views.append(adjusted)
        return adjustments, views, failures

    def _bundle_source_refs(
        self,
        request: MarketDataRequest,
        versions: list[CorporateActionVersion],
        adjustments: list[Mapping[str, Any]],
        quarantines: list[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        refs: list[Mapping[str, Any]] = [
            _reference("BarSemanticsManifest", request.bar_semantics_manifest)
        ]
        refs.extend(
            _reference("CorporateActionRecord", version.contract)
            for version in versions
            if _parse_utc(version.observed_at, "action_observed_at")
            <= _parse_utc(request.cutoff, "cutoff")
        )
        refs.extend(_reference("AdjustmentManifest", item) for item in adjustments)
        refs.extend(_reference("QuarantineCase", item) for item in quarantines)
        return _unique_refs(refs)

    def _instrument_by_id(self, request: MarketDataRequest) -> dict[str, Mapping[str, Any]]:
        return {value["id"]: _plain(value) for value in request.instrument_records}

    def _instrument_id_by_symbol(self, request: MarketDataRequest) -> dict[str, str]:
        return {
            value["symbol"]: value["instrument_ref"]["target_id"]
            for value in request.symbol_assignments
        }

    def _contract(
        self,
        name: str,
        request: MarketDataRequest,
        values: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        metadata = {
            "schema_name": CONTRACTS[name][1],
            "schema_version": "1.0",
            "id": self._id_factory(),
            "created_at": _format_utc(_parse_utc(self._clock(), "clock")),
            "owning_authority": AUTHORITY_OVERRIDES[name],
            "evidence_class": request.evidence_class,
            "environment_namespace": request.environment_namespace,
            "source_refs": [],
        }
        metadata.update(_plain(values))
        try:
            validate_contract(name, metadata)
        except ContractValidationError:
            raise MarketDataError(f"generated_{name.lower()}_invalid") from None
        return metadata

    def _store_contract_artifact(
        self,
        name: str,
        contract: Mapping[str, Any],
        artifacts: list[dict[str, Any]],
        *,
        include: bool = True,
    ) -> None:
        body = canonical_json_bytes(_plain(contract))
        stored = self._store.put(
            f"contracts/{name}/{contract['id']}.json", body, "application/json"
        )
        if include:
            self._add_artifact(stored, CONTRACTS[name][1], "1.0", artifacts)

    def _store_request_dependencies(
        self,
        request: MarketDataRequest,
        artifacts: list[dict[str, Any]],
    ) -> None:
        required = [
            ("CalendarManifest", request.calendar_manifest),
            ("CandidateCensus", request.candidate_census),
            ("BarSemanticsManifest", request.bar_semantics_manifest),
            *(("Instrument", value) for value in request.instrument_records),
            *(("SymbolAssignment", value) for value in request.symbol_assignments),
            *(
                ("CorporateActionRecord", version.contract)
                for version in request.known_action_versions
            ),
        ]
        if request.quarantine_evidence_ref is not None:
            evidence_id = request.quarantine_evidence_ref["target_id"]
            for name, contract in request.supporting_objects:
                if name == "EvidenceEvent" and _plain(contract).get("id") == evidence_id:
                    required.append(("EvidenceEvent", contract))
                    break
        for name, contract in required:
            self._store_contract_artifact(name, contract, artifacts)

    def _store_artifact(
        self,
        relative_path: str,
        body: bytes,
        media_type: str,
        schema_name: str,
        schema_version: str,
        artifacts: list[dict[str, Any]],
    ) -> None:
        stored = self._store.put(relative_path, body, media_type)
        self._add_artifact(stored, schema_name, schema_version, artifacts)

    @staticmethod
    def _add_artifact(
        stored: StoredArtifact,
        schema_name: str,
        schema_version: str,
        artifacts: list[dict[str, Any]],
    ) -> None:
        entry = {
            "relative_path": stored.relative_path,
            "length_bytes": stored.byte_length,
            "media_type": stored.media_type,
            "schema_name": schema_name,
            "schema_version": schema_version,
            "sha256": stored.sha256,
        }
        if any(value["relative_path"] == stored.relative_path for value in artifacts):
            return
        artifacts.append(entry)

    def _anomaly(
        self,
        reason_code: str,
        symbol: str | None,
        session_id: str | None,
        receipt_refs: list[Mapping[str, Any]],
        details: Any,
    ) -> DataAnomaly:
        details_hash = hashlib.sha256(
            canonical_json_bytes(_hash_material(details))
        ).hexdigest()
        return DataAnomaly(
            reason_code=reason_code,
            symbol=symbol,
            session_id=session_id,
            raw_receipt_refs=tuple(_unique_refs(receipt_refs)),
            details_hash=details_hash,
        )


def _reference(name: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    reference = {
        "target_schema_name": CONTRACTS[name][1],
        "target_id": contract["id"],
    }
    if name in CONTENT_ADDRESSED:
        reference["content_hash"] = contract["content_hash"]
    return reference


def _unique_refs(values: Any) -> list[Mapping[str, Any]]:
    by_identity: dict[tuple[str, str], Mapping[str, Any]] = {}
    for value in values:
        key = (value["target_schema_name"], value["target_id"])
        by_identity[key] = value
    return [by_identity[key] for key in sorted(by_identity)]


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {
            item.name: _plain(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _hash_material(value: Any) -> Any:
    """Keep provider JSON numbers distinct from strings in derived hashes."""
    if isinstance(value, Decimal):
        return {"$decimal": _format_decimal(value)}
    if isinstance(value, Mapping):
        return {str(key): _hash_material(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_hash_material(item) for item in value]
    if isinstance(value, float):
        raise MarketDataError("binary_float_forbidden")
    if isinstance(value, int) and not isinstance(value, bool):
        return {"$integer": value}
    if value is None or isinstance(value, (str, bool)):
        return value
    raise MarketDataError("provider_json_value_unsupported")


def _strict_provider_json(body: bytes) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise MarketDataError("provider_json_duplicate_key")
            result[key] = value
        return result

    def invalid_constant(_: str) -> None:
        raise MarketDataError("provider_json_non_finite_number")

    try:
        text = body.decode("utf-8", errors="strict")
        return json.loads(
            text,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=invalid_constant,
            object_pairs_hook=pairs,
        )
    except MarketDataError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidOperation, ValueError):
        raise MarketDataError("provider_json_invalid") from None


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        str(key).lower(): str(value).strip()
        for key, value in headers.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _path_family(manifest: Mapping[str, Any]) -> str:
    return "market_data"


def _required_string(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise MarketDataError(f"provider_field_{key}_invalid")
    return result


def _decimal_value(value: Any, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise MarketDataError(f"provider_field_{name}_invalid")
    try:
        result = Decimal(value) if not isinstance(value, Decimal) else value
    except (InvalidOperation, ValueError):
        raise MarketDataError(f"provider_field_{name}_invalid") from None
    if not result.is_finite():
        raise MarketDataError(f"provider_field_{name}_non_finite")
    return result


def _format_decimal(value: Decimal | None) -> str:
    if value is None or not value.is_finite():
        raise MarketDataError("decimal_value_invalid")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _format_probability(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        raise MarketDataError("coverage_denominator_invalid")
    value = (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.000000000001"), rounding=ROUND_HALF_EVEN
    )
    return format(value, ".12f")


def _parse_date(value: Any, field_name: str) -> date:
    if not isinstance(value, str):
        raise MarketDataError(f"{field_name}_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise MarketDataError(f"{field_name}_invalid") from None
    if parsed.isoformat() != value:
        raise MarketDataError(f"{field_name}_invalid")
    return parsed


def _parse_utc(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise MarketDataError(f"{field_name}_invalid") from None
    else:
        raise MarketDataError(f"{field_name}_invalid")
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise MarketDataError(f"{field_name}_must_be_explicit_utc")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    if normalized.microsecond == 0:
        return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")
    fractional = f"{normalized.microsecond:06d}".rstrip("0")
    return normalized.strftime("%Y-%m-%dT%H:%M:%S") + f".{fractional}Z"
