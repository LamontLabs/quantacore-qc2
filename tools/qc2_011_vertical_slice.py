#!/usr/bin/env python3
"""Run the bounded QC2-011 Alpaca IEX diagnostic acquisition and seal."""

from __future__ import annotations

import hashlib
import http.client
import os
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, fields, is_dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "market_data_adapter" / "src"))

from qc2_contracts.runtime import (  # noqa: E402
    canonical_content_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
    parse_json_strict,
    validate_contract,
    validate_contract_collection,
    verify_content_hash,
)
from qc2_market_data_adapter.adapter import AlpacaMarketDataAdapter  # noqa: E402
from qc2_market_data_adapter.diagnostic import (  # noqa: E402
    seal_diagnostic_snapshot,
)
from qc2_market_data_adapter.errors import MarketDataError  # noqa: E402
from qc2_market_data_adapter.models import MarketDataRequest, RetryPolicy  # noqa: E402
from qc2_market_data_adapter.replay import (  # noqa: E402
    CaptureRuntime,
    reconstruct_from_saved_receipts,
)
from qc2_market_data_adapter.storage import ContentAddressedStore  # noqa: E402
from qc2_market_data_adapter.transport import UrllibAlpacaTransport  # noqa: E402

PAPER_HOST = "paper-api.alpaca.markets"
CAPABILITY_PATH = ROOT / "docs/reference/QC2-010_CAPABILITY_MANIFESTS/market_data_iex.json"
CAPTURE_PATH = ROOT / "docs/reference/QC2-011_CAPTURE"
MAX_SUPPORTING_BODY_BYTES = 8_000_000
# One completed session keeps the provider-scoped diagnostic mapping explicitly
# bounded; it does not assert historical identity continuity or warm-up coverage.
HISTORY_SESSION_COUNT = 1
FINALIZATION_BUFFER = timedelta(minutes=60)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _credentials() -> dict[str, str]:
    key_id = os.environ.get("APCA_API_KEY_ID")
    secret_key = os.environ.get("APCA_API_SECRET_KEY")
    if not key_id or not secret_key:
        raise MarketDataError("alpaca_credentials_missing")
    return {
        "APCA-API-KEY-ID": key_id,
        "APCA-API-SECRET-KEY": secret_key,
    }


def _paper_get(
    path: str,
    params: Mapping[str, str],
    *,
    headers: Mapping[str, str],
    store: ContentAddressedStore,
    purpose: str,
) -> tuple[Any, dict[str, Any]]:
    if path not in {"/v2/calendar", "/v2/assets/SPY"}:
        raise MarketDataError("paper_read_path_not_allowed")
    query = urlencode(sorted(params.items()))
    target = f"{path}?{query}" if query else path
    started = time.monotonic()
    connection = http.client.HTTPSConnection(PAPER_HOST, timeout=20)
    try:
        connection.request(
            "GET",
            target,
            headers={**headers, "Accept": "application/json"},
        )
        response = connection.getresponse()
        status_code = response.status
        content_type = response.getheader("Content-Type", "")
        body = response.read(MAX_SUPPORTING_BODY_BYTES + 1)
        response_headers = {
            key.lower(): value
            for key, value in response.getheaders()
            if key.lower() in {"content-type", "date", "x-request-id"}
        }
    except OSError:
        raise MarketDataError("paper_read_transport_error") from None
    finally:
        connection.close()

    if status_code != 200:
        raise MarketDataError(f"paper_read_http_status_{status_code}")
    if len(body) > MAX_SUPPORTING_BODY_BYTES:
        raise MarketDataError("paper_read_body_too_large")
    if "application/json" not in content_type.casefold():
        raise MarketDataError("paper_read_content_type_invalid")
    try:
        document = parse_json_strict(body.decode("utf-8"))
    except Exception:
        raise MarketDataError("paper_read_json_invalid") from None

    received_at = _utc_text(_now_utc())
    digest = hashlib.sha256(body).hexdigest()
    artifact = store.put(
        f"provenance/{purpose}/{digest}.json",
        body,
        "application/json",
    )
    observation = {
        "purpose": purpose,
        "method": "GET",
        "path": path,
        "query": dict(sorted(params.items())),
        "status_code": status_code,
        "response_headers": response_headers,
        "received_at": received_at,
        "client_round_trip_ms": f"{(time.monotonic() - started) * 1000:.3f}",
        "sha256": digest,
        "byte_length": len(body),
        "storage_ref": artifact.storage_ref,
        "relative_path": artifact.relative_path,
    }
    return document, observation


def _reference(contract: Mapping[str, Any]) -> dict[str, str]:
    reference = {
        "target_schema_name": contract["schema_name"],
        "target_id": contract["id"],
    }
    if "content_hash" in contract:
        reference["content_hash"] = contract["content_hash"]
    return reference


def _base_contract(
    schema_name: str,
    owning_authority: str,
    *,
    identifier: str,
    created_at: str,
    source_refs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_name": schema_name,
        "schema_version": "1.0",
        "id": identifier,
        "created_at": created_at,
        "owning_authority": owning_authority,
        "evidence_class": "FORWARD_OPERATIONAL",
        "environment_namespace": "production",
        "source_refs": source_refs or [],
    }


