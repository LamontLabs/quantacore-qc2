from datetime import datetime, timedelta, timezone
from decimal import Decimal

from qc2_position_state import (
    BrokerOrderEvent,
    CorporateActionAdjustment,
    DurablePositionLedger,
    ExecutionEpisodeSeed,
    Fill,
    FillCorrection,
    OrderSpec,
)


T0 = datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)


def episode(opening_cash: str = "1000") -> ExecutionEpisodeSeed:
    return ExecutionEpisodeSeed(
        episode_id="episode-1",
        episode_hash="a" * 64,
        content_hash="c" * 64,
        account_fingerprint="b" * 64,
        currency="USD",
        opening_cash=Decimal(opening_cash),
        opened_at=T0,
    )


def order(
    order_id: str,
    side: str,
    quantity: str,
    *,
    instrument_id: str = "instrument-1",
    reserved_amount: str | None = None,
    reservation_id: str | None = None,
) -> OrderSpec:
    return OrderSpec(
        order_id=order_id,
        episode_id="episode-1",
        instrument_id=instrument_id,
        side=side,  # type: ignore[arg-type]
        quantity=Decimal(quantity),
        currency="USD",
        reservation_id=reservation_id,
        reservation_kind="CASH" if reserved_amount is not None else None,
        reserved_amount=Decimal(reserved_amount) if reserved_amount is not None else None,
    )


def event(
    event_id: str,
    order_id: str,
    sequence: int,
    kind: str,
    *,
    provider_id: str | None = None,
) -> BrokerOrderEvent:
    return BrokerOrderEvent(
        event_id=event_id,
        order_id=order_id,
        provider_event_id=provider_id or event_id,
        event_type=kind,
        event_sequence=sequence,
        event_at=T0 + timedelta(minutes=sequence),
        received_at=T0 + timedelta(minutes=sequence),
        event_payload_hash=(event_id.encode().hex() * 64)[:64],
    )


def fill(
    fill_id: str,
    order_id: str,
    provider_id: str,
    side: str,
    quantity: str,
    price: str,
    minute: int,
    *,
    instrument_id: str = "instrument-1",
) -> Fill:
    return Fill(
        fill_id=fill_id,
        order_id=order_id,
        provider_fill_id=provider_id,
        instrument_id=instrument_id,
        side=side,  # type: ignore[arg-type]
        quantity=Decimal(quantity),
        price=Decimal(price),
        currency="USD",
        filled_at=T0 + timedelta(minutes=minute),
        received_at=T0 + timedelta(minutes=minute + 10),
    )


def correction(
    correction_id: str,
    fill_id: str,
    source_event_id: str,
    kind: str,
    quantity_delta: str,
    price_delta: str,
    minute: int,
) -> FillCorrection:
    return FillCorrection(
        correction_id=correction_id,
        original_fill_id=fill_id,
        source_event_id=source_event_id,
        correction_kind=kind,  # type: ignore[arg-type]
        quantity_delta=Decimal(quantity_delta),
        price_delta=Decimal(price_delta),
        reason_code="provider_correction",
        corrected_at=T0 + timedelta(minutes=minute),
    )


