from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from qc2_contracts.runtime import canonical_content_hash
from qc2_validation_authority.metrics import METRIC_SPECIFICATIONS
from qc2_validation_authority import (
    ClosureDecision,
    OutcomeObservation,
    PredictionObservation,
    QualificationEvidence,
    ValidationAuthority,
    ValidationAuthorityError,
)

EPOCH_REF = {
    "target_schema_name": "qc2.validation.ValidationEpoch.v1",
    "target_id": "018f0000-0000-7000-8000-000000000001",
    "content_hash": "a" * 64,
}
DATASET_REF = {
    "target_schema_name": "qc2.outcomes_research.DatasetManifest.v1",
    "target_id": "018f0000-0000-7000-8000-000000000700",
    "content_hash": "d" * 64,
}


class IdFactory:
    def __init__(self, start: int = 0x1000) -> None:
        self.value = start

    def __call__(self) -> str:
        value = f"018f0000-0000-7000-8000-{self.value:012x}"
        self.value += 1
        return value


def make_authority(
    session_ids: tuple[str, ...] = ("2026-10-05",),
    *,
    seal_attempts: bool = True,
) -> ValidationAuthority:
    authority = ValidationAuthority(epoch_ref=EPOCH_REF, id_factory=IdFactory())
    deadlines = {session: f"{session}T20:00:00Z" for session in session_ids}
    authority.schedule_sessions(
        session_ids=session_ids,
        deadlines=deadlines,
        created_at="2026-10-01T18:00:00Z",
    )
    if seal_attempts:
        for index, session in enumerate(session_ids):
            run_ref = {
                "target_schema_name": "qc2.models_prediction.PredictionRun.v1",
                "target_id": f"018f0000-0000-7000-8000-{0x900 + int(session[-2:]):012x}",
            }
            authority.record_attempt_state(
                session_id=session,
                new_state="STARTED",
                run_ref=run_ref,
            )
            authority.record_attempt_state(
                session_id=session,
                new_state="SEALED",
                run_ref=run_ref,
            )
    return authority


def prediction_seal_contract(session: str) -> dict[str, Any]:
    payload = {
        "schema_name": "qc2.models_prediction.PredictionSeal.v1",
        "schema_version": "1.0",
        "id": f"018f0000-0000-7000-8000-{0xa00 + int(session[-2:]):012x}",
        "created_at": f"{session}T19:30:00Z",
        "owning_authority": "prediction",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        "run_ref": {
            "target_schema_name": "qc2.models_prediction.PredictionRun.v1",
            "target_id": f"018f0000-0000-7000-8000-{0x900 + int(session[-2:]):012x}",
        },
        "session_id": session,
        "role": "OPERATING",
        "ordered_prediction_refs": [
            {
                "target_schema_name": "qc2.models_prediction.Prediction.v1",
                "target_id": f"018f0000-0000-7000-8000-{0xc00 + int(session[-2:]):012x}",
                "content_hash": "b" * 64,
            }
        ],
        "disposition_counts": ["SCORED:12", "UNSCORABLE:0"],
        "payload_inventory_hash": "b" * 64,
        "deadline": f"{session}T20:00:00Z",
        "sealed_at": f"{session}T19:30:00Z",
        "evidence_refs": [],
        "content_hash": "0" * 64,
    }
    payload["content_hash"] = canonical_content_hash("PredictionSeal", payload)
    return payload


def checkpoint_contract(session: str) -> dict[str, Any]:
    payload = {
        "schema_name": "qc2.integrity_build.Checkpoint.v1",
        "schema_version": "1.0",
        "id": f"018f0000-0000-7000-8000-{0xb00 + int(session[-2:]):012x}",
        "created_at": f"{session}T19:40:00Z",
        "owning_authority": "evidence",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        "stream_id": "validation-test-stream",
        "head_sequence": 1,
        "head_hash": "c" * 64,
        "event_count": 1,
        "artifact_root_hash": "d" * 64,
        "checkpoint_hash": "e" * 64,
        "content_hash": "0" * 64,
    }
    payload["content_hash"] = canonical_content_hash("Checkpoint", payload)
    return payload


