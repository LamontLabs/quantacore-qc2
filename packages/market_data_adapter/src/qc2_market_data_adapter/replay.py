"""Offline reconstruction of adapter output from saved raw response receipts."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qc2_contracts.runtime import artifact_inventory_hash, canonical_json_bytes, new_uuidv7

from .adapter import AlpacaMarketDataAdapter
from .errors import MarketDataError
from .models import MarketDataRequest, MarketDataResult
from .storage import ContentAddressedStore
from .transport import HttpResponse


class CaptureRuntime:
    """Records the adapter's IDs and clock reads so replay is byte-for-byte."""

    def __init__(
        self,
        *,
        clock_source: Callable[[], datetime] | None = None,
        id_source: Callable[[], str] | None = None,
    ) -> None:
        self._clock_source = clock_source or (lambda: datetime.now(timezone.utc))
        self._id_source = id_source or new_uuidv7
        self.clock_trace: list[str] = []
        self.id_trace: list[str] = []

    def clock(self) -> datetime:
        value = self._clock_source()
        if value.tzinfo is None or value.utcoffset() is None:
            raise MarketDataError("capture_clock_timezone_required")
        normalized = value.astimezone(timezone.utc)
        self.clock_trace.append(_format_utc(normalized))
        return normalized

    def new_id(self) -> str:
        value = self._id_source()
        self.id_trace.append(value)
        return value

    def record(self) -> dict[str, list[str]]:
        return {
            "clock_trace": list(self.clock_trace),
            "id_trace": list(self.id_trace),
        }


class ReplayRuntime:
    def __init__(self, clock_trace: Sequence[str], id_trace: Sequence[str]) -> None:
        self._clock_values = tuple(_parse_utc(value) for value in clock_trace)
        self._id_values = tuple(id_trace)
        self._clock_index = 0
        self._id_index = 0

    def clock(self) -> datetime:
        if self._clock_index >= len(self._clock_values):
            raise MarketDataError("offline_replay_clock_trace_exhausted")
        value = self._clock_values[self._clock_index]
        self._clock_index += 1
        return value

    def new_id(self) -> str:
        if self._id_index >= len(self._id_values):
            raise MarketDataError("offline_replay_id_trace_exhausted")
        value = self._id_values[self._id_index]
        self._id_index += 1
        return value

    def assert_exhausted(self) -> None:
        if (
            self._clock_index != len(self._clock_values)
            or self._id_index != len(self._id_values)
        ):
            raise MarketDataError("offline_replay_runtime_trace_not_consumed")


class _ReplayTransport:
    def __init__(self, pages: Sequence[tuple[str, Mapping[str, str], HttpResponse]]) -> None:
        self._pages = tuple(pages)
        self._index = 0

    def get(self, path: str, params: Mapping[str, str]) -> HttpResponse:
        if self._index >= len(self._pages):
            raise MarketDataError("offline_replay_unexpected_request")
        expected_path, expected_params, response = self._pages[self._index]
        if path != expected_path or dict(params) != dict(expected_params):
            raise MarketDataError("offline_replay_request_mismatch")
        self._index += 1
        return response

    def assert_exhausted(self) -> None:
        if self._index != len(self._pages):
            raise MarketDataError("offline_replay_response_unconsumed")


def reconstruct_from_saved_receipts(
    request: MarketDataRequest,
    captured: MarketDataResult,
    store: ContentAddressedStore,
    *,
    clock_trace: Sequence[str],
    id_trace: Sequence[str],
    replay_root: Path,
) -> MarketDataResult:
    """Re-run normalization without network access, using only stored response bytes."""
    receipts_by_request: dict[str, list[Mapping[str, Any]]] = {}
    for receipt in captured.raw_receipts:
        receipts_by_request.setdefault(
            receipt["request_ref"]["target_id"], []
        ).append(receipt)

    artifacts_by_path = {
        item["relative_path"]: item for item in captured.artifact_inventory
    }
    pages: list[tuple[str, Mapping[str, str], HttpResponse]] = []
    for evidence in captured.request_evidence:
        request_id = evidence.request_ref["target_id"]
        receipts = receipts_by_request.get(request_id, [])
        if len(receipts) != 1:
            raise MarketDataError("offline_replay_receipt_count_invalid")
        receipt = receipts[0]
        raw_digest = receipt["raw_sha256"]
        raw_path = f"raw/{raw_digest}.bin"
        raw_artifact = artifacts_by_path.get(raw_path)
        if raw_artifact is None or raw_artifact["sha256"] != raw_digest:
            raise MarketDataError("offline_replay_raw_receipt_missing")
        body = store.read(raw_path, raw_digest)
        if len(body) != receipt["byte_length"]:
            raise MarketDataError("offline_replay_raw_receipt_length_mismatch")

        prefix = f"transport-meta/{evidence.request_hash}/"
        metadata_artifacts = [
            item
            for item in captured.artifact_inventory
            if item["relative_path"].startswith(prefix)
        ]
        if len(metadata_artifacts) != 1:
            raise MarketDataError("offline_replay_response_metadata_invalid")
        metadata_artifact = metadata_artifacts[0]
        metadata_bytes = store.read(
            metadata_artifact["relative_path"],
            metadata_artifact["sha256"],
        )
        metadata = _parse_json_object(metadata_bytes)
        if metadata.get("request_hash") != evidence.request_hash:
            raise MarketDataError("offline_replay_response_metadata_mismatch")
        headers = dict(metadata.get("headers", {}))
        headers.setdefault("content-type", receipt["media_type"])
        headers.setdefault("content-length", str(len(body)))
        response = HttpResponse(
            status_code=metadata["status_code"],
            headers=headers,
            body=body,
        )
        descriptor = evidence.descriptor
        pages.append(
            (
                descriptor["path"],
                dict(descriptor["query"]),
                response,
            )
        )

    if len(receipts_by_request) != len(captured.request_evidence):
        raise MarketDataError("offline_replay_orphan_receipt")

    transport = _ReplayTransport(pages)
    runtime = ReplayRuntime(clock_trace, id_trace)
    replayed = AlpacaMarketDataAdapter(
        transport=transport,
        store=ContentAddressedStore(replay_root),
        clock=runtime.clock,
        sleeper=lambda _: None,
        id_factory=runtime.new_id,
    ).acquire(request)
    transport.assert_exhausted()
    runtime.assert_exhausted()

    if (
        canonical_json_bytes(_plain(replayed.data_bundle))
        != canonical_json_bytes(_plain(captured.data_bundle))
        or canonical_json_bytes(_plain(replayed.daily_bars))
        != canonical_json_bytes(_plain(captured.daily_bars))
        or canonical_json_bytes(_plain(replayed.raw_receipts))
        != canonical_json_bytes(_plain(captured.raw_receipts))
        or artifact_inventory_hash(list(replayed.artifact_inventory))
        != artifact_inventory_hash(list(captured.artifact_inventory))
    ):
        raise MarketDataError("offline_reconstruction_mismatch")
    return replayed


def _parse_json_object(body: bytes) -> dict[str, Any]:
    from qc2_contracts.runtime import parse_json_strict

    try:
        value = parse_json_strict(body.decode("utf-8"))
    except Exception:
        raise MarketDataError("offline_replay_metadata_invalid") from None
    if not isinstance(value, dict):
        raise MarketDataError("offline_replay_metadata_invalid")
    return value


def _format_utc(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise MarketDataError("offline_replay_timestamp_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketDataError("offline_replay_timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
