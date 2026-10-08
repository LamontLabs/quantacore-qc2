from __future__ import annotations

from decimal import Decimal

import pytest

from qc2_validation_authority import (
    ClosureEvidence,
    DependenceEstimate,
    FrozenAnalysisPlan,
    SplitRow,
    ValidationAuthorityError,
    assess_dependence_readiness,
    decide_closure,
    normalize_public_verdict,
    validate_temporal_split,
)

CALENDAR = (
    "2026-10-01",
    "2026-10-02",
    "2026-10-05",
    "2026-10-06",
    "2026-10-07",
)


def valid_split_rows() -> list[SplitRow]:
    return [
        SplitRow(
            "train-row",
            "2026-10-01",
            "TRAINING",
            "2026-10-02",
            "2026-10-02T20:00:00Z",
        ),
        SplitRow(
            "validation-row",
            "2026-10-05",
            "VALIDATION",
            "2026-10-06",
            "2026-10-06T20:00:00Z",
        ),
        SplitRow(
            "qualification-row",
            "2026-10-07",
            "QUALIFICATION",
            "2026-10-07",
            "2026-10-07T20:00:00Z",
        ),
    ]


def test_session_grouped_temporal_split_accepts_purged_outer_stages() -> None:
    result = validate_temporal_split(
        session_order=CALENDAR,
        rows=valid_split_rows(),
        training_sessions=("2026-10-01",),
        validation_sessions=("2026-10-05",),
        qualification_sessions=("2026-10-07",),
        purged_sessions=("2026-10-02",),
        embargo_sessions=("2026-10-06",),
        training_cutoff_at="2026-10-03T00:00:00Z",
        validation_cutoff_at="2026-10-07T00:00:00Z",
    )
    assert result.training_sessions == ("2026-10-01",)
    assert result.purged_sessions == ("2026-10-02",)
    assert result.embargo_sessions == ("2026-10-06",)


def test_train_validation_overlap_and_unmatured_labels_are_rejected() -> None:
    with pytest.raises(ValidationAuthorityError, match="overlap"):
        validate_temporal_split(
            session_order=CALENDAR,
            rows=valid_split_rows(),
            training_sessions=("2026-10-01", "2026-10-05"),
            validation_sessions=("2026-10-05",),
            qualification_sessions=("2026-10-07",),
            purged_sessions=("2026-10-02",),
            embargo_sessions=("2026-10-06",),
            training_cutoff_at="2026-10-03T00:00:00Z",
            validation_cutoff_at="2026-10-07T00:00:00Z",
        )

    rows = valid_split_rows()
    rows[0] = SplitRow(
        "train-row",
        "2026-10-01",
        "TRAINING",
        "2026-10-05",
        "2026-10-02T20:00:00Z",
    )
    with pytest.raises(ValidationAuthorityError, match="overlap the validation boundary"):
        validate_temporal_split(
            session_order=CALENDAR,
            rows=rows,
            training_sessions=("2026-10-01",),
            validation_sessions=("2026-10-05",),
            qualification_sessions=("2026-10-07",),
            purged_sessions=("2026-10-02",),
            embargo_sessions=("2026-10-06",),
            training_cutoff_at="2026-10-03T00:00:00Z",
            validation_cutoff_at="2026-10-07T00:00:00Z",
        )


def analysis_plan(
    *,
    calibration_status: str = "CALIBRATED_AND_FROZEN",
    interval_method: str = "contiguous_block_bootstrap_v1",
) -> FrozenAnalysisPlan:
    return FrozenAnalysisPlan(
        interval_method=interval_method,
        alpha=Decimal("0.05"),
        practical_minimum_effect=Decimal("0.1"),
        minimum_event_clusters=2,
        minimum_effective_blocks=4,
        resample_count=10_000,
        missingness_method="adverse_paired_bound_v1",
        stopping_rule="fixed_schedule_and_maturity_window_v1",
        calibration_status=calibration_status,
        frozen_at="2026-10-01T18:00:00Z",
    )


