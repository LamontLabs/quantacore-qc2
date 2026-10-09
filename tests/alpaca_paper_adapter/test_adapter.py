from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import pytest

from qc2_alpaca_paper import (
    ACCOUNT_FINGERPRINT_DOMAIN,
    PAPER_API_HOST,
    AccountIdentityMismatch,
    AlpacaPaperAdapter,
    BrokerOrderEventType,
    BrokerOrderState,
    DuplicateClientOrderKey,
    MalformedProviderResponse,
    PaperHostViolation,
    ProviderRequestFailed,
    StdlibPaperTransport,
    TransportResponse,
    UnsupportedOrderTerms,
    WriteGateClosed,
    normalize_fill,
    normalize_order,
    paper_account_fingerprint,
    validate_paper_relative_path,
)
from qc2_execution.authority import SubmissionOutcome, build_normalized_request


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "alpaca_paper_adapter" / "fixtures"
ACCOUNT_ID = "00000000-0000-4000-8000-000000000001"
ACCOUNT_FINGERPRINT = paper_account_fingerprint(ACCOUNT_ID)
INTENT_ID = "018f47e6-c574-7b5a-8e2c-57fc2b824001"
PRIOR_INTENT_ID = "018f47e6-c574-7b5a-8e2c-57fc2b824002"
INSTRUMENT_ID = "018f47e6-c574-7b5a-8e2c-57fc2b824003"
SYMBOL_ASSIGNMENT_ID = "018f47e6-c574-7b5a-8e2c-57fc2b824004"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _response(
    status: int,
    value: Any = None,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> TransportResponse:
    if body is None:
        body = b"" if value is None else json.dumps(value).encode("utf-8")
    return TransportResponse(status, headers or {}, body)


def _account(account_id: str = ACCOUNT_ID) -> dict[str, Any]:
    return {
        "id": account_id,
        "status": "ACTIVE",
        "trading_blocked": False,
        "account_blocked": False,
        "equity": "98765.43",
        "cash": "43210.00",
    }


def _order_request(
    *,
    key: str = "qc2-entry-001",
    action: str = "OPEN_LONG",
    price: str = "12.34",
    quantity: int = 3,
    side: str = "BUY",
) -> dict[str, Any]:
    return {
        "paper_account_fingerprint": ACCOUNT_FINGERPRINT,
        "account_mode": "PAPER",
        "action_kind": action,
        "idempotency_key": key,
        "session_restriction": "REGULAR_SESSION_ONLY",
        "extended_hours": False,
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "stop_price": None,
        "side": side,
        "quantity_whole_shares": quantity,
        "limit_price": price,
        "symbol": "XYZ",
    }


def _normalized_submit_request(
    *,
    key: str = "qc2-entry-001",
    action: str = "OPEN_LONG",
    price: str = "12.34",
    quantity: int = 3,
    side: str = "BUY",
) -> dict[str, Any]:
    intent = {
        "id": INTENT_ID,
        "action_kind": action,
        "paper_account_fingerprint": ACCOUNT_FINGERPRINT,
        "idempotency_key": key,
        "instrument_ref": {"target_id": INSTRUMENT_ID},
        "side": side,
        "quantity_whole_shares": quantity,
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "session_restriction": "REGULAR_SESSION_ONLY",
        "limit_price": price,
        "stop_price": None,
    }
    snapshot = SimpleNamespace(
        broker_symbol="XYZ",
        symbol_assignment_id=SYMBOL_ASSIGNMENT_ID,
    )
    return build_normalized_request(intent, snapshot)


def _normalized_cancel_request(
    *,
    key: str,
    target_client_order_key: str,
    broker_order_id: str | None = None,
) -> dict[str, Any]:
    prior_intent = {
        "id": PRIOR_INTENT_ID,
        "paper_account_fingerprint": ACCOUNT_FINGERPRINT,
        "idempotency_key": target_client_order_key,
    }
    intent = {
        "id": INTENT_ID,
        "action_kind": "CANCEL_PENDING_ENTRY",
        "paper_account_fingerprint": ACCOUNT_FINGERPRINT,
        "idempotency_key": key,
        "source_ref": {"target_id": PRIOR_INTENT_ID},
    }
    snapshot = SimpleNamespace(prior_broker_order_id=broker_order_id)
    return build_normalized_request(
        intent,
        snapshot,
        prior_intent=prior_intent,
    )


class FakeTransport:
    def __init__(self):
        self.responses: dict[tuple[str, str], deque[Any]] = defaultdict(deque)
        self.calls: list[tuple[str, str, Any]] = []

    def add(self, method: str, path: str, *responses: Any) -> None:
        self.responses[(method.upper(), urlsplit(path).path)].extend(responses)

    def request(self, method: str, relative_path: str, *, body=None) -> TransportResponse:
        self.calls.append((method, relative_path, deepcopy(body)))
        route = (method.upper(), urlsplit(relative_path).path)
        if not self.responses[route]:
            raise AssertionError(f"unexpected request: {method} {relative_path}")
        response = self.responses[route].popleft()
        if isinstance(response, BaseException):
            raise response
        return response


def _adapter(fake: FakeTransport, *, sleeper=lambda _: None) -> AlpacaPaperAdapter:
    return AlpacaPaperAdapter(
        api_key="synthetic-test-key",
        secret_key="synthetic-test-secret",
        expected_account_fingerprint=ACCOUNT_FINGERPRINT,
        transport=fake,
        sleeper=sleeper,
    )


def test_fixed_paper_host_and_absolute_live_host_rejection():
    assert PAPER_API_HOST == "paper-api.alpaca.markets"
    assert ACCOUNT_FINGERPRINT_DOMAIN == "qc2.identity_market.paper-account-fingerprint.v1"
    with pytest.raises(PaperHostViolation):
        validate_paper_relative_path("https://api.alpaca.markets/v2/orders")
    with pytest.raises(PaperHostViolation):
        validate_paper_relative_path("//api.alpaca.markets/v2/orders")
    with pytest.raises(PaperHostViolation):
        validate_paper_relative_path("/v2/%2e%2e/orders")


def test_stdlib_transport_blocks_mutations_before_opening_a_connection(monkeypatch):
    def connection_must_not_be_created(*args, **kwargs):
        raise AssertionError("the QC2-047 transport must not open a mutation connection")

    monkeypatch.setattr(
        "qc2_alpaca_paper.transport.http.client.HTTPSConnection",
        connection_must_not_be_created,
    )
    transport = StdlibPaperTransport("synthetic-test-key", "synthetic-test-secret")
    with pytest.raises(WriteGateClosed):
        transport.request("POST", "/v2/orders", body={"symbol": "XYZ"})
    with pytest.raises(WriteGateClosed):
        transport.request("DELETE", "/v2/orders/904837e3-3b76-47ec-b432-046db621571b")
    with pytest.raises(WriteGateClosed):
        transport.request("PATCH", "/v2/orders/904837e3-3b76-47ec-b432-046db621571b")


def test_redirect_is_rejected_without_following_unapproved_location():
    fake = FakeTransport()
    fake.add(
        "GET",
        "/v2/account",
        _response(
            302,
            headers={"Location": "https://api.alpaca.markets/v2/account"},
        ),
    )
    with pytest.raises(PaperHostViolation, match="paper_redirect_blocked"):
        _adapter(fake).get_account_identity()
    assert len(fake.calls) == 1


def test_account_identity_hash_matches_but_never_returns_raw_or_financial_fields():
    fake = FakeTransport()
    fake.add("GET", "/v2/account", _response(200, _account()))
    identity = _adapter(fake).get_account_identity()
    assert identity.account_fingerprint == ACCOUNT_FINGERPRINT
    assert identity.account_status == "ACTIVE"
    assert "98765.43" not in repr(identity)
    assert ACCOUNT_ID not in repr(identity)


def test_wrong_account_fingerprint_fails_closed():
    fake = FakeTransport()
    other_id = "00000000-0000-4000-8000-000000000099"
    fake.add("GET", "/v2/account", _response(200, _account(other_id)))
    with pytest.raises(AccountIdentityMismatch, match="paper_account_fingerprint_mismatch"):
        _adapter(fake).get_account_identity()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("time_in_force", "GTC"),
        ("order_type", "MARKET"),
        ("session_restriction", "EXTENDED_HOURS"),
    ],
)
def test_unsupported_time_in_force_type_and_session_are_rejected(field, value):
    fake = FakeTransport()
    request = _order_request()
    request[field] = value
    with pytest.raises(UnsupportedOrderTerms):
        _adapter(fake)._build_order_payload(request, client_order_key="qc2-entry-001")
    assert fake.calls == []


