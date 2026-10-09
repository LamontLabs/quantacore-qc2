from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from qc2_alpaca_paper.models import (
    BrokerOrderEventType,
    BrokerOrderState,
    NormalizedFill,
    NormalizedOrder,
)
from qc2_broker_reconciliation import (
    BrokerInventorySnapshot,
    CashBalance,
    LocalFill,
    LocalInventorySnapshot,
    LocalOrder,
    LocalPosition,
    PostgresReconciliationStore,
    RemotePosition,
    UnknownSubmission,
    build_reconciliation_report,
    compare_inventories,
    resolve_unknown_submission,
)
from qc2_execution.authority import (
    ReconciliationDisposition,
    normalized_request_hash,
)


NOW = datetime(2026, 10, 5, 20, 0, tzinfo=UTC)
ACCOUNT = "a" * 64
OTHER_ACCOUNT = "b" * 64
EPISODE_ID = "018f0000-0000-7000-8000-000000000001"
EPISODE_REF = {
    "target_schema_name": "qc2.execution.ExecutionEpisode.v1",
    "target_id": EPISODE_ID,
    "content_hash": "c" * 64,
}
INSTRUMENT_ID = "018f0000-0000-7000-8000-000000000002"
BROKER_ORDER_ID = "018f0000-0000-7000-8000-000000000003"
ORDER_REF = {
    "target_schema_name": "qc2.execution.BrokerOrder.v1",
    "target_id": "018f0000-0000-7000-8000-000000000004",
}
POSITION_REF = {
    "target_schema_name": "qc2.execution.Position.v1",
    "target_id": "018f0000-0000-7000-8000-000000000005",
}
EVIDENCE_REF = {
    "target_schema_name": "qc2.integrity_build.EvidenceEvent.v1",
    "target_id": "018f0000-0000-7000-8000-000000000006",
    "content_hash": "d" * 64,
}


def remote_order(
    *,
    order_id: str = BROKER_ORDER_ID,
    client_key: str = "intent-key",
    symbol: str = "ACME",
    side: str = "BUY",
    quantity: str = "2",
    filled: str = "0",
    limit_price: str = "10",
    state: BrokerOrderState = BrokerOrderState.ACKNOWLEDGED,
) -> NormalizedOrder:
    quantity_value = Decimal(quantity)
    filled_value = Decimal(filled)
    return NormalizedOrder(
        broker_order_id=order_id,
        client_order_key=client_key,
        state=state,
        provider_status="accepted" if state == BrokerOrderState.ACKNOWLEDGED else "filled",
        symbol=symbol,
        side=side,
        quantity=quantity_value,
        filled_quantity=filled_value,
        remaining_quantity=quantity_value - filled_value,
        order_type="LIMIT",
        time_in_force="DAY",
        limit_price=Decimal(limit_price),
        submitted_at=NOW,
        updated_at=NOW,
        filled_average_price=None if filled_value == 0 else Decimal(limit_price),
    )


def base_local(**changes) -> LocalInventorySnapshot:
    values = {
        "episode_ref": EPISODE_REF,
        "paper_account_fingerprint": ACCOUNT,
        "generation": 4,
        "orders": (),
        "fills": (),
        "positions": (),
        "cash": (CashBalance("USD", Decimal("1000")),),
        "unknown_submissions": (),
        "symbol_to_instrument": {"ACME": INSTRUMENT_ID},
    }
    values.update(changes)
    return LocalInventorySnapshot(**values)


def base_broker(**changes) -> BrokerInventorySnapshot:
    values = {
        "account_fingerprint": ACCOUNT,
        "read_token": "fixture-window-1",
        "orders": (),
        "fills": (),
        "positions": (),
        "cash": (CashBalance("USD", Decimal("1000")),),
        "checked_sources": ("broker_order_inventory",),
        "orders_complete": True,
        "fills_complete": True,
        "positions_complete": True,
        "cash_complete": True,
        "consistency_window_closed": False,
    }
    values.update(changes)
    return BrokerInventorySnapshot(**values)


def local_order(
    *,
    order_id: str = BROKER_ORDER_ID,
    client_key: str = "intent-key",
    state: str = "ACKNOWLEDGED",
    filled: str = "0",
) -> LocalOrder:
    return LocalOrder(
        order_ref=ORDER_REF,
        broker_order_id=order_id,
        intent_id=EPISODE_ID,
        client_order_key=client_key,
        symbol="ACME",
        side="BUY",
        quantity=Decimal("2"),
        filled_quantity=Decimal(filled),
        order_type="LIMIT",
        time_in_force="DAY",
        limit_price=Decimal("10"),
        state=state,
    )


