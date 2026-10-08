from __future__ import annotations

import hashlib
import uuid
from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from qc2_contracts.runtime import (
    canonical_content_hash,
    domain_separated_sha256,
)
from qc2_temporal_firewall.models import canonical_json_bytes

from qc2_apexlab import (
    ExperimentLedger,
    ExperimentLedgerError,
    HoldoutConsumptionState,
    ResourceUsage,
    TrialState,
)

RESOURCE_BUDGET_SCHEMA = "qc2.integrity_build.ResourceBudget.v1"
EXPERIMENT_SCHEMA = "qc2.outcomes_research.Experiment.v1"
DATASET_SCHEMA = "qc2.outcomes_research.DatasetManifest.v1"
SPLIT_SCHEMA = "qc2.outcomes_research.SplitManifest.v1"
MODEL_SCHEMA = "qc2.models_prediction.ModelManifest.v1"
CONFIG_SCHEMA = "qc2.integrity_build.ConfigurationManifest.v1"
ARTIFACT_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"
RECEIPT_SCHEMA = "qc2.outcomes_research.HoldoutAccessReceipt.v1"


def _uuid7(name: str) -> str:
    timestamp_ms = 1_793_424_000_000
    random_bytes = hashlib.sha256(name.encode("utf-8")).digest()
    rand_a = int.from_bytes(random_bytes[:2], "big") & 0x0FFF
    rand_b = int.from_bytes(random_bytes[2:8], "big") & ((1 << 62) - 1)
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return str(uuid.UUID(int=value))


def _ref(schema_name: str, identity: str, digest: str | None = None) -> dict[str, str]:
    result = {"target_schema_name": schema_name, "target_id": _uuid7(identity)}
    if digest is not None:
        result["content_hash"] = digest
    return result


