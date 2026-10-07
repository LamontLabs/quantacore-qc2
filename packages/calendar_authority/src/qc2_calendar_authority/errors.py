"""Stable, non-sensitive calendar authority errors."""


class CalendarAuthorityError(ValueError):
    """A malformed or internally inconsistent calendar input."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CalendarUnavailable(CalendarAuthorityError):
    """Required calendar coverage or provider data is unavailable."""