def test_provider_order_status_normalization_includes_partial_and_nonterminal_cancel():
    accepted = normalize_order(_fixture("order_new.json"))
    partial = normalize_order(_fixture("order_partially_filled.json"))
    pending_cancel = normalize_order(_fixture("order_pending_cancel.json"))
    assert accepted.state == BrokerOrderState.ACKNOWLEDGED
    assert partial.state == BrokerOrderState.PARTIALLY_FILLED
    assert partial.filled_quantity == Decimal("1")
    assert partial.remaining_quantity == Decimal("2")
    assert pending_cancel.state == BrokerOrderState.CANCEL_REQUESTED
    assert pending_cancel.state != BrokerOrderState.CANCELLED


@pytest.mark.parametrize(
    ("provider_status", "normalized"),
    [
        ("done_for_day", BrokerOrderState.SUBMISSION_UNKNOWN),
        ("pending_replace", BrokerOrderState.SUBMISSION_UNKNOWN),
        ("calculated", BrokerOrderState.SUBMISSION_UNKNOWN),
        ("filled", BrokerOrderState.FILLED),
        ("canceled", BrokerOrderState.CANCELLED),
    ],
)
def test_documented_provider_statuses_map_without_false_terminal_success(provider_status, normalized):
    value = _fixture("order_new.json")
    value["status"] = provider_status
    assert normalize_order(value).state == normalized


