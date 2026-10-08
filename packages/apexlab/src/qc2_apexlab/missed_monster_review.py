"""Deterministic, research-only missed-monster review queue generation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from qc2_contracts.runtime import ContractValidationError, domain_separated_sha256, validate_contract
from qc2_temporal_firewall.models import canonical_json_bytes, parse_utc_instant

from .models import (
    OUTCOME_SCHEMA,
    PREDICTION_SCHEMA,
    RUNNER_EVENT_SCHEMA,
    RUNNER_GENOME_SCHEMA,
    GenomeError,
    RunnerGenomeRecord,
    _contract_dict,
)

REVIEW_CASE_SCHEMA = "qc2.outcomes_research.ReviewCase.v1"
MISSED_MONSTER_REVIEW_BUILDER_VERSION = "qc2.missed_monster_review.v1"
_LABEL_DEFINITION_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
_EVIDENCE_EVENT_SCHEMA = "qc2.integrity_build.EvidenceEvent.v1"
_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EVIDENCE_CLASSES = frozenset(
    {"SYNTHETIC_FIXTURE", "HISTORICAL_RECONSTRUCTED", "FORWARD_OPERATIONAL", "FORWARD_SEALED"}
)
_ENVIRONMENTS = frozenset({"development", "test", "research"})


class MissedMonsterCategory(StrEnum):
    """Failure category encoded in a ReviewCase reason code."""

    RANKED_LOW = "RANKED_LOW"
    UNSCORABLE = "UNSCORABLE"
    EXCLUDED = "EXCLUDED"
    UNOBSERVED = "UNOBSERVED"
    MISSED_SESSION = "MISSED_SESSION"


class ReviewDisposition(StrEnum):
    """The existing ReviewCase disposition supplied by authoritative inputs."""

    SCORED = "SCORED"
    UNSCORABLE = "UNSCORABLE"
    EXCLUDED = "EXCLUDED"
    PENDING = "PENDING"


class ReviewCoverage(StrEnum):
    """Frozen coverage classification for the event's prediction session."""

    OBSERVED = "OBSERVED"
    UNOBSERVED = "UNOBSERVED"
    MISSED_SESSION = "MISSED_SESSION"


@dataclass(frozen=True, slots=True)
class ReviewArtifactRef:
    """Immutable, typed contract reference used by review evidence."""

    target_schema_name: str
    target_id: str
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_schema_name, str) or not self.target_schema_name:
            raise GenomeError("review artifact reference needs a schema name")
        if not isinstance(self.target_id, str) or not _UUID7.fullmatch(self.target_id):
            raise GenomeError("review artifact reference target_id must be a UUIDv7")
        if self.content_hash is not None and (
            not isinstance(self.content_hash, str) or not _SHA256.fullmatch(self.content_hash)
        ):
            raise GenomeError("review artifact reference content_hash must be lowercase SHA-256")

    @classmethod
    def from_value(cls, value: ReviewArtifactRef | Mapping[str, object]) -> ReviewArtifactRef:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise GenomeError("review artifact references must be typed mappings")
        if set(value) - {"target_schema_name", "target_id", "content_hash"}:
            raise GenomeError("review artifact reference contains unknown fields")
        return cls(
            target_schema_name=value.get("target_schema_name"),  # type: ignore[arg-type]
            target_id=value.get("target_id"),  # type: ignore[arg-type]
            content_hash=value.get("content_hash"),  # type: ignore[arg-type]
        )

    def as_dict(self) -> dict[str, str]:
        result = {
            "target_schema_name": self.target_schema_name,
            "target_id": self.target_id,
        }
        if self.content_hash is not None:
            result["content_hash"] = self.content_hash
        return result

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.target_schema_name, self.target_id)


