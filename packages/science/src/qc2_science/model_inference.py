"""Exact-artifact, data-only QC2 model inference.

Inference accepts one pinned ModelManifest and its one-file safe JSON artifact.
It never discovers artifacts, trains models, or imports serialization/model
libraries. The small arithmetic evaluator runs in a resource-limited worker.
"""

from __future__ import annotations

import decimal as decimal_runtime
import hashlib
import platform
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

from qc2_contracts.runtime import (
    canonical_json_bytes,
    new_uuidv7,
    parse_json_strict,
    validate_contract,
    verify_content_hash,
)

_WORKER_SCRIPT = Path(__file__).with_name("model_inference_worker.py")
SAFE_FORMAT = "qc2_safe_linear_json_v1"
ARTIFACT_SCHEMA = "qc2.safe_linear_model.v1"
ALGORITHM = "qc2_safe_linear_heads"
ALGORITHM_VERSION = "1.0"
MAX_ARTIFACT_BYTES = 1_048_576
MAX_FEATURES = 256
MAX_HEADS = 32
MAX_PROBES = 32
WORKER_CPU_SECONDS = 2
WORKER_MEMORY_BYTES = 256 * 1024 * 1024
WORKER_TIMEOUT_SECONDS = 3.0
_MAX_REQUEST_BYTES = 2_200_000
_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]{0,31})(?:\.[0-9]{1,12})?$")
_PROBABILITY_KINDS = frozenset({"PROBABILITY", "CONTINUATION", "FAILURE"})
_LINEAR_KINDS = frozenset(
    {"EXPECTED_MFE", "EXPECTED_MAE", "TIME_TO_EXPANSION"}
)
_OPERATOR_FOR_KIND = {
    **{kind: "LOGISTIC_REGRESSION" for kind in _PROBABILITY_KINDS},
    **{kind: "LINEAR_REGRESSION" for kind in _LINEAR_KINDS},
}
_OUTPUT_UNITS = {
    "PROBABILITY": "probability",
    "CONTINUATION": "probability",
    "FAILURE": "probability",
    "EXPECTED_MFE": "fraction",
    "EXPECTED_MAE": "fraction",
    "TIME_TO_EXPANSION": "sessions",
    "SCORE": "score",
}
_RESOURCE_CONSTRAINT = (
    "qc2_safe_linear_json_v1:max_artifact_bytes=1048576,"
    "max_features=256,max_heads=32,cpu_seconds=2,memory_bytes=268435456"
)
_REQUIRED_RESOURCE_CONSTRAINTS = frozenset(
    {_RESOURCE_CONSTRAINT, "network_access=none", "training_access=none"}
)
_MODEL_SCHEMA = "qc2.models_prediction.ModelManifest.v1"
_ARTIFACT_MANIFEST_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"
_FEATURE_REGISTRY_SCHEMA = "qc2.scientific_definitions.FeatureRegistry.v1"
_FEATURE_DEFINITION_SCHEMA = "qc2.scientific_definitions.FeatureDefinition.v1"
_FEATURE_SNAPSHOT_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
_LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
_HEAD_SCHEMA = "qc2.models_prediction.ModelHeadDefinition.v1"
_HEAD_OUTPUT_SCHEMA = "qc2.models_prediction.ModelHeadOutput.v1"
_POINTER_SCHEMA = "qc2.governance_owner.ChampionPointer.v1"


class InferenceError(ValueError):
    """The requested exact model inference cannot be completed safely."""


class ProbeMismatch(InferenceError):
    """A fixed model probe did not reproduce its registered expected output."""


@dataclass(frozen=True, slots=True)
class SafeArtifactHead:
    head_name: str
    operator: str


@dataclass(frozen=True, slots=True)
class LoadedModel:
    """Immutable, verified identity and bytes of one exact safe model artifact."""

    model_id: str
    model_content_hash: str
    model_created_at: str
    artifact_manifest_id: str
    artifact_manifest_hash: str
    artifact_hash: str
    artifact_bytes: bytes
    artifact_json: str
    evidence_class: str
    environment_namespace: str
    feature_registry_id: str
    feature_registry_hash: str
    registry_feature_ids: tuple[str, ...]
    ordered_feature_ids: tuple[str, ...]
    feature_units: tuple[tuple[str, str, int], ...]
    training_cutoff: str
    package_lock_hash: str
    environment_fingerprint: str
    heads: tuple[SafeArtifactHead, ...]
    target_label_refs: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class InferenceResult:
    head_outputs: tuple[dict[str, Any], ...]
    receipt: dict[str, Any]


