"""Immutable, broker-independent paper order intentions and exposure planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from enum import StrEnum
import json
import re
from typing import Any, Mapping

from qc2_contracts.runtime import (
    ContractValidationError,
    assert_transition,
    canonical_content_hash,
    canonical_decimal_text,
    canonical_json_bytes,
    validate_contract,
    verify_content_hash,
)


_INTENT_SCHEMA = "qc2.execution.PaperOrderIntent.v1"
_INTENT_VERSION = "1.0"
_UUID7_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_HASH_ENVELOPE_FIELDS = {
    "schema_name",
    "schema_version",
    "id",
    "created_at",
    "content_hash",
    "intent_state",
}
_ACTIVE_PRIOR_STATES = {
    "CREATED",
    "VERIFIED",
    "RESERVED",
    "QUEUED_FOR_SUBMISSION",
    "SUBMISSION_STARTED",
    "SUBMISSION_UNKNOWN",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "CANCEL_REQUESTED",
}


class IntentAction(StrEnum):
    OPEN_LONG = "OPEN_LONG"
    REDUCE_LONG = "REDUCE_LONG"
    CLOSE_LONG = "CLOSE_LONG"
    CANCEL_PENDING_ENTRY = "CANCEL_PENDING_ENTRY"
    REPLACE_ORDER = "REPLACE_ORDER"


class IntentState(StrEnum):
    CREATED = "CREATED"
    VERIFIED = "VERIFIED"
    RESERVED = "RESERVED"
    QUEUED_FOR_SUBMISSION = "QUEUED_FOR_SUBMISSION"
    SUBMISSION_STARTED = "SUBMISSION_STARTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    REJECTED = "REJECTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"


@dataclass(frozen=True, slots=True)
class PaperOrderIntent:
    """A frozen intent value; callers receive copies of the decoded contract."""

    _payload_bytes: bytes
    immutable_bytes: bytes
    content_hash: str
    idempotency_key: str
    intent_id: str

    @classmethod
    def _from_payload(cls, payload: dict[str, Any]) -> PaperOrderIntent:
        immutable_terms = {
            key: value for key, value in payload.items() if key not in _HASH_ENVELOPE_FIELDS
        }
        return cls(
            _payload_bytes=canonical_json_bytes(payload),
            immutable_bytes=canonical_json_bytes(immutable_terms),
            content_hash=payload["content_hash"],
            idempotency_key=payload["idempotency_key"],
            intent_id=payload["id"],
        )

    @property
    def payload(self) -> dict[str, Any]:
        """Return a new mutable copy; changing it cannot change this intent."""
        return json.loads(self._payload_bytes)

    def to_bytes(self) -> bytes:
        """Return the canonical full-contract serialization."""
        return self._payload_bytes

    def with_state(self, new_state: IntentState | str) -> PaperOrderIntent:
        payload = self.payload
        state = IntentState(new_state).value
        assert_transition("PaperOrderIntent", payload["intent_state"], state)
        updated = {**payload, "intent_state": state}
        validate_contract("PaperOrderIntent", updated)
        verify_content_hash("PaperOrderIntent", updated)
        result = self._from_payload(updated)
        if result.immutable_bytes != self.immutable_bytes:
            raise ContractValidationError("A lifecycle transition changed immutable intent terms")
        return result


@dataclass(frozen=True, slots=True)
class ReservationEffect:
    """Exact exposure reserved for this intent and any still-live replaced order."""

    reservation_kind: str | None
    reserved_cash: Decimal
    reserved_quantity: Decimal
    worst_case_pending_cash: Decimal
    worst_case_pending_quantity: Decimal
    holds_reservation_for: str | None = None
    release_only_after_definitive_cancel: bool = False


def _as_decimal(value: Decimal | str | int, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an exact finite decimal")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an exact finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _aware_instant(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 UTC instant")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 UTC instant") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return result.astimezone(UTC)


def _validate_source_and_side(payload: Mapping[str, Any]) -> None:
    action = payload["action_kind"]
    source_schema = payload["source_ref"]["target_schema_name"]
    side = payload["side"]
    if action == IntentAction.OPEN_LONG:
        if source_schema != "qc2.models_prediction.Prediction.v1" or side != "BUY":
            raise ValueError("OPEN_LONG must be a BUY sourced from a Prediction")
        if (
            payload["order_type"] != "LIMIT"
            or payload["time_in_force"] != "DAY"
            or payload["session_restriction"] != "REGULAR_SESSION_ONLY"
            or payload["limit_price"] is None
        ):
            raise ValueError("OPEN_LONG requires a price-capped regular-session DAY limit")
    elif action in {IntentAction.REDUCE_LONG, IntentAction.CLOSE_LONG}:
        if source_schema != "qc2.execution.Position.v1" or side != "SELL":
            raise ValueError(f"{action} must be a SELL sourced from a Position")
    elif action in {IntentAction.CANCEL_PENDING_ENTRY, IntentAction.REPLACE_ORDER}:
        if source_schema != _INTENT_SCHEMA:
            raise ValueError(f"{action} must reference a prior PaperOrderIntent")
    else:
        raise ValueError(f"Unsupported paper action: {action}")

    for field in ("limit_price", "stop_price"):
        value = payload[field]
        if value is not None:
            canonical = canonical_decimal_text(value)
            if Decimal(canonical) <= 0:
                raise ValueError(f"{field} must be positive when supplied")
            if canonical != value:
                raise ValueError(f"{field} must use canonical decimal text")


def build_paper_order_intent(
    payload: Mapping[str, Any],
    *,
    expected_account_fingerprint: str,
    now: datetime | None = None,
) -> PaperOrderIntent:
    """Validate and seal an immutable intent against a trusted paper-account scope."""
    if not isinstance(payload, Mapping):
        raise ValueError("PaperOrderIntent must be a mapping")
    normalized = dict(payload)
    if not isinstance(expected_account_fingerprint, str) or not _SHA256_PATTERN.fullmatch(
        expected_account_fingerprint
    ):
        raise ValueError("expected account fingerprint must be a lowercase SHA-256 digest")
    if normalized.get("schema_name") != _INTENT_SCHEMA:
        raise ValueError("Unsupported PaperOrderIntent schema")
    if normalized.get("schema_version") != _INTENT_VERSION:
        raise ValueError("Unsupported PaperOrderIntent version")
    if not _UUID7_PATTERN.fullmatch(str(normalized.get("id", ""))):
        raise ValueError("intent id must be a UUIDv7")
    if normalized.get("paper_account_fingerprint") != expected_account_fingerprint:
        raise ValueError("PaperOrderIntent belongs to a different paper account")
    if normalized.get("account_mode") != "PAPER" or normalized.get("extended_hours") is not False:
        raise ValueError("Only regular-session PAPER intents are supported")

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must include a UTC offset")
    expiry = _aware_instant(normalized.get("expires_at"), "expires_at")
    if expiry <= current_time.astimezone(UTC):
        raise ValueError("PaperOrderIntent is expired")
    if normalized.get("intent_state", "CREATED") != "CREATED":
        raise ValueError("New intents must begin in CREATED state")

    for field in ("limit_price", "stop_price"):
        value = normalized.get(field)
        if value is not None:
            normalized[field] = canonical_decimal_text(value)

    normalized["intent_state"] = "CREATED"
    normalized["content_hash"] = "0" * 64
    validate_contract("PaperOrderIntent", normalized)
    _validate_source_and_side(normalized)
    normalized["content_hash"] = canonical_content_hash("PaperOrderIntent", normalized)
    verify_content_hash("PaperOrderIntent", normalized)
    return PaperOrderIntent._from_payload(normalized)


def whole_shares_floor(
    requested_quantity: Decimal | str | int,
    *,
    upper_bound: Decimal | str | int | None = None,
) -> int:
    """Round down without exceeding either the request or a reconciled share cap."""
    requested = _as_decimal(requested_quantity, "requested quantity")
    if requested <= 0:
        raise ValueError("requested quantity must be positive")
    if upper_bound is not None:
        maximum = _as_decimal(upper_bound, "upper_bound")
        if maximum <= 0:
            raise ValueError("upper_bound must be positive")
        requested = min(requested, maximum)
    rounded = int(requested.to_integral_value(rounding=ROUND_FLOOR))
    if rounded < 1:
        raise ValueError("whole-share rounding produced no executable shares")
    return rounded


def _assert_prior(
    intent: PaperOrderIntent,
    prior_intent: PaperOrderIntent | None,
) -> dict[str, Any]:
    if prior_intent is None:
        raise ValueError(f"{intent.payload['action_kind']} requires its referenced prior intent")
    payload = intent.payload
    prior = prior_intent.payload
    source_ref = payload["source_ref"]
    if source_ref["target_id"] != prior_intent.intent_id:
        raise ValueError("source_ref does not identify the supplied prior intent")
    if source_ref.get("content_hash") != prior_intent.content_hash:
        raise ValueError("source_ref content hash does not match the prior intent")
    if prior["paper_account_fingerprint"] != payload["paper_account_fingerprint"]:
        raise ValueError("Prior intent belongs to a different paper account")
    if prior["instrument_ref"]["target_id"] != payload["instrument_ref"]["target_id"]:
        raise ValueError("Prior intent refers to a different instrument")
    if prior["intent_state"] not in _ACTIVE_PRIOR_STATES:
        raise ValueError("Prior intent is no longer pending")
    return prior


def plan_reservation_effect(
    intent: PaperOrderIntent,
    *,
    cash_cost_buffer: Decimal | str | int = Decimal(0),
    cash_available: Decimal | str | int | None = None,
    position_quantity: Decimal | str | int | None = None,
    prior_intent: PaperOrderIntent | None = None,
    prior_effect: ReservationEffect | None = None,
) -> ReservationEffect:
    """Calculate a nonnegative cash/share reservation without releasing prior exposure."""
    payload = intent.payload
    action = payload["action_kind"]
    quantity = Decimal(payload["quantity_whole_shares"])

    if action == IntentAction.CANCEL_PENDING_ENTRY:
        prior = _assert_prior(intent, prior_intent)
        if prior["action_kind"] != IntentAction.OPEN_LONG or prior["side"] != "BUY":
            raise ValueError("CANCEL_PENDING_ENTRY must reference a pending long entry")
        if prior_effect is None:
            raise ValueError("A cancel must preserve the prior entry reservation until confirmed")
        return ReservationEffect(
            reservation_kind=None,
            reserved_cash=Decimal(0),
            reserved_quantity=Decimal(0),
            worst_case_pending_cash=prior_effect.worst_case_pending_cash,
            worst_case_pending_quantity=prior_effect.worst_case_pending_quantity,
            holds_reservation_for=prior_intent.intent_id,
            release_only_after_definitive_cancel=True,
        )

    prior_cash = Decimal(0)
    prior_quantity = Decimal(0)
    if action == IntentAction.REPLACE_ORDER:
        prior = _assert_prior(intent, prior_intent)
        if prior["side"] != payload["side"]:
            raise ValueError("A replacement must preserve the prior order side")
        if prior_effect is None:
            raise ValueError("A replacement must carry forward the prior pending reservation")
        if (payload["side"] == "BUY") != (prior_effect.reservation_kind == "CASH"):
            raise ValueError("Replacement reservation kind does not match its order side")
        prior_cash = prior_effect.worst_case_pending_cash
        prior_quantity = prior_effect.worst_case_pending_quantity

    if payload["side"] == "BUY":
        if payload["limit_price"] is None:
            raise ValueError("A BUY reservation requires a finite limit price")
        price = _as_decimal(payload["limit_price"], "limit_price")
        buffer = _as_decimal(cash_cost_buffer, "cash_cost_buffer")
        if price <= 0 or buffer < 0:
            raise ValueError("BUY price must be positive and cash cost buffer nonnegative")
        new_cash = quantity * price + buffer
        worst_case_cash = prior_cash + new_cash
        if cash_available is not None and worst_case_cash > _as_decimal(
            cash_available, "cash_available"
        ):
            raise ValueError("Worst-case pending BUY exposure exceeds available cash")
        if prior_quantity:
            raise ValueError("BUY replacement cannot carry a share reservation")
        return ReservationEffect(
            reservation_kind="CASH",
            reserved_cash=new_cash,
            reserved_quantity=Decimal(0),
            worst_case_pending_cash=worst_case_cash,
            worst_case_pending_quantity=Decimal(0),
            holds_reservation_for=prior_intent.intent_id if prior_intent else None,
            release_only_after_definitive_cancel=prior_intent is not None,
        )

    if payload["side"] != "SELL":
        raise ValueError("Paper order side must be BUY or SELL")
    if position_quantity is None:
        raise ValueError("SELL reservation requires a reconciled position quantity")
    owned = _as_decimal(position_quantity, "position_quantity")
    if owned <= 0 or quantity > owned:
        raise ValueError("SELL quantity exceeds reconciled owned shares")
    if action == IntentAction.CLOSE_LONG and quantity != owned:
        raise ValueError("CLOSE_LONG must cover the exact whole-share position")
    new_quantity = quantity
    worst_case_quantity = prior_quantity + new_quantity
    if worst_case_quantity > owned:
        raise ValueError("Replacement SELL would reserve the same shares more than once")
    if cash_available is not None and prior_cash:
        raise ValueError("SELL reservation cannot carry forward cash exposure")
    return ReservationEffect(
        reservation_kind="SHARES",
        reserved_cash=Decimal(0),
        reserved_quantity=new_quantity,
        worst_case_pending_cash=Decimal(0),
        worst_case_pending_quantity=worst_case_quantity,
        holds_reservation_for=prior_intent.intent_id if prior_intent else None,
        release_only_after_definitive_cancel=prior_intent is not None,
    )
