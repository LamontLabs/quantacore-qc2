"""Isolated evaluator for the QC2 safe linear-model JSON format.

Only bounded declarative data is accepted. This worker does not import model
libraries, application modules, training code, persistence, or network APIs.
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Any

_MAX_REQUEST_BYTES = 2_200_000
_MAX_ARTIFACT_BYTES = 1_048_576
_MAX_FEATURES = 256
_MAX_HEADS = 32
_MAX_PROBES = 32
_MAX_VECTOR_VALUES = 48
_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]{0,31})(?:\.[0-9]{1,12})?$")
_OPERATORS = frozenset({"LINEAR_REGRESSION", "LOGISTIC_REGRESSION"})
_Q12 = Decimal("0.000000000001")
_PROBABILITY_KINDS = frozenset({"PROBABILITY", "CONTINUATION", "FAILURE"})
_LINEAR_KINDS = frozenset(
    {"EXPECTED_MFE", "EXPECTED_MAE", "TIME_TO_EXPANSION"}
)


class _WorkerFault(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _set_resource_limits() -> bool:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
        resource.setrlimit(
            resource.RLIMIT_AS,
            (256 * 1024 * 1024, 256 * 1024 * 1024),
        )
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
    except (ImportError, OSError, ValueError):
        return False
    return True


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _WorkerFault("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise _WorkerFault(f"INVALID_JSON_CONSTANT:{value}")


def _reject_float(value: str) -> None:
    raise _WorkerFault("JSON_FLOATS_NOT_ALLOWED")


def _strict_json(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except _WorkerFault:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _WorkerFault("INVALID_JSON") from exc


def _decimal(value: Any) -> Decimal:
    if (
        not isinstance(value, str)
        or len(value) > _MAX_VECTOR_VALUES
        or not _DECIMAL.fullmatch(value)
    ):
        raise _WorkerFault("INVALID_DECIMAL")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise _WorkerFault("INVALID_DECIMAL") from exc
    if not parsed.is_finite():
        raise _WorkerFault("INVALID_DECIMAL")
    return parsed


def _validate_artifact(artifact_json: Any) -> dict[str, Any]:
    if not isinstance(artifact_json, str):
        raise _WorkerFault("INVALID_ARTIFACT")
    raw = artifact_json.encode("utf-8")
    if not raw or len(raw) > _MAX_ARTIFACT_BYTES:
        raise _WorkerFault("ARTIFACT_SIZE_LIMIT")
    artifact = _strict_json(artifact_json)
    if not isinstance(artifact, dict) or set(artifact) != {
        "schema_name",
        "schema_version",
        "ordered_feature_ids",
        "heads",
    }:
        raise _WorkerFault("INVALID_ARTIFACT_SHAPE")
    if artifact["schema_name"] != "qc2.safe_linear_model.v1":
        raise _WorkerFault("UNSUPPORTED_ARTIFACT_SCHEMA")
    if artifact["schema_version"] != "1.0":
        raise _WorkerFault("UNSUPPORTED_ARTIFACT_VERSION")
    canonical = json.dumps(
        artifact,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if canonical != raw:
        raise _WorkerFault("NON_CANONICAL_ARTIFACT_JSON")

    feature_ids = artifact["ordered_feature_ids"]
    if (
        not isinstance(feature_ids, list)
        or not 1 <= len(feature_ids) <= _MAX_FEATURES
        or any(not isinstance(item, str) or not _SLUG.fullmatch(item) for item in feature_ids)
        or len(feature_ids) != len(set(feature_ids))
    ):
        raise _WorkerFault("INVALID_FEATURE_ORDER")

    raw_heads = artifact["heads"]
    if not isinstance(raw_heads, list) or not 1 <= len(raw_heads) <= _MAX_HEADS:
        raise _WorkerFault("INVALID_HEAD_SET")
    names: set[str] = set()
    heads: list[dict[str, Any]] = []
    for head in raw_heads:
        if not isinstance(head, dict) or set(head) != {
            "head_name",
            "operator",
            "intercept",
            "coefficients",
        }:
            raise _WorkerFault("INVALID_HEAD_SHAPE")
        name = head["head_name"]
        operator = head["operator"]
        if not isinstance(name, str) or not _SLUG.fullmatch(name) or name in names:
            raise _WorkerFault("INVALID_HEAD_NAME")
        if not isinstance(operator, str) or operator not in _OPERATORS:
            raise _WorkerFault("UNSUPPORTED_OPERATOR")
        coefficients = head["coefficients"]
        if not isinstance(coefficients, list) or len(coefficients) != len(feature_ids):
            raise _WorkerFault("COEFFICIENT_FEATURE_COUNT_MISMATCH")
        parameter_values = [head["intercept"], *coefficients]
        for parameter in parameter_values:
            if (
                not isinstance(parameter, str)
                or "." not in parameter
                or len(parameter.partition(".")[2]) != 12
                or (parameter.startswith("-") and _decimal(parameter) == 0)
            ):
                raise _WorkerFault("NON_CANONICAL_MODEL_PARAMETER")
        intercept = _decimal(head["intercept"])
        parsed_coefficients = [_decimal(item) for item in coefficients]
        names.add(name)
        heads.append(
            {
                "head_name": name,
                "operator": operator,
                "intercept": format(intercept, "f"),
                "coefficients": [
                    format(value, "f") for value in parsed_coefficients
                ],
            }
        )
    return {
        "schema_name": artifact["schema_name"],
        "schema_version": artifact["schema_version"],
        "ordered_feature_ids": list(feature_ids),
        "heads": heads,
    }


def _feature_vector(value: Any, ordered_feature_ids: list[str]) -> list[Decimal] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != len(ordered_feature_ids):
        raise _WorkerFault("FEATURE_VECTOR_ORDER_MISMATCH")
    names: list[str] = []
    values: list[Decimal] = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            raise _WorkerFault("INVALID_FEATURE_VECTOR")
        name, raw_value = pair
        if not isinstance(name, str):
            raise _WorkerFault("INVALID_FEATURE_VECTOR")
        names.append(name)
        values.append(_decimal(raw_value))
    if names != ordered_feature_ids:
        raise _WorkerFault("FEATURE_VECTOR_ORDER_MISMATCH")
    return values


def _head_value(head: dict[str, Any], vector: list[Decimal]) -> str:
    with localcontext() as context:
        context.prec = 64
        intercept = _decimal(head["intercept"])
        coefficients = [_decimal(item) for item in head["coefficients"]]
        score = intercept + sum(
            (coefficient * value for coefficient, value in zip(coefficients, vector, strict=True)),
            Decimal(0),
        )
        if not score.is_finite() or abs(score) > Decimal(1000):
            raise _WorkerFault("INVALID_PREDICTION_MAGNITUDE")
        if head["operator"] == "LOGISTIC_REGRESSION":
            if score >= 0:
                tail = (-score).exp()
                result = Decimal(1) / (Decimal(1) + tail)
            else:
                tail = score.exp()
                result = tail / (Decimal(1) + tail)
        elif head["operator"] == "LINEAR_REGRESSION":
            result = score
        else:
            raise _WorkerFault("UNSUPPORTED_OPERATOR")
        if not result.is_finite():
            raise _WorkerFault("NON_FINITE_OUTPUT")
        return format(result.quantize(_Q12, rounding=ROUND_HALF_EVEN), "f")


def _run(request: Any) -> dict[str, Any]:
    if not _set_resource_limits():
        return {"ok": False, "code": "RESOURCE_LIMITS_UNAVAILABLE"}
    if not isinstance(request, dict) or not isinstance(request.get("mode"), str):
        return {"ok": False, "code": "INVALID_REQUEST"}
    try:
        artifact = _validate_artifact(request.get("artifact_json"))
        if request["mode"] == "validate":
            if set(request) != {"mode", "artifact_json"}:
                raise _WorkerFault("INVALID_REQUEST")
            return {
                "ok": True,
                "ordered_feature_ids": artifact["ordered_feature_ids"],
                "heads": artifact["heads"],
            }
        if request["mode"] != "infer" or set(request) != {
            "mode",
            "artifact_json",
            "requested_head_names",
            "actual_vector",
            "probe_vectors",
        }:
            raise _WorkerFault("INVALID_REQUEST")

        requested = request["requested_head_names"]
        if (
            not isinstance(requested, list)
            or not requested
            or len(requested) > _MAX_HEADS
            or any(not isinstance(name, str) for name in requested)
            or len(requested) != len(set(requested))
        ):
            raise _WorkerFault("INVALID_HEAD_SET")
        heads_by_name = {head["head_name"]: head for head in artifact["heads"]}
        if set(requested) - set(heads_by_name):
            raise _WorkerFault("MODEL_HEAD_MISSING")

        actual = _feature_vector(request["actual_vector"], artifact["ordered_feature_ids"])
        raw_probes = request["probe_vectors"]
        if not isinstance(raw_probes, list) or not 1 <= len(raw_probes) <= _MAX_PROBES:
            raise _WorkerFault("INVALID_PROBE_SET")
        probe_ids: set[str] = set()
        probes: list[tuple[str, list[Decimal]]] = []
        for probe in raw_probes:
            if not isinstance(probe, dict) or set(probe) != {"probe_id", "feature_values"}:
                raise _WorkerFault("INVALID_PROBE")
            probe_id = probe["probe_id"]
            if (
                not isinstance(probe_id, str)
                or not _SLUG.fullmatch(probe_id)
                or probe_id in probe_ids
            ):
                raise _WorkerFault("INVALID_PROBE_ID")
            vector = _feature_vector(probe["feature_values"], artifact["ordered_feature_ids"])
            if vector is None:
                raise _WorkerFault("INVALID_PROBE")
            probe_ids.add(probe_id)
            probes.append((probe_id, vector))

        def evaluate(vector: list[Decimal] | None) -> dict[str, str] | None:
            if vector is None:
                return None
            return {
                name: _head_value(heads_by_name[name], vector)
                for name in requested
            }

        return {
            "ok": True,
            "actual": evaluate(actual),
            "probes": [
                {"probe_id": probe_id, "outputs": evaluate(vector)}
                for probe_id, vector in probes
            ],
        }
    except _WorkerFault as exc:
        return {"ok": False, "code": exc.code}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
        if len(raw) > _MAX_REQUEST_BYTES:
            response = {"ok": False, "code": "REQUEST_SIZE_LIMIT"}
        else:
            try:
                request = _strict_json(raw.decode("utf-8"))
                response = _run(request)
            except (UnicodeDecodeError, _WorkerFault) as exc:
                code = exc.code if isinstance(exc, _WorkerFault) else "INVALID_UTF8"
                response = {"ok": False, "code": code}
    except BaseException:
        response = {"ok": False, "code": "WORKER_FAILURE"}
    sys.stdout.write(json.dumps(response, separators=(",", ":"), sort_keys=True))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
