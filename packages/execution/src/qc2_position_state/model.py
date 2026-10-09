"""Immutable values used by the durable execution-position ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

Side = Literal["BUY", "SELL"]
CorrectionKind = Literal[
    "BUST", "QUANTITY_ADJUSTMENT", "PRICE_ADJUSTMENT", "FEE_ADJUSTMENT"
]
ProjectionStatus = Literal["RECONCILED", "HOLD"]
ReservationState = Literal[
    "ACTIVE", "PARTIALLY_CONSUMED", "SETTLED", "RELEASED", "HELD"
]


@dataclass(frozen=True, slots=True)
class OpeningPosition:
    instrument_id: str
    quantity: Decimal
    average_cost: Decimal
    currency: str
    source_fill_ids: tuple[str, ...] = ()
    corporate_action_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExecutionEpisodeSeed:
    episode_id: str
    episode_hash: str
    content_hash: str
    account_fingerprint: str
    currency: str
    opening_cash: Decimal
    opened_at: datetime
    opening_positions: tuple[OpeningPosition, ...] = ()


@dataclass(frozen=True, slots=True)
class OrderSpec:
    order_id: str
    episode_id: str
    instrument_id: str
    side: Side
    quantity: Decimal
    currency: str
    reservation_id: str | None = None
    reservation_kind: Literal["CASH", "SHARES"] | None = None
    reserved_amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class BrokerOrderEvent:
    event_id: str
    order_id: str
    provider_event_id: str
    event_type: str
    event_sequence: int
    event_at: datetime
    received_at: datetime
    event_payload_hash: str


@dataclass(frozen=True, slots=True)
class Fill:
    fill_id: str
    order_id: str
    provider_fill_id: str
    instrument_id: str
    side: Side
    quantity: Decimal
    price: Decimal
    currency: str
    filled_at: datetime
    received_at: datetime


@dataclass(frozen=True, slots=True)
class FillCorrection:
    correction_id: str
    original_fill_id: str
    source_event_id: str
    correction_kind: CorrectionKind
    quantity_delta: Decimal
    price_delta: Decimal
    reason_code: str
    corrected_at: datetime


@dataclass(frozen=True, slots=True)
class CorporateActionAdjustment:
    """Explicit, normalized adjustment supplied by an authorized caller.

    ``share_ratio`` changes shares while preserving cost basis. A
    ``cash_per_share`` amount posts a cash distribution against the shares held
    immediately before the adjustment. No market-data lookup is performed.
    """

    adjustment_id: str
    corporate_action_id: str
    instrument_id: str
    currency: str
    effective_at: datetime
    share_ratio: Decimal
    cash_per_share: Decimal


@dataclass(frozen=True, slots=True)
class PositionProjection:
    episode_id: str
    instrument_id: str
    quantity: Decimal
    average_cost: Decimal
    currency: str
    as_of: datetime
    source_fill_ids: tuple[str, ...]
    corporate_action_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReservationSettlement:
    order_id: str
    reservation_id: str
    state: ReservationState
    original_amount: Decimal
    remaining_amount: Decimal
    settled_amount: Decimal
    cumulative_fill_quantity: Decimal


@dataclass(frozen=True, slots=True)
class ProjectionSnapshot:
    episode_id: str
    currency: str
    cash_balance: Decimal
    positions: tuple[PositionProjection, ...]
    reservations: tuple[ReservationSettlement, ...]
    status: ProjectionStatus
    hold_reasons: tuple[str, ...]
    as_of: datetime
    projection_hash: str
