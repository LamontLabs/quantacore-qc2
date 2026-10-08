"""Read-only interpreter for the allowlisted QC2-035 JSON model artifacts."""

from __future__ import annotations

import json
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from qc2_contracts.runtime import canonical_json_bytes

from .metrics import as_decimal, quantize
from .models import EvaluationError, QualificationRow, thaw_json


_ARTIFACT_SCHEMA = "qc2.apexlab.SafeModelArtifact.v1"
_ARTIFACT_VERSION = "1.0"
_MODEL_ARTIFACT_FIELDS = {
    "schema_name",
    "schema_version",
    "model_id",
    "family",
    "task",
    "seed",
    "parameters",
    "feature_ids",
    "estimator_state",
    "preprocessing_lineage",
    "calibration_lineage",
    "dataset_ref",
    "split_ref",
    "fold_id",
    "training_index_hash",
    "training_row_keys",
    "validation_row_keys",
    "environment_fingerprint",
}
_SUPPORTED_FAMILIES = {
    "linear_regression",
    "logistic_regression",
    "random_forest",
    "gradient_boosting",
    "xgboost",
}
_MAX_FEATURES = 512
_MAX_TREES = 10_000
_MAX_TREE_NODES = 1_000_000


@dataclass(frozen=True, slots=True)
class SafeCandidateModel:
    family: str
    task: str
    feature_ids: tuple[str, ...]
    means: tuple[Decimal, ...]
    scales: tuple[Decimal, ...]
    estimator_state: Mapping[str, Any]
    training_row_keys: tuple[str, ...]
    validation_row_keys: tuple[str, ...]
    fit_row_keys: tuple[str, ...]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationError(f"candidate JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise EvaluationError(f"candidate JSON contains non-finite value {value}")


def _parse_json(data: bytes) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_object,
        )
    except EvaluationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise EvaluationError(f"candidate model artifact is not valid strict JSON: {exc}") from exc


def validate_environment_manifest(
    environment_bytes: bytes,
    model_manifest: Mapping[str, Any],
) -> Mapping[str, Any]:
    environment = _parse_json(environment_bytes)
    if (
        not isinstance(environment, dict)
        or environment.get("schema_name") != "qc2.apexlab.TrainingEnvironment.v1"
        or environment.get("schema_version") != "1.0"
        or not isinstance(environment.get("packages"), dict)
    ):
        raise EvaluationError("candidate training environment manifest is malformed")
    fingerprint = hashlib.sha256(canonical_json_bytes(environment)).hexdigest()
    if (
        fingerprint != model_manifest.get("environment_fingerprint")
        or environment.get("package_lock_hash") != model_manifest.get("package_lock_hash")
    ):
        raise EvaluationError("training environment bytes do not match ModelManifest")
    package = (
        "xgboost"
        if model_manifest.get("algorithm") == "xgboost"
        else "scikit-learn"
    )
    if model_manifest.get("algorithm_version") != f"{package}=={environment['packages'].get(package)}":
        raise EvaluationError("training algorithm version differs from its environment manifest")
    return environment


def _ref_matches(actual: Any, expected: Mapping[str, Any]) -> bool:
    if not isinstance(actual, Mapping):
        return False
    return all(actual.get(key) == expected.get(key) for key in (
        "target_schema_name",
        "target_id",
        "content_hash",
    ))


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise EvaluationError(f"{field} must be an ordered list of unique nonempty strings")
    return tuple(value)


