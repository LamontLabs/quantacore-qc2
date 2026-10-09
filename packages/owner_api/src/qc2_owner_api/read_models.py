"""Strict, rebuildable owner read projections over canonical source receipts."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from qc2_contracts.runtime import canonical_json_bytes, domain_separated_sha256

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "v1"
_MAX_PAGE_SIZE = 100
_MAX_EXPORT_SIZE = 1000
_MAX_EXPORT_BYTES = 1_048_576
_MAX_RETAINED_SNAPSHOTS = 5
_CURSOR_VERSION = 1
_RECEIPT_DOMAIN = "qc2.owner_api.read_source_receipt.v1"
_SNAPSHOT_DOMAIN = "qc2.owner_api.read_projection_snapshot.v1"
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")
_ENVIRONMENTS = frozenset({"development", "test", "research", "production"})
_VIEWS = {
    "today": "OwnerTodayPayload.schema.json",
    "predictions": "OwnerPredictionsPayload.schema.json",
    "validation": "OwnerValidationPayload.schema.json",
    "models": "OwnerModelsPayload.schema.json",
    "system": "OwnerSystemPayload.schema.json",
    "positions": "OwnerPositionsPayload.schema.json",
    "alerts": "OwnerAlertsPayload.schema.json",
    "reports": "OwnerReportsPayload.schema.json",
    "evidence": "OwnerEvidencePayload.schema.json",
}
_SOURCE_SCHEMAS_BY_VIEW = {
    "today": frozenset(
        {
            "qc2.models_prediction.PredictionSeal.v1",
            "qc2.time_operation.MarketSession.v1",
            "qc2.time_operation.ReadinessAssessment.v1",
        }
    ),
    "predictions": frozenset({"qc2.models_prediction.Prediction.v1"}),
    "validation": frozenset(
        {
            "qc2.validation.QualificationReceipt.v1",
            "qc2.validation.ValidationReport.v1",
        }
    ),
    "models": frozenset(
        {
            "qc2.models_prediction.ModelManifest.v1",
            "qc2.governance_owner.ChampionPointer.v1",
        }
    ),
    "system": frozenset({"qc2.time_operation.ReadinessAssessment.v1"}),
    "positions": frozenset({"qc2.execution.Position.v1"}),
    "alerts": frozenset(
        {
            "qc2.governance_owner.Alert.v1",
            "qc2.execution.ReconciliationReport.v1",
        }
    ),
    "reports": frozenset(
        {
            "qc2.validation.ValidationReport.v1",
            "qc2.execution.ReconciliationReport.v1",
        }
    ),
    "evidence": frozenset(
        {
            "qc2.integrity_build.EvidenceEvent.v1",
            "qc2.integrity_build.Checkpoint.v1",
        }
    ),
}


class OwnerReadErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    INVALID_RECEIPT = "invalid_receipt"
    INVALID_SCHEMA = "invalid_schema"
    INVALID_CURSOR = "invalid_cursor"
    CURSOR_EXPIRED = "cursor_expired"
    INVALID_PAGINATION = "invalid_pagination"
    EXPORT_TOO_LARGE = "export_too_large"


class OwnerReadModelError(ValueError):
    """Stable, redacted error raised at the owner read-model boundary."""

    def __init__(self, code: OwnerReadErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


def _json_native(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)
        return {key: _json_native(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(child) for child in value]
    return value


def _load_validator(filename: str) -> Draft202012Validator:
    schema = json.loads((_SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


_RECEIPT_VALIDATOR = _load_validator("OwnerReadSourceReceipt.schema.json")
_PAYLOAD_VALIDATORS = {
    view: _load_validator(filename) for view, filename in _VIEWS.items()
}


def _now_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)
    if value.utcoffset() != UTC.utcoffset(value):
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)
    return value.astimezone(UTC)


def _format_instant(value: datetime) -> str:
    instant = _now_utc(value)
    return instant.isoformat(timespec="microseconds" if instant.microsecond else "seconds").replace(
        "+00:00", "Z"
    )


def _validate_schema(
    validator: Draft202012Validator,
    value: dict[str, Any],
    code: OwnerReadErrorCode,
) -> None:
    try:
        validator.validate(value)
    except ValidationError as exc:
        raise OwnerReadModelError(code) from exc


def _receipt_hash(receipt: Mapping[str, Any]) -> str:
    body = {key: _json_native(value) for key, value in receipt.items() if key != "receipt_hash"}
    return domain_separated_sha256(_RECEIPT_DOMAIN, canonical_json_bytes(body))


def create_source_receipt(
    *,
    environment_namespace: str,
    view_name: str,
    source_sequence: int,
    item_id: str,
    sort_key: str,
    source_ref: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a source receipt using the same hash contract checked by the projector."""
    receipt: dict[str, Any] = {
        "schema_name": "qc2.owner_api.OwnerReadSourceReceipt.v1",
        "schema_version": "1.0",
        "environment_namespace": environment_namespace,
        "view_name": view_name,
        "source_sequence": source_sequence,
        "item_id": item_id,
        "sort_key": sort_key,
        "source_ref": _json_native(source_ref),
        "payload": _json_native(payload),
    }
    receipt["receipt_hash"] = _receipt_hash(receipt)
    _validate_source_receipt(receipt, environment_namespace, view_name)
    return receipt


