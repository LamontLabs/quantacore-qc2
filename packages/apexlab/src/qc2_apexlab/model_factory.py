"""Bounded, research-only model training with JSON-only artifact export."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import resource
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, fields as dataclass_fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import BoundedSemaphore, Lock
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import UUID

from qc2_contracts.runtime import (
    artifact_inventory_hash,
    canonical_content_hash,
    canonical_json_bytes,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

from .dataset_models import FoldFeatureTransform, FoldTrainingIndex, PreparedDatasetRow
from .experiment_models import ResourceUsage

_MODEL_SCHEMA = "qc2.models_prediction.ModelManifest.v1"
_ARTIFACT_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"
_DATASET_SCHEMA = "qc2.outcomes_research.DatasetManifest.v1"
_SPLIT_SCHEMA = "qc2.outcomes_research.SplitManifest.v1"
_BUDGET_SCHEMA = "qc2.integrity_build.ResourceBudget.v1"
_LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
_FEATURE_REGISTRY_SCHEMA = "qc2.scientific_definitions.FeatureRegistry.v1"
_PROTOCOL_REGISTRY_SCHEMA = "qc2.scientific_definitions.RunnerProtocolRegistry.v1"
_SAFE_ARTIFACT_SCHEMA = "qc2.apexlab.SafeModelArtifact.v1"
_HYPERPARAMETER_SCHEMA = "qc2.apexlab.FrozenHyperparameterSpace.v1"
_ENVIRONMENT_SCHEMA = "qc2.apexlab.TrainingEnvironment.v1"
_FIXED_SEED = 20261008
_MAX_TRAINING_ROWS = 50_000
_MAX_FEATURES = 512
_BASE_MEMORY_RESERVE = 256 * 1024 * 1024
_MIN_WALL_SECONDS = 2
_MIN_CPU_SECONDS = 1


class ModelFamily(str, Enum):
    LINEAR_REGRESSION = "linear_regression"
    LOGISTIC_REGRESSION = "logistic_regression"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    XGBOOST = "xgboost"


class PredictionTask(str, Enum):
    REGRESSION = "REGRESSION"
    BINARY_CLASSIFICATION = "BINARY_CLASSIFICATION"


class TrainingOutcomeState(str, Enum):
    CANDIDATE_CREATED = "CANDIDATE_CREATED"
    INCOMPATIBLE = "INCOMPATIBLE"
    FAILED = "FAILED"


def _freeze_grid(
    values: Mapping[ModelFamily, Sequence[Mapping[str, Any]]],
) -> Mapping[ModelFamily, tuple[Mapping[str, Any], ...]]:
    return MappingProxyType(
        {
        family: tuple(MappingProxyType(dict(parameters)) for parameters in choices)
        for family, choices in values.items()
        }
    )


FROZEN_PARAMETER_SPACES: Mapping[ModelFamily, tuple[Mapping[str, Any], ...]] = (
    _freeze_grid(
        {
            ModelFamily.LINEAR_REGRESSION: (
                {"alpha": 0.1},
                {"alpha": 1.0},
            ),
            ModelFamily.LOGISTIC_REGRESSION: (
                {"C": 0.5},
                {"C": 1.0},
            ),
            ModelFamily.RANDOM_FOREST: (
                {"max_depth": 3, "min_samples_leaf": 1, "n_estimators": 24},
                {"max_depth": 4, "min_samples_leaf": 2, "n_estimators": 32},
            ),
            ModelFamily.GRADIENT_BOOSTING: (
                {"learning_rate": 0.05, "max_depth": 2, "n_estimators": 24},
                {"learning_rate": 0.03, "max_depth": 3, "n_estimators": 32},
            ),
            ModelFamily.XGBOOST: (
                {
                    "learning_rate": 0.05,
                    "max_depth": 2,
                    "n_estimators": 24,
                    "reg_lambda": 1.0,
                },
                {
                    "learning_rate": 0.03,
                    "max_depth": 3,
                    "n_estimators": 32,
                    "reg_lambda": 2.0,
                },
            ),
        }
    )
)


class ModelFactoryError(ValueError):
    """A request violates a frozen model-factory or provenance contract."""


@dataclass(frozen=True, slots=True)
class ModelTrainingRequest:
    """The only row-bearing inputs are released train and development rows."""

    family: ModelFamily
    task: PredictionTask
    parameter_index: int
    dataset_manifest: Mapping[str, Any]
    split_manifest: Mapping[str, Any]
    fold_id: str
    training_index: FoldTrainingIndex
    transform: FoldFeatureTransform
    validation_rows: tuple[PreparedDatasetRow, ...]
    protocol_registry_ref: Mapping[str, Any]
    resource_budget: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TrainingCandidate:
    model_manifest: Mapping[str, Any]
    artifact_manifest: Mapping[str, Any]
    hyperparameter_manifest: Mapping[str, Any]
    artifact_path: Path
    validation_predictions: tuple[float, ...]
    validation_metric_name: str
    validation_metric_value: float
    resource_usage: ResourceUsage

    @property
    def model_ref(self) -> dict[str, str]:
        return {
            "target_schema_name": _MODEL_SCHEMA,
            "target_id": str(self.model_manifest["id"]),
            "content_hash": str(self.model_manifest["content_hash"]),
        }


@dataclass(frozen=True, slots=True)
class TrainingOutcome:
    state: TrainingOutcomeState
    candidate: TrainingCandidate | None
    reason_code: str | None
    reason: str | None
    resource_usage: ResourceUsage


@dataclass(frozen=True, slots=True)
class TrainingEnvironment:
    manifest: Mapping[str, Any]
    package_lock_hash: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _PreparedJob:
    dataset: dict[str, Any]
    split: dict[str, Any]
    budget: dict[str, Any]
    training_rows: tuple[PreparedDatasetRow, ...]
    validation_rows: tuple[PreparedDatasetRow, ...]
    training_interval: dict[str, Any]
    validation_interval: dict[str, Any]
    qualification_interval: dict[str, Any]
    target_label_refs: tuple[dict[str, str], ...]
    feature_registry_ref: dict[str, str]
    protocol_registry_ref: dict[str, str]
    parameters: dict[str, Any]


_SEMAPHORES: dict[tuple[str, int], BoundedSemaphore] = {}
_SEMAPHORES_LOCK = Lock()


def _plain(value: Any) -> Any:
    """Thaw immutable contract mappings/tuples before JSON Schema validation."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _plain(getattr(value, item.name))
            for item in dataclass_fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _dataset_hash(value: Any) -> str:
    return _sha256(canonical_json_bytes(_plain(value)))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _typed_ref(value: Mapping[str, Any], expected_schema: str, name: str) -> dict[str, str]:
    ref = _plain(value)
    if not isinstance(ref, dict) or set(ref) != {
        "target_schema_name",
        "target_id",
        "content_hash",
    }:
        raise ModelFactoryError(f"{name} must be a complete typed reference")
    if ref["target_schema_name"] != expected_schema:
        raise ModelFactoryError(f"{name} must reference {expected_schema}")
    try:
        if UUID(ref["target_id"]).version != 7:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ModelFactoryError(f"{name} must use a UUIDv7 target id") from exc
    digest = ref["content_hash"]
    if not isinstance(digest, str) or len(digest) != 64 or any(
        char not in "0123456789abcdef" for char in digest
    ):
        raise ModelFactoryError(f"{name} must include a lowercase SHA-256 content hash")
    return {key: str(ref[key]) for key in ref}


