"""Versioned, fail-closed exchange calendar and clock authority."""

from .authority import CalendarAuthority, DeadlineDecision, PhaseAssessment
from .clock import ClockMonitor, ClockOutcome, ClockReading
from .errors import CalendarAuthorityError, CalendarUnavailable
from .provider import AlpacaCalendarAdapter, ProviderSession
from .records import build_calendar_records

__all__ = [
    "AlpacaCalendarAdapter",
    "CalendarAuthority",
    "CalendarAuthorityError",
    "CalendarUnavailable",
    "ClockMonitor",
    "ClockOutcome",
    "ClockReading",
    "DeadlineDecision",
    "PhaseAssessment",
    "ProviderSession",
    "build_calendar_records",
]