def qualification_evidence(
    session: str = "2026-10-05",
    **overrides: Any,
) -> QualificationEvidence:
    values: dict[str, Any] = {
        "prediction_seal_contract": prediction_seal_contract(session),
        "prediction_integrity": "FULL_VERIFIED",
        "denominator_status": "VALID",
        "receipt_sealed_at": f"{session}T19:50:00Z",
        "comparator_available": True,
        "protocol_conformity": True,
        "checkpoint_contract": checkpoint_contract(session),
    }
    values.update(overrides)
    return QualificationEvidence(**values)


def qualify(
    authority: ValidationAuthority,
    session: str = "2026-10-05",
    **overrides: Any,
) -> Any:
    return authority.qualify_session(
        session_id=session,
        evidence=qualification_evidence(session, **overrides),
    )


def metric_slice(session: str) -> Mapping[str, Any]:
    instruments = tuple(f"instrument-{index:02d}" for index in range(12))
    operating = [
        PredictionObservation(instrument, index + 1, "e" * 64, "QUALIFICATION")
        for index, instrument in enumerate(instruments)
    ]
    ranks = [((index + 2) % len(instruments)) + 1 for index in range(len(instruments))]
    comparator = [
        PredictionObservation(instrument, ranks[index], "e" * 64, "QUALIFICATION")
        for index, instrument in enumerate(instruments)
    ]
    outcomes = [
        OutcomeObservation(
            instrument,
            index == 8,
            "f" * 64,
            "QUALIFICATION",
        )
        for index, instrument in enumerate(instruments)
    ]
    return {
        "session_id": session,
        "eligible_instrument_ids": instruments,
        "operating_rows": operating,
        "comparator_rows": comparator,
        "outcomes": outcomes,
    }


def access_receipt(
    authority: ValidationAuthority,
    *,
    requested_at: str = "2026-10-08T18:00:00Z",
    granted_at: str = "2026-10-08T18:05:00Z",
) -> dict[str, Any]:
    return authority.consume_holdout(
        dataset_ref=DATASET_REF,
        evaluator_identity="separate-validation-evaluator",
        access_scope="METRICS_ONLY",
        requested_at=requested_at,
        granted_at=granted_at,
        consumed_fields=(
            "eligible_instrument_ids",
            "sealed_rank",
            "matured_binary_event",
            "feed_snapshot_hash",
            "label_registry_hash",
            "session_id",
        ),
        released_metrics=tuple(spec.metric_key for spec in METRIC_SPECIFICATIONS),
    )


def test_prospective_schedule_is_frozen_and_missed_start_waits_for_deadline() -> None:
    authority = make_authority(seal_attempts=False)
    with pytest.raises(ValidationAuthorityError, match="already frozen"):
        authority.schedule_sessions(
            session_ids=("2026-10-05",),
            deadlines={"2026-10-05": "2026-10-05T20:01:00Z"},
            created_at="2026-10-01T18:00:00Z",
        )
    with pytest.raises(ValidationAuthorityError, match="before its deadline"):
        authority.reconcile_missed_start(
            session_id="2026-10-05",
            reason="scheduled_start_not_observed",
            observed_at="2026-10-05T19:59:59Z",
        )
    missed = authority.reconcile_missed_start(
        session_id="2026-10-05",
        reason="scheduled_start_not_observed",
        observed_at="2026-10-05T20:00:00Z",
    )
    assert missed["attempt_state"] == "MISSED_START"
    assert missed["missed_reason"] == "scheduled_start_not_observed"


def test_qualification_is_sealed_without_outcome_or_broker_inputs() -> None:
    authority = make_authority()
    receipt = qualify(authority)
    original_hash = receipt.contract["content_hash"]
    assert receipt.state == "QUALIFYING"
    assert "profit" not in receipt.contract
    assert "broker" not in receipt.contract
    assert "outcome" not in receipt.contract

    authority.record_later_integrity_finding(
        session_id="2026-10-05",
        severity="WARNING",
        reason_code="late_integrity_observation",
        found_at="2026-10-09T18:00:00Z",
    )
    assert authority.qualification_receipts[0].contract["content_hash"] == original_hash