def local_position(quantity: str = "3") -> LocalPosition:
    return LocalPosition(
        position_ref=POSITION_REF,
        instrument_id=INSTRUMENT_ID,
        symbol="ACME",
        quantity=Decimal(quantity),
        average_cost=Decimal("8"),
        currency="USD",
    )


def test_remote_accepted_unknown_submission_resolves_only_by_matching_evidence():
    request = {
        "schema_name": "qc2.execution.normalized_mutation_request.v1",
        "action": "SUBMIT",
        "intent_id": EPISODE_ID,
        "account_fingerprint": ACCOUNT,
        "client_order_key": "intent-key",
        "instrument_id": INSTRUMENT_ID,
        "symbol_assignment_id": EPISODE_ID,
        "symbol": "ACME",
        "side": "BUY",
        "quantity_whole_shares": 2,
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "session_restriction": "REGULAR_SESSION_ONLY",
        "limit_price": "10",
        "stop_price": None,
        "extended_hours": False,
    }
    unknown = UnknownSubmission(
        attempt_id="018f0000-0000-7000-8000-000000000007",
        intent_id=EPISODE_ID,
        account_fingerprint=ACCOUNT,
        client_order_key="intent-key",
        normalized_request_hash=normalized_request_hash(request),
        expected_request=request,
    )

    class Authority:
        def __init__(self):
            self.accepted = []

        def accept_reconciliation(self, attempt_id, evidence):
            self.accepted.append((attempt_id, evidence))
            return True

        def submit_order(self, *args, **kwargs):
            raise AssertionError("reconciliation must never submit an order")

        def cancel_order(self, *args, **kwargs):
            raise AssertionError("reconciliation must never cancel an order")

    authority = Authority()
    result = resolve_unknown_submission(
        unknown,
        base_broker(orders=(remote_order(),)),
        evidence_ref=EVIDENCE_REF,
        authority=authority,
    )

    assert result.resolved is True
    assert result.disposition == ReconciliationDisposition.FOUND
    assert result.broker_order_id == BROKER_ORDER_ID
    assert len(authority.accepted) == 1
    assert authority.accepted[0][1].evidence_ref == EVIDENCE_REF


def test_missing_local_fill_is_held_without_inventing_a_local_fill():
    remote_fill = NormalizedFill(
        provider_activity_id="fill-1",
        broker_order_id=BROKER_ORDER_ID,
        event_type=BrokerOrderEventType.FILL,
        symbol="ACME",
        side="BUY",
        quantity=Decimal("1"),
        cumulative_quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        price=Decimal("10"),
        filled_at=NOW,
    )
    local = base_local(orders=(local_order(),))
    broker = base_broker(orders=(remote_order(),), fills=(remote_fill,))

    draft = compare_inventories(local, broker)

    assert draft.status == "HOLD"
    assert "missing_local_fill:fill-1" in draft.discrepancies
    assert local.fills == ()


def test_reused_fill_identifier_with_changed_terms_is_not_accepted():
    local = base_local(
        orders=(local_order(),),
        fills=(
            LocalFill(
                provider_activity_id="fill-1",
                broker_order_id=BROKER_ORDER_ID,
                quantity=Decimal("1"),
                price=Decimal("10"),
            ),
        ),
    )
    remote_fill = NormalizedFill(
        provider_activity_id="fill-1",
        broker_order_id=BROKER_ORDER_ID,
        event_type=BrokerOrderEventType.FILL,
        symbol="ACME",
        side="BUY",
        quantity=Decimal("1"),
        cumulative_quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        price=Decimal("11"),
        filled_at=NOW,
    )

    draft = compare_inventories(
        local,
        base_broker(orders=(remote_order(),), fills=(remote_fill,)),
    )

    assert draft.status == "HOLD"
    assert "fill_details_mismatch:fill-1" in draft.discrepancies


def test_unknown_remote_order_is_detected_as_a_manual_order():
    broker = base_broker(
        orders=(remote_order(client_key="manual-order", order_id="018f0000-0000-7000-8000-000000000008"),)
    )

    draft = compare_inventories(base_local(), broker)

    assert draft.status == "HOLD"
    assert any(key.startswith("manual_order:") for key in draft.discrepancies)


def test_duplicate_remote_client_keys_are_detected():
    broker = base_broker(
        orders=(
            remote_order(
                order_id="018f0000-0000-7000-8000-000000000012",
            ),
            remote_order(
                order_id="018f0000-0000-7000-8000-000000000013",
            ),
        )
    )

    draft = compare_inventories(base_local(), broker)

    assert "duplicate_remote_client_order_key:intent-key" in draft.discrepancies


