"""Deterministic replay of immutable execution records."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Iterable

from .model import (
    BrokerOrderEvent,
    CorporateActionAdjustment,
    ExecutionEpisodeSeed,
    Fill,
    FillCorrection,
    OrderSpec,
    PositionProjection,
    ProjectionSnapshot,
    ReservationSettlement,
)

SCALE = Decimal("0.000000000001")
ZERO = Decimal("0")
ONE = Decimal("1")
TERMINAL_EVENTS = frozenset({"CANCELLED", "REJECTED", "EXPIRED"})
KNOWN_CORRECTIONS = frozenset(
    {"BUST", "QUANTITY_ADJUSTMENT", "PRICE_ADJUSTMENT", "FEE_ADJUSTMENT"}
)


def decimal12(value: Decimal | str | int) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ValueError("decimal value is invalid") from exc
    if not number.is_finite():
        raise ValueError("decimal value must be finite")
    with localcontext() as context:
        context.prec = 50
        rounded = number.quantize(SCALE, rounding=ROUND_HALF_EVEN)
    if abs(rounded) >= Decimal("100000000000000000000000000"):
        raise ValueError("decimal value exceeds numeric(38,12)")
    return rounded


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def _canonical_time(value: datetime) -> str:
    return _instant(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fill_signature(fill: Fill) -> tuple[object, ...]:
    # Provider identity is semantic; transport timestamps and QC2 record IDs
    # do not make the same provider fill a second trade.
    return (
        fill.order_id,
        fill.provider_fill_id,
        fill.instrument_id,
        fill.side,
        decimal12(fill.quantity),
        decimal12(fill.price),
        fill.currency,
        _instant(fill.filled_at),
    )


def _event_signature(event: BrokerOrderEvent) -> tuple[object, ...]:
    return (
        event.order_id,
        event.provider_event_id,
        event.event_type,
        event.event_sequence,
        _instant(event.event_at),
        event.event_payload_hash,
    )


def _effective_fills(
    fills: tuple[Fill, ...],
    corrections: tuple[FillCorrection, ...],
    events_by_id: dict[str, BrokerOrderEvent],
    order_by_id: dict[str, OrderSpec],
    issues: list[str],
) -> tuple[dict[str, tuple[Decimal, Decimal]], dict[str, Decimal]]:
    fill_by_id = {fill.fill_id: fill for fill in fills}
    correction_groups: dict[str, list[FillCorrection]] = defaultdict(list)
    correction_ids: dict[str, FillCorrection] = {}
    seen_source_events: dict[tuple[str, str], FillCorrection] = {}
    for correction in sorted(
        corrections, key=lambda row: (_instant(row.corrected_at), row.correction_id)
    ):
        prior_id = correction_ids.get(correction.correction_id)
        if prior_id is not None and prior_id != correction:
            issues.append(f"correction_id_conflict:{correction.correction_id}")
            continue
        correction_ids[correction.correction_id] = correction
        key = (correction.original_fill_id, correction.source_event_id)
        prior_source = seen_source_events.get(key)
        if prior_source is not None:
            if prior_source != correction:
                issues.append(f"correction_event_conflict:{correction.source_event_id}")
            continue
        seen_source_events[key] = correction

        fill = fill_by_id.get(correction.original_fill_id)
        event = events_by_id.get(correction.source_event_id)
        if fill is None:
            issues.append(f"correction_missing_fill:{correction.correction_id}")
            continue
        if event is None or event.event_type != "CORRECTION":
            issues.append(f"correction_missing_source_event:{correction.correction_id}")
            continue
        order = order_by_id.get(fill.order_id)
        if order is None or event.order_id != order.order_id:
            issues.append(f"correction_order_mismatch:{correction.correction_id}")
            continue
        correction_groups[fill.fill_id].append(correction)

    effective: dict[str, tuple[Decimal, Decimal]] = {}
    fee_cash: dict[str, Decimal] = {}
    for fill in fills:
        quantity = decimal12(fill.quantity)
        price = decimal12(fill.price)
        fees = ZERO
        for correction in correction_groups.get(fill.fill_id, []):
            quantity_delta = decimal12(correction.quantity_delta)
            price_delta = decimal12(correction.price_delta)
            kind = correction.correction_kind
            valid = True
            if kind == "BUST":
                # BUST is a signed compensating quantity; price stays intact so
                # the original notional is exactly reversed.
                valid = quantity_delta == -quantity and price_delta == ZERO
                if valid:
                    quantity = ZERO
            elif kind == "QUANTITY_ADJUSTMENT":
                valid = price_delta == ZERO and quantity + quantity_delta >= ZERO
                if valid:
                    quantity = decimal12(quantity + quantity_delta)
            elif kind == "PRICE_ADJUSTMENT":
                valid = quantity_delta == ZERO and price + price_delta > ZERO
                if valid:
                    price = decimal12(price + price_delta)
            elif kind == "FEE_ADJUSTMENT":
                valid = quantity_delta == ZERO
                if valid:
                    # The contract's price_delta is currency/share. A positive
                    # fee correction is an additional cash outflow.
                    fees = decimal12(fees - price_delta * quantity)
            else:
                valid = False
            if not valid:
                issues.append(f"invalid_{kind.lower()}:{correction.correction_id}")
        if quantity < ZERO or price <= ZERO:
            issues.append(f"invalid_effective_fill:{fill.fill_id}")
            continue
        effective[fill.fill_id] = (quantity, price)
        fee_cash[fill.fill_id] = fees
    return effective, fee_cash


def rebuild_projection(
    episode: ExecutionEpisodeSeed,
    orders: Iterable[OrderSpec],
    events: Iterable[BrokerOrderEvent],
    fills: Iterable[Fill],
    corrections: Iterable[FillCorrection],
    corporate_actions: Iterable[CorporateActionAdjustment] = (),
) -> ProjectionSnapshot:
    """Rebuild one episode projection without mutating any ledger record.

    Invalid or contradictory broker facts remain represented by the caller's
    ledger and produce a HOLD projection. A short position is never emitted.
    """

    order_rows = tuple(orders)
    event_rows = tuple(events)
    fill_rows = tuple(fills)
    correction_rows = tuple(corrections)
    action_rows = tuple(corporate_actions)
    issues: list[str] = []
    order_by_id: dict[str, OrderSpec] = {}

    for order in order_rows:
        prior = order_by_id.get(order.order_id)
        if prior is not None and prior != order:
            issues.append(f"order_id_conflict:{order.order_id}")
            continue
        if order.episode_id != episode.episode_id:
            issues.append(f"order_episode_mismatch:{order.order_id}")
        if decimal12(order.quantity) <= ZERO:
            issues.append(f"invalid_order_quantity:{order.order_id}")
        order_by_id[order.order_id] = order

    provider_events: dict[tuple[str, str], BrokerOrderEvent] = {}
    sequences: dict[tuple[str, int], BrokerOrderEvent] = {}
    event_by_id: dict[str, BrokerOrderEvent] = {}
    for event in sorted(
        event_rows,
        key=lambda row: (row.order_id, row.event_sequence, row.event_id),
    ):
        if event.order_id not in order_by_id:
            issues.append(f"event_missing_order:{event.event_id}")
        prior_id = event_by_id.get(event.event_id)
        if prior_id is not None and prior_id != event:
            issues.append(f"event_id_conflict:{event.event_id}")
            continue
        event_by_id[event.event_id] = event
        key = (event.order_id, event.provider_event_id)
        prior_provider = provider_events.get(key)
        if prior_provider is not None:
            if (
                prior_provider.event_payload_hash != event.event_payload_hash
                or prior_provider.event_type != event.event_type
                or prior_provider.event_sequence != event.event_sequence
                or _instant(prior_provider.event_at) != _instant(event.event_at)
            ):
                issues.append(f"provider_event_conflict:{event.provider_event_id}")
            continue
        provider_events[key] = event
        sequence_key = (event.order_id, event.event_sequence)
        prior_sequence = sequences.get(sequence_key)
        if prior_sequence is not None:
            if (
                prior_sequence.provider_event_id != event.provider_event_id
                or prior_sequence.event_payload_hash != event.event_payload_hash
                or prior_sequence.event_type != event.event_type
                or _instant(prior_sequence.event_at) != _instant(event.event_at)
            ):
                issues.append(f"event_sequence_conflict:{event.order_id}:{event.event_sequence}")
            continue
        sequences[sequence_key] = event

    # Corrections must be able to resolve their source against this preserved
    # event ledger; duplicate and conflicting provider facts are not discarded.
    effective_fill_rows: list[Fill] = []
    seen_fill_identity: dict[tuple[str, str], Fill] = {}
    for fill in sorted(
        fill_rows,
        key=lambda row: (row.order_id, row.provider_fill_id, row.fill_id),
    ):
        order = order_by_id.get(fill.order_id)
        if order is None:
            issues.append(f"fill_missing_order:{fill.fill_id}")
            continue
        if (
            fill.instrument_id != order.instrument_id
            or fill.side != order.side
            or fill.currency != order.currency
            or fill.currency != episode.currency
        ):
            issues.append(f"fill_order_mismatch:{fill.fill_id}")
        identity = (fill.order_id, fill.provider_fill_id)
        prior = seen_fill_identity.get(identity)
        if prior is not None:
            if _fill_signature(prior) != _fill_signature(fill):
                issues.append(f"provider_fill_conflict:{fill.provider_fill_id}")
            continue
        seen_fill_identity[identity] = fill
        effective_fill_rows.append(fill)

    # A correction may reference a fill that was represented by a conflicting
    # duplicate. Bind it to the canonical provider-fill row only.
    canonical_fill_ids = {row.fill_id for row in effective_fill_rows}
    canonical_corrections = tuple(
        row for row in correction_rows if row.original_fill_id in canonical_fill_ids
    )
    canonical_events = {
        event_id: event for event_id, event in event_by_id.items()
    }
    effective, fee_cash = _effective_fills(
        tuple(effective_fill_rows),
        canonical_corrections,
        canonical_events,
        order_by_id,
        issues,
    )

    fills_by_order: dict[str, Decimal] = defaultdict(lambda: ZERO)
    fills_by_instrument: dict[str, list[Fill]] = defaultdict(list)
    cash = decimal12(episode.opening_cash)
    for fill in effective_fill_rows:
        quantity_price = effective.get(fill.fill_id)
        if quantity_price is None:
            continue
        quantity, price = quantity_price
        fills_by_order[fill.order_id] = decimal12(fills_by_order[fill.order_id] + quantity)
        fills_by_instrument[fill.instrument_id].append(fill)
        sign = ONE if fill.side == "SELL" else -ONE
        cash = decimal12(cash + sign * quantity * price + fee_cash.get(fill.fill_id, ZERO))

    for order_id, cumulative in fills_by_order.items():
        order = order_by_id[order_id]
        if cumulative > decimal12(order.quantity):
            issues.append(f"cumulative_quantity_exceeded:{order_id}")

    actions_by_instrument: dict[str, list[CorporateActionAdjustment]] = defaultdict(list)
    for action in action_rows:
        if action.currency != episode.currency:
            issues.append(f"corporate_action_currency_mismatch:{action.adjustment_id}")
        if _instant(action.effective_at) < _instant(episode.opened_at):
            issues.append(f"corporate_action_before_episode:{action.adjustment_id}")
        if decimal12(action.share_ratio) <= ZERO:
            issues.append(f"invalid_corporate_action_ratio:{action.adjustment_id}")
            continue
        if decimal12(action.cash_per_share) < ZERO:
            issues.append(f"invalid_corporate_action_cash:{action.adjustment_id}")
            continue
        actions_by_instrument[action.instrument_id].append(action)

    position_ids = {
        position.instrument_id
        for position in episode.opening_positions
    } | set(fills_by_instrument) | set(actions_by_instrument)
    positions: list[PositionProjection] = []
    corporate_cash = ZERO

    for instrument_id in sorted(position_ids):
        opening = next(
            (
                row
                for row in episode.opening_positions
                if row.instrument_id == instrument_id
            ),
            None,
        )
        quantity = decimal12(opening.quantity) if opening else ZERO
        cost_basis = (
            decimal12(opening.quantity * opening.average_cost) if opening else ZERO
        )
        currency = opening.currency if opening else episode.currency
        if currency != episode.currency:
            issues.append(f"opening_position_currency_mismatch:{instrument_id}")
        source_fill_ids = set(opening.source_fill_ids if opening else ())
        action_ids = set(opening.corporate_action_ids if opening else ())
        timeline: list[tuple[datetime, int, str, object]] = []
        for action in actions_by_instrument.get(instrument_id, []):
            timeline.append((_instant(action.effective_at), 0, action.adjustment_id, action))
        for fill in fills_by_instrument.get(instrument_id, []):
            timeline.append((_instant(fill.filled_at), 1, fill.fill_id, fill))
        timeline.sort(key=lambda item: (item[0], item[1], item[2]))
        short_detected = False

        for _, _, _, item in timeline:
            if isinstance(item, CorporateActionAdjustment):
                previous_quantity = quantity
                ratio = decimal12(item.share_ratio)
                quantity = decimal12(quantity * ratio)
                if quantity > ZERO:
                    cost_basis = decimal12(cost_basis)
                corporate_cash = decimal12(
                    corporate_cash
                    + previous_quantity * decimal12(item.cash_per_share)
                )
                action_ids.add(item.corporate_action_id)
                continue

            fill = item
            effective_values = effective.get(fill.fill_id)
            if effective_values is None:
                continue
            fill_quantity, fill_price = effective_values
            if fill_quantity == ZERO:
                source_fill_ids.add(fill.fill_id)
                continue
            if fill.side == "BUY":
                quantity = decimal12(quantity + fill_quantity)
                cost_basis = decimal12(cost_basis + fill_quantity * fill_price)
                source_fill_ids.add(fill.fill_id)
            elif fill.side == "SELL":
                if fill_quantity > quantity:
                    issues.append(f"short_position_blocked:{instrument_id}:{fill.fill_id}")
                    short_detected = True
                    break
                if quantity > ZERO:
                    average_cost = decimal12(cost_basis / quantity)
                    quantity = decimal12(quantity - fill_quantity)
                    cost_basis = decimal12(cost_basis - average_cost * fill_quantity)
                if quantity == ZERO:
                    cost_basis = ZERO
                source_fill_ids.add(fill.fill_id)
            else:
                issues.append(f"invalid_fill_side:{fill.fill_id}")
                short_detected = True
                break

        if quantity > ZERO:
            average_cost = decimal12(cost_basis / quantity)
            positions.append(
                PositionProjection(
                    episode_id=episode.episode_id,
                    instrument_id=instrument_id,
                    quantity=quantity,
                    average_cost=average_cost,
                    currency=currency,
                    as_of=max(
                        [_instant(episode.opened_at)]
                        + [row[0] for row in timeline]
                    ),
                    source_fill_ids=tuple(sorted(source_fill_ids)),
                    corporate_action_ids=tuple(sorted(action_ids)),
                )
            )
        elif not short_detected and quantity < ZERO:
            # This is defensive: all sell paths check before subtracting.
            issues.append(f"negative_position_blocked:{instrument_id}")

    cash = decimal12(cash + corporate_cash)
    event_groups: dict[str, list[BrokerOrderEvent]] = defaultdict(list)
    for event in provider_events.values():
        event_groups[event.order_id].append(event)

    reservations: list[ReservationSettlement] = []
    for order in sorted(order_by_id.values(), key=lambda row: row.order_id):
        if order.reservation_id is None or order.reserved_amount is None:
            continue
        original_amount = decimal12(order.reserved_amount)
        if original_amount < ZERO:
            issues.append(f"invalid_reservation_amount:{order.order_id}")
            continue
        cumulative = fills_by_order.get(order.order_id, ZERO)
        order_events = event_groups.get(order.order_id, [])
        latest_event = max(
            order_events,
            key=lambda row: (row.event_sequence, row.event_id),
            default=None,
        )
        terminal = (
            latest_event is not None and latest_event.event_type in TERMINAL_EVENTS
        ) or cumulative >= decimal12(order.quantity)
        # Any unresolved episode discrepancy keeps every reservation intact;
        # resolving one order must not free capacity while the episode is held.
        order_held = bool(issues)
        if order_held:
            state = "HELD"
            remaining = original_amount
        elif terminal:
            state = (
                "SETTLED"
                if cumulative >= decimal12(order.quantity)
                else "RELEASED"
            )
            remaining = ZERO
        else:
            remaining_quantity = max(decimal12(order.quantity) - cumulative, ZERO)
            with localcontext() as context:
                context.prec = 50
                remaining = decimal12(
                    original_amount * remaining_quantity / decimal12(order.quantity)
                )
            state = "PARTIALLY_CONSUMED" if cumulative > ZERO else "ACTIVE"
        reservations.append(
            ReservationSettlement(
                order_id=order.order_id,
                reservation_id=order.reservation_id,
                state=state,  # type: ignore[arg-type]
                original_amount=original_amount,
                remaining_amount=remaining,
                settled_amount=decimal12(original_amount - remaining),
                cumulative_fill_quantity=cumulative,
            )
        )

    as_of_values = [_instant(episode.opened_at)]
    as_of_values.extend(_instant(row.event_at) for row in event_rows)
    as_of_values.extend(_instant(row.filled_at) for row in fill_rows)
    as_of_values.extend(_instant(row.corrected_at) for row in correction_rows)
    as_of_values.extend(_instant(row.effective_at) for row in action_rows)
    as_of = max(as_of_values)
    status = "HOLD" if issues else "RECONCILED"
    snapshot_payload = {
        "episode_id": episode.episode_id,
        "episode_hash": episode.episode_hash,
        "episode_content_hash": episode.content_hash,
        "cash": _decimal_text(cash),
        "currency": episode.currency,
        "status": status,
        "hold_reasons": sorted(set(issues)),
        "positions": [
            {
                "instrument_id": row.instrument_id,
                "quantity": _decimal_text(row.quantity),
                "average_cost": _decimal_text(row.average_cost),
                "currency": row.currency,
                "source_fill_ids": row.source_fill_ids,
                "corporate_action_ids": row.corporate_action_ids,
            }
            for row in sorted(positions, key=lambda row: row.instrument_id)
        ],
        "events": sorted(
            (row.event_id, row.event_payload_hash, row.event_sequence)
            for row in event_rows
        ),
        "fills": sorted(
            (
                row.fill_id,
                row.provider_fill_id,
                _decimal_text(decimal12(row.quantity)),
                _decimal_text(decimal12(row.price)),
            )
            for row in fill_rows
        ),
        "corrections": sorted(
            (
                row.correction_id,
                row.original_fill_id,
                row.source_event_id,
                row.correction_kind,
            )
            for row in correction_rows
        ),
        "actions": sorted(row.adjustment_id for row in action_rows),
    }
    projection_hash = _fingerprint(snapshot_payload)
    return ProjectionSnapshot(
        episode_id=episode.episode_id,
        currency=episode.currency,
        cash_balance=cash,
        positions=tuple(sorted(positions, key=lambda row: row.instrument_id)),
        reservations=tuple(reservations),
        status=status,  # type: ignore[arg-type]
        hold_reasons=tuple(sorted(set(issues))),
        as_of=as_of,
        projection_hash=projection_hash,
    )
