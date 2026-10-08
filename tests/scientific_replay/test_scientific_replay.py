from __future__ import annotations

import copy
import hashlib
import importlib.util
import socket
import sqlite3
import sys
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Callable

import pytest

from qc2_contracts.runtime import (
    artifact_inventory_hash,
    canonical_content_hash,
    canonical_json_bytes,
    validate_contract,
)
from qc2_scientific_replay import (
    ReplayLimits,
    ReplayRunner,
    StageExecutor,
    build_environment_profile,
    capture_package_lock_hash,
    capture_runtime_environment,
)
from qc2_scientific_replay.runner import (
    GRAPH_SCHEMA,
    MANIFEST_SCHEMA,
    PLAN_SCHEMA,
    REQUIRED_ROOT_ROLES,
    SEAL_SCHEMA,
    STAGE_ORDER,
)


ROOT = Path(__file__).resolve().parents[2]
_HELPER_PATH = ROOT / "tests" / "prediction_authority" / "test_prediction_authority.py"
_HELPER_SPEC = importlib.util.spec_from_file_location(
    "qc2_prediction_authority_replay_fixtures", _HELPER_PATH
)
assert _HELPER_SPEC is not None and _HELPER_SPEC.loader is not None
prediction_fixtures = importlib.util.module_from_spec(_HELPER_SPEC)
sys.modules[_HELPER_SPEC.name] = prediction_fixtures
_HELPER_SPEC.loader.exec_module(prediction_fixtures)


HISTORY_SCHEMA = "qc2.fixture.HistoricalBars.v1"
CENSUS_SCHEMA = "qc2.fixture.CandidateCensus.v1"
POLICY_SCHEMA = "qc2.fixture.UniversePolicy.v1"
FEATURE_REGISTRY_SCHEMA = "qc2.fixture.FeatureRegistry.v1"
PROTOCOL_REGISTRY_SCHEMA = "qc2.fixture.ProtocolRegistry.v1"
MODEL_SCHEMA = "qc2.fixture.ModelArtifact.v1"
MEMORY_INDEX_SCHEMA = "qc2.fixture.MemoryIndex.v1"
SCORE_MANIFEST_SCHEMA = "qc2.fixture.ScoreManifest.v1"
CHECKPOINT_SCHEMA = "qc2.scientific_replay.StageCheckpoint.v1"
PAYLOAD_SCHEMA = "qc2.models_prediction.ScientificPredictionPayload.v1"
PROFILE_SCHEMA = "qc2.scientific_replay.QualifiedEnvironmentProfile.v1"
REQUEST_SCHEMA = "qc2.models_prediction.ReplayRequest.v1"
INVENTORY_DOMAIN = "qc2.prediction-inventory.v1"

INSTRUMENT_A = prediction_fixtures.id_for(101)
INSTRUMENT_B = prediction_fixtures.id_for(102)
INSTRUMENT_C = prediction_fixtures.id_for(103)
INSTRUMENT_EXCLUDED = prediction_fixtures.id_for(104)
INSTRUMENT_NO_HISTORY = prediction_fixtures.id_for(105)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _contract_ref(schema_name: str, contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_schema_name": schema_name,
        "target_id": contract["id"],
        "content_hash": contract["content_hash"],
    }


def _source_result() -> Any:
    authority, _, _, run_id = prediction_fixtures.start_run()
    prediction_fixtures.rank_run(authority, run_id, retry=False)
    return authority.seal(
        run_id=run_id,
        sealed_at="2026-10-08T20:59:00Z",
        evidence_refs=(prediction_fixtures.evidence_ref(),),
    )


def _base_history() -> dict[str, Any]:
    return {
        "bars": [
            {"instrument_id": INSTRUMENT_A, "prior_close": "10.00", "close": "10.50"},
            {"instrument_id": INSTRUMENT_B, "prior_close": "20.00", "close": "20.50"},
            {"instrument_id": INSTRUMENT_C, "prior_close": "30.00", "close": "30.75"},
        ]
    }


