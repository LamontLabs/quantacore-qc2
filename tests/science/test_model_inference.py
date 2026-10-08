from __future__ import annotations

import copy
import hashlib
import inspect
import json
import re
import subprocess
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from types import MappingProxyType

import pytest
from qc2_contracts.runtime import (
    artifact_inventory_hash,
    canonical_content_hash,
    canonical_json_bytes,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

import qc2_science.model_inference as inference
from qc2_science import (
    InferenceError,
    ProbeMismatch,
    compute_environment_fingerprint,
    infer_exact_artifact,
    load_exact_model,
)

ROOT = Path(__file__).resolve().parents[2]
_VALID_FIXTURES = json.loads(
    (ROOT / "packages/contracts/fixtures/v1/valid.json").read_text(encoding="utf-8")
)
_SESSION = "2026-10-05"
_CUTOFF = "2026-10-05T20:00:00Z"
_LOCK_HASH = "a" * 64
_RESOURCE_LIMIT = (
    "qc2_safe_linear_json_v1:max_artifact_bytes=1048576,"
    "max_features=256,max_heads=32,cpu_seconds=2,memory_bytes=268435456"
)
_FEATURE_IDS = ("return_1", "return_5")


def _fixture_contract(name: str) -> dict:
    return copy.deepcopy(
        next(item["payload"] for item in _VALID_FIXTURES if item["contract"] == name)
    )


def _seal(name: str, payload: dict) -> dict:
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash(name, payload)
    validate_contract(name, payload)
    verify_content_hash(name, payload)
    return payload


def _ref(payload: dict) -> dict:
    return {
        "target_schema_name": payload["schema_name"],
        "target_id": payload["id"],
        "content_hash": payload["content_hash"],
    }


def _freeze_json(value):
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _label(target_event: str, stable_key: str, horizon: int) -> dict:
    payload = _fixture_contract("LabelDefinition")
    payload.update(
        {
            "id": new_uuidv7(),
            "created_at": _CUTOFF,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "stable_key": stable_key,
            "version": 1,
            "horizon_sessions": horizon,
            "target_event": target_event,
        }
    )
    return _seal("LabelDefinition", payload)


def _feature_registry() -> tuple[dict, list[dict]]:
    definitions = []
    for feature_id in _FEATURE_IDS:
        definition = _fixture_contract("FeatureDefinition")
        definition.update(
            {
                "id": new_uuidv7(),
                "created_at": _CUTOFF,
                "evidence_class": "SYNTHETIC_FIXTURE",
                "environment_namespace": "test",
                "stable_key": feature_id,
                "version": 1,
                "output_unit": "fraction",
                "output_dtype": "DECIMAL",
                "precision": 12,
            }
        )
        definitions.append(_seal("FeatureDefinition", definition))

    registry = _fixture_contract("FeatureRegistry")
    registry.update(
        {
            "id": new_uuidv7(),
            "created_at": _CUTOFF,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "definition_refs": [_ref(item) for item in definitions],
            "ordered_feature_ids": list(_FEATURE_IDS),
            "effective_from": _SESSION,
        }
    )
    return _seal("FeatureRegistry", registry), definitions


def _safe_artifact(
    *,
    feature_ids: tuple[str, ...] = _FEATURE_IDS,
    operator: str = "LOGISTIC_REGRESSION",
) -> bytes:
    return canonical_json_bytes(
        {
            "schema_name": inference.ARTIFACT_SCHEMA,
            "schema_version": "1.0",
            "ordered_feature_ids": list(feature_ids),
            "heads": [
                {
                    "head_name": "expansion_runner",
                    "operator": operator,
                    "intercept": "0.000000000000",
                    "coefficients": [
                        "1.000000000000",
                        "0.000000000000",
                    ],
                }
            ],
        }
    )


def _head(
    model: dict,
    label: dict,
    *,
    head_name: str,
    output_kind: str,
    availability: str,
    horizon: int,
) -> dict:
    payload = _fixture_contract("ModelHeadDefinition")
    payload.update(
        {
            "id": new_uuidv7(),
            "created_at": _CUTOFF,
            "evidence_class": model["evidence_class"],
            "environment_namespace": model["environment_namespace"],
            "model_ref": _ref(model),
            "head_name": head_name,
            "output_kind": output_kind,
            "label_ref": _ref(label),
            "horizon_sessions": horizon,
            "availability": availability,
            "output_precision": 12,
        }
    )
    validate_contract("ModelHeadDefinition", payload)
    return payload


def _pointer(model: dict, generation: int = 4) -> dict:
    payload = _fixture_contract("ChampionPointer")
    payload.update(
        {
            "id": new_uuidv7(),
            "created_at": _CUTOFF,
            "evidence_class": model["evidence_class"],
            "environment_namespace": model["environment_namespace"],
            "role": "REFERENCE",
            "model_ref": _ref(model),
            "generation": generation,
            "transitioned_at": _CUTOFF,
        }
    )
    validate_contract("ChampionPointer", payload)
    return payload


def _snapshot(
    registry: dict,
    *,
    values: dict[str, str] | None = None,
    feature_order: tuple[str, ...] = _FEATURE_IDS,
) -> dict:
    values = values or {"return_1": "0.4", "return_5": "-0.2"}
    payload = _fixture_contract("FeatureSnapshot")
    payload.update(
        {
            "id": new_uuidv7(),
            "created_at": "2026-10-05T20:04:00Z",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "session_id": _SESSION,
            "instrument_ref": {
                "target_schema_name": "qc2.identity_market.Instrument.v1",
                "target_id": new_uuidv7(),
            },
            "registry_ref": _ref(registry),
            "feature_values": [
                {
                    "feature_id": feature_id,
                    "unit": "fraction",
                    "output_dtype": "DECIMAL",
                    "value": values[feature_id],
                }
                for feature_id in feature_order
            ],
            "decision_cutoff": "2026-10-05T20:04:00Z",
            "environment_fingerprint": "b" * 64,
        }
    )
    return _seal("FeatureSnapshot", payload)


def _build_fixture(
    *,
    safe_format: str = inference.SAFE_FORMAT,
    artifact_feature_ids: tuple[str, ...] = _FEATURE_IDS,
    operator: str = "LOGISTIC_REGRESSION",
    artifact_bytes: bytes | None = None,
    snapshot_order: tuple[str, ...] = _FEATURE_IDS,
    optional_state: str = "UNAVAILABLE_MODEL",
) -> dict:
    registry, feature_definitions = _feature_registry()
    primary_label = _label("EXPANSION_RUNNER", "expansion_runner_1", 1)
    optional_label = _label("SESSION_MONSTER", "session_monster_5", 5)
    if artifact_bytes is None:
        artifact_bytes = _safe_artifact(
            feature_ids=artifact_feature_ids,
            operator=operator,
        )

    artifact_manifest = _fixture_contract("ArtifactManifest")
    artifact_manifest.update(
        {
            "id": new_uuidv7(),
            "created_at": _CUTOFF,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "files": [
                {
                    "relative_path": "model/model.json",
                    "length_bytes": len(artifact_bytes),
                    "media_type": "application/json",
                    "schema_name": inference.ARTIFACT_SCHEMA,
                    "schema_version": "1.0",
                    "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
                }
            ],
        }
    )
    artifact_manifest["inventory_hash"] = artifact_inventory_hash(
        artifact_manifest["files"]
    )
    _seal("ArtifactManifest", artifact_manifest)

    model = _fixture_contract("ModelManifest")
    model.update(
        {
            "id": new_uuidv7(),
            "created_at": _CUTOFF,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "artifact_manifest_ref": _ref(artifact_manifest),
            "safe_format": safe_format,
            "algorithm": inference.ALGORITHM,
            "algorithm_version": inference.ALGORITHM_VERSION,
            "target_label_refs": [_ref(primary_label), _ref(optional_label)],
            "feature_registry_ref": _ref(registry),
            "ordered_feature_ids": list(_FEATURE_IDS),
            "training_start": "2026-10-01",
            "training_cutoff": _CUTOFF,
            "package_lock_hash": _LOCK_HASH,
            "environment_fingerprint": compute_environment_fingerprint(_LOCK_HASH),
            "resource_constraints": [
                _RESOURCE_LIMIT,
                "network_access=none",
                "training_access=none",
            ],
            "lifecycle_state": "RESEARCH",
        }
    )
    _seal("ModelManifest", model)
    pinned_pointer = _pointer(model)
    primary_head = _head(
        model,
        primary_label,
        head_name="expansion_runner",
        output_kind="PROBABILITY",
        availability="AVAILABLE",
        horizon=1,
    )
    optional_head = _head(
        model,
        optional_label,
        head_name="session_monster",
        output_kind="PROBABILITY",
        availability=optional_state,
        horizon=5,
    )
    snapshot = _snapshot(
        registry,
        feature_order=snapshot_order,
    )
    return {
        "artifact_bytes": artifact_bytes,
        "artifact_manifest": artifact_manifest,
        "feature_definitions": feature_definitions,
        "feature_registry": registry,
        "labels": [primary_label, optional_label],
        "model": model,
        "optional_head": optional_head,
        "pinned_pointer": pinned_pointer,
        "primary_head": primary_head,
        "snapshot": snapshot,
    }


def _load(fixture: dict) -> inference.LoadedModel:
    return load_exact_model(
        fixture["model"],
        fixture["artifact_manifest"],
        fixture["feature_registry"],
        fixture["feature_definitions"],
        fixture["artifact_bytes"],
        expected_package_lock_hash=_LOCK_HASH,
    )


def _sigmoid_text(value: str) -> str:
    with localcontext() as context:
        context.prec = 64
        score = Decimal(value)
        if score >= 0:
            tail = (-score).exp()
            output = Decimal(1) / (Decimal(1) + tail)
        else:
            tail = score.exp()
            output = tail / (Decimal(1) + tail)
        return f"{output.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_EVEN):.12f}"


def _probes() -> list[dict]:
    return [
        {
            "probe_id": "zero",
            "feature_values": {"return_1": "0", "return_5": "0"},
            "expected_outputs": {"expansion_runner": "0.500000000000"},
        },
        {
            "probe_id": "unit_move",
            "feature_values": {"return_1": "1", "return_5": "0"},
            "expected_outputs": {"expansion_runner": _sigmoid_text("1")},
        },
    ]


def _infer(loaded: inference.LoadedModel, fixture: dict):
    return infer_exact_artifact(
        loaded,
        pinned_pointer=fixture["pinned_pointer"],
        primary_head=fixture["primary_head"],
        optional_heads=[fixture["optional_head"]],
        label_definitions=fixture["labels"],
        feature_snapshot=fixture["snapshot"],
        probe_set=_probes(),
        evaluated_at="2026-10-05T20:05:00Z",
    )


def test_exact_safe_artifact_emits_repeatable_typed_heads_and_receipt() -> None:
    fixture = _build_fixture()
    loaded = _load(fixture)
    first = _infer(loaded, fixture)
    second = _infer(loaded, fixture)

    assert first.head_outputs[0]["availability"] == "AVAILABLE"
    assert first.head_outputs[0]["output_value"] == _sigmoid_text("0.4")
    assert first.head_outputs[1]["availability"] == "UNAVAILABLE_MODEL"
    assert first.head_outputs[1]["output_value"] is None
    assert first.head_outputs[1]["reason_code"] == "HEAD_UNAVAILABLE_MODEL"
    assert first.receipt["loaded_artifact_hash"] == loaded.artifact_hash
    assert first.receipt["generation"] == 4
    assert first.receipt["deterministic"] is True
    assert first.receipt["probe_set_hash"] == second.receipt["probe_set_hash"]
    assert first.receipt["output_hash"] == second.receipt["output_hash"]


def test_inference_requires_matching_pinned_pointer_and_uses_its_generation() -> None:
    fixture = _build_fixture()
    loaded = _load(fixture)
    fixture["pinned_pointer"]["generation"] = 7
    fixture["pinned_pointer"]["pointer_hash"] = "b" * 64
    validate_contract("ChampionPointer", fixture["pinned_pointer"])
    result = _infer(loaded, fixture)
    assert result.receipt["generation"] == 7

    fixture["pinned_pointer"]["model_ref"]["content_hash"] = "c" * 64
    fixture["pinned_pointer"]["pointer_hash"] = "d" * 64
    with pytest.raises(InferenceError, match="pinned pointer does not select"):
        _infer(loaded, fixture)


def test_unavailable_label_head_remains_null_and_typed() -> None:
    fixture = _build_fixture(optional_state="UNAVAILABLE_LABEL")
    fixture["labels"] = fixture["labels"][:1]
    result = _infer(_load(fixture), fixture)
    assert result.head_outputs[1]["availability"] == "UNAVAILABLE_LABEL"
    assert result.head_outputs[1]["output_value"] is None
    assert result.head_outputs[1]["reason_code"] == "HEAD_UNAVAILABLE_LABEL"


def test_unsafe_serialization_format_is_rejected_before_worker(monkeypatch) -> None:
    fixture = _build_fixture(safe_format="pickle", artifact_bytes=b"not executable data")
    monkeypatch.setattr(
        inference,
        "_run_isolated_worker",
        lambda _request: pytest.fail("unsafe formats must be rejected before the worker"),
    )
    with pytest.raises(InferenceError, match="safe_format"):
        _load(fixture)


def test_exact_artifact_rejects_wrong_feature_order() -> None:
    fixture = _build_fixture(artifact_feature_ids=tuple(reversed(_FEATURE_IDS)))
    with pytest.raises(InferenceError, match="feature order"):
        _load(fixture)


def test_artifact_bytes_must_match_exact_content_addressed_inventory() -> None:
    fixture = _build_fixture()
    changed = fixture["artifact_bytes"].replace(
        b"1.000000000000", b"2.000000000000", 1
    )
    with pytest.raises(InferenceError, match="exact manifest inventory"):
        load_exact_model(
            fixture["model"],
            fixture["artifact_manifest"],
            fixture["feature_registry"],
            fixture["feature_definitions"],
            changed,
            expected_package_lock_hash=_LOCK_HASH,
        )


def test_snapshot_order_must_match_its_pinned_feature_registry() -> None:
    fixture = _build_fixture(snapshot_order=tuple(reversed(_FEATURE_IDS)))
    loaded = _load(fixture)
    with pytest.raises(InferenceError, match="FeatureSnapshot order"):
        _infer(loaded, fixture)


def test_oversized_artifact_is_rejected_before_worker(monkeypatch) -> None:
    fixture = _build_fixture(
        artifact_bytes=b"x" * (inference.MAX_ARTIFACT_BYTES + 1)
    )
    monkeypatch.setattr(
        inference,
        "_run_isolated_worker",
        lambda _request: pytest.fail("oversized artifacts must be rejected before the worker"),
    )
    with pytest.raises(InferenceError, match="1 MiB"):
        _load(fixture)


def test_unsupported_operator_is_rejected() -> None:
    fixture = _build_fixture(operator="PYTHON_EVAL")
    with pytest.raises(InferenceError, match="unsupported operator"):
        _load(fixture)


def test_invalid_probability_is_typed_invalid_not_zero(monkeypatch) -> None:
    fixture = _build_fixture()
    loaded = _load(fixture)
    run_worker = inference._run_isolated_worker

    def invalid_actual(request: dict) -> dict:
        response = run_worker(request)
        if request["mode"] == "infer" and request["actual_vector"] is not None:
            response["actual"]["expansion_runner"] = "1.500000000000"
        return response

    monkeypatch.setattr(inference, "_run_isolated_worker", invalid_actual)
    result = _infer(loaded, fixture)
    assert result.head_outputs[0]["availability"] == "INVALID"
    assert result.head_outputs[0]["output_value"] is None
    assert result.head_outputs[0]["reason_code"] == "INVALID_PROBABILITY"


def test_probe_mismatch_fails_closed(monkeypatch) -> None:
    fixture = _build_fixture()
    loaded = _load(fixture)
    run_worker = inference._run_isolated_worker

    def wrong_probe(request: dict) -> dict:
        response = run_worker(request)
        if request["mode"] == "infer":
            response["probes"][0]["outputs"]["expansion_runner"] = "0.600000000000"
        return response

    monkeypatch.setattr(inference, "_run_isolated_worker", wrong_probe)
    with pytest.raises(ProbeMismatch, match="probe zero"):
        _infer(loaded, fixture)


def test_worker_has_no_training_or_network_imports_and_runs_isolated(
    monkeypatch,
) -> None:
    worker_path = Path(inference._WORKER_SCRIPT)
    worker_source = worker_path.read_text(encoding="utf-8")
    parent_source = Path(inference.__file__).read_text(encoding="utf-8")
    forbidden_import = re.compile(
        r"^\s*(?:import\s+|from\s+)"
        r"(?:socket|urllib|http|pickle|joblib|cloudpickle|sklearn|xgboost|torch|pandas)\b",
        re.MULTILINE,
    )
    assert forbidden_import.search(worker_source) is None
    assert forbidden_import.search(parent_source) is None
    assert "training" not in inspect.signature(load_exact_model).parameters
    assert "network" not in inspect.signature(infer_exact_artifact).parameters

    real_run = subprocess.run
    commands: list[list[str]] = []

    def guarded_run(command, **kwargs):
        commands.append(list(command))
        assert command[1:3] == ["-I", "-S"]
        assert kwargs["cwd"] == "/"
        assert set(kwargs["env"]) == {"LANG", "LC_ALL", "TZ"}
        assert kwargs["timeout"] <= inference.WORKER_TIMEOUT_SECONDS
        return real_run(command, **kwargs)

    monkeypatch.setattr(inference.subprocess, "run", guarded_run)
    fixture = _build_fixture()
    _infer(_load(fixture), fixture)
    assert len(commands) == 3


def test_package_lock_mismatch_rejects_environment() -> None:
    fixture = _build_fixture()
    with pytest.raises(InferenceError, match="package lock"):
        load_exact_model(
            fixture["model"],
            fixture["artifact_manifest"],
            fixture["feature_registry"],
            fixture["feature_definitions"],
            fixture["artifact_bytes"],
            expected_package_lock_hash="c" * 64,
        )


def test_immutable_contract_inputs_are_thawed_before_validation() -> None:
    fixture = _build_fixture()
    loaded = load_exact_model(
        _freeze_json(fixture["model"]),
        _freeze_json(fixture["artifact_manifest"]),
        _freeze_json(fixture["feature_registry"]),
        tuple(_freeze_json(item) for item in fixture["feature_definitions"]),
        fixture["artifact_bytes"],
        expected_package_lock_hash=_LOCK_HASH,
    )
    assert loaded.artifact_hash == hashlib.sha256(fixture["artifact_bytes"]).hexdigest()