def _validate_source_receipt(
    value: Mapping[str, Any],
    environment_namespace: str,
    view_name: str,
) -> dict[str, Any]:
    receipt = _json_native(value)
    if not isinstance(receipt, dict):
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_RECEIPT)
    try:
        _validate_schema(
            _RECEIPT_VALIDATOR, receipt, OwnerReadErrorCode.INVALID_RECEIPT
        )
        if receipt["environment_namespace"] != environment_namespace:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_RECEIPT)
        if receipt["view_name"] != view_name or view_name not in _VIEWS:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_RECEIPT)
        if receipt["source_ref"]["target_schema_name"] not in _SOURCE_SCHEMAS_BY_VIEW[
            view_name
        ]:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_RECEIPT)
        _validate_schema(
            _PAYLOAD_VALIDATORS[view_name],
            receipt["payload"],
            OwnerReadErrorCode.INVALID_SCHEMA,
        )
    except (KeyError, TypeError) as exc:
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_RECEIPT) from exc
    if receipt["receipt_hash"] != _receipt_hash(receipt):
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_RECEIPT)
    return receipt


@dataclass(frozen=True, slots=True)
class ProjectionSnapshot:
    environment_namespace: str
    view_name: str
    projection_sequence: int
    source_sequence: int
    source_highwater_sequence: int
    built_at: str
    freshness_deadline: str
    source_refs: tuple[dict[str, Any], ...]
    items: tuple[dict[str, Any], ...]
    snapshot_hash: str

    @property
    def lag(self) -> int:
        return max(0, self.source_highwater_sequence - self.source_sequence)

    @property
    def stale(self) -> bool:
        return self.lag > 0 or datetime.fromisoformat(
            self.freshness_deadline.replace("Z", "+00:00")
        ) <= datetime.now(UTC)


class OwnerReadModelProjector:
    """Builds deterministic typed projections without changing canonical source records."""

    def rebuild(
        self,
        *,
        environment_namespace: str,
        view_name: str,
        source_receipts: Iterable[Mapping[str, Any]],
        source_sequence: int,
        source_highwater_sequence: int,
        previous_projection_sequence: int,
        built_at: datetime,
        freshness_deadline: datetime,
    ) -> ProjectionSnapshot:
        if environment_namespace not in _ENVIRONMENTS or view_name not in _VIEWS:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)
        counters = (
            source_sequence,
            source_highwater_sequence,
            previous_projection_sequence,
        )
        if any(type(value) is not int or value < 0 for value in counters):
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)
        if source_sequence > source_highwater_sequence:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)

        built_at_utc = _now_utc(built_at)
        freshness_utc = _now_utc(freshness_deadline)
        if freshness_utc <= built_at_utc:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)

        validated: list[dict[str, Any]] = []
        seen_item_ids: set[str] = set()
        seen_sequences: set[int] = set()
        for raw_receipt in source_receipts:
            receipt = _validate_source_receipt(
                raw_receipt, environment_namespace, view_name
            )
            receipt_sequence = receipt["source_sequence"]
            if receipt_sequence > source_sequence or receipt_sequence in seen_sequences:
                raise OwnerReadModelError(OwnerReadErrorCode.INVALID_RECEIPT)
            if receipt["item_id"] in seen_item_ids:
                raise OwnerReadModelError(OwnerReadErrorCode.INVALID_RECEIPT)
            seen_sequences.add(receipt_sequence)
            seen_item_ids.add(receipt["item_id"])
            validated.append(receipt)

        validated.sort(key=lambda row: (row["sort_key"], row["item_id"]))
        items = tuple(
            {
                "item_id": receipt["item_id"],
                "sort_key": receipt["sort_key"],
                "source_sequence": receipt["source_sequence"],
                "source_ref": receipt["source_ref"],
                "payload": receipt["payload"],
                "receipt_hash": receipt["receipt_hash"],
            }
            for receipt in validated
        )
        unique_refs: dict[bytes, dict[str, Any]] = {}
        for item in items:
            ref = item["source_ref"]
            unique_refs[canonical_json_bytes(ref)] = ref
        source_refs = tuple(unique_refs[key] for key in sorted(unique_refs))
        projection_sequence = previous_projection_sequence + 1
        built_text = _format_instant(built_at_utc)
        freshness_text = _format_instant(freshness_utc)
        hash_body = {
            "environment_namespace": environment_namespace,
            "view_name": view_name,
            "projection_sequence": projection_sequence,
            "source_sequence": source_sequence,
            "source_highwater_sequence": source_highwater_sequence,
            "built_at": built_text,
            "freshness_deadline": freshness_text,
            "source_refs": list(source_refs),
            "items": list(items),
        }
        snapshot_hash = domain_separated_sha256(
            _SNAPSHOT_DOMAIN, canonical_json_bytes(hash_body)
        )
        return ProjectionSnapshot(
            environment_namespace=environment_namespace,
            view_name=view_name,
            projection_sequence=projection_sequence,
            source_sequence=source_sequence,
            source_highwater_sequence=source_highwater_sequence,
            built_at=built_text,
            freshness_deadline=freshness_text,
            source_refs=source_refs,
            items=items,
            snapshot_hash=snapshot_hash,
        )