def _contract_ref(payload: Mapping[str, Any], schema_name: str) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": str(payload["id"]),
        "content_hash": str(payload["content_hash"]),
    }


def _parse_json_object(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            result = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ModelFactoryError(f"{field} is not valid JSON") from exc
    else:
        result = _plain(value)
    if not isinstance(result, dict):
        raise ModelFactoryError(f"{field} must be a JSON object")
    return result


def _parse_intervals(value: Any, field: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (tuple, list)) or not value:
        raise ModelFactoryError(f"{field} must contain at least one fold interval")
    return tuple(_parse_json_object(item, field) for item in value)


def _valid_numeric_rows(rows: Sequence[PreparedDatasetRow], width: int, name: str) -> None:
    if not rows:
        raise ModelFactoryError(f"{name} rows cannot be empty")
    for row in rows:
        if len(row.feature_values) != width:
            raise ModelFactoryError(f"{name} row {row.row_key} has the wrong feature width")
        for value in (*row.feature_values, row.target_value):
            try:
                decimal_value = Decimal(value)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ModelFactoryError(f"{name} rows must contain exact decimal values") from exc
            if not decimal_value.is_finite():
                raise ModelFactoryError(f"{name} rows must contain finite numeric values")
        if row.sample_weight is not None:
            weight = Decimal(row.sample_weight)
            if not weight.is_finite() or weight <= 0:
                raise ModelFactoryError(f"{name} sample weights must be finite and positive")


def _prepare_job(request: ModelTrainingRequest) -> _PreparedJob:
    try:
        dataset = _plain(request.dataset_manifest)
        split = _plain(request.split_manifest)
        budget = _plain(request.resource_budget)
        validate_contract("DatasetManifest", dataset)
        verify_content_hash("DatasetManifest", dataset)
        validate_contract("SplitManifest", split)
        verify_content_hash("SplitManifest", split)
        validate_contract("ResourceBudget", budget)
        verify_content_hash("ResourceBudget", budget)
    except (TypeError, ValueError, KeyError) as exc:
        raise ModelFactoryError(f"dataset, split, or budget contract is invalid: {exc}") from exc

    if budget["configuration_domain"] != "RESEARCH":
        raise ModelFactoryError("model factory accepts only RESEARCH resource budgets")
    if budget["environment_namespace"] not in {"test", "research"}:
        raise ModelFactoryError("model factory is restricted to test and research namespaces")
    if budget["authorized_cost_minor_units"] != 0:
        raise ModelFactoryError("model factory cannot spend or authorize paid resources")
    if split["dataset_ref"] != _contract_ref(dataset, _DATASET_SCHEMA):
        raise ModelFactoryError("split manifest is not bound to the selected dataset")
    if split["split_hash"] != dataset["split_assignment_hash"]:
        raise ModelFactoryError("dataset and split do not share the same assignment hash")

    if not isinstance(request.fold_id, str) or not request.fold_id:
        raise ModelFactoryError("fold_id is required")
    training_intervals = _parse_intervals(split["training_intervals"], "training_intervals")
    validation_intervals = _parse_intervals(
        split["validation_intervals"], "validation_intervals"
    )
    train_matches = [item for item in training_intervals if item.get("fold_id") == request.fold_id]
    validation_matches = [
        item for item in validation_intervals if item.get("fold_id") == request.fold_id
    ]
    if len(train_matches) != 1 or len(validation_matches) != 1:
        raise ModelFactoryError("selected fold must have one training and one validation interval")
    training_interval = train_matches[0]
    validation_interval = validation_matches[0]
    qualification_interval = _parse_json_object(
        split["qualification_interval"], "qualification_interval"
    )
    if qualification_interval.get("labels_released") is not False:
        raise ModelFactoryError("qualification labels must remain sealed during training")

    training_rows = tuple(request.training_index.rows)
    validation_rows = tuple(request.validation_rows)
    train_keys = tuple(row.row_key for row in training_rows)
    validation_keys = tuple(row.row_key for row in validation_rows)
    if len(set(train_keys)) != len(train_keys) or len(set(validation_keys)) != len(
        validation_keys
    ):
        raise ModelFactoryError("training and validation row keys must be unique")
    if set(train_keys) & set(validation_keys):
        raise ModelFactoryError("training and validation rows must not overlap")
    if tuple(request.training_index.member_row_keys) != train_keys:
        raise ModelFactoryError("training index member order differs from its rows")
    if set(training_interval.get("released_row_keys", ())) != set(train_keys):
        raise ModelFactoryError("training rows do not match the governed fold interval")
    if set(validation_interval.get("released_row_keys", ())) != set(validation_keys):
        raise ModelFactoryError("validation rows do not match the governed fold interval")
    if not {
        row.session_id for row in training_rows
    }.issubset(set(training_interval.get("sessions", ()))):
        raise ModelFactoryError("training row sessions differ from the governed fold interval")
    if not {
        row.session_id for row in validation_rows
    }.issubset(set(validation_interval.get("sessions", ()))):
        raise ModelFactoryError("validation row sessions differ from the governed fold interval")
    if request.training_index.fold_id != request.fold_id:
        raise ModelFactoryError("training index belongs to another fold")
    if request.transform.fold_id != request.fold_id:
        raise ModelFactoryError("preprocessing transform belongs to another fold")
    if request.training_index.cutoff_at != request.transform.cutoff_at:
        raise ModelFactoryError("training index and preprocessing cutoffs differ")
    if tuple(request.transform.fit_row_keys) != train_keys:
        raise ModelFactoryError("preprocessing must be fitted on these training rows only")
    feature_ids = tuple(request.transform.feature_ids)
    if not feature_ids or len(set(feature_ids)) != len(feature_ids):
        raise ModelFactoryError("ordered feature ids must be nonempty and unique")
    if (
        len(request.transform.means) != len(feature_ids)
        or len(request.transform.scales) != len(feature_ids)
    ):
        raise ModelFactoryError("preprocessing parameters do not match the feature order")
    if any(Decimal(scale) <= 0 for scale in request.transform.scales):
        raise ModelFactoryError("preprocessing scales must be positive")
    for digest, name in (
        (request.transform.transform_hash, "transform_hash"),
        (request.training_index.index_hash, "training_index_hash"),
    ):
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ModelFactoryError(f"{name} must be a lowercase SHA-256 digest")
    expected_transform_hash = _dataset_hash(
        {
            "fold_id": request.transform.fold_id,
            "cutoff_at": request.transform.cutoff_at,
            "feature_ids": request.transform.feature_ids,
            "means": request.transform.means,
            "scales": request.transform.scales,
            "fit_row_keys": request.transform.fit_row_keys,
        }
    )
    if request.transform.transform_hash != expected_transform_hash:
        raise ModelFactoryError("preprocessing transform hash does not match its parameters")
    expected_index_hash = _dataset_hash(
        {
            "fold_id": request.training_index.fold_id,
            "cutoff_at": request.training_index.cutoff_at,
            "transform_hash": request.transform.transform_hash,
            "rows": training_rows,
        }
    )
    if request.training_index.index_hash != expected_index_hash:
        raise ModelFactoryError("training index hash does not match its released rows")
    _valid_numeric_rows(training_rows, len(feature_ids), "training")
    _valid_numeric_rows(validation_rows, len(feature_ids), "validation")
    if (
        len(training_rows) > _MAX_TRAINING_ROWS
        or len(validation_rows) > _MAX_TRAINING_ROWS
        or len(feature_ids) > _MAX_FEATURES
    ):
        raise ModelFactoryError("dataset exceeds the frozen model-factory input bounds")

    target_refs = {
        (str(ref.get("target_id")), str(ref.get("content_hash"))): ref
        for ref in dataset["source_refs"]
        if isinstance(ref, Mapping) and ref.get("target_schema_name") == _LABEL_SCHEMA
    }
    if not target_refs:
        raise ModelFactoryError("dataset source refs do not identify the target label")
    target_label_refs = tuple(
        _typed_ref(ref, _LABEL_SCHEMA, "target_label_ref")
        for _, ref in sorted(target_refs.items())
    )
    feature_refs = [
        ref
        for ref in dataset["registry_refs"]
        if ref.get("target_schema_name") == _FEATURE_REGISTRY_SCHEMA
    ]
    if len(feature_refs) != 1:
        raise ModelFactoryError("dataset must bind exactly one feature registry")
    feature_registry_ref = _typed_ref(
        feature_refs[0], _FEATURE_REGISTRY_SCHEMA, "feature_registry_ref"
    )
    protocol_registry_ref = _typed_ref(
        request.protocol_registry_ref, _PROTOCOL_REGISTRY_SCHEMA, "protocol_registry_ref"
    )

    choices = FROZEN_PARAMETER_SPACES[request.family]
    if type(request.parameter_index) is not int or not 0 <= request.parameter_index < len(choices):
        raise ModelFactoryError("parameter_index is outside the frozen parameter space")
    parameters = _plain(choices[request.parameter_index])

    return _PreparedJob(
        dataset=dataset,
        split=split,
        budget=budget,
        training_rows=training_rows,
        validation_rows=validation_rows,
        training_interval=training_interval,
        validation_interval=validation_interval,
        qualification_interval=qualification_interval,
        target_label_refs=target_label_refs,
        feature_registry_ref=feature_registry_ref,
        protocol_registry_ref=protocol_registry_ref,
        parameters=parameters,
    )


def build_training_environment(lock_file: Path) -> TrainingEnvironment:
    """Bind candidate provenance to the exact project lock and installed libraries."""
    lock_bytes = Path(lock_file).read_bytes()
    lock_hash = _sha256(lock_bytes)
    package_names = ("scikit-learn", "xgboost", "numpy", "scipy")
    package_versions: dict[str, str] = {}
    for name in package_names:
        try:
            package_versions[name] = version(name)
        except PackageNotFoundError as exc:
            raise ModelFactoryError(f"required training dependency is unavailable: {name}") from exc
    manifest = {
        "schema_name": _ENVIRONMENT_SCHEMA,
        "schema_version": "1.0",
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "package_lock_hash": lock_hash,
        "packages": package_versions,
        "native_threads_per_job": 1,
        "worker_isolation": "allowlisted_environment_with_os_resource_limits",
    }
    fingerprint = _sha256(canonical_json_bytes(manifest))
    return TrainingEnvironment(
        manifest=manifest,
        package_lock_hash=lock_hash,
        fingerprint=fingerprint,
    )


def _worker_environment(home: Path) -> dict[str, str]:
    """Do not forward broker, database, owner, or other ambient credentials."""
    from importlib.util import find_spec

    site_paths: set[str] = set()
    for package in ("numpy", "scipy", "sklearn", "xgboost", "threadpoolctl"):
        spec = find_spec(package)
        if spec is None or spec.origin is None:
            raise ModelFactoryError(f"trusted training package is unavailable: {package}")
        origin = Path(spec.origin).resolve()
        site_root = next(
            (
                parent
                for parent in origin.parents
                if parent.name in {"site-packages", "dist-packages"}
            ),
            None,
        )
        if site_root is None or not site_root.is_dir():
            raise ModelFactoryError(
                f"trusted site-packages root cannot be resolved for {package}"
            )
        site_paths.add(str(site_root))
    ordered_site_paths = sorted(site_paths)
    if not ordered_site_paths:
        raise ModelFactoryError("no trusted installed package directory is available")
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "PYTHONPATH": os.pathsep.join(ordered_site_paths),
        "PYTHONNOUSERSITE": "1",
        "PYTHONHASHSEED": "0",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }


