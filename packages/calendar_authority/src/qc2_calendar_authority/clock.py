"""Clock comparison and deadline-safe assessment helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any

from qc2_contracts.runtime import validate_contract

from .errors import CalendarAuthorityError

UTC = timezone.utc


@dataclass(frozen=True)
class ClockReading:
    observed_at: datetime
    trusted_time_at: datetime
    wall_clock_at: datetime
    monotonic_elapsed_ms: int
    uncertainty_ms: int


@dataclass(frozen=True)
class ClockOutcome:
    status: str
    reason_code: str
    assessment: Mapping[str, Any] | None


class ClockMonitor:
    """Assess supplied clock samples and latch detected backward jumps.

    The monitor is process-local. A production caller must restore its previous
    sample and any latched fault from durable authority before enabling actions.
    """

    def __init__(self, *, max_uncertainty_ms: int | None) -> None:
        if max_uncertainty_ms is not None and (
            not isinstance(max_uncertainty_ms, int)
            or isinstance(max_uncertainty_ms, bool)
            or max_uncertainty_ms < 0
        ):
            raise CalendarAuthorityError("clock_uncertainty_limit_invalid")
        self.max_uncertainty_ms = max_uncertainty_ms
        self._previous: ClockReading | None = None
        self._backward_jump_latched = False

    def assess(
        self,
        reading: ClockReading,
        *,
        assessment_id: str,
        created_at: str,
        evidence_class: str,
        environment_namespace: str,
        source_refs: Sequence[Mapping[str, Any]] = (),
    ) -> ClockOutcome:
        _validate_reading(reading)
        status, reason = self._status_for(reading)
        record = {
            "schema_name": "qc2.time_operation.ClockAssessment.v1",
            "schema_version": "1.0",
            "id": assessment_id,
            "created_at": created_at,
            "owning_authority": "calendar",
            "evidence_class": evidence_class,
            "environment_namespace": environment_namespace,
            "source_refs": [dict(ref) for ref in source_refs],
            "observed_at": _format_utc(reading.observed_at),
            "trusted_time_at": _format_utc(reading.trusted_time_at),
            "wall_clock_at": _format_utc(reading.wall_clock_at),
            "monotonic_elapsed_ms": reading.monotonic_elapsed_ms,
            "uncertainty_ms": reading.uncertainty_ms,
            "status": status,
        }
        validate_contract("ClockAssessment", record)
        self._previous = reading
        return ClockOutcome(
            status=status,
            reason_code=reason,
            assessment=MappingProxyType(record),
        )

    def unavailable(self, reason_code: str) -> ClockOutcome:
        """Represent missing trusted-time input without fabricating a wire record."""
        return ClockOutcome(status="UNAVAILABLE", reason_code=reason_code, assessment=None)

    def _status_for(self, reading: ClockReading) -> tuple[str, str]:
        if self._backward_jump_latched:
            return "BACKWARD_JUMP", "clock_backward_jump"

        if self._previous is not None:
            uncertainty_budget = self._previous.uncertainty_ms + reading.uncertainty_ms
            expected_wall = self._previous.wall_clock_at + timedelta(
                milliseconds=reading.monotonic_elapsed_ms
            )
            wall_went_back = reading.wall_clock_at < expected_wall - timedelta(
                milliseconds=uncertainty_budget
            )
            trusted_went_back = (
                reading.trusted_time_at
                < self._previous.trusted_time_at - timedelta(milliseconds=uncertainty_budget)
            )
            if wall_went_back or trusted_went_back:
                self._backward_jump_latched = True
                return "BACKWARD_JUMP", "clock_backward_jump"

        if self.max_uncertainty_ms is None:
            return "UNAVAILABLE", "clock_uncertainty_limit_unavailable"
        if reading.uncertainty_ms > self.max_uncertainty_ms:
            return "UNCERTAIN", "clock_uncertainty_exceeds_limit"

        skew_ms = abs((reading.wall_clock_at - reading.trusted_time_at).total_seconds() * 1000)
        if skew_ms > self.max_uncertainty_ms:
            return "UNCERTAIN", "wall_clock_disagrees_with_trusted_time"
        return "TRUSTED", "clock_trusted"


def _validate_reading(reading: ClockReading) -> None:
    if not isinstance(reading, ClockReading):
        raise CalendarAuthorityError("clock_reading_invalid")
    for value in (
        reading.observed_at,
        reading.trusted_time_at,
        reading.wall_clock_at,
    ):
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() != timedelta(0)
        ):
            raise CalendarAuthorityError("clock_instants_must_be_utc")
    if (
        not isinstance(reading.monotonic_elapsed_ms, int)
        or isinstance(reading.monotonic_elapsed_ms, bool)
        or reading.monotonic_elapsed_ms < 0
    ):
        raise CalendarAuthorityError("clock_monotonic_elapsed_invalid")
    if (
        not isinstance(reading.uncertainty_ms, int)
        or isinstance(reading.uncertainty_ms, bool)
        or reading.uncertainty_ms < 0
    ):
        raise CalendarAuthorityError("clock_uncertainty_invalid")


def _format_utc(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    if normalized.microsecond == 0:
        return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")
    fractional = f"{normalized.microsecond:06d}".rstrip("0")
    return normalized.strftime("%Y-%m-%dT%H:%M:%S") + f".{fractional}Z"