def _seal(contract_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash(contract_name, payload)
    return payload


def _budget(
    *,
    budget_id: str = "ledger-budget",
    max_experiments: int = 2,
    max_concurrent_jobs: int = 1,
    authorized_cost_minor_units: int = 0,
    owner_approval_ref: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _seal(
        "ResourceBudget",
        {
            "schema_name": RESOURCE_BUDGET_SCHEMA,
            "schema_version": "1.0",
            "id": _uuid7(budget_id),
            "created_at": "2026-10-08T12:00:00Z",
            "owning_authority": "configuration",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [],
            "budget_key": f"{budget_id}-key",
            "configuration_domain": "RESEARCH",
            "version": 1,
            "max_experiments": max_experiments,
            "max_concurrent_jobs": max_concurrent_jobs,
            "max_elapsed_seconds": 120,
            "max_cpu_seconds": 120,
            "max_memory_bytes": 4096,
            "max_artifact_bytes": 2048,
            "authorized_cost_minor_units": authorized_cost_minor_units,
            "currency": "USD",
            "owner_approval_ref": owner_approval_ref,
            "effective_from": "2026-10-08",
            "fixture_only": True,
        },
    )


def _experiment(
    budget: dict[str, Any],
    *,
    experiment_id: str,
    candidate_id: str,
    dataset_ref: dict[str, str] | None = None,
    split_ref: dict[str, str] | None = None,
    created_at: str = "2026-10-08T12:01:00Z",
) -> dict[str, Any]:
    return _seal(
        "Experiment",
        {
            "schema_name": EXPERIMENT_SCHEMA,
            "schema_version": "1.0",
            "id": _uuid7(experiment_id),
            "created_at": created_at,
            "owning_authority": "apexlab",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [],
            "hypothesis": f"fixture hypothesis for {experiment_id}",
            "search_space_hash": "a" * 64,
            "code_hash": "b" * 64,
            "environment_fingerprint": "c" * 64,
            "dataset_ref": dataset_ref or _ref(DATASET_SCHEMA, "shared-dataset", "d" * 64),
            "split_ref": split_ref or _ref(SPLIT_SCHEMA, "shared-split", "e" * 64),
            "candidate_refs": [_ref(MODEL_SCHEMA, candidate_id, "f" * 64)],
            "algorithm": "fixture_model",
            "seed": 17,
            "configuration_ref": _ref(CONFIG_SCHEMA, "research-config", "1" * 64),
            "budget_ref": {
                "target_schema_name": RESOURCE_BUDGET_SCHEMA,
                "target_id": budget["id"],
                "content_hash": budget["content_hash"],
            },
            "compute_cost": "0",
            "evaluation_access": [],
            "result_ref": None,
            "rejection_reason": None,
            "artifact_refs": [],
        },
    )


def _artifact(identity: str) -> dict[str, str]:
    return _ref(ARTIFACT_SCHEMA, identity, "9" * 64)


def _registered_comparison(ledger: ExperimentLedger, *experiments: dict[str, Any]) -> None:
    ledger.register_comparison(
        [item["id"] for item in experiments],
        registered_at="2026-10-08T12:02:00Z",
    )


def _holdout_receipt(dataset_ref: dict[str, str]) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_name": RECEIPT_SCHEMA,
        "schema_version": "1.0",
        "id": _uuid7("holdout-receipt"),
        "created_at": "2026-10-08T12:05:00Z",
        "owning_authority": "validation",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [
            _ref("qc2.validation.ValidationEpoch.v1", "validation-epoch", "a" * 64)
        ],
        "dataset_ref": dataset_ref,
        "evaluator_identity": "validation-evaluator",
        "access_scope": "METRICS_ONLY",
        "requested_at": "2026-10-08T12:03:00Z",
        "granted_at": "2026-10-08T12:04:00Z",
        "consumed_fields": ["sealed_metric_bundle"],
        "released_metrics": ["qualification_summary"],
        "receipt_hash": "0" * 64,
    }
    body = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    receipt["receipt_hash"] = domain_separated_sha256(
        "qc2.validation.holdout-access.v1", canonical_json_bytes(body)
    )
    return receipt


def _setup_two_experiments() -> tuple[ExperimentLedger, dict[str, Any], dict[str, Any], dict[str, Any]]:
    ledger = ExperimentLedger()
    budget = _budget()
    first = _experiment(budget, experiment_id="rejected", candidate_id="candidate-a")
    second = _experiment(budget, experiment_id="interrupted", candidate_id="candidate-b")
    ledger.register_budget(budget)
    ledger.register_experiment(first)
    ledger.register_experiment(second)
    _registered_comparison(ledger, first, second)
    return ledger, budget, first, second


def test_rejected_and_interrupted_trials_are_retained_and_count_toward_budget() -> None:
    ledger, budget, first, second = _setup_two_experiments()

    ledger.reject_trial(
        first["id"],
        reason="candidate failed preregistered compatibility checks",
        reason_code="COMPATIBILITY_REJECTED",
        recorded_at="2026-10-08T12:03:00Z",
        usage=ResourceUsage(cpu_seconds=2, elapsed_seconds=3),
    )
    ledger.start_trial(second["id"], recorded_at="2026-10-08T12:03:01Z")
    checkpoint = _artifact("interruption-checkpoint")
    ledger.interrupt_trial(
        second["id"],
        reason="worker was interrupted",
        checkpoint_ref=checkpoint,
        recorded_at="2026-10-08T12:03:10Z",
        usage=ResourceUsage(
            elapsed_seconds=9,
            cpu_seconds=6,
            peak_memory_bytes=512,
            artifact_bytes=64,
        ),
    )

    third = _experiment(budget, experiment_id="over-budget", candidate_id="candidate-c")
    with pytest.raises(ExperimentLedgerError, match="experiment count budget is exhausted"):
        ledger.register_experiment(third)

    assert ledger.experiment_state(first["id"]) is TrialState.REJECTED
    assert ledger.experiment_state(second["id"]) is TrialState.INTERRUPTED
    assert [item.event_type for item in ledger.trial_events(first["id"])] == [
        "TRIAL_REJECTED"
    ]
    second_events = ledger.trial_events(second["id"])
    assert [item.event_type for item in second_events] == [
        "TRIAL_STARTED",
        "TRIAL_INTERRUPTED",
    ]
    assert second_events[-1].payload["checkpoint_ref"] == checkpoint
    assert ledger.verify_history(first["id"])
    assert ledger.verify_history(second["id"])
    with pytest.raises(FrozenInstanceError):
        second_events[-1].event_type = "TRIAL_COMPLETED"  # type: ignore[misc]

    report = ledger.budget_report(budget["id"])
    assert report.registered_experiments == 2
    assert report.counts()[TrialState.REJECTED.value] == 1
    assert report.counts()[TrialState.INTERRUPTED.value] == 1
    assert report.elapsed_seconds == 12
    assert report.cpu_seconds == 8
    assert report.peak_memory_bytes == 512
    assert report.artifact_bytes == 64
    assert report.spent_minor_units == 0
    assert report.currency == "USD"
    assert report.over_budget_experiments == ()


def test_interrupted_trial_resumes_from_its_preserved_checkpoint() -> None:
    ledger = ExperimentLedger()
    budget = _budget(max_experiments=1)
    experiment = _experiment(budget, experiment_id="resumable", candidate_id="candidate")
    ledger.register_budget(budget)
    ledger.register_experiment(experiment)
    ledger.start_trial(experiment["id"], recorded_at="2026-10-08T12:03:00Z")
    interrupted = ledger.interrupt_trial(
        experiment["id"],
        reason="worker was interrupted",
        checkpoint_ref=_artifact("resume-checkpoint"),
        recorded_at="2026-10-08T12:03:10Z",
        usage=ResourceUsage(elapsed_seconds=10, cpu_seconds=7),
    )

    resumed = ledger.start_trial(
        experiment["id"],
        recorded_at="2026-10-08T12:04:00Z",
    )

    assert resumed.event_type == "TRIAL_RESUMED"
    assert resumed.attempt_number == 2
    assert resumed.payload["checkpoint_ref"] == interrupted.payload["checkpoint_ref"]
    assert resumed.payload["resume_from_event_id"] == interrupted.event_id
    assert ledger.experiment_state(experiment["id"]) is TrialState.RUNNING
    assert ledger.verify_history(experiment["id"])


def test_resource_overrun_is_retained_and_reported_instead_of_erased() -> None:
    ledger = ExperimentLedger()
    budget = _budget(max_experiments=1, authorized_cost_minor_units=0)
    experiment = _experiment(budget, experiment_id="cost-overrun", candidate_id="candidate")
    ledger.register_budget(budget)
    ledger.register_experiment(experiment)
    ledger.start_trial(experiment["id"], recorded_at="2026-10-08T12:03:00Z")
    failed = ledger.fail_trial(
        experiment["id"],
        reason="worker exceeded the zero-cost fixture ceiling",
        reason_code="RESOURCE_BUDGET_EXCEEDED",
        recorded_at="2026-10-08T12:03:10Z",
        usage=ResourceUsage(cost_minor_units=1),
    )

    assert failed.payload["budget_overruns"] == ["AUTHORIZED_COST_MINOR_UNITS"]
    report = ledger.resource_report(experiment["id"])
    assert report.spent_minor_units == 1
    assert report.remaining_cost_minor_units == 0
    assert report.over_budget_experiments == (experiment["id"],)


def test_repeated_holdout_access_changes_derived_consumption_state() -> None:
    ledger, _, first, second = _setup_two_experiments()
    dataset_ref = first["dataset_ref"]
    receipt = _holdout_receipt(dataset_ref)

    assert (
        ledger.holdout_consumption_state(dataset_ref)
        is HoldoutConsumptionState.NOT_CONSUMED
    )
    granted = ledger.record_holdout_access_attempt(
        first["id"],
        dataset_ref,
        requested_at="2026-10-08T12:03:00Z",
        receipt_contract=receipt,
    )
    assert granted.disposition == "GRANTED"
    assert (
        ledger.holdout_consumption_state(dataset_ref)
        is HoldoutConsumptionState.CONSUMED
    )

    repeated = ledger.record_holdout_access_attempt(
        second["id"],
        dataset_ref,
        requested_at="2026-10-08T12:06:00Z",
        denial_reason="a repeat attempt is logged but not released",
    )
    assert repeated.disposition == "REPEAT_BLOCKED"
    assert repeated.receipt_id == receipt["id"]
    assert (
        ledger.holdout_consumption_state(dataset_ref)
        is HoldoutConsumptionState.REPEATED_ACCESS
    )
    attempts = ledger.holdout_access_attempts(dataset_ref)
    assert [item.sequence for item in attempts] == [1, 2]
    assert "released_metrics" not in attempts[0].payload
    assert "consumed_fields" not in attempts[0].payload


def test_paid_budget_waits_for_verifiable_owner_approval() -> None:
    ledger = ExperimentLedger()
    unauthorized = _budget(
        budget_id="unauthorized-paid-budget",
        authorized_cost_minor_units=100,
        owner_approval_ref=_ref(
            "qc2.governance_owner.OwnerCommandReceipt.v1",
            "unverified-approval-reference",
            "c" * 64,
        ),
    )

    with pytest.raises(
        ExperimentLedgerError, match="positive paid-cost budgets remain disabled"
    ):
        ledger.register_budget(unauthorized)


def test_holdout_receipt_cannot_release_row_level_data() -> None:
    ledger, _, first, _ = _setup_two_experiments()
    dataset_ref = first["dataset_ref"]
    receipt = _holdout_receipt(dataset_ref)
    receipt["access_scope"] = "ROW_LEVEL_APPROVED"
    body = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    receipt["receipt_hash"] = domain_separated_sha256(
        "qc2.validation.holdout-access.v1", canonical_json_bytes(body)
    )

    with pytest.raises(ExperimentLedgerError, match="cannot release holdout rows"):
        ledger.record_holdout_access_attempt(
            first["id"],
            dataset_ref,
            requested_at="2026-10-08T12:03:00Z",
            receipt_contract=receipt,
        )