def test_duplicate_and_out_of_order_partial_fills_rebuild_once():
    ledger = DurablePositionLedger(episode())
    ledger.register_order(
        order(
            "buy-1",
            "BUY",
            "10",
            reserved_amount="110",
            reservation_id="reservation-1",
        )
    )
    ledger.append_event(event("accepted", "buy-1", 0, "ACCEPTED"))

    # The later fill is received first; replay sorts by economic fill time.
    ledger.append_event(event("partial-2", "buy-1", 2, "PARTIAL_FILL"))
    ledger.append_fill(fill("fill-2", "buy-1", "provider-fill-2", "BUY", "4", "11", 2))
    ledger.append_event(event("partial-1", "buy-1", 1, "PARTIAL_FILL"))
    first_fill = fill("fill-1", "buy-1", "provider-fill-1", "BUY", "3", "10", 1)
    assert ledger.append_fill(first_fill)
    assert not ledger.append_fill(
        fill(
            "duplicate-transport-row",
            "buy-1",
            "provider-fill-1",
            "BUY",
            "3",
            "10",
            1,
        )
    )

    projection = ledger.rebuild()
    assert projection.status == "RECONCILED"
    assert projection.cash_balance == Decimal("926.000000000000")
    assert len(projection.positions) == 1
    assert projection.positions[0].quantity == Decimal("7.000000000000")
    assert projection.positions[0].average_cost == Decimal("10.571428571429")
    settlement = projection.reservations[0]
    assert settlement.state == "PARTIALLY_CONSUMED"
    assert settlement.cumulative_fill_quantity == Decimal("7.000000000000")
    assert settlement.remaining_amount == Decimal("33.000000000000")

    rebuilt = ledger.rebuild()
    assert rebuilt == projection
    assert rebuilt.projection_hash == projection.projection_hash
    assert len(ledger.fills) == 2


def test_provider_event_identity_conflict_holds_reservation_capacity():
    ledger = DurablePositionLedger(episode())
    ledger.register_order(
        order(
            "buy-1",
            "BUY",
            "5",
            reserved_amount="50",
            reservation_id="reservation-1",
        )
    )
    accepted = event("event-1", "buy-1", 0, "ACCEPTED", provider_id="shared-event")
    ledger.append_event(accepted)
    ledger.append_event(
        BrokerOrderEvent(
            event_id="event-2",
            order_id="buy-1",
            provider_event_id="shared-event",
            event_type="CANCELLED",
            event_sequence=1,
            event_at=T0 + timedelta(minutes=1),
            received_at=T0 + timedelta(minutes=1),
            event_payload_hash=accepted.event_payload_hash,
        )
    )

    projection = ledger.rebuild()
    assert projection.status == "HOLD"
    assert "provider_event_conflict:shared-event" in projection.hold_reasons
    assert projection.reservations[0].state == "HELD"
    assert projection.reservations[0].remaining_amount == Decimal("50.000000000000")


def test_correction_bust_is_compensating_and_never_deletes_fill():
    ledger = DurablePositionLedger(episode())
    ledger.register_order(order("buy-1", "BUY", "4"))
    ledger.append_event(event("accepted", "buy-1", 0, "ACCEPTED"))
    original = fill("fill-1", "buy-1", "provider-fill-1", "BUY", "4", "10", 1)
    ledger.append_fill(original)
    ledger.append_event(event("correction-event", "buy-1", 1, "CORRECTION"))
    ledger.append_correction(
        correction("correction-1", "fill-1", "correction-event", "BUST", "-4", "0", 2)
    )

    projection = ledger.rebuild()
    assert projection.status == "RECONCILED"
    assert projection.cash_balance == Decimal("1000.000000000000")
    assert projection.positions == ()
    assert len(ledger.fills) == 1
    assert len(ledger.corrections) == 1


def test_quantity_price_and_fee_corrections_replay_deterministically():
    ledger = DurablePositionLedger(episode())
    ledger.register_order(order("buy-1", "BUY", "10"))
    ledger.append_fill(fill("fill-1", "buy-1", "provider-fill-1", "BUY", "10", "10", 1))
    for sequence in range(1, 4):
        ledger.append_event(
            event(f"correction-event-{sequence}", "buy-1", sequence, "CORRECTION")
        )
    ledger.append_correction(
        correction(
            "quantity-correction",
            "fill-1",
            "correction-event-1",
            "QUANTITY_ADJUSTMENT",
            "-2",
            "0",
            2,
        )
    )
    ledger.append_correction(
        correction(
            "price-correction",
            "fill-1",
            "correction-event-2",
            "PRICE_ADJUSTMENT",
            "0",
            "2",
            3,
        )
    )
    ledger.append_correction(
        correction(
            "fee-correction",
            "fill-1",
            "correction-event-3",
            "FEE_ADJUSTMENT",
            "0",
            "0.01",
            4,
        )
    )

    projection = ledger.rebuild()
    assert projection.status == "RECONCILED"
    assert projection.positions[0].quantity == Decimal("8.000000000000")
    assert projection.positions[0].average_cost == Decimal("12.000000000000")
    assert projection.cash_balance == Decimal("903.920000000000")


