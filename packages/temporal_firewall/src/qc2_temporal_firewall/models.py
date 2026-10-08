"""Immutable temporal-firewall inputs and results."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .errors import TemporalViolation


class TemporalMode(StrEnum):
    FORWARD = "FORWARD"
    HISTORICAL_RECONSTRUCTED = "HISTORICAL_RECONSTRUCTED"


class TemporalOperation(StrEnum):
    QUERY = "QUERY"
    EXPORT = "EXPORT"


def parse_utc_instant(value: str, field_name: str) -> datetime:
    """Parse a UTC instant; reject naive or non-UTC offsets."""
    if not isinstance(value, str) or not value:
        raise TemporalViolation("invalid_utc_timestamp", f"{field_name} must be a UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TemporalViolation(
            "invalid_utc_timestamp", f"{field_name} must be a valid UTC instant"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise TemporalViolation("invalid_utc_timestamp", f"{field_name} must use UTC")
    return parsed.astimezone(timezone.utc)


def normalize_kind(value: str) -> str:
    """Normalize a contract schema name or a short artifact kind."""
    if not isinstance(value, str) or not value.strip():
        raise TemporalViolation("invalid_artifact_kind", "artifact kind must be nonblank text")
    name = re.sub(r"(?i)\.v[0-9]+$", "", value.strip())
    name = name.rsplit(".", 1)[-1]
    name = re.sub(r"(?i)v[0-9]+$", "", name)
    normalized = re.sub(r"[^A-Za-z0-9]", "", name).upper()
    if not normalized:
        raise TemporalViolation("invalid_artifact_kind", "artifact kind is not recognizable")
    return normalized


def parse_session_date(value: str, field_name: str) -> date:
    """Parse an exchange session date without deriving it from a UTC instant."""
    if not isinstance(value, str) or not value:
        raise TemporalViolation("invalid_session_date", f"{field_name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise TemporalViolation(
            "invalid_session_date", f"{field_name} must be YYYY-MM-DD"
        ) from exc
    if parsed.isoformat() != value:
        raise TemporalViolation("invalid_session_date", f"{field_name} must be YYYY-MM-DD")
    return parsed


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TemporalViolation(
                "invalid_contract_payload", "JSON object keys must be strings"
            )
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TemporalViolation("invalid_contract_payload", "payload must contain JSON values only")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            _thaw_json(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TemporalViolation("invalid_contract_payload", "payload is not canonical JSON") from exc


def _ref_ids(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TemporalViolation("invalid_dependency_refs", f"{field_name} must be a list")
    result: list[str] = []
    for ref in value:
        if isinstance(ref, str) and ref:
            result.append(ref)
            continue
        if isinstance(ref, Mapping):
            target = ref.get("target_id", ref.get("artifact_id", ref.get("id")))
            if isinstance(target, str) and target:
                result.append(target)
                continue
        raise TemporalViolation(
            "invalid_dependency_refs", f"{field_name} contains a reference without an ID"
        )
    if len(result) != len(set(result)):
        raise TemporalViolation("duplicate_dependency_ref", f"{field_name} contains duplicate IDs")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class TemporalArtifact:
    """An immutable contract plus separate actual and reconstructed availability times."""

    artifact_id: str
    artifact_kind: str
    revision_id: str
    content_hash: str
    created_at: str
    known_at: str
    evidence_class: str
    observed_at: str | None = None
    ingested_at: str | None = None
    event_time: str | None = None
    available_for_learning_at: str | None = None
    historical_assumed_available_at: str | None = None
    historical_assumed_available_for_learning_at: str | None = None
    training_cutoff: str | None = None
    memory_cutoff: str | None = None
    decision_cutoff: str | None = None
    index_cutoff: str | None = None
    training_session_cutoff: str | None = None
    dataset_start_session: str | None = None
    dataset_end_session: str | None = None
    session_id: str | None = None
    dependency_refs: tuple[str, ...] = ()
    index_member_refs: tuple[str, ...] = ()
    logical_key: str | None = None
    alias_target: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for field_name in (
            "artifact_id",
            "artifact_kind",
            "revision_id",
            "content_hash",
            "created_at",
            "known_at",
            "evidence_class",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise TemporalViolation("missing_temporal_field", f"{field_name} is required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise TemporalViolation("invalid_content_hash", "content_hash must be SHA-256 hex")

        time_fields = (
            "created_at",
            "known_at",
            "observed_at",
            "ingested_at",
            "event_time",
            "available_for_learning_at",
            "historical_assumed_available_at",
            "historical_assumed_available_for_learning_at",
            "training_cutoff",
            "memory_cutoff",
            "decision_cutoff",
            "index_cutoff",
        )
        parsed = {
            name: parse_utc_instant(value, name)
            for name in time_fields
            if (value := getattr(self, name)) is not None
        }
        actual_observations = [
            parsed[name] for name in ("created_at", "observed_at", "ingested_at") if name in parsed
        ]
        if parsed["known_at"] < max(actual_observations):
            raise TemporalViolation(
                "known_at_precedes_actual_availability",
                "known_at cannot precede actual creation, observation, or ingestion",
            )
        if (
            "available_for_learning_at" in parsed
            and parsed["available_for_learning_at"] < parsed["known_at"]
        ):
            raise TemporalViolation(
                "learning_availability_precedes_known_at",
                "available_for_learning_at cannot precede actual known_at",
            )
        if (
            "historical_assumed_available_at" in parsed
            and "historical_assumed_available_for_learning_at" in parsed
            and parsed["historical_assumed_available_for_learning_at"]
            < parsed["historical_assumed_available_at"]
        ):
            raise TemporalViolation(
                "simulated_learning_availability_precedes_availability",
                "simulated learning availability cannot precede simulated availability",
            )
        for field_name in (
            "training_session_cutoff",
            "dataset_start_session",
            "dataset_end_session",
            "session_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                parse_session_date(value, field_name)
        if (
            self.dataset_start_session is not None
            and self.dataset_end_session is not None
            and parse_session_date(self.dataset_start_session, "dataset_start_session")
            > parse_session_date(self.dataset_end_session, "dataset_end_session")
        ):
            raise TemporalViolation(
                "invalid_dataset_session_range", "dataset start session exceeds end session"
            )

        for name in ("dependency_refs", "index_member_refs"):
            raw_refs = getattr(self, name)
            if not isinstance(raw_refs, Sequence) or isinstance(raw_refs, (str, bytes)):
                raise TemporalViolation("invalid_dependency_refs", f"{name} must be a list of IDs")
            refs = tuple(raw_refs)
            if any(not isinstance(ref, str) or not ref for ref in refs):
                raise TemporalViolation("invalid_dependency_refs", f"{name} must contain IDs")
            if len(refs) != len(set(refs)):
                raise TemporalViolation("duplicate_dependency_ref", f"{name} contains duplicate IDs")
            object.__setattr__(self, name, refs)

        if self.logical_key is not None and (
            not isinstance(self.logical_key, str) or not self.logical_key.strip()
        ):
            raise TemporalViolation("invalid_logical_key", "logical_key must be nonblank text")
        if normalize_kind(self.artifact_kind) == "METADATAALIAS":
            if not self.logical_key or not self.alias_target:
                raise TemporalViolation(
                    "invalid_metadata_alias", "metadata aliases require a key and target ID"
                )
        if self.alias_target is not None and (
            not isinstance(self.alias_target, str) or not self.alias_target.strip()
        ):
            raise TemporalViolation("invalid_metadata_alias", "alias_target must be nonblank text")
        if not isinstance(self.payload, Mapping):
            raise TemporalViolation("invalid_contract_payload", "payload must be an object")
        object.__setattr__(self, "payload", _freeze_json(self.payload))

    @classmethod
    def from_contract(
        cls,
        contract: Mapping[str, Any],
        *,
        known_at: str | None = None,
        available_for_learning_at: str | None = None,
        revision_id: str | None = None,
        historical_assumed_available_at: str | None = None,
        historical_assumed_available_for_learning_at: str | None = None,
        dependency_refs: Sequence[str] | None = None,
        index_member_refs: Sequence[str] | None = None,
        logical_key: str | None = None,
        alias_target: str | None = None,
        evidence_class: str | None = None,
    ) -> TemporalArtifact:
        """Bind a contract to actual receipt time; provider asof is never a fallback."""
        if not isinstance(contract, Mapping):
            raise TemporalViolation("invalid_contract_payload", "contract must be an object")
        contract_known_at = contract.get("known_at")
        if known_at is not None and contract_known_at is not None:
            if parse_utc_instant(known_at, "known_at") != parse_utc_instant(
                contract_known_at, "contract.known_at"
            ):
                raise TemporalViolation("known_at_mismatch", "explicit and contract known_at differ")
        resolved_known_at = contract_known_at if contract_known_at is not None else known_at
        if not isinstance(resolved_known_at, str):
            raise TemporalViolation(
                "known_at_required",
                "known_at must be supplied from actual installation evidence; provider asof is not usable",
            )

        payload_bytes = canonical_json_bytes(contract)
        digest = hashlib.sha256(payload_bytes).hexdigest()
        raw_revision = revision_id or contract.get("revision_id") or contract.get("revision")
        resolved_revision = raw_revision if isinstance(raw_revision, str) and raw_revision else digest
        raw_id = contract.get("id")
        raw_kind = contract.get("schema_name")
        if not isinstance(raw_id, str) or not raw_id:
            raise TemporalViolation("contract_identity_missing", "contract id is required")
        if not isinstance(raw_kind, str) or not raw_kind:
            raise TemporalViolation("contract_identity_missing", "contract schema_name is required")

        ref_fields = (
            "action_refs",
            "artifact_manifest_ref",
            "calibration_ref",
            "dataset_ref",
            "definition_ref",
            "dependency_refs",
            "embedding_artifact_ref",
            "event_ref",
            "feature_registry_ref",
            "feature_snapshot_ref",
            "head_output_refs",
            "hyperparameter_refs",
            "label_ref",
            "learned_dependency_refs",
            "learned_memory_refs",
            "model_ref",
            "next_open_bar_ref",
            "normalization_ref",
            "outcome_ref",
            "outcome_refs",
            "pre_event_snapshot_refs",
            "prediction_refs",
            "prior_outcome_ref",
            "protocol_registry_ref",
            "protocol_result_refs",
            "provenance_refs",
            "raw_receipt_refs",
            "reference_bar_ref",
            "registry_ref",
            "registry_refs",
            "replacement_outcome_ref",
            "run_ref",
            "snapshot_ref",
            "snapshot_refs",
            "source_refs",
            "split_ref",
            "target_label_refs",
            "temporal_dependency_refs",
            "transform_refs",
            "revision_refs",
        )
        extracted_refs: list[str] = []
        if dependency_refs is None:
            for name in ref_fields:
                if name in contract:
                    value = contract[name]
                    if name.endswith("_ref") and value is not None:
                        value = (value,)
                    extracted_refs.extend(_ref_ids(value, name))
        else:
            extracted_refs.extend(_ref_ids(dependency_refs, "dependency_refs"))

        raw_members = index_member_refs
        if raw_members is None:
            raw_members = contract.get("member_refs", contract.get("member_ids", ()))
        members = _ref_ids(raw_members, "index_member_refs")
        raw_learning = contract.get("available_for_learning_at")
        if (
            available_for_learning_at is not None
            and raw_learning is not None
            and parse_utc_instant(available_for_learning_at, "available_for_learning_at")
            != parse_utc_instant(raw_learning, "contract.available_for_learning_at")
        ):
            raise TemporalViolation(
                "learning_availability_mismatch",
                "explicit and contract available_for_learning_at differ",
            )
        actual_learning = raw_learning or available_for_learning_at
        kind = normalize_kind(raw_kind)
        index_cutoff = (
            contract.get("cutoff")
            if kind in {"EMBEDDINGINDEX", "INDEX", "MEMORYINDEX", "MEMORYINDEXMANIFEST"}
            else None
        )

        return cls(
            artifact_id=raw_id,
            artifact_kind=raw_kind,
            revision_id=resolved_revision,
            content_hash=digest,
            created_at=contract.get("created_at", ""),
            known_at=resolved_known_at,
            evidence_class=evidence_class or contract.get("evidence_class", ""),
            observed_at=contract.get("observed_at"),
            ingested_at=contract.get("ingested_at"),
            event_time=contract.get("event_time"),
            available_for_learning_at=actual_learning,
            historical_assumed_available_at=historical_assumed_available_at,
            historical_assumed_available_for_learning_at=(
                historical_assumed_available_for_learning_at
            ),
            training_cutoff=contract.get("training_cutoff"),
            memory_cutoff=contract.get("memory_cutoff"),
            decision_cutoff=contract.get("decision_cutoff"),
            index_cutoff=index_cutoff,
            training_session_cutoff=contract.get("training_session_cutoff"),
            dataset_start_session=contract.get("time_start"),
            dataset_end_session=contract.get("time_end"),
            session_id=contract.get("session_id"),
            dependency_refs=tuple(dict.fromkeys(extracted_refs)),
            index_member_refs=members,
            logical_key=logical_key,
            alias_target=alias_target,
            payload=contract,
        )


@dataclass(frozen=True, slots=True)
class TemporalPermission:
    """Narrow, explicit API capability; no wildcard or implicit export is allowed."""

    operations: frozenset[TemporalOperation]
    artifact_kinds: frozenset[str]
    allow_historical_reconstructed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.allow_historical_reconstructed, bool):
            raise TemporalViolation(
                "invalid_temporal_permission",
                "historical reconstruction permission must be an explicit boolean",
            )
        if isinstance(self.operations, (str, bytes)) or isinstance(
            self.artifact_kinds, (str, bytes)
        ):
            raise TemporalViolation(
                "invalid_temporal_permission",
                "operations and artifact kinds must be explicit collections",
            )
        operations = frozenset(TemporalOperation(value) for value in self.operations)
        if any(not isinstance(value, str) for value in self.artifact_kinds):
            raise TemporalViolation(
                "invalid_temporal_permission", "artifact kinds must be strings"
            )
        kinds = frozenset(normalize_kind(value) for value in self.artifact_kinds)
        if not operations or not kinds or "" in kinds or "*" in kinds:
            raise TemporalViolation(
                "invalid_temporal_permission",
                "permission must list explicit operations and artifact kinds",
            )
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "artifact_kinds", kinds)


@dataclass(frozen=True, slots=True)
class TemporalQuery:
    """An explicit cutoff and selector; empty/unbounded reads are rejected."""

    cutoff: str
    mode: TemporalMode
    operation: TemporalOperation
    artifact_ids: tuple[str, ...] = ()
    logical_keys: tuple[str, ...] = ()
    training_cutoff: str | None = None
    session_id: str | None = None
    training_session_cutoff: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", TemporalMode(self.mode))
        object.__setattr__(self, "operation", TemporalOperation(self.operation))
        parse_utc_instant(self.cutoff, "cutoff")
        if self.training_cutoff is not None:
            parse_utc_instant(self.training_cutoff, "training_cutoff")
            if parse_utc_instant(self.training_cutoff, "training_cutoff") > parse_utc_instant(
                self.cutoff, "cutoff"
            ):
                raise TemporalViolation(
                    "training_cutoff_after_query_cutoff",
                    "training_cutoff cannot exceed the query cutoff",
                )
        if self.session_id is not None:
            parse_session_date(self.session_id, "session_id")
        if self.training_session_cutoff is not None:
            parse_session_date(self.training_session_cutoff, "training_session_cutoff")
            if (
                self.session_id is not None
                and parse_session_date(self.training_session_cutoff, "training_session_cutoff")
                > parse_session_date(self.session_id, "session_id")
            ):
                raise TemporalViolation(
                    "training_session_after_query_session",
                    "training session cutoff cannot exceed query session",
                )
        if not self.artifact_ids and not self.logical_keys:
            raise TemporalViolation(
                "unbounded_temporal_query", "a temporal query requires IDs or logical keys"
            )
        for field_name in ("artifact_ids", "logical_keys"):
            raw_values = getattr(self, field_name)
            if not isinstance(raw_values, Sequence) or isinstance(raw_values, (str, bytes)):
                raise TemporalViolation(
                    "invalid_query_selector",
                    f"{field_name} must be a list or tuple of strings",
                )
            values = tuple(raw_values)
            if any(not isinstance(value, str) or not value for value in values):
                raise TemporalViolation("invalid_query_selector", f"{field_name} must contain strings")
            if len(values) != len(set(values)):
                raise TemporalViolation("duplicate_query_selector", f"{field_name} contains duplicates")
            object.__setattr__(self, field_name, values)
        if self.operation is TemporalOperation.EXPORT and self.training_cutoff is None:
            raise TemporalViolation(
                "training_cutoff_required", "exports require an explicit training_cutoff"
            )


@dataclass(frozen=True, slots=True)
class TemporalView:
    """Filtered, immutable query result with a mode label and source revision."""

    cutoff: str
    mode: TemporalMode
    operation: TemporalOperation
    evidence_class: str
    catalog_revision: str
    artifacts: tuple[TemporalArtifact, ...]
    resolved_aliases: Mapping[str, str] = field(default_factory=dict)
    dependency_closure: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    cache_hit: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "resolved_aliases", MappingProxyType(dict(self.resolved_aliases)))
        closure = {
            artifact_id: tuple(dependencies)
            for artifact_id, dependencies in self.dependency_closure.items()
        }
        object.__setattr__(self, "dependency_closure", MappingProxyType(closure))


@dataclass(frozen=True, slots=True)
class TemporalExport:
    """Canonical JSON export coupled to the exact filtered view."""

    view: TemporalView
    payload: bytes