def test_unknown_position_and_cash_change_are_both_detected():
    broker = base_broker(
        positions=(RemotePosition("MYST", Decimal("1"), Decimal("4"), "USD"),),
        cash=(CashBalance("USD", Decimal("975")),),
    )

    draft = compare_inventories(base_local(), broker)

    assert "unknown_remote_position:MYST" in draft.discrepancies
    assert "cash_balance_mismatch:USD" in draft.discrepancies
    assert draft.status == "HOLD"


def test_nonpositive_remote_position_is_reported_as_a_discrepancy():
    local = base_local(positions=(local_position(),))
    broker = base_broker(
        positions=(RemotePosition("ACME", Decimal("-1"), Decimal("8"), "USD"),),
    )

    draft = compare_inventories(local, broker)

    assert draft.status == "HOLD"
    assert "position_quantity_mismatch:" + INSTRUMENT_ID in draft.discrepancies


def test_account_reset_does_not_infer_that_local_positions_were_closed():
    local = base_local(positions=(local_position(),))
    broker = base_broker(
        account_fingerprint=OTHER_ACCOUNT,
        positions=(),
        cash=(),
    )

    draft = compare_inventories(local, broker)

    assert draft.status == "HOLD"
    assert draft.discrepancies == ("account_reset",)
    assert draft.position_refs == (POSITION_REF,)
    assert "local_position_missing_remotely:" not in " ".join(draft.discrepancies)


def test_unknown_submission_absence_requires_two_sources_and_closed_window():
    request = {
        "schema_name": "qc2.execution.normalized_mutation_request.v1",
        "action": "SUBMIT",
        "intent_id": EPISODE_ID,
        "account_fingerprint": ACCOUNT,
        "client_order_key": "intent-key",
        "instrument_id": INSTRUMENT_ID,
        "symbol_assignment_id": EPISODE_ID,
        "symbol": "ACME",
        "side": "BUY",
        "quantity_whole_shares": 2,
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "session_restriction": "REGULAR_SESSION_ONLY",
        "limit_price": "10",
        "stop_price": None,
        "extended_hours": False,
    }
    unknown = UnknownSubmission(
        attempt_id="018f0000-0000-7000-8000-000000000009",
        intent_id=EPISODE_ID,
        account_fingerprint=ACCOUNT,
        client_order_key="intent-key",
        normalized_request_hash=normalized_request_hash(request),
        expected_request=request,
    )

    class Authority:
        def __init__(self, result):
            self.result = result
            self.accepted = []

        def accept_reconciliation(self, attempt_id, evidence):
            self.accepted.append((attempt_id, evidence))
            return (
                self.result
                and evidence.disposition != ReconciliationDisposition.UNRESOLVED
            )

    one_source = Authority(True)
    insufficient = resolve_unknown_submission(
        unknown,
        base_broker(),
        evidence_ref=EVIDENCE_REF,
        authority=one_source,
    )
    assert insufficient.disposition == ReconciliationDisposition.UNRESOLVED
    assert insufficient.resolved is False
    assert one_source.accepted[0][1].disposition == ReconciliationDisposition.UNRESOLVED

    proof_broker = base_broker(
        checked_sources=("client_order_key_lookup", "complete_order_inventory"),
        consistency_window_closed=True,
    )
    authority = Authority(True)
    proven = resolve_unknown_submission(
        unknown,
        proof_broker,
        evidence_ref=EVIDENCE_REF,
        authority=authority,
    )
    assert proven.disposition == ReconciliationDisposition.ABSENCE_PROVEN
    assert proven.resolved is True
    assert authority.accepted[0][1].broker_order_id is None


def test_incomplete_remote_inventory_is_unknown_and_does_not_prove_absence():
    local = base_local(positions=(local_position(),))
    broker = base_broker(positions_complete=False, positions=())

    draft = compare_inventories(local, broker)

    assert draft.status == "UNKNOWN"
    assert "inventory_incomplete:positions" in draft.discrepancies
    assert not any(key.startswith("local_position_missing_remotely:") for key in draft.discrepancies)


