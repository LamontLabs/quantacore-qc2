"""Private subprocess entry point for deterministic, single-thread model fitting."""

from __future__ import annotations

import json
import math
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any


def _deny_external_capabilities(event: str, args: tuple[Any, ...]) -> None:
    del args
    if event.startswith("socket.") or event in {
        "os.system",
        "os.exec",
        "os.posix_spawn",
        "subprocess.Popen",
    }:
        raise PermissionError(f"isolated model worker denied capability: {event}")


def _finite(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return _finite(value.tolist())
    if isinstance(value, dict):
        return {str(key): _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    if hasattr(value, "item"):
        return _finite(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("model state contains a nonfinite number")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported model state value: {type(value).__name__}")


def _tree_state(estimator: Any) -> dict[str, Any]:
    tree = estimator.tree_
    return {
        "node_count": int(tree.node_count),
        "children_left": tree.children_left.tolist(),
        "children_right": tree.children_right.tolist(),
        "feature": tree.feature.tolist(),
        "threshold": tree.threshold.tolist(),
        "value": tree.value.tolist(),
        "impurity": tree.impurity.tolist(),
        "n_node_samples": tree.n_node_samples.tolist(),
        "weighted_n_node_samples": tree.weighted_n_node_samples.tolist(),
    }


def _scikit_state(model: Any, family: str, features: int) -> dict[str, Any]:
    if family in {"linear_regression", "logistic_regression"}:
        return {
            "kind": "linear_coefficients",
            "classes": _finite(getattr(model, "classes_", [])),
            "coefficient_matrix": _finite(model.coef_),
            "intercept": _finite(model.intercept_),
            "n_features_in": int(model.n_features_in_),
        }
    if family == "random_forest":
        estimators = list(model.estimators_)
        return {
            "kind": "forest_trees",
            "classes": _finite(getattr(model, "classes_", [])),
            "n_features_in": int(model.n_features_in_),
            "trees": [_tree_state(tree) for tree in estimators],
        }
    if family == "gradient_boosting":
        estimators = [tree for tree in model.estimators_.ravel()]
        base_prediction = model._raw_predict_init(
            __import__("numpy").zeros((1, features), dtype="float64")
        )
        return {
            "kind": "gradient_boosting_trees",
            "classes": _finite(getattr(model, "classes_", [])),
            "n_features_in": int(model.n_features_in_),
            "learning_rate": float(model.learning_rate),
            "base_raw_prediction": _finite(base_prediction),
            "trees": [_tree_state(tree) for tree in estimators],
        }
    if family == "xgboost":
        raw_model = model.get_booster().save_raw(raw_format="json")
        return {
            "kind": "xgboost_booster_json",
            "booster": json.loads(bytes(raw_model).decode("utf-8")),
            "n_features_in": int(model.n_features_in_),
        }
    raise ValueError(f"unsupported model family: {family}")


def _fit(request: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    from threadpoolctl import threadpool_limits

    family = request["family"]
    task = request["task"]
    parameters = dict(request["parameters"])
    seed = int(request["seed"])
    x_train = np.asarray(request["training_x"], dtype="float64")
    y_train = np.asarray(request["training_y"], dtype="float64")
    weights = np.asarray(request["training_weights"], dtype="float64")
    x_validation = np.asarray(request["validation_x"], dtype="float64")
    y_validation = np.asarray(request["validation_y"], dtype="float64")
    if (
        x_train.ndim != 2
        or x_validation.ndim != 2
        or x_train.shape[1] == 0
        or x_train.shape[1] != x_validation.shape[1]
        or len(x_train) != len(y_train)
        or len(x_train) != len(weights)
        or len(x_validation) != len(y_validation)
        or not np.isfinite(x_train).all()
        or not np.isfinite(y_train).all()
        or not np.isfinite(weights).all()
        or not np.isfinite(x_validation).all()
        or not np.isfinite(y_validation).all()
        or (weights <= 0).any()
    ):
        raise ValueError("isolated worker received invalid training arrays")

    if family == "linear_regression" and task == "REGRESSION":
        from sklearn.linear_model import Ridge

        model = Ridge(alpha=parameters["alpha"], solver="lsqr")
        metric_name = "rmse"
    elif family == "logistic_regression" and task == "BINARY_CLASSIFICATION":
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(
            C=parameters["C"],
            max_iter=256,
            n_jobs=1,
            random_state=seed,
            solver="liblinear",
        )
        metric_name = "brier"
    elif family in {"random_forest", "gradient_boosting"}:
        if family == "random_forest":
            if task == "REGRESSION":
                from sklearn.ensemble import RandomForestRegressor as Estimator
            else:
                from sklearn.ensemble import RandomForestClassifier as Estimator
            model = Estimator(
                **parameters,
                n_jobs=1,
                random_state=seed,
                max_features=1.0,
            )
        else:
            if task == "REGRESSION":
                from sklearn.ensemble import GradientBoostingRegressor as Estimator
            else:
                from sklearn.ensemble import GradientBoostingClassifier as Estimator
            model = Estimator(**parameters, random_state=seed)
        metric_name = "rmse" if task == "REGRESSION" else "brier"
    elif family == "xgboost":
        if task == "REGRESSION":
            from xgboost import XGBRegressor as Estimator

            objective = "reg:squarederror"
            metric_name = "rmse"
        else:
            from xgboost import XGBClassifier as Estimator

            objective = "binary:logistic"
            metric_name = "brier"
        model = Estimator(
            **parameters,
            device="cpu",
            eval_metric="rmse" if task == "REGRESSION" else "logloss",
            n_jobs=1,
            objective=objective,
            random_state=seed,
            tree_method="hist",
            verbosity=0,
        )
    else:
        raise ValueError("family and prediction task are incompatible")

    started_elapsed = time.monotonic()
    with threadpool_limits(limits=1):
        model.fit(x_train, y_train, sample_weight=weights)
        if task == "REGRESSION":
            predictions = model.predict(x_validation)
            metric_value = float(
                np.sqrt(np.mean(np.square(predictions.astype("float64") - y_validation)))
            )
        else:
            predictions = model.predict_proba(x_validation)[:, 1]
            metric_value = float(np.mean(np.square(predictions - y_validation)))
    if not np.isfinite(predictions).all() or not math.isfinite(metric_value):
        raise ValueError("model produced a nonfinite validation score")
    state = _scikit_state(model, family, x_train.shape[1])
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_memory_bytes = int(peak_rss if sys.platform == "darwin" else peak_rss * 1024)
    return {
        "status": "OK",
        "model_state": _finite(state),
        "validation_predictions": _finite(predictions),
        "validation_metric_name": metric_name,
        "validation_metric_value": metric_value,
        "resource_usage": {
            "elapsed_seconds": max(0, int(math.ceil(time.monotonic() - started_elapsed))),
            "cpu_seconds": max(0, int(math.ceil(time.process_time()))),
            "peak_memory_bytes": max(0, peak_memory_bytes),
            "artifact_bytes": 0,
        },
    }


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    request_path = Path(sys.argv[1])
    response_path = Path(sys.argv[2])
    sys.addaudithook(_deny_external_capabilities)
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        result = _fit(request)
    except BaseException as exc:
        result = {
            "status": "FAILED",
            "reason_code": "TRAINING_FAILED",
            "reason": f"{type(exc).__name__}: {str(exc)[:500]}",
            "resource_usage": {
                "elapsed_seconds": 0,
                "cpu_seconds": max(0, int(math.ceil(time.process_time()))),
                "peak_memory_bytes": max(
                    0,
                    int(
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                        * (1 if sys.platform == "darwin" else 1024)
                    ),
                ),
                "artifact_bytes": 0,
            },
        }
    temporary_path = response_path.with_suffix(".tmp")
    with temporary_path.open("xb") as handle:
        handle.write(
            json.dumps(
                result,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, response_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
