"""Versioned Alpaca paper-account identity fingerprint implementation."""

from __future__ import annotations

import hashlib
import re
from typing import Literal, TypedDict
from urllib.parse import urlsplit

from qc2_contracts.runtime import canonical_json_bytes


FINGERPRINT_SCHEME_ID = "qc2.alpaca-paper-account-fingerprint.v1"
FINGERPRINT_DOMAIN = FINGERPRINT_SCHEME_ID.encode("ascii")
ALPACA_PAPER_API_ORIGIN = "https://paper-api.alpaca.markets"
ALPACA_PAPER_API_HOST = "paper-api.alpaca.markets"

_ACCOUNT_UUID_PATTERN = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\Z"
)
_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


class InvalidPaperAccountIdentity(ValueError):
    """Invalid identity input; exception messages never contain the input value."""


class AlpacaPaperAccountIdentityV1(TypedDict):
    account_id: str
    broker: Literal["alpaca"]
    environment: Literal["paper"]
    origin: Literal["https://paper-api.alpaca.markets"]


def validate_paper_identity_context(
    *,
    broker: object = "alpaca",
    environment: object = "paper",
    origin: object = ALPACA_PAPER_API_ORIGIN,
) -> None:
    """Require the exact paper broker identity and its allowed HTTPS origin."""
    if (
        broker != "alpaca"
        or environment != "paper"
        or not isinstance(origin, str)
        or origin != ALPACA_PAPER_API_ORIGIN
    ):
        raise InvalidPaperAccountIdentity("paper_identity_context_unsupported")
    parsed = urlsplit(ALPACA_PAPER_API_ORIGIN)
    if (
        parsed.scheme != "https"
        or parsed.netloc != ALPACA_PAPER_API_HOST
        or parsed.hostname != ALPACA_PAPER_API_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise InvalidPaperAccountIdentity("paper_identity_origin_unsupported")


def require_fingerprint_scheme(value: object) -> str:
    if value != FINGERPRINT_SCHEME_ID:
        raise InvalidPaperAccountIdentity("paper_fingerprint_scheme_unsupported")
    return FINGERPRINT_SCHEME_ID


def normalize_paper_account_id(value: object) -> str:
    """Validate and lowercase an exact hyphenated UUID without echoing it."""
    if not isinstance(value, str) or not _ACCOUNT_UUID_PATTERN.fullmatch(value):
        raise InvalidPaperAccountIdentity("paper_account_id_invalid")
    normalized = value.lower()
    if normalized == _ZERO_UUID:
        raise InvalidPaperAccountIdentity("paper_account_id_invalid")
    return normalized


def _identity_payload(
    account_id: object,
    *,
    broker: object,
    environment: object,
    origin: object,
) -> tuple[AlpacaPaperAccountIdentityV1, bytes]:
    validate_paper_identity_context(
        broker=broker,
        environment=environment,
        origin=origin,
    )
    normalized_id = normalize_paper_account_id(account_id)
    identity: AlpacaPaperAccountIdentityV1 = {
        "account_id": normalized_id,
        "broker": "alpaca",
        "environment": "paper",
        "origin": ALPACA_PAPER_API_ORIGIN,
    }
    return identity, canonical_json_bytes(identity)


def paper_account_fingerprint(
    account_id: object,
    *,
    broker: object = "alpaca",
    environment: object = "paper",
    origin: object = ALPACA_PAPER_API_ORIGIN,
) -> str:
    """Return the v1 fingerprint; mutable account data and credentials are excluded."""
    _, payload_bytes = _identity_payload(
        account_id,
        broker=broker,
        environment=environment,
        origin=origin,
    )
    return hashlib.sha256(FINGERPRINT_DOMAIN + b"\x00" + payload_bytes).hexdigest()