def _parse_session_close(session_date: str, value: str) -> datetime:
    try:
        parsed_date = date.fromisoformat(session_date)
    except (TypeError, ValueError):
        raise MarketDataError("provider_calendar_date_invalid") from None
    if not isinstance(value, str):
        raise MarketDataError("provider_calendar_time_invalid")

    if "T" in value or " " in value:
        try:
            parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise MarketDataError("provider_calendar_time_invalid") from None
        if parsed_datetime.date() != parsed_date:
            raise MarketDataError("provider_calendar_date_time_mismatch")
        if parsed_datetime.tzinfo is None:
            parsed_datetime = parsed_datetime.replace(
                tzinfo=ZoneInfo("America/New_York")
            )
        return parsed_datetime.astimezone(timezone.utc)

    try:
        parsed_time = dt_time.fromisoformat(value)
    except ValueError:
        raise MarketDataError("provider_calendar_time_invalid") from None
    parsed_datetime = datetime.combine(parsed_date, parsed_time)
    if parsed_datetime.tzinfo is None:
        parsed_datetime = parsed_datetime.replace(
            tzinfo=ZoneInfo("America/New_York")
        )
    return parsed_datetime.astimezone(timezone.utc)


def _build_request(
    capability: Mapping[str, Any],
    calendar_document: Any,
    calendar_observation: Mapping[str, Any],
    asset_document: Any,
    asset_observation: Mapping[str, Any],
    *,
    cutoff: datetime,
) -> tuple[MarketDataRequest, dict[str, Any]]:
    if not isinstance(calendar_document, list) or not isinstance(asset_document, dict):
        raise MarketDataError("provider_supporting_response_shape_invalid")
    asset = asset_document
    if (
        asset.get("symbol") != "SPY"
        or asset.get("class") != "us_equity"
        or asset.get("status") != "active"
        or not isinstance(asset.get("id"), str)
        or not isinstance(asset.get("exchange"), str)
        or not asset["exchange"]
    ):
        raise MarketDataError("provider_asset_identity_unverified")

    rows_by_date: dict[str, Mapping[str, Any]] = {}
    for row in calendar_document:
        if not isinstance(row, dict):
            raise MarketDataError("provider_calendar_row_invalid")
        date = row.get("date")
        if not isinstance(date, str) or not isinstance(row.get("close"), str):
            raise MarketDataError("provider_calendar_row_invalid")
        if date in rows_by_date:
            raise MarketDataError("provider_calendar_duplicate_session")
        rows_by_date[date] = row

    cutoff_text = _utc_text(cutoff)
    earliest_tested_session = capability.get("earliest_tested_session")
    completed_rows: list[Mapping[str, Any]] = []
    for date, row in sorted(rows_by_date.items()):
        if earliest_tested_session and date < earliest_tested_session:
            continue
        close_at = _parse_session_close(date, row["close"])
        if close_at + FINALIZATION_BUFFER <= cutoff:
            completed_rows.append(row)
    selected_rows = completed_rows[-HISTORY_SESSION_COUNT:]
    if not selected_rows:
        raise MarketDataError("no_completed_capability_session_available")
    sessions = [row["date"] for row in selected_rows]
    asof = sessions[-1]
    start = sessions[0]
    asset_received_at = str(asset_observation["received_at"])

    run_id = new_uuidv7()
    asset_identity_evidence = {
        "provider": "alpaca",
        "asset_id": asset["id"],
        "symbol": asset["symbol"],
        "asset_class": asset["class"],
        "asset_status": asset["status"],
        "exchange": asset["exchange"],
        "asset_response_sha256": asset_observation["sha256"],
        "calendar_response_sha256": calendar_observation["sha256"],
        "diagnostic_sessions": sessions,
    }
    event = _base_contract(
        "qc2.integrity_build.EvidenceEvent.v1",
        "evidence",
        identifier=new_uuidv7(),
        created_at=asset_received_at,
    )
    event.update(
        content_hash="0" * 64,
        installation_id="qc2-011-capture",
        stream_id=f"qc2-011-{run_id}",
        sequence=1,
        event_type="diagnostic_asset_observation",
        actor_identity="qc2-011-runner",
        authorized_command_ref=None,
        correlation_id=f"qc2-011-{run_id}",
        payload_hash=domain_separated_sha256(
            "qc2.evidence-payload.v1",
            canonical_json_bytes(asset_identity_evidence),
        ),
        dependency_refs=[],
        previous_event_hash=None,
        event_hash="0" * 64,
        wall_clock_at=asset_received_at,
        monotonic_generation=0,
    )
    event_hash_basis = {
        key: value
        for key, value in event.items()
        if key not in {"content_hash", "event_hash"}
    }
    event["event_hash"] = domain_separated_sha256(
        "qc2.evidence-event.v1",
        canonical_json_bytes(event_hash_basis),
    )
    event["content_hash"] = canonical_content_hash("EvidenceEvent", event)
    validate_contract("EvidenceEvent", event)
    verify_content_hash("EvidenceEvent", event)
    event_ref = _reference(event)

    calendar = _base_contract(
        "qc2.time_operation.CalendarManifest.v1",
        "calendar",
        identifier=new_uuidv7(),
        created_at=asset_received_at,
        source_refs=[event_ref],
    )
    calendar.update(
        content_hash="0" * 64,
        calendar_version=1,
        timezone="America/New_York",
        valid_from=start,
        valid_through=asof,
        sessions=sessions,
    )
    calendar["content_hash"] = canonical_content_hash("CalendarManifest", calendar)
    validate_contract("CalendarManifest", calendar)
    verify_content_hash("CalendarManifest", calendar)

    instrument = _base_contract(
        "qc2.identity_market.Instrument.v1",
        "instrument_universe",
        identifier=new_uuidv7(),
        created_at=asset_received_at,
        source_refs=[event_ref],
    )
    instrument.update(
        stable_instrument_key=f"alpaca_asset_{asset['id'].lower().replace('-', '_')}",
        first_known_at=asset_received_at,
        identity_status="UNRESOLVED",
    )
    validate_contract("Instrument", instrument)

    census_instrument_ref = {
        "target_schema_name": instrument["schema_name"],
        "target_id": instrument["id"],
    }
    census = _base_contract(
        "qc2.identity_market.CandidateCensus.v1",
        "instrument_universe",
        identifier=new_uuidv7(),
        created_at=asset_received_at,
        source_refs=[event_ref],
    )
    census.update(
        session_id=asof,
        instrument_refs=[census_instrument_ref],
        cutoff=cutoff_text,
        source_manifest_refs=[],
        membership_hash=hashlib.sha256(
            canonical_json_bytes([census_instrument_ref])
        ).hexdigest(),
    )
    validate_contract("CandidateCensus", census)

    assignment = _base_contract(
        "qc2.identity_market.SymbolAssignment.v1",
        "instrument_universe",
        identifier=new_uuidv7(),
        created_at=asset_received_at,
        source_refs=[event_ref],
    )
    assignment.update(
        instrument_ref=census_instrument_ref,
        symbol="SPY",
        exchange=asset["exchange"],
        currency="USD",
        effective_from=start,
        effective_to=None,
        known_from=asset_received_at,
        known_to=None,
        source_evidence_ref=event_ref,
        mapping_confidence="1.000000000000",
    )
    validate_contract("SymbolAssignment", assignment)

    semantics = _base_contract(
        "qc2.identity_market.BarSemanticsManifest.v1",
        "market_data",
        identifier=new_uuidv7(),
        created_at=asset_received_at,
    )
    semantics.update(
        provider="alpaca",
        feed="IEX",
        timeframe="1DAY",
        interval_timezone="America/New_York",
        field_meanings=[
            "Daily OHLC is an interval aggregate, not an official auction execution or guarantee of an executable price.",
            "IEX volume represents a single venue and is not consolidated market volume.",
            "IEX fields can include extended-hours trade conditions as defined by the provider.",
        ],
        revision_policy=(
            "Preserve each raw response; later provider revisions remain separately observable."
        ),
        finalization_rule=(
            "Finalize only after the last interval affecting every included field has ended "
            "and the supplied session deadline has passed."
        ),
        tested_at=asset_received_at,
    )
    validate_contract("BarSemanticsManifest", semantics)

    finalization_deadlines = {
        row["date"]: _utc_text(
            _parse_session_close(row["date"], row["close"])
            + FINALIZATION_BUFFER
        )
        for row in selected_rows
    }
    session_deadline = max(
        cutoff + timedelta(hours=1),
        max(
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            for value in finalization_deadlines.values()
        )
        + timedelta(hours=1),
    )
    request = MarketDataRequest(
        provider="alpaca",
        feed="IEX",
        adjustment="RAW",
        timeframe="1DAY",
        currency="USD",
        asof=asof,
        start=start,
        end=asof,
        action_process_start=start,
        action_process_end=asof,
        cutoff=cutoff_text,
        session_deadline_at=_utc_text(session_deadline),
        page_limit=100,
        calendar_manifest=calendar,
        candidate_census=census,
        bar_semantics_manifest=semantics,
        instrument_records=(instrument,),
        symbol_assignments=(assignment,),
        expected_sessions_by_symbol={"SPY": tuple(sessions)},
        finalization_deadlines=finalization_deadlines,
        retry_policy=RetryPolicy(
            maximum_attempts=1,
            maximum_total_wait_seconds=Decimal("0"),
            fallback_initial_delay_seconds=Decimal("0"),
            fallback_maximum_delay_seconds=Decimal("0"),
            maximum_pages=10,
        ),
        mapping_policy="ALPACA_ASOF",
        evidence_class="FORWARD_OPERATIONAL",
        environment_namespace="production",
        quarantine_evidence_ref=event_ref,
        known_action_versions=(),
        supporting_objects=(
            ("EvidenceEvent", event),
            ("CalendarManifest", calendar),
            ("CandidateCensus", census),
            ("BarSemanticsManifest", semantics),
            ("Instrument", instrument),
            ("SymbolAssignment", assignment),
        ),
    )
    context = _request_context(request)
    return request, {
        "run_id": run_id,
        "selected_sessions": sessions,
        "asset_identity_evidence": asset_identity_evidence,
        "calendar_manifest": calendar,
        "candidate_census": census,
        "bar_semantics_manifest": semantics,
        "instrument": instrument,
        "symbol_assignment": assignment,
        "evidence_event": event,
        "request_context": context,
    }


