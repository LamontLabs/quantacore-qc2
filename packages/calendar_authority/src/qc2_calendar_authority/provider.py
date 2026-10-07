"""Offline adapters for explicitly supplied provider-calendar payloads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from .errors import CalendarAuthorityError, CalendarUnavailable

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class ProviderSession:
    """A normalized provider session; it is not evidence of live capability."""

    session_id: str
    opens_at: str
    closes_at: str


class AlpacaCalendarAdapter:
    """Normalize a supplied Alpaca-style calendar response without network I/O.

    The adapter intentionally does not fetch data, retry, choose another
    provider, or assert that a response covers a requested period. Live
    entitlement and response-completeness measurements belong to QC2-010.
    """

    _FIELDS = frozenset({"date", "open", "close"})

    def normalize_rows(
        self,
        rows: Iterable[Mapping[str, object]],
        *,
        valid_from: str,
        valid_through: str,
    ) -> tuple[ProviderSession, ...]:
        start = _parse_session_date(valid_from)
        end = _parse_session_date(valid_through)
        if start > end:
            raise CalendarAuthorityError("calendar_range_reversed")

        normalized: dict[date, ProviderSession] = {}
        for row in rows:
            if not isinstance(row, Mapping) or frozenset(row) != self._FIELDS:
                raise CalendarAuthorityError("provider_calendar_row_shape_invalid")
            session_day = _parse_session_date(row["date"])
            if not start <= session_day <= end:
                raise CalendarAuthorityError("provider_session_outside_declared_range")
            if session_day in normalized:
                raise CalendarAuthorityError("provider_session_duplicate")
            opening = _parse_local_time(row["open"])
            closing = _parse_local_time(row["close"])
            open_at = _local_to_utc(session_day, opening)
            close_at = _local_to_utc(session_day, closing)
            if close_at <= open_at:
                raise CalendarAuthorityError("provider_session_close_not_after_open")
            normalized[session_day] = ProviderSession(
                session_id=session_day.isoformat(),
                opens_at=_format_utc(open_at),
                closes_at=_format_utc(close_at),
            )

        if not normalized:
            raise CalendarUnavailable("provider_calendar_empty")
        if start not in normalized or end not in normalized:
            raise CalendarUnavailable("provider_calendar_boundary_unavailable")
        return tuple(normalized[day] for day in sorted(normalized))


def _parse_session_date(value: object) -> date:
    if not isinstance(value, str):
        raise CalendarAuthorityError("session_date_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CalendarAuthorityError("session_date_invalid") from exc
    if parsed.isoformat() != value:
        raise CalendarAuthorityError("session_date_invalid")
    return parsed


def _parse_local_time(value: object) -> time:
    if not isinstance(value, str):
        raise CalendarAuthorityError("provider_local_time_invalid")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise CalendarAuthorityError("provider_local_time_invalid") from exc
    if parsed.tzinfo is not None or len(value) not in {5, 8}:
        raise CalendarAuthorityError("provider_local_time_invalid")
    timespec = "minutes" if len(value) == 5 else "seconds"
    if parsed.isoformat(timespec=timespec) != value:
        raise CalendarAuthorityError("provider_local_time_invalid")
    return parsed


def _local_to_utc(session_day: date, local_time: time) -> datetime:
    local_value = datetime.combine(session_day, local_time)
    candidates = [local_value.replace(tzinfo=NEW_YORK, fold=fold) for fold in (0, 1)]
    valid = [
        candidate
        for candidate in candidates
        if candidate.astimezone(UTC).astimezone(NEW_YORK).replace(tzinfo=None) == local_value
    ]
    offsets = {candidate.utcoffset() for candidate in valid}
    if not valid:
        raise CalendarAuthorityError("provider_local_time_nonexistent")
    if len(offsets) > 1:
        raise CalendarAuthorityError("provider_local_time_ambiguous")
    return valid[0].astimezone(UTC)


def _format_utc(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    if normalized.microsecond == 0:
        return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")
    fractional = f"{normalized.microsecond:06d}".rstrip("0")
    return normalized.strftime("%Y-%m-%dT%H:%M:%S") + f".{fractional}Z"
