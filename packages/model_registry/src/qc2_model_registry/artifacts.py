"""Safe, content-addressed model-artifact staging."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import threading
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from qc2_contracts.runtime import (
    artifact_inventory_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    validate_contract,
    verify_content_hash,
)


MODEL_SCHEMA = "qc2.models_prediction.ModelManifest.v1"
ARTIFACT_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"
_ALLOWED_FILE_SCHEMAS = {
    "qc2.apexlab.SafeModelArtifact.v1",
    "qc2.apexlab.TrainingEnvironment.v1",
    "qc2.apexlab.FrozenHyperparameterSpace.v1",
}
_MODEL_FILES = {"model.json", "environment.json"}
_HYPERPARAMETER_FILE = "hyperparameters.json"
_SHA256_LENGTH = 64


class ArtifactVerificationError(ValueError):
    """An artifact bundle is malformed, unsafe, or does not match its manifest."""


@dataclass(frozen=True, slots=True)
class BlobWriteReceipt:
    digest: str
    object_key: str
    backend: str
    durable: bool
    durability_receipt: str | None
    staged_at: str


class ArtifactBlobStore(Protocol):
    """Content-addressed byte storage; production stores must acknowledge durability."""

    @property
    def durable(self) -> bool: ...

    @property
    def backend_name(self) -> str: ...

    def put(self, digest: str, content: bytes) -> BlobWriteReceipt: ...

    def get(self, digest: str) -> bytes: ...


class MemoryArtifactBlobStore:
    """Fixture-only blob store. It deliberately cannot satisfy production loading."""

    durable = False
    backend_name = "fixture_memory"

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self._lock = threading.RLock()

    def put(self, digest: str, content: bytes) -> BlobWriteReceipt:
        _verify_digest_and_bytes(digest, content)
        with self._lock:
            existing = self._objects.get(digest)
            if existing is not None and existing != content:
                raise ArtifactVerificationError("content-addressed blob overwrite refused")
            self._objects.setdefault(digest, bytes(content))
        return BlobWriteReceipt(
            digest, digest, self.backend_name, False, None, _utc_now()
        )

    def get(self, digest: str) -> bytes:
        _validate_digest(digest)
        with self._lock:
            try:
                content = self._objects[digest]
            except KeyError as exc:
                raise ArtifactVerificationError("content-addressed blob is missing") from exc
        _verify_digest_and_bytes(digest, content)
        return bytes(content)


class FileSystemArtifactBlobStore:
    """Atomic local CAS for development and acceptance tests, never production storage."""

    durable = False
    backend_name = "local_cache"

    def __init__(self, root: str | Path) -> None:
        supplied = Path(root).expanduser().absolute()
        if supplied.exists() and supplied.is_symlink():
            raise ArtifactVerificationError("artifact-store root must not be a symlink")
        supplied.mkdir(parents=True, exist_ok=True)
        self._root = supplied.resolve(strict=True)
        if not self._root.is_dir():
            raise ArtifactVerificationError("artifact-store root must be a directory")
        self._lock = threading.RLock()

    def put(self, digest: str, content: bytes) -> BlobWriteReceipt:
        _verify_digest_and_bytes(digest, content)
        target = self._root / digest
        with self._lock:
            if target.exists() or target.is_symlink():
                self._verify_existing(target, digest, content)
            else:
                fd, temporary_name = tempfile.mkstemp(prefix=".stage-", dir=self._root)
                temporary = Path(temporary_name)
                try:
                    with os.fdopen(fd, "wb") as staged:
                        staged.write(content)
                        staged.flush()
                        os.fsync(staged.fileno())
                        os.fchmod(staged.fileno(), 0o400)
                    try:
                        os.link(temporary, target, follow_symlinks=False)
                    except FileExistsError:
                        self._verify_existing(target, digest, content)
                    finally:
                        temporary.unlink(missing_ok=True)
                except Exception:
                    temporary.unlink(missing_ok=True)
                    raise
        return BlobWriteReceipt(
            digest, digest, self.backend_name, False, None, _utc_now()
        )

    def get(self, digest: str) -> bytes:
        _validate_digest(digest)
        path = self._root / digest
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, os.O_RDONLY | nofollow)
        except OSError as exc:
            raise ArtifactVerificationError("content-addressed blob is missing or unsafe") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ArtifactVerificationError("content-addressed object is not a regular file")
            with os.fdopen(fd, "rb", closefd=False) as source:
                content = source.read()
        finally:
            os.close(fd)
        _verify_digest_and_bytes(digest, content)
        return content

    def _verify_existing(self, path: Path, digest: str, expected: bytes) -> None:
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, os.O_RDONLY | nofollow)
        except OSError as exc:
            raise ArtifactVerificationError("existing content-addressed object is unsafe") from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ArtifactVerificationError("existing content-addressed object is not a file")
            with os.fdopen(fd, "rb", closefd=False) as source:
                actual = source.read()
        finally:
            os.close(fd)
        _verify_digest_and_bytes(digest, actual)
        if actual != expected:
            raise ArtifactVerificationError("content-addressed blob overwrite refused")


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    manifest: Mapping[str, Any]
    files: Mapping[str, bytes]

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest", _freeze_json(self.manifest))
        if any(not isinstance(path, str) or not isinstance(data, bytes) for path, data in self.files.items()):
            raise ArtifactVerificationError("artifact bundle must map paths to immutable bytes")
        object.__setattr__(self, "files", _freeze_json(dict(self.files)))


@dataclass(frozen=True, slots=True)
class VerifiedArtifactBundle:
    manifest: Mapping[str, Any]
    blob_hashes: Mapping[str, str]
    total_bytes: int


def artifact_verification_hash(
    manifest: Mapping[str, Any],
    *,
    storage_backend: str,
    durability_receipt: str | None,
) -> str:
    """Bind full byte verification to the exact manifest and durable store receipt."""
    value = _as_object(manifest, "ArtifactManifest")
    ordered_files = sorted(
        value["files"],
        key=lambda record: record["relative_path"].encode("utf-8"),
    )
    payload = {
        "manifest_id": value["id"],
        "manifest_content_hash": value["content_hash"],
        "files": ordered_files,
        "storage_backend": storage_backend,
        "durability_receipt": durability_receipt or "",
    }
    return domain_separated_sha256(
        "qc2.model-artifact-verification.v1",
        canonical_json_bytes(payload),
    )


def storage_acknowledgment(receipts: Sequence[BlobWriteReceipt]) -> str | None:
    """Aggregate provider acknowledgments without hiding the per-object receipts."""
    if not receipts or any(
        not receipt.durable or not receipt.durability_receipt
        for receipt in receipts
    ):
        return None
    rows = sorted(
        (
            {
                "sha256": receipt.digest,
                "object_key": receipt.object_key,
                "durability_receipt": receipt.durability_receipt,
            }
            for receipt in receipts
        ),
        key=lambda row: (row["sha256"], row["object_key"]),
    )
    return domain_separated_sha256(
        "qc2.model-artifact-storage-ack.v1",
        canonical_json_bytes(rows),
    )


def verify_artifact_bundle(
    raw_manifest: Mapping[str, Any],
    raw_files: Mapping[str, bytes],
    *,
    max_artifact_bytes: int,
    model_manifest: Mapping[str, Any] | None = None,
) -> VerifiedArtifactBundle:
    """Verify all declared bytes and reject archives, executable formats, and unsafe JSON."""
    if type(max_artifact_bytes) is not int or max_artifact_bytes < 1:
        raise ArtifactVerificationError("an explicit positive artifact-size budget is required")
    manifest = _as_object(raw_manifest, "ArtifactManifest")
    files = dict(raw_files)
    try:
        validate_contract("ArtifactManifest", manifest)
        verify_content_hash("ArtifactManifest", manifest)
    except (TypeError, ValueError, KeyError) as exc:
        raise ArtifactVerificationError(f"ArtifactManifest verification failed: {exc}") from exc
    if manifest["owning_authority"] != "model_registry":
        raise ArtifactVerificationError("artifact manifests must be owned by model_registry")
    if not files:
        raise ArtifactVerificationError("empty artifact bundles are not loadable")
    if any(not isinstance(path, str) or not isinstance(value, bytes) for path, value in files.items()):
        raise ArtifactVerificationError("artifact inputs must be a path-to-bytes mapping")

    records: dict[str, Mapping[str, Any]] = {}
    for record in manifest["files"]:
        path = record["relative_path"]
        _validate_relative_path(path)
        if path in records:
            raise ArtifactVerificationError("artifact manifest repeats a normalized path")
        records[path] = record
    if set(records) != set(files):
        raise ArtifactVerificationError("supplied file inventory differs from ArtifactManifest")
    if manifest["inventory_hash"] != artifact_inventory_hash(manifest["files"]):
        raise ArtifactVerificationError("artifact inventory hash does not match its file records")

    total_bytes = 0
    verified_hashes: dict[str, str] = {}
    parsed: dict[str, Mapping[str, Any]] = {}
    for path, content in files.items():
        _validate_relative_path(path)
        record = records[path]
        if record["media_type"] != "application/json":
            raise ArtifactVerificationError("only allowlisted JSON data artifacts are accepted")
        if record["schema_name"] not in _ALLOWED_FILE_SCHEMAS or record["schema_version"] != "1.0":
            raise ArtifactVerificationError("artifact file schema is not on the safe-format allowlist")
        if not path.endswith(".json"):
            raise ArtifactVerificationError("JSON artifacts must use a .json relative path")
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != record["sha256"] or len(content) != record["length_bytes"]:
            raise ArtifactVerificationError(f"artifact bytes do not match manifest record: {path}")
        total_bytes += len(content)
        if total_bytes > max_artifact_bytes:
            raise ArtifactVerificationError("artifact bundle exceeds its explicit byte budget")
        parsed[path] = _parse_safe_json(content, record["schema_name"], path)
        verified_hashes[path] = actual_hash

    if model_manifest is not None:
        _verify_model_bundle(manifest, files, parsed, model_manifest)
    elif set(files) not in (_MODEL_FILES, {_HYPERPARAMETER_FILE}):
        raise ArtifactVerificationError(
            "non-primary artifact bundles must contain only hyperparameters.json"
        )
    elif set(files) == {_HYPERPARAMETER_FILE}:
        parameter = parsed[_HYPERPARAMETER_FILE]
        if parameter.get("schema_name") != "qc2.apexlab.FrozenHyperparameterSpace.v1":
            raise ArtifactVerificationError("hyperparameter file has the wrong safe schema")

    return VerifiedArtifactBundle(
        manifest=_freeze_json(manifest),
        blob_hashes=_freeze_json(verified_hashes),
        total_bytes=total_bytes,
    )


def _verify_model_bundle(
    artifact_manifest: Mapping[str, Any],
    files: Mapping[str, bytes],
    parsed: Mapping[str, Mapping[str, Any]],
    raw_model: Mapping[str, Any],
) -> None:
    model = _as_object(raw_model, "ModelManifest")
    if model.get("safe_format") != "json":
        raise ArtifactVerificationError("ModelManifest.safe_format must be json")
    if set(files) != _MODEL_FILES:
        raise ArtifactVerificationError("model bundle must contain exactly model.json and environment.json")
    if not _ref_matches(
        model.get("artifact_manifest_ref", {}),
        _contract_ref(ARTIFACT_SCHEMA, artifact_manifest),
    ):
        raise ArtifactVerificationError("ModelManifest does not bind the supplied model artifact")
    if (
        artifact_manifest["evidence_class"] != model.get("evidence_class")
        or artifact_manifest["environment_namespace"] != model.get("environment_namespace")
    ):
        raise ArtifactVerificationError("model artifact evidence context differs from its manifest")
    if parsed["model.json"].get("schema_name") != "qc2.apexlab.SafeModelArtifact.v1":
        raise ArtifactVerificationError("model.json has the wrong allowlisted schema")
    if parsed["environment.json"].get("schema_name") != "qc2.apexlab.TrainingEnvironment.v1":
        raise ArtifactVerificationError("environment.json has the wrong allowlisted schema")

    try:
        from qc2_candidate_evaluator.inference import (
            load_candidate_model,
            validate_environment_manifest,
        )

        load_candidate_model(
            files["model.json"],
            model,
            model["dataset_ref"],
            model["split_ref"],
        )
        validate_environment_manifest(files["environment.json"], model)
    except (ImportError, KeyError, TypeError, ValueError) as exc:
        raise ArtifactVerificationError(f"safe model interpreter rejected the artifact: {exc}") from exc


def _parse_safe_json(content: bytes, schema_name: str, path: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_object,
        )
    except ArtifactVerificationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ArtifactVerificationError(f"{path} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ArtifactVerificationError(f"{path} must contain a JSON object")
    if value.get("schema_name") != schema_name or value.get("schema_version") != "1.0":
        raise ArtifactVerificationError(f"{path} schema metadata differs from its manifest")
    _check_json_complexity(value, max_depth=64, max_nodes=1_000_000)
    return value


def _check_json_complexity(value: Any, *, max_depth: int, max_nodes: int) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    count = 0
    while stack:
        current, depth = stack.pop()
        count += 1
        if depth > max_depth or count > max_nodes:
            raise ArtifactVerificationError("JSON artifact exceeds structural safety limits")
        if isinstance(current, Mapping):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactVerificationError(f"JSON artifact repeats key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ArtifactVerificationError(f"JSON artifact contains forbidden constant {value}")


def _validate_relative_path(path: str) -> None:
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or unicodedata.normalize("NFC", path) != path
    ):
        raise ArtifactVerificationError("artifact path is not a normalized relative POSIX path")
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != path
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or any(":" in part for part in parsed.parts)
    ):
        raise ArtifactVerificationError("artifact path is absolute, ambiguous, or traverses directories")


def _validate_digest(digest: str) -> None:
    if not isinstance(digest, str) or len(digest) != _SHA256_LENGTH:
        raise ArtifactVerificationError("blob key must be a lowercase SHA-256 digest")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ArtifactVerificationError("blob key must be a lowercase SHA-256 digest")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _verify_digest_and_bytes(digest: str, content: bytes) -> None:
    _validate_digest(digest)
    if not isinstance(content, bytes) or hashlib.sha256(content).hexdigest() != digest:
        raise ArtifactVerificationError("blob bytes do not match their content address")


def _as_object(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = _thaw_json(raw)
    if not isinstance(value, dict):
        raise ArtifactVerificationError(f"{name} must be a JSON object")
    return value


def _contract_ref(schema_name: str, payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": str(payload["id"]),
        "content_hash": str(payload["content_hash"]),
    }


def _ref_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(actual.get(key) == expected.get(key) for key in (
        "target_schema_name",
        "target_id",
        "content_hash",
    ))


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        from types import MappingProxyType

        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value