def _encode_cursor(
    view_name: str,
    projection_sequence: int,
    sort_key: str,
    item_id: str,
) -> str:
    body = {
        "item_id": item_id,
        "projection_sequence": projection_sequence,
        "sort_key": sort_key,
        "version": _CURSOR_VERSION,
        "view_name": view_name,
    }
    return base64.urlsafe_b64encode(canonical_json_bytes(body)).rstrip(b"=").decode(
        "ascii"
    )


def _decode_cursor(value: str, view_name: str) -> dict[str, Any]:
    if not isinstance(value, str) or not _BASE64URL.fullmatch(value):
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_CURSOR)
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
            raise ValueError("non-canonical cursor")
        body = json.loads(decoded)
        if not isinstance(body, dict) or set(body) != {
            "version",
            "view_name",
            "projection_sequence",
            "sort_key",
            "item_id",
        }:
            raise ValueError("invalid cursor envelope")
        if canonical_json_bytes(body) != decoded:
            raise ValueError("non-canonical cursor body")
        if body["version"] != _CURSOR_VERSION or body["view_name"] != view_name:
            raise ValueError("cursor scope mismatch")
        if (
            type(body["projection_sequence"]) is not int
            or body["projection_sequence"] < 1
            or not isinstance(body["sort_key"], str)
            or len(body["sort_key"]) > 256
            or not body["sort_key"].isascii()
            or not isinstance(body["item_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", body["item_id"])
        ):
            raise ValueError("invalid cursor fields")
        return body
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_CURSOR) from exc