def _limits_preexec(cpu_seconds: int, memory_bytes: int):
    def apply_limits() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

    return apply_limits


def _resource_usage(payload: Mapping[str, Any]) -> ResourceUsage:
    usage = payload.get("resource_usage", {})
    return ResourceUsage(
        elapsed_seconds=max(0, int(usage.get("elapsed_seconds", 0))),
        cpu_seconds=max(0, int(usage.get("cpu_seconds", 0))),
        peak_memory_bytes=max(0, int(usage.get("peak_memory_bytes", 0))),
        artifact_bytes=max(0, int(usage.get("artifact_bytes", 0))),
        cost_minor_units=0,
    )


def _budget_failure(code: str, reason: str, usage: ResourceUsage = ResourceUsage()) -> TrainingOutcome:
    return TrainingOutcome(
        state=TrainingOutcomeState.FAILED,
        candidate=None,
        reason_code=code,
        reason=reason,
        resource_usage=usage,
    )


def _incompatible(code: str, reason: str) -> TrainingOutcome:
    return TrainingOutcome(
        state=TrainingOutcomeState.INCOMPATIBLE,
        candidate=None,
        reason_code=code,
        reason=reason,
        resource_usage=ResourceUsage(),
    )


def _validate_target(request: ModelTrainingRequest, job: _PreparedJob) -> str | None:
    values = [float(row.target_value) for row in job.training_rows]
    values.extend(float(row.target_value) for row in job.validation_rows)
    if any(not math.isfinite(value) for value in values):
        return "TARGET_OUT_OF_RANGE"
    if request.task is PredictionTask.BINARY_CLASSIFICATION:
        labels = {float(row.target_value) for row in job.training_rows}
        validation_labels = {float(row.target_value) for row in job.validation_rows}
        if not labels.issubset({0.0, 1.0}) or not validation_labels.issubset({0.0, 1.0}):
            return "NON_BINARY_TARGET"
        if len(labels) < 2:
            return "SINGLE_CLASS_TRAINING_TARGET"
    return None