def _parse_window(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise EvaluationError(f"ModelManifest.{field} must be JSON text")
    try:
        window = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise EvaluationError(f"ModelManifest.{field} must be valid JSON text") from exc
    if not isinstance(window, dict):
        raise EvaluationError(f"ModelManifest.{field} must contain a JSON object")
    return window


def load_candidate_model(
    model_bytes: bytes,
    model_manifest: Mapping[str, Any],
    dataset_ref: Mapping[str, Any],
    split_ref: Mapping[str, Any],
) -> SafeCandidateModel:
    if not isinstance(model_bytes, bytes) or not model_bytes:
        raise EvaluationError("candidate model.json must be nonempty bytes")
    artifact = _parse_json(model_bytes)
    if not isinstance(artifact, dict) or set(artifact) != _MODEL_ARTIFACT_FIELDS:
        raise EvaluationError(
            "candidate model artifact has unknown fields or omits required provenance"
        )
    if (
        artifact.get("schema_name") != _ARTIFACT_SCHEMA
        or artifact.get("schema_version") != _ARTIFACT_VERSION
    ):
        raise EvaluationError("candidate model artifact schema/version is unsupported")
    model = thaw_json(model_manifest)
    if not isinstance(model, dict):
        raise EvaluationError("ModelManifest must be an object")
    family = artifact.get("family")
    task = artifact.get("task")
    if family not in _SUPPORTED_FAMILIES or family != model.get("algorithm"):
        raise EvaluationError("candidate algorithm is not allowlisted or disagrees with its manifest")
    if task not in {"REGRESSION", "BINARY_CLASSIFICATION"}:
        raise EvaluationError("candidate prediction task is not allowlisted")
    if family == "linear_regression" and task != "REGRESSION":
        raise EvaluationError("linear-regression family and task are incompatible")
    if family == "logistic_regression" and task != "BINARY_CLASSIFICATION":
        raise EvaluationError("logistic-regression family and task are incompatible")
    if (
        artifact.get("model_id") != model.get("id")
        or artifact.get("seed") != model.get("seed")
        or artifact.get("environment_fingerprint") != model.get("environment_fingerprint")
        or not _ref_matches(artifact.get("dataset_ref"), dataset_ref)
        or not _ref_matches(artifact.get("split_ref"), split_ref)
    ):
        raise EvaluationError("candidate artifact is not bound to the nominated model and data")

    feature_ids = _string_tuple(artifact.get("feature_ids"), "feature_ids")
    if (
        not feature_ids
        or len(feature_ids) > _MAX_FEATURES
        or list(feature_ids) != model.get("ordered_feature_ids")
    ):
        raise EvaluationError("candidate feature order does not match ModelManifest")

    preprocessing = artifact.get("preprocessing_lineage")
    if not isinstance(preprocessing, dict):
        raise EvaluationError("candidate preprocessing lineage is required")
    if preprocessing.get("feature_order") != list(feature_ids):
        raise EvaluationError("preprocessing feature order does not match the model")
    means_raw = preprocessing.get("means")
    scales_raw = preprocessing.get("scales")
    if (
        not isinstance(means_raw, list)
        or not isinstance(scales_raw, list)
        or len(means_raw) != len(feature_ids)
        or len(scales_raw) != len(feature_ids)
    ):
        raise EvaluationError("preprocessing means and scales must match feature order")
    means = tuple(as_decimal(value, "preprocessing mean") for value in means_raw)
    scales = tuple(as_decimal(value, "preprocessing scale") for value in scales_raw)
    if any(scale == 0 for scale in scales):
        raise EvaluationError("preprocessing scales must be nonzero")

    training_keys = _string_tuple(artifact.get("training_row_keys"), "training_row_keys")
    validation_keys = _string_tuple(
        artifact.get("validation_row_keys"), "validation_row_keys"
    )
    fit_keys = _string_tuple(preprocessing.get("fit_row_keys"), "fit_row_keys")
    if set(training_keys) & set(validation_keys):
        raise EvaluationError("training and validation row inventories overlap")
    if set(fit_keys) != set(training_keys):
        raise EvaluationError("preprocessing fit rows do not match the training inventory")

    validation_window = _parse_window(model.get("validation_window"), "validation_window")
    manifest_validation_keys = validation_window.get("released_row_keys")
    if (
        not isinstance(manifest_validation_keys, list)
        or tuple(sorted(manifest_validation_keys)) != tuple(sorted(validation_keys))
    ):
        raise EvaluationError("validation row inventory differs from ModelManifest")
    qualification_window = _parse_window(
        model.get("qualification_window"), "qualification_window"
    )
    if qualification_window.get("labels_released") is not False:
        raise EvaluationError("candidate training manifest says qualification labels were released")

    calibration_lineage = artifact.get("calibration_lineage")
    if not isinstance(calibration_lineage, dict):
        raise EvaluationError("candidate calibration lineage is required")
    if calibration_lineage.get("calibration_ref") != model.get("calibration_ref"):
        raise EvaluationError("calibration artifact lineage differs from ModelManifest")

    estimator_state = artifact.get("estimator_state")
    if not isinstance(estimator_state, dict):
        raise EvaluationError("candidate estimator state must be a data object")
    expected_kind = {
        "linear_regression": "linear_coefficients",
        "logistic_regression": "linear_coefficients",
        "random_forest": "forest_trees",
        "gradient_boosting": "gradient_boosting_trees",
        "xgboost": "xgboost_booster_json",
    }[family]
    if estimator_state.get("kind") != expected_kind:
        raise EvaluationError("candidate estimator state is not an allowlisted representation")
    if estimator_state.get("n_features_in") != len(feature_ids):
        raise EvaluationError("candidate estimator feature count does not match ModelManifest")

    return SafeCandidateModel(
        family=family,
        task=task,
        feature_ids=feature_ids,
        means=means,
        scales=scales,
        estimator_state=estimator_state,
        training_row_keys=training_keys,
        validation_row_keys=validation_keys,
        fit_row_keys=fit_keys,
    )


def _sigmoid(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        if value >= 0:
            return Decimal(1) / (Decimal(1) + (-value).exp())
        exponential = value.exp()
        return exponential / (Decimal(1) + exponential)


def _scalar(value: Any, field: str) -> Decimal:
    if isinstance(value, list):
        if len(value) != 1:
            raise EvaluationError(f"{field} must contain exactly one output")
        return _scalar(value[0], field)
    return as_decimal(value, field)


def _matrix_row(value: Any, field: str) -> list[Decimal]:
    if not isinstance(value, list) or not value:
        raise EvaluationError(f"{field} must be a nonempty numeric matrix")
    if isinstance(value[0], list):
        if len(value) != 1:
            raise EvaluationError(f"{field} must contain one output row")
        value = value[0]
    if not isinstance(value, list):
        raise EvaluationError(f"{field} must be a numeric vector")
    return [as_decimal(item, field) for item in value]


def _tree_leaf(
    tree: Mapping[str, Any],
    row: Sequence[Decimal],
) -> Any:
    required_arrays = (
        "children_left",
        "children_right",
        "feature",
        "threshold",
        "value",
    )
    if any(not isinstance(tree.get(name), list) for name in required_arrays):
        raise EvaluationError("tree estimator arrays are missing")
    count = tree.get("node_count")
    if type(count) is not int or not 1 <= count <= _MAX_TREE_NODES:
        raise EvaluationError("tree node_count is invalid")
    if any(len(tree[name]) != count for name in required_arrays):
        raise EvaluationError("tree estimator arrays have inconsistent lengths")
    left = tree["children_left"]
    right = tree["children_right"]
    feature = tree["feature"]
    threshold = tree["threshold"]
    values = tree["value"]
    node = 0
    for _ in range(count):
        left_child = left[node]
        right_child = right[node]
        if type(left_child) is not int or type(right_child) is not int:
            raise EvaluationError("tree child indices must be integers")
        if left_child == -1 and right_child == -1:
            leaf_values = values[node]
            if not isinstance(leaf_values, list) or len(leaf_values) != 1:
                raise EvaluationError("tree leaf value has an unsupported shape")
            leaf = leaf_values[0]
            if not isinstance(leaf, list) or not leaf:
                raise EvaluationError("tree leaf value has an unsupported shape")
            return leaf
        if not (0 <= left_child < count and 0 <= right_child < count):
            raise EvaluationError("tree child index is out of range")
        feature_index = feature[node]
        if type(feature_index) is not int or not 0 <= feature_index < len(row):
            raise EvaluationError("tree split feature is out of range")
        threshold_value = as_decimal(threshold[node], "tree threshold")
        node = left_child if row[feature_index] <= threshold_value else right_child
    raise EvaluationError("tree traversal exceeded its node bound")


def _tree_regression_value(tree: Mapping[str, Any], row: Sequence[Decimal]) -> Decimal:
    leaf = _tree_leaf(tree, row)
    if not isinstance(leaf, list) or len(leaf) != 1:
        raise EvaluationError("regression tree leaf has an unsupported value shape")
    return _scalar(leaf[0], "regression tree leaf")


def _tree_positive_probability(
    tree: Mapping[str, Any],
    row: Sequence[Decimal],
) -> Decimal:
    leaf = _tree_leaf(tree, row)
    if not isinstance(leaf, list) or len(leaf) != 2:
        raise EvaluationError("classification tree leaf has an unsupported value shape")
    counts = [as_decimal(value, "classification leaf count") for value in leaf]
    total = sum(counts, Decimal(0))
    if total <= 0:
        raise EvaluationError("classification tree must contain two nonempty classes")
    return counts[1] / total


def _classes_are_binary(state: Mapping[str, Any]) -> bool:
    classes = state.get("classes")
    if not isinstance(classes, list) or len(classes) != 2:
        return False
    try:
        return [as_decimal(item, "class label") for item in classes] == [
            Decimal(0),
            Decimal(1),
        ]
    except EvaluationError:
        return False


def _xgboost_base_score(learner: Mapping[str, Any]) -> Decimal:
    parameter = learner.get("learner_model_param")
    if not isinstance(parameter, Mapping):
        raise EvaluationError("XGBoost learner parameters are missing")
    value: Any = parameter.get("base_score")
    if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise EvaluationError("XGBoost base score is invalid") from exc
    if isinstance(value, list):
        if len(value) != 1:
            raise EvaluationError("multi-output XGBoost base scores are unsupported")
        value = value[0]
    return as_decimal(value, "XGBoost base score")


def _xgboost_tree_value(
    tree: Mapping[str, Any],
    row: Sequence[Decimal],
) -> Decimal:
    left = tree.get("left_children")
    right = tree.get("right_children")
    features = tree.get("split_indices")
    conditions = tree.get("split_conditions")
    if not all(isinstance(values, list) for values in (left, right, features, conditions)):
        raise EvaluationError("XGBoost tree arrays are missing")
    count = len(left)
    if not 1 <= count <= _MAX_TREE_NODES or any(
        len(values) != count for values in (right, features, conditions)
    ):
        raise EvaluationError("XGBoost tree arrays have inconsistent sizes")
    node = 0
    for _ in range(count):
        left_child = left[node]
        right_child = right[node]
        if type(left_child) is not int or type(right_child) is not int:
            raise EvaluationError("XGBoost child indices must be integers")
        if left_child == -1 and right_child == -1:
            return as_decimal(conditions[node], "XGBoost leaf weight")
        if not (0 <= left_child < count and 0 <= right_child < count):
            raise EvaluationError("XGBoost child index is out of range")
        feature_index = features[node]
        if type(feature_index) is not int or not 0 <= feature_index < len(row):
            raise EvaluationError("XGBoost split feature is out of range")
        threshold = as_decimal(conditions[node], "XGBoost split threshold")
        node = left_child if row[feature_index] < threshold else right_child
    raise EvaluationError("XGBoost tree traversal exceeded its node bound")


def _predict_one(model: SafeCandidateModel, row: Sequence[Decimal]) -> Decimal:
    state = model.estimator_state
    if model.family in {"linear_regression", "logistic_regression"}:
        if model.task == "BINARY_CLASSIFICATION" and not _classes_are_binary(state):
            raise EvaluationError("linear classifier must declare ordered classes [0, 1]")
        coefficients = _matrix_row(
            state.get("coefficient_matrix"), "linear coefficient matrix"
        )
        intercept = _scalar(state.get("intercept"), "linear intercept")
        if len(coefficients) != len(row):
            raise EvaluationError("linear coefficient count does not match feature order")
        raw = intercept + sum(
            (coefficient * feature for coefficient, feature in zip(coefficients, row)),
            Decimal(0),
        )
        return _sigmoid(raw) if model.task == "BINARY_CLASSIFICATION" else raw

    if model.family == "random_forest":
        trees = state.get("trees")
        if not isinstance(trees, list) or not 1 <= len(trees) <= _MAX_TREES:
            raise EvaluationError("random-forest tree inventory is invalid")
        if model.task == "BINARY_CLASSIFICATION":
            if not _classes_are_binary(state):
                raise EvaluationError("random-forest classes must be ordered [0, 1]")
            return sum(
                (_tree_positive_probability(tree, row) for tree in trees),
                Decimal(0),
            ) / Decimal(len(trees))
        return sum(
            (_tree_regression_value(tree, row) for tree in trees),
            Decimal(0),
        ) / Decimal(len(trees))

    if model.family == "gradient_boosting":
        trees = state.get("trees")
        if not isinstance(trees, list) or not 1 <= len(trees) <= _MAX_TREES:
            raise EvaluationError("gradient-boosting tree inventory is invalid")
        learning_rate = as_decimal(state.get("learning_rate"), "learning rate")
        base = _scalar(state.get("base_raw_prediction"), "base raw prediction")
        if learning_rate <= 0:
            raise EvaluationError("gradient-boosting learning rate must be positive")
        if model.task == "BINARY_CLASSIFICATION" and not _classes_are_binary(state):
            raise EvaluationError("gradient-boosting classes must be ordered [0, 1]")
        raw = base + learning_rate * sum(
            (_tree_regression_value(tree, row) for tree in trees),
            Decimal(0),
        )
        return _sigmoid(raw) if model.task == "BINARY_CLASSIFICATION" else raw

    if model.family == "xgboost":
        booster = state.get("booster")
        if not isinstance(booster, Mapping):
            raise EvaluationError("XGBoost booster data is missing")
        learner = booster.get("learner")
        if not isinstance(learner, Mapping):
            raise EvaluationError("XGBoost learner data is missing")
        objective = learner.get("objective")
        if not isinstance(objective, Mapping):
            raise EvaluationError("XGBoost objective is missing")
        objective_name = objective.get("name")
        expected_objective = (
            "binary:logistic"
            if model.task == "BINARY_CLASSIFICATION"
            else "reg:squarederror"
        )
        if objective_name != expected_objective:
            raise EvaluationError("XGBoost objective does not match the candidate task")
        gradient_booster = learner.get("gradient_booster")
        model_data = (
            gradient_booster.get("model")
            if isinstance(gradient_booster, Mapping)
            else None
        )
        trees = model_data.get("trees") if isinstance(model_data, Mapping) else None
        if not isinstance(trees, list) or not 1 <= len(trees) <= _MAX_TREES:
            raise EvaluationError("XGBoost tree inventory is invalid")
        raw = _xgboost_base_score(learner)
        if model.task == "BINARY_CLASSIFICATION":
            if not Decimal(0) < raw < Decimal(1):
                raise EvaluationError("XGBoost binary base score must lie in (0, 1)")
            raw = (raw / (Decimal(1) - raw)).ln()
        raw += sum(
            (_xgboost_tree_value(tree, row) for tree in trees),
            Decimal(0),
        )
        return _sigmoid(raw) if model.task == "BINARY_CLASSIFICATION" else raw

    raise EvaluationError("candidate model family is not supported by the evaluator")


def infer_predictions(
    model: SafeCandidateModel,
    rows: Sequence[QualificationRow],
) -> tuple[Decimal, ...]:
    predictions: list[Decimal] = []
    for row in rows:
        transformed: list[Decimal] = []
        for feature_id, mean, scale in zip(
            model.feature_ids,
            model.means,
            model.scales,
        ):
            if feature_id not in row.features:
                raise EvaluationError(f"qualification row omits feature {feature_id}")
            raw_value = as_decimal(row.features[feature_id], f"feature {feature_id}")
            transformed.append((raw_value - mean) / scale)
        prediction = quantize(_predict_one(model, transformed))
        if not prediction.is_finite():
            raise EvaluationError("candidate inference produced a non-finite prediction")
        predictions.append(prediction)
    return tuple(predictions)
