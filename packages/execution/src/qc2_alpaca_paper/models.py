"""Contract-limited, secret-safe Alpaca paper adapter values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re
import uuid
from typing import Any, Mapping

from qc2_contracts.runtime import domain_separated_sha256


ACCOUNT_FINGERPRINT_DOMAIN = "qc2.identity_market.paper-account-fingerprint.v1"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_CLIENT_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z")
_SYMBOL_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,14}\Z")


class AlpacaPaperError(RuntimeError):
    """Base class for sanitized adapter failures."""


class CredentialsMissing(AlpacaPaperError):
    """Required Alpaca paper credentials are not configured."""


class PaperHostViolation(AlpacaPaperError):
    """A request or redirect would leave the fixed paper API host."""


class AccountIdentityMismatch(AlpacaPaperError):
    """The authenticated account does not match the pinned paper account."""


class AccountNotTradeable(AlpacaPaperError):
    """The authenticated account is blocked or inactive."""


class UnsupportedOrderTerms(AlpacaPaperError):
    """An intent falls outside the pinned simple regular-session order policy."""


class DuplicateClientOrderKey(AlpacaPaperError):
    """An idempotency key was reused for different immutable order terms."""


class MalformedProviderResponse(AlpacaPaperError):
    """A provider response is incomplete, malformed, or outside the contract."""


class ProviderRequestFailed(AlpacaPaperError):
    """A provider request failed; raw response content is deliberately omitted."""

    def __init__(self, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(
            "paper_provider_request_failed"
            if status_code is None
            else f"paper_provider_request_failed:{status_code}"
        )


class ReadRateBudgetExceeded(AlpacaPaperError):
    """A read request would exceed the adapter's bounded rate wait."""


class WriteGateClosed(AlpacaPaperError):
    """Broker mutations are disabled until the QC2-086 gate is accepted."""


