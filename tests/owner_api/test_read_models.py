from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from qc2_owner_api.read_models import (
    InMemoryOwnerReadModelRepository,
    OwnerReadErrorCode,
    OwnerReadModelError,
    OwnerReadModelProjector,
    create_source_receipt,
    validate_read_page,
)

NOW = datetime(2026, 10, 9, 16, 0, tzinfo=UTC)
UUIDS = [
    f"018f0000-0000-7000-8000-{number:012x}"
    for number in range(1, 1010)
]
HASH = "a" * 64

SOURCE_SCHEMAS = {
    "today": "qc2.models_prediction.PredictionSeal.v1",
    "predictions": "qc2.models_prediction.Prediction.v1",
    "validation": "qc2.validation.QualificationReceipt.v1",
    "models": "qc2.models_prediction.ModelManifest.v1",
    "system": "qc2.time_operation.ReadinessAssessment.v1",
    "positions": "qc2.execution.Position.v1",
    "alerts": "qc2.governance_owner.Alert.v1",
    "reports": "qc2.validation.ValidationReport.v1",
    "evidence": "qc2.integrity_build.EvidenceEvent.v1",
}


def _ref(schema_name: str, index: int = 0) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": UUIDS[index],
        "content_hash": HASH,
    }


def _payload(view_name: str, index: int = 0) -> dict[str, object]:
    if view_name == "today":
        return {
            "session_id": "2026-10-09",
            "session_state": "CLOSED",
            "last_sealed_run_ref": None,
            "top_1_symbols": [],
            "top_5_symbols": [],
            "top_10_symbols": [],
            "actionable_alert_count": 0,
            "paper_state": "UNKNOWN",
            "readiness_state": "READY",
        }
    if view_name == "predictions":
        return {
            "session_id": "2026-10-09",
            "rank": index + 1,
            "instrument_ref": _ref("qc2.identity_market.Instrument.v1", index),
            "symbol": f"SYM{index}",
            "prediction_state": "SCORED",
            "score": "0.812",
            "uncertainty": "0.1",
            "excluded_reason": None,
            "evidence_refs": [],
        }
    if view_name == "validation":
        return {
            "epoch_ref": _ref("qc2.validation.ValidationEpoch.v1", index),
            "session_id": "2026-10-09",
            "status": "PASS",
            "collection_count": 20,
            "matured_count": 18,
            "coverage": "0.9",
            "report_ref": _ref("qc2.validation.ValidationReport.v1", index),
        }
    if view_name == "models":
        return {
            "model_ref": _ref("qc2.models_prediction.ModelManifest.v1", index),
            "role": "CANDIDATE",
            "state": "ACTIVE",
            "display_name": f"Candidate {index}",
            "lineage_refs": [],
            "eligible_for_promotion": False,
        }
    if view_name == "system":
        return {
            "component": "owner_api",
            "state": "READY",
            "observed_at": "2026-10-09T16:00:00Z",
            "reason_codes": [],
            "fresh_until": "2026-10-09T16:05:00Z",
        }
    if view_name == "positions":
        return {
            "position_ref": _ref("qc2.execution.Position.v1", index),
            "instrument_ref": _ref("qc2.identity_market.Instrument.v1", index),
            "quantity": "2.0",
            "average_entry_price": "3.0",
            "unrealized_pnl": None,
            "reconciliation_state": "RECONCILED",
        }
    if view_name == "alerts":
        return {
            "alert_ref": _ref("qc2.governance_owner.Alert.v1", index),
            "severity": "WARNING",
            "state": "OPEN",
            "title": "Reconciliation requires review",
            "triggered_at": "2026-10-09T16:00:00Z",
            "acknowledged_at": None,
            "source_refs": [],
        }
    if view_name == "reports":
        return {
            "report_ref": _ref("qc2.validation.ValidationReport.v1", index),
            "report_type": "validation",
            "status": "FINAL",
            "created_at": "2026-10-09T16:00:00Z",
            "source_refs": [],
            "export_bytes": 256,
        }
    if view_name == "evidence":
        return {
            "evidence_ref": _ref("qc2.integrity_build.EvidenceEvent.v1", index),
            "evidence_type": "PREDICTION_SEAL",
            "verification_status": "VERIFIED",
            "created_at": "2026-10-09T16:00:00Z",
            "source_refs": [],
            "artifact_length_bytes": 0,
        }
    raise AssertionError(f"unknown view {view_name}")


def _receipt(view_name: str, index: int) -> dict[str, object]:
    return create_source_receipt(
        environment_namespace="test",
        view_name=view_name,
        source_sequence=index + 1,
        item_id=f"item-{index:04d}",
        sort_key=f"{index:04d}",
        source_ref=_ref(SOURCE_SCHEMAS[view_name], index),
        payload=_payload(view_name, index),
    )