class InMemoryOwnerReadModelRepository:
    """Deterministic fixture repository used by acceptance tests, never production."""

    fixture_only = True

    def __init__(
        self,
        *,
        environment_namespace: str,
        clock: Any = None,
    ) -> None:
        if environment_namespace not in _ENVIRONMENTS:
            raise ValueError("unsupported environment namespace")
        self.environment_namespace = environment_namespace
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._snapshots: dict[str, dict[int, ProjectionSnapshot]] = {
            view: {} for view in _VIEWS
        }
        self._latest_sequence: dict[str, int] = {view: 0 for view in _VIEWS}
        self._source_highwater: dict[str, int] = {view: 0 for view in _VIEWS}

    def rebuild(
        self,
        *,
        view_name: str,
        source_receipts: Iterable[Mapping[str, Any]],
        source_sequence: int,
        source_highwater_sequence: int,
        built_at: datetime,
        freshness_deadline: datetime,
    ) -> ProjectionSnapshot:
        if view_name not in _VIEWS:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)
        projector = OwnerReadModelProjector()
        snapshot = projector.rebuild(
            environment_namespace=self.environment_namespace,
            view_name=view_name,
            source_receipts=source_receipts,
            source_sequence=source_sequence,
            source_highwater_sequence=source_highwater_sequence,
            previous_projection_sequence=self._latest_sequence[view_name],
            built_at=built_at,
            freshness_deadline=freshness_deadline,
        )
        self._latest_sequence[view_name] = snapshot.projection_sequence
        self._source_highwater[view_name] = max(
            self._source_highwater[view_name], source_highwater_sequence
        )
        snapshots = self._snapshots[view_name]
        snapshots[snapshot.projection_sequence] = snapshot
        for old_sequence in sorted(snapshots)[:-_MAX_RETAINED_SNAPSHOTS]:
            del snapshots[old_sequence]
        return snapshot

    def advance_source_highwater(self, *, view_name: str, source_sequence: int) -> None:
        if (
            view_name not in _VIEWS
            or type(source_sequence) is not int
            or source_sequence < self._source_highwater[view_name]
        ):
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)
        self._source_highwater[view_name] = source_sequence

    def read_page(
        self,
        *,
        view_name: str,
        limit: int = 50,
        cursor: str | None = None,
        export: bool = False,
    ) -> dict[str, Any]:
        maximum = _MAX_EXPORT_SIZE if export else _MAX_PAGE_SIZE
        if (
            view_name not in _VIEWS
            or type(limit) is not int
            or limit < 1
            or limit > maximum
        ):
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_PAGINATION)
        cursor_body = _decode_cursor(cursor, view_name) if cursor is not None else None
        sequence = (
            cursor_body["projection_sequence"]
            if cursor_body is not None
            else self._latest_sequence[view_name]
        )
        snapshot = self._snapshots[view_name].get(sequence)
        if snapshot is None:
            if sequence == 0 and cursor_body is None:
                raise OwnerReadModelError(OwnerReadErrorCode.INVALID_INPUT)
            raise OwnerReadModelError(OwnerReadErrorCode.CURSOR_EXPIRED)

        after = (
            (cursor_body["sort_key"], cursor_body["item_id"])
            if cursor_body is not None
            else None
        )
        ordered = [
            item
            for item in snapshot.items
            if after is None or (item["sort_key"], item["item_id"]) > after
        ]
        selected = ordered[:limit]
        page_source_refs = {
            canonical_json_bytes(item["source_ref"]): item["source_ref"]
            for item in selected
        }
        has_more = len(ordered) > limit
        if export and has_more:
            raise OwnerReadModelError(OwnerReadErrorCode.EXPORT_TOO_LARGE)
        next_cursor = (
            _encode_cursor(
                view_name,
                snapshot.projection_sequence,
                selected[-1]["sort_key"],
                selected[-1]["item_id"],
            )
            if has_more and selected
            else None
        )
        source_highwater = self._source_highwater[view_name]
        lag = max(0, source_highwater - snapshot.source_sequence)
        freshness_expired = datetime.fromisoformat(
            snapshot.freshness_deadline.replace("Z", "+00:00")
        ) <= _now_utc(self._clock())
        stale = lag > 0 or freshness_expired
        response = {
            "schema_name": "qc2.owner_api.OwnerReadPage.v1",
            "schema_version": "1.0",
            "environment_namespace": self.environment_namespace,
            "view_name": view_name,
            "projection_sequence": snapshot.projection_sequence,
            "source_sequence": snapshot.source_sequence,
            "source_highwater_sequence": source_highwater,
            "lag": lag,
            "stale": stale,
            "data_state": "STALE"
            if stale
            else ("CURRENT" if snapshot.items else "EMPTY"),
            "built_at": snapshot.built_at,
            "freshness_deadline": snapshot.freshness_deadline,
            "source_refs": [
                page_source_refs[key] for key in sorted(page_source_refs)
            ],
            "items": selected,
            "next_cursor": next_cursor,
        }
        if export and len(canonical_json_bytes(response)) > _MAX_EXPORT_BYTES:
            raise OwnerReadModelError(OwnerReadErrorCode.EXPORT_TOO_LARGE)
        return response

    def diagnostics(self) -> dict[str, Any]:
        views: list[dict[str, Any]] = []
        for view_name in _VIEWS:
            sequence = self._latest_sequence[view_name]
            snapshot = self._snapshots[view_name].get(sequence)
            highwater = self._source_highwater[view_name]
            views.append(
                {
                    "view_name": view_name,
                    "projection_sequence": sequence,
                    "source_sequence": snapshot.source_sequence if snapshot else 0,
                    "source_highwater_sequence": highwater,
                    "lag": max(0, highwater - (snapshot.source_sequence if snapshot else 0)),
                    "stale": snapshot is None
                    or highwater > snapshot.source_sequence
                    or datetime.fromisoformat(
                        snapshot.freshness_deadline.replace("Z", "+00:00")
                    )
                    <= _now_utc(self._clock()),
                    "built_at": snapshot.built_at if snapshot else None,
                }
            )
        return {
            "schema_name": "qc2.owner_api.OwnerReadDiagnostics.v1",
            "environment_namespace": self.environment_namespace,
            "views": views,
        }


