"""Fail-closed diagnostic sealing for a captured market-data bundle."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from qc2_contracts.runtime import (
    artifact_inventory_hash,
    canonical_json_bytes,
    validate_contract,
    validate_contract_collection,
    verify_content_hash,
)

from .errors import MarketDataError
from .models import MarketDataRequest, MarketDataResult
from .storage import ContentAddressedStore, StoredArtifact

_DIAGNOSTIC_ONLY_RULE = (
    "QC2-011: explicitly supplied diagnostic census only; no member is eligible "
    "for official universe qualification, prediction, F0, or trading."
)


@dataclass(frozen=True)
class DiagnosticEvidenceVerification:
    status: str
    verification_level: str
    external_anchor: bool
    feed: str
    coverage: str
    expected_bar_count: int
    verified_bar_count: int
    verified_receipt_count: int
    receipt_hashes: tuple[str, ...]
    receipt_received_at: tuple[str, ...]
    inventory_hash: str
    capability_tested_at: str
    capability_expires_at: str
    effective_delay_ms: None
    contract_count: int


@dataclass(frozen=True)
class DiagnosticSeal:
    universe_manifest: Mapping[str, Any]
    snapshot: Mapping[str, Any]
    universe_artifact: StoredArtifact
    snapshot_artifact: StoredArtifact
    verification: DiagnosticEvidenceVerification


def seal_diagnostic_snapshot(
    request: MarketDataRequest,
    result: MarketDataResult,
    store: ContentAddressedStore,
    capability_manifest: Mapping[str, Any],
    *,
    sealed_at: str,
    id_factory: Callable[[], str],
) -> DiagnosticSeal:
    """Verify a complete diagnostic capture, then store immutable snapshot bytes.

    The required UniverseManifest is deliberately non-qualifying: every member
    of the supplied census is recorded as unscorable for official use.
    """
    verification, contract_collection = _verify_capture(
        request,
        result,
        store,
        capability_manifest,
        sealed_at=sealed_at,
    )

    census = dict(request.candidate_census)
    data_bundle = dict(result.data_bundle)
    universe_manifest = {
        "schema_name": "qc2.identity_market.UniverseManifest.v1",
        "schema_version": "1.0",
        "id": id_factory(),
        "created_at": sealed_at,
        "owning_authority": "instrument_universe",
        "evidence_class": request.evidence_class,
        "environment_namespace": request.environment_namespace,
        "source_refs": [],
        "session_id": request.asof,
        "census_ref": _reference(census),
        "data_bundle_ref": _reference(data_bundle),
        "eligibility_rule_hash": hashlib.sha256(
            _DIAGNOSTIC_ONLY_RULE.encode("utf-8")
        ).hexdigest(),
        "eligible_instrument_refs": [],
        "unscorable_instrument_refs": list(census["instrument_refs"]),
        "reason_counts": ["QC2_011_DIAGNOSTIC_ONLY"],
        "cutoff": request.cutoff,
    }
    snapshot = {
        "schema_name": "qc2.identity_market.MarketSnapshot.v1",
        "schema_version": "1.0",
        "id": id_factory(),
        "created_at": sealed_at,
        "owning_authority": "market_data",
        "evidence_class": request.evidence_class,
        "environment_namespace": request.environment_namespace,
        "source_refs": [],
        "session_id": request.asof,
        "calendar_ref": _reference(dict(request.calendar_manifest)),
        "census_ref": _reference(census),
        "data_bundle_ref": _reference(data_bundle),
        "universe_ref": _reference(universe_manifest),
        "provider": request.provider,
        "feed": request.feed,
        "decision_cutoff": request.cutoff,
        "sealed_at": sealed_at,
        "row_count": len(result.daily_bars),
        "coverage": data_bundle["coverage"],
        "dependency_refs": [
            _reference(dict(request.calendar_manifest)),
            _reference(census),
            _reference(data_bundle),
            _reference(universe_manifest),
        ],
    }

    try:
        validate_contract("UniverseManifest", universe_manifest)
        validate_contract("MarketSnapshot", snapshot)
        validate_contract_collection(
            contract_collection
            + [
                ("UniverseManifest", universe_manifest),
                ("MarketSnapshot", snapshot),
            ]
        )
    except Exception:
        raise MarketDataError("diagnostic_snapshot_contract_invalid") from None

    universe_body = canonical_json_bytes(universe_manifest)
    universe_digest = hashlib.sha256(universe_body).hexdigest()
    universe_artifact = store.put(
        f"universe/{universe_digest}.json",
        universe_body,
        "application/json",
    )
    body = canonical_json_bytes(snapshot)
    snapshot_digest = hashlib.sha256(body).hexdigest()
    snapshot_artifact = store.put(
        f"snapshots/{snapshot_digest}.json",
        body,
        "application/json",
    )
    return DiagnosticSeal(
        universe_manifest=universe_manifest,
        snapshot=snapshot,
        universe_artifact=universe_artifact,
        snapshot_artifact=snapshot_artifact,
        verification=DiagnosticEvidenceVerification(
            status=verification.status,
            verification_level=verification.verification_level,
            external_anchor=verification.external_anchor,
            feed=verification.feed,
            coverage=verification.coverage,
            expected_bar_count=verification.expected_bar_count,
            verified_bar_count=verification.verified_bar_count,
            verified_receipt_count=verification.verified_receipt_count,
            receipt_hashes=verification.receipt_hashes,
            receipt_received_at=verification.receipt_received_at,
            inventory_hash=verification.inventory_hash,
            capability_tested_at=verification.capability_tested_at,
            capability_expires_at=verification.capability_expires_at,
            effective_delay_ms=verification.effective_delay_ms,
            contract_count=verification.contract_count + 2,
        ),
    )


def _verify_capture(
    request: MarketDataRequest,
    result: MarketDataResult,
    store: ContentAddressedStore,
    capability_manifest: Mapping[str, Any],
    *,
    sealed_at: str,
) -> tuple[DiagnosticEvidenceVerification, list[tuple[str, Mapping[str, Any]]]]:
    try:
        validate_contract("DataCapabilityManifest", dict(capability_manifest))
        if "content_hash" in capability_manifest:
            verify_content_hash(
                "DataCapabilityManifest", dict(capability_manifest)
            )
        validate_contract("CalendarManifest", dict(request.calendar_manifest))
        verify_content_hash("CalendarManifest", dict(request.calendar_manifest))
        validate_contract("CandidateCensus", dict(request.candidate_census))
    except Exception:
        raise MarketDataError("diagnostic_input_contract_invalid") from None

    if (
        capability_manifest["capability"] != "MARKET_DATA"
        or capability_manifest["feed"] != "IEX"
        or capability_manifest["feed"] != request.feed
        or capability_manifest["evidence_class"] != request.evidence_class
        or capability_manifest["environment_namespace"]
        != request.environment_namespace
        or request.bar_semantics_manifest["feed"] != request.feed
        or request.feed != "IEX"
        or request.provider != "alpaca"
        or request.adjustment != "RAW"
        or request.timeframe != "1DAY"
        or request.evidence_class
        not in {"SYNTHETIC_FIXTURE", "FORWARD_OPERATIONAL", "FORWARD_SEALED"}
        or (
            request.evidence_class == "SYNTHETIC_FIXTURE"
            and request.environment_namespace != "test"
        )
        or (
            request.evidence_class in {"FORWARD_OPERATIONAL", "FORWARD_SEALED"}
            and request.environment_namespace not in {"production", "research"}
        )
    ):
        raise MarketDataError("diagnostic_feed_semantics_mismatch")
    if capability_manifest["effective_delay_ms"] is not None:
        raise MarketDataError("diagnostic_provider_delay_unresolved")

    sealed_time = _parse_utc(sealed_at)
    tested_at = _parse_utc(capability_manifest["tested_at"])
    expires_at = _parse_utc(capability_manifest["expires_at"])
    if not tested_at <= sealed_time <= expires_at:
        raise MarketDataError("diagnostic_capability_expired")

    bundle = dict(result.data_bundle)
    if (
        bundle.get("completeness") != "COMPLETE"
        or result.failure_codes
        or result.missing_symbols
        or any(bar.get("bar_status") != "FINAL" for bar in result.daily_bars)
    ):
        raise MarketDataError("diagnostic_bundle_incomplete")

    expected_pairs = {
        (assignment["instrument_ref"]["target_id"], session)
        for assignment in request.symbol_assignments
        for session in request.expected_sessions_by_symbol[assignment["symbol"]]
    }
    observed_pairs = {
        (bar["instrument_ref"]["target_id"], bar["session_id"])
        for bar in result.daily_bars
        if bar["bar_status"] == "FINAL"
    }
    if len(observed_pairs) != len(result.daily_bars) or observed_pairs != expected_pairs:
        raise MarketDataError("diagnostic_bar_coverage_mismatch")

    if (
        artifact_inventory_hash(list(result.artifact_inventory))
        != bundle["content_inventory_hash"]
    ):
        raise MarketDataError("diagnostic_inventory_hash_mismatch")

    semantics_text = " ".join(
        request.bar_semantics_manifest["field_meanings"]
    ).casefold()
    if not all(token in semantics_text for token in ("iex", "consolidated", "auction", "extended")):
        raise MarketDataError("diagnostic_feed_semantics_mismatch")

    request_ids = {manifest["id"] for manifest in result.request_manifests}
    request_evidence_ids = {
        item.request_ref["target_id"] for item in result.request_evidence
    }
    bundle_request_ids = _reference_ids(
        bundle["request_refs"], "qc2.identity_market.RequestManifest.v1"
    )
    if (
        request_ids != request_evidence_ids
        or request_ids != bundle_request_ids
        or len(request_ids) != len(result.request_manifests)
    ):
        raise MarketDataError("diagnostic_request_evidence_mismatch")
    receipt_ids = {receipt["id"] for receipt in result.raw_receipts}
    bundle_receipt_ids = _reference_ids(
        bundle["raw_receipt_refs"], "qc2.identity_market.RawReceipt.v1"
    )
    bundle_bar_ids = _reference_ids(
        bundle["bar_refs"], "qc2.identity_market.DailyBar.v1"
    )
    if (
        receipt_ids != bundle_receipt_ids
        or len(receipt_ids) != len(result.raw_receipts)
        or bundle_bar_ids != {bar["id"] for bar in result.daily_bars}
    ):
        raise MarketDataError("diagnostic_receipt_lineage_mismatch")

    artifact_by_path = {
        item["relative_path"]: item for item in result.artifact_inventory
    }
    request_by_id = {manifest["id"]: manifest for manifest in result.request_manifests}
    receipt_hashes: list[str] = []
    receipt_times: list[str] = []
    for receipt in result.raw_receipts:
        try:
            validate_contract("RawReceipt", dict(receipt))
        except Exception:
            raise MarketDataError("diagnostic_receipt_contract_invalid") from None
        request_id = receipt["request_ref"]["target_id"]
        if request_id not in request_by_id:
            raise MarketDataError("diagnostic_receipt_request_missing")
        if request_by_id[request_id]["feed"] != capability_manifest["feed"]:
            raise MarketDataError("diagnostic_request_feed_mismatch")
        matching_evidence = [
            item
            for item in result.request_evidence
            if item.request_ref["target_id"] == request_id
        ]
        if (
            len(matching_evidence) != 1
            or matching_evidence[0].descriptor.get("feed")
            != capability_manifest["feed"]
        ):
            raise MarketDataError("diagnostic_request_feed_mismatch")

        digest = receipt["raw_sha256"]
        relative_path = f"raw/{digest}.bin"
        artifact = artifact_by_path.get(relative_path)
        if (
            artifact is None
            or artifact["sha256"] != digest
            or artifact["length_bytes"] != receipt["byte_length"]
            or receipt["storage_ref"] != f"qc2blob:sha256:{digest}"
        ):
            raise MarketDataError("diagnostic_receipt_artifact_mismatch")
        raw_body = store.read(relative_path, digest)
        if len(raw_body) != receipt["byte_length"]:
            raise MarketDataError("diagnostic_receipt_length_mismatch")

        received_at = _parse_utc(receipt["received_at"])
        if not tested_at <= received_at <= expires_at:
            raise MarketDataError("diagnostic_receipt_outside_capability_window")
        if received_at > _parse_utc(request.cutoff):
            raise MarketDataError("diagnostic_receipt_after_cutoff")
        receipt_hashes.append(digest)
        receipt_times.append(receipt["received_at"])

    if not receipt_hashes:
        raise MarketDataError("diagnostic_receipts_missing")
    if sealed_time < max(_parse_utc(value) for value in receipt_times):
        raise MarketDataError("diagnostic_seal_before_receipt")

    contract_collection = [
        (name, dict(contract)) for name, contract in request.supporting_objects
    ]
    contract_collection.extend(
        ("CorporateActionRecord", dict(version.contract))
        for version in request.known_action_versions
    )
    contract_collection.extend(
        ("RequestManifest", dict(value)) for value in result.request_manifests
    )
    contract_collection.extend(
        ("RawReceipt", dict(value)) for value in result.raw_receipts
    )
    contract_collection.extend(("DailyBar", dict(value)) for value in result.daily_bars)
    contract_collection.extend(
        ("QuarantineCase", dict(value)) for value in result.quarantine_cases
    )
    contract_collection.extend(
        ("CorporateActionRecord", dict(value))
        for value in result.corporate_action_records
    )
    contract_collection.extend(
        ("AdjustmentManifest", dict(value))
        for value in result.adjustment_manifests
    )
    contract_collection.append(("DataBundle", bundle))
    try:
        validate_contract_collection(contract_collection)
    except Exception:
        raise MarketDataError("diagnostic_contract_lineage_invalid") from None

    return (
        DiagnosticEvidenceVerification(
            status="FULL_VERIFIED",
            verification_level="LOCAL_CONTRACT_CLOSURE_AND_CONTENT_HASHES",
            external_anchor=False,
            feed=request.feed,
            coverage=bundle["coverage"],
            expected_bar_count=len(expected_pairs),
            verified_bar_count=len(result.daily_bars),
            verified_receipt_count=len(result.raw_receipts),
            receipt_hashes=tuple(receipt_hashes),
            receipt_received_at=tuple(receipt_times),
            inventory_hash=bundle["content_inventory_hash"],
            capability_tested_at=capability_manifest["tested_at"],
            capability_expires_at=capability_manifest["expires_at"],
            effective_delay_ms=None,
            contract_count=len(contract_collection) + 1,
        ),
        contract_collection,
    )


def _reference(contract: Mapping[str, Any]) -> dict[str, str]:
    reference = {
        "target_schema_name": contract["schema_name"],
        "target_id": contract["id"],
    }
    if "content_hash" in contract:
        reference["content_hash"] = contract["content_hash"]
    return reference


def _reference_ids(
    references: list[Mapping[str, Any]],
    schema_name: str,
) -> set[str]:
    return {
        reference["target_id"]
        for reference in references
        if reference["target_schema_name"] == schema_name
    }


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise MarketDataError("diagnostic_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise MarketDataError("diagnostic_timestamp_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketDataError("diagnostic_timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)