def test_sell_cannot_project_a_short_but_conflicting_fill_is_preserved():
    ledger = DurablePositionLedger(episode())
    ledger.register_order(order("buy-1", "BUY", "3"))
    ledger.register_order(order("sell-1", "SELL", "4"))
    ledger.append_fill(fill("fill-buy", "buy-1", "buy-fill", "BUY", "3", "10", 1))
    excess_sale = fill("fill-sell", "sell-1", "sell-fill", "SELL", "4", "11", 2)
    ledger.append_fill(excess_sale)

    projection = ledger.rebuild()
    assert projection.status == "HOLD"
    assert "short_position_blocked:instrument-1:fill-sell" in projection.hold_reasons
    assert projection.positions[0].quantity == Decimal("3.000000000000")
    assert all(position.quantity >= 0 for position in projection.positions)
    assert len(ledger.fills) == 2


def test_duplicate_provider_identity_with_changed_payload_is_held_not_counted_twice():
    ledger = DurablePositionLedger(episode())
    ledger.register_order(order("buy-1", "BUY", "5"))
    ledger.append_fill(fill("fill-1", "buy-1", "provider-1", "BUY", "2", "10", 1))
    ledger.append_fill(fill("fill-2", "buy-1", "provider-1", "BUY", "2", "12", 1))

    projection = ledger.rebuild()
    assert projection.status == "HOLD"
    assert "provider_fill_conflict:provider-1" in projection.hold_reasons
    assert projection.positions[0].quantity == Decimal("2.000000000000")
    assert projection.cash_balance == Decimal("980.000000000000")
    assert len(ledger.fills) == 2


def test_corporate_action_adjustments_are_explicit_and_reproducible():
    ledger = DurablePositionLedger(episode())
    ledger.register_order(order("buy-1", "BUY", "4"))
    ledger.append_fill(fill("fill-1", "buy-1", "provider-fill-1", "BUY", "4", "100", 1))
    ledger.append_corporate_action(
        CorporateActionAdjustment(
            adjustment_id="split-adjustment",
            corporate_action_id="action-split",
            instrument_id="instrument-1",
            currency="USD",
            effective_at=T0 + timedelta(minutes=2),
            share_ratio=Decimal("2"),
            cash_per_share=Decimal("0"),
        )
    )
    ledger.append_corporate_action(
        CorporateActionAdjustment(
            adjustment_id="distribution-adjustment",
            corporate_action_id="action-dividend",
            instrument_id="instrument-1",
            currency="USD",
            effective_at=T0 + timedelta(minutes=3),
            share_ratio=Decimal("1"),
            cash_per_share=Decimal("0.5"),
        )
    )

    projection = ledger.rebuild()
    assert projection.status == "RECONCILED"
    assert projection.positions[0].quantity == Decimal("8.000000000000")
    assert projection.positions[0].average_cost == Decimal("50.000000000000")
    assert projection.positions[0].corporate_action_ids == (
        "action-dividend",
        "action-split",
    )
    assert projection.cash_balance == Decimal("604.000000000000")


def test_cumulative_quantity_violation_holds_reservation_and_projection():
    ledger = DurablePositionLedger(episode())
    ledger.register_order(
        order(
            "buy-1",
            "BUY",
            "2",
            reserved_amount="20",
            reservation_id="reservation-1",
        )
    )
    ledger.append_fill(fill("fill-1", "buy-1", "provider-1", "BUY", "3", "10", 1))

    projection = ledger.rebuild()
    assert projection.status == "HOLD"
    assert "cumulative_quantity_exceeded:buy-1" in projection.hold_reasons
    assert projection.reservations[0].state == "HELD"
    assert projection.reservations[0].remaining_amount == Decimal("20.000000000000")
