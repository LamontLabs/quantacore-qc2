"""Errors raised when a temporal read cannot be proven safe."""

from __future__ import annotations


class TemporalViolation(ValueError):
    """A fail-closed temporal or permission decision with a stable reason code."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
