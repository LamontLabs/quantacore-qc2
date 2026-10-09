"""Resource-limited subprocess probe for the allowlisted JSON model interpreter."""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any


class CandidateModelUnsafeError(ValueError):
    """The safe interpreter rejected candidate bytes or provenance."""


class CandidateSandboxError(ValueError):
    """The isolated probe could not complete within its configured boundary."""


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    max_wall_seconds: float
    max_cpu_seconds: int
    max_memory_bytes: int

    def __post_init__(self) -> None:
        if self.max_wall_seconds <= 0 or self.max_cpu_seconds <= 0:
            raise ValueError("sandbox time limits must be positive")
        if self.max_memory_bytes < 64 * 1024 * 1024:
            raise ValueError("sandbox memory limit must be at least 64 MiB")


@dataclass(frozen=True, slots=True)
class CandidateProbeResult:
    family: str
    task: str
    deterministic: bool
    probe_hash: str


_WORKER = r"""
import base64
import hashlib
import json
import os
import socket
import subprocess
import sys

candidate_root, contracts_root, *trusted_package_roots = sys.argv[1:]
sys.path.extend(trusted_package_roots)
sys.path.insert(0, contracts_root)
sys.path.insert(0, candidate_root)

from qc2_candidate_evaluator.inference import (  # noqa: E402
    infer_predictions,
    load_candidate_model,
    validate_environment_manifest,
)
from qc2_candidate_evaluator.models import EvaluationError  # noqa: E402


def _deny(*_args, **_kwargs):
    raise PermissionError("network and child-process access are disabled")


socket.socket = _deny
socket.create_connection = _deny
subprocess.Popen = _deny
subprocess.run = _deny
os.system = _deny
os.popen = _deny


class _ProbeRow:
    def __init__(self, features):
        self.features = features


try:
    request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    model_bytes = base64.b64decode(request["model"], validate=True)
    environment_bytes = base64.b64decode(request["environment"], validate=True)
    model_manifest = request["model_manifest"]
    dataset_ref = request["dataset_ref"]
    split_ref = request["split_ref"]
    validate_environment_manifest(environment_bytes, model_manifest)
    model = load_candidate_model(model_bytes, model_manifest, dataset_ref, split_ref)
    rows = [
        _ProbeRow({
            feature_id: str(mean)
            for feature_id, mean in zip(model.feature_ids, model.means)
        }),
        _ProbeRow({
            feature_id: str(mean + scale)
            for feature_id, mean, scale in zip(
                model.feature_ids, model.means, model.scales
            )
        }),
    ]
    first = tuple(str(value) for value in infer_predictions(model, rows))
    second = tuple(str(value) for value in infer_predictions(model, rows))
    if first != second or len(first) != 2:
        print(json.dumps({"ok": False, "kind": "MODEL_UNSAFE"}))
        raise SystemExit(0)
    digest = hashlib.sha256(
        json.dumps(first, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    print(json.dumps({
        "ok": True,
        "family": model.family,
        "task": model.task,
        "deterministic": True,
        "probe_hash": digest,
    }, sort_keys=True, separators=(",", ":")))
except EvaluationError:
    print(json.dumps({"ok": False, "kind": "MODEL_UNSAFE"}))
except BaseException:
    print(json.dumps({"ok": False, "kind": "SANDBOX_FAILURE"}))
"""


def probe_candidate_model(
    *,
    model_bytes: bytes,
    environment_bytes: bytes,
    model_manifest: Mapping[str, Any],
    dataset_ref: Mapping[str, Any],
    split_ref: Mapping[str, Any],
    limits: SandboxLimits,
) -> CandidateProbeResult:
    """Load and probe verified JSON bytes without running bundle-provided code."""
    candidate_root = _source_root("qc2_candidate_evaluator.inference")
    contracts_root = _source_root("qc2_contracts.runtime")
    trusted_package_roots = _trusted_package_roots()
    request = {
        "model": base64.b64encode(model_bytes).decode("ascii"),
        "environment": base64.b64encode(environment_bytes).decode("ascii"),
        "model_manifest": _plain(model_manifest),
        "dataset_ref": _plain(dataset_ref),
        "split_ref": _plain(split_ref),
    }
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                _WORKER,
                str(candidate_root),
                str(contracts_root),
                *map(str, trusted_package_roots),
            ],
            input=json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd="/",
            env={"LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=limits.max_wall_seconds,
            check=False,
            close_fds=True,
            start_new_session=True,
            preexec_fn=lambda: _apply_limits(limits),
        )
    except subprocess.TimeoutExpired as exc:
        raise CandidateSandboxError("candidate probe exceeded its wall-time limit") from exc
    except (OSError, ValueError) as exc:
        raise CandidateSandboxError("candidate probe process could not be started") from exc
    if completed.returncode != 0:
        raise CandidateSandboxError("candidate probe process exited outside its protocol")
    try:
        result = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateSandboxError("candidate probe returned malformed output") from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        if isinstance(result, dict) and result.get("kind") == "MODEL_UNSAFE":
            raise CandidateModelUnsafeError("allowlisted candidate interpreter rejected the model")
        raise CandidateSandboxError("candidate probe failed inside the isolated process")
    if (
        set(result) != {"ok", "family", "task", "deterministic", "probe_hash"}
        or not isinstance(result["family"], str)
        or result["task"] not in {"REGRESSION", "BINARY_CLASSIFICATION"}
        or result["deterministic"] is not True
        or not isinstance(result["probe_hash"], str)
        or len(result["probe_hash"]) != 64
    ):
        raise CandidateSandboxError("candidate probe output violated its response schema")
    return CandidateProbeResult(
        family=result["family"],
        task=result["task"],
        deterministic=True,
        probe_hash=result["probe_hash"],
    )


def _source_root(module_name: str) -> Path:
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ModuleNotFoundError, ValueError) as exc:
        raise CandidateSandboxError(f"trusted module {module_name!r} is unavailable") from exc
    if spec is None or spec.origin is None:
        raise CandidateSandboxError(f"trusted module {module_name!r} is unavailable")
    return Path(spec.origin).resolve().parents[1]


def _trusted_package_roots() -> tuple[Path, ...]:
    """Resolve isolated import roots from the installed contract validator stack."""
    roots: set[Path] = set()
    for module_name in ("jsonschema", "attrs", "referencing", "rpds"):
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, ModuleNotFoundError, ValueError) as exc:
            raise CandidateSandboxError(
                f"trusted runtime dependency {module_name!r} is unavailable"
            ) from exc
        if spec is None:
            raise CandidateSandboxError(
                f"trusted runtime dependency {module_name!r} is unavailable"
            )
        locations = list(spec.submodule_search_locations or ())
        if not locations and spec.origin is not None:
            locations = [spec.origin]
        module_roots: set[Path] = set()
        for location in locations:
            path = Path(location).resolve()
            for parent in (path, *path.parents):
                if parent.name in {"site-packages", "dist-packages"}:
                    module_roots.add(parent)
                    break
        if not module_roots:
            raise CandidateSandboxError(
                f"trusted runtime dependency {module_name!r} has no installed package root"
            )
        roots.update(module_roots)
    return tuple(sorted(roots))


def _apply_limits(limits: SandboxLimits) -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (limits.max_memory_bytes, limits.max_memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (limits.max_cpu_seconds, limits.max_cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
