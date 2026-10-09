"""Immutable input values for fixture-only broker reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from types import MappingProxyType
from typing import Any, Mapping

from qc2_alpaca_paper.models import NormalizedFill, NormalizedOrder


_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")


def exact_decimal(value: Decimal | str | int, field: str) -> Decimal:
    """Parse exact fixture values without accepting float or boolean coercion."""
    if isinstance(value, (bool, float)):
        raise ValueError(f"{field} must be an exact decimal, not float or boolean")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an exact decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def decimal_text(value: Decimal) -> str:
    """Return stable non-exponent decimal text for hashing and evidence."""
    if not value.is_finite():
        raise ValueError("decimal value must be finite")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _uuid7(value: str, field: str) -> None:
    if not isinstance(value, str) or not _UUID7.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase UUIDv7")


def _sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _currency(value: str, field: str = "currency") -> None:
    if not isinstance(value, str) or not _CURRENCY.fullmatch(value):
        raise ValueError(f"{field} must be an uppercase ISO currency code")


def _freeze_ref(value: Mapping[str, Any], *, schema_name: str, field: str) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a typed contract reference")
    target_schema = value.get("target_schema_name")
    target_id = value.get("target_id")
    if target_schema != schema_name:
        raise ValueError(f"{field} has the wrong target schema")
    _uuid7(target_id, f"{field}.target_id")
    frozen = {
        "target_schema_name": target_schema,
        "target_id": target_id,
    }
    content_hash = value.get("content_hash")
    if content_hash is not None:
        _sha256(content_hash, f"{field}.content_hash")
        frozen["content_hash"] = content_hash
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class CashBalance:
    currency: str
    balance: Decimal

    def __post_init__(self) -> None:
        _currency(self.currency)
        object.__setattr__(self, "balance", exact_decimal(self.balance, "cash balance"))


@dataclass(frozen=True, slots=True)
class LocalOrder:
    order_ref: Mapping[str, Any]
    broker_order_id: str
    intent_id: str
    client_order_key: str
    symbol: str
    side: str
    quantity: Decimal
    filled_quantity: Decimal
    order_type: str
    time_in_force: str
    limit_price: Decimal
    state: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "order_ref",
            _freeze_ref(
                self.order_ref,
                schema_name="qc2.execution.BrokerOrder.v1",
                field="order_ref",
            ),
        )
        _uuid7(self.intent_id, "intent_id")
        if not isinstance(self.broker_order_id, str) or not self.broker_order_id:
            raise ValueError("broker_order_id must be non-empty")
        if not isinstance(self.client_order_key, str) or not self.client_order_key:
            raise ValueError("client_order_key must be non-empty")
        if not isinstance(self.symbol, str) or not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("symbol must use the normalized uppercase symbol form")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        quantity = exact_decimal(self.quantity, "order quantity")
        filled = exact_decimal(self.filled_quantity, "filled quantity")
        price = exact_decimal(self.limit_price, "limit price")
        if quantity <= 0 or filled < 0 or filled > quantity or price <= 0:
            raise ValueError("local order quantities or limit price are out of range")
        if self.order_type != "LIMIT" or self.time_in_force != "DAY":
            raise ValueError("only regular-session DAY limit orders are supported")
        if not isinstance(self.state, str) or not self.state:
            raise ValueError("order state must be non-empty")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "filled_quantity", filled)
        object.__setattr__(self, "limit_price", price)


@dataclass(frozen=True, slots=True)
class LocalFill:
    provider_activity_id: str
    broker_order_id: str
    quantity: Decimal
    price: Decimal

    def __post_init__(self) -> None:
        if not self.provider_activity_id or not self.broker_order_id:
            raise ValueError("local fill identifiers must be non-empty")
        quantity = exact_decimal(self.quantity, "fill quantity")
        price = exact_decimal(self.price, "fill price")
        if quantity <= 0 or price <= 0:
            raise ValueError("local fill quantity and price must be positive")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "price", price)


@dataclass(frozen=True, slots=True)
class LocalPosition:
    position_ref: Mapping[str, Any]
    instrument_id: str
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "position_ref",
            _freeze_ref(
                self.position_ref,
                schema_name="qc2.execution.Position.v1",
                field="position_ref",
            ),
        )
        _uuid7(self.instrument_id, "instrument_id")
        if not isinstance(self.symbol, str) or not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("symbol must use the normalized uppercase symbol form")
        quantity = exact_decimal(self.quantity, "position quantity")
        average_cost = exact_decimal(self.average_cost, "position average cost")
        if quantity <= 0 or average_cost <= 0:
            raise ValueError("local positions must have positive quantity and cost")
        _currency(self.currency)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "average_cost", average_cost)


@dataclass(frozen=True, slots=True)
class RemotePosition:
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("symbol must use the normalized uppercase symbol form")
        quantity = exact_decimal(self.quantity, "remote position quantity")
        average_cost = exact_decimal(self.average_cost, "remote position average cost")
        if average_cost < 0:
            raise ValueError("remote position average cost cannot be negative")
        _currency(self.currency)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "average_cost", average_cost)


@dataclass(frozen=True, slots=True)
class UnknownSubmission:
    attempt_id: str
    intent_id: str
    account_fingerprint: str
    client_order_key: str
    normalized_request_hash: str
    expected_request: Mapping[str, Any]

    def __post_init__(self) -> None:
        _uuid7(self.attempt_id, "attempt_id")
        _uuid7(self.intent_id, "intent_id")
        _sha256(self.account_fingerprint, "account_fingerprint")
        _sha256(self.normalized_request_hash, "normalized_request_hash")
        if not isinstance(self.client_order_key, str) or not self.client_order_key:
            raise ValueError("client_order_key must be non-empty")
        if not isinstance(self.expected_request, Mapping):
            raise ValueError("expected_request must be a mapping")
        if any(
            not isinstance(key, str)
            or isinstance(value, float)
            or not (value is None or isinstance(value, (str, int, bool)))
            for key, value in self.expected_request.items()
        ):
            raise ValueError("expected_request must be a flat, exact JSON object")
        object.__setattr__(
            self,
            "expected_request",
            MappingProxyType(dict(self.expected_request)),
        )


@dataclass(frozen=True, slots=True)
class LocalInventorySnapshot:
    episode_ref: Mapping[str, Any]
    paper_account_fingerprint: str
    generation: int
    orders: tuple[LocalOrder, ...]
    fills: tuple[LocalFill, ...]
    positions: tuple[LocalPosition, ...]
    cash: tuple[CashBalance, ...]
    unknown_submissions: tuple[UnknownSubmission, ...] = ()
    symbol_to_instrument: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "episode_ref",
            _freeze_ref(
                self.episode_ref,
                schema_name="qc2.execution.ExecutionEpisode.v1",
                field="episode_ref",
            ),
        )
        if "content_hash" not in self.episode_ref:
            raise ValueError("episode_ref must include its content hash")
        _sha256(self.paper_account_fingerprint, "paper_account_fingerprint")
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise ValueError("local generation must be a non-negative integer")
        for name in (
            "orders",
            "fills",
            "positions",
            "cash",
            "unknown_submissions",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        _unique((row.broker_order_id for row in self.orders), "local broker order IDs")
        _unique((row.provider_activity_id for row in self.fills), "local fill IDs")
        _unique((row.instrument_id for row in self.positions), "local position instruments")
        _unique((row.currency for row in self.cash), "local cash currencies")
        _unique((row.attempt_id for row in self.unknown_submissions), "unknown attempt IDs")
        if any(not isinstance(row, LocalOrder) for row in self.orders):
            raise ValueError("orders must contain LocalOrder values")
        if any(not isinstance(row, LocalFill) for row in self.fills):
            raise ValueError("fills must contain LocalFill values")
        if any(not isinstance(row, LocalPosition) for row in self.positions):
            raise ValueError("positions must contain LocalPosition values")
        if any(not isinstance(row, CashBalance) for row in self.cash):
            raise ValueError("cash must contain CashBalance values")
        if any(not isinstance(row, UnknownSubmission) for row in self.unknown_submissions):
            raise ValueError("unknown_submissions must contain UnknownSubmission values")
        mapping = dict(self.symbol_to_instrument or {})
        for symbol, instrument_id in mapping.items():
            if not _SYMBOL.fullmatch(symbol):
                raise ValueError("symbol_to_instrument contains an invalid symbol")
            _uuid7(instrument_id, "symbol_to_instrument instrument ID")
        object.__setattr__(self, "symbol_to_instrument", MappingProxyType(mapping))


@dataclass(frozen=True, slots=True)
class BrokerInventorySnapshot:
    account_fingerprint: str
    read_token: str
    orders: tuple[NormalizedOrder, ...]
    fills: tuple[NormalizedFill, ...]
    positions: tuple[RemotePosition, ...]
    cash: tuple[CashBalance, ...]
    checked_sources: tuple[str, ...]
    orders_complete: bool
    fills_complete: bool
    positions_complete: bool
    cash_complete: bool
    consistency_window_closed: bool

    def __post_init__(self) -> None:
        _sha256(self.account_fingerprint, "account_fingerprint")
        if not isinstance(self.read_token, str) or not self.read_token.strip():
            raise ValueError("read_token must identify the fixture observation window")
        for name in ("orders", "fills", "positions", "cash", "checked_sources"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        for name in (
            "orders_complete",
            "fills_complete",
            "positions_complete",
            "cash_complete",
            "consistency_window_closed",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if any(not isinstance(source, str) or not source.strip() for source in self.checked_sources):
            raise ValueError("checked_sources must contain non-empty names")
        _unique(self.checked_sources, "checked source names")
        _unique((row.broker_order_id for row in self.orders), "remote broker order IDs")
        _unique((row.provider_activity_id for row in self.fills), "remote fill IDs")
        _unique((row.symbol for row in self.positions), "remote position symbols")
        _unique((row.currency for row in self.cash), "remote cash currencies")
        if any(not isinstance(row, NormalizedOrder) for row in self.orders):
            raise ValueError("orders must contain NormalizedOrder values")
        if any(not isinstance(row, NormalizedFill) for row in self.fills):
            raise ValueError("fills must contain NormalizedFill values")
        if any(not isinstance(row, RemotePosition) for row in self.positions):
            raise ValueError("positions must contain RemotePosition values")
        if any(not isinstance(row, CashBalance) for row in self.cash):
            raise ValueError("cash must contain CashBalance values")


def _unique(values: Any, field: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)):
        raise ValueError(f"{field} must be unique")


def normalized_order(value: NormalizedOrder) -> NormalizedOrder:
    if not isinstance(value, NormalizedOrder):
        raise ValueError("broker orders must be normalized read-only order values")
    return value


def normalized_fill(value: NormalizedFill) -> NormalizedFill:
    if not isinstance(value, NormalizedFill):
        raise ValueError("broker fills must be normalized read-only fill values")
    return value
