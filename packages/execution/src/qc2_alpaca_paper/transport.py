"""Fixed-host HTTPS transport for the Alpaca paper API."""

from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import ssl
from typing import Any, Mapping, Protocol
from urllib.parse import unquote, urlsplit

from .fingerprint import (
    ALPACA_PAPER_API_ORIGIN,
    InvalidPaperAccountIdentity,
    validate_paper_identity_context,
)

from .models import PaperHostViolation, WriteGateClosed


PAPER_API_HOST = "paper-api.alpaca.markets"
PAPER_API_BASE_URL = f"https://{PAPER_API_HOST}"
_MAX_RESPONSE_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None


class PaperTransport(Protocol):
    @property
    def origin(self) -> str: ...

    def request(
        self,
        method: str,
        relative_path: str,
        *,
        body: Mapping[str, Any] | None = None,
    ) -> TransportResponse: ...


def validate_paper_relative_path(relative_path: str) -> None:
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or len(relative_path) > 4096
        or any(ord(character) < 32 or ord(character) == 127 for character in relative_path)
        or "\\" in relative_path
    ):
        raise PaperHostViolation("paper_path_invalid")
    parsed = urlsplit(relative_path)
    decoded_path = unquote(parsed.path)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or not decoded_path.startswith("/v2/")
        or any(segment in {".", ".."} for segment in decoded_path.split("/"))
        or decoded_path.startswith("//")
    ):
        raise PaperHostViolation("paper_path_outside_allowlist")


class StdlibPaperTransport:
    """No configurable host and no redirects; this transport never sends mutations."""

    def __init__(self, api_key: str, secret_key: str, *, timeout_seconds: float = 10.0):
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("Alpaca API key is missing")
        if not isinstance(secret_key, str) or not secret_key:
            raise ValueError("Alpaca API secret is missing")
        if not 0 < timeout_seconds <= 20:
            raise ValueError("timeout_seconds must be in (0, 20]")
        self._api_key = api_key
        self._secret_key = secret_key
        self._timeout_seconds = timeout_seconds

    @property
    def origin(self) -> str:
        return ALPACA_PAPER_API_ORIGIN

    def __repr__(self) -> str:
        return "StdlibPaperTransport(host='paper-api.alpaca.markets', mutations_enabled=False)"

    def request(
        self,
        method: str,
        relative_path: str,
        *,
        body: Mapping[str, Any] | None = None,
    ) -> TransportResponse:
        normalized_method = method.upper() if isinstance(method, str) else ""
        if normalized_method != "GET":
            raise WriteGateClosed("paper_mutations_disabled_until_qc2_086")
        try:
            validate_paper_identity_context(origin=self.origin)
        except InvalidPaperAccountIdentity:
            raise PaperHostViolation("paper_connection_origin_not_allowed") from None
        if (
            self.origin != PAPER_API_BASE_URL
            or PAPER_API_BASE_URL != f"https://{PAPER_API_HOST}"
            or urlsplit(self.origin).hostname != PAPER_API_HOST
        ):
            raise PaperHostViolation("paper_connection_origin_not_allowed")
        validate_paper_relative_path(relative_path)
        connection = http.client.HTTPSConnection(
            PAPER_API_HOST,
            timeout=self._timeout_seconds,
            context=ssl.create_default_context(),
        )
        headers = {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret_key,
            "Accept": "application/json",
            "User-Agent": "qc2-alpaca-paper-adapter/1",
        }
        payload = None
        if body is not None:
            payload = json.dumps(
                body,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            connection.request(normalized_method, relative_path, body=payload, headers=headers)
            response = connection.getresponse()
            response_body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(response_body) > _MAX_RESPONSE_BYTES:
                raise PaperHostViolation("paper_response_too_large")
            return TransportResponse(
                status_code=response.status,
                headers={key.lower(): value for key, value in response.getheaders()},
                body=response_body,
            )
        except PaperHostViolation:
            raise
        except (OSError, http.client.HTTPException, ssl.SSLError):
            raise ConnectionError("paper_transport_failure") from None
        finally:
            connection.close()