def _ordered_refs(
    refs: Sequence[ReviewArtifactRef | Mapping[str, object]],
) -> tuple[ReviewArtifactRef, ...]:
    by_identity: dict[tuple[str, str], ReviewArtifactRef] = {}
    for value in refs:
        ref = ReviewArtifactRef.from_value(value)
        prior = by_identity.get(ref.sort_key)
        if prior is not None and prior != ref:
            raise GenomeError("review input contains conflicting references to one artifact")
        by_identity[ref.sort_key] = ref
    return tuple(by_identity[key] for key in sorted(by_identity))


def _utc(value: str, field: str) -> datetime:
    try:
        return parse_utc_instant(value, field)
    except ValueError as exc:
        raise GenomeError(f"{field} must be a valid UTC instant") from exc


def _reference_matches(left: ReviewArtifactRef, right: ReviewArtifactRef) -> bool:
    if (left.target_schema_name, left.target_id) != (
        right.target_schema_name,
        right.target_id,
    ):
        return False
    return (
        left.content_hash is None
        or right.content_hash is None
        or left.content_hash == right.content_hash
    )


def _deterministic_uuid7(identity: Mapping[str, object], *, timestamp: str) -> str:
    """Project a stable review identity into the UUIDv7 shape required by ReviewCase."""
    instant = _utc(timestamp, "policy.frozen_at").astimezone(UTC)
    delta = instant - datetime(1970, 1, 1, tzinfo=UTC)
    timestamp_ms = delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000
    if timestamp_ms < 0 or timestamp_ms >= 1 << 48:
        raise GenomeError("policy.frozen_at is outside the UUIDv7 timestamp range")
    digest = hashlib.sha256(canonical_json_bytes(identity)).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    rand_a = random_bits >> 62
    rand_b = random_bits & ((1 << 62) - 1)
    value = (
        (timestamp_ms << 80)
        | (7 << 76)
        | (rand_a << 64)
        | (2 << 62)
        | rand_b
    )
    return str(UUID(int=value))


@dataclass(frozen=True, slots=True)
class FrozenMissedMonsterPolicy:
    """Frozen event/rank/coverage references and the primary-rank trigger."""

    event_definition_ref: ReviewArtifactRef
    rank_rule_ref: ReviewArtifactRef
    coverage_rule_ref: ReviewArtifactRef
    max_included_rank: int
    frozen_at: str

    def __post_init__(self) -> None:
        for name in ("event_definition_ref", "rank_rule_ref", "coverage_rule_ref"):
            ref = ReviewArtifactRef.from_value(getattr(self, name))
            object.__setattr__(self, name, ref)
        if self.event_definition_ref.target_schema_name != _LABEL_DEFINITION_SCHEMA:
            raise GenomeError("missed-monster policy must bind a LabelDefinition")
        if (
            isinstance(self.max_included_rank, bool)
            or not isinstance(self.max_included_rank, int)
            or self.max_included_rank < 1
        ):
            raise GenomeError("max_included_rank must be a positive integer")
        _utc(self.frozen_at, "policy.frozen_at")

    @property
    def policy_hash(self) -> str:
        payload = {
            "builder_version": MISSED_MONSTER_REVIEW_BUILDER_VERSION,
            "review_kind": "MISSED_MONSTER",
            "event_definition_ref": self.event_definition_ref.as_dict(),
            "rank_rule_ref": self.rank_rule_ref.as_dict(),
            "coverage_rule_ref": self.coverage_rule_ref.as_dict(),
            "max_included_rank": self.max_included_rank,
            "frozen_at": self.frozen_at,
            "classification_order": [
                "UNOBSERVED",
                "EXCLUDED",
                "UNSCORABLE",
                "MISSED_SESSION",
                "RANKED_LOW",
            ],
        }
        return domain_separated_sha256(
            "qc2.apexlab.missed-monster-trigger.v1", canonical_json_bytes(payload)
        )

    @property
    def source_refs(self) -> tuple[ReviewArtifactRef, ...]:
        return _ordered_refs(
            (self.event_definition_ref, self.rank_rule_ref, self.coverage_rule_ref)
        )


