"""Small content-addressed local store used by offline acquisition and tests."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .errors import MarketDataError


@dataclass(frozen=True)
class StoredArtifact:
    relative_path: str
    storage_ref: str
    sha256: str
    byte_length: int
    media_type: str


class ContentAddressedStore:
    """Persist exact bytes under caller-chosen, traversal-safe artifact paths."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise MarketDataError("artifact_store_root_must_be_path")
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, relative_path: str, body: bytes, media_type: str) -> StoredArtifact:
        if not isinstance(body, bytes) or not isinstance(media_type, str) or not media_type:
            raise MarketDataError("artifact_store_input_invalid")
        path = PurePosixPath(relative_path)
        windows_path = PureWindowsPath(relative_path)
        if (
            not relative_path
            or path.is_absolute()
            or windows_path.is_absolute()
            or ".." in path.parts
            or "\\" in relative_path
            or any(part in {"", "."} for part in path.parts)
        ):
            raise MarketDataError("artifact_store_path_invalid")

        destination = (self._root / Path(*path.parts)).resolve()
        if destination != self._root and self._root not in destination.parents:
            raise MarketDataError("artifact_store_path_invalid")
        digest = hashlib.sha256(body).hexdigest()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != body:
                raise MarketDataError("artifact_store_immutable_path_conflict")
        else:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=".qc2-", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.replace(temporary, destination)
            except OSError:
                temporary.unlink(missing_ok=True)
                if not destination.exists() or destination.read_bytes() != body:
                    raise MarketDataError("artifact_store_write_failed") from None

        return StoredArtifact(
            relative_path=path.as_posix(),
            storage_ref=f"qc2blob:sha256:{digest}",
            sha256=digest,
            byte_length=len(body),
            media_type=media_type,
        )