def _grid_for_request(request: ModelTrainingRequest) -> dict[str, Any]:
    return {
        "schema_name": _HYPERPARAMETER_SCHEMA,
        "schema_version": "1.0",
        "family": request.family.value,
        "task": request.task.value,
        "seed": _FIXED_SEED,
        "selected_index": request.parameter_index,
        "parameter_space": [
            _plain(item) for item in FROZEN_PARAMETER_SPACES[request.family]
        ],
        "search_policy": "FIXED_ORDER_NO_ADAPTIVE_SELECTION",
        "selection_authority": "EXTERNAL_RESEARCH_POLICY",
    }


def _make_artifact_manifest(
    *,
    files: list[dict[str, Any]],
    created_at: str,
    evidence_class: str,
    environment_namespace: str,
    source_refs: list[dict[str, str]],
) -> dict[str, Any]:
    inventory = artifact_inventory_hash(files)
    payload: dict[str, Any] = {
        "schema_name": _ARTIFACT_SCHEMA,
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": created_at,
        "owning_authority": "model_registry",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": source_refs,
        "manifest_version": 1,
        "files": files,
        "inventory_hash": inventory,
        "detached_signature": None,
        "transport_hash": None,
        "content_hash": "0" * 64,
    }
    payload["content_hash"] = canonical_content_hash("ArtifactManifest", payload)
    validate_contract("ArtifactManifest", payload)
    verify_content_hash("ArtifactManifest", payload)
    return payload


