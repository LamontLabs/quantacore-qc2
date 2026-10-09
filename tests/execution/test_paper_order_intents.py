from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

import pytest

from qc2_execution import (
    IntentAction,
    IntentState,
    PaperOrderIntent,
    build_paper_order_intent,
    plan_reservation_effect,
    whole_shares_floor,
)


NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
ACCOUNT = "a" * 64
INSTRUMENT_ID = "018f0000-0000-7000-8000-000000000001"


def _ref(schema_name: str, target_id: str, *, content_hash: str | None = None):
    result = {"target_schema_name": schema_name, "target_id": target_id}
    if content_hash is not None:
        result["content_hash"] = content_hash
    return result


def _intent_id(key: str) -> str:
    suffix = sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"018f0000-0000-7000-8000-{suffix}"


def _intent(
    valid_intent_fixture: dict[str, Any],
    *,
    action: IntentAction = IntentAction.OPEN_LONG,
    side: str | None = None,
    intent_id: str | None = None,
    source: dict[str, Any] | None = None,
    key: str = "intent-test",
    quantity: int = 2,
    limit_price: str | None = "10.00",
    expiry: str = "2026-10-08T12:30:00Z",
    account: str = ACCOUNT,
    state: str = "CREATED",
) -> PaperOrderIntent:
    payload = deepcopy(valid_intent_fixture)
    payload.update(
        {
            "id": intent_id or _intent_id(key),
            "created_at": "2026-10-08T11:55:00Z",
            "paper_account_fingerprint": account,
            "action_kind": action.value,
            "side": side or ("BUY" if action == IntentAction.OPEN_LONG else "SELL"),
            "quantity_whole_shares": quantity,
            "limit_price": limit_price,
            "expires_at": expiry,
            "idempotency_key": key,
            "intent_state": state,
            "reservation_ref": None,
        }
    )
    if source is not None:
        payload["source_ref"] = source
    elif action == IntentAction.OPEN_LONG:
        payload["source_ref"] = _ref(
            "qc2.models_prediction.Prediction.v1",
            "018f0000-0000-7000-8000-000000000011",
            content_hash="a" * 64,
        )
    elif action in {IntentAction.REDUCE_LONG, IntentAction.CLOSE_LONG}:
        payload["source_ref"] = _ref("qc2.execution.Position.v1", INSTRUMENT_ID)
    payload["instrument_ref"] = _ref("qc2.identity_market.Instrument.v1", INSTRUMENT_ID)
    payload["content_hash"] = "0" * 64
    return build_paper_order_intent(
        payload,
        expected_account_fingerprint=account,
        now=NOW,
    )


def _replacement(
    valid_intent_fixture: dict[str, Any],
    prior: PaperOrderIntent,
    *,
    key: str,
    quantity: int,
    limit_price: str | None,
    side: str,
) -> PaperOrderIntent:
    return _intent(
        valid_intent_fixture,
        action=IntentAction.REPLACE_ORDER,
        side=side,
        source=_ref(
            "qc2.execution.PaperOrderIntent.v1",
            prior.intent_id,
            content_hash=prior.content_hash,
        ),
        key=key,
        quantity=quantity,
        limit_price=limit_price,
    )


def test_intent_hash_binds_terms_but_not_state(valid_intent_fixture):
    first = _intent(valid_intent_fixture, key="stable-entry", quantity=2)
    changed = _intent(valid_intent_fixture, key="stable-entry", quantity=3)

    assert first.content_hash != changed.content_hash
    assert first.immutable_bytes != changed.immutable_bytes

    verified = first.with_state(IntentState.VERIFIED)
    reserved = verified.with_state(IntentState.RESERVED)
    assert first.payload["intent_state"] == "CREATED"
    assert verified.payload["intent_state"] == "VERIFIED"
    assert reserved.payload["intent_state"] == "RESERVED"
    assert first.content_hash == verified.content_hash == reserved.content_hash
    assert first.immutable_bytes == verified.immutable_bytes == reserved.immutable_bytes

    exposed_copy = first.payload
    exposed_copy["side"] = "SELL"
    assert first.payload["side"] == "BUY"


def test_expired_or_wrong_account_intent_is_rejected(valid_intent_fixture):
    with pytest.raises(ValueError, match="expired"):
        _intent(valid_intent_fixture, expiry="2026-10-08T11:59:59Z")

    payload = deepcopy(valid_intent_fixture)
    payload.update(
        {
            "id": "018f0000-0000-7000-8000-000000000002",
            "created_at": "2026-10-08T11:55:00Z",
            "expires_at": "2026-10-08T12:30:00Z",
            "paper_account_fingerprint": "b" * 64,
            "limit_price": "10",
            "idempotency_key": "wrong-account",
            "content_hash": "0" * 64,
        }
    )
    with pytest.raises(ValueError, match="different paper account"):
        build_paper_order_intent(
            payload,
            expected_account_fingerprint=ACCOUNT,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("requested", "upper_bound", "expected"),
    [
        ("5.99", None, 5),
        ("5.99", "4.99", 4),
        ("1.000", "1.999", 1),
    ],
)
def test_whole_share_rounding_never_exceeds_request_or_cap(requested, upper_bound, expected):
    assert whole_shares_floor(requested, upper_bound=upper_bound) == expected