@dataclass(frozen=True, slots=True)
class MissedMonsterCandidate:
    """One positive event/session with explicit scoring, eligibility and coverage facts."""

    event_ref: ReviewArtifactRef
    runner_genome_ref: ReviewArtifactRef
    event_definition_ref: ReviewArtifactRef
    outcome_refs: tuple[ReviewArtifactRef, ...]
    session_id: str
    disposition: ReviewDisposition
    coverage: ReviewCoverage
    prediction_ref: ReviewArtifactRef | None = None
    rank: int | None = None
    rank_source_refs: tuple[ReviewArtifactRef, ...] = ()
    status_source_refs: tuple[ReviewArtifactRef, ...] = ()
    evidence_refs: tuple[ReviewArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "event_ref",
            "runner_genome_ref",
            "event_definition_ref",
        ):
            object.__setattr__(
                self, name, ReviewArtifactRef.from_value(getattr(self, name))
            )
        if self.prediction_ref is not None:
            object.__setattr__(
                self,
                "prediction_ref",
                ReviewArtifactRef.from_value(self.prediction_ref),
            )
        for name in ("outcome_refs", "rank_source_refs", "status_source_refs", "evidence_refs"):
            values = _ordered_refs(getattr(self, name))
            object.__setattr__(self, name, values)
        try:
            object.__setattr__(self, "disposition", ReviewDisposition(self.disposition))
            object.__setattr__(self, "coverage", ReviewCoverage(self.coverage))
        except ValueError as exc:
            raise GenomeError("candidate has an unsupported disposition or coverage state") from exc

        if self.event_ref.target_schema_name != RUNNER_EVENT_SCHEMA:
            raise GenomeError("missed-monster candidate event_ref must be a RunnerEvent")
        if self.runner_genome_ref.target_schema_name != RUNNER_GENOME_SCHEMA:
            raise GenomeError("missed-monster candidate requires a RunnerGenome reference")
        if self.event_definition_ref.target_schema_name != _LABEL_DEFINITION_SCHEMA:
            raise GenomeError("candidate event definition must be a LabelDefinition")
        if not self.outcome_refs or any(
            ref.target_schema_name != OUTCOME_SCHEMA for ref in self.outcome_refs
        ):
            raise GenomeError("missed-monster candidate requires resolved Outcome references")
        try:
            parsed_session = datetime.strptime(self.session_id, "%Y-%m-%d").date()
        except (TypeError, ValueError) as exc:
            raise GenomeError("session_id must be an ISO exchange-session date") from exc
        if parsed_session.isoformat() != self.session_id:
            raise GenomeError("session_id must be an ISO exchange-session date")
        if self.prediction_ref is not None and (
            self.prediction_ref.target_schema_name != PREDICTION_SCHEMA
        ):
            raise GenomeError("prediction_ref must reference a Prediction")
        if self.rank is not None and (
            isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1
        ):
            raise GenomeError("rank must be a positive one-based integer")

        if self.disposition is ReviewDisposition.SCORED:
            if (
                self.coverage is not ReviewCoverage.OBSERVED
                or self.prediction_ref is None
                or self.rank is None
                or not self.rank_source_refs
            ):
                raise GenomeError("SCORED candidate needs observed coverage, prediction, rank and evidence")
        elif self.disposition is ReviewDisposition.UNSCORABLE:
            if (
                self.coverage is not ReviewCoverage.OBSERVED
                or self.prediction_ref is not None
                or self.rank is not None
                or not self.status_source_refs
            ):
                raise GenomeError("UNSCORABLE candidate needs observed coverage and eligibility evidence")
        elif self.disposition is ReviewDisposition.EXCLUDED:
            if (
                self.coverage is not ReviewCoverage.OBSERVED
                or self.prediction_ref is not None
                or self.rank is not None
                or not self.status_source_refs
            ):
                raise GenomeError("EXCLUDED candidate needs observed coverage and explicit exclusion evidence")
        elif self.disposition is ReviewDisposition.PENDING:
            if (
                self.coverage not in {ReviewCoverage.UNOBSERVED, ReviewCoverage.MISSED_SESSION}
                or self.prediction_ref is not None
                or self.rank is not None
                or not self.status_source_refs
            ):
                raise GenomeError("PENDING candidate needs an explicit coverage-failure source")

        if self.coverage is ReviewCoverage.UNOBSERVED and (
            self.disposition is not ReviewDisposition.PENDING
        ):
            raise GenomeError("UNOBSERVED coverage cannot be represented as scored or excluded")
        if self.coverage is ReviewCoverage.MISSED_SESSION and (
            self.disposition is not ReviewDisposition.PENDING
        ):
            raise GenomeError("MISSED_SESSION coverage must remain pending")

    @classmethod
    def from_runner_genome(
        cls,
        genome: RunnerGenomeRecord,
        event_contract: Mapping[str, object],
        *,
        session_id: str,
        disposition: ReviewDisposition,
        coverage: ReviewCoverage,
        prediction_ref: ReviewArtifactRef | Mapping[str, object] | None = None,
        rank: int | None = None,
        rank_source_refs: Sequence[ReviewArtifactRef | Mapping[str, object]] = (),
        status_source_refs: Sequence[ReviewArtifactRef | Mapping[str, object]] = (),
        evidence_refs: Sequence[ReviewArtifactRef | Mapping[str, object]] = (),
    ) -> MissedMonsterCandidate:
        """Bind a review row to the exact RunnerEvent and immutable genome lineage."""
        if not isinstance(genome, RunnerGenomeRecord):
            raise GenomeError("from_runner_genome requires a RunnerGenomeRecord")
        event = _contract_dict(event_contract)
        if event.get("schema_name") != RUNNER_EVENT_SCHEMA:
            raise GenomeError("event_contract must be a RunnerEvent")
        event_ref = ReviewArtifactRef(
            RUNNER_EVENT_SCHEMA,
            str(event.get("id")),
            event.get("content_hash") if isinstance(event.get("content_hash"), str) else None,
        )
        genome_contract = genome.contract
        if not _reference_matches(
            event_ref,
            ReviewArtifactRef.from_value(genome_contract["event_ref"]),
        ):
            raise GenomeError("RunnerEvent does not match the RunnerGenome event reference")
        outcome_refs = tuple(
            ReviewArtifactRef.from_value(ref) for ref in genome_contract["outcome_refs"]
        )
        if "outcome_ref" in event and not any(
            _reference_matches(ReviewArtifactRef.from_value(event["outcome_ref"]), ref)
            for ref in outcome_refs
        ):
            raise GenomeError("RunnerEvent outcome is not present in the RunnerGenome")

        normalized_prediction = (
            ReviewArtifactRef.from_value(prediction_ref)
            if prediction_ref is not None
            else None
        )
        genome_predictions = tuple(
            ReviewArtifactRef.from_value(ref)
            for ref in genome_contract["prediction_refs"]
        )
        if normalized_prediction is not None and not any(
            _reference_matches(normalized_prediction, ref) for ref in genome_predictions
        ):
            raise GenomeError("prediction_ref is not linked by the RunnerGenome")

        return cls(
            event_ref=event_ref,
            runner_genome_ref=ReviewArtifactRef.from_value(genome.replay_dependency_ref),
            event_definition_ref=ReviewArtifactRef.from_value(event["label_ref"]),
            outcome_refs=outcome_refs,
            session_id=session_id,
            disposition=disposition,
            coverage=coverage,
            prediction_ref=normalized_prediction,
            rank=rank,
            rank_source_refs=tuple(rank_source_refs),
            status_source_refs=tuple(status_source_refs),
            evidence_refs=tuple(evidence_refs),
        )