def _build_model_manifests(
    request: ModelTrainingRequest,
    job: _PreparedJob,
    environment: TrainingEnvironment,
    model_id: str,
    created_at: str,
    model_bytes: bytes,
    parameter_bytes: bytes,
    environment_bytes: bytes,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    evidence_class = job.budget["evidence_class"]
    environment_namespace = job.budget["environment_namespace"]
    dataset_ref = _contract_ref(job.dataset, _DATASET_SCHEMA)
    split_ref = _contract_ref(job.split, _SPLIT_SCHEMA)
    budget_ref = _contract_ref(job.budget, _BUDGET_SCHEMA)
    refs = [dataset_ref, split_ref, budget_ref]
    artifact_files = [
        {
            "relative_path": "model.json",
            "length_bytes": len(model_bytes),
            "media_type": "application/json",
            "schema_name": _SAFE_ARTIFACT_SCHEMA,
            "schema_version": "1.0",
            "sha256": _sha256(model_bytes),
        },
        {
            "relative_path": "environment.json",
            "length_bytes": len(environment_bytes),
            "media_type": "application/json",
            "schema_name": _ENVIRONMENT_SCHEMA,
            "schema_version": "1.0",
            "sha256": _sha256(environment_bytes),
        },
    ]
    artifact_manifest = _make_artifact_manifest(
        files=artifact_files,
        created_at=created_at,
        evidence_class=evidence_class,
        environment_namespace=environment_namespace,
        source_refs=refs,
    )
    parameter_manifest = _make_artifact_manifest(
        files=[
            {
                "relative_path": "hyperparameters.json",
                "length_bytes": len(parameter_bytes),
                "media_type": "application/json",
                "schema_name": _HYPERPARAMETER_SCHEMA,
                "schema_version": "1.0",
                "sha256": _sha256(parameter_bytes),
            }
        ],
        created_at=created_at,
        evidence_class=evidence_class,
        environment_namespace=environment_namespace,
        source_refs=[dataset_ref, split_ref, budget_ref],
    )
    artifact_ref = _contract_ref(artifact_manifest, _ARTIFACT_SCHEMA)
    parameter_ref = _contract_ref(parameter_manifest, _ARTIFACT_SCHEMA)
    training_sessions = job.training_interval.get("sessions")
    if not isinstance(training_sessions, list) or not training_sessions:
        raise ModelFactoryError("training interval does not record exchange sessions")
    training_start = min(str(item) for item in training_sessions)
    validation_window = json.dumps(
        {
            "fold_id": request.fold_id,
            "sessions": job.validation_interval.get("sessions", []),
            "cutoff_at": job.validation_interval.get("cutoff_at"),
            "released_row_keys": sorted(row.row_key for row in job.validation_rows),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    qualification_window = json.dumps(
        {
            "sessions": job.qualification_interval.get("sessions", []),
            "cutoff_at": job.qualification_interval.get("cutoff_at"),
            "labels_released": False,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    resource_constraints = [
        f"max_artifact_bytes={job.budget['max_artifact_bytes']}",
        f"max_cpu_seconds={job.budget['max_cpu_seconds']}",
        f"max_elapsed_seconds={job.budget['max_elapsed_seconds']}",
        f"max_memory_bytes={job.budget['max_memory_bytes']}",
        "native_threads_per_job=1",
        "worker_environment=allowlisted",
    ]
    payload: dict[str, Any] = {
        "schema_name": _MODEL_SCHEMA,
        "schema_version": "1.0",
        "id": model_id,
        "created_at": created_at,
        "owning_authority": "model_registry",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [
            *refs,
            *job.target_label_refs,
            job.feature_registry_ref,
            job.protocol_registry_ref,
            artifact_ref,
            parameter_ref,
        ],
        "artifact_manifest_ref": artifact_ref,
        "safe_format": "json",
        "algorithm": request.family.value,
        "algorithm_version": _algorithm_version(request.family, environment),
        "target_label_refs": list(job.target_label_refs),
        "feature_registry_ref": job.feature_registry_ref,
        "ordered_feature_ids": list(request.transform.feature_ids),
        "protocol_registry_ref": job.protocol_registry_ref,
        "training_start": training_start,
        "training_cutoff": request.training_index.cutoff_at,
        "validation_window": validation_window,
        "qualification_window": qualification_window,
        "dataset_ref": dataset_ref,
        "split_ref": split_ref,
        "seed": _FIXED_SEED,
        "hyperparameter_refs": [parameter_ref],
        "calibration_ref": None,
        "package_lock_hash": environment.package_lock_hash,
        "environment_fingerprint": environment.fingerprint,
        "learned_dependency_refs": [dataset_ref],
        "resource_constraints": resource_constraints,
        "lifecycle_state": "RESEARCH",
        "content_hash": "0" * 64,
    }
    payload["content_hash"] = canonical_content_hash("ModelManifest", payload)
    validate_contract("ModelManifest", payload)
    verify_content_hash("ModelManifest", payload)
    return payload, artifact_manifest, parameter_manifest


def _algorithm_version(family: ModelFamily, environment: TrainingEnvironment) -> str:
    package = "xgboost" if family is ModelFamily.XGBOOST else "scikit-learn"
    return f"{package}=={environment.manifest['packages'][package]}"


def _safe_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            _plain(value),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelFactoryError(f"artifact cannot be represented as safe JSON: {exc}") from exc


def _commit_artifact_bundle(
    export_directory: Path,
    model_id: str,
    files: Mapping[str, bytes],
) -> Path:
    root = Path(export_directory)
    if not root.is_dir():
        raise ModelFactoryError("artifact export directory must already exist")
    final_path = root / model_id
    if final_path.exists():
        raise ModelFactoryError("artifact export destination already exists")
    staging = Path(tempfile.mkdtemp(prefix=f".{model_id}.", dir=root))
    try:
        for name, contents in files.items():
            if Path(name).name != name or name in {"", ".", ".."}:
                raise ModelFactoryError("artifact bundle paths must be simple filenames")
            target = staging / name
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(staging, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.rename(staging, final_path)
        parent_fd = os.open(root, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return final_path
    finally:
        if staging.exists():
            for child in staging.iterdir():
                child.unlink(missing_ok=True)
            staging.rmdir()


def _semaphore_for(budget: Mapping[str, Any]) -> BoundedSemaphore:
    key = (str(budget["id"]), int(budget["max_concurrent_jobs"]))
    with _SEMAPHORES_LOCK:
        semaphore = _SEMAPHORES.get(key)
        if semaphore is None:
            semaphore = BoundedSemaphore(key[1])
            _SEMAPHORES[key] = semaphore
        return semaphore


def train_candidate(
    request: ModelTrainingRequest,
    *,
    export_directory: Path,
    lock_file: Path,
) -> TrainingOutcome:
    """Train one frozen-grid model in a credential-free, OS-limited subprocess.

    This creates a RESEARCH artifact only. It does not qualify, calibrate,
    promote, select, persist to a database, or contact any provider.
    """
    if not isinstance(request.family, ModelFamily) or not isinstance(
        request.task, PredictionTask
    ):
        return _budget_failure(
            "INVALID_TRAINING_CONTRACT", "family and task must use the frozen enums"
        )
    if request.family is ModelFamily.LINEAR_REGRESSION and (
        request.task is not PredictionTask.REGRESSION
    ):
        return _incompatible(
            "TASK_FAMILY_MISMATCH", "linear regression requires a regression target"
        )
    if request.family is ModelFamily.LOGISTIC_REGRESSION and (
        request.task is not PredictionTask.BINARY_CLASSIFICATION
    ):
        return _incompatible(
            "TASK_FAMILY_MISMATCH",
            "logistic regression requires a binary classification target",
        )
    try:
        job = _prepare_job(request)
    except ModelFactoryError as exc:
        return _budget_failure("INVALID_TRAINING_CONTRACT", str(exc))

    incompatibility = _validate_target(request, job)
    if incompatibility:
        return _incompatible(incompatibility, "target values do not fit this model task")
    if request.family is ModelFamily.XGBOOST and not _package_available("xgboost"):
        return _incompatible(
            "REQUIRED_LIBRARY_UNAVAILABLE",
            "XGBoost adapter requires the pinned xgboost package.",
        )
    if not _package_available("sklearn"):
        return _incompatible(
            "REQUIRED_LIBRARY_UNAVAILABLE",
            "scikit-learn adapter requires the pinned scikit-learn package.",
        )

    budget = job.budget
    if budget["max_elapsed_seconds"] < _MIN_WALL_SECONDS:
        return _budget_failure(
            "TIME_BUDGET_EXHAUSTED",
            "the declared wall-time budget is too small to start an isolated trainer",
        )
    if budget["max_cpu_seconds"] < _MIN_CPU_SECONDS:
        return _budget_failure(
            "CPU_BUDGET_EXHAUSTED",
            "the declared CPU budget is too small to start an isolated trainer",
        )
    estimated_matrix_bytes = (
        len(job.training_rows) + len(job.validation_rows)
    ) * len(request.transform.feature_ids) * 8 * 8
    if budget["max_memory_bytes"] < estimated_matrix_bytes + _BASE_MEMORY_RESERVE:
        return _budget_failure(
            "MEMORY_BUDGET_EXHAUSTED",
            "the declared memory budget is below the frozen input and runtime reserve",
        )
    if budget["max_artifact_bytes"] < 1024:
        return _budget_failure(
            "ARTIFACT_BUDGET_EXHAUSTED",
            "the declared artifact budget is too small for a model manifest",
        )
    if budget["max_concurrent_jobs"] < 1:
        return _budget_failure(
            "CONCURRENCY_BUDGET_EXHAUSTED",
            "the declared concurrency budget does not permit a training job",
        )
    if not Path(export_directory).is_dir():
        return _budget_failure(
            "EXPORT_DIRECTORY_UNAVAILABLE",
            "artifact export directory must already exist",
        )
    semaphore = _semaphore_for(budget)
    if not semaphore.acquire(blocking=False):
        return _budget_failure(
            "CONCURRENCY_BUDGET_EXHAUSTED",
            "all concurrent-job slots for this research budget are occupied",
        )

    started = time.monotonic()
    try:
        try:
            environment = build_training_environment(lock_file)
        except (OSError, ModelFactoryError) as exc:
            return _budget_failure("ENVIRONMENT_MANIFEST_INVALID", str(exc))

        training_rows = job.training_rows
        validation_rows = job.validation_rows
        training_x = [[float(value) for value in row.feature_values] for row in training_rows]
        validation_x = [
            [float(value) for value in row.feature_values] for row in validation_rows
        ]
        training_y = [float(row.target_value) for row in training_rows]
        validation_y = [float(row.target_value) for row in validation_rows]
        training_weights = [
            1.0 if row.sample_weight is None else float(row.sample_weight)
            for row in training_rows
        ]
        payload = {
            "family": request.family.value,
            "task": request.task.value,
            "seed": _FIXED_SEED,
            "parameters": job.parameters,
            "training_x": training_x,
            "training_y": training_y,
            "training_weights": training_weights,
            "validation_x": validation_x,
            "validation_y": validation_y,
        }
        if not sys.platform.startswith("linux") or not hasattr(resource, "RLIMIT_AS"):
            return _budget_failure(
                "RESOURCE_LIMITS_UNAVAILABLE",
                "this trainer requires Linux CPU, address-space, and wall-time limits",
            )

        with tempfile.TemporaryDirectory(prefix="qc2-model-factory-") as temporary:
            temp_root = Path(temporary)
            request_file = temp_root / "request.json"
            response_file = temp_root / "response.json"
            request_file.write_bytes(_safe_json_bytes(payload))
            command = [
                sys.executable,
                "-s",
                str(Path(__file__).with_name("_model_worker.py")),
                str(request_file),
                str(response_file),
            ]
            remaining_seconds = float(budget["max_elapsed_seconds"]) - (
                time.monotonic() - started
            )
            if remaining_seconds <= 0:
                return _budget_failure(
                    "TIME_BUDGET_EXHAUSTED",
                    "the declared wall-time budget expired before the trainer started",
                    ResourceUsage(elapsed_seconds=max(1, math.ceil(time.monotonic() - started))),
                )
            try:
                process = subprocess.Popen(
                    command,
                    cwd=Path(__file__).resolve().parents[4],
                    env=_worker_environment(temp_root),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    close_fds=True,
                    start_new_session=True,
                    preexec_fn=_limits_preexec(
                        int(budget["max_cpu_seconds"]),
                        int(budget["max_memory_bytes"]),
                    ),
                )
                _, stderr = process.communicate(timeout=remaining_seconds)
            except subprocess.TimeoutExpired:
                if "process" in locals() and process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                elapsed = max(1, math.ceil(time.monotonic() - started))
                return _budget_failure(
                    "TIME_BUDGET_EXHAUSTED",
                    "the isolated trainer exceeded its wall-time budget",
                    ResourceUsage(elapsed_seconds=elapsed),
                )
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                return _budget_failure("TRAINER_LAUNCH_FAILED", str(exc))

            elapsed = max(1, math.ceil(time.monotonic() - started))
            if process.returncode != 0 or not response_file.is_file():
                stderr_text = (stderr or "").strip()
                reason_code = (
                    "CPU_BUDGET_EXHAUSTED"
                    if process.returncode == -signal.SIGXCPU
                    else "MEMORY_BUDGET_EXHAUSTED"
                    if process.returncode in {-signal.SIGSEGV, -signal.SIGKILL}
                    else "TRAINER_PROCESS_FAILED"
                )
                return _budget_failure(
                    reason_code,
                    stderr_text[-1000:] or "isolated trainer exited without a safe result",
                    ResourceUsage(elapsed_seconds=elapsed),
                )
            try:
                worker_result = json.loads(response_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return _budget_failure(
                    "TRAINER_OUTPUT_INVALID",
                    f"isolated trainer output is invalid: {exc}",
                    ResourceUsage(elapsed_seconds=elapsed),
                )
            if worker_result.get("status") != "OK":
                return _budget_failure(
                    str(worker_result.get("reason_code", "TRAINER_PROCESS_FAILED")),
                    str(worker_result.get("reason", "isolated trainer failed")),
                    _resource_usage(worker_result),
                )
            usage = _resource_usage(worker_result)
            usage = ResourceUsage(
                elapsed_seconds=elapsed,
                cpu_seconds=usage.cpu_seconds,
                peak_memory_bytes=usage.peak_memory_bytes,
                cost_minor_units=0,
            )
            if (
                usage.elapsed_seconds > budget["max_elapsed_seconds"]
                or usage.cpu_seconds > budget["max_cpu_seconds"]
                or usage.peak_memory_bytes > budget["max_memory_bytes"]
            ):
                return _budget_failure(
                    "RESOURCE_BUDGET_EXCEEDED",
                    "observed trainer resource use exceeded the declared budget",
                    usage,
                )

            try:
                model_state = worker_result["model_state"]
                predictions = tuple(
                    float(item) for item in worker_result["validation_predictions"]
                )
                metric_value = float(worker_result["validation_metric_value"])
                if (
                    not all(math.isfinite(value) for value in predictions)
                    or not math.isfinite(metric_value)
                    or len(predictions) != len(validation_rows)
                ):
                    raise ValueError("trainer returned an invalid development prediction set")
                created_at = _utc_now()
                model_id = new_uuidv7()
                parameter_payload = _grid_for_request(request)
                model_payload: dict[str, Any] = {
                    "schema_name": _SAFE_ARTIFACT_SCHEMA,
                    "schema_version": "1.0",
                    "model_id": model_id,
                    "family": request.family.value,
                    "task": request.task.value,
                    "seed": _FIXED_SEED,
                    "parameters": job.parameters,
                    "feature_ids": list(request.transform.feature_ids),
                    "estimator_state": model_state,
                    "preprocessing_lineage": {
                        "transform_hash": request.transform.transform_hash,
                        "fit_row_keys": list(request.transform.fit_row_keys),
                        "fit_cutoff": request.transform.cutoff_at,
                        "means": [str(item) for item in request.transform.means],
                        "scales": [str(item) for item in request.transform.scales],
                        "feature_order": list(request.transform.feature_ids),
                    },
                    "calibration_lineage": {
                        "state": "NOT_APPLIED",
                        "reason_code": "CALIBRATION_OUTSIDE_MODEL_FACTORY_SCOPE",
                        "calibration_ref": None,
                    },
                    "dataset_ref": _contract_ref(job.dataset, _DATASET_SCHEMA),
                    "split_ref": _contract_ref(job.split, _SPLIT_SCHEMA),
                    "fold_id": request.fold_id,
                    "training_index_hash": request.training_index.index_hash,
                    "training_row_keys": [row.row_key for row in training_rows],
                    "validation_row_keys": [row.row_key for row in validation_rows],
                    "environment_fingerprint": environment.fingerprint,
                }
                model_bytes = _safe_json_bytes(model_payload)
                parameter_bytes = _safe_json_bytes(parameter_payload)
                environment_bytes = _safe_json_bytes(environment.manifest)
                artifact_bytes = len(model_bytes) + len(parameter_bytes) + len(environment_bytes)
                usage = ResourceUsage(
                    elapsed_seconds=elapsed,
                    cpu_seconds=usage.cpu_seconds,
                    peak_memory_bytes=usage.peak_memory_bytes,
                    artifact_bytes=artifact_bytes,
                    cost_minor_units=0,
                )
                if artifact_bytes > budget["max_artifact_bytes"]:
                    return _budget_failure(
                        "ARTIFACT_BUDGET_EXCEEDED",
                        "the safe JSON bundle exceeds the declared artifact budget",
                        usage,
                    )
                model_manifest, artifact_manifest, parameter_manifest = (
                    _build_model_manifests(
                        request,
                        job,
                        environment,
                        model_id,
                        created_at,
                        model_bytes,
                        parameter_bytes,
                        environment_bytes,
                    )
                )
                bundle_path = _commit_artifact_bundle(
                    Path(export_directory),
                    model_id,
                    {
                        "model.json": model_bytes,
                        "hyperparameters.json": parameter_bytes,
                        "environment.json": environment_bytes,
                    },
                )
                completed_elapsed = max(1, math.ceil(time.monotonic() - started))
                usage = ResourceUsage(
                    elapsed_seconds=completed_elapsed,
                    cpu_seconds=usage.cpu_seconds,
                    peak_memory_bytes=usage.peak_memory_bytes,
                    artifact_bytes=artifact_bytes,
                    cost_minor_units=0,
                )
                if completed_elapsed > budget["max_elapsed_seconds"]:
                    shutil.rmtree(bundle_path)
                    return _budget_failure(
                        "TIME_BUDGET_EXHAUSTED",
                        "the completed export exceeded the declared wall-time budget",
                        usage,
                    )
            except (OSError, ModelFactoryError, TypeError, ValueError, KeyError) as exc:
                return _budget_failure(
                    "ARTIFACT_EXPORT_INTERRUPTED",
                    f"candidate export did not complete: {exc}",
                    usage,
                )

        candidate = TrainingCandidate(
            model_manifest=model_manifest,
            artifact_manifest=artifact_manifest,
            hyperparameter_manifest=parameter_manifest,
            artifact_path=bundle_path,
            validation_predictions=predictions,
            validation_metric_name=str(worker_result["validation_metric_name"]),
            validation_metric_value=metric_value,
            resource_usage=usage,
        )
        return TrainingOutcome(
            state=TrainingOutcomeState.CANDIDATE_CREATED,
            candidate=candidate,
            reason_code=None,
            reason=None,
            resource_usage=usage,
        )
    finally:
        semaphore.release()


def _package_available(package_name: str) -> bool:
    try:
        from importlib.util import find_spec

        return find_spec(package_name) is not None
    except (ImportError, ValueError):
        return False


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_safe_model_artifact(path: Path, *, max_bytes: int = 16 * 1024 * 1024) -> dict[str, Any]:
    """Parse JSON data only; this function never imports or executes model code."""
    model_file = Path(path) / "model.json"
    if type(max_bytes) is not int or max_bytes < 1:
        raise ModelFactoryError("safe parser byte limit must be a positive integer")
    if model_file.stat().st_size > max_bytes:
        raise ModelFactoryError("model artifact exceeds the safe parser byte limit")
    contents = model_file.read_bytes()
    if len(contents) > max_bytes:
        raise ModelFactoryError("model artifact exceeds the safe parser byte limit")
    try:
        payload = json.loads(
            contents,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite JSON value: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ModelFactoryError(f"model artifact is not strict JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_name") != _SAFE_ARTIFACT_SCHEMA:
        raise ModelFactoryError("model artifact schema is unsupported")
    if payload.get("schema_version") != "1.0" or payload.get("calibration_lineage", {}).get(
        "state"
    ) != "NOT_APPLIED":
        raise ModelFactoryError("model artifact safety or calibration state is invalid")
    return payload