@pytest.mark.parametrize("requested", ["0", "-1", "0.99", "NaN", "Infinity"])
def test_whole_share_rounding_rejects_non_executable_quantity(requested):
    with pytest.raises(ValueError):
        whole_shares_floor(requested)


def test_entry_reserves_exact_limit_notional_plus_explicit_buffer(valid_intent_fixture):
    intent = _intent(valid_intent_fixture, quantity=3, limit_price="10")

    effect = plan_reservation_effect(
        intent,
        cash_cost_buffer=Decimal("0.15"),
        cash_available=Decimal("40"),
    )

    assert effect.reservation_kind == "CASH"
    assert effect.reserved_cash == Decimal("30.15")
    assert effect.worst_case_pending_cash == Decimal("30.15")
    assert effect.reserved_quantity == 0


def test_reduction_and_close_cannot_sell_more_than_owned(valid_intent_fixture):
    reduction = _intent(
        valid_intent_fixture,
        action=IntentAction.REDUCE_LONG,
        key="reduce",
        quantity=4,
        limit_price=None,
    )
    assert plan_reservation_effect(
        reduction,
        position_quantity=Decimal("4.5"),
    ).reserved_quantity == Decimal(4)

    excessive = _intent(
        valid_intent_fixture,
        action=IntentAction.REDUCE_LONG,
        key="excessive",
        quantity=5,
        limit_price=None,
    )
    with pytest.raises(ValueError, match="exceeds"):
        plan_reservation_effect(excessive, position_quantity=Decimal("4.5"))

    fractional_close = _intent(
        valid_intent_fixture,
        action=IntentAction.CLOSE_LONG,
        key="fractional-close",
        quantity=4,
        limit_price=None,
    )
    with pytest.raises(ValueError, match="exact whole-share"):
        plan_reservation_effect(fractional_close, position_quantity=Decimal("4.5"))


def test_cancel_keeps_prior_entry_exposure_until_confirmed(valid_intent_fixture):
    prior = _intent(valid_intent_fixture, key="prior-entry", quantity=2, limit_price="10")
    prior_effect = plan_reservation_effect(prior)
    cancel = _intent(
        valid_intent_fixture,
        action=IntentAction.CANCEL_PENDING_ENTRY,
        side="BUY",
        source=_ref(
            "qc2.execution.PaperOrderIntent.v1",
            prior.intent_id,
            content_hash=prior.content_hash,
        ),
        key="cancel-entry",
        quantity=prior.payload["quantity_whole_shares"],
        limit_price=prior.payload["limit_price"],
    )

    effect = plan_reservation_effect(
        cancel,
        prior_intent=prior,
        prior_effect=prior_effect,
    )

    assert effect.reservation_kind is None
    assert effect.reserved_cash == 0
    assert effect.worst_case_pending_cash == Decimal("20")
    assert effect.holds_reservation_for == prior.intent_id
    assert effect.release_only_after_definitive_cancel


def test_replacement_reserves_new_order_without_releasing_prior(valid_intent_fixture):
    prior = _intent(valid_intent_fixture, key="old-entry", quantity=2, limit_price="10")
    prior_effect = plan_reservation_effect(prior)
    replacement = _replacement(
        valid_intent_fixture,
        prior,
        key="new-entry-revision",
        quantity=3,
        limit_price="11",
        side="BUY",
    )

    effect = plan_reservation_effect(
        replacement,
        prior_intent=prior,
        prior_effect=prior_effect,
        cash_cost_buffer=Decimal("1"),
        cash_available=Decimal("60"),
    )

    assert effect.reserved_cash == Decimal("34")
    assert effect.worst_case_pending_cash == Decimal("54")
    assert effect.holds_reservation_for == prior.intent_id
    assert effect.release_only_after_definitive_cancel


def test_replacement_sell_cannot_double_reserve_the_same_shares(valid_intent_fixture):
    prior = _intent(
        valid_intent_fixture,
        action=IntentAction.REDUCE_LONG,
        key="old-exit",
        quantity=2,
        limit_price=None,
    )
    prior_effect = plan_reservation_effect(prior, position_quantity=Decimal("4"))
    replacement = _replacement(
        valid_intent_fixture,
        prior,
        key="new-exit-revision",
        quantity=3,
        limit_price=None,
        side="SELL",
    )

    with pytest.raises(ValueError, match="more than once"):
        plan_reservation_effect(
            replacement,
            prior_intent=prior,
            prior_effect=prior_effect,
            position_quantity=Decimal("4"),
        )


def test_wrong_source_action_is_rejected(valid_intent_fixture):
    payload = deepcopy(valid_intent_fixture)
    payload.update(
        {
            "id": "018f0000-0000-7000-8000-000000000003",
            "created_at": "2026-10-08T11:55:00Z",
            "expires_at": "2026-10-08T12:30:00Z",
            "idempotency_key": "bad-source",
            "limit_price": "10",
            "source_ref": _ref("qc2.execution.Position.v1", INSTRUMENT_ID),
            "content_hash": "0" * 64,
        }
    )

    with pytest.raises(ValueError):
        build_paper_order_intent(
            payload,
            expected_account_fingerprint=ACCOUNT,
            now=NOW,
        )