@dataclass(frozen=True, slots=True)
class MissedMonsterReviewCase:
    """Validated ReviewCase contract plus non-authoritative research annotations."""

    canonical_json: str
    category: MissedMonsterCategory
    trigger_policy_hash: str
    explanation_template: str
    explanation: str
    research_annotations: tuple[str, ...]

    @property
    def contract(self) -> dict[str, object]:
        return json.loads(self.canonical_json)

    @property
    def case_id(self) -> str:
        return str(self.contract["id"])


@dataclass(frozen=True, slots=True)
class MissedMonsterReviewQueue:
    """Stable ordered queue. It has no mutation API for outcomes, ranks or metrics."""

    policy: FrozenMissedMonsterPolicy
    cases: tuple[MissedMonsterReviewCase, ...]

    @property
    def queue_hash(self) -> str:
        payload = {
            "builder_version": MISSED_MONSTER_REVIEW_BUILDER_VERSION,
            "policy_hash": self.policy.policy_hash,
            "case_ids": [case.case_id for case in self.cases],
        }
        return domain_separated_sha256(
            "qc2.apexlab.missed-monster-review-queue.v1", canonical_json_bytes(payload)
        )


_EXPLANATION_TEMPLATE = (
    "RunnerEvent {event_id} matched frozen event definition {event_definition_id}. "
    "The frozen trigger policy classified this event/session as {category}; "
    "recorded rank: {rank}. Evidence references: {evidence_ids}. "
    "This is a research-only explanation and does not revise outcomes, predictions, "
    "ranks, or official denominators."
)


