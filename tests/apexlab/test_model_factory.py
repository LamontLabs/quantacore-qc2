from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from qc2_contracts.runtime import (
    canonical_content_hash,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)
from qc2_apexlab.dataset_models import FoldFeatureTransform, FoldTrainingIndex, PreparedDatasetRow
from qc2_apexlab.dataset_builder import _hash as dataset_hash
from qc2_apexlab.model_factory import (
    FROZEN_PARAMETER_SPACES,
    ModelFamily,
    ModelTrainingRequest,
    PredictionTask,
    TrainingOutcomeState,
    load_safe_model_artifact,
    train_candidate,
)
import qc2_apexlab.model_factory as model_factory


FIXTURE_PATH = Path(__file__).parents[2] / "packages/contracts/fixtures/v1/valid.json"
FIXTURES = {
    item["contract"]: item["payload"]
    for item in json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
}
TRAIN_SESSIONS = ("2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08")
VALIDATION_SESSIONS = ("2026-10-09", "2026-10-12")
QUALIFICATION_SESSIONS = ("2026-10-13",)
TRAINING_CUTOFF = "2026-10-09T00:00:00Z"
VALIDATION_CUTOFF = "2026-10-13T00:00:00Z"


def _sealed(name: str, payload: dict) -> dict:
    payload["content_hash"] = canonical_content_hash(name, payload)
    validate_contract(name, payload)
    verify_content_hash(name, payload)
    return payload


def _typed_ref(schema_name: str) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": new_uuidv7(),
        "content_hash": hashlib.sha256(schema_name.encode("utf-8")).hexdigest(),
    }


