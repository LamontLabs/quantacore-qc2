"""Restricted deterministic ZIP framing for signed promotion bundles."""

from __future__ import annotations

import io
import json
import stat
import unicodedata
import zipfile
from pathlib import PurePosixPath
from typing import Any, Mapping

from qc2_contracts.runtime import canonical_json_bytes, parse_json_strict

from .limits import BundleLimits, PromotionBundleError

MANIFEST_PATH = ".qc2/manifest.json"
INVENTORY_PATH = ".qc2/inventory.json"
SIGNATURE_PATH = ".qc2/signature.json"
METADATA_PATHS = frozenset({MANIFEST_PATH, INVENTORY_PATH, SIGNATURE_PATH})


def validate_relative_path(path: Any, *, allow_metadata: bool = False) -> str:
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or "\x00" in path
        or unicodedata.normalize("NFC", path) != path
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in path)
    ):
        raise PromotionBundleError("bundle path is not normalized relative POSIX text")
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != path
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or any(":" in part for part in parsed.parts)
    ):
        raise PromotionBundleError("bundle path is absolute, ambiguous, or traverses directories")
    if not allow_metadata and (path in METADATA_PATHS or parsed.parts[0] == ".qc2"):
        raise PromotionBundleError("payload path collides with reserved bundle metadata")
    try:
        path.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PromotionBundleError("bundle path contains invalid Unicode") from exc
    return path


def encode_archive(
    manifest: Mapping[str, Any],
    inventory: list[dict[str, Any]],
    signature: Mapping[str, Any],
    files: Mapping[str, bytes],
    limits: BundleLimits,
) -> bytes:
    entries: dict[str, bytes] = {
        MANIFEST_PATH: canonical_json_bytes(dict(manifest)),
        INVENTORY_PATH: canonical_json_bytes(inventory),
        SIGNATURE_PATH: canonical_json_bytes(dict(signature)),
    }
    for path, content in files.items():
        validate_relative_path(path)
        if path in entries or not isinstance(content, bytes):
            raise PromotionBundleError("payload path or bytes are invalid")
        entries[path] = content
    if len(entries) > limits.max_entries:
        raise PromotionBundleError("bundle exceeds its explicit entry-count limit")
    if any(len(content) > limits.max_file_bytes for content in entries.values()):
        raise PromotionBundleError("archive member exceeds its explicit file-size limit")
    if sum(map(len, entries.values())) > limits.max_uncompressed_bytes:
        raise PromotionBundleError("bundle exceeds its explicit unpacked-size limit")

    output = io.BytesIO()
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
            archive.comment = b""
            for path in sorted(entries, key=lambda value: value.encode("utf-8")):
                info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, entries[path])
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise PromotionBundleError(f"could not encode promotion bundle archive: {exc}") from exc

    result = output.getvalue()
    if len(result) > limits.max_archive_bytes:
        raise PromotionBundleError("bundle exceeds its explicit archive-size limit")
    return result


def decode_archive(
    archive_bytes: bytes,
    limits: BundleLimits,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, bytes]]:
    if not isinstance(archive_bytes, bytes) or not archive_bytes:
        raise PromotionBundleError("promotion bundle archive must be non-empty bytes")
    if len(archive_bytes) > limits.max_archive_bytes:
        raise PromotionBundleError("bundle exceeds its explicit archive-size limit")

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            if archive.comment:
                raise PromotionBundleError("ZIP archive comments are not permitted")
            infos = archive.infolist()
            if not infos or len(infos) > limits.max_entries:
                raise PromotionBundleError("bundle has an invalid number of archive entries")

            names: dict[str, zipfile.ZipInfo] = {}
            normalized_names: set[str] = set()
            total_uncompressed = 0
            for info in infos:
                path = validate_relative_path(info.filename, allow_metadata=True)
                if info.is_dir() or path in names:
                    raise PromotionBundleError("archive contains a directory or duplicate path")
                normalized_path = unicodedata.normalize("NFC", path)
                if normalized_path in normalized_names:
                    raise PromotionBundleError("archive contains duplicate normalized paths")
                normalized_names.add(normalized_path)
                if info.flag_bits & 0x1:
                    raise PromotionBundleError("encrypted ZIP members are not permitted")
                if info.extra:
                    raise PromotionBundleError("ZIP member extra fields are not permitted")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise PromotionBundleError("ZIP compression method is not permitted")
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if file_type not in {0, stat.S_IFREG} or mode & 0o111:
                    raise PromotionBundleError("archive contains a link, special file, or executable")
                if info.file_size < 0 or info.file_size > limits.max_file_bytes:
                    raise PromotionBundleError("archive member exceeds its explicit file-size limit")
                if info.file_size and (
                    info.compress_size < 1
                    or info.file_size > info.compress_size * limits.max_compression_ratio
                ):
                    raise PromotionBundleError("archive member exceeds its compression-ratio limit")
                total_uncompressed += info.file_size
                if total_uncompressed > limits.max_uncompressed_bytes:
                    raise PromotionBundleError("bundle exceeds its explicit unpacked-size limit")
                names[path] = info

            if not METADATA_PATHS.issubset(names):
                raise PromotionBundleError("archive is missing required bundle metadata")
            control_values: dict[str, Any] = {}
            for path in METADATA_PATHS:
                info = names[path]
                raw = archive.read(info)
                if len(raw) != info.file_size:
                    raise PromotionBundleError("archive member size differs from its ZIP directory")
                value = parse_json_strict(raw.decode("utf-8"))
                if canonical_json_bytes(value) != raw:
                    raise PromotionBundleError("bundle metadata must use canonical QC2 JSON bytes")
                control_values[path] = value

            manifest = control_values[MANIFEST_PATH]
            inventory = control_values[INVENTORY_PATH]
            signature = control_values[SIGNATURE_PATH]
            if not isinstance(manifest, dict) or not isinstance(inventory, list) or not isinstance(signature, dict):
                raise PromotionBundleError("bundle metadata has an invalid JSON shape")
            payload_names = set(names) - METADATA_PATHS
            inventory_paths = {
                validate_relative_path(row.get("relative_path"))
                for row in inventory
                if isinstance(row, dict)
            }
            if len(inventory_paths) != len(inventory) or payload_names != inventory_paths:
                raise PromotionBundleError("archive entries differ from the declared signed inventory")
            files: dict[str, bytes] = {}
            for path in sorted(payload_names, key=lambda value: value.encode("utf-8")):
                raw = archive.read(names[path])
                if len(raw) != names[path].file_size:
                    raise PromotionBundleError("archive member size differs from its ZIP directory")
                files[path] = raw
            return manifest, inventory, signature, files
    except PromotionBundleError:
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        RuntimeError,
        OSError,
        EOFError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise PromotionBundleError(f"promotion bundle archive is invalid: {exc}") from exc
