from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import FrozenInstanceError
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
for package in ("contracts", "temporal_firewall", "apexlab", "candidate_evaluator"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))

from qc2_candidate_evaluator import (  # noqa: E402
    FROZEN_POLICY,
    POLICY_HASH,
    CandidateEvaluator,
    CandidatePackage,
    EvaluationError,
    QualificationRow,
    QualificationSnapshot,
    QualificationVault,
    TrainingRow,
)
from qc2_candidate_evaluator.metrics import compute_metrics  # noqa: E402
from qc2_candidate_evaluator.models import thaw_json  # noqa: E402
from qc2_candidate_evaluator.inference import (  # noqa: E402
    SafeCandidateModel,
    infer_predictions,
)
from qc2_apexlab._model_worker import _scikit_state  # noqa: E402
from qc2_contracts.runtime import (  # noqa: E402
    artifact_inventory_hash,
    canonical_content_hash,
    canonical_json_bytes,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)


def _valid_contract(name: str) -> dict[str, Any]:
    rows = json.loads(
        (ROOT / "packages/contracts/fixtures/v1/valid.json").read_text(encoding="utf-8")
    )
    return copy.deepcopy(next(row["payload"] for row in rows if row["contract"] == name))


def _seal(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash(name, payload)
    validate_contract(name, payload)
    verify_content_hash(name, payload)
    return payload


def _ref(schema: str, payload: dict[str, Any]) -> dict[str, str]:
    return {
        "target_schema_name": schema,
        "target_id": payload["id"],
        "content_hash": payload["content_hash"],
    }


def _artifact_manifest(
    *,
    files: list[dict[str, Any]],
    dataset_ref: dict[str, str],
    split_ref: dict[str, str],
    budget_ref: dict[str, str],
) -> dict[str, Any]:
    payload = _valid_contract("ArtifactManifest")
    payload.update(
        {
            "id": new_uuidv7(),
            "created_at": "2026-10-07T00:00:00Z",
            "owning_authority": "model_registry",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [dataset_ref, split_ref, budget_ref],
            "manifest_version": 1,
            "files": files,
            "inventory_hash": artifact_inventory_hash(files),
            "detached_signature": None,
            "transport_hash": None,
        }
    )
    return _seal("ArtifactManifest", payload)


def _build_candidate(
    *,
    include_all_rows_in_training: bool = False,
    include_fabricated_metrics: bool = False,
) -> tuple[CandidatePackage, QualificationSnapshot]:
    dataset = _valid_contract("DatasetManifest")
    dataset["id"] = new_uuidv7()
    dataset["evidence_class"] = "SYNTHETIC_FIXTURE"
    dataset["environment_namespace"] = "test"
    dataset = _seal("DatasetManifest", dataset)
    dataset_ref = _ref("qc2.outcomes_research.DatasetManifest.v1", dataset)

    split = _valid_contract("SplitManifest")
    split.update(
        {
            "id": new_uuidv7(),
            "created_at": "2026-10-07T00:00:00Z",
            "evidence_class": dataset["evidence_class"],
            "environment_namespace": dataset["environment_namespace"],
            "dataset_ref": dataset_ref,
        }
    )
    split = _seal("SplitManifest", split)
    split_ref = _ref("qc2.outcomes_research.SplitManifest.v1", split)

    budget = _valid_contract("ResourceBudget")
    budget.update(
        {
            "id": new_uuidv7(),
            "created_at": "2026-10-07T00:00:00Z",
            "evidence_class": dataset["evidence_class"],
            "environment_namespace": dataset["environment_namespace"],
            "max_artifact_bytes": 10_000_000,
            "max_cpu_seconds": 120,
            "max_elapsed_seconds": 120,
            "max_memory_bytes": 1_000_000_000,
        }
    )
    budget = _seal("ResourceBudget", budget)
    budget_ref = _ref("qc2.integrity_build.ResourceBudget.v1", budget)

    environment = {
        "schema_name": "qc2.apexlab.TrainingEnvironment.v1",
        "schema_version": "1.0",
        "python_version": "3.13.11",
        "python_implementation": "CPython",
        "platform": "test-platform",
        "package_lock_hash": "b" * 64,
        "packages": {
            "scikit-learn": "1.9.1",
            "xgboost": "3.4.1",
            "numpy": "2.3.0",
            "scipy": "1.16.0",
        },
        "native_threads_per_job": 1,
        "worker_isolation": "allowlisted_environment_with_os_resource_limits",
    }
    environment_bytes = json.dumps(
        environment,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    environment_fingerprint = hashlib.sha256(canonical_json_bytes(environment)).hexdigest()

    model_id = new_uuidv7()
    train_keys = ["train-1", "train-2"]
    if include_all_rows_in_training:
        train_keys.append("qualification-1")
    validation_keys = ["validation-1"]
    model_artifact: dict[str, Any] = {
        "schema_name": "qc2.apexlab.SafeModelArtifact.v1",
        "schema_version": "1.0",
        "model_id": model_id,
        "family": "linear_regression",
        "task": "REGRESSION",
        "seed": 0,
        "parameters": {"alpha": 1.0},
        "feature_ids": ["fixture"],
        "estimator_state": {
            "kind": "linear_coefficients",
            "classes": [],
            "coefficient_matrix": [2.0],
            "intercept": 1.0,
            "n_features_in": 1,
        },
        "preprocessing_lineage": {
            "transform_hash": "c" * 64,
            "fit_row_keys": train_keys,
            "fit_cutoff": "2026-10-06T20:00:00Z",
            "means": ["0"],
            "scales": ["1"],
            "feature_order": ["fixture"],
        },
        "calibration_lineage": {
            "state": "NOT_APPLIED",
            "reason_code": "CALIBRATION_OUTSIDE_MODEL_FACTORY_SCOPE",
            "calibration_ref": None,
        },
        "dataset_ref": dataset_ref,
        "split_ref": split_ref,
        "fold_id": "fixture-fold",
        "training_index_hash": "d" * 64,
        "training_row_keys": train_keys,
        "validation_row_keys": validation_keys,
        "environment_fingerprint": environment_fingerprint,
    }
    if include_fabricated_metrics:
        model_artifact["reported_test_metrics"] = {
            "rmse": "0",
            "accuracy": "1",
            "row_count": 999_999,
        }
    model_bytes = json.dumps(
        model_artifact,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    parameter_bytes = json.dumps(
        {
            "schema_name": "qc2.apexlab.FrozenHyperparameterSpace.v1",
            "schema_version": "1.0",
            "family": "linear_regression",
            "task": "REGRESSION",
            "seed": 0,
            "selected_index": 0,
            "parameter_space": [{"alpha": 1.0}],
            "search_policy": "FIXED_ORDER_NO_ADAPTIVE_SELECTION",
            "selection_authority": "EXTERNAL_RESEARCH_POLICY",
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    files = [
        {
            "relative_path": "model.json",
            "length_bytes": len(model_bytes),
            "media_type": "application/json",
            "schema_name": "qc2.apexlab.SafeModelArtifact.v1",
            "schema_version": "1.0",
            "sha256": hashlib.sha256(model_bytes).hexdigest(),
        },
        {
            "relative_path": "environment.json",
            "length_bytes": len(environment_bytes),
            "media_type": "application/json",
            "schema_name": "qc2.apexlab.TrainingEnvironment.v1",
            "schema_version": "1.0",
            "sha256": hashlib.sha256(environment_bytes).hexdigest(),
        },
    ]
    artifact_manifest = _artifact_manifest(
        files=files,
        dataset_ref=dataset_ref,
        split_ref=split_ref,
        budget_ref=budget_ref,
    )
    parameter_manifest = _artifact_manifest(
        files=[
            {
                "relative_path": "hyperparameters.json",
                "length_bytes": len(parameter_bytes),
                "media_type": "application/json",
                "schema_name": "qc2.apexlab.FrozenHyperparameterSpace.v1",
                "schema_version": "1.0",
                "sha256": hashlib.sha256(parameter_bytes).hexdigest(),
            }
        ],
        dataset_ref=dataset_ref,
        split_ref=split_ref,
        budget_ref=budget_ref,
    )
    artifact_ref = _ref("qc2.integrity_build.ArtifactManifest.v1", artifact_manifest)
    parameter_ref = _ref("qc2.integrity_build.ArtifactManifest.v1", parameter_manifest)

    model = _valid_contract("ModelManifest")
    model.update(
        {
            "id": model_id,
            "created_at": "2026-10-07T00:00:00Z",
            "owning_authority": "model_registry",
            "evidence_class": dataset["evidence_class"],
            "environment_namespace": dataset["environment_namespace"],
            "source_refs": [
                dataset_ref,
                split_ref,
                budget_ref,
                artifact_ref,
                parameter_ref,
            ],
            "artifact_manifest_ref": artifact_ref,
            "safe_format": "json",
            "algorithm": "linear_regression",
            "algorithm_version": "scikit-learn==1.9.1",
            "ordered_feature_ids": ["fixture"],
            "training_start": "2026-10-05",
            "training_cutoff": "2026-10-06T20:00:00Z",
            "validation_window": json.dumps(
                {"fold_id": "fixture-fold", "released_row_keys": validation_keys},
                separators=(",", ":"),
                sort_keys=True,
            ),
            "qualification_window": json.dumps(
                {"sessions": ["2026-10-07"], "labels_released": False},
                separators=(",", ":"),
                sort_keys=True,
            ),
            "dataset_ref": dataset_ref,
            "split_ref": split_ref,
            "seed": 0,
            "hyperparameter_refs": [parameter_ref],
            "calibration_ref": None,
            "package_lock_hash": environment["package_lock_hash"],
            "environment_fingerprint": environment_fingerprint,
            "learned_dependency_refs": [dataset_ref],
            "resource_constraints": [
                f"max_artifact_bytes={budget['max_artifact_bytes']}",
                f"max_cpu_seconds={budget['max_cpu_seconds']}",
                f"max_elapsed_seconds={budget['max_elapsed_seconds']}",
                f"max_memory_bytes={budget['max_memory_bytes']}",
                "native_threads_per_job=1",
                "worker_environment=allowlisted",
            ],
            "lifecycle_state": "RESEARCH",
        }
    )
    model = _seal("ModelManifest", model)
    package = CandidatePackage(
        model_manifest=model,
        artifact_manifest=artifact_manifest,
        dataset_manifest=dataset,
        split_manifest=split,
        resource_budget=budget,
        artifact_files={
            "model.json": model_bytes,
            "environment.json": environment_bytes,
        },
        hyperparameter_manifest=parameter_manifest,
        hyperparameter_bytes=parameter_bytes,
    )

    train_rows = (
        TrainingRow("train-1", {"fixture": "1"}, "3"),
        TrainingRow("train-2", {"fixture": "2"}, "5"),
    )
    validation_rows = (TrainingRow("validation-1", {"fixture": "1.5"}, "4"),)
    qualification_rows = (
        QualificationRow(
            "qualification-1",
            "QUALIFICATION",
            {"fixture": "1"},
            "3",
            "2026-10-07T00:00:00Z",
        ),
        QualificationRow(
            "qualification-2",
            "QUALIFICATION",
            {"fixture": "2"},
            "4",
            "2026-10-07T00:00:00Z",
        ),
        QualificationRow(
            "qualification-3",
            "QUALIFICATION",
            {"fixture": "3"},
            "6",
            "2026-10-07T00:00:00Z",
        ),
    )
    snapshot = QualificationSnapshot(
        dataset_ref=dataset_ref,
        split_ref=split_ref,
        training_rows=train_rows,
        validation_rows=validation_rows,
        qualification_rows=qualification_rows,
        expected_qualification_row_keys=tuple(
            row.row_key for row in qualification_rows
        ),
        split_assignment_hash=dataset["split_assignment_hash"],
    )
    return package, snapshot


def _evaluator(
    candidate: CandidatePackage,
    snapshot: QualificationSnapshot,
) -> CandidateEvaluator:
    return CandidateEvaluator(
        QualificationVault((snapshot,)),
        approved_resource_budgets=(candidate.resource_budget,),
    )


def test_training_view_excludes_qualification_labels_and_policy_is_code_owned() -> None:
    candidate, snapshot = _build_candidate()
    vault = QualificationVault((snapshot,))

    trainer_view = vault.trainer_view(
        candidate.model_manifest["dataset_ref"],
        candidate.model_manifest["split_ref"],
        runtime_role="qc2_runtime_apexlab",
    )
    assert {row.row_key for row in trainer_view.training_rows} == {"train-1", "train-2"}
    assert {row.row_key for row in trainer_view.validation_rows} == {"validation-1"}
    assert not hasattr(trainer_view, "qualification_rows")
    assert all(
        row.row_key not in {item.row_key for item in snapshot.qualification_rows}
        for row in (*trainer_view.training_rows, *trainer_view.validation_rows)
    )
    with pytest.raises(EvaluationError, match="ApexLab runtime role"):
        vault.trainer_view(
            candidate.model_manifest["dataset_ref"],
            candidate.model_manifest["split_ref"],
            runtime_role="qc2_runtime_model_registry",
        )
    evaluator = _evaluator(candidate, snapshot)
    with pytest.raises(EvaluationError, match="model-registry runtime role"):
        evaluator.nominate(
            candidate,
            nominated_by="qc2_runtime_apexlab",
            nominated_at="2026-10-07T01:00:00Z",
        )
    with pytest.raises(TypeError):
        CandidateEvaluator(
            vault,
            approved_resource_budgets=(candidate.resource_budget,),
            policy={"decimal_places": 0},  # type: ignore[call-arg]
        )
    with pytest.raises(FrozenInstanceError):
        FROZEN_POLICY.decimal_places = 0  # type: ignore[misc]
    assert POLICY_HASH == hashlib.sha256(
        canonical_json_bytes(
            {
                "version": FROZEN_POLICY.version,
                "decimal_places": FROZEN_POLICY.decimal_places,
                "calibration_bins": FROZEN_POLICY.calibration_bins,
                "regression_baseline": FROZEN_POLICY.regression_baseline,
                "classification_baseline": FROZEN_POLICY.classification_baseline,
                "calibration_threshold_policy": FROZEN_POLICY.calibration_threshold_policy,
                "performance_policy": FROZEN_POLICY.performance_policy,
            }
        )
    ).hexdigest()


def test_candidate_cannot_replace_the_independently_approved_resource_budget() -> None:
    candidate, snapshot = _build_candidate()
    evaluator = _evaluator(candidate, snapshot)
    forged_budget = thaw_json(candidate.resource_budget)
    forged_budget["max_elapsed_seconds"] = 10_000
    forged_budget = _seal("ResourceBudget", forged_budget)
    forged_candidate = CandidatePackage(
        model_manifest=candidate.model_manifest,
        artifact_manifest=candidate.artifact_manifest,
        dataset_manifest=candidate.dataset_manifest,
        split_manifest=candidate.split_manifest,
        resource_budget=forged_budget,
        artifact_files=candidate.artifact_files,
        hyperparameter_manifest=candidate.hyperparameter_manifest,
        hyperparameter_bytes=candidate.hyperparameter_bytes,
    )

    with pytest.raises(EvaluationError, match="approved catalog"):
        evaluator.nominate(
            forged_candidate,
            nominated_by="qc2_runtime_model_registry",
            nominated_at="2026-10-07T01:00:00Z",
        )
    assert evaluator.information_release_log == ()


def test_evaluator_recomputes_metrics_and_logs_one_use_information_release() -> None:
    candidate, snapshot = _build_candidate()
    evaluator = _evaluator(candidate, snapshot)
    nomination = evaluator.nominate(
        candidate,
        nominated_by="qc2_runtime_model_registry",
        nominated_at="2026-10-07T01:00:00Z",
    )
    result = evaluator.evaluate(nomination, evaluated_at="2026-10-08T00:00:00Z")

    with localcontext() as context:
        context.prec = 40
        expected_rmse = (Decimal(2) / Decimal(3)).sqrt()
        expected_mae = Decimal(2) / Decimal(3)
        expected_baseline_rmse = (Decimal(61) / Decimal(3)).sqrt()
        expected_skill = Decimal(1) - expected_rmse / expected_baseline_rmse
    quantum = Decimal("0.000000000001")
    assert result.report["metrics"] == {
        "observation_count": "3",
        "rmse": format(expected_rmse.quantize(quantum, rounding=ROUND_HALF_EVEN), "f"),
        "mae": format(expected_mae.quantize(quantum, rounding=ROUND_HALF_EVEN), "f"),
        "zero_baseline_rmse": format(
            expected_baseline_rmse.quantize(quantum, rounding=ROUND_HALF_EVEN), "f"
        ),
        "rmse_skill_vs_zero": format(
            expected_skill.quantize(quantum, rounding=ROUND_HALF_EVEN), "f"
        ),
    }
    assert result.candidate_evaluation["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert {gate["gate_id"]: gate["status"] for gate in result.candidate_evaluation["gate_results"]} == {
        "heldout_leakage": "PASS",
        "deterministic_inference": "PASS",
        "resource_budget": "PASS",
        "regression_performance": "PASS",
        "calibration": "WARN",
        "evidence_class": "UNKNOWN",
        "evaluator_policy": "PASS",
    }
    assert result.holdout_receipt["access_scope"] == "METRICS_ONLY"
    assert list(result.holdout_receipt["released_metrics"]) == sorted(result.report["metrics"])
    serialized_report = json.dumps(thaw_json(result.report), sort_keys=True)
    assert "qualification-1" not in serialized_report
    assert '"label"' not in serialized_report

    events = evaluator.information_release_log
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert [event.event_type for event in events] == [
        "CANDIDATE_NOMINATED",
        "HOLDOUT_ACCESS_GRANTED",
        "AGGREGATE_METRICS_RELEASED",
        "EVALUATION_RECEIPTS_ISSUED",
    ]
    for index, event in enumerate(events):
        assert event.prior_event_hash == (events[index - 1].event_hash if index else None)
    released = json.loads(events[2].payload_json)
    assert released["details"]["report_hash"] == result.report["report_hash"]
    assert released["details"]["holdout_receipt_hash"] == result.holdout_receipt["receipt_hash"]


def test_fabricated_metrics_and_all_row_training_are_rejected() -> None:
    fabricated, fabricated_snapshot = _build_candidate(include_fabricated_metrics=True)
    fabricated_evaluator = _evaluator(fabricated, fabricated_snapshot)
    with pytest.raises(EvaluationError, match="unknown fields"):
        fabricated_evaluator.nominate(
            fabricated,
            nominated_by="qc2_runtime_model_registry",
            nominated_at="2026-10-07T01:00:00Z",
        )
    assert fabricated_evaluator.information_release_log == ()

    all_rows, all_rows_snapshot = _build_candidate(include_all_rows_in_training=True)
    evaluator = _evaluator(all_rows, all_rows_snapshot)
    nomination = evaluator.nominate(
        all_rows,
        nominated_by="qc2_runtime_model_registry",
        nominated_at="2026-10-07T01:00:00Z",
    )
    with pytest.raises(EvaluationError, match="overlap the holdout"):
        evaluator.evaluate(nomination, evaluated_at="2026-10-08T00:00:00Z")
    events = evaluator.information_release_log
    assert events[-1].event_type == "EVALUATION_ABORTED_AFTER_HOLDOUT_ACCESS"
    assert "AGGREGATE_METRICS_RELEASED" not in [event.event_type for event in events]
    assert any(event.event_type == "HOLDOUT_ACCESS_GRANTED" for event in events)


def test_reused_holdout_nomination_is_blocked_and_logged() -> None:
    candidate, snapshot = _build_candidate()
    evaluator = _evaluator(candidate, snapshot)
    first = evaluator.nominate(
        candidate,
        nominated_by="qc2_runtime_model_registry",
        nominated_at="2026-10-07T01:00:00Z",
    )
    evaluator.evaluate(first, evaluated_at="2026-10-08T00:00:00Z")

    with pytest.raises(EvaluationError, match="only one candidate nomination"):
        evaluator.nominate(
            candidate,
            nominated_by="qc2_runtime_model_registry",
            nominated_at="2026-10-08T01:00:00Z",
        )
    assert evaluator.information_release_log[-1].event_type == "NOMINATION_REUSE_BLOCKED"


def test_independent_binary_calibration_metrics_match_fixture_calculation() -> None:
    labels = [Decimal(1), Decimal(0), Decimal(1), Decimal(0)]
    predictions = [Decimal("0.9"), Decimal("0.2"), Decimal("0.8"), Decimal("0.1")]
    metrics = compute_metrics("BINARY_CLASSIFICATION", labels, predictions)
    with localcontext() as context:
        context.prec = 40
        expected_log_loss = -(
            Decimal("0.9").ln()
            + Decimal("0.8").ln()
            + Decimal("0.8").ln()
            + Decimal("0.9").ln()
        ) / Decimal(4)
    quantum = Decimal("0.000000000001")
    assert metrics["brier"] == "0.025000000000"
    assert metrics["fixed_0_5_baseline_brier"] == "0.250000000000"
    assert metrics["expected_calibration_error_10_bin"] == "0.150000000000"
    assert metrics["log_loss"] == format(
        expected_log_loss.quantize(quantum, rounding=ROUND_HALF_EVEN),
        "f",
    )


def test_safe_interpreters_match_all_qc2_035_model_family_outputs() -> None:
    np = pytest.importorskip("numpy")
    sklearn_ensemble = pytest.importorskip("sklearn.ensemble")
    sklearn_linear = pytest.importorskip("sklearn.linear_model")
    threadpoolctl = pytest.importorskip("threadpoolctl")
    xgboost = pytest.importorskip("xgboost")

    x = np.asarray([[0.0], [1.0], [2.0], [3.0]], dtype="float64")
    regression_targets = np.asarray([0.0, 1.0, 2.0, 3.0], dtype="float64")
    classification_targets = np.asarray([0.0, 0.0, 1.0, 1.0], dtype="float64")
    rows = tuple(
        QualificationRow(
            row_key=f"family-row-{index}",
            split_role="QUALIFICATION",
            features={"feature": str(float(index))},
            label=str(float(label)),
            label_available_at="2026-10-07T00:00:00Z",
        )
        for index, label in enumerate(regression_targets)
    )
    cases = [
        (
            "linear_regression",
            "REGRESSION",
            sklearn_linear.Ridge(alpha=1.0, solver="lsqr"),
            regression_targets,
        ),
        (
            "logistic_regression",
            "BINARY_CLASSIFICATION",
            sklearn_linear.LogisticRegression(
                solver="liblinear",
                random_state=0,
            ),
            classification_targets,
        ),
        (
            "random_forest",
            "REGRESSION",
            sklearn_ensemble.RandomForestRegressor(
                n_estimators=2,
                max_depth=2,
                random_state=0,
                n_jobs=1,
                max_features=1.0,
            ),
            regression_targets,
        ),
        (
            "random_forest",
            "BINARY_CLASSIFICATION",
            sklearn_ensemble.RandomForestClassifier(
                n_estimators=2,
                max_depth=2,
                random_state=0,
                n_jobs=1,
                max_features=1.0,
            ),
            classification_targets,
        ),
        (
            "gradient_boosting",
            "REGRESSION",
            sklearn_ensemble.GradientBoostingRegressor(
                n_estimators=2,
                max_depth=1,
                random_state=0,
            ),
            regression_targets,
        ),
        (
            "gradient_boosting",
            "BINARY_CLASSIFICATION",
            sklearn_ensemble.GradientBoostingClassifier(
                n_estimators=2,
                max_depth=1,
                random_state=0,
            ),
            classification_targets,
        ),
        (
            "xgboost",
            "REGRESSION",
            xgboost.XGBRegressor(
                n_estimators=2,
                max_depth=1,
                n_jobs=1,
                tree_method="hist",
                objective="reg:squarederror",
                device="cpu",
            ),
            regression_targets,
        ),
        (
            "xgboost",
            "BINARY_CLASSIFICATION",
            xgboost.XGBClassifier(
                n_estimators=2,
                max_depth=1,
                n_jobs=1,
                tree_method="hist",
                objective="binary:logistic",
                device="cpu",
            ),
            classification_targets,
        ),
    ]
    with threadpoolctl.threadpool_limits(limits=1):
        for family, task, estimator, targets in cases:
            estimator.fit(x, targets)
            worker_state = _scikit_state(estimator, family, x.shape[1])
            safe_model = SafeCandidateModel(
                family=family,
                task=task,
                feature_ids=("feature",),
                means=(Decimal(0),),
                scales=(Decimal(1),),
                estimator_state=worker_state,
                training_row_keys=(),
                validation_row_keys=(),
                fit_row_keys=(),
            )
            actual = infer_predictions(safe_model, rows)
            reference = (
                estimator.predict(x)
                if task == "REGRESSION"
                else estimator.predict_proba(x)[:, 1]
            )
            assert len(actual) == len(reference)
            assert all(
                abs(value - Decimal(str(expected))) <= Decimal("0.000001")
                for value, expected in zip(actual, reference)
            ), family