@pytest.mark.parametrize("view_name", SOURCE_SCHEMAS)
def test_all_typed_views_build_and_validate(view_name: str) -> None:
    receipt = _receipt(view_name, 0)
    snapshot = OwnerReadModelProjector().rebuild(
        environment_namespace="test",
        view_name=view_name,
        source_receipts=[receipt],
        source_sequence=1,
        source_highwater_sequence=1,
        previous_projection_sequence=0,
        built_at=NOW,
        freshness_deadline=NOW + timedelta(minutes=5),
    )
    repo = InMemoryOwnerReadModelRepository(
        environment_namespace="test",
        clock=lambda: NOW,
    )
    repo.rebuild(
        view_name=view_name,
        source_receipts=[receipt],
        source_sequence=1,
        source_highwater_sequence=1,
        built_at=NOW,
        freshness_deadline=NOW + timedelta(minutes=5),
    )

    page = repo.read_page(view_name=view_name)
    validate_read_page(page, view_name=view_name)
    assert snapshot.projection_sequence == page["projection_sequence"] == 1
    assert page["items"][0]["source_ref"] == receipt["source_ref"]
    assert page["data_state"] == "CURRENT"


def test_pagination_is_stable_and_uses_frozen_projection_sequence() -> None:
    repo = InMemoryOwnerReadModelRepository(
        environment_namespace="test",
        clock=lambda: NOW,
    )
    receipts = [_receipt("predictions", index) for index in range(3)]
    repo.rebuild(
        view_name="predictions",
        source_receipts=receipts,
        source_sequence=3,
        source_highwater_sequence=3,
        built_at=NOW,
        freshness_deadline=NOW + timedelta(minutes=5),
    )

    first = repo.read_page(view_name="predictions", limit=2)
    assert [item["item_id"] for item in first["items"]] == [
        "item-0000",
        "item-0001",
    ]
    assert first["next_cursor"] is not None
    repo.rebuild(
        view_name="predictions",
        source_receipts=receipts[:1],
        source_sequence=1,
        source_highwater_sequence=3,
        built_at=NOW + timedelta(seconds=1),
        freshness_deadline=NOW + timedelta(minutes=5),
    )

    second = repo.read_page(
        view_name="predictions",
        limit=2,
        cursor=first["next_cursor"],
    )
    assert second["projection_sequence"] == 1
    assert [item["item_id"] for item in second["items"]] == ["item-0002"]
    validate_read_page(second, view_name="predictions")


def test_lag_and_expired_freshness_mark_pages_stale() -> None:
    clock = [NOW]
    repo = InMemoryOwnerReadModelRepository(
        environment_namespace="test",
        clock=lambda: clock[0],
    )
    repo.rebuild(
        view_name="system",
        source_receipts=[_receipt("system", 0)],
        source_sequence=1,
        source_highwater_sequence=1,
        built_at=NOW,
        freshness_deadline=NOW + timedelta(minutes=1),
    )
    repo.advance_source_highwater(view_name="system", source_sequence=3)
    lagged = repo.read_page(view_name="system")
    assert lagged["lag"] == 2
    assert lagged["stale"] is True
    assert lagged["data_state"] == "STALE"

    with pytest.raises(OwnerReadModelError) as exc:
        repo.advance_source_highwater(view_name="system", source_sequence=0)
    assert exc.value.code == OwnerReadErrorCode.INVALID_INPUT

    fresh_repo = InMemoryOwnerReadModelRepository(
        environment_namespace="test",
        clock=lambda: clock[0],
    )
    fresh_repo.rebuild(
        view_name="system",
        source_receipts=[_receipt("system", 0)],
        source_sequence=1,
        source_highwater_sequence=1,
        built_at=NOW,
        freshness_deadline=NOW + timedelta(minutes=1),
    )
    clock[0] = NOW + timedelta(minutes=2)
    expired = fresh_repo.read_page(view_name="system")
    assert expired["lag"] == 0
    assert expired["stale"] is True


def test_empty_projection_and_bounded_export() -> None:
    repo = InMemoryOwnerReadModelRepository(
        environment_namespace="test",
        clock=lambda: NOW,
    )
    repo.rebuild(
        view_name="evidence",
        source_receipts=[],
        source_sequence=0,
        source_highwater_sequence=0,
        built_at=NOW,
        freshness_deadline=NOW + timedelta(minutes=5),
    )
    empty = repo.read_page(view_name="evidence")
    assert empty["data_state"] == "EMPTY"
    validate_read_page(empty, view_name="evidence")

    repo.rebuild(
        view_name="predictions",
        source_receipts=[_receipt("predictions", 0), _receipt("predictions", 1)],
        source_sequence=2,
        source_highwater_sequence=2,
        built_at=NOW,
        freshness_deadline=NOW + timedelta(minutes=5),
    )
    with pytest.raises(OwnerReadModelError) as exc:
        repo.read_page(view_name="predictions", limit=1, export=True)
    assert exc.value.code == OwnerReadErrorCode.EXPORT_TOO_LARGE
    exported = repo.read_page(view_name="predictions", limit=2, export=True)
    assert len(exported["items"]) == 2
    assert exported["next_cursor"] is None


