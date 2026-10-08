"""Immutable inputs and audit records for matched-decoy research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
import json
from types import MappingProxyType
from typing import Any

from qc2_temporal_firewall import TemporalArtifact

from .models import GenomeError


_OUTCOME_FEATURE_TOKENS = frozenset(
    {"outcome", "mfe", "mae", "realized", "future", "forward", "target", "label"}
)
_OUTCOME_FEATURE_IDS = frozenset(
    {
        "endpoint_return",
        "max_high_return",
        "min_low_return",
        "max_high_price",
        "max_high_session",
        "max_high_session_offset",
        "min_low_price",
        "min_low_session",
        "min_low_session_offset",
        "opening_gap_return",
        "next_open_proxy_endpoint_return",
        "next_open_proxy_max_high_return",
        "next_open_proxy_min_low_return",
        "next_open_proxy_mfe",
        "next_open_proxy_mae",
        "outcome_state",
    }
)


class MatchedDecoyError(GenomeError):
    """A matched-decoy selection cannot be justified by its frozen inputs."""


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _immutable_ref(value: Mapping[str, Any]) -> Mapping[str, str]:
    ref = dict(value)
    if not isinstance(ref.get("target_schema_name"), str) or not isinstance(
        ref.get("target_id"), str
    ):
        raise MatchedDecoyError("typed reference requires target_schema_name and target_id")
    if set(ref) - {"target_schema_name", "target_id", "content_hash"}:
        raise MatchedDecoyError("typed reference contains unsupported fields")
    if "content_hash" in ref and not isinstance(ref["content_hash"], str):
        raise MatchedDecoyError("reference content_hash must be text")
    return MappingProxyType(ref)


def _immutable_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    def freeze(item: Any) -> Any:
        if isinstance(item, Mapping):
            return MappingProxyType({str(key): freeze(child) for key, child in item.items()})
        if isinstance(item, (list, tuple)):
            return tuple(freeze(child) for child in item)
        return item

    return freeze(value)


@dataclass(frozen=True, slots=True)
class CaliperRule:
    """A frozen numeric matching variable and its absolute caliper."""

    feature_id: str
    unit: str
    scale: Decimal
    maximum_difference: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, str) or not self.feature_id.strip():
            raise MatchedDecoyError("matching feature_id must be nonblank text")
        normalized_id = self.feature_id.strip().lower()
        tokens = set(normalized_id.replace("-", "_").replace(".", "_").split("_"))
        if normalized_id in _OUTCOME_FEATURE_IDS or tokens & _OUTCOME_FEATURE_TOKENS:
            raise MatchedDecoyError(
                "outcome, target, and future-derived fields cannot be matching variables"
            )
        object.__setattr__(self, "feature_id", normalized_id)
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise MatchedDecoyError("matching feature unit must be nonblank text")
        for name in ("scale", "maximum_difference"):
            try:
                value = Decimal(str(getattr(self, name)))
            except Exception as exc:
                raise MatchedDecoyError(f"{name} must be a finite decimal") from exc
            if not value.is_finite():
                raise MatchedDecoyError(f"{name} must be a finite decimal")
            object.__setattr__(self, name, value.normalize() if value else Decimal(0))
        if self.scale <= 0 or self.maximum_difference < 0:
            raise MatchedDecoyError("scale must be positive and caliper nonnegative")


@dataclass(frozen=True, slots=True)
class MatchingPolicy:
    """Content-addressed policy; outcome fields are not accepted as variables."""

    rules: tuple[CaliperRule, ...]
    decoys_per_case: int = 1

    def __post_init__(self) -> None:
        if not self.rules or any(not isinstance(rule, CaliperRule) for rule in self.rules):
            raise MatchedDecoyError("matching policy requires CaliperRule entries")
        ordered = tuple(sorted(self.rules, key=lambda rule: rule.feature_id))
        feature_ids = [rule.feature_id for rule in ordered]
        if len(feature_ids) != len(set(feature_ids)):
            raise MatchedDecoyError("matching policy repeats a feature_id")
        if isinstance(self.decoys_per_case, bool) or not isinstance(self.decoys_per_case, int):
            raise MatchedDecoyError("decoys_per_case must be a positive integer")
        if self.decoys_per_case < 1:
            raise MatchedDecoyError("decoys_per_case must be a positive integer")
        object.__setattr__(self, "rules", ordered)

    @property
    def feature_ids(self) -> tuple[str, ...]:
        return tuple(rule.feature_id for rule in self.rules)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "policy_version": "qc2.matched_decoy_policy.v1",
            "distance_metric": "SCALED_L1",
            "distance_scale": "PER_VARIABLE_SCALE",
            "caliper_rule": "ABSOLUTE_DIFFERENCE_PER_VARIABLE",
            "candidate_tie_break": "DISTANCE_THEN_INSTRUMENT_ID",
            "reuse_policy": "WITH_REPLACEMENT_UNBOUNDED_AND_COUNTED",
            "outcome_policy": "POST_MATCH_MEMBERSHIP_ONLY_NO_BACKFILL",
            "decoys_per_case": self.decoys_per_case,
            "rules": [
                {
                    "feature_id": rule.feature_id,
                    "unit": rule.unit,
                    "scale": _decimal_text(rule.scale),
                    "maximum_difference": _decimal_text(rule.maximum_difference),
                }
                for rule in self.rules
            ],
        }


@dataclass(frozen=True, slots=True)
class RiskSetMember:
    """One eligible instrument and its cutoff-bound feature snapshot, if available."""

    instrument: TemporalArtifact
    feature_snapshot: TemporalArtifact | None
    missing_feature_reason: str | None = None


@dataclass(frozen=True, slots=True)
class MatchedDecoyRiskSet:
    """One session/regime stratum backed by a UniverseManifest."""

    universe_manifest: TemporalArtifact
    regime_id: str
    members: tuple[RiskSetMember, ...]
    source_artifacts: tuple[TemporalArtifact, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "members", tuple(self.members))
        object.__setattr__(self, "source_artifacts", tuple(self.source_artifacts))
        if not isinstance(self.regime_id, str) or not self.regime_id.strip():
            raise MatchedDecoyError("risk-set regime_id must be nonblank text")


@dataclass(frozen=True, slots=True)
class PositiveCase:
    """A resolved positive event; it supplies case membership, never match features."""

    event: TemporalArtifact


@dataclass(frozen=True, slots=True)
class VariableDistance:
    feature_id: str
    absolute_difference: Decimal
    scaled_difference: Decimal
    maximum_difference: Decimal


@dataclass(frozen=True, slots=True)
class MatchAssignment:
    event_ref: Mapping[str, str]
    positive_instrument_ref: Mapping[str, str]
    decoy_instrument_ref: Mapping[str, str]
    session_id: str
    regime_id: str
    positive_feature_snapshot_ref: Mapping[str, str]
    decoy_feature_snapshot_ref: Mapping[str, str]
    positive_feature_proof_hash: str
    decoy_feature_proof_hash: str
    variable_distances: tuple[VariableDistance, ...]
    total_distance: Decimal
    candidate_rank: int

    def __post_init__(self) -> None:
        for name in (
            "event_ref",
            "positive_instrument_ref",
            "decoy_instrument_ref",
            "positive_feature_snapshot_ref",
            "decoy_feature_snapshot_ref",
        ):
            object.__setattr__(self, name, _immutable_ref(getattr(self, name)))
        object.__setattr__(self, "variable_distances", tuple(self.variable_distances))


@dataclass(frozen=True, slots=True)
class UnmatchedCase:
    event_ref: Mapping[str, str]
    positive_instrument_ref: Mapping[str, str]
    session_id: str
    regime_id: str
    reason: str
    required_decoys: int
    pre_outcome_matches: int
    confirmed_negative_matches: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_ref", _immutable_ref(self.event_ref))
        object.__setattr__(
            self, "positive_instrument_ref", _immutable_ref(self.positive_instrument_ref)
        )


@dataclass(frozen=True, slots=True)
class StratumCandidateCount:
    event_ref: Mapping[str, str]
    same_stratum_candidates: int
    feature_usable_candidates: int
    within_caliper_candidates: int
    selected_candidates: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_ref", _immutable_ref(self.event_ref))


@dataclass(frozen=True, slots=True)
class MatchPlan:
    """Outcome-blind result from the selection stage."""

    risk_set: MatchedDecoyRiskSet
    policy: MatchingPolicy
    cases: tuple[PositiveCase, ...]
    assignments: tuple[MatchAssignment, ...]
    unmatched_cases: tuple[UnmatchedCase, ...]
    candidate_counts: tuple[StratumCandidateCount, ...]
    catalog_revision: str
    universe_ref: Mapping[str, str]
    session_id: str
    decision_cutoff: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cases", tuple(self.cases))
        object.__setattr__(self, "assignments", tuple(self.assignments))
        object.__setattr__(self, "unmatched_cases", tuple(self.unmatched_cases))
        object.__setattr__(self, "candidate_counts", tuple(self.candidate_counts))
        object.__setattr__(self, "universe_ref", _immutable_ref(self.universe_ref))


@dataclass(frozen=True, slots=True)
class OriginalPopulationEvidence:
    """Resolved-label population evidence, supplied only after matching is frozen."""

    dataset_manifest: TemporalArtifact
    outcome_artifacts: tuple[TemporalArtifact, ...]
    source_artifacts: tuple[TemporalArtifact, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome_artifacts", tuple(self.outcome_artifacts))
        object.__setattr__(self, "source_artifacts", tuple(self.source_artifacts))


@dataclass(frozen=True, slots=True)
class FinalizedMatch:
    assignment: MatchAssignment
    outcome_membership: str
    reuse_count: int
    retained_as_decoy: bool


@dataclass(frozen=True, slots=True)
class DecoyReuse:
    instrument_ref: Mapping[str, str]
    pre_outcome_use_count: int
    confirmed_negative_use_count: int
    outcome_membership: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_ref", _immutable_ref(self.instrument_ref))


@dataclass(frozen=True, slots=True)
class TrainingSampleWeight:
    sample_kind: str
    sample_ref: Mapping[str, str]
    weight: Decimal
    reuse_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_ref", _immutable_ref(self.sample_ref))


@dataclass(frozen=True, slots=True)
class MatchedDecoyRecord:
    canonical_json: str
    temporal_artifact: TemporalArtifact

    @property
    def contract(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


@dataclass(frozen=True, slots=True)
class MatchedDecoyResult:
    record: MatchedDecoyRecord
    plan: MatchPlan
    finalized_matches: tuple[FinalizedMatch, ...]
    reuse: tuple[DecoyReuse, ...]
    unmatched_cases: tuple[UnmatchedCase, ...]
    original_population_ref: Mapping[str, str]
    positive_population_count: int
    negative_population_count: int
    unresolved_population_count: int
    natural_prevalence: Decimal | None
    sample_prevalence: Decimal | None
    training_sample_weights: tuple[TrainingSampleWeight, ...]
    weight_status: str
    audit_hash: str
    calibration_eligible: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "finalized_matches", tuple(self.finalized_matches))
        object.__setattr__(self, "reuse", tuple(self.reuse))
        object.__setattr__(self, "unmatched_cases", tuple(self.unmatched_cases))
        object.__setattr__(self, "training_sample_weights", tuple(self.training_sample_weights))
        object.__setattr__(
            self, "original_population_ref", _immutable_ref(self.original_population_ref)
        )