def _request_context(request: MarketDataRequest) -> dict[str, Any]:
    return {
        "provider": request.provider,
        "feed": request.feed,
        "adjustment": request.adjustment,
        "timeframe": request.timeframe,
        "currency": request.currency,
        "asof": request.asof,
        "start": request.start,
        "end": request.end,
        "action_process_start": request.action_process_start,
        "action_process_end": request.action_process_end,
        "cutoff": request.cutoff,
        "session_deadline_at": request.session_deadline_at,
        "page_limit": request.page_limit,
        "calendar_manifest": request.calendar_manifest,
        "candidate_census": request.candidate_census,
        "bar_semantics_manifest": request.bar_semantics_manifest,
        "instrument_records": list(request.instrument_records),
        "symbol_assignments": list(request.symbol_assignments),
        "expected_sessions_by_symbol": {
            symbol: list(sessions)
            for symbol, sessions in request.expected_sessions_by_symbol.items()
        },
        "finalization_deadlines": dict(request.finalization_deadlines),
        "retry_policy": {
            "maximum_attempts": request.retry_policy.maximum_attempts,
            "maximum_total_wait_seconds": str(
                request.retry_policy.maximum_total_wait_seconds
            ),
            "fallback_initial_delay_seconds": str(
                request.retry_policy.fallback_initial_delay_seconds
            ),
            "fallback_maximum_delay_seconds": str(
                request.retry_policy.fallback_maximum_delay_seconds
            ),
            "maximum_pages": request.retry_policy.maximum_pages,
        },
        "mapping_policy": request.mapping_policy,
        "evidence_class": request.evidence_class,
        "environment_namespace": request.environment_namespace,
        "quarantine_evidence_ref": request.quarantine_evidence_ref,
        "known_action_versions": [],
        "supporting_objects": [
            {"contract_name": name, "contract": contract}
            for name, contract in request.supporting_objects
        ],
    }


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    return value