def test_unknown_or_malformed_order_event_is_rejected():
    value = _fixture("order_new.json")
    value["status"] = "new_vendor_state"
    with pytest.raises(MalformedProviderResponse, match="order_status_unsupported"):
        normalize_order(value)

    value = _fixture("order_new.json")
    value["filled_qty"] = "4"
    with pytest.raises(MalformedProviderResponse, match="order_quantity_outside_policy"):
        normalize_order(value)


def test_partial_fill_activity_normalizes_exact_quantities_and_cursor():
    partial = normalize_fill(_fixture("activity_partial_fill.json"))
    full = normalize_fill(_fixture("activity_fill.json"))
    assert partial.event_type == BrokerOrderEventType.PARTIAL_FILL
    assert partial.quantity == Decimal("1")
    assert partial.cumulative_quantity == Decimal("1")
    assert partial.remaining_quantity == Decimal("2")
    assert full.event_type == BrokerOrderEventType.FILL
    assert full.quantity == Decimal("2")
    assert full.cumulative_quantity == Decimal("3")
    assert full.remaining_quantity == Decimal("0")
    assert "::" in partial.provider_activity_id


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("activity_type", "DIV", "activity_type_unsupported"),
        ("type", "void", "activity_type_unsupported"),
        ("qty", "NaN", "activity_quantity_invalid"),
        ("leaves_qty", "-1", "activity_quantities_inconsistent"),
    ],
)
def test_malformed_or_unsupported_activity_is_rejected(field, value, reason):
    activity = _fixture("activity_partial_fill.json")
    activity[field] = value
    with pytest.raises(MalformedProviderResponse, match=reason):
        normalize_fill(activity)


def test_submit_uses_paper_only_limit_day_request_and_returns_normalized_order():
    fake = FakeTransport()
    fake.add("GET", "/v2/account", _response(200, _account()))
    fake.add("GET", "/v2/orders:by_client_order_id", _response(404, {"code": 40410000}))
    fake.add("POST", "/v2/orders", _response(201, _fixture("order_new.json")))
    result = _adapter(fake).submit_order(
        _normalized_submit_request(),
        client_order_key="qc2-entry-001",
    )
    assert result.outcome == SubmissionOutcome.ACKNOWLEDGED
    assert result.broker_order_id == "904837e3-3b76-47ec-b432-046db621571b"
    assert result.order_state == BrokerOrderState.ACKNOWLEDGED.value
    post = next(call for call in fake.calls if call[0] == "POST")
    assert post[2] == {
        "symbol": "XYZ",
        "qty": "3",
        "side": "buy",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": "12.34",
        "extended_hours": False,
        "order_class": "simple",
        "client_order_id": "qc2-entry-001",
    }


