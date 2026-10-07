"""Explicit failure codes for the canonical market-data acquisition path."""

from __future__ import annotations


class MarketDataError(RuntimeError):
    """A safe, stable failure code; messages never include credentials or URLs."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