def _write_json(path: Path, value: Any) -> None:
    body = canonical_json_bytes(_plain(value))
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_contract(
    capture_root: Path,
    contract_name: str,
    identifier: str,
) -> tuple[dict[str, Any], bytes, str]:
    path = (
        capture_root
        / "objects"
        / "contracts"
        / contract_name
        / f"{identifier}.json"
    )
    try:
        body = path.read_bytes()
        contract = parse_json_strict(body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise MarketDataError("saved_contract_missing_or_invalid") from None
    if not isinstance(contract, dict) or contract.get("id") != identifier:
        raise MarketDataError("saved_contract_identity_mismatch")
    return contract, body, path.relative_to(capture_root).as_posix()


def _parse_utc_text(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise MarketDataError("saved_evidence_timestamp_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketDataError("saved_evidence_timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def write_saved_evidence_reports(capture_root: Path = CAPTURE_PATH) -> None:
    """Expose and independently validate the already sealed, offline evidence."""
    try:
        report = parse_json_strict(
            (capture_root / "capture_report.json").read_text(encoding="utf-8")
        )
        provenance = parse_json_strict(
            (capture_root / "supporting_provenance.json").read_text(
                encoding="utf-8"
            )
        )
        replay_report = parse_json_strict(
            (capture_root / "offline_replay_report.json").read_text(
                encoding="utf-8"
            )
        )
        snapshot = parse_json_strict(
            (capture_root / "diagnostic_snapshot.json").read_text(
                encoding="utf-8"
            )
        )
        universe = parse_json_strict(
            (capture_root / "diagnostic_universe_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        event_payload = parse_json_strict(
            (capture_root / "evidence_event_payload.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeDecodeError, ValueError):
        raise MarketDataError("saved_evidence_sidecar_invalid") from None
    if not all(
        isinstance(item, dict)
        for item in (report, provenance, replay_report, snapshot, universe, event_payload)
    ):
        raise MarketDataError("saved_evidence_sidecar_invalid")

    capability_path = ROOT / provenance["capability_manifest_path"]
    try:
        capability_body = capability_path.read_bytes()
        capability = parse_json_strict(capability_body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise MarketDataError("saved_capability_manifest_invalid") from None
    capability_hash = hashlib.sha256(capability_body).hexdigest()
    if capability_hash != report["capability_manifest_file_sha256"]:
        raise MarketDataError("saved_capability_manifest_hash_mismatch")
    validate_contract("DataCapabilityManifest", capability)
    if (
        capability["feed"] != report["feed"]
        or capability["effective_delay_ms"] is not None
        or capability["tested_at"] != report["capability_manifest_tested_at"]
        or capability["expires_at"] != report["capability_manifest_expires_at"]
    ):
        raise MarketDataError("saved_capability_manifest_mismatch")

    bundle_id = snapshot["data_bundle_ref"]["target_id"]
    data_bundle, bundle_body, bundle_path = _read_contract(
        capture_root, "DataBundle", bundle_id
    )
    census_id = universe["census_ref"]["target_id"]
    census, _, census_path = _read_contract(
        capture_root, "CandidateCensus", census_id
    )
    event_id = report["evidence_event_id"]
    event, _, event_path = _read_contract(
        capture_root, "EvidenceEvent", event_id
    )
    validate_contract("DataBundle", data_bundle)
    verify_content_hash("EvidenceEvent", event)
    validate_contract("CandidateCensus", census)
    validate_contract("UniverseManifest", universe)
    validate_contract("MarketSnapshot", snapshot)

    payload_hash = domain_separated_sha256(
        "qc2.evidence-payload.v1",
        canonical_json_bytes(event_payload),
    )
    event_hash_basis = {
        key: value
        for key, value in event.items()
        if key not in {"content_hash", "event_hash"}
    }
    event_hash = domain_separated_sha256(
        "qc2.evidence-event.v1",
        canonical_json_bytes(event_hash_basis),
    )
    if (
        payload_hash != event["payload_hash"]
        or event["payload_hash"] != report["evidence_event_payload_hash"]
        or event_hash != event["event_hash"]
        or event["content_hash"] != report["evidence_event_content_hash"]
        or event["event_hash"] != report["evidence_event_hash"]
    ):
        raise MarketDataError("saved_evidence_event_hash_mismatch")

    contract_collection: list[tuple[str, Mapping[str, Any]]] = []
    contract_root = capture_root / "objects" / "contracts"
    for path in sorted(contract_root.rglob("*.json")):
        contract = parse_json_strict(path.read_text(encoding="utf-8"))
        name = contract["schema_name"].split(".")[-2]
        validate_contract(name, contract)
        if "content_hash" in contract:
            verify_content_hash(name, contract)
        contract_collection.append((name, contract))
    contract_collection.extend(
        [("UniverseManifest", universe), ("MarketSnapshot", snapshot)]
    )
    try:
        validate_contract_collection(contract_collection)
    except Exception:
        raise MarketDataError("saved_evidence_chain_contract_closure_failed") from None

    content_store = ContentAddressedStore(capture_root / "objects")
    receipt_evidence = []
    request_evidence = []
    requests_by_id: dict[str, Mapping[str, Any]] = {}
    for reference in data_bundle["request_refs"]:
        request, _, path = _read_contract(
            capture_root, "RequestManifest", reference["target_id"]
        )
        if request["feed"] != capability["feed"]:
            raise MarketDataError("saved_request_feed_mismatch")
        descriptor_path = (
            capture_root
            / "objects"
            / "requests"
            / f"{request['sanitized_request_hash']}.json"
        )
        try:
            descriptor = parse_json_strict(
                descriptor_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, ValueError):
            raise MarketDataError("saved_request_descriptor_invalid") from None
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("feed") != capability["feed"]
        ):
            raise MarketDataError("saved_request_descriptor_mismatch")
        requests_by_id[request["id"]] = request
        request_evidence.append(
            {
                "id": request["id"],
                "feed": request["feed"],
                "path": descriptor.get("path"),
                "query": descriptor.get("query"),
                "contract_path": path,
            }
        )
    tested_at = _parse_utc_text(capability["tested_at"])
    expires_at = _parse_utc_text(capability["expires_at"])
    for reference in data_bundle["raw_receipt_refs"]:
        receipt, _, path = _read_contract(
            capture_root, "RawReceipt", reference["target_id"]
        )
        digest = receipt["raw_sha256"]
        raw_path = f"raw/{digest}.bin"
        raw_body = content_store.read(raw_path, digest)
        received_at = _parse_utc_text(receipt["received_at"])
        request = requests_by_id.get(receipt["request_ref"]["target_id"])
        if (
            hashlib.sha256(raw_body).hexdigest() != digest
            or len(raw_body) != receipt["byte_length"]
            or not tested_at <= received_at <= expires_at
            or request is None
            or received_at > _parse_utc_text(request["cutoff"])
            or receipt["storage_ref"] != f"qc2blob:sha256:{digest}"
        ):
            raise MarketDataError("saved_raw_receipt_verification_failed")
        receipt_evidence.append(
            {
                "id": receipt["id"],
                "request_id": receipt["request_ref"]["target_id"],
                "sha256": digest,
                "received_at": receipt["received_at"],
                "byte_length": receipt["byte_length"],
                "contract_path": path,
                "raw_path": f"objects/{raw_path}",
            }
        )

    bundle_sha256 = hashlib.sha256(bundle_body).hexdigest()
    if (
        data_bundle["id"] != snapshot["data_bundle_ref"]["target_id"]
        or data_bundle["content_inventory_hash"]
        != report["content_inventory_sha256"]
        or data_bundle["coverage"] != report["coverage"]
        or snapshot["feed"] != capability["feed"]
        or snapshot["coverage"] != report["coverage"]
        or len(data_bundle["bar_refs"]) != report["verified_bar_count"]
        or len(receipt_evidence) != report["raw_receipt_count"]
        or event_payload.get("asset_response_sha256")
        != next(
            item["sha256"]
            for item in provenance["observations"]
            if item["purpose"] == "asset"
        )
        or event_payload.get("calendar_response_sha256")
        != next(
            item["sha256"]
            for item in provenance["observations"]
            if item["purpose"] == "calendar"
        )
    ):
        raise MarketDataError("saved_evidence_lineage_mismatch")
    stored_universe = content_store.read(
        f"universe/{report['universe_manifest_sha256']}.json",
        report["universe_manifest_sha256"],
    )
    stored_snapshot = content_store.read(
        f"snapshots/{report['snapshot_sha256']}.json",
        report["snapshot_sha256"],
    )
    if (
        stored_universe != canonical_json_bytes(universe)
        or stored_snapshot != canonical_json_bytes(snapshot)
        or not _parse_utc_text(report["capture_sealed_at"])
        >= max(_parse_utc_text(item["received_at"]) for item in receipt_evidence)
    ):
        raise MarketDataError("saved_diagnostic_snapshot_hash_mismatch")

    normalized_path = capture_root / "normalized_data_bundle.json"
    _write_json(normalized_path, data_bundle)
    if normalized_path.read_bytes() != bundle_body:
        raise MarketDataError("normalized_bundle_copy_mismatch")
    census_copy_path = capture_root / "diagnostic_census.json"
    _write_json(census_copy_path, census)

    elapsed_seconds = (
        _parse_utc_text(report["capture_sealed_at"])
        - _parse_utc_text(report["capture_started_at"])
    ).total_seconds()
    timing_report = {
        "status": "VERIFIED",
        "capture_started_at": report["capture_started_at"],
        "capture_sealed_at": report["capture_sealed_at"],
        "capture_elapsed_seconds": f"{elapsed_seconds:.3f}",
        "supporting_provider_observations": [
            {
                key: observation[key]
                for key in (
                    "purpose",
                    "method",
                    "path",
                    "status_code",
                    "received_at",
                    "client_round_trip_ms",
                    "sha256",
                    "byte_length",
                )
            }
            for observation in provenance["observations"]
        ],
        "market_data_receipts": [
            {
                "sha256": receipt["sha256"],
                "received_at": receipt["received_at"],
                "byte_length": receipt["byte_length"],
            }
            for receipt in receipt_evidence
        ],
        "capability_window": {
            "tested_at": capability["tested_at"],
            "expires_at": capability["expires_at"],
            "effective_delay_ms": capability["effective_delay_ms"],
        },
        "expected_bar_count": report["expected_bar_count"],
        "verified_bar_count": report["verified_bar_count"],
        "coverage": report["coverage"],
        "provider_side_effective_delay": "UNRESOLVED",
        "receipt_timestamps": "client-side UTC response receipt times",
    }
    evidence_chain = {
        "status": report["verification"]["status"],
        "verification_level": report["verification"]["verification_level"],
        "external_anchor": report["verification"]["external_anchor"],
        "capability_manifest": {
            "path": provenance["capability_manifest_path"],
            "file_sha256": capability_hash,
            "feed": capability["feed"],
            "tested_at": capability["tested_at"],
            "expires_at": capability["expires_at"],
            "effective_delay_ms": capability["effective_delay_ms"],
        },
        "evidence_event": {
            "id": event["id"],
            "event_hash": event["event_hash"],
            "content_hash": event["content_hash"],
            "payload_hash": event["payload_hash"],
            "contract_path": event_path,
            "payload_path": "evidence_event_payload.json",
        },
        "candidate_census": {
            "id": census["id"],
            "contract_path": census_path,
            "instrument_count": len(census["instrument_refs"]),
            "universe_manifest_id": universe["id"],
            "eligible_instrument_count": len(
                universe["eligible_instrument_refs"]
            ),
            "unscorable_instrument_count": len(
                universe["unscorable_instrument_refs"]
            ),
        },
        "data_bundle": {
            "id": data_bundle["id"],
            "contract_path": bundle_path,
            "normalized_copy_path": "normalized_data_bundle.json",
            "contract_sha256": bundle_sha256,
            "content_inventory_sha256": data_bundle["content_inventory_hash"],
            "completeness": data_bundle["completeness"],
            "coverage": data_bundle["coverage"],
            "request_refs": request_evidence,
            "raw_receipts": receipt_evidence,
        },
        "universe_manifest": {
            "id": universe["id"],
            "sha256": report["universe_manifest_sha256"],
            "eligible_instrument_count": len(
                universe["eligible_instrument_refs"]
            ),
            "unscorable_instrument_count": len(
                universe["unscorable_instrument_refs"]
            ),
        },
        "snapshot": {
            "id": snapshot["id"],
            "sha256": report["snapshot_sha256"],
            "row_count": snapshot["row_count"],
            "coverage": snapshot["coverage"],
            "sealed_at": snapshot["sealed_at"],
        },
        "offline_reconstruction": replay_report,
        "official_prediction": "NOT_PERFORMED",
        "official_universe_qualification": "NOT_PERFORMED",
        "future_outcomes": "NOT_INCLUDED",
        "f0_activation": "NOT_AUTHORIZED",
        "trading_or_order_submission": "NONE",
    }
    _write_json(capture_root / "acquisition_timing_report.json", timing_report)
    _write_json(capture_root / "evidence_chain.json", evidence_chain)
    report.update(
        {
            "candidate_census_id": census["id"],
            "candidate_census_path": "diagnostic_census.json",
            "data_bundle_id": data_bundle["id"],
            "data_bundle_contract_path": bundle_path,
            "normalized_data_bundle_path": "normalized_data_bundle.json",
            "data_bundle_contract_sha256": bundle_sha256,
            "universe_manifest_id": universe["id"],
            "snapshot_id": snapshot["id"],
            "timing_report_path": "acquisition_timing_report.json",
            "evidence_chain_path": "evidence_chain.json",
        }
    )
    _write_json(capture_root / "capture_report.json", report)


def _wait_until(instant: datetime) -> None:
    while True:
        remaining = (instant - _now_utc()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 1.0))


def run_capture() -> dict[str, Any]:
    if CAPTURE_PATH.exists():
        raise MarketDataError("capture_output_already_exists")
    if not CAPABILITY_PATH.is_file():
        raise MarketDataError("accepted_iex_capability_manifest_missing")
    capability_bytes = CAPABILITY_PATH.read_bytes()
    capability_hash = hashlib.sha256(capability_bytes).hexdigest()
    try:
        capability = parse_json_strict(capability_bytes.decode("utf-8"))
        validate_contract("DataCapabilityManifest", capability)
    except Exception:
        raise MarketDataError("accepted_iex_capability_manifest_invalid") from None
    if (
        capability.get("capability") != "MARKET_DATA"
        or capability.get("feed") != "IEX"
        or capability.get("evidence_class") != "FORWARD_OPERATIONAL"
        or capability.get("environment_namespace") != "production"
        or capability.get("effective_delay_ms") is not None
    ):
        raise MarketDataError("accepted_iex_capability_manifest_mismatch")
    now = _now_utc()
    try:
        expires_at = datetime.fromisoformat(
            capability["expires_at"].replace("Z", "+00:00")
        )
    except (AttributeError, TypeError, ValueError):
        raise MarketDataError("accepted_iex_capability_expiry_invalid") from None
    if expires_at.tzinfo is None or expires_at <= now:
        raise MarketDataError("accepted_iex_capability_manifest_expired")

    headers = _credentials()
    reference_root = CAPTURE_PATH.parent
    stage_context = tempfile.TemporaryDirectory(
        prefix=".qc2-011-stage-",
        dir=reference_root,
    )
    stage = Path(stage_context.name)
    final_created = False
    try:
        store = ContentAddressedStore(stage / "objects")
        run_started_at = _utc_text(_now_utc())
        local_now = _now_utc()
        calendar_start = (
            local_now.astimezone(ZoneInfo("America/New_York")).date()
            - timedelta(days=21)
        ).isoformat()
        calendar_end = local_now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        calendar_document, calendar_observation = _paper_get(
            "/v2/calendar",
            {"start": calendar_start, "end": calendar_end},
            headers=headers,
            store=store,
            purpose="calendar",
        )
        asset_document, asset_observation = _paper_get(
            "/v2/assets/SPY",
            {},
            headers=headers,
            store=store,
            purpose="asset",
        )

        cutoff = _now_utc() + timedelta(seconds=45)
        request, diagnostics = _build_request(
            capability,
            calendar_document,
            calendar_observation,
            asset_document,
            asset_observation,
            cutoff=cutoff,
        )
        runtime = CaptureRuntime()
        adapter = AlpacaMarketDataAdapter(
            transport=UrllibAlpacaTransport(
                credential_headers=_credentials,
                timeout_seconds=20,
            ),
            store=store,
            clock=runtime.clock,
            sleeper=time.sleep,
            id_factory=runtime.new_id,
        )
        result = adapter.acquire(request)
        if (
            result.data_bundle.get("completeness") != "COMPLETE"
            or result.failure_codes
            or result.missing_symbols
        ):
            raise MarketDataError("real_iex_acquisition_incomplete")

        with tempfile.TemporaryDirectory(prefix="qc2-011-replay-") as replay_dir:
            reconstruct_from_saved_receipts(
                request,
                result,
                store,
                clock_trace=runtime.clock_trace,
                id_trace=runtime.id_trace,
                replay_root=Path(replay_dir),
            )
        _wait_until(cutoff)
        sealed_at = _utc_text(_now_utc())
        seal = seal_diagnostic_snapshot(
            request,
            result,
            store,
            capability,
            sealed_at=sealed_at,
            id_factory=new_uuidv7,
        )

        _write_json(stage / "request_context.json", diagnostics["request_context"])
        _write_json(stage / "runtime_trace.json", runtime.record())
        _write_json(
            stage / "supporting_provenance.json",
            {
                "paper_host": PAPER_HOST,
                "observations": [calendar_observation, asset_observation],
                "capability_manifest_path": str(
                    CAPABILITY_PATH.relative_to(ROOT)
                ),
                "capability_manifest_file_sha256": capability_hash,
                "capability_manifest_summary": {
                    key: capability.get(key)
                    for key in (
                        "feed",
                        "observed_result",
                        "earliest_tested_session",
                        "tested_at",
                        "expires_at",
                        "effective_delay_ms",
                    )
                },
            },
        )

        if CAPTURE_PATH.exists():
            raise MarketDataError("capture_output_already_exists")
        shutil.copytree(stage, CAPTURE_PATH)
        final_created = True

        final_store = ContentAddressedStore(CAPTURE_PATH / "objects")
        for artifact in result.artifact_inventory:
            final_store.read(artifact["relative_path"], artifact["sha256"])
        final_store.read(
            seal.universe_artifact.relative_path,
            seal.universe_artifact.sha256,
        )
        final_store.read(
            seal.snapshot_artifact.relative_path,
            seal.snapshot_artifact.sha256,
        )
        with tempfile.TemporaryDirectory(prefix="qc2-011-final-replay-") as replay_dir:
            replayed = reconstruct_from_saved_receipts(
                request,
                result,
                final_store,
                clock_trace=runtime.clock_trace,
                id_trace=runtime.id_trace,
                replay_root=Path(replay_dir),
            )
        if replayed.data_bundle != result.data_bundle:
            raise MarketDataError("final_offline_reconstruction_mismatch")

        verification = asdict(seal.verification)
        report = {
            "task_id": "QC2-011",
            "status": "CAPTURED_AND_LOCALLY_VERIFIED",
            "capture_started_at": run_started_at,
            "capture_sealed_at": sealed_at,
            "provider": request.provider,
            "feed": request.feed,
            "adjustment": request.adjustment,
            "timeframe": request.timeframe,
            "symbol": "SPY",
            "asof": request.asof,
            "history_start": request.start,
            "history_end": request.end,
            "selected_completed_sessions": diagnostics["selected_sessions"],
            "expected_bar_count": seal.verification.expected_bar_count,
            "verified_bar_count": seal.verification.verified_bar_count,
            "coverage": seal.verification.coverage,
            "raw_receipt_count": seal.verification.verified_receipt_count,
            "raw_receipt_sha256": list(seal.verification.receipt_hashes),
            "raw_receipt_received_at": list(
                seal.verification.receipt_received_at
            ),
            "capability_manifest_file_sha256": capability_hash,
            "capability_manifest_tested_at": capability["tested_at"],
            "capability_manifest_expires_at": capability["expires_at"],
            "effective_delay_ms": None,
            "content_inventory_sha256": seal.verification.inventory_hash,
            "universe_manifest_sha256": seal.universe_artifact.sha256,
            "snapshot_sha256": seal.snapshot_artifact.sha256,
            "evidence_event_id": diagnostics["evidence_event"]["id"],
            "evidence_event_hash": diagnostics["evidence_event"]["event_hash"],
            "evidence_event_content_hash": diagnostics["evidence_event"][
                "content_hash"
            ],
            "evidence_event_payload_hash": diagnostics["evidence_event"][
                "payload_hash"
            ],
            "offline_reconstruction": "PASS_FROM_FINAL_SAVED_RECEIPTS",
            "verification": verification,
            "diagnostic_boundary": {
                "eligible_instrument_count": 0,
                "unscorable_instrument_count": len(
                    seal.universe_manifest["unscorable_instrument_refs"]
                ),
                "universe_qualification": "NOT_PERFORMED",
                "prediction": "NOT_PERFORMED",
                "future_outcomes": "NOT_INCLUDED",
                "f0_activation": "NOT_AUTHORIZED",
                "trading_or_order_submission": "NONE",
                "external_anchor": False,
                "provider_side_effective_delay": "UNRESOLVED",
                "receipt_timestamps": "client-side UTC response receipt times",
            },
        }
        _write_json(
            CAPTURE_PATH / "evidence_event_payload.json",
            diagnostics["asset_identity_evidence"],
        )
        _write_json(CAPTURE_PATH / "diagnostic_universe_manifest.json", seal.universe_manifest)
        _write_json(CAPTURE_PATH / "diagnostic_snapshot.json", seal.snapshot)
        _write_json(CAPTURE_PATH / "diagnostic_verification.json", verification)
        _write_json(
            CAPTURE_PATH / "offline_replay_report.json",
            {
                "status": "PASS",
                "source": "final content-addressed capture store",
                "normalized_bundle_sha256": seal.verification.inventory_hash,
                "daily_bar_count": len(replayed.daily_bars),
                "request_trace_count": len(runtime.clock_trace),
                "generated_id_count": len(runtime.id_trace),
                "network_access_during_reconstruction": False,
            },
        )
        _write_json(CAPTURE_PATH / "capture_report.json", report)
        write_saved_evidence_reports(CAPTURE_PATH)
        return report
    except Exception:
        if final_created:
            shutil.rmtree(CAPTURE_PATH)
        raise
    finally:
        stage_context.cleanup()


def main() -> int:
    try:
        report = run_capture()
    except MarketDataError as error:
        print(f"QC2-011 capture blocked: {error.code}")
        return 2
    print(
        "QC2-011 capture complete: "
        f"{report['feed']} {report['symbol']} {report['history_start']}..{report['history_end']}; "
        f"{report['verified_bar_count']}/{report['expected_bar_count']} bars; "
        f"offline replay {report['offline_reconstruction']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