def _stage_functions(
    *,
    corrupt_features: bool = False,
    attempt_network: bool = False,
    attempt_database: bool = False,
    drop_prediction: bool = False,
) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    def universe(inputs: dict[str, Any]) -> dict[str, Any]:
        history_by_id = {row["instrument_id"]: row for row in inputs["history"]["bars"]}
        allowed = set(inputs["policy"]["allowed_ids"])
        eligible: list[str] = []
        excluded: list[dict[str, Any]] = []
        unscorable: list[dict[str, Any]] = []
        for instrument_id in inputs["census"]["candidate_ids"]:
            if instrument_id not in allowed:
                excluded.append(
                    {
                        "instrument_id": instrument_id,
                        "disposition": "EXCLUDED",
                        "reason": "policy_excluded",
                    }
                )
            elif instrument_id not in history_by_id:
                unscorable.append(
                    {
                        "instrument_id": instrument_id,
                        "disposition": "UNSCORABLE",
                        "reason": "missing_history",
                    }
                )
            else:
                eligible.append(instrument_id)
        return {"eligible_ids": eligible, "excluded": excluded, "unscorable": unscorable}

    def features(inputs: dict[str, Any]) -> dict[str, Any]:
        if attempt_network:
            socket.create_connection(("127.0.0.1", 9), timeout=0.01)
        if attempt_database:
            sqlite3.connect(":memory:")
        history_by_id = {row["instrument_id"]: row for row in inputs["history"]["bars"]}
        rows: list[dict[str, Any]] = []
        for instrument_id in inputs["out_universe"]["eligible_ids"]:
            bar = history_by_id[instrument_id]
            prior = Decimal(bar["prior_close"])
            close = Decimal(bar["close"])
            momentum = ((close / prior) - Decimal(1)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_EVEN
            )
            if corrupt_features and instrument_id == INSTRUMENT_A:
                momentum += Decimal("0.001000")
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "availability": "AVAILABLE",
                    "reference_price": bar["close"],
                    "momentum": format(momentum, ".6f"),
                }
            )
        return {"rows": rows, "registry_id": inputs["feature_registry"]["registry_id"]}

    def protocols(inputs: dict[str, Any]) -> dict[str, Any]:
        minimum = Decimal(inputs["protocol_registry"]["minimum_momentum"])
        rows = []
        for feature in inputs["out_features"]["rows"]:
            passed = Decimal(feature["momentum"]) >= minimum
            rows.append(
                {
                    "instrument_id": feature["instrument_id"],
                    "status": "PASS" if passed else "BLOCKED",
                    "reason": None if passed else "below_minimum_momentum",
                }
            )
        return {"rows": rows, "registry_id": inputs["protocol_registry"]["registry_id"]}

    def heads(inputs: dict[str, Any]) -> dict[str, Any]:
        model = inputs["model"]
        missing = set(model["missing_heads"])
        head_values = model["head_values"]
        rows = []
        for protocol in inputs["out_protocols"]["rows"]:
            instrument_id = protocol["instrument_id"]
            if protocol["status"] != "PASS" or instrument_id in missing:
                rows.append(
                    {
                        "instrument_id": instrument_id,
                        "output": None,
                        "reason": "missing_head",
                    }
                )
            else:
                rows.append(
                    {
                        "instrument_id": instrument_id,
                        "output": head_values[instrument_id],
                        "reason": None,
                    }
                )
        return {
            "rows": rows,
            "model_id": model["model_id"],
            "memory_index_id": inputs["memory_index"]["index_id"],
        }

    def score(inputs: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for head in inputs["out_heads"]["rows"]:
            rows.append(
                {
                    "instrument_id": head["instrument_id"],
                    "score": head["output"],
                    "unscorable_reason": head["reason"],
                }
            )
        return {
            "rows": rows,
            "score_manifest_id": inputs["score_manifest"]["manifest_id"],
        }

    def rank(inputs: dict[str, Any]) -> dict[str, Any]:
        source_rows = inputs["out_score"]["rows"]
        scored = [row for row in source_rows if row["score"] is not None]
        scored.sort(key=lambda row: (-Decimal(row["score"]), row["instrument_id"].encode("utf-8")))
        unscorable = sorted(
            (row for row in source_rows if row["score"] is None),
            key=lambda row: row["instrument_id"].encode("utf-8"),
        )
        rows: list[dict[str, Any]] = []
        for ordinal, row in enumerate(scored, start=1):
            rows.append(
                {
                    "instrument_id": row["instrument_id"],
                    "score": row["score"],
                    "rank": ordinal,
                    "disposition": "SCORED",
                    "unscorable_reason": None,
                }
            )
        for row in unscorable:
            rows.append(
                {
                    "instrument_id": row["instrument_id"],
                    "score": None,
                    "rank": None,
                    "disposition": "UNSCORABLE",
                    "unscorable_reason": row["unscorable_reason"],
                }
            )
        return {"rows": rows}

    def payloads(inputs: dict[str, Any]) -> dict[str, Any]:
        authority, _, _, run_id = prediction_fixtures.start_run()
        authority.record_feature_rows(
            run_id=run_id,
            feature_rows=prediction_fixtures.make_features(),
        )
        authority.record_scores(
            run_id=run_id,
            score_results={
                row["instrument_id"]: prediction_fixtures.ScoreResult(
                    row["score"], row["unscorable_reason"]
                )
                for row in inputs["out_rank"]["rows"]
            },
            completed_at="2026-10-08T19:40:00Z",
        )
        authority.rank(run_id=run_id, created_at="2026-10-08T19:43:00Z")
        result = authority.seal(
            run_id=run_id,
            sealed_at="2026-10-08T20:59:00Z",
            evidence_refs=(prediction_fixtures.evidence_ref(),),
        )
        predictions = [dict(row) for row in result.rows]
        if drop_prediction:
            predictions.pop()
        return {
            "predictions": predictions,
            "payloads": [
                dict(payload)
                for _, payload in sorted(result.scientific_payloads.items())
            ],
        }

    return {
        "UNIVERSE": universe,
        "FEATURES": features,
        "PROTOCOLS": protocols,
        "HEADS": heads,
        "SCORE": score,
        "RANK": rank,
        "PAYLOADS": payloads,
    }


def _fixture_documents(
    *,
    mode: str = "EXACT",
    corrected_history: dict[str, Any] | None = None,
    corrupt_features: bool = False,
    attempt_network: bool = False,
    attempt_database: bool = False,
    drop_prediction: bool = False,
) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, StageExecutor], dict[str, Any]]:
    source_result = _source_result()
    source_seal = dict(source_result.seal)
    history = _base_history()
    census = {
        "candidate_ids": [
            INSTRUMENT_A,
            INSTRUMENT_B,
            INSTRUMENT_C,
            INSTRUMENT_EXCLUDED,
            INSTRUMENT_NO_HISTORY,
        ]
    }
    policy = {"allowed_ids": [INSTRUMENT_A, INSTRUMENT_B, INSTRUMENT_C, INSTRUMENT_NO_HISTORY]}
    feature_registry = {"registry_id": "feature-registry-fixture-v1", "features": ["momentum"]}
    protocol_registry = {
        "registry_id": "protocol-registry-fixture-v1",
        "minimum_momentum": "0.000000",
    }
    model = {
        "model_id": "sealed-model-fixture-v1",
        "head_values": {INSTRUMENT_A: "0.850000", INSTRUMENT_B: "0.850000"},
        "missing_heads": [INSTRUMENT_C],
    }
    memory_index = {"index_id": "sealed-memory-index-v1", "entries": []}
    score_manifest = {"manifest_id": "score-manifest-fixture-v1", "source": "head_output"}

    executor_functions = _stage_functions(
        corrupt_features=corrupt_features,
        attempt_network=attempt_network,
        attempt_database=attempt_database,
        drop_prediction=drop_prediction,
    )
    reference_functions = _stage_functions()
    executor_hashes = {
        f"fixture.{stage.lower()}": _sha256(f"fixture-stage:{stage}:v1".encode())
        for stage in STAGE_ORDER
    }
    runtime = capture_runtime_environment()
    profile = build_environment_profile(
        package_lock_hash=capture_package_lock_hash(),
        executor_hashes=executor_hashes,
        runtime=runtime,
    )
    executors = {
        stage: StageExecutor(
            executor_id=f"fixture.{stage.lower()}",
            stage_kind=stage,
            implementation_hash=executor_hashes[f"fixture.{stage.lower()}"],
            execute=executor_functions[stage],
        )
        for stage in STAGE_ORDER
    }

    common_inputs: dict[str, Any] = {
        "history": history,
        "census": census,
        "policy": policy,
        "feature_registry": feature_registry,
        "protocol_registry": protocol_registry,
        "model": model,
        "memory_index": memory_index,
        "score_manifest": score_manifest,
    }
    expected_outputs: dict[str, Any] = {}
    stage_inputs = common_inputs
    stage_input_ids = {
        "UNIVERSE": ["history", "census", "policy"],
        "FEATURES": ["out_universe", "history", "feature_registry"],
        "PROTOCOLS": ["out_features", "protocol_registry"],
        "HEADS": ["out_protocols", "model", "memory_index"],
        "SCORE": ["out_heads", "score_manifest"],
        "RANK": ["out_score"],
        "PAYLOADS": ["out_rank", "source_seal"],
    }
    for stage in STAGE_ORDER:
        if stage == "FEATURES":
            stage_inputs = {
                "out_universe": expected_outputs["UNIVERSE"],
                "history": history,
                "feature_registry": feature_registry,
            }
        elif stage == "PROTOCOLS":
            stage_inputs = {
                "out_features": expected_outputs["FEATURES"],
                "protocol_registry": protocol_registry,
            }
        elif stage == "HEADS":
            stage_inputs = {
                "out_protocols": expected_outputs["PROTOCOLS"],
                "model": model,
                "memory_index": memory_index,
            }
        elif stage == "SCORE":
            stage_inputs = {
                "out_heads": expected_outputs["HEADS"],
                "score_manifest": score_manifest,
            }
        elif stage == "RANK":
            stage_inputs = {"out_score": expected_outputs["SCORE"]}
        elif stage == "PAYLOADS":
            stage_inputs = {
                "out_rank": expected_outputs["RANK"],
                "source_seal": source_seal,
            }
        expected_outputs[stage] = reference_functions[stage](stage_inputs)

    contents: dict[str, bytes] = {}
    file_schema: dict[str, tuple[str, str]] = {}
    node_specs: list[dict[str, Any]] = []

    def add_json(path: str, value: Any, schema_name: str, schema_version: str = "1.0") -> None:
        contents[path] = _json_bytes(value)
        file_schema[path] = (schema_name, schema_version)

    def add_node(
        node_id: str,
        role: str,
        path: str,
        *,
        dependencies: list[str] | None = None,
        contract_name: str | None = None,
    ) -> None:
        node_specs.append(
            {
                "node_id": node_id,
                "role": role,
                "relative_path": path,
                "depends_on": dependencies or [],
                "contract_name": contract_name,
            }
        )

    add_json("inputs/history.json", history, HISTORY_SCHEMA)
    add_json("inputs/census.json", census, CENSUS_SCHEMA)
    add_json("inputs/policy.json", policy, POLICY_SCHEMA)
    add_json("inputs/feature_registry.json", feature_registry, FEATURE_REGISTRY_SCHEMA)
    add_json("inputs/protocol_registry.json", protocol_registry, PROTOCOL_REGISTRY_SCHEMA)
    add_json("inputs/model.json", model, MODEL_SCHEMA)
    add_json("inputs/memory_index.json", memory_index, MEMORY_INDEX_SCHEMA)
    add_json("inputs/score_manifest.json", score_manifest, SCORE_MANIFEST_SCHEMA)
    add_json(
        "source/prediction_seal.json",
        source_seal,
        source_seal["schema_name"],
        source_seal["schema_version"],
    )
    add_json("control/environment_profile.json", profile, PROFILE_SCHEMA)

    input_nodes = [
        ("history", "MARKET_HISTORY", "inputs/history.json", HISTORY_SCHEMA, []),
        ("policy", "UNIVERSE_POLICY", "inputs/policy.json", POLICY_SCHEMA, []),
        ("census", "CANDIDATE_CENSUS", "inputs/census.json", CENSUS_SCHEMA, []),
        (
            "feature_registry",
            "FEATURE_REGISTRY",
            "inputs/feature_registry.json",
            FEATURE_REGISTRY_SCHEMA,
            [],
        ),
        (
            "protocol_registry",
            "PROTOCOL_REGISTRY",
            "inputs/protocol_registry.json",
            PROTOCOL_REGISTRY_SCHEMA,
            [],
        ),
        ("model", "MODEL", "inputs/model.json", MODEL_SCHEMA, ["memory_index"]),
        ("memory_index", "MEMORY_INDEX", "inputs/memory_index.json", MEMORY_INDEX_SCHEMA, []),
        ("score_manifest", "SCORE_MANIFEST", "inputs/score_manifest.json", SCORE_MANIFEST_SCHEMA, []),
        (
            "environment_profile",
            "ENVIRONMENT_PROFILE",
            "control/environment_profile.json",
            PROFILE_SCHEMA,
            [],
        ),
        (
            "source_seal",
            "SOURCE_SEAL",
            "source/prediction_seal.json",
            source_seal["schema_name"],
            [
                "history",
                "policy",
                "census",
                "feature_registry",
                "protocol_registry",
                "model",
                "memory_index",
                "score_manifest",
                "environment_profile",
            ],
        ),
    ]
    role_roots: list[str] = []
    for node_id, role, path, contract_name, dependencies in input_nodes:
        add_node(
            node_id,
            role,
            path,
            dependencies=dependencies,
            contract_name="PredictionSeal" if role == "SOURCE_SEAL" else None,
        )
        role_roots.append(node_id)

    if corrected_history is not None:
        add_json("inputs/history_corrected.json", corrected_history, HISTORY_SCHEMA)
        add_node("history_corrected", "CORRECTED_MARKET_HISTORY", "inputs/history_corrected.json")

    expected_payload_ids: list[str] = []
    for payload in expected_outputs["PAYLOADS"]["payloads"]:
        instrument_id = payload["instrument_ref"]["target_id"]
        node_id = f"expected_payload_{instrument_id}"
        path = f"expected/payloads/{instrument_id}.json"
        add_json(path, payload, PAYLOAD_SCHEMA, "1.0")
        add_node(node_id, "EXPECTED_PAYLOAD", path, contract_name="ScientificPredictionPayload")
        expected_payload_ids.append(node_id)

    stage_documents: list[dict[str, Any]] = []
    prior_output = ""
    for index, stage in enumerate(STAGE_ORDER):
        output_id = f"out_{stage.lower()}"
        expected_id = f"expected_{stage.lower()}"
        expected_path = f"expected/stages/{stage.lower()}.json"
        add_json(expected_path, expected_outputs[stage], CHECKPOINT_SCHEMA, "1.0")
        add_node(expected_id, "EXPECTED_STAGE_OUTPUT", expected_path)
        inputs = list(stage_input_ids[stage])
        stage_documents.append(
            {
                "stage_id": f"stage-{index + 1}-{stage.lower()}",
                "stage_kind": stage,
                "executor_id": executors[stage].executor_id,
                "implementation_hash": executors[stage].implementation_hash,
                "input_node_ids": inputs,
                "output_node_id": output_id,
                "expected_node_id": expected_id,
                "expected_payload_node_ids": (
                    expected_payload_ids if stage == "PAYLOADS" else []
                ),
            }
        )
        prior_output = output_id
    assert prior_output == "out_payloads"

    if mode == "CORRECTED_DATA_SENSITIVITY":
        assert corrected_history is not None
        corrected_overrides = {"MARKET_HISTORY": "history_corrected"}
    else:
        corrected_overrides = {}
    plan = {
        "schema_name": PLAN_SCHEMA,
        "schema_version": "1.0",
        "required_root_roles": list(REQUIRED_ROOT_ROLES),
        "stages": stage_documents,
        "corrected_overrides": corrected_overrides,
    }
    add_json("control/replay_plan.json", plan, PLAN_SCHEMA)
    graph = {
        "schema_name": GRAPH_SCHEMA,
        "schema_version": "1.0",
        "roots": role_roots,
        "nodes": node_specs,
    }
    add_json("control/dependency_graph.json", graph, GRAPH_SCHEMA)

    records = [
        {
            "relative_path": path,
            "length_bytes": len(data),
            "media_type": "application/json",
            "schema_name": file_schema[path][0],
            "schema_version": file_schema[path][1],
            "sha256": _sha256(data),
        }
        for path, data in sorted(contents.items())
    ]
    manifest: dict[str, Any] = {
        "schema_name": MANIFEST_SCHEMA,
        "schema_version": "1.0",
        "id": prediction_fixtures.id_for(8001),
        "created_at": "2026-10-08T20:59:00Z",
        "owning_authority": "model_registry",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        "content_hash": "0" * 64,
        "manifest_version": 1,
        "files": records,
        "inventory_hash": artifact_inventory_hash(records),
        "detached_signature": None,
        "transport_hash": None,
    }
    manifest["content_hash"] = canonical_content_hash("ArtifactManifest", manifest)
    validate_contract("ArtifactManifest", manifest)

    request: dict[str, Any] = {
        "schema_name": REQUEST_SCHEMA,
        "schema_version": "1.0",
        "id": prediction_fixtures.id_for(8002),
        "created_at": "2026-10-08T20:59:00Z",
        "owning_authority": "validation",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [_contract_ref(MANIFEST_SCHEMA, manifest)],
        "source_seal_ref": _contract_ref(SEAL_SCHEMA, source_seal),
        "requested_at": "2026-10-08T20:59:00Z",
        "environment_fingerprint": profile["fingerprint"],
        "reason_code": "full_scientific_replay_fixture",
        "replay_mode": mode,
    }
    validate_contract("ReplayRequest", request)

    executors_by_id = {executor.executor_id: executor for executor in executors.values()}
    return contents, request, source_seal, manifest, executors_by_id, {
        "profile": profile,
        "runtime": runtime,
        "plan": plan,
        "graph": graph,
        "expected_outputs": expected_outputs,
        "source_result": source_result,
    }