def estimate(
    lower: str = "0.12",
    upper: str = "0.18",
    *,
    method_id: str = "contiguous_block_bootstrap_v1",
    effective_blocks: int = 5,
    event_clusters: int = 2,
) -> DependenceEstimate:
    return DependenceEstimate(
        method_id=method_id,
        lower_confidence_bound=Decimal(lower),
        upper_confidence_bound=Decimal(upper),
        effective_blocks=effective_blocks,
        event_clusters=event_clusters,
        resample_count=10_000,
        coverage_gate_passed=True,
        deterministic_seed_hash="c" * 64,
    )


def closure_evidence(
    *,
    adverse_missingness_lower_bound: str = "0.11",
    operational_gates: dict[str, bool | None] | None = None,
    calibration_gates: dict[str, bool | None] | None = None,
) -> ClosureEvidence:
    return ClosureEvidence(
        integrity_status="FULL_VERIFIED",
        scheduled_opportunities_reconciled=True,
        required_outcomes_matured=True,
        adverse_missingness_lower_bound=Decimal(adverse_missingness_lower_bound),
        operational_gates=(
            {"schedule_reconciliation": True}
            if operational_gates is None
            else operational_gates
        ),
        calibration_gates=(
            {"simulated_coverage": True}
            if calibration_gates is None
            else calibration_gates
        ),
    )


def test_closure_uses_only_explicit_dependence_and_policy_boundaries() -> None:
    passing = decide_closure(
        evidence=closure_evidence(),
        plan=analysis_plan(),
        dependence=estimate(),
    )
    assert passing.verdict == "PASS"

    failing = decide_closure(
        evidence=closure_evidence(),
        plan=analysis_plan(),
        dependence=estimate("0.02", "0.08"),
    )
    assert failing.verdict == "FAIL"

    uncertain = decide_closure(
        evidence=closure_evidence(),
        plan=analysis_plan(),
        dependence=estimate("0.08", "0.13"),
    )
    assert uncertain.verdict == "INSUFFICIENT_EVIDENCE"


def test_iid_unevaluated_gates_and_inadequate_blocks_never_pass() -> None:
    iid = decide_closure(
        evidence=closure_evidence(),
        plan=analysis_plan(interval_method="iid_accuracy"),
        dependence=estimate(method_id="iid_accuracy"),
    )
    assert iid.verdict == "INSUFFICIENT_EVIDENCE"
    assert "iid_or_unspecified_interval_method_forbidden" in iid.reason_codes

    unregistered = assess_dependence_readiness(
        analysis_plan(interval_method="normal_approximation"),
        estimate(method_id="normal_approximation"),
    )
    assert not unregistered.ready
    assert "dependence_method_unregistered" in unregistered.reason_codes

    uncalibrated_plan = analysis_plan(calibration_status="UNEVALUATED")
    readiness = assess_dependence_readiness(uncalibrated_plan, estimate())
    assert not readiness.ready
    assert "calibration_gates_unevaluated" in readiness.reason_codes

    inadequate = decide_closure(
        evidence=closure_evidence(),
        plan=analysis_plan(),
        dependence=estimate(effective_blocks=3),
    )
    assert inadequate.verdict == "INSUFFICIENT_EVIDENCE"
    assert "effective_time_block_gate_not_met" in inadequate.reason_codes

    undeclared_gates = decide_closure(
        evidence=closure_evidence(operational_gates={}, calibration_gates={}),
        plan=analysis_plan(),
        dependence=estimate(),
    )
    assert undeclared_gates.verdict == "INSUFFICIENT_EVIDENCE"
    assert "operational_gates_not_declared" in undeclared_gates.reason_codes
    assert "calibration_gates_not_declared" in undeclared_gates.reason_codes


def test_missingness_bound_must_clear_policy_for_pass() -> None:
    result = decide_closure(
        evidence=closure_evidence(adverse_missingness_lower_bound="0.09"),
        plan=analysis_plan(),
        dependence=estimate(),
    )
    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert "adverse_missingness_bound_does_not_clear_policy" in result.reason_codes


def test_public_report_state_maps_legacy_enum_to_insufficient() -> None:
    assert normalize_public_verdict("NOT_INTERPRETABLE") == "INSUFFICIENT_EVIDENCE"
    with pytest.raises(ValidationAuthorityError, match="unsupported closure verdict"):
        normalize_public_verdict("MAYBE")
