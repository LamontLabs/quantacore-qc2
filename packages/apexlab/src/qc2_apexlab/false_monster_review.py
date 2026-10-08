"""Deterministic, research-only false-monster review and annotation records."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID

from qc2_contracts.runtime import (
    CONTENT_ADDRESSED,
    ContractValidationError,
    domain_separated_sha256,
    validate_contract,
    verify_content_hash,
)
from qc2_temporal_firewall.models import canonical_json_bytes, parse_utc_instant

from .failure_models import FailureCategory, failure_category_for_type
from .missed_monster_review import REVIEW_CASE_SCHEMA, ReviewArtifactRef
from .models import GenomeError, _contract_dict

FALSE_MONSTER_REVIEW_BUILDER_VERSION = "qc2.false_monster_review.v1"
FALSE_MONSTER_ANNOTATION_SCHEMA = "qc2.apexlab.false_monster_hypothesis_annotation.v1"

_LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
_SCORE_MANIFEST_SCHEMA = "qc2.scientific_definitions.ScoreManifest.v1"
_HEAD_SCHEMA = "qc2.models_prediction.ModelHeadDefinition.v1"
_HEAD_OUTPUT_SCHEMA = "qc2.models_prediction.ModelHeadOutput.v1"
_PREDICTION_SCHEMA = "qc2.models_prediction.Prediction.v1"
_OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
_OUTCOME_REVISION_SCHEMA = "qc2.outcomes_research.OutcomeRevision.v1"
_RUNNER_EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"
_FAILURE_GENOME_SCHEMA = "qc2.outcomes_research.FailureGenome.v1"
_PROBABILITY_TEXT = re.compile(r"^(?:0|1)\.[0-9]{12}$")
_EVIDENCE_CLASSES = frozenset(
    {"SYNTHETIC_FIXTURE", "HISTORICAL_RECONSTRUCTED", "FORWARD_OPERATIONAL", "FORWARD_SEALED"}
)
_RESEARCH_ENVIRONMENTS = frozenset({"development", "test", "research"})
_FALSE_MONSTER_CATEGORIES = frozenset(
    {
        FailureCategory.NON_EVENT,
        FailureCategory.DOWNSIDE,
        FailureCategory.TIMING_MISS,
        FailureCategory.DATA_ERROR,
    }
)
_CORE_OUTCOME_FIELDS = frozenset(
    {"endpoint_return", "max_high_return", "min_low_return", "mfe", "mae"}
)


class FalseMonsterCategory(StrEnum):
    """False-monster review labels; DATA_ERROR remains diagnostic only."""

    NON_EVENT = "NON_EVENT"
    DOWNSIDE = "DOWNSIDE"
    TIMING_MISS = "TIMING_MISS"
    DATA_ERROR = "DATA_ERROR"


class FalseMonsterUncertaintyReason(StrEnum):
    """Reasons an apparently high-confidence candidate cannot be adjudicated."""

    OUTCOME_NOT_RESOLVED = "OUTCOME_NOT_RESOLVED"
    PROBABILITY_HEAD_UNAVAILABLE = "PROBABILITY_HEAD_UNAVAILABLE"
    PREDICTION_SCORE_UNAVAILABLE = "PREDICTION_SCORE_UNAVAILABLE"
    GROUND_TRUTH_EVENT_MISSING = "GROUND_TRUTH_EVENT_MISSING"
    GROUND_TRUTH_EVENT_MISMATCH = "GROUND_TRUTH_EVENT_MISMATCH"
    FAILURE_ADJUDICATION_MISSING = "FAILURE_ADJUDICATION_MISSING"


def _utc(value: str, field: str) -> datetime:
    try:
        return parse_utc_instant(value, field)
    except (TypeError, ValueError) as exc:
        raise GenomeError(f"{field} must be a valid UTC instant") from exc


def _contract_json(value: Mapping[str, object], field: str) -> str:
    try:
        payload = _contract_dict(value)
        return canonical_json_bytes(payload).decode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GenomeError(f"{field} must be a JSON-compatible contract mapping") from exc


def _validated_contract(
    contract_name: str, value: Mapping[str, object], expected_schema: str
) -> dict[str, object]:
    payload = _contract_dict(value)
    if payload.get("schema_name") != expected_schema:
        raise GenomeError(f"{contract_name} source uses the wrong schema")
    try:
        validate_contract(contract_name, payload)
        if contract_name in CONTENT_ADDRESSED:
            verify_content_hash(contract_name, payload)
    except ContractValidationError as exc:
        raise GenomeError(f"invalid {contract_name} source contract: {exc}") from exc
    return payload


def _ref(value: Mapping[str, object]) -> ReviewArtifactRef:
    schema_name = value.get("schema_name")
    artifact_id = value.get("id")
    if not isinstance(schema_name, str) or not isinstance(artifact_id, str):
        raise GenomeError("source contract has no typed identity")
    content_hash = value.get("content_hash")
    if content_hash is not None and not isinstance(content_hash, str):
        raise GenomeError("source contract content_hash must be text")
    return ReviewArtifactRef(schema_name, artifact_id, content_hash)


def _matches(left: ReviewArtifactRef, right: ReviewArtifactRef) -> bool:
    return (
        left.target_schema_name == right.target_schema_name
        and left.target_id == right.target_id
        and left.content_hash == right.content_hash
    )


def _ordered_refs(
    refs: Sequence[ReviewArtifactRef | Mapping[str, object]],
) -> tuple[ReviewArtifactRef, ...]:
    by_identity: dict[tuple[str, str], ReviewArtifactRef] = {}
    for value in refs:
        ref = ReviewArtifactRef.from_value(value)
        key = ref.sort_key
        previous = by_identity.get(key)
        if previous is not None and previous != ref:
            raise GenomeError("review inputs contain conflicting references to one source")
        by_identity[key] = ref
    return tuple(by_identity[key] for key in sorted(by_identity))


def _deterministic_uuid7(identity: Mapping[str, object], *, timestamp: str) -> str:
    instant = _utc(timestamp, "identity timestamp").astimezone(UTC)
    delta = instant - datetime(1970, 1, 1, tzinfo=UTC)
    timestamp_ms = delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000
    if timestamp_ms < 0 or timestamp_ms >= 1 << 48:
        raise GenomeError("identity timestamp is outside the UUIDv7 range")
    random_bits = int.from_bytes(hashlib.sha256(canonical_json_bytes(identity)).digest()[:10], "big")
    random_bits &= (1 << 74) - 1
    value = (
        (timestamp_ms << 80)
        | (7 << 76)
        | ((random_bits >> 62) << 64)
        | (2 << 62)
        | (random_bits & ((1 << 62) - 1))
    )
    return str(UUID(int=value))


@dataclass(frozen=True, slots=True)
class FrozenFalseMonsterPolicy:
    """Explicit, immutable high-confidence rule bound to a label, score and head."""

    label_definition_ref: ReviewArtifactRef
    score_manifest_ref: ReviewArtifactRef
    probability_head_ref: ReviewArtifactRef
    minimum_probability: str
    frozen_at: str

    def __post_init__(self) -> None:
        expected = {
            "label_definition_ref": _LABEL_SCHEMA,
            "score_manifest_ref": _SCORE_MANIFEST_SCHEMA,
            "probability_head_ref": _HEAD_SCHEMA,
        }
        for name, schema in expected.items():
            ref = ReviewArtifactRef.from_value(getattr(self, name))
            if ref.target_schema_name != schema:
                raise GenomeError(f"{name} must reference {schema}")
            if schema in {
                _LABEL_SCHEMA,
                _SCORE_MANIFEST_SCHEMA,
            } and ref.content_hash is None:
                raise GenomeError(f"{name} requires its content hash")
            object.__setattr__(self, name, ref)
        if not isinstance(self.minimum_probability, str) or not _PROBABILITY_TEXT.fullmatch(
            self.minimum_probability
        ):
            raise GenomeError("minimum_probability must be an exact 12-place decimal in [0, 1]")
        if Decimal(self.minimum_probability) < 0 or Decimal(self.minimum_probability) > 1:
            raise GenomeError("minimum_probability must be in [0, 1]")
        _utc(self.frozen_at, "policy.frozen_at")

    @property
    def policy_hash(self) -> str:
        payload = {
            "builder_version": FALSE_MONSTER_REVIEW_BUILDER_VERSION,
            "review_kind": "FALSE_MONSTER",
            "label_definition_ref": self.label_definition_ref.as_dict(),
            "score_manifest_ref": self.score_manifest_ref.as_dict(),
            "probability_head_ref": self.probability_head_ref.as_dict(),
            "minimum_probability": self.minimum_probability,
            "frozen_at": self.frozen_at,
            "probability_rule": "AVAILABLE probability output >= minimum_probability",
            "failure_type_map": {
                "FALSE_MONSTER": "NON_EVENT",
                "COLLAPSE": "DOWNSIDE",
                "TIMING_MISS": "TIMING_MISS",
                "DATA_ERROR": "DATA_ERROR",
            },
            "non_training_categories": ["DATA_ERROR", "UNRESOLVED"],
        }
        return domain_separated_sha256(
            "qc2.apexlab.false-monster-trigger.v1", canonical_json_bytes(payload)
        )

    @property
    def source_refs(self) -> tuple[ReviewArtifactRef, ...]:
        return _ordered_refs(
            (
                self.label_definition_ref,
                self.score_manifest_ref,
                self.probability_head_ref,
            )
        )


@dataclass(frozen=True, slots=True, init=False)
class FalseMonsterCandidate:
    """Immutable snapshot of the exact prediction, head, outcome and adjudication inputs."""

    _prediction_json: str
    _head_definition_json: str
    _head_output_json: str
    _score_manifest_json: str
    _label_definition_json: str
    _outcome_json: str
    _runner_event_json: str | None
    _failure_genome_json: str | None
    _prior_outcome_json: str | None
    _outcome_revision_json: str | None

    def __init__(
        self,
        *,
        prediction_contract: Mapping[str, object],
        head_definition_contract: Mapping[str, object],
        head_output_contract: Mapping[str, object],
        score_manifest_contract: Mapping[str, object],
        label_definition_contract: Mapping[str, object],
        outcome_contract: Mapping[str, object],
        runner_event_contract: Mapping[str, object] | None = None,
        failure_genome_contract: Mapping[str, object] | None = None,
        prior_outcome_contract: Mapping[str, object] | None = None,
        outcome_revision_contract: Mapping[str, object] | None = None,
    ) -> None:
        fields = {
            "_prediction_json": (prediction_contract, "prediction_contract"),
            "_head_definition_json": (head_definition_contract, "head_definition_contract"),
            "_head_output_json": (head_output_contract, "head_output_contract"),
            "_score_manifest_json": (score_manifest_contract, "score_manifest_contract"),
            "_label_definition_json": (label_definition_contract, "label_definition_contract"),
            "_outcome_json": (outcome_contract, "outcome_contract"),
            "_runner_event_json": (runner_event_contract, "runner_event_contract"),
            "_failure_genome_json": (failure_genome_contract, "failure_genome_contract"),
            "_prior_outcome_json": (prior_outcome_contract, "prior_outcome_contract"),
            "_outcome_revision_json": (outcome_revision_contract, "outcome_revision_contract"),
        }
        for name, (value, field) in fields.items():
            encoded = _contract_json(value, field) if value is not None else None
            object.__setattr__(self, name, encoded)

    @staticmethod
    def _decoded(value: str | None) -> dict[str, object] | None:
        return json.loads(value) if value is not None else None

    @property
    def prediction_contract(self) -> dict[str, object]:
        return json.loads(self._prediction_json)

    @property
    def head_definition_contract(self) -> dict[str, object]:
        return json.loads(self._head_definition_json)

    @property
    def head_output_contract(self) -> dict[str, object]:
        return json.loads(self._head_output_json)

    @property
    def score_manifest_contract(self) -> dict[str, object]:
        return json.loads(self._score_manifest_json)

    @property
    def label_definition_contract(self) -> dict[str, object]:
        return json.loads(self._label_definition_json)

    @property
    def outcome_contract(self) -> dict[str, object]:
        return json.loads(self._outcome_json)

    @property
    def runner_event_contract(self) -> dict[str, object] | None:
        return self._decoded(self._runner_event_json)

    @property
    def failure_genome_contract(self) -> dict[str, object] | None:
        return self._decoded(self._failure_genome_json)

    @property
    def prior_outcome_contract(self) -> dict[str, object] | None:
        return self._decoded(self._prior_outcome_json)

    @property
    def outcome_revision_contract(self) -> dict[str, object] | None:
        return self._decoded(self._outcome_revision_json)


@dataclass(frozen=True, slots=True)
class FalseMonsterReviewCase:
    """Validated immutable ReviewCase plus the frozen research trigger identity."""

    canonical_json: str
    category: FalseMonsterCategory
    policy_hash: str

    def __post_init__(self) -> None:
        try:
            payload = json.loads(self.canonical_json)
            category = FalseMonsterCategory(self.category)
            validate_contract("ReviewCase", payload)
        except (TypeError, ValueError, ContractValidationError) as exc:
            raise GenomeError("false-monster review case must contain a valid ReviewCase") from exc
        if canonical_json_bytes(payload).decode("utf-8") != self.canonical_json:
            raise GenomeError("false-monster ReviewCase JSON must be canonical")
        if not re.fullmatch(r"[0-9a-f]{64}", self.policy_hash):
            raise GenomeError("false-monster policy hash must be lowercase SHA-256")
        expected_kind = (
            "DATA_QUALITY"
            if category is FalseMonsterCategory.DATA_ERROR
            else "FALSE_MONSTER"
        )
        if payload.get("review_kind") != expected_kind:
            raise GenomeError("ReviewCase kind conflicts with its false-monster category")
        if f"FALSE_MONSTER_{category.value}" not in payload.get("reason_codes", []):
            raise GenomeError("ReviewCase reason codes omit its false-monster category")
        if f"FALSE_MONSTER_POLICY_SHA256:{self.policy_hash}" not in payload.get(
            "reason_codes", []
        ):
            raise GenomeError("ReviewCase reason codes omit its frozen policy hash")
        object.__setattr__(self, "category", category)

    @property
    def contract(self) -> dict[str, object]:
        return json.loads(self.canonical_json)

    @property
    def case_id(self) -> str:
        return str(self.contract["id"])

    @property
    def case_ref(self) -> ReviewArtifactRef:
        return ReviewArtifactRef(REVIEW_CASE_SCHEMA, self.case_id)

    @property
    def is_negative_training_example(self) -> bool:
        return self.category in {
            FalseMonsterCategory.NON_EVENT,
            FalseMonsterCategory.DOWNSIDE,
            FalseMonsterCategory.TIMING_MISS,
        }


@dataclass(frozen=True, slots=True)
class FalseMonsterUncertainty:
    """Research-only uncertainty sidecar; never a ReviewCase or training row."""

    canonical_json: str
    reason: FalseMonsterUncertaintyReason
    policy_hash: str

    def __post_init__(self) -> None:
        try:
            record = json.loads(self.canonical_json)
            reason = FalseMonsterUncertaintyReason(self.reason)
        except (TypeError, ValueError) as exc:
            raise GenomeError("uncertainty record has invalid JSON or reason") from exc
        if canonical_json_bytes(record).decode("utf-8") != self.canonical_json:
            raise GenomeError("uncertainty record JSON must be canonical")
        if (
            record.get("record_schema") != "qc2.apexlab.false_monster_uncertainty.v1"
            or record.get("reason_code") != reason.value
            or record.get("policy_hash") != self.policy_hash
            or record.get("training_eligible") is not False
            or record.get("classification") != "UNCERTAIN_NOT_FALSE_POSITIVE"
        ):
            raise GenomeError("uncertainty record must remain separate from false-positive labels")
        object.__setattr__(self, "reason", reason)

    @property
    def record(self) -> dict[str, object]:
        return json.loads(self.canonical_json)

    @property
    def record_id(self) -> str:
        return str(self.record["id"])

    @property
    def is_negative_training_example(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class FalseMonsterReviewQueue:
    """Deterministically ordered false-positive cases and separate uncertainty records."""

    policy: FrozenFalseMonsterPolicy
    cases: tuple[FalseMonsterReviewCase, ...]
    uncertainties: tuple[FalseMonsterUncertainty, ...]

    @property
    def queue_hash(self) -> str:
        payload = {
            "builder_version": FALSE_MONSTER_REVIEW_BUILDER_VERSION,
            "policy_hash": self.policy.policy_hash,
            "case_ids": [item.case_id for item in self.cases],
            "uncertainty_ids": [item.record_id for item in self.uncertainties],
        }
        return domain_separated_sha256(
            "qc2.apexlab.false-monster-review-queue.v1", canonical_json_bytes(payload)
        )


def _candidate_contracts(
    candidate: FalseMonsterCandidate,
) -> dict[str, dict[str, object] | None]:
    values: dict[str, tuple[dict[str, object] | None, str, str]] = {
        "prediction": (candidate.prediction_contract, "Prediction", _PREDICTION_SCHEMA),
        "head_definition": (
            candidate.head_definition_contract,
            "ModelHeadDefinition",
            _HEAD_SCHEMA,
        ),
        "head_output": (candidate.head_output_contract, "ModelHeadOutput", _HEAD_OUTPUT_SCHEMA),
        "score_manifest": (
            candidate.score_manifest_contract,
            "ScoreManifest",
            _SCORE_MANIFEST_SCHEMA,
        ),
        "label_definition": (
            candidate.label_definition_contract,
            "LabelDefinition",
            _LABEL_SCHEMA,
        ),
        "outcome": (candidate.outcome_contract, "Outcome", _OUTCOME_SCHEMA),
        "runner_event": (
            candidate.runner_event_contract,
            "RunnerEvent",
            _RUNNER_EVENT_SCHEMA,
        ),
        "failure_genome": (
            candidate.failure_genome_contract,
            "FailureGenome",
            _FAILURE_GENOME_SCHEMA,
        ),
        "prior_outcome": (candidate.prior_outcome_contract, "Outcome", _OUTCOME_SCHEMA),
        "outcome_revision": (
            candidate.outcome_revision_contract,
            "OutcomeRevision",
            _OUTCOME_REVISION_SCHEMA,
        ),
    }
    result: dict[str, dict[str, object] | None] = {}
    for key, (payload, name, schema) in values.items():
        if payload is None:
            result[key] = None
        else:
            result[key] = _validated_contract(name, payload, schema)
    return result


def _require_ref(actual: object, expected: ReviewArtifactRef, field: str) -> None:
    try:
        if not isinstance(actual, (Mapping, ReviewArtifactRef)):
            raise GenomeError("not a typed reference")
        found = ReviewArtifactRef.from_value(actual)
    except (TypeError, ValueError) as exc:
        raise GenomeError(f"{field} is not a valid typed source reference") from exc
    if not _matches(found, expected):
        raise GenomeError(f"{field} does not match its bound source contract")


def _contains_ref(values: object, expected: ReviewArtifactRef, field: str) -> bool:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise GenomeError(f"{field} must be a reference sequence")
    return any(
        _matches(ReviewArtifactRef.from_value(value), expected)
        for value in values
        if isinstance(value, Mapping)
    )


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise GenomeError(f"{field} must be an exact decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise GenomeError(f"{field} must be an exact decimal string") from exc


def _check_source_consistency(
    contracts: Mapping[str, dict[str, object] | None],
    policy: FrozenFalseMonsterPolicy,
) -> tuple[bool, FalseMonsterUncertaintyReason | None]:
    prediction = contracts["prediction"]
    head = contracts["head_definition"]
    output = contracts["head_output"]
    score_manifest = contracts["score_manifest"]
    label = contracts["label_definition"]
    outcome = contracts["outcome"]
    assert prediction is not None and head is not None and output is not None
    assert score_manifest is not None and label is not None and outcome is not None

    label_ref = _ref(label)
    score_ref = _ref(score_manifest)
    head_ref = _ref(head)
    output_ref = _ref(output)

    if not _matches(label_ref, policy.label_definition_ref):
        return False, None
    if not _matches(score_ref, policy.score_manifest_ref):
        return False, None
    if not _matches(head_ref, policy.probability_head_ref):
        return False, None

    target_event = label.get("target_event")
    if target_event not in {"EXPANSION_RUNNER", "SESSION_MONSTER"}:
        raise GenomeError("false-monster review supports runner and session-monster labels only")
    if head.get("output_kind") != "PROBABILITY" or head.get("availability") != "AVAILABLE":
        raise GenomeError("frozen false-monster head must be an available probability head")
    _require_ref(head.get("label_ref"), label_ref, "ModelHeadDefinition.label_ref")
    if head.get("horizon_sessions") != label.get("horizon_sessions"):
        raise GenomeError("probability head horizon differs from its frozen label definition")
    precision = head.get("output_precision")
    if isinstance(precision, bool) or not isinstance(precision, int) or precision < 0:
        raise GenomeError("probability head output_precision must be a nonnegative integer")

    _require_ref(output.get("head_ref"), head_ref, "ModelHeadOutput.head_ref")
    if output.get("session_id") != prediction.get("session_id"):
        raise GenomeError("prediction and probability head use different sessions")
    prediction_instrument_value = prediction.get("instrument_ref")
    if not isinstance(prediction_instrument_value, Mapping):
        raise GenomeError("Prediction.instrument_ref is not a typed reference")
    prediction_instrument_ref = ReviewArtifactRef.from_value(prediction_instrument_value)
    _require_ref(
        output.get("instrument_ref"),
        prediction_instrument_ref,
        "ModelHeadOutput.instrument_ref",
    )
    if not _contains_ref(prediction.get("head_output_refs"), output_ref, "Prediction.head_output_refs"):
        raise GenomeError("Prediction does not bind the supplied ModelHeadOutput")
    if not _contains_ref(prediction.get("horizon_label_refs"), label_ref, "Prediction.horizon_label_refs"):
        raise GenomeError("Prediction does not bind the frozen event label")
    _require_ref(prediction.get("score_manifest_ref"), score_ref, "Prediction.score_manifest_ref")

    if (
        prediction.get("session_id") != outcome.get("session_id")
        or prediction.get("instrument_ref") != outcome.get("instrument_ref")
    ):
        raise GenomeError("Prediction and Outcome identify different session or instrument")
    _require_ref(outcome.get("label_ref"), label_ref, "Outcome.label_ref")

    frozen_at = _utc(policy.frozen_at, "policy.frozen_at")
    prediction_at = _utc(str(prediction.get("created_at")), "Prediction.created_at")
    output_at = _utc(str(output.get("created_at")), "ModelHeadOutput.created_at")
    outcome_at = _utc(str(outcome.get("created_at")), "Outcome.created_at")
    definition_times = {
        "LabelDefinition.created_at": label.get("created_at"),
        "ScoreManifest.created_at": score_manifest.get("created_at"),
        "ModelHeadDefinition.created_at": head.get("created_at"),
    }
    for field, value in definition_times.items():
        if not isinstance(value, str) or _utc(value, field) > prediction_at:
            raise GenomeError(f"{field} must not postdate its Prediction")
    if frozen_at > prediction_at:
        raise GenomeError("the high-confidence policy must be frozen before prediction")
    if output_at > prediction_at:
        raise GenomeError("ModelHeadOutput postdates its contemporaneous Prediction")
    if prediction_at > outcome_at:
        raise GenomeError("resolved Outcome predates its Prediction")
    if not _matches(
        prediction_instrument_ref,
        ReviewArtifactRef.from_value(outcome["instrument_ref"]),
    ):
        raise GenomeError("Prediction and Outcome instrument references disagree")

    if output.get("output_unit") != "probability":
        raise GenomeError("probability ModelHeadOutput must use the probability unit")
    if output.get("availability") != "AVAILABLE":
        if output.get("output_value") is not None:
            raise GenomeError("unavailable probability head cannot carry an output value")
        return False, FalseMonsterUncertaintyReason.PROBABILITY_HEAD_UNAVAILABLE
    if output.get("output_value") is None:
        return False, FalseMonsterUncertaintyReason.PROBABILITY_HEAD_UNAVAILABLE
    probability_text = output["output_value"]
    probability = _decimal(probability_text, "ModelHeadOutput.output_value")
    if not probability.is_finite() or probability < 0 or probability > 1:
        raise GenomeError("probability head output must be finite and in [0, 1]")
    decimals = len(probability_text.partition(".")[2])
    if decimals != precision:
        raise GenomeError("probability head output does not use its registered precision")

    if prediction.get("disposition") != "SCORED" or prediction.get("score") is None:
        return False, FalseMonsterUncertaintyReason.PREDICTION_SCORE_UNAVAILABLE
    score = _decimal(prediction["score"], "Prediction.score")
    if not score.is_finite() or score < 0 or score > 100:
        raise GenomeError("Prediction.score must be finite and within [0, 100]")

    return probability >= Decimal(policy.minimum_probability), None


def _uncertainty(
    *,
    contracts: Mapping[str, dict[str, object] | None],
    policy: FrozenFalseMonsterPolicy,
    reason: FalseMonsterUncertaintyReason,
    created_at: str,
) -> FalseMonsterUncertainty:
    prediction = contracts["prediction"]
    output = contracts["head_output"]
    outcome = contracts["outcome"]
    assert prediction is not None and output is not None and outcome is not None
    refs_list: list[ReviewArtifactRef] = [
        _ref(prediction),
        _ref(output),
        _ref(outcome),
        policy.label_definition_ref,
        policy.score_manifest_ref,
        policy.probability_head_ref,
    ]
    for key in ("runner_event", "failure_genome", "prior_outcome", "outcome_revision"):
        source = contracts[key]
        if source is not None:
            refs_list.append(_ref(source))
    refs = _ordered_refs(refs_list)
    identity = {
        "policy_hash": policy.policy_hash,
        "reason": reason.value,
        "source_refs": [item.as_dict() for item in refs],
        "created_at": created_at,
    }
    record_id = _deterministic_uuid7(identity, timestamp=policy.frozen_at)
    payload: dict[str, object] = {
        "record_schema": "qc2.apexlab.false_monster_uncertainty.v1",
        "id": record_id,
        "created_at": created_at,
        "policy_hash": policy.policy_hash,
        "reason_code": reason.value,
        "outcome_state": outcome.get("outcome_state"),
        "source_refs": [item.as_dict() for item in refs],
        "classification": "UNCERTAIN_NOT_FALSE_POSITIVE",
        "training_eligible": False,
    }
    return FalseMonsterUncertainty(
        canonical_json=canonical_json_bytes(payload).decode("utf-8"),
        reason=reason,
        policy_hash=policy.policy_hash,
    )


def _failure_category(
    contracts: Mapping[str, dict[str, object] | None],
) -> FalseMonsterCategory:
    prediction = contracts["prediction"]
    outcome = contracts["outcome"]
    event = contracts["runner_event"]
    genome = contracts["failure_genome"]
    assert prediction is not None and outcome is not None and event is not None and genome is not None
    if event.get("event_type") != "FAILURE":
        raise GenomeError("negative false-monster categories require a FAILURE RunnerEvent")
    event_ref = _ref(event)
    prediction_ref = _ref(prediction)
    outcome_ref = _ref(outcome)
    _require_ref(genome.get("event_ref"), event_ref, "FailureGenome.event_ref")
    if not _contains_ref(genome.get("prediction_refs"), prediction_ref, "FailureGenome.prediction_refs"):
        raise GenomeError("FailureGenome does not bind the reviewed Prediction")
    if not _contains_ref(genome.get("outcome_refs"), outcome_ref, "FailureGenome.outcome_refs"):
        raise GenomeError("FailureGenome does not bind the resolved Outcome")

    revision = contracts["outcome_revision"]
    prior = contracts["prior_outcome"]
    event_outcome = ReviewArtifactRef.from_value(event["outcome_ref"])
    if revision is None:
        if prior is not None:
            raise GenomeError("prior Outcome cannot be supplied without an OutcomeRevision")
        if not _matches(event_outcome, outcome_ref):
            raise GenomeError(
                "RunnerEvent outcome differs from the resolved Outcome; an OutcomeRevision is required"
            )
    else:
        if prior is None:
            raise GenomeError("OutcomeRevision requires its prior Outcome source")
        prior_ref = _ref(prior)
        revision_prior = ReviewArtifactRef.from_value(revision["prior_outcome_ref"])
        revision_replacement = ReviewArtifactRef.from_value(revision["replacement_outcome_ref"])
        if not _matches(revision_prior, prior_ref) or not _matches(revision_replacement, outcome_ref):
            raise GenomeError("OutcomeRevision does not bind the supplied prior and replacement Outcomes")
        if not _contains_ref(genome.get("provenance_refs"), _ref(revision), "FailureGenome.provenance_refs"):
            raise GenomeError("FailureGenome does not retain its OutcomeRevision provenance")
        if not (_matches(event_outcome, prior_ref) or _matches(event_outcome, outcome_ref)):
            raise GenomeError("RunnerEvent does not bind either Outcome in its revision lineage")

    try:
        failure_category = failure_category_for_type(str(genome.get("failure_type")))
    except GenomeError:
        raise
    if failure_category not in _FALSE_MONSTER_CATEGORIES:
        raise GenomeError("FailureGenome category is not a false-monster review category")
    if failure_category is FailureCategory.DATA_ERROR:
        if revision is None or prior is None:
            raise GenomeError("DATA_ERROR requires a linked OutcomeRevision and replacement Outcome")
        if outcome.get("outcome_state") != "RESOLVED":
            raise GenomeError("DATA_ERROR replacement Outcome must be resolved")
    elif revision is not None:
        raise GenomeError("OutcomeRevision diagnostics must use the DATA_ERROR category")
    return FalseMonsterCategory(failure_category.value)


def _validate_resolved_outcome(outcome: Mapping[str, object]) -> None:
    validity = outcome.get("field_validity")
    if not isinstance(validity, Sequence) or isinstance(validity, (str, bytes)):
        raise GenomeError("resolved Outcome requires per-field validity evidence")
    statuses: dict[str, str] = {}
    for item in validity:
        if not isinstance(item, Mapping):
            raise GenomeError("Outcome field_validity entries must be objects")
        field_name = item.get("field_name")
        status = item.get("status")
        if not isinstance(field_name, str) or not isinstance(status, str):
            raise GenomeError("Outcome field_validity entries require field and status")
        if field_name in statuses:
            raise GenomeError("Outcome field_validity cannot repeat a field")
        statuses[field_name] = status
    if any(status == "UNRESOLVED" for status in statuses.values()):
        raise GenomeError("unresolved Outcome fields cannot enter false-monster review")
    missing_core = _CORE_OUTCOME_FIELDS.difference(statuses)
    invalid_core = {
        field_name
        for field_name in _CORE_OUTCOME_FIELDS
        if statuses.get(field_name) != "VALID" or outcome.get(field_name) is None
    }
    if missing_core or invalid_core:
        raise GenomeError(
            "false-monster review requires valid endpoint, extrema, MFE and MAE fields"
        )


def _validate_preclassification_sources(
    contracts: Mapping[str, dict[str, object] | None],
    *,
    reviewed_at: str,
) -> None:
    prediction = contracts["prediction"]
    label = contracts["label_definition"]
    outcome = contracts["outcome"]
    assert prediction is not None and label is not None and outcome is not None
    prediction_instrument_value = prediction.get("instrument_ref")
    if not isinstance(prediction_instrument_value, Mapping):
        raise GenomeError("Prediction.instrument_ref is not a typed reference")
    prediction_ref = _ref(prediction)
    label_ref = _ref(label)
    outcome_ref = _ref(outcome)

    event = contracts["runner_event"]
    if event is not None:
        _require_ref(event.get("label_ref"), label_ref, "RunnerEvent.label_ref")
        _require_ref(
            event.get("instrument_ref"),
            ReviewArtifactRef.from_value(prediction_instrument_value),
            "RunnerEvent.instrument_ref",
        )
        event_outcome = ReviewArtifactRef.from_value(event["outcome_ref"])
        revision = contracts["outcome_revision"]
        prior = contracts["prior_outcome"]
        if revision is None:
            if prior is not None:
                raise GenomeError("prior Outcome cannot be supplied without an OutcomeRevision")
            if not _matches(event_outcome, outcome_ref):
                raise GenomeError(
                    "RunnerEvent outcome differs from the resolved Outcome; an OutcomeRevision is required"
                )
        else:
            if prior is None:
                raise GenomeError("OutcomeRevision requires its prior Outcome source")
            prior_ref = _ref(prior)
            _require_ref(
                revision.get("prior_outcome_ref"),
                prior_ref,
                "OutcomeRevision.prior_outcome_ref",
            )
            _require_ref(
                revision.get("replacement_outcome_ref"),
                outcome_ref,
                "OutcomeRevision.replacement_outcome_ref",
            )
            if not (_matches(event_outcome, prior_ref) or _matches(event_outcome, outcome_ref)):
                raise GenomeError("RunnerEvent does not bind either Outcome in its revision lineage")
        if _utc(reviewed_at, "created_at") < _utc(
            str(event.get("detected_at")), "RunnerEvent.detected_at"
        ):
            raise GenomeError("review cannot predate RunnerEvent detection")

    revision = contracts["outcome_revision"]
    prior = contracts["prior_outcome"]
    if revision is None and prior is not None:
        raise GenomeError("prior Outcome cannot be supplied without an OutcomeRevision")
    if revision is not None:
        if prior is None:
            raise GenomeError("OutcomeRevision requires its prior Outcome source")
        if _utc(reviewed_at, "created_at") < _utc(
            str(revision.get("discovered_at")), "OutcomeRevision.discovered_at"
        ):
            raise GenomeError("review cannot predate OutcomeRevision discovery")

    genome = contracts["failure_genome"]
    if genome is not None:
        if event is not None:
            _require_ref(genome.get("event_ref"), _ref(event), "FailureGenome.event_ref")
        if not _contains_ref(genome.get("prediction_refs"), prediction_ref, "FailureGenome.prediction_refs"):
            raise GenomeError("FailureGenome does not bind the reviewed Prediction")
        if not _contains_ref(genome.get("outcome_refs"), outcome_ref, "FailureGenome.outcome_refs"):
            raise GenomeError("FailureGenome does not bind the resolved Outcome")
        if revision is not None and not _contains_ref(
            genome.get("provenance_refs"), _ref(revision), "FailureGenome.provenance_refs"
        ):
            raise GenomeError("FailureGenome does not retain its OutcomeRevision provenance")
        if _utc(reviewed_at, "created_at") < _utc(
            str(genome.get("created_at")), "FailureGenome.created_at"
        ):
            raise GenomeError("review cannot predate FailureGenome adjudication")
        available = genome.get("available_for_learning_at")
        if not isinstance(available, str) or _utc(reviewed_at, "created_at") < _utc(
            available, "FailureGenome.available_for_learning_at"
        ):
            raise GenomeError("review cannot predate FailureGenome learning availability")

    if outcome.get("outcome_state") == "RESOLVED":
        available = outcome.get("available_for_learning_at")
        if not isinstance(available, str) or _utc(reviewed_at, "created_at") < _utc(
            available, "Outcome.available_for_learning_at"
        ):
            raise GenomeError("review cannot predate the resolved Outcome's learning availability")


def _review_case(
    *,
    contracts: Mapping[str, dict[str, object] | None],
    policy: FrozenFalseMonsterPolicy,
    category: FalseMonsterCategory,
    created_at: str,
    evidence_class: str,
    environment_namespace: str,
) -> FalseMonsterReviewCase:
    prediction = contracts["prediction"]
    head = contracts["head_definition"]
    output = contracts["head_output"]
    score_manifest = contracts["score_manifest"]
    label = contracts["label_definition"]
    outcome = contracts["outcome"]
    event = contracts["runner_event"]
    genome = contracts["failure_genome"]
    assert (
        prediction is not None
        and head is not None
        and output is not None
        and score_manifest is not None
        and label is not None
        and outcome is not None
        and event is not None
        and genome is not None
    )
    source_values: list[ReviewArtifactRef] = [
        *policy.source_refs,
        _ref(prediction),
        _ref(head),
        _ref(output),
        _ref(score_manifest),
        _ref(label),
        _ref(outcome),
        _ref(event),
        _ref(genome),
    ]
    prior = contracts["prior_outcome"]
    revision = contracts["outcome_revision"]
    evidence_values: list[ReviewArtifactRef] = [_ref(event), _ref(outcome)]
    if prior is not None:
        source_values.append(_ref(prior))
        evidence_values.append(_ref(prior))
    if revision is not None:
        source_values.append(_ref(revision))
    source_refs = _ordered_refs(source_values)
    evidence_refs = _ordered_refs(evidence_values)

    identity = {
        "policy_hash": policy.policy_hash,
        "category": category.value,
        "created_at": created_at,
        "source_refs": [item.as_dict() for item in source_refs],
        "evidence_refs": [item.as_dict() for item in evidence_refs],
    }
    case_id = _deterministic_uuid7(identity, timestamp=policy.frozen_at)
    reason_codes = [
        f"FALSE_MONSTER_{category.value}",
        f"FALSE_MONSTER_POLICY_SHA256:{policy.policy_hash}",
        "HIGH_CONFIDENCE_THRESHOLD_MET",
        "RESEARCH_ONLY",
    ]
    if category is FalseMonsterCategory.DATA_ERROR:
        reason_codes.append("DATA_ERROR_DIAGNOSTIC_NOT_NEGATIVE_TRAINING")
    payload: dict[str, object] = {
        "schema_name": REVIEW_CASE_SCHEMA,
        "schema_version": "1.0",
        "id": case_id,
        "created_at": created_at,
        "owning_authority": "apexlab",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [item.as_dict() for item in source_refs],
        "review_kind": (
            "DATA_QUALITY"
            if category is FalseMonsterCategory.DATA_ERROR
            else "FALSE_MONSTER"
        ),
        "event_ref": _ref(event).as_dict(),
        "prediction_ref": _ref(prediction).as_dict(),
        "disposition": "SCORED",
        "reason_codes": reason_codes,
        "reviewed_at": created_at,
        "evidence_refs": [item.as_dict() for item in evidence_refs],
    }
    try:
        validate_contract("ReviewCase", payload)
    except ContractValidationError as exc:
        raise GenomeError(f"generated ReviewCase is invalid: {exc}") from exc
    return FalseMonsterReviewCase(
        canonical_json=canonical_json_bytes(payload).decode("utf-8"),
        category=category,
        policy_hash=policy.policy_hash,
    )


def build_false_monster_review_queue(
    candidates: Sequence[FalseMonsterCandidate],
    *,
    policy: FrozenFalseMonsterPolicy,
    created_at: str,
    evidence_class: str,
    environment_namespace: str,
) -> FalseMonsterReviewQueue:
    """Build cases only from frozen high-probability predictions and resolved adjudications."""
    if not isinstance(policy, FrozenFalseMonsterPolicy):
        raise GenomeError("false-monster review requires a frozen policy")
    reviewed_at = str(created_at)
    reviewed_dt = _utc(reviewed_at, "created_at")
    if reviewed_dt < _utc(policy.frozen_at, "policy.frozen_at"):
        raise GenomeError("review queue cannot predate its frozen policy")
    if evidence_class not in _EVIDENCE_CLASSES:
        raise GenomeError("unsupported false-monster evidence class")
    if environment_namespace not in _RESEARCH_ENVIRONMENTS:
        raise GenomeError("false-monster reviews are research-only, not production artifacts")
    candidate_list = tuple(candidates)
    if any(not isinstance(item, FalseMonsterCandidate) for item in candidate_list):
        raise GenomeError("candidates must be immutable FalseMonsterCandidate values")

    seen: set[tuple[str, str]] = set()
    cases: list[FalseMonsterReviewCase] = []
    uncertainties: list[FalseMonsterUncertainty] = []
    for candidate in candidate_list:
        contracts = _candidate_contracts(candidate)
        prediction = contracts["prediction"]
        outcome = contracts["outcome"]
        assert prediction is not None and outcome is not None
        candidate_key = (str(prediction["id"]), str(outcome["id"]))
        if candidate_key in seen:
            raise GenomeError("review queue repeats a Prediction/Outcome pair")
        seen.add(candidate_key)
        if any(
            source is not None
            and source.get("environment_namespace") != environment_namespace
            for source in contracts.values()
        ):
            raise GenomeError("review sources must share the requested research environment")

        is_high_confidence, confidence_uncertainty = _check_source_consistency(
            contracts, policy
        )
        if is_high_confidence or confidence_uncertainty is not None:
            _validate_preclassification_sources(contracts, reviewed_at=reviewed_at)
        if confidence_uncertainty is not None:
            uncertainties.append(
                _uncertainty(
                    contracts=contracts,
                    policy=policy,
                    reason=confidence_uncertainty,
                    created_at=reviewed_at,
                )
            )
            continue
        if not is_high_confidence:
            continue

        if outcome.get("outcome_state") == "RESOLVED":
            _validate_resolved_outcome(outcome)
        if outcome.get("outcome_state") != "RESOLVED":
            uncertainties.append(
                _uncertainty(
                    contracts=contracts,
                    policy=policy,
                    reason=FalseMonsterUncertaintyReason.OUTCOME_NOT_RESOLVED,
                    created_at=reviewed_at,
                )
            )
            continue
        event = contracts["runner_event"]
        if event is None:
            uncertainties.append(
                _uncertainty(
                    contracts=contracts,
                    policy=policy,
                    reason=FalseMonsterUncertaintyReason.GROUND_TRUTH_EVENT_MISSING,
                    created_at=reviewed_at,
                )
            )
            continue
        label = contracts["label_definition"]
        assert label is not None
        event_type = event.get("event_type")
        if event_type in {"EXPANSION_RUNNER", "SESSION_MONSTER"}:
            if event_type == label.get("target_event"):
                if contracts["failure_genome"] is not None:
                    raise GenomeError("scientific success cannot also carry a negative FailureGenome")
                continue
            uncertainties.append(
                _uncertainty(
                    contracts=contracts,
                    policy=policy,
                    reason=FalseMonsterUncertaintyReason.GROUND_TRUTH_EVENT_MISMATCH,
                    created_at=reviewed_at,
                )
            )
            continue
        if event_type != "FAILURE":
            uncertainties.append(
                _uncertainty(
                    contracts=contracts,
                    policy=policy,
                    reason=FalseMonsterUncertaintyReason.GROUND_TRUTH_EVENT_MISMATCH,
                    created_at=reviewed_at,
                )
            )
            continue
        if contracts["failure_genome"] is None:
            uncertainties.append(
                _uncertainty(
                    contracts=contracts,
                    policy=policy,
                    reason=FalseMonsterUncertaintyReason.FAILURE_ADJUDICATION_MISSING,
                    created_at=reviewed_at,
                )
            )
            continue

        genome = contracts["failure_genome"]
        assert genome is not None
        category = _failure_category(contracts)
        cases.append(
            _review_case(
                contracts=contracts,
                policy=policy,
                category=category,
                created_at=reviewed_at,
                evidence_class=evidence_class,
                environment_namespace=environment_namespace,
            )
        )

    cases.sort(key=lambda item: item.case_id)
    uncertainties.sort(key=lambda item: item.record_id)
    return FalseMonsterReviewQueue(
        policy=policy,
        cases=tuple(cases),
        uncertainties=tuple(uncertainties),
    )


@dataclass(frozen=True, slots=True)
class ResearchHypothesisAnnotation:
    """One immutable, hash-chained proposal; it cannot modify a ReviewCase."""

    sequence: int
    annotation_id: str
    case_ref: ReviewArtifactRef
    created_at: str
    hypothesis: str
    supporting_refs: tuple[ReviewArtifactRef, ...]
    previous_hash: str | None
    annotation_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_name": FALSE_MONSTER_ANNOTATION_SCHEMA,
            "sequence": self.sequence,
            "annotation_id": self.annotation_id,
            "case_ref": self.case_ref.as_dict(),
            "created_at": self.created_at,
            "hypothesis": self.hypothesis,
            "supporting_refs": [item.as_dict() for item in self.supporting_refs],
            "previous_hash": self.previous_hash,
            "annotation_hash": self.annotation_hash,
        }


def _annotation_seed(
    *,
    sequence: int,
    case_ref: ReviewArtifactRef,
    created_at: str,
    hypothesis: str,
    supporting_refs: Sequence[ReviewArtifactRef],
    previous_hash: str | None,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "case_ref": case_ref.as_dict(),
        "created_at": created_at,
        "hypothesis": hypothesis,
        "supporting_refs": [item.as_dict() for item in supporting_refs],
        "previous_hash": previous_hash,
    }


def _make_annotation(
    *,
    sequence: int,
    case_ref: ReviewArtifactRef,
    created_at: str,
    hypothesis: str,
    supporting_refs: Sequence[ReviewArtifactRef],
    previous_hash: str | None,
) -> ResearchHypothesisAnnotation:
    seed = _annotation_seed(
        sequence=sequence,
        case_ref=case_ref,
        created_at=created_at,
        hypothesis=hypothesis,
        supporting_refs=supporting_refs,
        previous_hash=previous_hash,
    )
    annotation_id = _deterministic_uuid7(seed, timestamp=created_at)
    body = {"schema_name": FALSE_MONSTER_ANNOTATION_SCHEMA, **seed, "annotation_id": annotation_id}
    annotation_hash = domain_separated_sha256(
        "qc2.apexlab.false-monster-hypothesis-annotation.v1",
        canonical_json_bytes(body),
    )
    return ResearchHypothesisAnnotation(
        sequence=sequence,
        annotation_id=annotation_id,
        case_ref=case_ref,
        created_at=created_at,
        hypothesis=hypothesis,
        supporting_refs=tuple(supporting_refs),
        previous_hash=previous_hash,
        annotation_hash=annotation_hash,
    )


@dataclass(frozen=True, slots=True)
class FalseMonsterAnnotationLedger:
    """Append-only immutable audit chain kept outside authoritative review evidence."""

    case_ref: ReviewArtifactRef
    annotations: tuple[ResearchHypothesisAnnotation, ...] = ()

    def __post_init__(self) -> None:
        case_ref = ReviewArtifactRef.from_value(self.case_ref)
        annotations = tuple(self.annotations)
        if case_ref.target_schema_name != REVIEW_CASE_SCHEMA or case_ref.content_hash is not None:
            raise GenomeError("annotation ledger must bind a ReviewCase")
        object.__setattr__(self, "case_ref", case_ref)
        object.__setattr__(self, "annotations", annotations)
        previous_hash: str | None = None
        previous_created_at: datetime | None = None
        seen: set[str] = set()
        for index, annotation in enumerate(self.annotations, start=1):
            if not isinstance(annotation, ResearchHypothesisAnnotation):
                raise GenomeError("annotation ledger contains an invalid record")
            if annotation.sequence != index or not _matches(annotation.case_ref, case_ref):
                raise GenomeError("annotation chain sequence or ReviewCase reference is invalid")
            if annotation.previous_hash != previous_hash:
                raise GenomeError("annotation hash chain has a broken predecessor link")
            annotation_created_at = _utc(
                annotation.created_at, "annotation.created_at"
            )
            if (
                previous_created_at is not None
                and annotation_created_at < previous_created_at
            ):
                raise GenomeError("annotation timestamps must follow append order")
            if annotation.annotation_id in seen:
                raise GenomeError("annotation chain repeats an annotation identity")
            expected = _make_annotation(
                sequence=annotation.sequence,
                case_ref=case_ref,
                created_at=annotation.created_at,
                hypothesis=annotation.hypothesis,
                supporting_refs=annotation.supporting_refs,
                previous_hash=previous_hash,
            )
            if expected != annotation:
                raise GenomeError("annotation record does not match its immutable hash")
            seen.add(annotation.annotation_id)
            previous_hash = annotation.annotation_hash
            previous_created_at = annotation_created_at

    @property
    def chain_hash(self) -> str:
        if self.annotations:
            return self.annotations[-1].annotation_hash
        return domain_separated_sha256(
            "qc2.apexlab.false-monster-hypothesis-ledger-empty.v1",
            canonical_json_bytes(self.case_ref.as_dict()),
        )

    @property
    def canonical_json(self) -> str:
        return canonical_json_bytes(
            {
                "schema_name": "qc2.apexlab.false_monster_hypothesis_ledger.v1",
                "case_ref": self.case_ref.as_dict(),
                "annotations": [item.as_dict() for item in self.annotations],
                "chain_hash": self.chain_hash,
            }
        ).decode("utf-8")

    def append(
        self,
        hypothesis: str,
        *,
        created_at: str,
        supporting_refs: Sequence[ReviewArtifactRef | Mapping[str, object]] = (),
    ) -> FalseMonsterAnnotationLedger:
        if not isinstance(hypothesis, str) or not hypothesis.strip():
            raise GenomeError("research hypothesis must be nonempty text")
        if len(hypothesis) > 2_000:
            raise GenomeError("research hypothesis exceeds 2,000 characters")
        created_dt = _utc(created_at, "annotation.created_at")
        if self.annotations and created_dt < _utc(
            self.annotations[-1].created_at, "previous annotation.created_at"
        ):
            raise GenomeError("annotation cannot predate the preceding ledger entry")
        refs = _ordered_refs(supporting_refs)
        previous_hash = self.annotations[-1].annotation_hash if self.annotations else None
        annotation = _make_annotation(
            sequence=len(self.annotations) + 1,
            case_ref=self.case_ref,
            created_at=created_at,
            hypothesis=hypothesis,
            supporting_refs=refs,
            previous_hash=previous_hash,
        )
        return FalseMonsterAnnotationLedger(
            case_ref=self.case_ref,
            annotations=(*self.annotations, annotation),
        )


def append_research_hypothesis_annotation(
    case: FalseMonsterReviewCase,
    hypothesis: str,
    *,
    created_at: str,
    ledger: FalseMonsterAnnotationLedger | None = None,
    supporting_refs: Sequence[ReviewArtifactRef | Mapping[str, object]] = (),
) -> FalseMonsterAnnotationLedger:
    """Return a new annotation ledger without changing the case or its evidence."""
    if not isinstance(case, FalseMonsterReviewCase):
        raise GenomeError("hypothesis annotation requires a FalseMonsterReviewCase")
    existing = ledger or FalseMonsterAnnotationLedger(case_ref=case.case_ref)
    if not _matches(existing.case_ref, case.case_ref):
        raise GenomeError("annotation ledger belongs to a different ReviewCase")
    if _utc(created_at, "annotation.created_at") < _utc(
        str(case.contract["created_at"]), "ReviewCase.created_at"
    ):
        raise GenomeError("hypothesis annotation cannot predate its ReviewCase")
    return existing.append(
        hypothesis,
        created_at=created_at,
        supporting_refs=supporting_refs,
    )


def verify_research_annotation_chain(
    ledger: FalseMonsterAnnotationLedger,
) -> bool:
    """Re-validate the hash chain from its frozen, serializable annotation records."""
    if not isinstance(ledger, FalseMonsterAnnotationLedger):
        raise GenomeError("annotation chain verification requires a ledger")
    FalseMonsterAnnotationLedger(
        case_ref=ledger.case_ref,
        annotations=tuple(ledger.annotations),
    )
    return True