def _category(candidate: MissedMonsterCandidate, policy: FrozenMissedMonsterPolicy) -> (
    MissedMonsterCategory | None
):
    if candidate.coverage is ReviewCoverage.UNOBSERVED:
        return MissedMonsterCategory.UNOBSERVED
    if candidate.disposition is ReviewDisposition.EXCLUDED:
        return MissedMonsterCategory.EXCLUDED
    if candidate.disposition is ReviewDisposition.UNSCORABLE:
        return MissedMonsterCategory.UNSCORABLE
    if candidate.coverage is ReviewCoverage.MISSED_SESSION:
        return MissedMonsterCategory.MISSED_SESSION
    if (
        candidate.disposition is ReviewDisposition.SCORED
        and candidate.rank is not None
        and candidate.rank > policy.max_included_rank
    ):
        return MissedMonsterCategory.RANKED_LOW
    return None


def build_missed_monster_review_queue(
    candidates: Sequence[MissedMonsterCandidate],
    *,
    policy: FrozenMissedMonsterPolicy,
    created_at: str,
    evidence_class: str,
    environment_namespace: str,
) -> MissedMonsterReviewQueue:
    """Generate every trigger-matching case without mutating its input evidence."""
    if not isinstance(policy, FrozenMissedMonsterPolicy):
        raise GenomeError("review queue requires a frozen trigger policy")
    created_at = str(created_at)
    created_dt = _utc(created_at, "created_at")
    if created_dt < _utc(policy.frozen_at, "policy.frozen_at"):
        raise GenomeError("review queue cannot predate its frozen trigger policy")
    if evidence_class not in _EVIDENCE_CLASSES:
        raise GenomeError("unsupported review evidence class")
    if environment_namespace not in _ENVIRONMENTS:
        raise GenomeError("missed-monster reviews are research-only, not production artifacts")

    candidate_list = tuple(candidates)
    if any(not isinstance(item, MissedMonsterCandidate) for item in candidate_list):
        raise GenomeError("review queue candidates must be MissedMonsterCandidate values")
    keys = [(item.event_ref.target_id, item.session_id) for item in candidate_list]
    if len(keys) != len(set(keys)):
        raise GenomeError("review candidates repeat a RunnerEvent/session pair")

    cases: list[MissedMonsterReviewCase] = []
    for candidate in sorted(
        candidate_list, key=lambda item: (item.event_ref.target_id, item.session_id)
    ):
        if not _reference_matches(candidate.event_definition_ref, policy.event_definition_ref):
            continue
        category = _category(candidate, policy)
        if category is None:
            continue

        rank_source_refs = candidate.rank_source_refs
        status_source_refs = candidate.status_source_refs
        candidate_sources = _ordered_refs(
            (
                candidate.runner_genome_ref,
                *policy.source_refs,
                *rank_source_refs,
                *status_source_refs,
                *((candidate.prediction_ref,) if candidate.prediction_ref is not None else ()),
            )
        )
        evidence_refs = _ordered_refs(
            (
                candidate.event_ref,
                *candidate.outcome_refs,
                *candidate.evidence_refs,
            )
        )
        if any(
            ref.target_schema_name
            not in {RUNNER_EVENT_SCHEMA, OUTCOME_SCHEMA, _EVIDENCE_EVENT_SCHEMA}
            for ref in evidence_refs
        ):
            raise GenomeError("ReviewCase evidence_refs only accepts Event, Outcome or EvidenceEvent")

        identity = {
            "policy_hash": policy.policy_hash,
            "event_ref": candidate.event_ref.as_dict(),
            "runner_genome_ref": candidate.runner_genome_ref.as_dict(),
            "session_id": candidate.session_id,
            "category": category.value,
            "prediction_ref": (
                candidate.prediction_ref.as_dict()
                if candidate.prediction_ref is not None
                else None
            ),
            "rank": candidate.rank,
            "source_refs": [ref.as_dict() for ref in candidate_sources],
            "evidence_refs": [ref.as_dict() for ref in evidence_refs],
        }
        case_id = _deterministic_uuid7(identity, timestamp=policy.frozen_at)
        category_reason = f"MISSED_MONSTER_{category.value}"
        reason_codes = [category_reason, f"TRIGGER_POLICY_SHA256:{policy.policy_hash}", "RESEARCH_ONLY"]
        if category is MissedMonsterCategory.RANKED_LOW:
            reason_codes.append("RANK_EXCEEDS_FROZEN_PRIMARY_K")
        elif candidate.prediction_ref is None:
            reason_codes.append("NO_PREDICTION_REFERENCE")
        payload: dict[str, object] = {
            "schema_name": REVIEW_CASE_SCHEMA,
            "schema_version": "1.0",
            "id": case_id,
            "created_at": created_at,
            "owning_authority": "apexlab",
            "evidence_class": evidence_class,
            "environment_namespace": environment_namespace,
            "source_refs": [ref.as_dict() for ref in candidate_sources],
            "review_kind": "MISSED_MONSTER",
            "event_ref": candidate.event_ref.as_dict(),
            "prediction_ref": (
                candidate.prediction_ref.as_dict()
                if candidate.prediction_ref is not None
                else None
            ),
            "disposition": candidate.disposition.value,
            "reason_codes": reason_codes,
            "reviewed_at": created_at,
            "evidence_refs": [ref.as_dict() for ref in evidence_refs],
        }
        try:
            validate_contract("ReviewCase", payload)
        except ContractValidationError as exc:
            raise GenomeError(f"generated ReviewCase is invalid: {exc}") from exc

        explanation = _EXPLANATION_TEMPLATE.format(
            event_id=candidate.event_ref.target_id,
            event_definition_id=policy.event_definition_ref.target_id,
            category=category.value,
            rank=(str(candidate.rank) if candidate.rank is not None else "not available"),
            evidence_ids=", ".join(ref.target_id for ref in evidence_refs),
        )
        annotations = (
            "RESEARCH_ONLY",
            "OUTCOME_IMMUTABLE",
            "PREDICTION_AND_RANK_IMMUTABLE",
            "OFFICIAL_DENOMINATORS_IMMUTABLE",
            *(
                ("NO_PREDICTION_REFERENCE",)
                if candidate.prediction_ref is None
                else ("PREDICTION_REFERENCE_PRESENT",)
            ),
        )
        cases.append(
            MissedMonsterReviewCase(
                canonical_json=canonical_json_bytes(payload).decode("utf-8"),
                category=category,
                trigger_policy_hash=policy.policy_hash,
                explanation_template=_EXPLANATION_TEMPLATE,
                explanation=explanation,
                research_annotations=annotations,
            )
        )

    return MissedMonsterReviewQueue(policy=policy, cases=tuple(cases))