def test_unverified_evidence_is_indeterminate_and_failed_gates_are_nonqualifying() -> None:
    first = make_authority()
    partial = qualify(first, prediction_integrity="PARTIAL_SCAN")
    assert partial.state == "INDETERMINATE"

    second = make_authority()
    no_comparator = qualify(second, comparator_available=False)
    assert no_comparator.state == "NONQUALIFYING"
    assert "required_comparator_unavailable" in no_comparator.reason_codes


def test_qualification_requires_sealed_predictions_and_is_one_per_session() -> None:
    authority = make_authority(seal_attempts=False)
    with pytest.raises(ValidationAuthorityError, match="sealed prediction run"):
        qualify(authority)

    sealed = make_authority()
    qualify(sealed)
    with pytest.raises(ValidationAuthorityError, match="immutable"):
        qualify(sealed)


def test_qualification_authenticates_source_contracts_and_uses_their_timestamps() -> None:
    authority = make_authority()
    evidence = qualification_evidence()
    tampered_seal = dict(evidence.prediction_seal_contract)
    tampered_seal["sealed_at"] = "2026-10-05T19:31:00Z"
    with pytest.raises(ValidationAuthorityError, match="content_hash"):
        authority.qualify_session(
            session_id="2026-10-05",
            evidence=replace(evidence, prediction_seal_contract=tampered_seal),
        )

    other_authority = make_authority()
    wrong_run_seal = dict(evidence.prediction_seal_contract)
    wrong_run_seal["run_ref"] = {
        "target_schema_name": "qc2.models_prediction.PredictionRun.v1",
        "target_id": "018f0000-0000-7000-8000-000000000999",
    }
    wrong_run_seal["content_hash"] = canonical_content_hash(
        "PredictionSeal", wrong_run_seal
    )
    with pytest.raises(ValidationAuthorityError, match="scheduled prediction run"):
        other_authority.qualify_session(
            session_id="2026-10-05",
            evidence=replace(evidence, prediction_seal_contract=wrong_run_seal),
        )

    late_authority = make_authority()
    late_checkpoint = checkpoint_contract("2026-10-05")
    late_checkpoint["created_at"] = "2026-10-05T20:01:00Z"
    late_checkpoint["content_hash"] = canonical_content_hash(
        "Checkpoint", late_checkpoint
    )
    late_evidence = qualification_evidence(
        receipt_sealed_at="2026-10-05T20:02:00Z",
        checkpoint_contract=late_checkpoint,
    )
    assessment = late_authority.qualify_session(
        session_id="2026-10-05",
        evidence=late_evidence,
    )
    assert assessment.state == "NONQUALIFYING"
    assert "anchor_late" in assessment.reason_codes


def test_holdout_receipt_is_narrow_single_use_and_evaluation_is_aggregate_only() -> None:
    authority = make_authority()
    qualify(authority)
    receipt = access_receipt(authority)
    assert receipt["access_scope"] == "METRICS_ONLY"
    assert receipt["source_refs"] == [EPOCH_REF]
    with pytest.raises(ValidationAuthorityError, match="already been consumed"):
        access_receipt(authority)

    receipt_ref = {
        "target_schema_name": receipt["schema_name"],
        "target_id": receipt["id"],
        "content_hash": receipt["receipt_hash"],
    }
    bundles, results = authority.evaluate_dataset(
        holdout_receipt_ref=receipt_ref,
        expected_session_ids=("2026-10-05",),
        session_slices=(metric_slice("2026-10-05"),),
        computed_at="2026-10-09T18:00:00Z",
    )
    assert len(bundles) == 1
    assert len(results) == 8
    assert {result["definition_ref"]["target_id"] for result in results}
    with pytest.raises(ValidationAuthorityError, match="already been evaluated"):
        authority.evaluate_dataset(
            holdout_receipt_ref=receipt_ref,
            expected_session_ids=("2026-10-05",),
            session_slices=(metric_slice("2026-10-05"),),
            computed_at="2026-10-09T18:01:00Z",
        )


def test_holdout_access_waits_for_closed_schedule_and_prospective_receipts() -> None:
    premature_access = make_authority()
    qualify(premature_access)
    with pytest.raises(ValidationAuthorityError, match="latest scheduled opportunity deadline"):
        access_receipt(
            premature_access,
            requested_at="2026-10-05T19:00:00Z",
            granted_at="2026-10-05T19:30:00Z",
        )

    open_schedule = make_authority(seal_attempts=False)
    with pytest.raises(ValidationAuthorityError, match="terminal"):
        access_receipt(open_schedule)

    sealed_without_qualification = make_authority()
    with pytest.raises(ValidationAuthorityError, match="qualification receipt"):
        access_receipt(sealed_without_qualification)


