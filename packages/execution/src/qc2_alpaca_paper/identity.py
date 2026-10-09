"""Sanitized, read-only Alpaca paper-account identity observation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from .fingerprint import (
    ALPACA_PAPER_API_ORIGIN,
    FINGERPRINT_SCHEME_ID,
    InvalidPaperAccountIdentity,
    paper_account_fingerprint,
    validate_paper_identity_context,
)

from .models import (
    AccountIdentity,
    MalformedProviderResponse,
    PaperHostViolation,
    ProviderRequestFailed,
)
from .transport import PaperTransport, TransportResponse


IdentityRequest = Callable[[str, str], TransportResponse]


def observe_account_identity(
    transport: PaperTransport,
    *,
    request: IdentityRequest | None = None,
) -> AccountIdentity:
    """Read /v2/account and return only the v1 hash plus non-financial status."""
    origin = getattr(transport, "origin", None)
    try:
        validate_paper_identity_context(origin=origin)
    except InvalidPaperAccountIdentity:
        raise PaperHostViolation("paper_identity_origin_not_allowed") from None

    response = (request or transport.request)("GET", "/v2/account")
    if 300 <= response.status_code < 400:
        raise PaperHostViolation("paper_redirect_blocked")
    if response.status_code != 200:
        raise ProviderRequestFailed(response.status_code)
    try:
        value: Any = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MalformedProviderResponse("paper_account_response_invalid") from None
    if not isinstance(value, Mapping):
        raise MalformedProviderResponse("paper_account_response_invalid")

    try:
        fingerprint = paper_account_fingerprint(value.get("id"), origin=origin)
    except InvalidPaperAccountIdentity:
        raise MalformedProviderResponse("paper_account_id_invalid") from None

    status = value.get("status")
    trading_blocked = value.get("trading_blocked")
    account_blocked = value.get("account_blocked")
    if (
        not isinstance(status, str)
        or not status
        or not isinstance(trading_blocked, bool)
        or not isinstance(account_blocked, bool)
    ):
        raise MalformedProviderResponse("paper_account_identity_fields_missing")
    return AccountIdentity(
        fingerprint_scheme=FINGERPRINT_SCHEME_ID,
        account_fingerprint=fingerprint,
        broker="alpaca",
        environment="paper",
        origin=ALPACA_PAPER_API_ORIGIN,
        account_status=status,
        trading_blocked=trading_blocked,
        account_blocked=account_blocked,
    )