def validate_read_page(value: Mapping[str, Any], *, view_name: str) -> None:
    """Validate the common page envelope and every view-specific payload."""
    if view_name not in _VIEWS or not isinstance(value, Mapping):
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
    page = _json_native(value)
    required = {
        "schema_name",
        "schema_version",
        "environment_namespace",
        "view_name",
        "projection_sequence",
        "source_sequence",
        "source_highwater_sequence",
        "lag",
        "stale",
        "data_state",
        "built_at",
        "freshness_deadline",
        "source_refs",
        "items",
        "next_cursor",
    }
    if not isinstance(page, dict) or set(page) != required:
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
    if (
        page["schema_name"] != "qc2.owner_api.OwnerReadPage.v1"
        or page["schema_version"] != "1.0"
        or page["view_name"] != view_name
        or page["environment_namespace"] not in _ENVIRONMENTS
        or type(page["projection_sequence"]) is not int
        or type(page["source_sequence"]) is not int
        or type(page["source_highwater_sequence"]) is not int
        or type(page["lag"]) is not int
        or type(page["stale"]) is not bool
        or page["data_state"] not in {"CURRENT", "STALE", "EMPTY"}
        or not isinstance(page["source_refs"], list)
        or not isinstance(page["items"], list)
        or len(page["source_refs"]) > _MAX_EXPORT_SIZE
        or len(page["items"]) > _MAX_EXPORT_SIZE
        or page["next_cursor"] is not None
        and not isinstance(page["next_cursor"], str)
        or isinstance(page["next_cursor"], str)
        and len(page["next_cursor"]) > 2048
    ):
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
    if (
        page["projection_sequence"] < 1
        or page["source_highwater_sequence"] < page["source_sequence"]
        or page["lag"]
        != max(0, page["source_highwater_sequence"] - page["source_sequence"])
        or page["stale"] != (page["data_state"] == "STALE")
    ):
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)

    source_refs: set[bytes] = set()
    previous_ref: bytes | None = None
    for source_ref in page["source_refs"]:
        if not isinstance(source_ref, dict):
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
        try:
            encoded_ref = canonical_json_bytes(source_ref)
        except Exception as exc:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA) from exc
        if encoded_ref in source_refs:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
        if previous_ref is not None and encoded_ref <= previous_ref:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
        source_refs.add(encoded_ref)
        previous_ref = encoded_ref

    item_source_refs: set[bytes] = set()
    previous_order_key: tuple[str, str] | None = None
    for item in page["items"]:
        if not isinstance(item, dict) or set(item) != {
            "item_id",
            "sort_key",
            "source_sequence",
            "source_ref",
            "payload",
            "receipt_hash",
        }:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
        if (
            type(item["source_sequence"]) is not int
            or item["source_sequence"] < 1
            or item["source_sequence"] > page["source_sequence"]
            or not isinstance(item["sort_key"], str)
            or not item["sort_key"].isascii()
            or len(item["sort_key"]) > 256
            or not isinstance(item["item_id"], str)
        ):
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
        receipt = {
            "schema_name": "qc2.owner_api.OwnerReadSourceReceipt.v1",
            "schema_version": "1.0",
            "environment_namespace": page["environment_namespace"],
            "view_name": view_name,
            "source_sequence": item["source_sequence"],
            "item_id": item["item_id"],
            "sort_key": item["sort_key"],
            "source_ref": item["source_ref"],
            "payload": item["payload"],
            "receipt_hash": item["receipt_hash"],
        }
        _validate_source_receipt(receipt, page["environment_namespace"], view_name)
        order_key = (item["sort_key"], item["item_id"])
        if previous_order_key is not None and order_key <= previous_order_key:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
        previous_order_key = order_key
        source_ref_bytes = canonical_json_bytes(item["source_ref"])
        if source_ref_bytes not in source_refs:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
        item_source_refs.add(source_ref_bytes)
    if source_refs != item_source_refs:
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
    if not isinstance(page["built_at"], str) or not isinstance(
        page["freshness_deadline"], str
    ):
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
    instants: dict[str, datetime] = {}
    for field in ("built_at", "freshness_deadline"):
        try:
            instant = datetime.fromisoformat(page[field].replace("Z", "+00:00"))
        except ValueError as exc:
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA) from exc
        if instant.tzinfo is None or instant.utcoffset() != UTC.utcoffset(instant):
            raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
        instants[field] = instant
    if instants["freshness_deadline"] <= instants["built_at"]:
        raise OwnerReadModelError(OwnerReadErrorCode.INVALID_SCHEMA)