def test_duplicate_client_order_key_does_not_submit_twice_or_change_terms():
    fake = FakeTransport()
    fake.add("GET", "/v2/account", _response(200, _account()))
    fake.add("GET", "/v2/orders:by_client_order_id", _response(404, {"code": 40410000}))
    fake.add("POST", "/v2/orders", _response(201, _fixture("order_new.json")))
    adapter = _adapter(fake)
    first = adapter.submit_order(
        _normalized_submit_request(),
        client_order_key="qc2-entry-001",
    )
    second = adapter.submit_order(
        _normalized_submit_request(),
        client_order_key="qc2-entry-001",
    )
    assert first == second
    assert sum(call[0] == "POST" for call in fake.calls) == 1
    with pytest.raises(DuplicateClientOrderKey):
        adapter.submit_order(
            _normalized_submit_request(price="12.35"),
            client_order_key="qc2-entry-001",
        )


def test_delayed_visibility_after_ambiguous_submit_never_resubmits():
    fake = FakeTransport()
    fake.add("GET", "/v2/account", _response(200, _account()))
    fake.add(
        "GET",
        "/v2/orders:by_client_order_id",
        _response(404, {"code": 40410000}),
        _response(404, {"code": 40410000}),
        _response(200, _fixture("order_new.json")),
    )
    fake.add("POST", "/v2/orders", ConnectionError("synthetic timeout"))
    adapter = _adapter(fake)

    normalized_request = _normalized_submit_request()
    first = adapter.submit_order(normalized_request, client_order_key="qc2-entry-001")
    second = adapter.submit_order(normalized_request, client_order_key="qc2-entry-001")
    third = adapter.submit_order(normalized_request, client_order_key="qc2-entry-001")
    assert first.outcome == SubmissionOutcome.SUBMISSION_UNKNOWN
    assert second.outcome == SubmissionOutcome.SUBMISSION_UNKNOWN
    assert third.outcome == SubmissionOutcome.ACKNOWLEDGED
    assert sum(call[0] == "POST" for call in fake.calls) == 1


def test_read_get_retries_are_bounded_and_raw_errors_are_redacted():
    fake = FakeTransport()
    fake.add(
        "GET",
        "/v2/account",
        _response(503, body=b'{"message":"synthetic-test-secret"}'),
        _response(200, _account()),
    )
    sleeps: list[float] = []
    identity = _adapter(fake, sleeper=sleeps.append).get_account_identity()
    assert identity.account_fingerprint == ACCOUNT_FINGERPRINT
    assert len(fake.calls) == 2
    assert any(0 < delay <= 0.05 for delay in sleeps)

    failed = FakeTransport()
    failed.add(
        "GET",
        "/v2/account",
        _response(500, body=b'{"message":"synthetic-test-secret"}'),
        _response(500, body=b'{"message":"synthetic-test-secret"}'),
    )
    adapter = _adapter(failed)
    with pytest.raises(ProviderRequestFailed) as error:
        adapter.get_account_identity()
    assert "synthetic-test-secret" not in str(error.value)
    assert "synthetic-test-key" not in repr(adapter)
    assert "synthetic-test-secret" not in repr(adapter)


def test_read_activity_page_uses_documented_cursor_and_descending_direction():
    fake = FakeTransport()
    activity = _fixture("activity_partial_fill.json")
    fake.add("GET", "/v2/account", _response(200, _account()))
    fake.add("GET", "/v2/account/activities", _response(200, [activity]))
    page = _adapter(fake).read_activities(limit=1)
    assert len(page.activities) == 1
    assert page.next_page_token == activity["id"]
    assert page.direction == "desc"
    assert "direction=desc" in fake.calls[-1][1]
    assert "page_size=1" in fake.calls[-1][1]
    assert "activity_types=FILL" in fake.calls[-1][1]