def _write_bundle(root: Path, contents: dict[str, bytes]) -> Path:
    bundle = root / "bundle"
    for relative_path, data in contents.items():
        target = bundle / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return bundle


def _run_case(
    tmp_path: Path,
    *,
    mode: str = "EXACT",
    corrected_history: dict[str, Any] | None = None,
    corrupt_features: bool = False,
    attempt_network: bool = False,
    attempt_database: bool = False,
    drop_prediction: bool = False,
) -> tuple[Any, dict[str, Any]]:
    contents, request, seal, manifest, executors, fixture = _fixture_documents(
        mode=mode,
        corrected_history=corrected_history,
        corrupt_features=corrupt_features,
        attempt_network=attempt_network,
        attempt_database=attempt_database,
        drop_prediction=drop_prediction,
    )
    bundle = _write_bundle(tmp_path, contents)
    runner = ReplayRunner(
        limits=ReplayLimits(
            max_files=256,
            max_file_bytes=2_000_000,
            max_total_bytes=20_000_000,
            max_dependency_depth=64,
        ),
        environment_provider=lambda: copy.deepcopy(fixture["runtime"]),
    )
    result = runner.run(
        bundle,
        replay_request=request,
        source_seal=seal,
        artifact_manifest=manifest,
        executors=executors,
    )
    return result, fixture


