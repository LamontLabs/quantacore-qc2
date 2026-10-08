"""Immutable inputs and row records for the QC2 prediction authority."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from qc2_contracts.runtime import validate_contract


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
SLUG_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z")
UTC = timezone.utc

REFERENCE_SCHEMAS = {
    "epoch": "qc2.validation.ValidationEpoch.v1",
    "snapshot": "qc2.identity_market.MarketSnapshot.v1",
    "census": "qc2.identity_market.CandidateCensus.v1",
    "universe": "qc2.identity_market.UniverseManifest.v1",
    "feature_registry": "qc2.scientific_definitions.FeatureRegistry.v1",
    "protocol_registry": "qc2.scientific_definitions.RunnerProtocolRegistry.v1",
    "label_registry": "qc2.scientific_definitions.LabelRegistry.v1",
    "score_manifest": "qc2.scientific_definitions.ScoreManifest.v1",
    "operating_model": "qc2.models_prediction.ModelManifest.v1",
    "reference_model": "qc2.models_prediction.ModelManifest.v1",
    "shadow_set": "qc2.models_prediction.ShadowPredictionSet.v1",
    "baseline": "qc2.scientific_definitions.BaselineManifest.v1",
    "calendar": "qc2.time_operation.CalendarManifest.v1",
    "memory_index": "qc2.outcomes_research.MemoryIndexManifest.v1",
    "scientific_code": "qc2.integrity_build.ArtifactManifest.v1",
    "instrument": "qc2.identity_market.Instrument.v1",
}


class PredictionAuthorityError(ValueError):
    """A prediction authority operation violates a scientific or state boundary."""


def utc_instant(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise PredictionAuthorityError(f"{field} must be a UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PredictionAuthorityError(f"{field} must be a UTC instant") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise PredictionAuthorityError(f"{field} must use UTC")
    return parsed.astimezone(UTC)


def utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise PredictionAuthorityError("timestamps must be timezone-aware UTC values")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _reference(
    value: Mapping[str, Any],
    expected_schema: str,
    field: str,
    *,
    require_content_hash: bool = False,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise PredictionAuthorityError(f"{field} must be a reference object")
    if set(value) - {"target_schema_name", "target_id", "content_hash"}:
        raise PredictionAuthorityError(f"{field} contains an unknown reference field")
    schema = value.get("target_schema_name")
    target_id = value.get("target_id")
    content_hash = value.get("content_hash")
    if schema != expected_schema or not isinstance(target_id, str) or not target_id:
        raise PredictionAuthorityError(f"{field} must reference {expected_schema}")
    result = {"target_schema_name": schema, "target_id": target_id}
    if content_hash is not None:
        if not isinstance(content_hash, str) or not SHA256_PATTERN.fullmatch(content_hash):
            raise PredictionAuthorityError(f"{field}.content_hash must be lowercase SHA-256")
        result["content_hash"] = content_hash
    elif require_content_hash:
        raise PredictionAuthorityError(f"{field} must pin a lowercase SHA-256 content hash")
    return result


def _references(
    values: Sequence[Mapping[str, Any]],
    expected_schema: str,
    field: str,
    *,
    require_content_hash: bool = False,
) -> tuple[dict[str, str], ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise PredictionAuthorityError(f"{field} must be a list of references")
    normalized = tuple(
        _reference(
            value,
            expected_schema,
            f"{field}[{index}]",
            require_content_hash=require_content_hash,
        )
        for index, value in enumerate(values)
    )
    keys = [(item["target_schema_name"], item["target_id"]) for item in normalized]
    if len(keys) != len(set(keys)):
        raise PredictionAuthorityError(f"{field} contains duplicate references")
    if require_content_hash and any("content_hash" not in item for item in normalized):
        raise PredictionAuthorityError(f"{field} requires content-addressed references")
    return tuple(sorted(normalized, key=lambda item: item["target_id"].encode("utf-8")))


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """A finite, frozen repair budget and reason allowlist for one run."""

    max_attempts: int
    retryable_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise PredictionAuthorityError("retry policy requires a finite positive attempt limit")
        if not isinstance(self.retryable_reason_codes, tuple):
            raise PredictionAuthorityError("retryable reason codes must be an immutable tuple")
        if len(set(self.retryable_reason_codes)) != len(self.retryable_reason_codes):
            raise PredictionAuthorityError("retry policy reason codes must be unique")
        if any(
            not isinstance(code, str) or not SLUG_PATTERN.fullmatch(code)
            for code in self.retryable_reason_codes
        ):
            raise PredictionAuthorityError("retry policy reason codes must be lowercase slugs")


@dataclass(frozen=True, slots=True)
class PredictionBindings:
    """One atomic, pre-inference capture of every dependency used by a run.

    A source adapter must return this complete value from one serializable
    database snapshot. It must never read the Champion or registries in separate
    transactions and must never resolve a missing dependency through a fallback.
    """

    epoch_ref: Mapping[str, Any]
    snapshot_ref: Mapping[str, Any]
    census_ref: Mapping[str, Any]
    universe_ref: Mapping[str, Any]
    feature_registry_ref: Mapping[str, Any]
    protocol_registry_ref: Mapping[str, Any]
    label_registry_ref: Mapping[str, Any]
    score_manifest_ref: Mapping[str, Any]
    operating_champion_pointer: Mapping[str, Any]
    operating_model_ref: Mapping[str, Any]
    reference_model_ref: Mapping[str, Any]
    shadow_prediction_set_refs: Sequence[Mapping[str, Any]]
    baseline_manifest_refs: Sequence[Mapping[str, Any]]
    calendar_ref: Mapping[str, Any]
    memory_index_refs: Sequence[Mapping[str, Any]]
    scientific_code_ref: Mapping[str, Any]
    eligible_instrument_refs: Sequence[Mapping[str, Any]]
    session_id: str
    regime: str
    decision_deadline: str
    seal_deadline: str
    next_regular_session_open_at: str
    evidence_class: str
    environment_namespace: str
    retry_policy: RetryPolicy

    def normalized(self) -> "NormalizedBindings":
        try:
            session = date.fromisoformat(self.session_id)
        except (TypeError, ValueError) as exc:
            raise PredictionAuthorityError("session_id must be an ISO exchange session") from exc
        if session.isoformat() != self.session_id:
            raise PredictionAuthorityError("session_id must be an ISO exchange session")
        if not SLUG_PATTERN.fullmatch(self.regime):
            raise PredictionAuthorityError("regime must be a lowercase slug")
        for name, value in (
            ("evidence_class", self.evidence_class),
            ("environment_namespace", self.environment_namespace),
        ):
            if not isinstance(value, str) or not SLUG_PATTERN.fullmatch(value.lower()):
                raise PredictionAuthorityError(f"{name} is invalid")

        refs = {
            "epoch_ref": _reference(
                self.epoch_ref,
                REFERENCE_SCHEMAS["epoch"],
                "epoch_ref",
                require_content_hash=True,
            ),
            "snapshot_ref": _reference(
                self.snapshot_ref,
                REFERENCE_SCHEMAS["snapshot"],
                "snapshot_ref",
                require_content_hash=True,
            ),
            "census_ref": _reference(
                self.census_ref,
                REFERENCE_SCHEMAS["census"],
                "census_ref",
                require_content_hash=True,
            ),
            "universe_ref": _reference(
                self.universe_ref,
                REFERENCE_SCHEMAS["universe"],
                "universe_ref",
                require_content_hash=True,
            ),
            "feature_registry_ref": _reference(
                self.feature_registry_ref,
                REFERENCE_SCHEMAS["feature_registry"],
                "feature_registry_ref",
                require_content_hash=True,
            ),
            "protocol_registry_ref": _reference(
                self.protocol_registry_ref,
                REFERENCE_SCHEMAS["protocol_registry"],
                "protocol_registry_ref",
                require_content_hash=True,
            ),
            "label_registry_ref": _reference(
                self.label_registry_ref,
                REFERENCE_SCHEMAS["label_registry"],
                "label_registry_ref",
                require_content_hash=True,
            ),
            "score_manifest_ref": _reference(
                self.score_manifest_ref,
                REFERENCE_SCHEMAS["score_manifest"],
                "score_manifest_ref",
                require_content_hash=True,
            ),
            "operating_model_ref": _reference(
                self.operating_model_ref,
                REFERENCE_SCHEMAS["operating_model"],
                "operating_model_ref",
                require_content_hash=True,
            ),
            "reference_model_ref": _reference(
                self.reference_model_ref,
                REFERENCE_SCHEMAS["reference_model"],
                "reference_model_ref",
                require_content_hash=True,
            ),
            "calendar_ref": _reference(
                self.calendar_ref,
                REFERENCE_SCHEMAS["calendar"],
                "calendar_ref",
                require_content_hash=True,
            ),
            "scientific_code_ref": _reference(
                self.scientific_code_ref,
                REFERENCE_SCHEMAS["scientific_code"],
                "scientific_code_ref",
                require_content_hash=True,
            ),
        }

        pointer = copy.deepcopy(dict(self.operating_champion_pointer))
        validate_contract("ChampionPointer", pointer)
        if pointer["role"] != "OPERATING":
            raise PredictionAuthorityError("run binding requires an OPERATING ChampionPointer")
        pointer_model = pointer["model_ref"]
        for field in ("target_schema_name", "target_id", "content_hash"):
            if pointer_model.get(field) != refs["operating_model_ref"].get(field):
                raise PredictionAuthorityError("ChampionPointer does not select the pinned model")
        if (
            pointer["epoch_ref"]["target_id"] != refs["epoch_ref"]["target_id"]
            or pointer["epoch_ref"]["content_hash"] != refs["epoch_ref"]["content_hash"]
        ):
            raise PredictionAuthorityError("ChampionPointer belongs to another validation epoch")
        if (
            pointer["evidence_class"] != self.evidence_class
            or pointer["environment_namespace"] != self.environment_namespace
        ):
            raise PredictionAuthorityError("ChampionPointer evidence context does not match run")
        pointer_epoch = pointer["epoch_ref"]
        if (
            pointer_epoch["target_schema_name"] != refs["epoch_ref"]["target_schema_name"]
            or pointer_epoch["target_id"] != refs["epoch_ref"]["target_id"]
            or pointer_epoch["content_hash"] != refs["epoch_ref"]["content_hash"]
        ):
            raise PredictionAuthorityError("ChampionPointer does not bind this epoch revision")
        if (
            self.environment_namespace == "production"
            and self.evidence_class != "FORWARD_SEALED"
        ):
            raise PredictionAuthorityError("production runs require FORWARD_SEALED evidence")
        if self.evidence_class == "SYNTHETIC_FIXTURE" and self.environment_namespace == "production":
            raise PredictionAuthorityError("fixture evidence cannot activate in production")

        pointer_ref = {
            "target_schema_name": "qc2.governance_owner.ChampionPointer.v1",
            "target_id": pointer["id"],
            "content_hash": pointer["pointer_hash"],
        }
        if pointer["generation"] < 1:
            raise PredictionAuthorityError("Champion generation must be positive")

        collection_specs = {
            "shadow_prediction_set_refs": REFERENCE_SCHEMAS["shadow_set"],
            "baseline_manifest_refs": REFERENCE_SCHEMAS["baseline"],
            "memory_index_refs": REFERENCE_SCHEMAS["memory_index"],
            "eligible_instrument_refs": REFERENCE_SCHEMAS["instrument"],
        }
        collections: dict[str, tuple[dict[str, str], ...]] = {}
        for name, schema in collection_specs.items():
            collections[name] = _references(
                getattr(self, name), schema, name, require_content_hash=True
            )
        if not collections["baseline_manifest_refs"]:
            raise PredictionAuthorityError("run bindings must include baseline manifests")
        if not collections["eligible_instrument_refs"]:
            raise PredictionAuthorityError("run universe has no eligible instruments")

        deadline = utc_instant(self.decision_deadline, "decision_deadline")
        seal_deadline = utc_instant(self.seal_deadline, "seal_deadline")
        next_open = utc_instant(self.next_regular_session_open_at, "next_regular_session_open_at")
        if not deadline <= seal_deadline < next_open:
            raise PredictionAuthorityError(
                "decision and seal deadlines must precede the next regular session open"
            )

        return NormalizedBindings(
            refs=refs,
            pointer=pointer,
            pointer_ref=pointer_ref,
            collections=collections,
            session_id=self.session_id,
            regime=self.regime,
            decision_deadline=utc_text(deadline),
            seal_deadline=utc_text(seal_deadline),
            next_regular_session_open_at=utc_text(next_open),
            evidence_class=self.evidence_class,
            environment_namespace=self.environment_namespace,
            retry_policy=self.retry_policy,
        )


@dataclass(frozen=True, slots=True)
class NormalizedBindings:
    """Validated immutable binding snapshot stored before feature or inference work."""

    refs: Mapping[str, Mapping[str, str]]
    pointer: Mapping[str, Any]
    pointer_ref: Mapping[str, str]
    collections: Mapping[str, tuple[Mapping[str, str], ...]]
    session_id: str
    regime: str
    decision_deadline: str
    seal_deadline: str
    next_regular_session_open_at: str
    evidence_class: str
    environment_namespace: str
    retry_policy: RetryPolicy

    @property
    def champion_generation(self) -> int:
        return int(self.pointer["generation"])

    @property
    def eligible_instrument_ids(self) -> tuple[str, ...]:
        return tuple(
            item["target_id"] for item in self.collections["eligible_instrument_refs"]
        )

    def dependency_refs(self) -> list[dict[str, str]]:
        items = [
            self.refs["feature_registry_ref"],
            self.refs["protocol_registry_ref"],
            self.refs["label_registry_ref"],
            self.refs["score_manifest_ref"],
            self.refs["operating_model_ref"],
            self.refs["reference_model_ref"],
            self.pointer_ref,
            self.refs["calendar_ref"],
            *self.collections["shadow_prediction_set_refs"],
            *self.collections["baseline_manifest_refs"],
            *self.collections["memory_index_refs"],
        ]
        unique: dict[tuple[str, str], dict[str, str]] = {}
        for item in items:
            key = (item["target_schema_name"], item["target_id"])
            current = unique.get(key)
            if current is not None and current != dict(item):
                raise PredictionAuthorityError(
                    "one dependency identity has conflicting content hashes"
                )
            unique[key] = dict(item)
        return [
            unique[key]
            for key in sorted(unique, key=lambda pair: (pair[0].encode(), pair[1].encode()))
        ]

    def source_refs(self) -> list[dict[str, str]]:
        refs = [
            self.refs["census_ref"],
            self.refs["universe_ref"],
            self.refs["scientific_code_ref"],
        ]
        unique = {(item["target_schema_name"], item["target_id"]): dict(item) for item in refs}
        return [
            unique[key]
            for key in sorted(unique, key=lambda pair: (pair[0].encode(), pair[1].encode()))
        ]

    def binding_document(self) -> dict[str, Any]:
        return {
            "epoch_ref": dict(self.refs["epoch_ref"]),
            "session_id": self.session_id,
            "snapshot_ref": dict(self.refs["snapshot_ref"]),
            "census_ref": dict(self.refs["census_ref"]),
            "universe_ref": dict(self.refs["universe_ref"]),
            "feature_registry_ref": dict(self.refs["feature_registry_ref"]),
            "protocol_registry_ref": dict(self.refs["protocol_registry_ref"]),
            "label_registry_ref": dict(self.refs["label_registry_ref"]),
            "score_manifest_ref": dict(self.refs["score_manifest_ref"]),
            "operating_champion_pointer": dict(self.pointer),
            "operating_model_ref": dict(self.refs["operating_model_ref"]),
            "reference_model_ref": dict(self.refs["reference_model_ref"]),
            "shadow_prediction_set_refs": [
                dict(item) for item in self.collections["shadow_prediction_set_refs"]
            ],
            "baseline_manifest_refs": [
                dict(item) for item in self.collections["baseline_manifest_refs"]
            ],
            "calendar_ref": dict(self.refs["calendar_ref"]),
            "memory_index_refs": [dict(item) for item in self.collections["memory_index_refs"]],
            "scientific_code_ref": dict(self.refs["scientific_code_ref"]),
            "eligible_instrument_refs": [
                dict(item) for item in self.collections["eligible_instrument_refs"]
            ],
            "decision_deadline": self.decision_deadline,
            "seal_deadline": self.seal_deadline,
            "next_regular_session_open_at": self.next_regular_session_open_at,
            "retry_policy": {
                "max_attempts": self.retry_policy.max_attempts,
                "retryable_reason_codes": sorted(self.retry_policy.retryable_reason_codes),
                "row_order": "STABLE_INSTRUMENT_ID_ASC",
                "replacement_policy": "FIRST_SCORED_RESULT_WINS",
            },
            "environment_namespace": self.environment_namespace,
            "evidence_class": self.evidence_class,
            "regime": self.regime,
        }


@dataclass(frozen=True, slots=True)
class FeatureRow:
    """Frozen per-instrument facts needed to score and serialize a prediction row."""

    instrument_ref: Mapping[str, Any]
    reference_kind: str
    reference_price: str
    horizon_label_refs: Sequence[Mapping[str, Any]]
    head_output_refs: Sequence[Mapping[str, Any]]
    feature_snapshot_ref: Mapping[str, Any]
    protocol_result_refs: Sequence[Mapping[str, Any]]
    learned_memory_refs: Sequence[Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """One deterministic score result or one explicit unscorable disposition."""

    score: str | None
    reason_code: str | None = None