def _governed_contracts() -> tuple[dict, dict, dict, dict]:
    dataset = copy.deepcopy(FIXTURES["DatasetManifest"])
    dataset.update(
        {
            "id": new_uuidv7(),
            "source_refs": [_typed_ref("qc2.scientific_definitions.LabelDefinition.v1")],
            "registry_refs": [
                copy.deepcopy(FIXTURES["DatasetManifest"]["registry_refs"][0]),
                _typed_ref("qc2.scientific_definitions.RunnerProtocolRegistry.v1"),
            ],
            "memory_cutoff": "2026-10-15T00:00:00Z",
            "time_start": TRAIN_SESSIONS[0],
            "time_end": QUALIFICATION_SESSIONS[0],
            "split_assignment_hash": hashlib.sha256(b"model-factory-fixture-split").hexdigest(),
        }
    )
    dataset = _sealed("DatasetManifest", dataset)
    protocol_ref = next(
        item
        for item in dataset["registry_refs"]
        if item["target_schema_name"]
        == "qc2.scientific_definitions.RunnerProtocolRegistry.v1"
    )

    training_rows = tuple(
        PreparedDatasetRow(
            row_key=f"train-{index}",
            session_id=session,
            instrument_id=f"instrument-{index}",
            feature_values=(Decimal(value),),
            target_value=Decimal(index % 2),
            sample_weight=Decimal("1"),
        )
        for index, (session, value) in enumerate(
            zip(TRAIN_SESSIONS, ("-1.5", "-0.5", "0.5", "1.5"), strict=True)
        )
    )
    validation_rows = tuple(
        PreparedDatasetRow(
            row_key=f"validation-{index}",
            session_id=session,
            instrument_id=f"instrument-validation-{index}",
            feature_values=(Decimal(value),),
            target_value=Decimal(index),
            sample_weight=None,
        )
        for index, (session, value) in enumerate(
            zip(VALIDATION_SESSIONS, ("2.5", "3.5"), strict=True)
        )
    )
    training_keys = [row.row_key for row in training_rows]
    validation_keys = [row.row_key for row in validation_rows]
    fold_id = "walk-forward-1"
    split = copy.deepcopy(FIXTURES["SplitManifest"])
    split.update(
        {
            "id": new_uuidv7(),
            "dataset_ref": {
                "target_schema_name": "qc2.outcomes_research.DatasetManifest.v1",
                "target_id": dataset["id"],
                "content_hash": dataset["content_hash"],
            },
            "source_refs": [
                *copy.deepcopy(dataset["source_refs"]),
                *copy.deepcopy(dataset["registry_refs"]),
            ],
            "training_intervals": [
                json.dumps(
                    {
                        "fold_id": fold_id,
                        "sessions": list(TRAIN_SESSIONS),
                        "released_row_keys": training_keys,
                        "cutoff_at": TRAINING_CUTOFF,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ],
            "validation_intervals": [
                json.dumps(
                    {
                        "fold_id": fold_id,
                        "sessions": list(VALIDATION_SESSIONS),
                        "released_row_keys": validation_keys,
                        "cutoff_at": VALIDATION_CUTOFF,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ],
            "qualification_interval": json.dumps(
                {
                    "sessions": list(QUALIFICATION_SESSIONS),
                    "cutoff_at": "2026-10-15T00:00:00Z",
                    "labels_released": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            "split_hash": dataset["split_assignment_hash"],
        }
    )
    split = _sealed("SplitManifest", split)

    budget = copy.deepcopy(FIXTURES["ResourceBudget"])
    budget.update(
        {
            "id": new_uuidv7(),
            "max_experiments": 16,
            "max_concurrent_jobs": 1,
            "max_elapsed_seconds": 120,
            "max_cpu_seconds": 120,
            "max_memory_bytes": 2 * 1024 * 1024 * 1024,
            "max_artifact_bytes": 16 * 1024 * 1024,
            "authorized_cost_minor_units": 0,
            "effective_from": "2026-10-05",
        }
    )
    budget = _sealed("ResourceBudget", budget)
    return dataset, split, budget, protocol_ref


def _training_rows():
    return (
        tuple(
            PreparedDatasetRow(
                row_key=f"train-{index}",
                session_id=session,
                instrument_id=f"instrument-{index}",
                feature_values=(Decimal(value),),
                target_value=Decimal(index % 2),
                sample_weight=Decimal("1"),
            )
            for index, (session, value) in enumerate(
                zip(TRAIN_SESSIONS, ("-1.5", "-0.5", "0.5", "1.5"), strict=True)
            )
        ),
        tuple(
            PreparedDatasetRow(
                row_key=f"validation-{index}",
                session_id=session,
                instrument_id=f"instrument-validation-{index}",
                feature_values=(Decimal(value),),
                target_value=Decimal(index),
                sample_weight=None,
            )
            for index, (session, value) in enumerate(
                zip(VALIDATION_SESSIONS, ("2.5", "3.5"), strict=True)
            )
        ),
    )


def _request(
    contracts: tuple[dict, dict, dict, dict],
    family: ModelFamily,
    task: PredictionTask,
    *,
    parameter_index: int = 0,
) -> ModelTrainingRequest:
    dataset, split, budget, protocol_ref = contracts
    training_rows, validation_rows = _training_rows()
    fold_id = "walk-forward-1"
    keys = tuple(row.row_key for row in training_rows)
    transform_fields = {
        "fold_id": fold_id,
        "cutoff_at": TRAINING_CUTOFF,
        "feature_ids": ("fixture",),
        "means": (Decimal("0"),),
        "scales": (Decimal("1"),),
        "fit_row_keys": keys,
    }
    transform_hash = dataset_hash(transform_fields)
    training_index = FoldTrainingIndex(
        fold_id=fold_id,
        cutoff_at=TRAINING_CUTOFF,
        member_row_keys=keys,
        rows=training_rows,
        index_hash=dataset_hash(
            {
                "fold_id": fold_id,
                "cutoff_at": TRAINING_CUTOFF,
                "transform_hash": transform_hash,
                "rows": training_rows,
            }
        ),
    )
    transform = FoldFeatureTransform(
        fold_id=fold_id,
        cutoff_at=TRAINING_CUTOFF,
        feature_ids=("fixture",),
        means=(Decimal("0"),),
        scales=(Decimal("1"),),
        fit_row_keys=keys,
        transform_hash=transform_hash,
    )
    return ModelTrainingRequest(
        family=family,
        task=task,
        parameter_index=parameter_index,
        dataset_manifest=dataset,
        split_manifest=split,
        fold_id=fold_id,
        training_index=training_index,
        transform=transform,
        validation_rows=validation_rows,
        protocol_registry_ref=protocol_ref,
        resource_budget=budget,
    )


def test_frozen_parameter_spaces_are_immutable():
    assert isinstance(FROZEN_PARAMETER_SPACES, MappingProxyType)
    assert isinstance(FROZEN_PARAMETER_SPACES[ModelFamily.XGBOOST][0], MappingProxyType)
    with pytest.raises(TypeError):
        FROZEN_PARAMETER_SPACES[ModelFamily.XGBOOST][0]["max_depth"] = 100


def test_fixture_competition_trains_all_families_on_identical_governed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    contracts = _governed_contracts()
    dataset, split, budget, _ = contracts
    export_directory = tmp_path / "exports"
    export_directory.mkdir()
    lock_file = Path(__file__).parents[2] / "uv.lock"
    seen_environments: list[dict[str, str]] = []
    original_worker_environment = model_factory._worker_environment
    credentials = {
        "APCA_API_KEY_ID": "test-only-credential-sentinel",
        "APCA_API_SECRET_KEY": "another-test-only-sentinel",
        "SESSION_SECRET": "session-sentinel",
        "DATABASE_URL": "database-sentinel",
        "BROKER_TOKEN": "broker-sentinel",
    }
    for name, value in credentials.items():
        monkeypatch.setenv(name, value)

    def capture_worker_environment(home: Path) -> dict[str, str]:
        environment = original_worker_environment(home)
        seen_environments.append(environment)
        return environment

    monkeypatch.setattr(model_factory, "_worker_environment", capture_worker_environment)
    cases = (
        (ModelFamily.LINEAR_REGRESSION, PredictionTask.REGRESSION),
        (ModelFamily.LOGISTIC_REGRESSION, PredictionTask.BINARY_CLASSIFICATION),
        (ModelFamily.RANDOM_FOREST, PredictionTask.REGRESSION),
        (ModelFamily.RANDOM_FOREST, PredictionTask.BINARY_CLASSIFICATION),
        (ModelFamily.GRADIENT_BOOSTING, PredictionTask.REGRESSION),
        (ModelFamily.GRADIENT_BOOSTING, PredictionTask.BINARY_CLASSIFICATION),
        (ModelFamily.XGBOOST, PredictionTask.REGRESSION),
        (ModelFamily.XGBOOST, PredictionTask.BINARY_CLASSIFICATION),
    )
    candidates = []
    for family, task in cases:
        request = _request(contracts, family, task)
        assert request.dataset_manifest["content_hash"] == dataset["content_hash"]
        assert request.split_manifest["content_hash"] == split["content_hash"]
        assert request.resource_budget["content_hash"] == budget["content_hash"]
        assert "qualification_rows" not in {
            field.name for field in fields(request)
        }
        outcome = train_candidate(
            request,
            export_directory=export_directory,
            lock_file=lock_file,
        )
        assert outcome.state is TrainingOutcomeState.CANDIDATE_CREATED, (
            family.value,
            task.value,
            outcome.reason_code,
            outcome.reason,
        )
        candidate = outcome.candidate
        assert candidate is not None
        validate_contract("ModelManifest", dict(candidate.model_manifest))
        verify_content_hash("ModelManifest", dict(candidate.model_manifest))
        validate_contract("ArtifactManifest", dict(candidate.artifact_manifest))
        verify_content_hash("ArtifactManifest", dict(candidate.artifact_manifest))
        validate_contract("ArtifactManifest", dict(candidate.hyperparameter_manifest))
        verify_content_hash("ArtifactManifest", dict(candidate.hyperparameter_manifest))
        assert candidate.model_manifest["lifecycle_state"] == "RESEARCH"
        assert candidate.model_manifest["calibration_ref"] is None
        assert candidate.model_manifest["seed"] == 20261008
        assert candidate.model_manifest["dataset_ref"]["content_hash"] == dataset["content_hash"]
        assert candidate.model_manifest["split_ref"]["content_hash"] == split["content_hash"]
        assert candidate.validation_metric_name in {"rmse", "brier"}
        assert len(candidate.validation_predictions) == 2
        assert candidate.resource_usage.cost_minor_units == 0
        assert candidate.resource_usage.artifact_bytes <= budget["max_artifact_bytes"]
        artifact = load_safe_model_artifact(candidate.artifact_path)
        assert artifact["calibration_lineage"]["state"] == "NOT_APPLIED"
        assert artifact["seed"] == 20261008
        assert sorted(path.name for path in candidate.artifact_path.iterdir()) == [
            "environment.json",
            "hyperparameters.json",
            "model.json",
        ]
        assert all((path.stat().st_mode & 0o777) == 0o600 for path in candidate.artifact_path.iterdir())
        candidates.append(candidate)

    assert len(candidates) == len(cases)
    assert len(seen_environments) == len(cases)
    assert all(
        set(environment)
        == {
            "PATH",
            "PYTHONPATH",
            "PYTHONNOUSERSITE",
            "PYTHONHASHSEED",
            "HOME",
            "LANG",
            "LC_ALL",
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        }
        for environment in seen_environments
    )
    assert all(
        not set(credentials).intersection(environment)
        for environment in seen_environments
    )
    assert all(
        not set(credentials.values()).intersection(environment.values())
        for environment in seen_environments
    )
    assert len({item.model_manifest["dataset_ref"]["content_hash"] for item in candidates}) == 1
    assert len({item.model_manifest["split_ref"]["content_hash"] for item in candidates}) == 1
    assert len({item.model_manifest["package_lock_hash"] for item in candidates}) == 1


def test_memory_budget_exhaustion_is_reason_coded_and_exports_nothing(tmp_path: Path):
    dataset, split, budget, protocol_ref = _governed_contracts()
    budget = copy.deepcopy(budget)
    budget["max_memory_bytes"] = 1024 * 1024
    budget = _sealed("ResourceBudget", budget)
    contracts = dataset, split, budget, protocol_ref
    export_directory = tmp_path / "exports"
    export_directory.mkdir()
    outcome = train_candidate(
        _request(contracts, ModelFamily.LINEAR_REGRESSION, PredictionTask.REGRESSION),
        export_directory=export_directory,
        lock_file=Path(__file__).parents[2] / "uv.lock",
    )
    assert outcome.state is TrainingOutcomeState.FAILED
    assert outcome.candidate is None
    assert outcome.reason_code == "MEMORY_BUDGET_EXHAUSTED"
    assert not list(export_directory.iterdir())


def test_interrupted_export_cleans_staging_directory_and_returns_no_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    contracts = _governed_contracts()
    export_directory = tmp_path / "exports"
    export_directory.mkdir()

    def interrupt_rename(_source: Path, _target: Path) -> None:
        raise OSError("injected interrupted export")

    monkeypatch.setattr(model_factory.os, "rename", interrupt_rename)
    outcome = train_candidate(
        _request(contracts, ModelFamily.LINEAR_REGRESSION, PredictionTask.REGRESSION),
        export_directory=export_directory,
        lock_file=Path(__file__).parents[2] / "uv.lock",
    )
    assert outcome.state is TrainingOutcomeState.FAILED
    assert outcome.candidate is None
    assert outcome.reason_code == "ARTIFACT_EXPORT_INTERRUPTED"
    assert not list(export_directory.iterdir())
    assert outcome.resource_usage.artifact_bytes > 0


def test_incompatible_family_is_never_silently_omitted(tmp_path: Path, monkeypatch):
    contracts = _governed_contracts()
    monkeypatch.setattr(
        model_factory,
        "_worker_environment",
        lambda _home: pytest.fail("incompatible requests must not start a trainer"),
    )
    export_directory = tmp_path / "exports"
    export_directory.mkdir()
    outcome = train_candidate(
        _request(
            contracts,
            ModelFamily.LOGISTIC_REGRESSION,
            PredictionTask.REGRESSION,
        ),
        export_directory=export_directory,
        lock_file=Path(__file__).parents[2] / "uv.lock",
    )
    assert outcome.state is TrainingOutcomeState.INCOMPATIBLE
    assert outcome.reason_code == "TASK_FAMILY_MISMATCH"
    assert outcome.candidate is None
    assert not list(export_directory.iterdir())


def test_strict_safe_json_parser_rejects_duplicate_keys(tmp_path: Path):
    artifact_path = tmp_path / "artifact"
    artifact_path.mkdir()
    (artifact_path / "model.json").write_text(
        '{"schema_name":"qc2.apexlab.SafeModelArtifact.v1",'
        '"schema_name":"qc2.apexlab.SafeModelArtifact.v1"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_safe_model_artifact(artifact_path)
