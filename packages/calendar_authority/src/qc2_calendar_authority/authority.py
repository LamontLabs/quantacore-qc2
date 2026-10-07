"""Single-source session inventory, phase, and deadline evaluation."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from qc2_contracts.runtime import (
    CONTENT_ADDRESSED,
    ContractValidationError,
    validate_contract,
    validate_contract_collection,
    verify_content_hash,
)

from .clock import ClockOutcome
from .errors import CalendarAuthorityError, CalendarUnavailable

UTC = timezone.utc
_CALENDAR_SCHEMA = "qc2.time_operation.CalendarManifest.v1"
_REVISION_SCHEMA = "qc2.time_operation.CalendarRevision.v1"
_SESSION_SCHEMA = "qc2.time_operation.MarketSession.v1"


@dataclass(frozen=True)
class PhaseAssessment:
    phase: str
    session_id: str | None
    reason_code: str


@dataclass(frozen=True)
class DeadlineDecision:
    allowed: bool
    reason_code: str
    deadline_at: str | None


class CalendarAuthority:
    """Validated, versioned market-session inventory with fail-closed queries."""

    def __init__(
        self,
        *,
        manifest: Mapping[str, Any],
        revisions: Iterable[Mapping[str, Any]],
        sessions: Iterable[Mapping[str, Any]],
        supporting_objects: Iterable[tuple[str, Mapping[str, Any]]] = (),
    ) -> None:
        manifest_record = _thaw(manifest)
        validate_contract("CalendarManifest", manifest_record)
        verify_content_hash("CalendarManifest", manifest_record)
        self.manifest = _freeze(manifest_record)
        if self.manifest["timezone"] != "America/New_York":
            raise CalendarAuthorityError("calendar_timezone_must_be_new_york")
        try:
            self.zone = ZoneInfo(self.manifest["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise CalendarUnavailable("calendar_timezone_unavailable") from exc

        self.valid_from = _parse_date(self.manifest["valid_from"])
        self.valid_through = _parse_date(self.manifest["valid_through"])
        if self.valid_from > self.valid_through:
            raise CalendarAuthorityError("calendar_range_reversed")

        inventory = tuple(self.manifest["sessions"])
        parsed_inventory = tuple(_parse_date(item) for item in inventory)
        if (
            not inventory
            or tuple(sorted(set(inventory))) != inventory
            or parsed_inventory[0] != self.valid_from
            or parsed_inventory[-1] != self.valid_through
        ):
            raise CalendarAuthorityError("calendar_session_inventory_invalid")
        self.session_ids = inventory
        self._session_dates = parsed_inventory

        revision_records = tuple(_thaw(row) for row in revisions)
        if not revision_records:
            raise CalendarUnavailable("calendar_revision_unavailable")
        revisions_by_date: list[tuple[date, Mapping[str, Any]]] = []
        seen_revision_ids: set[str] = set()
        seen_revision_numbers: set[int] = set()
        seen_effective_dates: set[date] = set()
        for revision in revision_records:
            validate_contract("CalendarRevision", revision)
            reference = revision["calendar_ref"]
            if (
                reference["target_schema_name"] != _CALENDAR_SCHEMA
                or reference["target_id"] != self.manifest["id"]
                or reference.get("content_hash") != self.manifest["content_hash"]
            ):
                raise CalendarAuthorityError("calendar_revision_manifest_mismatch")
            effective = _parse_date(revision["effective_session"])
            if not self.valid_from <= effective <= self.valid_through:
                raise CalendarAuthorityError("calendar_revision_outside_range")
            if effective.isoformat() not in self.session_ids:
                raise CalendarAuthorityError("calendar_revision_effective_session_missing")
            if revision["id"] in seen_revision_ids:
                raise CalendarAuthorityError("calendar_revision_duplicate")
            if revision["revision_number"] in seen_revision_numbers:
                raise CalendarAuthorityError("calendar_revision_number_duplicate")
            if effective in seen_effective_dates:
                raise CalendarAuthorityError("calendar_revision_effective_date_duplicate")
            seen_revision_ids.add(revision["id"])
            seen_revision_numbers.add(revision["revision_number"])
            seen_effective_dates.add(effective)
            revisions_by_date.append((effective, revision))

        revisions_by_date.sort(key=lambda item: item[0])
        if revisions_by_date != sorted(
            revisions_by_date, key=lambda item: item[1]["revision_number"]
        ):
            raise CalendarAuthorityError("calendar_revision_order_invalid")
        self._revisions_by_date = tuple(
            (effective, _freeze(revision)) for effective, revision in revisions_by_date
        )
        self.revisions = tuple(revision for _, revision in self._revisions_by_date)

        session_records = tuple(_thaw(session) for session in sessions)
        self._sessions: dict[str, Mapping[str, Any]] = {}
        seen_session_record_ids: set[str] = set()
        for record in session_records:
            validate_contract("MarketSession", record)
            if record["id"] in seen_session_record_ids:
                raise CalendarAuthorityError("market_session_record_id_duplicate")
            seen_session_record_ids.add(record["id"])
            session_id = record["session_id"]
            if session_id not in self.session_ids:
                raise CalendarAuthorityError("market_session_not_in_manifest")
            if session_id in self._sessions:
                raise CalendarAuthorityError("market_session_duplicate")
            reference = record["calendar_revision_ref"]
            expected_revision = self._revision_for(_parse_date(session_id))
            if (
                reference["target_schema_name"] != _REVISION_SCHEMA
                or reference["target_id"] != expected_revision["id"]
            ):
                raise CalendarAuthorityError("market_session_revision_mismatch")
            opening = _parse_utc(record["opens_at"])
            closing = _parse_utc(record["closes_at"])
            session_day = _parse_date(session_id)
            if (
                opening.astimezone(self.zone).date() != session_day
                or closing.astimezone(self.zone).date() != session_day
            ):
                raise CalendarAuthorityError("market_session_local_date_mismatch")
            if closing <= opening:
                raise CalendarAuthorityError("market_session_close_not_after_open")
            self._sessions[session_id] = _freeze(record)

        if set(self._sessions) != set(self.session_ids):
            raise CalendarUnavailable("calendar_session_inventory_incomplete")
        self._open_dates = tuple(_parse_date(value) for value in self.session_ids)

        collection = [
            ("CalendarManifest", manifest_record),
            *[("CalendarRevision", _thaw(revision)) for revision in revision_records],
            *[("MarketSession", session) for session in session_records],
        ]
        collection.extend((name, _thaw(payload)) for name, payload in supporting_objects)
        try:
            validate_contract_collection(collection)
            for name, payload in collection:
                if name in CONTENT_ADDRESSED:
                    verify_content_hash(name, payload)
        except ContractValidationError as exc:
            raise CalendarAuthorityError("calendar_reference_integrity_failed") from exc

    def scheduled_sessions(self, start: str, end: str) -> tuple[str, ...]:
        first, last = _parse_date(start), _parse_date(end)
        self._require_covered(first, last)
        return tuple(
            session_id
            for session_id in self.session_ids
            if first <= _parse_date(session_id) <= last
        )

    def next_session(self, after_session: str) -> str:
        after = _parse_date(after_session)
        if after < self.valid_from:
            raise CalendarUnavailable("calendar_range_unavailable")
        if after > self.valid_through:
            raise CalendarUnavailable("calendar_expired")
        index = bisect_right(self._open_dates, after)
        if index >= len(self.session_ids):
            raise CalendarUnavailable("calendar_range_unavailable")
        return self.session_ids[index]

    def phase_at(self, instant: datetime | str) -> PhaseAssessment:
        point = _parse_utc(instant)
        session_day = point.astimezone(self.zone).date()
        if session_day < self.valid_from:
            return PhaseAssessment("UNAVAILABLE", None, "calendar_range_unavailable")
        if session_day > self.valid_through:
            return PhaseAssessment("UNAVAILABLE", None, "calendar_expired")
        session_id = session_day.isoformat()
        record = self._sessions.get(session_id)
        if record is None:
            return PhaseAssessment("CLOSED", None, "market_closed")
        opening, closing = _parse_utc(record["opens_at"]), _parse_utc(record["closes_at"])
        if point < opening:
            return PhaseAssessment("PRE_OPEN", session_id, "before_session_open")
        if point < closing:
            return PhaseAssessment("REGULAR", session_id, "within_session")
        return PhaseAssessment("POST_CLOSE", session_id, "after_session_close")

    def deadline_at(self, session_id: str, boundary: str) -> str:
        _parse_date(session_id)
        if session_id not in self._sessions:
            if session_id not in self.session_ids:
                raise CalendarUnavailable("calendar_session_unavailable")
            raise CalendarUnavailable("calendar_session_inventory_incomplete")
        if boundary not in {"OPEN", "CLOSE"}:
            raise CalendarAuthorityError("calendar_deadline_boundary_invalid")
        field = "opens_at" if boundary == "OPEN" else "closes_at"
        return str(self._sessions[session_id][field])

    def deadline_gate(
        self,
        *,
        session_id: str,
        boundary: str,
        clock: ClockOutcome,
    ) -> DeadlineDecision:
        if clock.assessment is None:
            return DeadlineDecision(False, clock.reason_code, None)
        assessment = dict(clock.assessment)
        validate_contract("ClockAssessment", assessment)
        if clock.status != "TRUSTED" or assessment["status"] != "TRUSTED":
            return DeadlineDecision(False, clock.reason_code, None)

        trusted_time = _parse_utc(assessment["trusted_time_at"])
        current_session_date = trusted_time.astimezone(self.zone).date()
        if current_session_date > self.valid_through:
            return DeadlineDecision(False, "calendar_expired", None)
        if current_session_date < self.valid_from:
            return DeadlineDecision(False, "calendar_range_unavailable", None)
        try:
            deadline = _parse_utc(self.deadline_at(session_id, boundary))
        except CalendarUnavailable as exc:
            return DeadlineDecision(False, exc.code, None)

        uncertainty = timedelta(milliseconds=assessment["uncertainty_ms"])
        if trusted_time + uncertainty < deadline:
            return DeadlineDecision(True, "before_deadline", _format_utc(deadline))
        if trusted_time - uncertainty >= deadline:
            return DeadlineDecision(False, "deadline_passed", _format_utc(deadline))
        return DeadlineDecision(False, "deadline_uncertain", _format_utc(deadline))

    def _revision_for(self, session_day: date) -> Mapping[str, Any]:
        eligible = [
            revision for effective, revision in self._revisions_by_date if effective <= session_day
        ]
        if not eligible:
            raise CalendarUnavailable("calendar_revision_not_yet_effective")
        return eligible[-1]

    def _require_covered(self, start: date, end: date) -> None:
        if start > end:
            raise CalendarAuthorityError("calendar_range_reversed")
        if start < self.valid_from or end > self.valid_through:
            if start > self.valid_through:
                raise CalendarUnavailable("calendar_expired")
            raise CalendarUnavailable("calendar_range_unavailable")


def _parse_date(value: object) -> date:
    if not isinstance(value, str):
        raise CalendarAuthorityError("session_date_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CalendarAuthorityError("session_date_invalid") from exc
    if parsed.isoformat() != value:
        raise CalendarAuthorityError("session_date_invalid")
    return parsed


def _parse_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CalendarAuthorityError("utc_instant_invalid") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise CalendarAuthorityError("utc_instant_invalid")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise CalendarAuthorityError("utc_instant_must_be_explicit_utc")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    if normalized.microsecond == 0:
        return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")
    fractional = f"{normalized.microsecond:06d}".rstrip("0")
    return normalized.strftime("%Y-%m-%dT%H:%M:%S") + f".{fractional}Z"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value