def test_exact_replay_reproduces_every_stage_payload_and_inventory_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contents, request, seal, manifest, executors, fixture = _fixture_documents()
    bundle = _write_bundle(tmp_path, contents)

    def forbidden_io(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("replay must not open network or SQLite connections")

    monkeypatch.setattr(socket, "socket", forbidden_io)
    monkeypatch.setattr(socket, "create_connection", forbidden_io)
    monkeypatch.setattr(sqlite3, "connect", forbidden_io)

    result = ReplayRunner(
        limits=ReplayLimits(256, 2_000_000, 20_000_000, 64),
        environment_provider=lambda: copy.deepcopy(fixture["runtime"]),
    ).run(
        bundle,
        replay_request=request,
        source_seal=seal,
        artifact_manifest=manifest,
        executors=executors,
    )

    assert result.receipt["verdict"] == "MATCH"
    assert result.receipt["expected_hash"] == seal["payload_inventory_hash"]
    assert result.receipt["actual_hash"] == seal["payload_inventory_hash"]
    assert result.receipt["expected_count"] == result.receipt["actual_count"] == 3
    assert [item["stage_kind"] for item in result.stage_comparisons] == list(STAGE_ORDER)
    assert all(item["matches"] for item in result.stage_comparisons)
    assert result.stage_comparisons[0]["matches"] is True
    assert result.dependency_closure.count("memory_index") == 1
    assert result.dependency_closure.count("source_seal") == 1
    assert result.corrected_input_identity is None
    expected_payloads = fixture["source_result"].scientific_payloads
    assert set(result.scientific_payload_bytes) == set(expected_payloads)
    for instrument_id, payload in expected_payloads.items():
        from qc2_contracts.catalog import SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS

        expected = {field: payload[field] for field in SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS}
        assert result.scientific_payload_bytes[instrument_id] == canonical_json_bytes(expected)
    universe = fixture["expected_outputs"]["UNIVERSE"]
    assert universe["excluded"][0]["disposition"] == "EXCLUDED"
    assert universe["unscorable"][0]["reason"] == "missing_history"
    final_rows = fixture["expected_outputs"]["PAYLOADS"]["predictions"]
    assert any(row["disposition"] == "UNSCORABLE" for row in final_rows)
    assert len(fixture["expected_outputs"]["PAYLOADS"]["payloads"]) == 2


@pytest.mark.parametrize(
    "missing_path",
    [
        "inputs/history.json",
        "inputs/model.json",
        "inputs/memory_index.json",
        "control/environment_profile.json",
    ],
)
def test_missing_sealed_dependencies_fail_closed(
    tmp_path: Path, missing_path: str
) -> None:
    contents, request, seal, manifest, executors, fixture = _fixture_documents()
    bundle = _write_bundle(tmp_path, contents)
    (bundle / missing_path).unlink()
    result = ReplayRunner(
        limits=ReplayLimits(256, 2_000_000, 20_000_000, 64),
        environment_provider=lambda: copy.deepcopy(fixture["runtime"]),
    ).run(
        bundle,
        replay_request=request,
        source_seal=seal,
        artifact_manifest=manifest,
        executors=executors,
    )
    assert result.receipt["verdict"] == "BLOCKED"
    assert "inventory differs" in result.receipt["first_mismatch"]
    assert result.stage_comparisons == ()


def test_environment_mismatch_blocks_before_any_stage_runs(tmp_path: Path) -> None:
    contents, request, seal, manifest, executors, fixture = _fixture_documents()
    bundle = _write_bundle(tmp_path, contents)
    changed_runtime = copy.deepcopy(fixture["runtime"])
    changed_runtime["platform_release"] = "unqualified-runtime"
    result = ReplayRunner(
        limits=ReplayLimits(256, 2_000_000, 20_000_000, 64),
        environment_provider=lambda: changed_runtime,
    ).run(
        bundle,
        replay_request=request,
        source_seal=seal,
        artifact_manifest=manifest,
        executors=executors,
    )
    assert result.receipt["verdict"] == "BLOCKED"
    assert "runtime environment does not match" in result.receipt["first_mismatch"]
    assert result.stage_comparisons == ()


def test_package_lock_mismatch_blocks_before_any_stage_runs(tmp_path: Path) -> None:
    contents, request, seal, manifest, executors, fixture = _fixture_documents()
    bundle = _write_bundle(tmp_path, contents)
    result = ReplayRunner(
        limits=ReplayLimits(256, 2_000_000, 20_000_000, 64),
        environment_provider=lambda: copy.deepcopy(fixture["runtime"]),
        package_lock_hash_provider=lambda: "0" * 64,
    ).run(
        bundle,
        replay_request=request,
        source_seal=seal,
        artifact_manifest=manifest,
        executors=executors,
    )
    assert result.receipt["verdict"] == "BLOCKED"
    assert "package lock hash does not match" in result.receipt["first_mismatch"]
    assert result.stage_comparisons == ()


def test_first_mismatch_localizes_to_the_earliest_stage(tmp_path: Path) -> None:
    result, _ = _run_case(tmp_path, corrupt_features=True)
    assert result.receipt["verdict"] == "MISMATCH"
    assert result.receipt["first_mismatch"].startswith("FEATURES $/rows/0/momentum")
    assert result.stage_comparisons[0]["matches"] is True
    assert result.stage_comparisons[1]["matches"] is False


def test_inventory_count_delta_returns_mismatch_receipt_not_blocked(
    tmp_path: Path,
) -> None:
    result, _ = _run_case(tmp_path, drop_prediction=True)
    assert result.receipt["verdict"] == "MISMATCH"
    assert result.receipt["expected_count"] == 3
    assert result.receipt["actual_count"] == 2
    assert "PAYLOADS $/predictions" in result.receipt["first_mismatch"]


def test_corrected_data_is_closed_over_retained_history_and_has_distinct_identity(
    tmp_path: Path,
) -> None:
    corrected_a = _base_history()
    corrected_a["bars"][0]["close"] = "9.50"
    result_a, _ = _run_case(
        tmp_path / "corrected-a",
        mode="CORRECTED_DATA_SENSITIVITY",
        corrected_history=corrected_a,
    )
    assert result_a.receipt["verdict"] == "INCOMPLETE"
    assert result_a.corrected_input_identity is not None
    assert "history_corrected" in result_a.dependency_closure
    assert "corrected-data sensitivity is not an exact replay" in result_a.receipt["first_mismatch"]

    corrected_b = _base_history()
    corrected_b["bars"][0]["close"] = "9.00"
    result_b, _ = _run_case(
        tmp_path / "corrected-b",
        mode="CORRECTED_DATA_SENSITIVITY",
        corrected_history=corrected_b,
    )
    assert result_b.receipt["verdict"] == "INCOMPLETE"
    assert result_b.corrected_input_identity is not None
    assert result_a.corrected_input_identity != result_b.corrected_input_identity


@pytest.mark.parametrize("attempted_io", ["network", "database"])
def test_stage_network_or_database_attempt_is_blocked(
    tmp_path: Path, attempted_io: str
) -> None:
    result, _ = _run_case(
        tmp_path,
        attempt_network=attempted_io == "network",
        attempt_database=attempted_io == "database",
    )
    assert result.receipt["verdict"] == "BLOCKED"
    assert "stage attempted network or mutable database access" in result.receipt["first_mismatch"]
    assert result.stage_comparisons == ()


def test_compatibility_mode_cannot_claim_an_exact_match(tmp_path: Path) -> None:
    result, _ = _run_case(tmp_path, mode="COMPATIBILITY_EXPERIMENT")
    assert result.receipt["verdict"] == "INCOMPLETE"
    assert "compatibility experiment is not an exact-environment qualification" in result.receipt[
        "first_mismatch"
    ]

