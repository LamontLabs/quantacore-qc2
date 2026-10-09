"""Append-only, idempotent in-process ledger facade for QC2 execution records."""

from __future__ import annotations

from threading import RLock

from .model import (
    BrokerOrderEvent,
    CorporateActionAdjustment,
    ExecutionEpisodeSeed,
    Fill,
    FillCorrection,
    OrderSpec,
    ProjectionSnapshot,
)
from .projector import _event_signature, _fill_signature, rebuild_projection


class DurablePositionLedger:
    """Keep immutable source records and rebuild projections without overwrites.

    PostgreSQL persistence is provided by the matching QC2 migration. This
    facade implements the deterministic domain rules independently so the
    migration adapter and acceptance tests can share one replay contract.
    """

    def __init__(self, episode: ExecutionEpisodeSeed) -> None:
        self.episode = episode
        self._orders: list[OrderSpec] = []
        self._events: list[BrokerOrderEvent] = []
        self._fills: list[Fill] = []
        self._corrections: list[FillCorrection] = []
        self._corporate_actions: list[CorporateActionAdjustment] = []
        self._lock = RLock()

    @property
    def orders(self) -> tuple[OrderSpec, ...]:
        return tuple(self._orders)

    @property
    def events(self) -> tuple[BrokerOrderEvent, ...]:
        return tuple(self._events)

    @property
    def fills(self) -> tuple[Fill, ...]:
        return tuple(self._fills)

    @property
    def corrections(self) -> tuple[FillCorrection, ...]:
        return tuple(self._corrections)

    @property
    def corporate_actions(self) -> tuple[CorporateActionAdjustment, ...]:
        return tuple(self._corporate_actions)

    def register_order(self, order: OrderSpec) -> bool:
        with self._lock:
            prior = next(
                (row for row in self._orders if row.order_id == order.order_id), None
            )
            if prior is not None:
                if prior != order:
                    raise ValueError("order identity was reused with different content")
                return False
            if order.episode_id != self.episode.episode_id:
                raise ValueError("order must belong to this execution episode")
            self._orders.append(order)
            return True

    def append_event(self, event: BrokerOrderEvent) -> bool:
        with self._lock:
            if not any(row.order_id == event.order_id for row in self._orders):
                raise ValueError("broker event must reference a registered order")
            prior = next(
                (
                    row
                    for row in self._events
                    if row.order_id == event.order_id
                    and row.provider_event_id == event.provider_event_id
                ),
                None,
            )
            if prior is not None and _event_signature(prior) == _event_signature(event):
                return False
            self._events.append(event)
            return True

    def append_fill(self, fill: Fill) -> bool:
        with self._lock:
            if not any(row.order_id == fill.order_id for row in self._orders):
                raise ValueError("fill must reference a registered order")
            prior = next(
                (
                    row
                    for row in self._fills
                    if row.order_id == fill.order_id
                    and row.provider_fill_id == fill.provider_fill_id
                ),
                None,
            )
            if prior is not None and _fill_signature(prior) == _fill_signature(fill):
                return False
            # A reused provider ID with different economics is preserved as a
            # second immutable fact; replay marks the episode HOLD.
            self._fills.append(fill)
            return True

    def append_correction(self, correction: FillCorrection) -> bool:
        with self._lock:
            if not any(row.fill_id == correction.original_fill_id for row in self._fills):
                raise ValueError("correction must reference a preserved fill")
            if not any(row.event_id == correction.source_event_id for row in self._events):
                raise ValueError("correction must reference a preserved broker event")
            prior = next(
                (
                    row
                    for row in self._corrections
                    if row.correction_id == correction.correction_id
                ),
                None,
            )
            if prior == correction:
                return False
            self._corrections.append(correction)
            return True

    def append_corporate_action(
        self, adjustment: CorporateActionAdjustment
    ) -> bool:
        with self._lock:
            prior = next(
                (
                    row
                    for row in self._corporate_actions
                    if row.adjustment_id == adjustment.adjustment_id
                ),
                None,
            )
            if prior is not None:
                if prior != adjustment:
                    raise ValueError("adjustment identity was reused with different content")
                return False
            self._corporate_actions.append(adjustment)
            return True

    def rebuild(self) -> ProjectionSnapshot:
        with self._lock:
            return rebuild_projection(
                self.episode,
                tuple(self._orders),
                tuple(self._events),
                tuple(self._fills),
                tuple(self._corrections),
                tuple(self._corporate_actions),
            )