def test_checkpoint_hash_is_order_independent_and_report_uses_existing_contract():
    local = base_local(
        orders=(local_order(),),
        positions=(local_position(),),
    )
    broker = base_broker(
        orders=(remote_order(),),
        positions=(RemotePosition("ACME", Decimal("3"), Decimal("8"), "USD"),),
    )
    first = compare_inventories(local, broker)
    reordered = compare_inventories(
        base_local(
            generation=99,
            orders=tuple(reversed(local.orders)),
            positions=tuple(reversed(local.positions)),
        ),
        base_broker(
            orders=tuple(reversed(broker.orders)),
            positions=tuple(reversed(broker.positions)),
        ),
    )

    assert first.checkpoint_hash == reordered.checkpoint_hash
    assert first.status == "RECONCILED"
    report = build_reconciliation_report(
        first,
        report_id="018f0000-0000-7000-8000-000000000010",
        created_at=NOW,
        evidence_ref=EVIDENCE_REF,
    )
    assert report["schema_name"] == "qc2.execution.ReconciliationReport.v1"
    assert report["status"] == "RECONCILED"
    assert report["discrepancies"] == []


def test_unknown_submission_terms_must_match_before_found_resolution():
    request = {
        "schema_name": "qc2.execution.normalized_mutation_request.v1",
        "action": "SUBMIT",
        "intent_id": EPISODE_ID,
        "account_fingerprint": ACCOUNT,
        "client_order_key": "intent-key",
        "instrument_id": INSTRUMENT_ID,
        "symbol_assignment_id": EPISODE_ID,
        "symbol": "ACME",
        "side": "BUY",
        "quantity_whole_shares": 2,
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "session_restriction": "REGULAR_SESSION_ONLY",
        "limit_price": "10",
        "stop_price": None,
        "extended_hours": False,
    }
    unknown = UnknownSubmission(
        attempt_id="018f0000-0000-7000-8000-000000000011",
        intent_id=EPISODE_ID,
        account_fingerprint=ACCOUNT,
        client_order_key="intent-key",
        normalized_request_hash=normalized_request_hash(request),
        expected_request=request,
    )

    class Authority:
        def __init__(self):
            self.accepted = []

        def accept_reconciliation(self, attempt_id, evidence):
            self.accepted.append(evidence)
            return evidence.disposition != ReconciliationDisposition.UNRESOLVED

    authority = Authority()
    result = resolve_unknown_submission(
        unknown,
        base_broker(orders=(remote_order(limit_price="11"),)),
        evidence_ref=EVIDENCE_REF,
        authority=authority,
    )

    assert result.disposition == ReconciliationDisposition.UNRESOLVED
    assert result.resolved is False
    assert result.reason_code == "UNKNOWN_SUBMISSION_TERMS_MISMATCH_NOT_ACCEPTED"
    assert authority.accepted[0].broker_order_id is None


def test_reconciliation_draft_contains_only_stable_local_contract_refs():
    local = base_local(
        orders=(local_order(),),
        positions=(local_position(),),
    )
    draft = compare_inventories(
        local,
        base_broker(orders=(remote_order(),)),
    )

    assert draft.broker_order_refs == (ORDER_REF,)
    assert draft.position_refs == (POSITION_REF,)
    assert draft.expected_account_fingerprint == ACCOUNT


def test_postgres_store_validates_report_and_binds_evidence_resolution():
    draft = compare_inventories(base_local(), base_broker())
    report = build_reconciliation_report(
        draft,
        report_id="018f0000-0000-7000-8000-000000000014",
        created_at=NOW,
        evidence_ref=EVIDENCE_REF,
    )

    class Cursor:
        description = None

        def __init__(self, row):
            self.row = row

        def execute(self, statement, parameters):
            self.statement = statement
            self.parameters = parameters

        def fetchone(self):
            return self.row

        def close(self):
            pass

    class Connection:
        def __init__(self, row):
            self.result_cursor = Cursor(row)

        def cursor(self):
            return self.result_cursor

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    responses = [
        {
            "result": {
                "checkpoint_id": report["id"],
                "checkpoint_hash": draft.checkpoint_hash,
                "generation": 1,
                "report_contract": report,
                "active_finding_keys": [],
                "already_recorded": False,
            }
        },
        {"resolved": True},
    ]

    def connection_factory():
        return Connection(responses.pop(0))

    store = PostgresReconciliationStore(connection_factory)
    persisted = store.record(draft)
    assert persisted.checkpoint_hash == draft.checkpoint_hash
    assert persisted.report_contract["id"] == report["id"]
    assert persisted.already_recorded is False
    assert (
        store.resolve_finding(
            episode_id=EPISODE_ID,
            finding_key="manual_order:fixture",
            resolution_code="reviewed_fixture",
            resolution_note="Owner reviewed fixture evidence.",
            evidence_ref=EVIDENCE_REF,
        )
        is True
    )
