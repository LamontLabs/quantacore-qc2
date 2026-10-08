"""Dependence-aware analysis interfaces and three-state closure logic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from .models import (
    SHA256_PATTERN,
    ValidationAuthorityError,
    exact_decimal,
    utc_instant,
)

MINIMUM_INITIAL_RESAMPLES = 10_000
PUBLIC_VERDICTS = {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE"}
SUPPORTED_DEPENDENCE_METHODS = frozenset(
    {
        "contiguous_block_bootstrap_v1",
        "moving_block_bootstrap_v1",
        "stationary_block_bootstrap_v1",
        "event_cluster_bootstrap_v1",
    }
)


@dataclass(frozen=True, slots=True)
class FrozenAnalysisPlan:
    """Values copied from an owner-approved prospective plan; none are guessed here."""

    interval_method: str | None = None
    alpha: Decimal | None = None
    practical_minimum_effect: Decimal | None = None
    minimum_event_clusters: int | None = None
    minimum_effective_blocks: int | None = None
    resample_count: int | None = None
    missingness_method: str | None = None
    stopping_rule: str | None = None
    calibration_status: str = "UNEVALUATED"
    frozen_at: str | None = None

    def __post_init__(self) -> None:
        if self.interval_method is not None and not isinstance(self.interval_method, str):
            raise ValidationAuthorityError("interval_method must be text or unknown")
        if self.alpha is not None and not Decimal(0) < exact_decimal(self.alpha, "alpha") < Decimal(1):
            raise ValidationAuthorityError("alpha must be between zero and one")
        if self.practical_minimum_effect is not None:
            exact_decimal(self.practical_minimum_effect, "practical_minimum_effect")
        for name, value in (
            ("minimum_event_clusters", self.minimum_event_clusters),
            ("minimum_effective_blocks", self.minimum_effective_blocks),
            ("resample_count", self.resample_count),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ValidationAuthorityError(f"{name} must be a positive integer")
        if self.calibration_status not in {"UNEVALUATED", "CALIBRATED_AND_FROZEN"}:
            raise ValidationAuthorityError("calibration_status is not a supported gate state")
        if self.frozen_at is not None:
            utc_instant(self.frozen_at, "frozen_at")


@dataclass(frozen=True, slots=True)
class DependenceEstimate:
    """Output contract for a block-based interval implementation supplied by a method."""

    method_id: str
    lower_confidence_bound: Decimal | None
    upper_confidence_bound: Decimal | None
    effective_blocks: int | None
    event_clusters: int | None
    resample_count: int | None
    coverage_gate_passed: bool | None
    deterministic_seed_hash: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.method_id, str) or not self.method_id:
            raise ValidationAuthorityError("dependence estimate requires a method ID")
        for name, value in (
            ("effective_blocks", self.effective_blocks),
            ("event_clusters", self.event_clusters),
            ("resample_count", self.resample_count),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValidationAuthorityError(f"{name} must be a nonnegative integer or unknown")
        if self.coverage_gate_passed not in {True, False, None}:
            raise ValidationAuthorityError("coverage_gate_passed must be boolean or unknown")
        if self.deterministic_seed_hash is not None and (
            not isinstance(self.deterministic_seed_hash, str)
            or not SHA256_PATTERN.fullmatch(self.deterministic_seed_hash)
        ):
            raise ValidationAuthorityError("deterministic seed commitment must be lowercase SHA-256")


class DependenceMethod(Protocol):
    """Adapter interface for a prospectively selected, dependence-aware method."""

    method_id: str

    def estimate(
        self,
        paired_session_differences: Sequence[Decimal],
        *,
        plan: FrozenAnalysisPlan,
    ) -> DependenceEstimate:
        """Return session-block inference and its simulation-coverage evidence."""


@dataclass(frozen=True, slots=True)
class DependenceReadiness:
    ready: bool
    reason_codes: tuple[str, ...]


def assess_dependence_readiness(
    plan: FrozenAnalysisPlan | None,
    estimate: DependenceEstimate | None,
) -> DependenceReadiness:
    """Reject IID-only results and keep missing calibration gates explicitly unevaluated."""
    reasons: list[str] = []
    if plan is None:
        return DependenceReadiness(False, ("analysis_plan_not_frozen",))
    required = (
        plan.interval_method,
        plan.alpha,
        plan.practical_minimum_effect,
        plan.minimum_event_clusters,
        plan.minimum_effective_blocks,
        plan.resample_count,
        plan.missingness_method,
        plan.stopping_rule,
        plan.frozen_at,
    )
    if any(item is None for item in required) or plan.calibration_status != "CALIBRATED_AND_FROZEN":
        reasons.append("calibration_gates_unevaluated")
    if (
        plan.interval_method is not None
        and plan.interval_method.strip().lower() not in SUPPORTED_DEPENDENCE_METHODS
    ):
        reasons.append("dependence_method_unregistered")
    if estimate is None:
        reasons.append("dependence_estimate_unavailable")
        return DependenceReadiness(False, tuple(reasons))

    if not isinstance(estimate.method_id, str):
        reasons.append("iid_or_unspecified_interval_method_forbidden")
        method = ""
    else:
        method = estimate.method_id.strip().lower()
    if not method or "iid" in method or "independent_observation" in method:
        reasons.append("iid_or_unspecified_interval_method_forbidden")
    elif method not in SUPPORTED_DEPENDENCE_METHODS:
        reasons.append("dependence_method_unregistered")
    if plan.interval_method is not None and estimate.method_id != plan.interval_method:
        reasons.append("dependence_method_does_not_match_frozen_plan")
    if estimate.lower_confidence_bound is None or estimate.upper_confidence_bound is None:
        reasons.append("confidence_interval_unavailable")
    elif (
        not isinstance(estimate.lower_confidence_bound, Decimal)
        or not isinstance(estimate.upper_confidence_bound, Decimal)
        or not estimate.lower_confidence_bound.is_finite()
        or not estimate.upper_confidence_bound.is_finite()
        or estimate.lower_confidence_bound > estimate.upper_confidence_bound
    ):
        reasons.append("confidence_interval_invalid")
    if estimate.resample_count is None or estimate.resample_count < MINIMUM_INITIAL_RESAMPLES:
        reasons.append("deterministic_resample_policy_not_met")
    if (
        plan.resample_count is not None
        and estimate.resample_count is not None
        and estimate.resample_count < plan.resample_count
    ):
        reasons.append("frozen_resample_count_not_met")
    if (
        plan.minimum_event_clusters is None
        or estimate.event_clusters is None
        or estimate.event_clusters < plan.minimum_event_clusters
    ):
        reasons.append("independent_event_cluster_gate_not_met")
    if (
        plan.minimum_effective_blocks is None
        or estimate.effective_blocks is None
        or estimate.effective_blocks < plan.minimum_effective_blocks
    ):
        reasons.append("effective_time_block_gate_not_met")
    if estimate.coverage_gate_passed is not True:
        reasons.append("simulated_interval_coverage_gate_not_passed")
    if (
        estimate.deterministic_seed_hash is None
        or not SHA256_PATTERN.fullmatch(estimate.deterministic_seed_hash)
    ):
        reasons.append("deterministic_seed_commitment_missing")
    return DependenceReadiness(not reasons, tuple(dict.fromkeys(reasons)))


@dataclass(frozen=True, slots=True)
class ClosureEvidence:
    """Frozen facts consumed by closure; unknown values cannot be coerced to success."""

    integrity_status: str | None
    scheduled_opportunities_reconciled: bool | None
    required_outcomes_matured: bool | None
    adverse_missingness_lower_bound: Decimal | None
    operational_gates: Mapping[str, bool | None] = field(default_factory=dict)
    calibration_gates: Mapping[str, bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        allowed_integrity = {
            None,
            "VALID",
            "FULL_VERIFIED",
            "PARTIAL_SCAN",
            "FAILED",
            "INVALID",
            "UNAVAILABLE",
        }
        if self.integrity_status not in allowed_integrity:
            raise ValidationAuthorityError("integrity_status is not a supported gate state")
        if self.scheduled_opportunities_reconciled not in {True, False, None}:
            raise ValidationAuthorityError("scheduled opportunity gate must be boolean or unknown")
        if self.required_outcomes_matured not in {True, False, None}:
            raise ValidationAuthorityError("outcome maturity gate must be boolean or unknown")
        if self.adverse_missingness_lower_bound is not None:
            exact_decimal(
                self.adverse_missingness_lower_bound,
                "adverse_missingness_lower_bound",
            )
        for label, gates in (
            ("operational_gates", self.operational_gates),
            ("calibration_gates", self.calibration_gates),
        ):
            if not isinstance(gates, Mapping):
                raise ValidationAuthorityError(f"{label} must be a mapping")
            if any(
                not isinstance(name, str)
                or not name
                or result not in {True, False, None}
                for name, result in gates.items()
            ):
                raise ValidationAuthorityError(f"{label} requires named boolean or unknown gates")


@dataclass(frozen=True, slots=True)
class ClosureDecision:
    verdict: str
    reason_codes: tuple[str, ...]


def normalize_public_verdict(value: str) -> str:
    """Map the legacy NOT_INTERPRETABLE report enum into the required public triad."""
    if value == "NOT_INTERPRETABLE":
        return "INSUFFICIENT_EVIDENCE"
    if value not in PUBLIC_VERDICTS:
        raise ValidationAuthorityError(f"unsupported closure verdict: {value}")
    return value


def decide_closure(
    *,
    evidence: ClosureEvidence,
    plan: FrozenAnalysisPlan | None,
    dependence: DependenceEstimate | None,
) -> ClosureDecision:
    """Apply immutable gates without inventing empirical thresholds or IID confidence."""
    reasons: list[str] = []
    integrity = evidence.integrity_status
    if integrity in {"FAILED", "INVALID"}:
        return ClosureDecision("FAIL", ("integrity_gate_failed",))
    if integrity not in {"VALID", "FULL_VERIFIED"}:
        reasons.append("integrity_gate_unevaluated")

    for name, result in evidence.operational_gates.items():
        if result is False:
            return ClosureDecision("FAIL", (f"operational_gate_failed:{name}",))
        if result is not True:
            reasons.append(f"operational_gate_unevaluated:{name}")
    for name, result in evidence.calibration_gates.items():
        if result is False:
            return ClosureDecision("FAIL", (f"calibration_gate_failed:{name}",))
        if result is not True:
            reasons.append(f"calibration_gate_unevaluated:{name}")
    if not evidence.operational_gates:
        reasons.append("operational_gates_not_declared")
    if not evidence.calibration_gates:
        reasons.append("calibration_gates_not_declared")

    if evidence.scheduled_opportunities_reconciled is not True:
        reasons.append("scheduled_opportunities_not_fully_reconciled")
    if evidence.required_outcomes_matured is not True:
        reasons.append("required_outcomes_not_matured")

    readiness = assess_dependence_readiness(plan, dependence)
    reasons.extend(readiness.reason_codes)
    if plan is None or plan.practical_minimum_effect is None:
        reasons.append("practical_effect_gate_unevaluated")
    if evidence.adverse_missingness_lower_bound is None:
        reasons.append("adverse_missingness_bound_unavailable")

    if reasons:
        return ClosureDecision(
            "INSUFFICIENT_EVIDENCE",
            tuple(dict.fromkeys(reasons)),
        )

    assert plan is not None
    assert plan.practical_minimum_effect is not None
    assert dependence is not None
    assert dependence.lower_confidence_bound is not None
    assert dependence.upper_confidence_bound is not None
    effect = exact_decimal(plan.practical_minimum_effect, "practical_minimum_effect")
    adverse_lower = exact_decimal(
        evidence.adverse_missingness_lower_bound, "adverse_missingness_lower_bound"
    )
    if dependence.upper_confidence_bound <= effect:
        return ClosureDecision("FAIL", ("primary_effect_upper_bound_not_above_policy",))
    if dependence.lower_confidence_bound <= effect:
        return ClosureDecision(
            "INSUFFICIENT_EVIDENCE",
            ("primary_confidence_bound_does_not_clear_policy",),
        )
    if adverse_lower <= effect:
        return ClosureDecision(
            "INSUFFICIENT_EVIDENCE",
            ("adverse_missingness_bound_does_not_clear_policy",),
        )
    return ClosureDecision("PASS", ())
