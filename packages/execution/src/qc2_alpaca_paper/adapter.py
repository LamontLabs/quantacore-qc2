"""Pinned, paper-only Alpaca order and activity adapter."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import hmac
import json
import os
import re
import threading
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
import uuid

from .fingerprint import (
    InvalidPaperAccountIdentity,
    require_fingerprint_scheme,
    validate_paper_identity_context,
)
from qc2_contracts.runtime import canonical_decimal_text, canonical_json_bytes
from qc2_execution.authority import BrokerResult, SubmissionOutcome

from .identity import observe_account_identity
from .models import (
    ACCOUNT_FINGERPRINT_SCHEME,
    AccountIdentity,
    AccountIdentityMismatch,
    AccountNotTradeable,
    AlpacaPaperError,
    BrokerOrderState,
    CredentialsMissing,
    DuplicateClientOrderKey,
    MalformedProviderResponse,
    NormalizedOrder,
    PaperHostViolation,
    ProviderRequestFailed,
    ReadRateBudgetExceeded,
    UnsupportedOrderTerms,
    WriteGateClosed,
    normalize_fill,
    normalize_order,
    require_client_order_key,
    validate_account_fingerprint,
)
from .fixtures import ActivityPage
from .transport import (
    PAPER_API_BASE_URL,
    PaperTransport,
    TransportResponse,
    validate_paper_relative_path,
)


_SYMBOL_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,14}\Z")
_NORMALIZED_REQUEST_SCHEMA = "qc2.execution.normalized_mutation_request.v1"
_READ_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_READ_ATTEMPTS = 2
_MAX_RETRY_DELAY_SECONDS = 0.25
_MIN_REQUEST_INTERVAL_SECONDS = 0.20
_MAX_RATE_WAIT_SECONDS = 2.0


@dataclass(slots=True)
class _MutationAttempt:
    request_fingerprint: str
    result: BrokerResult | None = None
    transmitted: bool = False


class AlpacaPaperAdapter:
    """Paper-only Alpaca client; actual broker writes are gated until QC2-086."""

    name = "ALPACA_PAPER"
    is_paper = True
    paper_api_base_url = PAPER_API_BASE_URL

    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        expected_account_fingerprint: str,
        expected_fingerprint_scheme: str = ACCOUNT_FINGERPRINT_SCHEME,
        transport: PaperTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.expected_account_fingerprint = validate_account_fingerprint(
            expected_account_fingerprint
        )
        try:
            self.expected_fingerprint_scheme = require_fingerprint_scheme(
                expected_fingerprint_scheme
            )
        except InvalidPaperAccountIdentity:
            raise UnsupportedOrderTerms("paper_fingerprint_scheme_unsupported") from None
        if not isinstance(api_key, str) or not api_key:
            raise CredentialsMissing("alpaca_api_key_missing")
        if not isinstance(secret_key, str) or not secret_key:
            raise CredentialsMissing("alpaca_api_secret_missing")
        if transport is None:
            from .transport import StdlibPaperTransport

            transport = StdlibPaperTransport(api_key, secret_key)
        try:
            validate_paper_identity_context(origin=getattr(transport, "origin", None))
        except InvalidPaperAccountIdentity:
            raise PaperHostViolation("paper_transport_origin_not_allowed") from None
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper
        self._next_request_at = 0.0
        self._rate_lock = threading.Lock()
        self._attempt_lock = threading.Lock()
        self._mutation_attempts: dict[tuple[str, str], _MutationAttempt] = {}

    def __repr__(self) -> str:
        return (
            "AlpacaPaperAdapter(host='paper-api.alpaca.markets', "
            f"fingerprint_scheme='{self.expected_fingerprint_scheme}', "
            f"account_fingerprint='{self.expected_account_fingerprint}', "
            "mutations_enabled=False)"
        )

    @classmethod
    def from_environment(
        cls,
        *,
        expected_account_fingerprint: str,
        expected_fingerprint_scheme: str = ACCOUNT_FINGERPRINT_SCHEME,
        transport: PaperTransport | None = None,
    ) -> AlpacaPaperAdapter:
        api_key = os.environ.get("APCA_API_KEY_ID")
        secret_key = os.environ.get("APCA_API_SECRET_KEY")
        if not api_key or not secret_key:
            raise CredentialsMissing("alpaca_paper_credentials_missing")
        return cls(
            api_key=api_key,
            secret_key=secret_key,
            expected_account_fingerprint=expected_account_fingerprint,
            expected_fingerprint_scheme=expected_fingerprint_scheme,
            transport=transport,
        )

    def _acquire_rate_slot(self) -> None:
        with self._rate_lock:
            now = self._clock()
            wait_seconds = max(0.0, self._next_request_at - now)
            if wait_seconds > _MAX_RATE_WAIT_SECONDS:
                raise ReadRateBudgetExceeded("paper_read_rate_budget_exceeded")
            if wait_seconds:
                self._sleeper(wait_seconds)
            self._next_request_at = max(self._next_request_at, self._clock()) + (
                _MIN_REQUEST_INTERVAL_SECONDS
            )

    @staticmethod
    def _retry_delay(response: TransportResponse) -> float | None:
        retry_after = response.header("retry-after")
        if retry_after is None:
            return 0.05 if response.status_code != 429 else None
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            return None
        if delay < 0 or delay > _MAX_RETRY_DELAY_SECONDS:
            return None
        return delay

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
    ) -> TransportResponse:
        try:
            validate_paper_identity_context(
                origin=getattr(self._transport, "origin", None)
            )
        except InvalidPaperAccountIdentity:
            raise PaperHostViolation("paper_transport_origin_not_allowed") from None
        validate_paper_relative_path(path)
        normalized_method = method.upper()
        attempts = _MAX_READ_ATTEMPTS if normalized_method == "GET" else 1
        for attempt in range(attempts):
            self._acquire_rate_slot()
            try:
                response = self._transport.request(normalized_method, path, body=body)
            except WriteGateClosed:
                raise
            except (OSError, TimeoutError):
                if normalized_method == "GET" and attempt + 1 < attempts:
                    self._sleeper(0.05)
                    continue
                raise ConnectionError("paper_transport_failure") from None
            if 300 <= response.status_code < 400:
                # The transport does not follow redirects; in particular it never
                # requests a Location host supplied by the provider.
                raise PaperHostViolation("paper_redirect_blocked")
            if (
                normalized_method == "GET"
                and response.status_code in _READ_RETRY_STATUSES
                and attempt + 1 < attempts
            ):
                delay = self._retry_delay(response)
                if delay is not None:
                    self._sleeper(delay)
                    continue
            return response
        raise ProviderRequestFailed()

    @staticmethod
    def _decode_json(
        response: TransportResponse,
        *,
        accepted_statuses: tuple[int, ...] = (200,),
        allow_not_found: bool = False,
    ) -> Any:
        if allow_not_found and response.status_code == 404:
            return None
        if response.status_code not in accepted_statuses:
            raise ProviderRequestFailed(response.status_code)
        try:
            return json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MalformedProviderResponse("paper_response_json_invalid") from exc

    @staticmethod
    def _require_object(value: Any, *, reason: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise MalformedProviderResponse(reason)
        return value

    def get_account_identity(self) -> AccountIdentity:
        """Perform a read-only GET and return only a hash and tradeability flags."""
        identity = observe_account_identity(self._transport, request=self._request)
        if not hmac.compare_digest(
            identity.fingerprint_scheme,
            self.expected_fingerprint_scheme,
        ):
            raise AccountIdentityMismatch("paper_fingerprint_scheme_mismatch")
        if not hmac.compare_digest(
            identity.account_fingerprint,
            self.expected_account_fingerprint,
        ):
            raise AccountIdentityMismatch("paper_account_fingerprint_mismatch")
        return identity

    def _verify_tradeable_account(self) -> AccountIdentity:
        identity = self.get_account_identity()
        if (
            identity.account_status != "ACTIVE"
            or identity.trading_blocked
            or identity.account_blocked
        ):
            raise AccountNotTradeable("paper_account_not_active_or_blocked")
        return identity

    @staticmethod
    def _order_path(order_id: str) -> str:
        try:
            canonical_id = str(uuid.UUID(order_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise UnsupportedOrderTerms("broker_order_id_invalid") from exc
        return f"/v2/orders/{canonical_id}"

    def _query_order_by_client_key(self, client_order_key: str) -> NormalizedOrder | None:
        key = require_client_order_key(client_order_key)
        path = "/v2/orders:by_client_order_id?" + urlencode({"client_order_id": key})
        response = self._request("GET", path)
        value = self._decode_json(response, allow_not_found=True)
        if value is None:
            return None
        order = normalize_order(self._require_object(value, reason="order_response_invalid"))
        if order.client_order_key != key:
            raise MalformedProviderResponse("client_order_lookup_mismatch")
        return order

    def _query_order_by_id(self, order_id: str) -> NormalizedOrder | None:
        response = self._request("GET", self._order_path(order_id))
        value = self._decode_json(response, allow_not_found=True)
        if value is None:
            return None
        return normalize_order(self._require_object(value, reason="order_response_invalid"))

    def get_order_by_client_order_key(self, client_order_key: str) -> NormalizedOrder | None:
        self._verify_tradeable_account()
        return self._query_order_by_client_key(client_order_key)

    def get_order_by_id(self, broker_order_id: str) -> NormalizedOrder | None:
        self._verify_tradeable_account()
        return self._query_order_by_id(broker_order_id)

    def list_orders(self, *, limit: int = 100) -> tuple[NormalizedOrder, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        self._verify_tradeable_account()
        query = urlencode({"status": "all", "limit": str(limit), "direction": "desc"})
        response = self._request("GET", f"/v2/orders?{query}")
        value = self._decode_json(response)
        if not isinstance(value, list):
            raise MalformedProviderResponse("orders_response_not_array")
        orders = tuple(
            normalize_order(self._require_object(item, reason="order_response_invalid"))
            for item in value
        )
        if len({order.broker_order_id for order in orders}) != len(orders):
            raise MalformedProviderResponse("duplicate_broker_order_id")
        return orders

    def read_activities(
        self,
        *,
        activity_type: str = "FILL",
        limit: int = 100,
        page_token: str | None = None,
    ) -> ActivityPage:
        if activity_type != "FILL":
            raise UnsupportedOrderTerms("only_fill_activities_are_supported")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        query: dict[str, str] = {
            "activity_types": "FILL",
            "page_size": str(limit),
            "direction": "desc",
        }
        if page_token is not None:
            if (
                not isinstance(page_token, str)
                or not page_token
                or len(page_token) > 256
                or any(ord(character) < 32 or ord(character) == 127 for character in page_token)
            ):
                raise ValueError("page_token is invalid")
            query["page_token"] = page_token
        self._verify_tradeable_account()
        response = self._request(
            "GET",
            f"/v2/account/activities?{urlencode(query)}",
        )
        value = self._decode_json(response)
        if not isinstance(value, list):
            raise MalformedProviderResponse("activities_response_not_array")
        activities = tuple(
            normalize_fill(self._require_object(item, reason="activity_response_invalid"))
            for item in value
        )
        return ActivityPage(
            activities=activities,
            next_page_token=(
                activities[-1].provider_activity_id
                if len(activities) == limit
                else None
            ),
        )

    @staticmethod
    def _validate_request_scope(
        request: Mapping[str, Any],
        *,
        expected_fingerprint: str,
        client_order_key: str,
    ) -> None:
        if request.get("paper_account_fingerprint") != expected_fingerprint:
            raise AccountIdentityMismatch("intent_account_fingerprint_mismatch")
        if request.get("account_mode") != "PAPER" or request.get("extended_hours") is not False:
            raise UnsupportedOrderTerms("paper_regular_session_scope_required")
        if request.get("idempotency_key") not in (None, client_order_key):
            raise DuplicateClientOrderKey("intent_client_order_key_mismatch")

    def _normalized_submit_intent(
        self,
        request: Mapping[str, Any],
        *,
        client_order_key: str,
    ) -> dict[str, Any]:
        if (
            not isinstance(request, Mapping)
            or request.get("schema_name") != _NORMALIZED_REQUEST_SCHEMA
        ):
            raise UnsupportedOrderTerms("normalized_submission_request_required")
        if request.get("action") != "SUBMIT":
            raise UnsupportedOrderTerms("normalized_submission_action_required")
        if request.get("account_fingerprint") != self.expected_account_fingerprint:
            raise AccountIdentityMismatch("intent_account_fingerprint_mismatch")
        if request.get("client_order_key") != client_order_key:
            raise DuplicateClientOrderKey("intent_client_order_key_mismatch")
        if request.get("extended_hours") is not False:
            raise UnsupportedOrderTerms("paper_regular_session_scope_required")
        for field in ("intent_id", "instrument_id", "symbol_assignment_id"):
            if not isinstance(request.get(field), str) or not request[field]:
                raise UnsupportedOrderTerms("normalized_submission_identity_missing")

        side = request.get("side")
        if side not in {"BUY", "SELL"}:
            raise UnsupportedOrderTerms("order_side_unsupported")
        return {
            "paper_account_fingerprint": request["account_fingerprint"],
            "account_mode": "PAPER",
            "action_kind": "OPEN_LONG" if side == "BUY" else "REDUCE_LONG",
            "idempotency_key": request["client_order_key"],
            "session_restriction": request.get("session_restriction"),
            "extended_hours": False,
            "order_type": request.get("order_type"),
            "time_in_force": request.get("time_in_force"),
            "stop_price": request.get("stop_price"),
            "side": side,
            "quantity_whole_shares": request.get("quantity_whole_shares"),
            "limit_price": request.get("limit_price"),
            "symbol": request.get("symbol"),
        }

    def _normalized_cancel_intent(
        self,
        request: Mapping[str, Any],
        *,
        client_order_key: str,
    ) -> dict[str, Any]:
        if (
            not isinstance(request, Mapping)
            or request.get("schema_name") != _NORMALIZED_REQUEST_SCHEMA
        ):
            raise UnsupportedOrderTerms("normalized_cancel_request_required")
        if request.get("action") != "CANCEL":
            raise UnsupportedOrderTerms("normalized_cancel_action_required")
        if request.get("account_fingerprint") != self.expected_account_fingerprint:
            raise AccountIdentityMismatch("intent_account_fingerprint_mismatch")
        if request.get("client_order_key") != client_order_key:
            raise DuplicateClientOrderKey("intent_client_order_key_mismatch")
        if not isinstance(request.get("target_intent_id"), str):
            raise UnsupportedOrderTerms("normalized_cancel_target_missing")

        normalized: dict[str, Any] = {
            "paper_account_fingerprint": request["account_fingerprint"],
            "account_mode": "PAPER",
            "action_kind": "CANCEL_PENDING_ENTRY",
            "idempotency_key": request["client_order_key"],
            "extended_hours": False,
        }
        broker_order_id = request.get("broker_order_id")
        if broker_order_id is not None:
            normalized["target_broker_order_id"] = broker_order_id
        else:
            normalized["target_client_order_key"] = request.get(
                "target_client_order_key"
            )
        return normalized

    def _build_order_payload(
        self,
        request: Mapping[str, Any],
        *,
        client_order_key: str,
    ) -> dict[str, str | bool]:
        if not isinstance(request, Mapping):
            raise UnsupportedOrderTerms("order_request_not_mapping")
        key = require_client_order_key(client_order_key)
        self._validate_request_scope(
            request,
            expected_fingerprint=self.expected_account_fingerprint,
            client_order_key=key,
        )
        if (
            request.get("session_restriction") != "REGULAR_SESSION_ONLY"
            or request.get("order_type") != "LIMIT"
            or request.get("time_in_force") != "DAY"
            or request.get("stop_price") is not None
        ):
            raise UnsupportedOrderTerms("only_regular_session_day_limit_supported")
        action = request.get("action_kind")
        if action not in {"OPEN_LONG", "REDUCE_LONG", "CLOSE_LONG", "REPLACE_ORDER"}:
            raise UnsupportedOrderTerms("order_action_unsupported")
        side = request.get("side")
        if (
            (action == "OPEN_LONG" and side != "BUY")
            or (action in {"REDUCE_LONG", "CLOSE_LONG"} and side != "SELL")
            or side not in {"BUY", "SELL"}
        ):
            raise UnsupportedOrderTerms("order_side_action_mismatch")
        symbol = request.get("symbol", request.get("broker_symbol"))
        if not isinstance(symbol, str) or not _SYMBOL_PATTERN.fullmatch(symbol):
            raise UnsupportedOrderTerms("resolved_broker_symbol_required")
        quantity = request.get("quantity_whole_shares")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise UnsupportedOrderTerms("whole_share_quantity_required")
        price_value = request.get("limit_price")
        if price_value is None:
            raise UnsupportedOrderTerms("limit_price_required")
        try:
            limit_price = canonical_decimal_text(price_value)
        except (TypeError, ValueError) as exc:
            raise UnsupportedOrderTerms("canonical_limit_price_required") from exc
        if not isinstance(price_value, str) or Decimal(limit_price) <= 0 or limit_price != price_value:
            raise UnsupportedOrderTerms("positive_canonical_limit_price_required")
        return {
            "symbol": symbol,
            "qty": str(quantity),
            "side": side.lower(),
            "type": "limit",
            "time_in_force": "day",
            "limit_price": limit_price,
            "extended_hours": False,
            "order_class": "simple",
            "client_order_id": key,
        }

    @staticmethod
    def _request_fingerprint(payload: Mapping[str, Any]) -> str:
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    def _reserve_attempt(
        self,
        operation: str,
        client_order_key: str,
        payload: Mapping[str, Any],
    ) -> tuple[_MutationAttempt, bool]:
        key = (operation, client_order_key)
        fingerprint = self._request_fingerprint(payload)
        with self._attempt_lock:
            existing = self._mutation_attempts.get(key)
            if existing is not None:
                if not hmac.compare_digest(existing.request_fingerprint, fingerprint):
                    raise DuplicateClientOrderKey("client_order_key_reused_for_different_request")
                return existing, False
            attempt = _MutationAttempt(request_fingerprint=fingerprint)
            self._mutation_attempts[key] = attempt
            return attempt, True

    def _discard_untransmitted_attempt(
        self,
        operation: str,
        client_order_key: str,
        attempt: _MutationAttempt,
    ) -> None:
        with self._attempt_lock:
            if not attempt.transmitted:
                self._mutation_attempts.pop((operation, client_order_key), None)

    @staticmethod
    def _unknown_result(broker_order_id: str | None = None) -> BrokerResult:
        return BrokerResult(
            outcome=SubmissionOutcome.SUBMISSION_UNKNOWN,
            broker_order_id=broker_order_id,
            order_state=BrokerOrderState.SUBMISSION_UNKNOWN.value,
        )

    @staticmethod
    def _result_for_order(order: NormalizedOrder) -> BrokerResult:
        if order.state == BrokerOrderState.SUBMISSION_UNKNOWN:
            outcome = SubmissionOutcome.SUBMISSION_UNKNOWN
        elif order.state == BrokerOrderState.REJECTED:
            outcome = SubmissionOutcome.REJECTED
        else:
            outcome = SubmissionOutcome.ACKNOWLEDGED
        return BrokerResult(
            outcome=outcome,
            broker_order_id=order.broker_order_id,
            order_state=order.state.value,
        )

    @staticmethod
    def _ensure_order_matches_payload(
        order: NormalizedOrder,
        payload: Mapping[str, Any],
    ) -> None:
        matches = (
            order.client_order_key == payload["client_order_id"]
            and order.symbol == payload["symbol"]
            and order.side.lower() == payload["side"]
            and order.quantity == Decimal(payload["qty"])
            and order.order_type.lower() == payload["type"]
            and order.time_in_force.lower() == payload["time_in_force"]
            and order.limit_price == Decimal(payload["limit_price"])
        )
        if not matches:
            raise DuplicateClientOrderKey("provider_order_terms_conflict_with_client_key")

    def _reconcile_submission(
        self,
        client_order_key: str,
        payload: Mapping[str, Any],
        attempt: _MutationAttempt,
    ) -> BrokerResult:
        try:
            order = self._query_order_by_client_key(client_order_key)
        except (AlpacaPaperError, OSError, TimeoutError):
            return attempt.result or self._unknown_result()
        if order is not None:
            self._ensure_order_matches_payload(order, payload)
            result = self._result_for_order(order)
            attempt.result = result
            return result
        return attempt.result or self._unknown_result()

    def submit_order(
        self,
        request: Mapping[str, Any],
        *,
        client_order_key: str,
    ) -> BrokerResult:
        """Submit once; ambiguous outcomes are looked up, never resubmitted."""
        key = require_client_order_key(client_order_key)
        normalized_request = self._normalized_submit_intent(
            request,
            client_order_key=key,
        )
        payload = self._build_order_payload(normalized_request, client_order_key=key)
        attempt, is_first = self._reserve_attempt("submit", key, payload)
        if not is_first:
            if attempt.result is not None and attempt.result.outcome != SubmissionOutcome.SUBMISSION_UNKNOWN:
                return attempt.result
            return self._reconcile_submission(key, payload, attempt)

        try:
            self._verify_tradeable_account()
            existing = self._query_order_by_client_key(key)
            if existing is not None:
                self._ensure_order_matches_payload(existing, payload)
                attempt.result = self._result_for_order(existing)
                return attempt.result
        except (AlpacaPaperError, OSError, TimeoutError):
            self._discard_untransmitted_attempt("submit", key, attempt)
            raise

        attempt.transmitted = True
        try:
            response = self._request("POST", "/v2/orders", body=payload)
        except WriteGateClosed:
            attempt.transmitted = False
            self._discard_untransmitted_attempt("submit", key, attempt)
            raise
        except (OSError, TimeoutError, PaperHostViolation):
            attempt.result = self._unknown_result()
            return attempt.result

        if response.status_code in {200, 201}:
            try:
                order = normalize_order(
                    self._require_object(
                        self._decode_json(response, accepted_statuses=(200, 201)),
                        reason="order_response_invalid",
                    )
                )
                self._ensure_order_matches_payload(order, payload)
            except (AlpacaPaperError, OSError, TimeoutError):
                attempt.result = self._unknown_result()
                return attempt.result
            attempt.result = self._result_for_order(order)
            return attempt.result

        if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
            attempt.result = self._reconcile_submission(key, payload, attempt)
            return attempt.result
        if 400 <= response.status_code < 500:
            attempt.result = BrokerResult(
                outcome=SubmissionOutcome.REJECTED,
                order_state=BrokerOrderState.REJECTED.value,
            )
            return attempt.result
        attempt.result = self._unknown_result()
        return attempt.result

    @staticmethod
    def _target_order(request: Mapping[str, Any]) -> tuple[str, str]:
        broker_id = request.get("target_broker_order_id")
        client_key = request.get("target_client_order_key")
        if (broker_id is None) == (client_key is None):
            raise UnsupportedOrderTerms("exactly_one_target_order_reference_required")
        if broker_id is not None:
            try:
                return "id", str(uuid.UUID(str(broker_id)))
            except (ValueError, TypeError, AttributeError) as exc:
                raise UnsupportedOrderTerms("target_broker_order_id_invalid") from exc
        return "client", require_client_order_key(client_key)

    def _lookup_target_order(self, kind: str, target: str) -> NormalizedOrder | None:
        if kind == "id":
            return self._query_order_by_id(target)
        return self._query_order_by_client_key(target)

    def cancel_order(
        self,
        request: Mapping[str, Any],
        *,
        client_order_key: str,
    ) -> BrokerResult:
        key = require_client_order_key(client_order_key)
        normalized_request = self._normalized_cancel_intent(
            request,
            client_order_key=key,
        )
        self._validate_request_scope(
            normalized_request,
            expected_fingerprint=self.expected_account_fingerprint,
            client_order_key=key,
        )
        target_kind, target = self._target_order(normalized_request)
        fingerprint_payload = {
            "target_kind": target_kind,
            "target": target,
            "paper_account_fingerprint": self.expected_account_fingerprint,
        }
        attempt, is_first = self._reserve_attempt("cancel", key, fingerprint_payload)
        if not is_first:
            if attempt.result is not None:
                return attempt.result
            order = self._lookup_target_order(target_kind, target)
            if order is None:
                return self._unknown_result()
            if order.state == BrokerOrderState.CANCEL_REQUESTED:
                result = BrokerResult(
                    SubmissionOutcome.ACKNOWLEDGED,
                    order.broker_order_id,
                    BrokerOrderState.CANCEL_REQUESTED.value,
                )
                attempt.result = result
                return result
            return self._unknown_result(order.broker_order_id)

        try:
            self._verify_tradeable_account()
            order = self._lookup_target_order(target_kind, target)
            if order is None:
                attempt.result = self._unknown_result()
                return attempt.result
            if order.state == BrokerOrderState.CANCEL_REQUESTED:
                attempt.result = BrokerResult(
                    SubmissionOutcome.ACKNOWLEDGED,
                    order.broker_order_id,
                    BrokerOrderState.CANCEL_REQUESTED.value,
                )
                return attempt.result
            if order.state not in {
                BrokerOrderState.ACKNOWLEDGED,
                BrokerOrderState.PARTIALLY_FILLED,
            }:
                attempt.result = BrokerResult(
                    SubmissionOutcome.REJECTED,
                    order.broker_order_id,
                    order.state.value,
                )
                return attempt.result
        except (AlpacaPaperError, OSError, TimeoutError):
            self._discard_untransmitted_attempt("cancel", key, attempt)
            raise

        attempt.transmitted = True
        try:
            response = self._request("DELETE", self._order_path(order.broker_order_id))
        except WriteGateClosed:
            attempt.transmitted = False
            self._discard_untransmitted_attempt("cancel", key, attempt)
            raise
        except (OSError, TimeoutError, PaperHostViolation):
            attempt.result = self._unknown_result(order.broker_order_id)
            return attempt.result
        if 200 <= response.status_code < 300:
            attempt.result = BrokerResult(
                SubmissionOutcome.ACKNOWLEDGED,
                order.broker_order_id,
                BrokerOrderState.CANCEL_REQUESTED.value,
            )
        elif 400 <= response.status_code < 500 and response.status_code not in {408, 409, 425, 429}:
            attempt.result = BrokerResult(
                SubmissionOutcome.REJECTED,
                order.broker_order_id,
                order.state.value,
            )
        else:
            attempt.result = self._unknown_result(order.broker_order_id)
        return attempt.result

    def replace_order(
        self,
        request: Mapping[str, Any],
        *,
        client_order_key: str,
    ) -> BrokerResult:
        """Replace an unfilled simple DAY order once; never retry an ambiguous PATCH."""
        key = require_client_order_key(client_order_key)
        if not isinstance(request, Mapping):
            raise UnsupportedOrderTerms("replace_request_not_mapping")
        payload = self._build_order_payload(request, client_order_key=key)
        target_kind, target = self._target_order(request)
        self._validate_request_scope(
            request,
            expected_fingerprint=self.expected_account_fingerprint,
            client_order_key=key,
        )
        if request.get("action_kind") != "REPLACE_ORDER":
            raise UnsupportedOrderTerms("replace_action_required")
        attempt_payload = {
            "target_kind": target_kind,
            "target": target,
            "replacement": payload,
        }
        attempt, is_first = self._reserve_attempt("replace", key, attempt_payload)
        if not is_first:
            if attempt.result is not None and attempt.result.outcome != SubmissionOutcome.SUBMISSION_UNKNOWN:
                return attempt.result
            return self._reconcile_submission(key, payload, attempt)

        try:
            self._verify_tradeable_account()
            # Check the new client ID before PATCH to make a restart-safe replacement
            # lookup possible whenever Alpaca has made the accepted order visible.
            prior_replacement = self._query_order_by_client_key(key)
            if prior_replacement is not None:
                self._ensure_order_matches_payload(prior_replacement, payload)
                attempt.result = self._result_for_order(prior_replacement)
                return attempt.result
            old_order = self._lookup_target_order(target_kind, target)
            if old_order is None:
                attempt.result = self._unknown_result()
                return attempt.result
            if (
                old_order.provider_status != "new"
                or old_order.state != BrokerOrderState.ACKNOWLEDGED
                or old_order.filled_quantity != 0
                or old_order.symbol != payload["symbol"]
                or old_order.side.lower() != payload["side"]
            ):
                attempt.result = BrokerResult(
                    SubmissionOutcome.REJECTED,
                    old_order.broker_order_id,
                    old_order.state.value,
                )
                return attempt.result
            changes: dict[str, str] = {"client_order_id": key}
            if Decimal(payload["qty"]) != old_order.quantity:
                changes["qty"] = payload["qty"]
            if Decimal(payload["limit_price"]) != old_order.limit_price:
                changes["limit_price"] = payload["limit_price"]
            if len(changes) == 1:
                raise UnsupportedOrderTerms("replacement_has_no_order_term_change")
        except (AlpacaPaperError, OSError, TimeoutError):
            self._discard_untransmitted_attempt("replace", key, attempt)
            raise

        attempt.transmitted = True
        try:
            response = self._request(
                "PATCH",
                self._order_path(old_order.broker_order_id),
                body=changes,
            )
        except WriteGateClosed:
            attempt.transmitted = False
            self._discard_untransmitted_attempt("replace", key, attempt)
            raise
        except (OSError, TimeoutError, PaperHostViolation):
            attempt.result = self._unknown_result(old_order.broker_order_id)
            return attempt.result

        if response.status_code in {200, 201}:
            try:
                new_order = normalize_order(
                    self._require_object(
                        self._decode_json(response, accepted_statuses=(200, 201)),
                        reason="replace_response_invalid",
                    )
                )
                self._ensure_order_matches_payload(new_order, payload)
            except (AlpacaPaperError, OSError, TimeoutError):
                attempt.result = self._unknown_result(old_order.broker_order_id)
                return attempt.result
            attempt.result = self._result_for_order(new_order)
        elif 400 <= response.status_code < 500 and response.status_code not in {
            408,
            409,
            425,
            429,
        }:
            attempt.result = BrokerResult(
                SubmissionOutcome.REJECTED,
                old_order.broker_order_id,
                old_order.state.value,
            )
        else:
            attempt.result = self._unknown_result(old_order.broker_order_id)
        return attempt.result