def test_export_size_cap_and_page_size_cap() -> None:
    repo = InMemoryOwnerReadModelRepository(
        environment_namespace="test",
        clock=lambda: NOW,
    )
    receipts = [_receipt("evidence", index) for index in range(1001)]
    repo.rebuild(
        view_name="evidence",
        source_receipts=receipts,
        source_sequence=1001,
        source_highwater_sequence=1001,
        built_at=NOW,
        freshness_deadline=NOW + timedelta(minutes=5),
    )
    page = repo.read_page(view_name="evidence", limit=25)
    assert len(page["items"]) == 25
    assert len(page["source_refs"]) == 25
    validate_read_page(page, view_name="evidence")
    with pytest.raises(OwnerReadModelError) as exc:
        repo.read_page(view_name="evidence", limit=1001, export=True)
    assert exc.value.code == OwnerReadErrorCode.INVALID_PAGINATION
    with pytest.raises(OwnerReadModelError) as exc:
        repo.read_page(view_name="evidence", limit=100, export=True)
    assert exc.value.code == OwnerReadErrorCode.EXPORT_TOO_LARGE
    with pytest.raises(OwnerReadModelError) as exc:
        repo.read_page(view_name="evidence", limit=101)
    assert exc.value.code == OwnerReadErrorCode.INVALID_PAGINATION


def test_rejects_noncanonical_sources_and_tampered_receipts() -> None:
    with pytest.raises(OwnerReadModelError) as exc:
        create_source_receipt(
            environment_namespace="test",
            view_name="predictions",
            source_sequence=1,
            item_id="item-0000",
            sort_key="0000",
            source_ref=_ref("qc2.unrelated.RandomRecord.v1"),
            payload=_payload("predictions"),
        )
    assert exc.value.code == OwnerReadErrorCode.INVALID_RECEIPT

    receipt = _receipt("predictions", 0)
    receipt["payload"] = _payload("predictions", 2)
    with pytest.raises(OwnerReadModelError) as exc:
        OwnerReadModelProjector().rebuild(
            environment_namespace="test",
            view_name="predictions",
            source_receipts=[receipt],
            source_sequence=1,
            source_highwater_sequence=1,
            previous_projection_sequence=0,
            built_at=NOW,
            freshness_deadline=NOW + timedelta(minutes=5),
        )
    assert exc.value.code == OwnerReadErrorCode.INVALID_RECEIPT


def test_rejects_duplicate_source_sequence_and_item_id() -> None:
    duplicate_sequence = [
        _receipt("predictions", 0),
        create_source_receipt(
            environment_namespace="test",
            view_name="predictions",
            source_sequence=1,
            item_id="item-0001",
            sort_key="0001",
            source_ref=_ref(SOURCE_SCHEMAS["predictions"], 1),
            payload=_payload("predictions", 1),
        ),
    ]
    duplicate_item_id = [
        _receipt("predictions", 0),
        create_source_receipt(
            environment_namespace="test",
            view_name="predictions",
            source_sequence=2,
            item_id="item-0000",
            sort_key="0001",
            source_ref=_ref(SOURCE_SCHEMAS["predictions"], 1),
            payload=_payload("predictions", 1),
        ),
    ]
    for receipts in (duplicate_sequence, duplicate_item_id):
        with pytest.raises(OwnerReadModelError) as exc:
            OwnerReadModelProjector().rebuild(
                environment_namespace="test",
                view_name="predictions",
                source_receipts=receipts,
                source_sequence=2,
                source_highwater_sequence=2,
                previous_projection_sequence=0,
                built_at=NOW,
                freshness_deadline=NOW + timedelta(minutes=5),
            )
        assert exc.value.code == OwnerReadErrorCode.INVALID_RECEIPT


def test_cursor_scope_tampering_and_retention_expiry() -> None:
    repo = InMemoryOwnerReadModelRepository(
        environment_namespace="test",
        clock=lambda: NOW,
    )
    receipts = [_receipt("predictions", index) for index in range(2)]
    repo.rebuild(
        view_name="predictions",
        source_receipts=receipts,
        source_sequence=2,
        source_highwater_sequence=2,
        built_at=NOW,
        freshness_deadline=NOW + timedelta(minutes=5),
    )
    first = repo.read_page(view_name="predictions", limit=1)
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)

    for invalid_cursor, view_name in ((cursor[:-1] + "A", "predictions"), (cursor, "models")):
        with pytest.raises(OwnerReadModelError) as exc:
            repo.read_page(view_name=view_name, cursor=invalid_cursor)
        assert exc.value.code == OwnerReadErrorCode.INVALID_CURSOR

    for generation in range(2, 7):
        repo.rebuild(
            view_name="predictions",
            source_receipts=receipts[:1],
            source_sequence=1,
            source_highwater_sequence=2,
            built_at=NOW + timedelta(seconds=generation),
            freshness_deadline=NOW + timedelta(minutes=5),
        )
    with pytest.raises(OwnerReadModelError) as exc:
        repo.read_page(view_name="predictions", cursor=cursor)
    assert exc.value.code == OwnerReadErrorCode.CURSOR_EXPIRED
