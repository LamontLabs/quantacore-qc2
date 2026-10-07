"""Injectable transport; the concrete HTTP transport cannot change providers."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .errors import MarketDataError

ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"
_ALLOWED_PATHS = frozenset({"/v2/stocks/bars", "/v1/corporate-actions"})


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class AlpacaTransport:
    """Structural protocol for deterministic scripted and HTTP transports."""

    def get(self, path: str, params: Mapping[str, str]) -> HttpResponse:
        raise NotImplementedError


class UrllibAlpacaTransport(AlpacaTransport):
    """HTTP GET transport bound to Alpaca's official market-data host.

    Credentials are supplied by an injected callback, never read from the
    environment and never included in request evidence.
    """

    def __init__(
        self,
        credential_headers: Callable[[], Mapping[str, str]],
        timeout_seconds: float,
    ) -> None:
        if timeout_seconds <= 0:
            raise MarketDataError("transport_timeout_invalid")
        self._credential_headers = credential_headers
        self._timeout_seconds = timeout_seconds

    def get(self, path: str, params: Mapping[str, str]) -> HttpResponse:
        if path not in _ALLOWED_PATHS:
            raise MarketDataError("provider_endpoint_not_allowed")
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in params.items()):
            raise MarketDataError("provider_query_invalid")
        try:
            headers = dict(self._credential_headers())
        except Exception:
            raise MarketDataError("credentials_unavailable") from None
        header_names = {key.lower() for key in headers}
        if not {
            "apca-api-key-id",
            "apca-api-secret-key",
        }.issubset(header_names):
            raise MarketDataError("credentials_unavailable")

        query = urllib.parse.urlencode(sorted(params.items()))
        url = f"{ALPACA_DATA_BASE_URL}{path}?{query}"
        request = urllib.request.Request(
            url,
            headers=headers,
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                return HttpResponse(
                    status_code=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response.read(),
                )
        except urllib.error.HTTPError as response:
            return HttpResponse(
                status_code=response.code,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(),
            )
        except Exception:
            raise MarketDataError("transport_error") from None