def test_holdout_cannot_omit_any_qualifying_session() -> None:
    authority = make_authority(("2026-10-05", "2026-10-06"))
    qualify(authority, "2026-10-05")
    qualify(authority, "2026-10-06")
    receipt = access_receipt(authority)
    receipt_ref = {
        "target_schema_name": receipt["schema_name"],
        "target_id": receipt["id"],
        "content_hash": receipt["receipt_hash"],
    }
    with pytest.raises(ValidationAuthorityError, match="every qualifying session"):
        authority.evaluate_dataset(
            holdout_receipt_ref=receipt_ref,
            expected_session_ids=("2026-10-05",),
            session_slices=(metric_slice("2026-10-05"),),
            computed_at="2026-10-09T18:00:00Z",
        )


def test_report_maps_three_state_contract_and_later_critical_finding_fails_closure() -> None:
    authority = make_authority()
    receipt = qualify(authority)
    authority.record_later_integrity_finding(
        session_id="2026-10-05",
        severity="CRITICAL",
        reason_code="prediction_payload_tampered",
        found_at="2026-10-09T18:00:00Z",
    )
    report = authority.build_report(
        decision=ClosureDecision("NOT_INTERPRETABLE", ("calibration_gate_unevaluated",)),
        sealed_at="2026-10-09T18:05:00Z",
    )
    assert report["verdict"] == "FAIL"
    assert report["qualification_refs"][0]["content_hash"] == receipt.contract["content_hash"]
    assert "LATER_CRITICAL_INTEGRITY_FINDING" in report["limitation_codes"]
    assert authority.report == report


def test_analysis_plan_is_content_addressed_but_never_self_calibrates() -> None:
    authority = make_authority()
    primary = next(
        item
        for item in authority.metric_definitions
        if item["metric_key"] == "paired_precision_difference_at_10"
    )
    plan = {
        "schema_name": "qc2.validation.StatisticalAnalysisPlan.v1",
        "schema_version": "1.0",
        "id": "018f0000-0000-7000-8000-000000000800",
        "created_at": "2026-10-08T18:00:00+00:00",
        "owning_authority": "validation",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        "content_hash": "0" * 64,
        "epoch_ref": EPOCH_REF,
        "primary_metric_ref": {
            "target_schema_name": "qc2.validation.MetricDefinition.v1",
            "target_id": primary["id"],
        },
        "comparator_ref": {
            "target_schema_name": "qc2.scientific_definitions.BaselineManifest.v1",
            "target_id": "018f0000-0000-7000-8000-000000000801",
            "content_hash": "8" * 64,
        },
        "interval_method": "contiguous_block_bootstrap_v1",
        "alpha": "0.050000000000",
        "practical_minimum_effect": "0.100000000000",
        "minimum_event_clusters": 2,
        "minimum_effective_blocks": 4,
        "resample_count": 10_000,
        "missingness_method": "adverse_paired_bound_v1",
        "stopping_rule": "fixed_schedule_and_maturity_window_v1",
        "frozen_at": "2026-10-08T18:00:00+00:00",
    }
    frozen = authority.freeze_analysis_plan(plan)
    assert len(frozen["content_hash"]) == 64
    assert frozen["created_at"] == "2026-10-08T18:00:00Z"
    assert frozen["frozen_at"] == "2026-10-08T18:00:00Z"
    assert authority.analysis_plan_for_closure().calibration_status == "UNEVALUATED"

    unsupported = dict(plan)
    unsupported["interval_method"] = "normal_approximation"
    with pytest.raises(ValidationAuthorityError, match="registered dependence-aware"):
        make_authority().freeze_analysis_plan(unsupported)


def test_production_namespace_is_rejected() -> None:
    with pytest.raises(ValidationAuthorityError, match="cannot run in production"):
        ValidationAuthority(
            epoch_ref=EPOCH_REF,
            environment_namespace="production",
            id_factory=IdFactory(),
        )