def test_nonterminal_cancel_response_is_not_reported_as_cancelled():
    fake = FakeTransport()
    pending = _fixture("order_pending_cancel.json")
    fake.add("GET", "/v2/account", _response(200, _account()))
    fake.add("GET", "/v2/orders/6329fba2-478c-40c0-997e-10d6f68d35a8", _response(200, pending))
    request = _normalized_cancel_request(
        key="qc2-cancel-001",
        target_client_order_key="qc2-entry-prior",
        broker_order_id=pending["id"],
    )
    result = _adapter(fake).cancel_order(request, client_order_key="qc2-cancel-001")
    assert result.outcome == SubmissionOutcome.ACKNOWLEDGED
    assert result.order_state == BrokerOrderState.CANCEL_REQUESTED.value
    assert all(call[0] != "DELETE" for call in fake.calls)


def test_cancel_204_means_request_acknowledged_not_terminal_cancelled():
    fake = FakeTransport()
    order = _fixture("order_new.json")
    fake.add("GET", "/v2/account", _response(200, _account()))
    fake.add("GET", "/v2/orders:by_client_order_id", _response(200, order))
    fake.add("DELETE", f"/v2/orders/{order['id']}", _response(204))
    request = _normalized_cancel_request(
        key="qc2-cancel-002",
        target_client_order_key=order["client_order_id"],
    )
    result = _adapter(fake).cancel_order(request, client_order_key="qc2-cancel-002")
    assert result.outcome == SubmissionOutcome.ACKNOWLEDGED
    assert result.order_state == BrokerOrderState.CANCEL_REQUESTED.value
    assert result.order_state != BrokerOrderState.CANCELLED.value


def test_replace_builds_only_supported_fields_and_normalizes_response():
    fake = FakeTransport()
    old_order = _fixture("order_new.json")
    replacement = deepcopy(old_order)
    replacement.update(
        {
            "id": "8d7a4906-8092-4b9d-9bcf-0eadc4d3876f",
            "client_order_id": "qc2-replace-001",
            "qty": "4",
            "limit_price": "12.35",
        }
    )
    fake.add("GET", "/v2/account", _response(200, _account()))
    fake.add("GET", "/v2/orders:by_client_order_id", _response(404, {"code": 40410000}))
    fake.add("GET", f"/v2/orders/{old_order['id']}", _response(200, old_order))
    fake.add("PATCH", f"/v2/orders/{old_order['id']}", _response(200, replacement))
    request = {
        **_order_request(key="qc2-replace-001", action="REPLACE_ORDER", price="12.35", quantity=4),
        "target_broker_order_id": old_order["id"],
    }
    result = _adapter(fake).replace_order(
        request,
        client_order_key="qc2-replace-001",
    )
    assert result.outcome == SubmissionOutcome.ACKNOWLEDGED
    assert result.broker_order_id == replacement["id"]
    patch_body = next(call[2] for call in fake.calls if call[0] == "PATCH")
    assert patch_body == {
        "client_order_id": "qc2-replace-001",
        "qty": "4",
        "limit_price": "12.35",
    }


def test_replace_rejects_accepted_provider_state_before_patch():
    fake = FakeTransport()
    accepted_order = _fixture("order_new.json")
    accepted_order["status"] = "accepted"
    fake.add("GET", "/v2/account", _response(200, _account()))
    fake.add("GET", "/v2/orders:by_client_order_id", _response(404, {"code": 40410000}))
    fake.add("GET", f"/v2/orders/{accepted_order['id']}", _response(200, accepted_order))
    request = {
        **_order_request(
            key="qc2-replace-accepted",
            action="REPLACE_ORDER",
            price="12.35",
            quantity=4,
        ),
        "target_broker_order_id": accepted_order["id"],
    }

    result = _adapter(fake).replace_order(
        request,
        client_order_key="qc2-replace-accepted",
    )

    assert result.outcome == SubmissionOutcome.REJECTED
    assert all(call[0] != "PATCH" for call in fake.calls)