class BrokerOrderState(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    REJECTED = "REJECTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"


class BrokerOrderEventType(StrEnum):
    PARTIAL_FILL = "PARTIAL_FILL"
    FILL = "FILL"


@dataclass(frozen=True, slots=True)
class AccountIdentity:
    account_fingerprint: str
    account_status: str
    trading_blocked: bool
    account_blocked: bool


@dataclass(frozen=True, slots=True)
class NormalizedOrder:
    broker_order_id: str
    client_order_key: str
    state: BrokerOrderState
    provider_status: str
    symbol: str
    side: str
    quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    order_type: str
    time_in_force: str
    limit_price: Decimal
    submitted_at: datetime
    updated_at: datetime
    filled_average_price: Decimal | None


@dataclass(frozen=True, slots=True)
class NormalizedFill:
    provider_activity_id: str
    broker_order_id: str
    event_type: BrokerOrderEventType
    symbol: str
    side: str
    quantity: Decimal
    cumulative_quantity: Decimal
    remaining_quantity: Decimal
    price: Decimal
    filled_at: datetime


def validate_account_fingerprint(value: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise ValueError("expected paper-account fingerprint must be lowercase SHA-256")
    return value


def paper_account_fingerprint(account_id: str) -> str:
    """Hash the provider account ID without returning or persisting it."""
    if not isinstance(account_id, str):
        raise MalformedProviderResponse("paper_account_id_missing")
    try:
        canonical_id = str(uuid.UUID(account_id))
    except (ValueError, AttributeError) as exc:
        raise MalformedProviderResponse("paper_account_id_invalid") from exc
    return domain_separated_sha256(
        ACCOUNT_FINGERPRINT_DOMAIN,
        canonical_id.encode("ascii"),
    )


def require_client_order_key(value: str) -> str:
    if not isinstance(value, str) or not _CLIENT_KEY_PATTERN.fullmatch(value):
        raise UnsupportedOrderTerms("client_order_key_invalid")
    return value


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise MalformedProviderResponse(f"{field}_invalid")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MalformedProviderResponse(f"{field}_invalid") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise MalformedProviderResponse(f"{field}_invalid")
    return result


def _aware_instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise MalformedProviderResponse(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise MalformedProviderResponse(f"{field}_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MalformedProviderResponse(f"{field}_missing_offset")
    return parsed.astimezone(UTC)


_ACKNOWLEDGED_STATUSES = {
    "new",
    "accepted",
    "pending_new",
    "accepted_for_bidding",
}
_UNKNOWN_STATUSES = {
    "done_for_day",
    "pending_replace",
    "stopped",
    "suspended",
    "calculated",
}
_STATUS_MAP = {
    **{status: BrokerOrderState.ACKNOWLEDGED for status in _ACKNOWLEDGED_STATUSES},
    "partially_filled": BrokerOrderState.PARTIALLY_FILLED,
    "filled": BrokerOrderState.FILLED,
    "pending_cancel": BrokerOrderState.CANCEL_REQUESTED,
    "canceled": BrokerOrderState.CANCELLED,
    "expired": BrokerOrderState.EXPIRED,
    "replaced": BrokerOrderState.REPLACED,
    "rejected": BrokerOrderState.REJECTED,
    **{status: BrokerOrderState.SUBMISSION_UNKNOWN for status in _UNKNOWN_STATUSES},
}


def normalize_order(value: Mapping[str, Any]) -> NormalizedOrder:
    """Normalize the documented simple-order response fields; reject broadened terms."""
    if not isinstance(value, Mapping):
        raise MalformedProviderResponse("order_response_not_object")
    try:
        order_id = str(uuid.UUID(str(value["id"])))
    except (KeyError, ValueError, AttributeError) as exc:
        raise MalformedProviderResponse("order_id_invalid") from exc
    client_key = require_client_order_key(value.get("client_order_id"))
    status = value.get("status")
    if not isinstance(status, str) or status not in _STATUS_MAP:
        raise MalformedProviderResponse("order_status_unsupported")
    state = _STATUS_MAP[status]

    symbol = value.get("symbol")
    if not isinstance(symbol, str) or not _SYMBOL_PATTERN.fullmatch(symbol):
        raise MalformedProviderResponse("order_symbol_invalid")
    side = value.get("side")
    if side not in {"buy", "sell"}:
        raise MalformedProviderResponse("order_side_unsupported")
    if (
        value.get("type") != "limit"
        or value.get("time_in_force") != "day"
        or value.get("order_class") not in {"", "simple"}
        or value.get("extended_hours") is not False
        or value.get("stop_price") is not None
    ):
        raise MalformedProviderResponse("order_terms_outside_policy")

    quantity = _decimal(value.get("qty"), "order_quantity", positive=True)
    filled = _decimal(value.get("filled_qty"), "order_filled_quantity")
    limit_price = _decimal(value.get("limit_price"), "order_limit_price", positive=True)
    if (
        quantity != quantity.to_integral_value()
        or filled != filled.to_integral_value()
        or filled < 0
        or filled > quantity
    ):
        raise MalformedProviderResponse("order_quantity_outside_policy")
    average_value = value.get("filled_avg_price")
    average = (
        _decimal(average_value, "order_filled_average_price", positive=True)
        if average_value not in (None, "")
        else None
    )
    if filled > 0 and average is None:
        raise MalformedProviderResponse("order_fill_price_missing")

    submitted = _aware_instant(value.get("submitted_at"), "order_submitted_at")
    updated = _aware_instant(value.get("updated_at"), "order_updated_at")
    if updated < submitted:
        raise MalformedProviderResponse("order_timestamp_order_invalid")

    return NormalizedOrder(
        broker_order_id=order_id,
        client_order_key=client_key,
        state=state,
        provider_status=status,
        symbol=symbol,
        side=side.upper(),
        quantity=quantity,
        filled_quantity=filled,
        remaining_quantity=quantity - filled,
        order_type="LIMIT",
        time_in_force="DAY",
        limit_price=limit_price,
        submitted_at=submitted,
        updated_at=updated,
        filled_average_price=average,
    )


def normalize_fill(value: Mapping[str, Any]) -> NormalizedFill:
    """Normalize an Alpaca FILL activity, including partial-fill activity records."""
    if not isinstance(value, Mapping):
        raise MalformedProviderResponse("activity_response_not_object")
    activity_type = value.get("activity_type")
    activity_kind = value.get("type")
    if activity_type != "FILL" or activity_kind not in {"fill", "partial_fill"}:
        raise MalformedProviderResponse("activity_type_unsupported")

    activity_id = value.get("id")
    if not isinstance(activity_id, str) or not activity_id or len(activity_id) > 128:
        raise MalformedProviderResponse("activity_id_invalid")
    try:
        order_id = str(uuid.UUID(str(value["order_id"])))
    except (KeyError, ValueError, AttributeError) as exc:
        raise MalformedProviderResponse("activity_order_id_invalid") from exc
    symbol = value.get("symbol")
    if not isinstance(symbol, str) or not _SYMBOL_PATTERN.fullmatch(symbol):
        raise MalformedProviderResponse("activity_symbol_invalid")
    side = value.get("side")
    if side not in {"buy", "sell"}:
        raise MalformedProviderResponse("activity_side_invalid")
    quantity = _decimal(value.get("qty"), "activity_quantity", positive=True)
    cumulative = _decimal(value.get("cum_qty"), "activity_cumulative_quantity", positive=True)
    remaining = _decimal(value.get("leaves_qty"), "activity_remaining_quantity")
    price = _decimal(value.get("price"), "activity_price", positive=True)
    if (
        quantity != quantity.to_integral_value()
        or cumulative != cumulative.to_integral_value()
        or remaining != remaining.to_integral_value()
        or cumulative < quantity
        or remaining < 0
        or (activity_kind == "partial_fill" and remaining == 0)
        or (activity_kind == "fill" and remaining != 0)
    ):
        raise MalformedProviderResponse("activity_quantities_inconsistent")

    return NormalizedFill(
        provider_activity_id=activity_id,
        broker_order_id=order_id,
        event_type=(
            BrokerOrderEventType.PARTIAL_FILL
            if activity_kind == "partial_fill"
            else BrokerOrderEventType.FILL
        ),
        symbol=symbol,
        side=side.upper(),
        quantity=quantity,
        cumulative_quantity=cumulative,
        remaining_quantity=remaining,
        price=price,
        filled_at=_aware_instant(value.get("transaction_time"), "activity_transaction_time"),
    )
