"""Immutable ApexLab inputs and cutoff-proof results."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from qc2_contracts.runtime import (
    CONTENT_ADDRESSED,
    SCHEMA_TO_CONTRACT,
    ContractValidationError,
    canonical_content_hash,
    domain_separated_sha256,
    validate_contract,
    verify_content_hash,
)
from qc2_temporal_firewall import TemporalArtifact
from qc2_temporal_firewall.models import canonical_json_bytes, parse_utc_instant

RUNNER_EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"
RUNNER_GENOME_SCHEMA = "qc2.outcomes_research.RunnerGenome.v1"
MEMORY_INDEX_SCHEMA = "qc2.outcomes_research.MemoryIndexManifest.v1"
OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
MARKET_SNAPSHOT_SCHEMA = "qc2.identity_market.MarketSnapshot.v1"
FEATURE_SNAPSHOT_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
PREDICTION_SCHEMA = "qc2.models_prediction.Prediction.v1"
ARTIFACT_MANIFEST_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"

_SNAPSHOT_SCHEMAS = frozenset({MARKET_SNAPSHOT_SCHEMA, FEATURE_SNAPSHOT_SCHEMA})
_PROVENANCE_SCHEMAS = frozenset(
    {
        "qc2.integrity_build.EvidenceEvent.v1",
        "qc2.identity_market.DataBundle.v1",
        "qc2.outcomes_research.OutcomeRevision.v1",
    }
)
_TEMPORAL_DEPENDENCY_SCHEMAS = frozenset(
    {
        MARKET_SNAPSHOT_SCHEMA,
        FEATURE_SNAPSHOT_SCHEMA,
        PREDICTION_SCHEMA,
        OUTCOME_SCHEMA,
        "qc2.outcomes_research.OutcomeRevision.v1",
        "qc2.integrity_build.EvidenceEvent.v1",
    }
)
_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
RUNNER_MEMORY_INDEX_BUILDER_VERSION = "qc2.runner_memory_index.v1"


class GenomeError(ValueError):
    """A source set cannot justify a RunnerGenome or temporal lookup."""


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _contract_dict(payload: Mapping[str, Any]) -> dict[str, Any]:
    plain = _plain_json(payload)
    if not isinstance(plain, dict):
        raise GenomeError("contract payload must be an object")
    return plain


def _utc(value: str, field: str) -> datetime:
    try:
        return parse_utc_instant(value, field)
    except ValueError as exc:
        raise GenomeError(f"{field} must be a valid UTC instant") from exc


def _date(value: str, field: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise GenomeError(f"{field} must be an ISO exchange-session date") from exc
    if parsed.isoformat() != value:
        raise GenomeError(f"{field} must be an ISO exchange-session date")
    return parsed


def _timestamp_text(value: str, field: str) -> str:
    _utc(value, field)
    return value


def _max_timestamp(values: Sequence[str], field: str) -> str:
    if not values:
        raise GenomeError(f"{field} requires at least one actual timestamp")
    return max(values, key=lambda value: _utc(value, field))


def _ordered_refs(refs: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    by_identity: dict[tuple[str, str], dict[str, str]] = {}
    for ref in refs:
        identity = (ref["target_schema_name"], ref["target_id"])
        prior = by_identity.get(identity)
        if prior is not None and prior != ref:
            raise GenomeError("one source identity resolved to conflicting contract hashes")
        by_identity[identity] = dict(ref)
    return [
        by_identity[key]
        for key in sorted(by_identity, key=lambda item: (item[0], item[1]))
    ]


def _artifact_ref(artifact: TemporalArtifact) -> dict[str, str]:
    payload = _contract_dict(artifact.payload)
    schema_name = payload.get("schema_name")
    artifact_id = payload.get("id")
    contract_name = SCHEMA_TO_CONTRACT.get(schema_name)
    if contract_name is None or artifact_id != artifact.artifact_id:
        raise GenomeError("temporal artifact identity is not backed by a known QC2 contract")
    ref = {"target_schema_name": schema_name, "target_id": artifact_id}
    if contract_name in CONTENT_ADDRESSED:
        content_hash = payload.get("content_hash")
        if not isinstance(content_hash, str) or not _SHA256.fullmatch(content_hash):
            raise GenomeError("content-addressed source is missing its canonical hash")
        ref["content_hash"] = content_hash
    return ref


def contract_artifact(
    contract: Mapping[str, Any],
    *,
    known_at: str,
    historical_assumed_available_at: str | None = None,
    historical_assumed_available_for_learning_at: str | None = None,
) -> TemporalArtifact:
    """Validate a QC2 contract and bind it to separately supplied actual times."""
    payload = _contract_dict(contract)
    schema_name = payload.get("schema_name")
    contract_name = SCHEMA_TO_CONTRACT.get(schema_name)
    if contract_name is None:
        raise GenomeError("source uses an unknown QC2 contract schema")
    try:
        validate_contract(contract_name, payload)
        if contract_name in CONTENT_ADDRESSED:
            verify_content_hash(contract_name, payload)
        artifact = TemporalArtifact.from_contract(
            payload,
            known_at=known_at,
            historical_assumed_available_at=historical_assumed_available_at,
            historical_assumed_available_for_learning_at=(
                historical_assumed_available_for_learning_at
            ),
        )
    except (ContractValidationError, ValueError) as exc:
        raise GenomeError(f"invalid {contract_name} source contract: {exc}") from exc
    return artifact


def seal_content_addressed_contract(
    contract_name: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    """Set and verify a contract's canonical hash without changing its fields."""
    result = _contract_dict(payload)
    if contract_name not in CONTENT_ADDRESSED:
        raise GenomeError(f"{contract_name} is not content-addressed")
    result["content_hash"] = "0" * 64
    try:
        result["content_hash"] = canonical_content_hash(contract_name, result)
        validate_contract(contract_name, result)
        verify_content_hash(contract_name, result)
    except ContractValidationError as exc:
        raise GenomeError(f"cannot seal {contract_name}: {exc}") from exc
    return result


