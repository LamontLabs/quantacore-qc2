"""Read-only scientific replay from a complete, content-pinned local bundle."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import sqlite3
import stat
import time
import unicodedata
import urllib.request
from contextlib import contextmanager
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from qc2_contracts.catalog import SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS
from qc2_contracts.runtime import (
    artifact_inventory_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
    scientific_payload_hash,
    validate_contract,
    verify_content_hash,
)

from .dependencies import resolve_dependency_closure
from .environment import PROFILE_SCHEMA, capture_runtime_environment, environment_fingerprint
from .models import ReplayError, ReplayInputError, ReplayLimits, ReplayRunResult, StageExecutor


PREDICTION_SCHEMA = "qc2.models_prediction.Prediction.v1"
SEAL_SCHEMA = "qc2.models_prediction.PredictionSeal.v1"
REQUEST_SCHEMA = "qc2.models_prediction.ReplayRequest.v1"
RECEIPT_SCHEMA = "qc2.models_prediction.ReplayReceipt.v1"
MANIFEST_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"
INVENTORY_HASH_DOMAIN = "qc2.prediction-inventory.v1"
EMPTY_INVENTORY_HASH = domain_separated_sha256(INVENTORY_HASH_DOMAIN, canonical_json_bytes([]))

GRAPH_SCHEMA = "qc2.scientific_replay.DependencyGraph.v1"
PLAN_SCHEMA = "qc2.scientific_replay.ReplayPlan.v1"
STAGE_ORDER = ("UNIVERSE", "FEATURES", "PROTOCOLS", "HEADS", "SCORE", "RANK", "PAYLOADS")
REQUIRED_ROOT_ROLES = (
    "MARKET_HISTORY",
    "UNIVERSE_POLICY",
    "CANDIDATE_CENSUS",
    "FEATURE_REGISTRY",
    "PROTOCOL_REGISTRY",
    "MODEL",
    "MEMORY_INDEX",
    "SCORE_MANIFEST",
    "ENVIRONMENT_PROFILE",
    "SOURCE_SEAL",
)
_HEX = frozenset("0123456789abcdef")


class _BlockedReplay(ReplayError):
    pass


def _fail_constant(value: str) -> None:
    raise ReplayInputError(f"non-JSON numeric constant is forbidden: {value}")


def _reject_float(value: str) -> None:
    raise ReplayInputError(f"floating point JSON value is forbidden: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReplayInputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_fail_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayInputError(f"{label} is not strict UTF-8 JSON") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in _HEX for char in value)


@contextmanager
def _offline_stage_io():
    """Deny common network and SQLite entry points while trusted code executes."""
    def denied(*_args: Any, **_kwargs: Any) -> Any:
        raise _BlockedReplay("stage attempted network or mutable database access")

    saved = {
        "socket": socket.socket,
        "create_connection": socket.create_connection,
        "create_server": socket.create_server,
        "getaddrinfo": socket.getaddrinfo,
        "urlopen": urllib.request.urlopen,
        "sqlite_connect": sqlite3.connect,
    }
    socket.socket = denied  # type: ignore[assignment]
    socket.create_connection = denied  # type: ignore[assignment]
    socket.create_server = denied  # type: ignore[assignment]
    socket.getaddrinfo = denied  # type: ignore[assignment]
    urllib.request.urlopen = denied  # type: ignore[assignment]
    sqlite3.connect = denied  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = saved["socket"]  # type: ignore[assignment]
        socket.create_connection = saved["create_connection"]  # type: ignore[assignment]
        socket.create_server = saved["create_server"]  # type: ignore[assignment]
        socket.getaddrinfo = saved["getaddrinfo"]  # type: ignore[assignment]
        urllib.request.urlopen = saved["urlopen"]  # type: ignore[assignment]
        sqlite3.connect = saved["sqlite_connect"]  # type: ignore[assignment]


def _reference(schema_name: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    reference: dict[str, Any] = {
        "target_schema_name": schema_name,
        "target_id": contract["id"],
    }
    if "content_hash" in contract:
        reference["content_hash"] = contract["content_hash"]
    return reference


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayInputError(f"{label} must be a JSON object")
    return value


def _normalized_bundle_path(value: object) -> str:
    if not isinstance(value, str):
        raise ReplayInputError("artifact path must be a string")
    normalized = unicodedata.normalize("NFC", value)
    path = PurePosixPath(normalized)
    if (
        normalized != value
        or path.is_absolute()
        or "\\" in normalized
        or not normalized
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
        or (path.parts and ":" in path.parts[0])
    ):
        raise ReplayInputError(f"unsafe or non-normalized artifact path: {value!r}")
    return normalized


def _scan_bundle(root: Path, limits: ReplayLimits) -> dict[str, bytes]:
    if root.is_symlink() or not root.is_dir():
        raise _BlockedReplay("replay bundle root must be a real directory")
    files: dict[str, bytes] = {}
    total = 0
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        for dirname in tuple(dirnames):
            entry = base / dirname
            if entry.is_symlink():
                raise _BlockedReplay(f"symlink directory is forbidden: {entry.relative_to(root)}")
            if not entry.is_dir():
                raise _BlockedReplay(f"non-directory path in replay bundle: {entry.relative_to(root)}")
        for filename in filenames:
            path = base / filename
            relative = _normalized_bundle_path(path.relative_to(root).as_posix())
            try:
                info = path.lstat()
            except OSError as exc:
                raise _BlockedReplay(f"cannot inspect replay artifact {relative}: {exc}") from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise _BlockedReplay(f"unsafe filesystem object in replay bundle: {relative}")
            if info.st_size > limits.max_file_bytes:
                raise _BlockedReplay(f"artifact exceeds max_file_bytes: {relative}")
            total += info.st_size
            if total > limits.max_total_bytes:
                raise _BlockedReplay("replay bundle exceeds max_total_bytes")
            if len(files) >= limits.max_files:
                raise _BlockedReplay("replay bundle exceeds max_files")
            files[relative] = path.read_bytes()
    return files


def _compare_inventory(
    root: Path,
    manifest: Mapping[str, Any],
    limits: ReplayLimits,
) -> dict[str, bytes]:
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) > limits.max_files:
        raise _BlockedReplay("ArtifactManifest file list is missing or exceeds max_files")
    declared: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise _BlockedReplay("ArtifactManifest contains a malformed file record")
        path = _normalized_bundle_path(record.get("relative_path"))
        if path in declared:
            raise _BlockedReplay(f"ArtifactManifest repeats path {path}")
        declared[path] = record
    actual = _scan_bundle(root, limits)
    if set(actual) != set(declared):
        missing = sorted(set(declared) - set(actual))
        extra = sorted(set(actual) - set(declared))
        detail = f"bundle inventory differs; missing={missing}, extra={extra}"
        raise _BlockedReplay(detail)
    total = 0
    for path, data in actual.items():
        record = declared[path]
        total += len(data)
        if total > limits.max_total_bytes:
            raise _BlockedReplay("replay bundle exceeds max_total_bytes")
        if record.get("length_bytes") != len(data) or record.get("sha256") != _sha256(data):
            raise _BlockedReplay(f"artifact hash or length mismatch: {path}")
    try:
        computed = artifact_inventory_hash([dict(record) for record in records])
    except (KeyError, TypeError, ValueError) as exc:
        raise _BlockedReplay(f"ArtifactManifest inventory is invalid: {exc}") from exc
    if computed != manifest.get("inventory_hash"):
        raise _BlockedReplay("ArtifactManifest inventory_hash does not match its file records")
    return actual


def _control_file(
    manifest: Mapping[str, Any],
    file_bytes: Mapping[str, bytes],
    schema_name: str,
) -> tuple[str, dict[str, Any]]:
    candidates = [
        record
        for record in manifest["files"]
        if record.get("schema_name") == schema_name
    ]
    if len(candidates) != 1:
        raise _BlockedReplay(f"expected one control artifact with schema {schema_name}")
    path = _normalized_bundle_path(candidates[0]["relative_path"])
    document = _object(_strict_json(file_bytes[path], path), path)
    if document.get("schema_name") != schema_name or document.get("schema_version") != "1.0":
        raise _BlockedReplay(f"control artifact schema mismatch at {path}")
    return path, document


def _validate_graph(graph: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    if set(graph) != {"schema_name", "schema_version", "roots", "nodes"}:
        raise _BlockedReplay("dependency graph has unknown or missing fields")
    if graph.get("schema_name") != GRAPH_SCHEMA or graph.get("schema_version") != "1.0":
        raise _BlockedReplay("dependency graph schema is unsupported")
    nodes = graph.get("nodes")
    roots = graph.get("roots")
    if not isinstance(nodes, list) or not isinstance(roots, list):
        raise _BlockedReplay("dependency graph nodes and roots must be arrays")
    normalized_nodes: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {
            "node_id",
            "role",
            "relative_path",
            "depends_on",
            "contract_name",
        }:
            raise _BlockedReplay("dependency graph has a malformed node")
        if (
            not isinstance(node["node_id"], str)
            or not node["node_id"]
            or not isinstance(node["role"], str)
            or not node["role"]
            or not isinstance(node["depends_on"], list)
            or any(not isinstance(item, str) for item in node["depends_on"])
            or (node["contract_name"] is not None and not isinstance(node["contract_name"], str))
        ):
            raise _BlockedReplay("dependency graph node has invalid field types")
        node = dict(node)
        node["relative_path"] = _normalized_bundle_path(node["relative_path"])
        normalized_nodes.append(node)
    return normalized_nodes, roots


def _validate_plan(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    if set(plan) != {
        "schema_name",
        "schema_version",
        "required_root_roles",
        "stages",
        "corrected_overrides",
    }:
        raise _BlockedReplay("replay plan has unknown or missing fields")
    if plan.get("schema_name") != PLAN_SCHEMA or plan.get("schema_version") != "1.0":
        raise _BlockedReplay("replay plan schema is unsupported")
    roles = plan.get("required_root_roles")
    if not isinstance(roles, list) or tuple(roles) != REQUIRED_ROOT_ROLES:
        raise _BlockedReplay("replay plan does not require the complete QC2 dependency roots")
    stages = plan.get("stages")
    if not isinstance(stages, list) or len(stages) != len(STAGE_ORDER):
        raise _BlockedReplay("replay plan must define every scientific stage exactly once")
    normalized: list[dict[str, Any]] = []
    for expected_kind, stage in zip(STAGE_ORDER, stages, strict=True):
        required = {
            "stage_id",
            "stage_kind",
            "executor_id",
            "implementation_hash",
            "input_node_ids",
            "output_node_id",
            "expected_node_id",
            "expected_payload_node_ids",
        }
        if not isinstance(stage, dict) or set(stage) != required:
            raise _BlockedReplay(f"{expected_kind} stage has unknown or missing fields")
        if (
            stage.get("stage_kind") != expected_kind
            or not isinstance(stage.get("stage_id"), str)
            or not stage["stage_id"]
            or not isinstance(stage.get("executor_id"), str)
            or not stage["executor_id"]
            or not _is_sha256(stage.get("implementation_hash"))
            or not isinstance(stage.get("input_node_ids"), list)
            or any(not isinstance(item, str) for item in stage["input_node_ids"])
            or len(set(stage["input_node_ids"])) != len(stage["input_node_ids"])
            or not isinstance(stage.get("output_node_id"), str)
            or not stage["output_node_id"]
            or not isinstance(stage.get("expected_node_id"), str)
            or not isinstance(stage.get("expected_payload_node_ids"), list)
            or any(not isinstance(item, str) for item in stage["expected_payload_node_ids"])
        ):
            raise _BlockedReplay(f"{expected_kind} stage fields are invalid")
        normalized.append(stage)
    corrected = plan.get("corrected_overrides")
    if not isinstance(corrected, dict) or any(
        not isinstance(role, str) or not isinstance(node_id, str)
        for role, node_id in corrected.items()
    ):
        raise _BlockedReplay("corrected_overrides must map roles to artifact node IDs")
    return normalized


def _first_difference(expected: Any, actual: Any, path: str = "$") -> str | None:
    if type(expected) is not type(actual):
        return f"{path}: expected type {type(expected).__name__}, got {type(actual).__name__}"
    if isinstance(expected, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys | actual_keys, key=lambda value: str(value).encode("utf-8")):
            child_path = f"{path}/{key}"
            if key not in expected:
                return f"{child_path}: unexpected key"
            if key not in actual:
                return f"{child_path}: missing key"
            mismatch = _first_difference(expected[key], actual[key], child_path)
            if mismatch:
                return mismatch
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: expected {len(expected)} items, got {len(actual)}"
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            mismatch = _first_difference(left, right, f"{path}/{index}")
            if mismatch:
                return mismatch
        return None
    if expected != actual:
        return f"{path}: expected {expected!r}, got {actual!r}"
    return None


def _scientific_payload_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {field: payload[field] for field in SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS}


def _stage_projection(stage_kind: str, output: Any) -> Any:
    if stage_kind != "PAYLOADS":
        return output
    if not isinstance(output, dict) or set(output) != {"predictions", "payloads"}:
        raise _BlockedReplay("PAYLOADS executor must return exactly predictions and payloads")
    predictions = output["predictions"]
    payloads = output["payloads"]
    if not isinstance(predictions, list) or not isinstance(payloads, list):
        raise _BlockedReplay("PAYLOADS predictions and payloads must be arrays")
    projected_predictions = []
    for row in predictions:
        if not isinstance(row, dict):
            raise _BlockedReplay("PAYLOADS contains a non-object prediction row")
        projected_predictions.append(
            {
                "id": row.get("id"),
                "content_hash": row.get("content_hash"),
                "instrument_id": row.get("instrument_ref", {}).get("target_id"),
                "disposition": row.get("disposition"),
                "rank": row.get("rank"),
                "unscorable_reason": row.get("unscorable_reason"),
            }
        )
    projected_payloads = []
    for payload in payloads:
        if not isinstance(payload, dict):
            raise _BlockedReplay("PAYLOADS contains a non-object ScientificPredictionPayload")
        projected_payloads.append(_scientific_payload_projection(payload))
    return {"predictions": projected_predictions, "payloads": projected_payloads}


def _prediction_inventory(
    output: Mapping[str, Any],
    seal: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    rows = output.get("predictions")
    payloads = output.get("payloads")
    if not isinstance(rows, list) or not isinstance(payloads, list):
        raise ReplayError("PAYLOADS output must contain prediction and payload arrays")
    expected_refs = seal.get("ordered_prediction_refs")
    if not isinstance(expected_refs, list):
        raise ReplayError("PredictionSeal ordered_prediction_refs is malformed")
    payload_by_instrument: dict[str, dict[str, Any]] = {}
    payload_bytes: dict[str, bytes] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            raise ReplayError("payload output contains a non-object")
        validate_contract("ScientificPredictionPayload", payload)
        verify_content_hash("ScientificPredictionPayload", payload)
        instrument_id = payload["instrument_ref"]["target_id"]
        if instrument_id in payload_by_instrument:
            raise ReplayError(f"duplicate ScientificPredictionPayload for {instrument_id}")
        payload_by_instrument[instrument_id] = payload
        payload_bytes[instrument_id] = canonical_json_bytes(_scientific_payload_projection(payload))

    inventory: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ReplayError("prediction output contains a non-object")
        validate_contract("Prediction", row)
        verify_content_hash("Prediction", row)
        instrument_id = row["instrument_ref"]["target_id"]
        disposition = row["disposition"]
        if disposition == "SCORED":
            payload = payload_by_instrument.get(instrument_id)
            payload_hash: str | None = (
                scientific_payload_hash(payload) if payload is not None else None
            )
        else:
            payload_hash = None
        inventory.append(
            {
                "instrument_id": instrument_id,
                "prediction_ref": {
                    "target_schema_name": PREDICTION_SCHEMA,
                    "target_id": row["id"],
                    "content_hash": row["content_hash"],
                },
                "disposition": disposition,
                "rank": row["rank"],
                "unscorable_reason": row["unscorable_reason"],
                "scientific_payload_hash": payload_hash,
            }
        )
    return inventory, payload_bytes


class ReplayRunner:
    """Run pinned deterministic stages without providers or mutable DB handles.

    The trusted executor mapping is supplied by the application, never loaded
    from the replay bundle. Every callback executes with common socket and
    HTTP entry points denied. All data inputs are read from the local bundle.
    """

    def __init__(
        self,
        *,
        limits: ReplayLimits,
        environment_provider=capture_runtime_environment,
        clock=time.perf_counter,
    ) -> None:
        self._limits = limits
        self._environment_provider = environment_provider
        self._clock = clock

    def run(
        self,
        bundle_root: Path,
        *,
        replay_request: Mapping[str, Any],
        source_seal: Mapping[str, Any],
        artifact_manifest: Mapping[str, Any],
        executors: Mapping[str, StageExecutor],
    ) -> ReplayRunResult:
        started = self._clock()
        request = copy.deepcopy(dict(replay_request))
        seal = copy.deepcopy(dict(source_seal))
        manifest = copy.deepcopy(dict(artifact_manifest))
        self._validate_authority_contracts(request, seal, manifest)
        fallback_environment = request["environment_fingerprint"]

        try:
            file_bytes = _compare_inventory(Path(bundle_root), manifest, self._limits)
            _, graph = _control_file(manifest, file_bytes, GRAPH_SCHEMA)
            _, plan = _control_file(manifest, file_bytes, PLAN_SCHEMA)
            _, profile = _control_file(manifest, file_bytes, PROFILE_SCHEMA)
            closure, node_map, stage_plan, values = self._prepare(
                graph=graph,
                plan=plan,
                profile=profile,
                file_bytes=file_bytes,
                manifest=manifest,
                request=request,
                seal=seal,
                executors=executors,
            )
            if request["replay_mode"] == "COMPATIBILITY_EXPERIMENT":
                mode_verdict = "INCOMPLETE"
            elif request["replay_mode"] == "CORRECTED_DATA_SENSITIVITY":
                mode_verdict = "INCOMPLETE"
            else:
                mode_verdict = "MATCH"
            comparisons: list[dict[str, Any]] = []
            first_mismatch: str | None = None
            generated: dict[str, Any] = {}
            for stage in stage_plan:
                executor = executors[stage["executor_id"]]
                stage_inputs: dict[str, Any] = {}
                override_map = (
                    plan["corrected_overrides"]
                    if request["replay_mode"] == "CORRECTED_DATA_SENSITIVITY"
                    else {}
                )
                for node_id in stage["input_node_ids"]:
                    selected_id = node_id
                    input_node = node_map.get(node_id)
                    if input_node is not None and input_node["role"] in override_map:
                        selected_id = override_map[input_node["role"]]
                    if selected_id in generated:
                        stage_inputs[node_id] = copy.deepcopy(generated[selected_id])
                    elif selected_id in values:
                        stage_inputs[node_id] = copy.deepcopy(values[selected_id])
                    else:
                        raise _BlockedReplay(f"stage {stage['stage_id']} input is missing: {selected_id}")
                with _offline_stage_io():
                    actual_output = executor.execute(copy.deepcopy(stage_inputs))
                actual_bytes = canonical_json_bytes(actual_output)
                actual_output = _strict_json(actual_bytes, f"output from {stage['stage_id']}")
                generated[stage["output_node_id"]] = actual_output
                expected_node = node_map[stage["expected_node_id"]]
                expected = values[expected_node["node_id"]]
                actual_compare = _stage_projection(stage["stage_kind"], actual_output)
                expected_compare = _stage_projection(stage["stage_kind"], expected)
                actual_compare_bytes = canonical_json_bytes(actual_compare)
                expected_compare_bytes = canonical_json_bytes(expected_compare)
                stage_mismatch = _first_difference(expected_compare, actual_compare)
                stage_record = {
                    "stage_id": stage["stage_id"],
                    "stage_kind": stage["stage_kind"],
                    "expected_sha256": _sha256(expected_compare_bytes),
                    "actual_sha256": _sha256(actual_compare_bytes),
                    "matches": expected_compare_bytes == actual_compare_bytes,
                    "first_difference": stage_mismatch,
                }
                comparisons.append(stage_record)
                if first_mismatch is None and stage_mismatch is not None:
                    first_mismatch = f"{stage['stage_kind']} {stage_mismatch}"

            final_output = generated[stage_plan[-1]["output_node_id"]]
            inventory, payload_bytes = _prediction_inventory(final_output, seal)
            actual_inventory_hash = domain_separated_sha256(
                INVENTORY_HASH_DOMAIN, canonical_json_bytes(inventory)
            )
            expected_payload_mismatches = self._validate_expected_payloads(
                stage_plan[-1]["expected_payload_node_ids"],
                values,
                payload_bytes,
            )
            if first_mismatch is None and expected_payload_mismatches:
                first_mismatch = expected_payload_mismatches[0]
            if actual_inventory_hash != seal["payload_inventory_hash"] and first_mismatch is None:
                first_mismatch = "PredictionSeal.payload_inventory_hash differs"
            all_stage_matches = all(item["matches"] for item in comparisons)
            exact_match = (
                all_stage_matches
                and actual_inventory_hash == seal["payload_inventory_hash"]
                and not expected_payload_mismatches
            )
            if request["replay_mode"] == "EXACT":
                verdict = "MATCH" if exact_match else "MISMATCH"
            else:
                verdict = mode_verdict
                label = (
                    "corrected-data sensitivity is not an exact replay"
                    if request["replay_mode"] == "CORRECTED_DATA_SENSITIVITY"
                    else "compatibility experiment is not an exact-environment qualification"
                )
                first_mismatch = f"{label}; first observed delta: {first_mismatch or 'none'}"
            corrected_identity = None
            if request["replay_mode"] == "CORRECTED_DATA_SENSITIVITY":
                override_ids = sorted(set(plan["corrected_overrides"].values()))
                corrected_identity = domain_separated_sha256(
                    "qc2.corrected-data-replay-identity.v1",
                    canonical_json_bytes(
                        [
                            {
                                "node_id": node_id,
                                "sha256": next(
                                    record["sha256"]
                                    for record in manifest["files"]
                                    if record["relative_path"] == node_map[node_id]["relative_path"]
                                ),
                            }
                            for node_id in override_ids
                        ]
                    ),
                )
            receipt = self._receipt(
                request=request,
                seal=seal,
                manifest=manifest,
                expected_hash=seal["payload_inventory_hash"],
                actual_hash=actual_inventory_hash,
                expected_count=len(seal["ordered_prediction_refs"]),
                actual_count=len(final_output["predictions"]),
                environment_fingerprint=profile["fingerprint"],
                first_mismatch=first_mismatch,
                duration_ms=max(0, int((self._clock() - started) * 1000)),
                verdict=verdict,
            )
            return ReplayRunResult(
                receipt=receipt,
                stage_comparisons=tuple(comparisons),
                dependency_closure=closure,
                scientific_payload_bytes=payload_bytes,
                corrected_input_identity=corrected_identity,
            )
        except _BlockedReplay as exc:
            receipt = self._receipt(
                request=request,
                seal=seal,
                manifest=manifest,
                expected_hash=seal["payload_inventory_hash"],
                actual_hash=EMPTY_INVENTORY_HASH,
                expected_count=len(seal["ordered_prediction_refs"]),
                actual_count=0,
                environment_fingerprint=fallback_environment,
                first_mismatch=f"BLOCKED: {exc}",
                duration_ms=max(0, int((self._clock() - started) * 1000)),
                verdict="BLOCKED",
            )
            return ReplayRunResult(receipt, (), (), {}, None)
        except ReplayError as exc:
            receipt = self._receipt(
                request=request,
                seal=seal,
                manifest=manifest,
                expected_hash=seal["payload_inventory_hash"],
                actual_hash=EMPTY_INVENTORY_HASH,
                expected_count=len(seal["ordered_prediction_refs"]),
                actual_count=0,
                environment_fingerprint=fallback_environment,
                first_mismatch=f"BLOCKED: {exc}",
                duration_ms=max(0, int((self._clock() - started) * 1000)),
                verdict="BLOCKED",
            )
            return ReplayRunResult(receipt, (), (), {}, None)
        except Exception as exc:
            receipt = self._receipt(
                request=request,
                seal=seal,
                manifest=manifest,
                expected_hash=seal["payload_inventory_hash"],
                actual_hash=EMPTY_INVENTORY_HASH,
                expected_count=len(seal["ordered_prediction_refs"]),
                actual_count=0,
                environment_fingerprint=fallback_environment,
                first_mismatch=f"BLOCKED: replay stage failed: {type(exc).__name__}: {exc}",
                duration_ms=max(0, int((self._clock() - started) * 1000)),
                verdict="BLOCKED",
            )
            return ReplayRunResult(receipt, (), (), {}, None)

    @staticmethod
    def _validate_authority_contracts(
        request: Mapping[str, Any],
        seal: Mapping[str, Any],
        manifest: Mapping[str, Any],
    ) -> None:
        try:
            validate_contract("ReplayRequest", dict(request))
            validate_contract("PredictionSeal", dict(seal))
            verify_content_hash("PredictionSeal", dict(seal))
            validate_contract("ArtifactManifest", dict(manifest))
            verify_content_hash("ArtifactManifest", dict(manifest))
        except Exception as exc:
            raise ReplayInputError(f"invalid replay authority contract: {exc}") from exc
        if request["source_seal_ref"] != _reference(SEAL_SCHEMA, seal):
            raise ReplayInputError("ReplayRequest source_seal_ref does not match source seal")
        manifest_ref = _reference(MANIFEST_SCHEMA, manifest)
        if manifest_ref not in request["source_refs"]:
            raise ReplayInputError("ReplayRequest does not pin the ArtifactManifest")
        if request["replay_mode"] not in {
            "EXACT",
            "CORRECTED_DATA_SENSITIVITY",
            "COMPATIBILITY_EXPERIMENT",
        }:
            raise ReplayInputError("unsupported replay mode")

    def _prepare(
        self,
        *,
        graph: Mapping[str, Any],
        plan: Mapping[str, Any],
        profile: Mapping[str, Any],
        file_bytes: Mapping[str, bytes],
        manifest: Mapping[str, Any],
        request: Mapping[str, Any],
        seal: Mapping[str, Any],
        executors: Mapping[str, StageExecutor],
    ) -> tuple[tuple[str, ...], dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        nodes, roots = _validate_graph(graph)
        stage_plan = _validate_plan(plan)
        node_map = {node["node_id"]: node for node in nodes}
        if len(node_map) != len(nodes):
            raise _BlockedReplay("dependency graph repeats node IDs")
        corrected = plan["corrected_overrides"]
        closure_roots = list(roots)
        if request["replay_mode"] == "CORRECTED_DATA_SENSITIVITY":
            closure_roots.extend(corrected.values())
        for node in nodes:
            if node["role"] not in {"CONTROL", "EXPECTED_STAGE_OUTPUT", "EXPECTED_PAYLOAD"}:
                if node["relative_path"] not in {
                    record["relative_path"] for record in manifest["files"]
                }:
                    raise _BlockedReplay(f"dependency artifact is absent from ArtifactManifest: {node['node_id']}")
        try:
            closure = resolve_dependency_closure(
                nodes,
                closure_roots,
                max_depth=self._limits.max_dependency_depth,
            )
        except ReplayError as exc:
            raise _BlockedReplay(str(exc)) from exc
        roles_in_closure = {node_map[node_id]["role"] for node_id in closure}
        missing_roles = [role for role in REQUIRED_ROOT_ROLES if role not in roles_in_closure]
        if missing_roles:
            raise _BlockedReplay(f"required dependency roles are missing: {missing_roles}")
        if tuple(plan["required_root_roles"]) != REQUIRED_ROOT_ROLES:
            raise _BlockedReplay("replay plan root roles differ from task requirements")
        if "MEMORY_INDEX" not in roles_in_closure:
            raise _BlockedReplay("required model memory index is not in the sealed dependency closure")
        model_nodes = [node for node in nodes if node["role"] == "MODEL"]
        if not model_nodes:
            raise _BlockedReplay("required exact model dependency is missing")
        for model_node in model_nodes:
            model_closure = resolve_dependency_closure(
                nodes,
                [model_node["node_id"]],
                max_depth=self._limits.max_dependency_depth,
            )
            if not any(node_map[item]["role"] == "MEMORY_INDEX" for item in model_closure):
                raise _BlockedReplay(f"model dependency {model_node['node_id']} omits its memory index")

        manifest_by_path = {record["relative_path"]: record for record in manifest["files"]}
        values: dict[str, Any] = {}
        for node in nodes:
            path = node["relative_path"]
            if path not in file_bytes:
                raise _BlockedReplay(f"missing artifact data for dependency node {node['node_id']}")
            record = manifest_by_path.get(path)
            if record is None:
                raise _BlockedReplay(f"dependency node {node['node_id']} has no manifest entry")
            if node["contract_name"] is not None:
                contract = _object(_strict_json(file_bytes[path], path), path)
                try:
                    validate_contract(node["contract_name"], contract)
                    if "content_hash" in contract:
                        verify_content_hash(node["contract_name"], contract)
                except Exception as exc:
                    raise _BlockedReplay(f"invalid {node['contract_name']} at {path}: {exc}") from exc
                values[node["node_id"]] = contract
            elif record["media_type"] == "application/json" or record["media_type"].endswith("+json"):
                values[node["node_id"]] = _strict_json(file_bytes[path], path)
            else:
                values[node["node_id"]] = file_bytes[path]

        seal_nodes = [node for node in nodes if node["role"] == "SOURCE_SEAL"]
        if len(seal_nodes) != 1:
            raise _BlockedReplay("dependency graph must contain exactly one SOURCE_SEAL")
        if canonical_json_bytes(values[seal_nodes[0]["node_id"]]) != canonical_json_bytes(dict(seal)):
            raise _BlockedReplay("retained source seal differs from the ReplayRequest's source seal")

        profile_nodes = [node for node in nodes if node["role"] == "ENVIRONMENT_PROFILE"]
        if len(profile_nodes) != 1:
            raise _BlockedReplay("dependency graph must contain exactly one ENVIRONMENT_PROFILE")
        profile_value = values[profile_nodes[0]["node_id"]]
        if not isinstance(profile_value, dict) or canonical_json_bytes(profile_value) != canonical_json_bytes(dict(profile)):
            raise _BlockedReplay("environment profile node and control profile differ")
        profile_body = dict(profile)
        fingerprint = profile_body.pop("fingerprint", None)
        if (
            profile.get("schema_name") != PROFILE_SCHEMA
            or profile.get("schema_version") != "1.0"
            or not _is_sha256(fingerprint)
            or environment_fingerprint(profile_body) != fingerprint
            or request["environment_fingerprint"] != fingerprint
        ):
            raise _BlockedReplay("ReplayRequest and qualified environment profile do not match")
        if dict(profile.get("runtime", {})) != self._environment_provider():
            raise _BlockedReplay("runtime environment does not match the qualified profile")

        executor_hashes: dict[str, str] = {}
        prior_outputs: set[str] = set()
        prior_output: str | None = None
        roles_by_id = {node["node_id"]: node["role"] for node in nodes}
        for role, node_id in corrected.items():
            if node_id not in node_map or node_map[node_id]["role"] != f"CORRECTED_{role}":
                raise _BlockedReplay(f"corrected override for {role} is not a retained corrected-data node")
        if request["replay_mode"] == "CORRECTED_DATA_SENSITIVITY":
            if not corrected:
                raise _BlockedReplay("corrected-data replay requires an explicit corrected input override")
            if "MARKET_HISTORY" not in corrected:
                raise _BlockedReplay("corrected-data replay must override retained market history")
        elif corrected:
            raise _BlockedReplay("corrected-data overrides are only valid in sensitivity replay mode")
        for stage in stage_plan:
            executor = executors.get(stage["executor_id"])
            if executor is None:
                raise _BlockedReplay(f"trusted stage executor is unavailable: {stage['executor_id']}")
            if (
                executor.stage_kind != stage["stage_kind"]
                or executor.implementation_hash != stage["implementation_hash"]
                or executor.executor_id != stage["executor_id"]
            ):
                raise _BlockedReplay(f"trusted stage binding differs for {stage['stage_id']}")
            executor_hashes[executor.executor_id] = executor.implementation_hash
            for input_id in stage["input_node_ids"]:
                if input_id not in node_map and input_id not in prior_outputs:
                    raise _BlockedReplay(f"{stage['stage_id']} references missing input {input_id}")
                if input_id in node_map and input_id not in closure:
                    raise _BlockedReplay(f"{stage['stage_id']} input is outside dependency closure: {input_id}")
            if prior_output is not None and prior_output not in stage["input_node_ids"]:
                raise _BlockedReplay(
                    f"{stage['stage_kind']} stage does not consume the preceding stage output"
                )
            if stage["expected_node_id"] not in node_map:
                raise _BlockedReplay(f"{stage['stage_id']} lacks its expected checkpoint")
            if node_map[stage["expected_node_id"]]["role"] != "EXPECTED_STAGE_OUTPUT":
                raise _BlockedReplay(f"{stage['stage_id']} checkpoint has the wrong artifact role")
            for payload_node_id in stage["expected_payload_node_ids"]:
                if payload_node_id not in node_map or node_map[payload_node_id]["role"] != "EXPECTED_PAYLOAD":
                    raise _BlockedReplay(f"{stage['stage_id']} has an invalid expected payload reference")
            needed_roles = {
                "UNIVERSE": {"MARKET_HISTORY", "CANDIDATE_CENSUS", "UNIVERSE_POLICY"},
                "FEATURES": {"FEATURE_REGISTRY"},
                "PROTOCOLS": {"PROTOCOL_REGISTRY"},
                "HEADS": {"MODEL", "MEMORY_INDEX"},
                "SCORE": {"SCORE_MANIFEST"},
                "RANK": set(),
                "PAYLOADS": {"SOURCE_SEAL"},
            }[stage["stage_kind"]]
            input_roles = {roles_by_id[item] for item in stage["input_node_ids"] if item in roles_by_id}
            if not needed_roles.issubset(input_roles):
                raise _BlockedReplay(
                    f"{stage['stage_kind']} stage omits required inputs: {sorted(needed_roles - input_roles)}"
                )
            prior_output = stage["output_node_id"]
            prior_outputs.add(stage["output_node_id"])
        if dict(profile.get("executor_hashes", {})) != dict(sorted(executor_hashes.items())):
            raise _BlockedReplay("qualified environment profile does not bind the exact stage executor hashes")
        if request["replay_mode"] == "CORRECTED_DATA_SENSITIVITY":
            for role, corrected_id in corrected.items():
                original_nodes = [node for node in nodes if node["role"] == role]
                if len(original_nodes) != 1:
                    raise _BlockedReplay(f"corrected replay requires one original {role} node")
                original_record = manifest_by_path[original_nodes[0]["relative_path"]]
                corrected_record = manifest_by_path[node_map[corrected_id]["relative_path"]]
                if original_record["sha256"] == corrected_record["sha256"]:
                    raise _BlockedReplay(f"corrected {role} input must have a distinct content hash")
                corrected_ref = node_map[corrected_id]
                if corrected_ref["contract_name"] is not None:
                    contract = values[corrected_id]
                    ref = _reference(contract["schema_name"], contract)
                    if ref not in request["source_refs"]:
                        raise _BlockedReplay(f"ReplayRequest does not pin corrected input {corrected_id}")
        return closure, node_map, stage_plan, values

    @staticmethod
    def _validate_expected_payloads(
        expected_node_ids: Sequence[str],
        values: Mapping[str, Any],
        actual_payload_bytes: Mapping[str, bytes],
    ) -> list[str]:
        expected_by_instrument: dict[str, bytes] = {}
        for node_id in expected_node_ids:
            payload = values[node_id]
            validate_contract("ScientificPredictionPayload", payload)
            verify_content_hash("ScientificPredictionPayload", payload)
            instrument_id = payload["instrument_ref"]["target_id"]
            if instrument_id in expected_by_instrument:
                raise _BlockedReplay(f"duplicate expected payload for {instrument_id}")
            expected_by_instrument[instrument_id] = canonical_json_bytes(
                _scientific_payload_projection(payload)
            )
        if len(expected_by_instrument) != len(actual_payload_bytes):
            return [
                "ScientificPredictionPayload count differs: "
                f"expected {len(expected_by_instrument)}, got {len(actual_payload_bytes)}"
            ]
        for instrument_id in sorted(set(expected_by_instrument) | set(actual_payload_bytes)):
            expected = expected_by_instrument.get(instrument_id)
            actual = actual_payload_bytes.get(instrument_id)
            if expected != actual:
                return [f"ScientificPredictionPayload[{instrument_id}] scientific bytes differ"]
        return []

    @staticmethod
    def _receipt(
        *,
        request: Mapping[str, Any],
        seal: Mapping[str, Any],
        manifest: Mapping[str, Any],
        expected_hash: str,
        actual_hash: str,
        expected_count: int,
        actual_count: int,
        environment_fingerprint: str,
        first_mismatch: str | None,
        duration_ms: int,
        verdict: str,
    ) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "schema_name": RECEIPT_SCHEMA,
            "schema_version": "1.0",
            "id": new_uuidv7(),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "owning_authority": "validation",
            "evidence_class": request["evidence_class"],
            "environment_namespace": request["environment_namespace"],
            "source_refs": [
                _reference(SEAL_SCHEMA, seal),
                _reference(MANIFEST_SCHEMA, manifest),
            ],
            "request_ref": {
                "target_schema_name": REQUEST_SCHEMA,
                "target_id": request["id"],
            },
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "expected_count": expected_count,
            "actual_count": actual_count,
            "environment_fingerprint": environment_fingerprint,
            "first_mismatch": first_mismatch,
            "duration_ms": duration_ms,
            "verdict": verdict,
        }
        validate_contract("ReplayReceipt", receipt)
        return receipt