def compute_environment_fingerprint(package_lock_hash: str) -> str:
    """Fingerprint the exact lock and current interpreter/platform contract."""
    if not isinstance(package_lock_hash, str) or not _SHA256.fullmatch(package_lock_hash):
        raise InferenceError("package_lock_hash must be a lowercase SHA-256")
    fingerprint = {
        "safe_format": SAFE_FORMAT,
        "package_lock_hash": package_lock_hash,
        "python_implementation": platform.python_implementation(),
        "python_version": list(sys.version_info[:3]),
        "python_cache_tag": sys.implementation.cache_tag or "",
        "python_platform": sys.platform,
        "decimal_version": decimal_runtime.__version__,
        "libmpdec_version": getattr(decimal_runtime, "__libmpdec_version__", None),
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "platform_processor": platform.processor(),
    }
    return hashlib.sha256(canonical_json_bytes(fingerprint)).hexdigest()


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _contract(name: str, value: Mapping[str, Any], *, content_addressed: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InferenceError(f"{name} must be a contract object")
    try:
        payload = _thaw_json(value)
        validate_contract(name, payload)
        if content_addressed:
            verify_content_hash(name, payload)
    except (TypeError, ValueError, KeyError) as exc:
        raise InferenceError(f"invalid {name}: {exc}") from exc
    return payload


def _reference(
    reference: Mapping[str, Any], schema_name: str, target_id: str, content_hash: str
) -> bool:
    return (
        isinstance(reference, Mapping)
        and reference.get("target_schema_name") == schema_name
        and reference.get("target_id") == target_id
        and reference.get("content_hash") == content_hash
    )


def _parse_instant(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InferenceError(f"{field_name} must be a UTC instant ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InferenceError(f"{field_name} is not a valid UTC instant") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise InferenceError(f"{field_name} must be UTC")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _decimal_text(value: Any, field_name: str) -> Decimal:
    if (
        not isinstance(value, str)
        or len(value) > 48
        or not _DECIMAL.fullmatch(value)
    ):
        raise InferenceError(f"{field_name} must be a bounded decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise InferenceError(f"{field_name} is not a decimal") from exc
    if not result.is_finite():
        raise InferenceError(f"{field_name} must be finite")
    return result


def _parse_artifact(artifact_bytes: bytes) -> tuple[str, dict[str, Any]]:
    if not isinstance(artifact_bytes, bytes):
        raise InferenceError("artifact bytes must be an immutable bytes value")
    if not artifact_bytes or len(artifact_bytes) > MAX_ARTIFACT_BYTES:
        raise InferenceError("safe model artifact exceeds the 1 MiB limit")
    try:
        text = artifact_bytes.decode("utf-8")
        artifact = parse_json_strict(text)
        canonical = canonical_json_bytes(artifact)
    except (UnicodeDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise InferenceError(f"safe model artifact is not strict canonical JSON: {exc}") from exc
    if canonical != artifact_bytes:
        raise InferenceError("safe model artifact JSON is not canonical")
    if not isinstance(artifact, dict) or set(artifact) != {
        "schema_name",
        "schema_version",
        "ordered_feature_ids",
        "heads",
    }:
        raise InferenceError("safe model artifact has an unknown shape")
    if (
        artifact["schema_name"] != ARTIFACT_SCHEMA
        or artifact["schema_version"] != "1.0"
    ):
        raise InferenceError("safe model artifact schema/version is unsupported")
    feature_ids = artifact["ordered_feature_ids"]
    if (
        not isinstance(feature_ids, list)
        or not 1 <= len(feature_ids) <= MAX_FEATURES
        or any(not isinstance(item, str) or not _SLUG.fullmatch(item) for item in feature_ids)
        or len(feature_ids) != len(set(feature_ids))
    ):
        raise InferenceError("safe model artifact has invalid ordered feature IDs")
    raw_heads = artifact["heads"]
    if not isinstance(raw_heads, list) or not 1 <= len(raw_heads) <= MAX_HEADS:
        raise InferenceError("safe model artifact must contain 1 to 32 heads")
    names: set[str] = set()
    for head in raw_heads:
        if not isinstance(head, dict) or set(head) != {
            "head_name",
            "operator",
            "intercept",
            "coefficients",
        }:
            raise InferenceError("safe model artifact contains an unknown head shape")
        name = head["head_name"]
        if not isinstance(name, str) or not _SLUG.fullmatch(name) or name in names:
            raise InferenceError("safe model artifact contains a duplicate/invalid head name")
        if head["operator"] not in {"LINEAR_REGRESSION", "LOGISTIC_REGRESSION"}:
            raise InferenceError("safe model artifact contains an unsupported operator")
        parameters = [head["intercept"], *head["coefficients"]] if isinstance(
            head["coefficients"], list
        ) else []
        if len(parameters) != len(feature_ids) + 1:
            raise InferenceError("model coefficient count does not match feature order")
        for parameter in parameters:
            _decimal_text(parameter, "model parameter")
            if (
                not isinstance(parameter, str)
                or "." not in parameter
                or len(parameter.partition(".")[2]) != 12
                or (parameter.startswith("-") and Decimal(parameter) == 0)
            ):
                raise InferenceError(
                    "model parameters must use non-negative-zero 12-place decimal strings"
                )
        names.add(name)
    return text, artifact


def _validate_isolated_artifact(artifact_json: str) -> tuple[tuple[str, ...], tuple[SafeArtifactHead, ...]]:
    response = _run_isolated_worker(
        {"mode": "validate", "artifact_json": artifact_json}
    )
    feature_ids = response.get("ordered_feature_ids")
    raw_heads = response.get("heads")
    if not isinstance(feature_ids, list) or not isinstance(raw_heads, list):
        raise InferenceError("isolated loader returned an invalid model description")
    try:
        heads = tuple(
            SafeArtifactHead(item["head_name"], item["operator"])
            for item in raw_heads
            if isinstance(item, dict)
            and set(item) == {"head_name", "operator", "intercept", "coefficients"}
        )
    except (KeyError, TypeError) as exc:
        raise InferenceError("isolated loader returned an invalid head description") from exc
    if len(heads) != len(raw_heads) or not all(
        isinstance(item, str) for item in feature_ids
    ):
        raise InferenceError("isolated loader returned malformed model metadata")
    return tuple(feature_ids), heads


def _run_isolated_worker(request: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = canonical_json_bytes(request)
    except (TypeError, ValueError) as exc:
        raise InferenceError(f"cannot serialize isolated inference request: {exc}") from exc
    if len(raw) > _MAX_REQUEST_BYTES:
        raise InferenceError("isolated inference request exceeds the 2.2 MB limit")
    command = [sys.executable, "-I", "-S", str(_WORKER_SCRIPT)]
    try:
        completed = subprocess.run(
            command,
            input=raw,
            capture_output=True,
            check=False,
            close_fds=True,
            cwd="/",
            env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            timeout=WORKER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise InferenceError("isolated inference worker timed out") from exc
    except OSError as exc:
        raise InferenceError("isolated inference worker could not be started") from exc
    if completed.returncode != 0:
        raise InferenceError("isolated inference worker exited unsuccessfully")
    try:
        response = parse_json_strict(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise InferenceError("isolated inference worker returned invalid JSON") from exc
    if not isinstance(response, dict):
        raise InferenceError("isolated inference worker returned a non-object response")
    if response.get("ok") is not True:
        code = response.get("code")
        raise InferenceError(
            f"isolated inference worker rejected the request: {code if isinstance(code, str) else 'INVALID_RESPONSE'}"
        )
    return response


def load_exact_model(
    model_manifest: Mapping[str, Any],
    artifact_manifest: Mapping[str, Any],
    feature_registry: Mapping[str, Any],
    feature_definitions: Sequence[Mapping[str, Any]],
    artifact_bytes: bytes,
    *,
    expected_package_lock_hash: str,
) -> LoadedModel:
    """Verify and isolate-load one exact ModelManifest/ArtifactManifest pair."""
    model = _contract("ModelManifest", model_manifest, content_addressed=True)
    artifacts = _contract("ArtifactManifest", artifact_manifest, content_addressed=True)
    registry = _contract("FeatureRegistry", feature_registry, content_addressed=True)
    if model["safe_format"] not in {SAFE_FORMAT}:
        raise InferenceError("model safe_format is not allowlisted")
    if model["algorithm"] != ALGORITHM or model["algorithm_version"] != ALGORITHM_VERSION:
        raise InferenceError("model algorithm/version is not supported by this inference contract")
    if model["lifecycle_state"] in {"REJECTED", "RETIRED"}:
        raise InferenceError("rejected or retired model artifacts cannot be inferred")
    if (
        not isinstance(expected_package_lock_hash, str)
        or not _SHA256.fullmatch(expected_package_lock_hash)
        or model["package_lock_hash"] != expected_package_lock_hash
    ):
        raise InferenceError("model package lock does not match the qualified runtime lock")
    actual_environment_fingerprint = compute_environment_fingerprint(
        expected_package_lock_hash
    )
    if model["environment_fingerprint"] != actual_environment_fingerprint:
        raise InferenceError("model environment fingerprint does not match this runtime")
    if not _REQUIRED_RESOURCE_CONSTRAINTS <= set(model["resource_constraints"]):
        raise InferenceError("model manifest omits required safe inference resource constraints")
    if not _reference(
        model["artifact_manifest_ref"],
        _ARTIFACT_MANIFEST_SCHEMA,
        artifacts["id"],
        artifacts["content_hash"],
    ):
        raise InferenceError("model manifest does not bind this exact ArtifactManifest")
    if not _reference(
        model["feature_registry_ref"],
        _FEATURE_REGISTRY_SCHEMA,
        registry["id"],
        registry["content_hash"],
    ):
        raise InferenceError("model manifest does not bind this exact FeatureRegistry")
    if (
        artifacts["evidence_class"] != model["evidence_class"]
        or artifacts["environment_namespace"] != model["environment_namespace"]
        or registry["evidence_class"] != model["evidence_class"]
        or registry["environment_namespace"] != model["environment_namespace"]
    ):
        raise InferenceError("model, artifact, and feature registry contexts do not match")

    definitions: dict[str, dict[str, Any]] = {}
    for raw_definition in feature_definitions:
        definition = _contract(
            "FeatureDefinition", raw_definition, content_addressed=True
        )
        if (
            definition["evidence_class"] != model["evidence_class"]
            or definition["environment_namespace"] != model["environment_namespace"]
        ):
            raise InferenceError("feature definition context does not match the model")
        stable_key = definition["stable_key"]
        if stable_key in definitions:
            raise InferenceError("feature definitions contain duplicate stable keys")
        definitions[stable_key] = definition
    registry_ids = registry["ordered_feature_ids"]
    registry_refs = registry["definition_refs"]
    expected_definition_keys = {
        (
            item["target_schema_name"],
            item["target_id"],
            item["content_hash"],
        )
        for item in registry_refs
    }
    actual_definition_keys = {
        (_FEATURE_DEFINITION_SCHEMA, definition["id"], definition["content_hash"])
        for definition in definitions.values()
    }
    if (
        len(registry_ids) != len(set(registry_ids))
        or set(registry_ids) != set(definitions)
        or expected_definition_keys != actual_definition_keys
        or len(registry_refs) != len(definitions)
    ):
        raise InferenceError("FeatureRegistry and FeatureDefinition inventory do not match")
    ordered_feature_ids = model["ordered_feature_ids"]
    if (
        not isinstance(ordered_feature_ids, list)
        or not ordered_feature_ids
        or len(ordered_feature_ids) > MAX_FEATURES
        or len(ordered_feature_ids) != len(set(ordered_feature_ids))
        or not set(ordered_feature_ids) <= set(registry_ids)
    ):
        raise InferenceError("ModelManifest has invalid or unregistered feature order")
    feature_units: list[tuple[str, str, int]] = []
    for feature_id in ordered_feature_ids:
        definition = definitions[feature_id]
        if definition["output_dtype"] != "DECIMAL":
            raise InferenceError("safe linear inference supports only decimal features")
        feature_units.append(
            (feature_id, definition["output_unit"], definition["precision"])
        )

    if not isinstance(artifact_bytes, bytes) or not artifact_bytes:
        raise InferenceError("artifact bytes must be supplied exactly")
    if len(artifact_bytes) > MAX_ARTIFACT_BYTES:
        raise InferenceError("safe model artifact exceeds the 1 MiB limit")
    artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
    inventory = artifacts["files"]
    if len(inventory) != 1:
        raise InferenceError("safe inference requires exactly one JSON artifact file")
    file_record = inventory[0]
    if (
        file_record["relative_path"] != "model/model.json"
        or file_record["length_bytes"] != len(artifact_bytes)
        or file_record["sha256"] != artifact_hash
        or file_record["media_type"] != "application/json"
        or file_record["schema_name"] != ARTIFACT_SCHEMA
        or file_record["schema_version"] != "1.0"
    ):
        raise InferenceError("artifact bytes do not match the exact manifest inventory")
    artifact_json, artifact = _parse_artifact(artifact_bytes)
    if artifact["ordered_feature_ids"] != ordered_feature_ids:
        raise InferenceError("artifact feature order differs from ModelManifest")
    isolated_feature_ids, heads = _validate_isolated_artifact(artifact_json)
    if tuple(artifact["ordered_feature_ids"]) != isolated_feature_ids:
        raise InferenceError("isolated loader disagrees with the declared feature order")
    if tuple(
        (item["head_name"], item["operator"]) for item in artifact["heads"]
    ) != tuple((head.head_name, head.operator) for head in heads):
        raise InferenceError("isolated loader disagrees with artifact head metadata")

    return LoadedModel(
        model_id=model["id"],
        model_content_hash=model["content_hash"],
        model_created_at=model["created_at"],
        artifact_manifest_id=artifacts["id"],
        artifact_manifest_hash=artifacts["content_hash"],
        artifact_hash=artifact_hash,
        artifact_bytes=artifact_bytes,
        artifact_json=artifact_json,
        evidence_class=model["evidence_class"],
        environment_namespace=model["environment_namespace"],
        feature_registry_id=registry["id"],
        feature_registry_hash=registry["content_hash"],
        registry_feature_ids=tuple(registry_ids),
        ordered_feature_ids=tuple(ordered_feature_ids),
        feature_units=tuple(feature_units),
        training_cutoff=model["training_cutoff"],
        package_lock_hash=model["package_lock_hash"],
        environment_fingerprint=actual_environment_fingerprint,
        heads=heads,
        target_label_refs=tuple(
            (
                item["target_schema_name"],
                item["target_id"],
                item["content_hash"],
            )
            for item in model["target_label_refs"]
        ),
    )


def _validate_feature_snapshot(
    snapshot: Mapping[str, Any], model: LoadedModel, evaluated_at: datetime
) -> tuple[list[list[str]], list[str]]:
    feature_snapshot = _contract(
        "FeatureSnapshot", snapshot, content_addressed=True
    )
    if (
        feature_snapshot["registry_ref"]["target_schema_name"] != _FEATURE_REGISTRY_SCHEMA
        or feature_snapshot["registry_ref"]["target_id"] != model.feature_registry_id
        or feature_snapshot["registry_ref"]["content_hash"] != model.feature_registry_hash
    ):
        raise InferenceError("FeatureSnapshot does not use the model's exact FeatureRegistry")
    if (
        feature_snapshot["evidence_class"] != model.evidence_class
        or feature_snapshot["environment_namespace"] != model.environment_namespace
    ):
        raise InferenceError("FeatureSnapshot context does not match the model")
    cutoff = _parse_instant(feature_snapshot["decision_cutoff"], "FeatureSnapshot.decision_cutoff")
    created_at = _parse_instant(feature_snapshot["created_at"], "FeatureSnapshot.created_at")
    if cutoff > evaluated_at or created_at > evaluated_at:
        raise InferenceError("FeatureSnapshot is from after the inference time")
    if _parse_instant(model.training_cutoff, "ModelManifest.training_cutoff") > cutoff:
        raise InferenceError("model training cutoff is after the inference feature cutoff")
    rows = feature_snapshot["feature_values"]
    if [row["feature_id"] for row in rows] != list(model.registry_feature_ids):
        raise InferenceError("FeatureSnapshot order differs from its exact registry")
    rows_by_id = {row["feature_id"]: row for row in rows}
    definitions = {feature_id: (unit, precision) for feature_id, unit, precision in model.feature_units}
    vector: list[list[str]] = []
    missing: list[str] = []
    for feature_id in model.ordered_feature_ids:
        row = rows_by_id[feature_id]
        expected_unit, precision = definitions[feature_id]
        if row["unit"] != expected_unit or row["output_dtype"] != "DECIMAL":
            raise InferenceError(f"FeatureSnapshot unit/type mismatch for {feature_id}")
        if "missing_reason" in row:
            missing.append(f"{feature_id}:{row['missing_reason']}")
            continue
        value = row.get("value")
        number = _decimal_text(value, f"FeatureSnapshot.{feature_id}")
        fractional_places = len(value.partition(".")[2])
        if fractional_places > precision:
            raise InferenceError(f"FeatureSnapshot precision exceeds registry for {feature_id}")
        vector.append([feature_id, format(number, "f")])
    if missing:
        return [], missing
    return vector, []


def _normalize_probe(
    probe: Mapping[str, Any],
    *,
    feature_ids: tuple[str, ...],
    available_head_precisions: Mapping[str, int],
) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(probe, Mapping) or set(probe) != {
        "probe_id",
        "feature_values",
        "expected_outputs",
    }:
        raise InferenceError("each fixed probe must declare ID, ordered values, and expected outputs")
    probe_id = probe["probe_id"]
    if not isinstance(probe_id, str) or not _SLUG.fullmatch(probe_id):
        raise InferenceError("probe ID must be a stable slug")
    feature_values = probe["feature_values"]
    if not isinstance(feature_values, Mapping) or tuple(feature_values) != feature_ids:
        raise InferenceError("probe feature order must exactly match ModelManifest")
    normalized_values: list[list[str]] = []
    for feature_id in feature_ids:
        value = feature_values[feature_id]
        number = _decimal_text(value, f"probe.{feature_id}")
        normalized_values.append([feature_id, format(number, "f")])
    expected = probe["expected_outputs"]
    if (
        not isinstance(expected, Mapping)
        or set(expected) != set(available_head_precisions)
    ):
        raise InferenceError("probe expected outputs must exactly cover available logical heads")
    normalized_expected: dict[str, str] = {}
    for head_name, precision in available_head_precisions.items():
        value = expected[head_name]
        if (
            not isinstance(value, str)
            or "." not in value
            or len(value.partition(".")[2]) != precision
        ):
            raise InferenceError(f"probe expected output for {head_name} has wrong precision")
        number = _decimal_text(value, f"probe expected output for {head_name}")
        if value != f"{number:.{precision}f}":
            raise InferenceError(
                f"probe expected output for {head_name} is not canonical"
            )
        normalized_expected[head_name] = value
    return (
        {"probe_id": probe_id, "feature_values": normalized_values},
        normalized_expected,
    )


def _format_output(value: str, precision: int) -> tuple[Decimal, str]:
    number = _decimal_text(value, "isolated model output")
    quantum = Decimal(1).scaleb(-precision)
    try:
        rounded = number.quantize(quantum, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:
        raise InferenceError("model output cannot be rounded to registered precision") from exc
    return rounded, f"{rounded:.{precision}f}"


def _output_domain_error(
    output_kind: str, value: Decimal, horizon_sessions: int
) -> str | None:
    if output_kind in _PROBABILITY_KINDS and not Decimal(0) <= value <= Decimal(1):
        return "INVALID_PROBABILITY"
    if output_kind == "EXPECTED_MFE" and value < 0:
        return "INVALID_EXPECTED_MFE"
    if output_kind == "EXPECTED_MAE" and value > 0:
        return "INVALID_EXPECTED_MAE"
    if output_kind == "TIME_TO_EXPANSION" and not (
        Decimal(0) < value <= Decimal(horizon_sessions)
    ):
        return "INVALID_TIME_TO_EXPANSION"
    return None


def _make_output(
    head: Mapping[str, Any],
    *,
    model: LoadedModel,
    feature_snapshot: Mapping[str, Any],
    evaluated_at: str,
    value: str | None,
    availability: str,
    reason_code: str | None,
) -> dict[str, Any]:
    payload = {
        "schema_name": _HEAD_OUTPUT_SCHEMA,
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": evaluated_at,
        "owning_authority": "inference",
        "evidence_class": model.evidence_class,
        "environment_namespace": model.environment_namespace,
        "source_refs": [
            {
                "target_schema_name": _MODEL_SCHEMA,
                "target_id": model.model_id,
                "content_hash": model.model_content_hash,
            },
            {
                "target_schema_name": _FEATURE_SNAPSHOT_SCHEMA,
                "target_id": feature_snapshot["id"],
                "content_hash": feature_snapshot["content_hash"],
            },
        ],
        "head_ref": {
            "target_schema_name": _HEAD_SCHEMA,
            "target_id": head["id"],
        },
        "instrument_ref": dict(feature_snapshot["instrument_ref"]),
        "session_id": feature_snapshot["session_id"],
        "output_value": value,
        "output_unit": _OUTPUT_UNITS[head["output_kind"]],
        "availability": availability,
        "reason_code": reason_code,
    }
    try:
        validate_contract("ModelHeadOutput", payload)
    except (TypeError, ValueError) as exc:
        raise InferenceError(f"generated ModelHeadOutput is invalid: {exc}") from exc
    return payload


def infer_exact_artifact(
    model: LoadedModel,
    *,
    pinned_pointer: Mapping[str, Any],
    primary_head: Mapping[str, Any],
    optional_heads: Sequence[Mapping[str, Any]],
    label_definitions: Sequence[Mapping[str, Any]],
    feature_snapshot: Mapping[str, Any],
    probe_set: Sequence[Mapping[str, Any]],
    evaluated_at: str,
) -> InferenceResult:
    """Infer typed logical heads from the exact loaded artifact and frozen inputs."""
    if not isinstance(model, LoadedModel):
        raise InferenceError("inference requires a LoadedModel from load_exact_model")
    inference_time = _parse_instant(evaluated_at, "evaluated_at")
    evaluated_text = _utc_text(inference_time)
    if _parse_instant(model.model_created_at, "ModelManifest.created_at") > inference_time:
        raise InferenceError("model artifact was created after the requested inference time")
    pointer = _contract("ChampionPointer", pinned_pointer, content_addressed=False)
    if (
        pointer["model_ref"]["target_schema_name"] != _MODEL_SCHEMA
        or pointer["model_ref"]["target_id"] != model.model_id
        or pointer["model_ref"]["content_hash"] != model.model_content_hash
    ):
        raise InferenceError("pinned pointer does not select this exact ModelManifest")
    if (
        pointer["evidence_class"] != model.evidence_class
        or pointer["environment_namespace"] != model.environment_namespace
    ):
        raise InferenceError("pinned pointer context does not match the loaded model")
    if _parse_instant(pointer["created_at"], "ChampionPointer.created_at") > inference_time:
        raise InferenceError("pinned pointer was created after the inference time")
    if _parse_instant(
        pointer["transitioned_at"], "ChampionPointer.transitioned_at"
    ) > inference_time:
        raise InferenceError("pinned pointer was transitioned after the inference time")
    generation = pointer["generation"]

    validated_labels: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_label in label_definitions:
        label = _contract("LabelDefinition", raw_label, content_addressed=True)
        key = (_LABEL_SCHEMA, label["id"])
        if key in validated_labels:
            raise InferenceError("label definitions contain duplicate identities")
        if (
            label["evidence_class"] != model.evidence_class
            or label["environment_namespace"] != model.environment_namespace
        ):
            raise InferenceError("label definition context does not match the model")
        if (
            _LABEL_SCHEMA,
            label["id"],
            label["content_hash"],
        ) not in model.target_label_refs:
            raise InferenceError("label definition is not pinned by the exact ModelManifest")
        validated_labels[key] = label

    if not isinstance(optional_heads, Sequence) or isinstance(optional_heads, (str, bytes)):
        raise InferenceError("optional_heads must be an explicit ordered sequence")
    if len(optional_heads) > MAX_HEADS - 1:
        raise InferenceError("too many optional logical heads")
    head_payloads: list[tuple[dict[str, Any], dict[str, Any] | None, bool]] = []
    names: set[str] = set()
    ids: set[str] = set()
    all_heads = [(primary_head, True), *((item, False) for item in optional_heads)]
    for raw_head, is_primary in all_heads:
        if not isinstance(raw_head, Mapping):
            raise InferenceError("model head definitions must be contract objects")
        head = _contract("ModelHeadDefinition", raw_head, content_addressed=False)
        if (
            head["model_ref"]["target_schema_name"] != _MODEL_SCHEMA
            or head["model_ref"]["target_id"] != model.model_id
            or head["model_ref"]["content_hash"] != model.model_content_hash
        ):
            raise InferenceError("model head is not bound to the loaded ModelManifest")
        if (
            head["evidence_class"] != model.evidence_class
            or head["environment_namespace"] != model.environment_namespace
            or head["label_ref"]["target_schema_name"] != _LABEL_SCHEMA
        ):
            raise InferenceError("model head context or label schema is incompatible")
        label_reference = (
            head["label_ref"]["target_schema_name"],
            head["label_ref"]["target_id"],
            head["label_ref"]["content_hash"],
        )
        if label_reference not in model.target_label_refs:
            raise InferenceError("model head label is not pinned by the exact ModelManifest")
        if head["head_name"] in names or head["id"] in ids:
            raise InferenceError("logical model head definitions contain duplicates")
        names.add(head["head_name"])
        ids.add(head["id"])
        label = validated_labels.get((_LABEL_SCHEMA, head["label_ref"]["target_id"]))
        if label is not None and label["content_hash"] != head["label_ref"]["content_hash"]:
            raise InferenceError("model head label hash does not match its LabelDefinition")
        if is_primary:
            if (
                head["availability"] != "AVAILABLE"
                or head["output_kind"] != "PROBABILITY"
                or label is None
                or label["target_event"] != "EXPANSION_RUNNER"
            ):
                raise InferenceError(
                    "the primary head must be an available Expansion Runner probability"
                )
        elif head["availability"] == "AVAILABLE":
            if label is None:
                raise InferenceError("an available optional head requires its exact LabelDefinition")
            if head["output_kind"] == "SCORE":
                raise InferenceError(
                    "QuantraScore is synthesized separately, not inferred as a model head"
                )
        elif head["availability"] == "UNAVAILABLE_LABEL":
            pass
        elif head["availability"] not in {"UNAVAILABLE_MODEL", "INVALID"}:
            raise InferenceError("optional head has an unsupported availability state")
        if head["output_kind"] == "SCORE":
            raise InferenceError(
                "QuantraScore is synthesized separately, not inferred as a model head"
            )
        if label is not None and label["horizon_sessions"] != head["horizon_sessions"]:
            raise InferenceError("model head horizon differs from its exact LabelDefinition")
        if label is not None:
            allowed_targets = {
                "PROBABILITY": {"EXPANSION_RUNNER", "SESSION_MONSTER"},
                "CONTINUATION": {"CONTINUATION"},
                "FAILURE": {"FAILURE"},
                "TIME_TO_EXPANSION": {"TIME_TO_EXPANSION"},
                "EXPECTED_MFE": {"EXPANSION_RUNNER", "SESSION_MONSTER"},
                "EXPECTED_MAE": {"EXPANSION_RUNNER", "SESSION_MONSTER"},
            }
            if label["target_event"] not in allowed_targets[head["output_kind"]]:
                raise InferenceError("model head kind is incompatible with its exact label target")
        head_payloads.append((head, label, is_primary))

    available_heads = [
        head for head, _, _ in head_payloads if head["availability"] == "AVAILABLE"
    ]
    expected_artifact_names = {head["head_name"] for head in available_heads}
    if expected_artifact_names != {head.head_name for head in model.heads}:
        raise InferenceError(
            "available logical heads must exactly cover the loaded artifact's head set"
        )
    artifact_heads = {head.head_name: head.operator for head in model.heads}
    for head in available_heads:
        expected_operator = _OPERATOR_FOR_KIND.get(head["output_kind"])
        if expected_operator is None:
            raise InferenceError(
                f"available head kind {head['output_kind']} is unsupported"
            )
        if artifact_heads.get(head["head_name"]) != expected_operator:
            raise InferenceError("model head kind/operator does not match the safe artifact")

    snapshot = _contract("FeatureSnapshot", feature_snapshot, content_addressed=True)
    vector, missing_features = _validate_feature_snapshot(
        snapshot, model, inference_time
    )
    if (
        snapshot["instrument_ref"]["target_schema_name"]
        != "qc2.identity_market.Instrument.v1"
    ):
        raise InferenceError("FeatureSnapshot instrument reference is invalid")

    if not isinstance(probe_set, Sequence) or isinstance(probe_set, (str, bytes)):
        raise InferenceError("probe_set must be an explicit ordered sequence")
    if not 1 <= len(probe_set) <= MAX_PROBES:
        raise InferenceError("probe_set must contain 1 to 32 fixed probes")
    precision_by_name = {
        head["head_name"]: head["output_precision"] for head in available_heads
    }
    normalized_probes: list[dict[str, Any]] = []
    expected_probe_outputs: list[dict[str, str]] = []
    seen_probe_ids: set[str] = set()
    for probe in probe_set:
        normalized, expected = _normalize_probe(
            probe,
            feature_ids=model.ordered_feature_ids,
            available_head_precisions=precision_by_name,
        )
        if normalized["probe_id"] in seen_probe_ids:
            raise InferenceError("probe IDs must be unique")
        seen_probe_ids.add(normalized["probe_id"])
        normalized_probes.append(normalized)
        expected_probe_outputs.append(expected)

    request = {
        "mode": "infer",
        "artifact_json": model.artifact_json,
        "requested_head_names": [
            head["head_name"] for head in available_heads
        ],
        "actual_vector": vector if not missing_features else None,
        "probe_vectors": normalized_probes,
    }
    first = _run_isolated_worker(request)
    second = _run_isolated_worker(request)
    if first.get("actual") != second.get("actual") or first.get("probes") != second.get("probes"):
        raise InferenceError("isolated model outputs are not deterministic")
    raw_actual = first.get("actual")
    raw_probes = first.get("probes")
    if raw_actual is not None and (
        not isinstance(raw_actual, dict)
        or set(raw_actual) != set(precision_by_name)
    ):
        raise InferenceError("isolated worker returned an invalid actual output set")
    if not isinstance(raw_probes, list) or len(raw_probes) != len(normalized_probes):
        raise InferenceError("isolated worker returned an invalid probe output set")
    normalized_probe_values: list[dict[str, str]] = []
    for raw_probe, normalized_probe, expected in zip(
        raw_probes, normalized_probes, expected_probe_outputs, strict=True
    ):
        if (
            not isinstance(raw_probe, dict)
            or raw_probe.get("probe_id") != normalized_probe["probe_id"]
            or not isinstance(raw_probe.get("outputs"), dict)
            or set(raw_probe["outputs"]) != set(precision_by_name)
        ):
            raise InferenceError("isolated worker returned a malformed probe result")
        formatted_outputs: dict[str, str] = {}
        for head in available_heads:
            name = head["head_name"]
            value, serialized = _format_output(
                raw_probe["outputs"][name], head["output_precision"]
            )
            domain_error = _output_domain_error(
                head["output_kind"], value, head["horizon_sessions"]
            )
            if domain_error is not None:
                raise ProbeMismatch(
                    f"probe {normalized_probe['probe_id']} produced {domain_error}"
                )
            if serialized != expected[name]:
                raise ProbeMismatch(
                    f"probe {normalized_probe['probe_id']} output differs for {name}"
                )
            formatted_outputs[name] = serialized
        normalized_probe_values.append(formatted_outputs)

    output_payloads: list[dict[str, Any]] = []
    output_projection: list[dict[str, Any]] = []
    for head, _, is_primary in head_payloads:
        value_text: str | None = None
        availability = head["availability"]
        reason_code: str | None = None
        if availability == "UNAVAILABLE_MODEL":
            reason_code = "HEAD_UNAVAILABLE_MODEL"
        elif availability == "UNAVAILABLE_LABEL":
            reason_code = "HEAD_UNAVAILABLE_LABEL"
        elif availability == "INVALID":
            reason_code = "HEAD_DECLARED_INVALID"
        elif missing_features:
            availability = "INVALID"
            reason_code = "MISSING_REQUIRED_FEATURES:" + ",".join(missing_features)
        else:
            if raw_actual is None:
                raise InferenceError("isolated worker omitted the required actual output")
            number, serialized = _format_output(
                raw_actual[head["head_name"]], head["output_precision"]
            )
            domain_error = _output_domain_error(
                head["output_kind"], number, head["horizon_sessions"]
            )
            if domain_error is None:
                availability = "AVAILABLE"
                value_text = serialized
            else:
                availability = "INVALID"
                reason_code = domain_error
        if is_primary and availability != "AVAILABLE" and not missing_features:
            # A bad primary prediction is recorded as typed INVALID rather than
            # coerced, zero-filled, or represented as a successful probability.
            reason_code = reason_code or "PRIMARY_OUTPUT_INVALID"
        output = _make_output(
            head,
            model=model,
            feature_snapshot=snapshot,
            evaluated_at=evaluated_text,
            value=value_text,
            availability=availability,
            reason_code=reason_code,
        )
        output_payloads.append(output)
        output_projection.append(
            {
                "head_name": head["head_name"],
                "head_id": head["id"],
                "instrument_id": snapshot["instrument_ref"]["target_id"],
                "session_id": snapshot["session_id"],
                "output_value": value_text,
                "output_unit": output["output_unit"],
                "availability": availability,
                "reason_code": reason_code,
            }
        )

    probe_set_hash = hashlib.sha256(
        canonical_json_bytes(
            {
                "model_id": model.model_id,
                "model_content_hash": model.model_content_hash,
                "artifact_hash": model.artifact_hash,
                "environment_fingerprint": model.environment_fingerprint,
                "ordered_feature_ids": list(model.ordered_feature_ids),
                "requested_head_names": [
                    head["head_name"] for head in available_heads
                ],
                "probes": [
                    {
                        **probe,
                        "expected_outputs": expected,
                    }
                    for probe, expected in zip(
                        normalized_probes, expected_probe_outputs, strict=True
                    )
                ],
            }
        )
    ).hexdigest()
    output_hash = hashlib.sha256(canonical_json_bytes(output_projection)).hexdigest()
    receipt = {
        "schema_name": "qc2.models_prediction.InferenceReceipt.v1",
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": evaluated_text,
        "owning_authority": "inference",
        "evidence_class": model.evidence_class,
        "environment_namespace": model.environment_namespace,
        "source_refs": [
            {
                "target_schema_name": _ARTIFACT_MANIFEST_SCHEMA,
                "target_id": model.artifact_manifest_id,
                "content_hash": model.artifact_manifest_hash,
            },
            {
                "target_schema_name": _POINTER_SCHEMA,
                "target_id": pointer["id"],
            },
        ],
        "model_ref": {
            "target_schema_name": _MODEL_SCHEMA,
            "target_id": model.model_id,
            "content_hash": model.model_content_hash,
        },
        "loaded_artifact_hash": model.artifact_hash,
        "generation": generation,
        "environment_fingerprint": model.environment_fingerprint,
        "probe_set_hash": probe_set_hash,
        "output_hash": output_hash,
        "evaluated_at": evaluated_text,
        "deterministic": True,
    }
    try:
        validate_contract("InferenceReceipt", receipt)
    except (TypeError, ValueError) as exc:
        raise InferenceError(f"generated InferenceReceipt is invalid: {exc}") from exc
    return InferenceResult(tuple(output_payloads), receipt)


__all__ = [
    "ALGORITHM",
    "ALGORITHM_VERSION",
    "ARTIFACT_SCHEMA",
    "InferenceError",
    "InferenceResult",
    "LoadedModel",
    "MAX_ARTIFACT_BYTES",
    "ProbeMismatch",
    "SAFE_FORMAT",
    "SafeArtifactHead",
    "compute_environment_fingerprint",
    "infer_exact_artifact",
    "load_exact_model",
]