@dataclass(frozen=True, slots=True)
class GenomeDraft:
    """Explicit curation request; an empty prediction tuple means none existed."""

    event_id: str
    pre_event_snapshot_ids: tuple[str, ...]
    prediction_ids: tuple[str, ...]
    outcome_ids: tuple[str, ...]
    provenance_ids: tuple[str, ...]
    event_time: str
    created_at: str
    review_completed_at: str
    curation_version: int
    learning_embargo_until: str | None = None
    historical_assumed_available_at: str | None = None
    historical_assumed_available_for_learning_at: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "event_id",
            "pre_event_snapshot_ids",
            "prediction_ids",
            "outcome_ids",
            "provenance_ids",
        ):
            value = getattr(self, field_name)
            if field_name == "event_id":
                if not isinstance(value, str) or not _UUID7.fullmatch(value):
                    raise GenomeError("event_id must be a UUIDv7")
                continue
            if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
                raise GenomeError(f"{field_name} must be an explicit sequence of IDs")
            values = tuple(value)
            if any(not isinstance(item, str) or not _UUID7.fullmatch(item) for item in values):
                raise GenomeError(f"{field_name} must contain UUIDv7 IDs")
            if len(values) != len(set(values)):
                raise GenomeError(f"{field_name} cannot contain duplicate IDs")
            object.__setattr__(self, field_name, values)
        if not self.pre_event_snapshot_ids:
            raise GenomeError("at least one pre-event snapshot is required")
        if not self.outcome_ids:
            raise GenomeError("at least one resolved outcome is required")
        if isinstance(self.curation_version, bool) or not isinstance(self.curation_version, int):
            raise GenomeError("curation_version must be a positive integer")
        if self.curation_version < 1:
            raise GenomeError("curation_version must be a positive integer")
        for field_name in (
            "event_time",
            "created_at",
            "review_completed_at",
            "learning_embargo_until",
            "historical_assumed_available_at",
            "historical_assumed_available_for_learning_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _timestamp_text(value, field_name)


@dataclass(frozen=True, slots=True)
class RunnerGenomeRecord:
    """Content-addressed genome plus its actual temporal catalog entry."""

    canonical_json: str
    temporal_artifact: TemporalArtifact

    @property
    def contract(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)

    @property
    def prediction_capture_status(self) -> str:
        return "PRESENT" if self.contract["prediction_refs"] else "ABSENT"

    @property
    def replay_dependency_ref(self) -> dict[str, str]:
        contract = self.contract
        return {
            "target_schema_name": RUNNER_GENOME_SCHEMA,
            "target_id": contract["id"],
            "content_hash": contract["content_hash"],
        }


@dataclass(frozen=True, slots=True)
class MemoryIndexRecord:
    """Immutable cutoff-specific index snapshot and actual creation metadata."""

    canonical_json: str
    temporal_artifact: TemporalArtifact
    mode: str

    @property
    def contract(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)

    @property
    def replay_dependency_ref(self) -> dict[str, str]:
        contract = self.contract
        return {
            "target_schema_name": MEMORY_INDEX_SCHEMA,
            "target_id": contract["id"],
            "content_hash": contract["content_hash"],
        }


@dataclass(frozen=True, slots=True)
class GenomeLookup:
    record: RunnerGenomeRecord
    cutoff: str
    mode: str
    catalog_revision: str
    dependency_closure: tuple[str, ...]
    eligibility_proof_hash: str


@dataclass(frozen=True, slots=True)
class MemoryIndexLookup:
    index: MemoryIndexRecord
    members: tuple[RunnerGenomeRecord, ...]
    cutoff: str
    mode: str
    catalog_revision: str
    dependency_closure: tuple[str, ...]
    eligibility_proof_hash: str


def member_inventory_hash(
    cutoff: str, member_refs: Sequence[Mapping[str, str]]
) -> str:
    """Bind index membership, cutoff, and the implementation version."""
    payload = {
        "builder_version": RUNNER_MEMORY_INDEX_BUILDER_VERSION,
        "cutoff": cutoff,
        "member_refs": [_contract_dict(ref) for ref in member_refs],
    }
    return domain_separated_sha256(
        "qc2.apexlab.runner-memory-index-members.v1", canonical_json_bytes(payload)
    )


def eligibility_proof_hash(
    *,
    artifact_ref: Mapping[str, str],
    cutoff: str,
    mode: str,
    catalog_revision: str,
    dependency_closure: Sequence[str],
) -> str:
    payload = {
        "artifact_ref": _contract_dict(artifact_ref),
        "cutoff": cutoff,
        "mode": mode,
        "catalog_revision": catalog_revision,
        "dependency_closure": list(dependency_closure),
    }
    return domain_separated_sha256(
        "qc2.apexlab.temporal-eligibility-proof.v1", canonical_json_bytes(payload)
    )


def _max_actual_source_time(
    sources: Sequence[TemporalArtifact],
    *,
    include_learning_times: bool = True,
) -> str:
    values: list[str] = []
    for source in sources:
        values.extend([source.created_at, source.known_at])
        if source.observed_at is not None:
            values.append(source.observed_at)
        if source.ingested_at is not None:
            values.append(source.ingested_at)
        if include_learning_times and source.available_for_learning_at is not None:
            values.append(source.available_for_learning_at)
    return _max_timestamp(values, "source availability")


def _assert_historical_sources(sources: Sequence[TemporalArtifact]) -> None:
    for source in sources:
        if source.evidence_class.upper() != "HISTORICAL_RECONSTRUCTED":
            raise GenomeError("historical reconstruction cannot mix evidence classes")
        if source.historical_assumed_available_at is None:
            raise GenomeError("historical source is missing an explicit availability assumption")
        if source.historical_assumed_available_for_learning_at is None:
            raise GenomeError("historical source is missing a learning-availability assumption")
