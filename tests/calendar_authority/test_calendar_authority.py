from __future__ import annotations

from datetime import datetime, timezone
from itertools import count
from typing import Any

import pytest
from qc2_contracts.runtime import (
    canonical_content_hash,
    verify_content_hash,
)

from qc2_calendar_authority import (
    AlpacaCalendarAdapter,
    CalendarAuthority,
    CalendarAuthorityError,
    CalendarUnavailable,
    ClockMonitor,
    ClockReading,
    build_calendar_records,
)

UTC = timezone.utc
EVIDENCE_SCHEMA = "qc2.integrity_build.EvidenceEvent.v1"


def _uuid(number: int) -> str:
    return f"018f0000-0000-7000-8000-{number:012x}"


def _make_calendar(
    rows: list[dict[str, str]],
    valid_from: str,
    valid_through: str,
) -> tuple[
    CalendarAuthority,
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
]:
    provider_sessions = AlpacaCalendarAdapter().normalize_rows(
        rows, valid_from=valid_from, valid_through=valid_through
    )
    generated_ids = count(100)
    evidence_event: dict[str, Any] = {
        "schema_name": EVIDENCE_SCHEMA,
        "schema_version": "1.0",
        "id": _uuid(3),
        "created_at": "2025-01-01T00:00:00Z",
        "owning_authority": "evidence",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        "content_hash": "0" * 64,
        "installation_id": "calendar-fixture",
        "stream_id": "calendar-fixture",
        "sequence": 1,
        "event_type": "calendar_fixture_source",
        "actor_identity": "fixture",
        "authorized_command_ref": None,
        "correlation_id": "calendar-fixture",
        "payload_hash": "b" * 64,
        "dependency_refs": [],
        "previous_event_hash": None,
        "event_hash": "c" * 64,
        "wall_clock_at": "2025-01-01T00:00:00Z",
        "monotonic_generation": 0,
    }
    evidence_event["content_hash"] = canonical_content_hash("EvidenceEvent", evidence_event)
    manifest, revision, sessions = build_calendar_records(
        provider_sessions,
        calendar_id=_uuid(1),
        revision_id=_uuid(2),
        calendar_version=1,
        revision_number=1,
        valid_from=valid_from,
        valid_through=valid_through,
        effective_session=valid_from,
        revision_reason="Pinned synthetic calendar fixture.",
        created_at="2025-01-01T00:00:00Z",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
        source_evidence_ref={
            "target_schema_name": EVIDENCE_SCHEMA,
            "target_id": evidence_event["id"],
            "content_hash": evidence_event["content_hash"],
        },
        id_factory=lambda: _uuid(next(generated_ids)),
    )
    verify_content_hash("EvidenceEvent", evidence_event)
    return (
        CalendarAuthority(
            manifest=manifest,
            revisions=[revision],
            sessions=sessions,
            supporting_objects=[("EvidenceEvent", evidence_event)],
        ),
        manifest,
        revision,
        sessions,
        evidence_event,
    )


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _clock(
    instant: str,
    *,
    assessment_number: int = 20,
    max_uncertainty_ms: int | None = 250,
    wall_clock: str | None = None,
    elapsed_ms: int = 0,
    uncertainty_ms: int = 100,
) -> tuple[ClockMonitor, Any]:
    monitor = ClockMonitor(max_uncertainty_ms=max_uncertainty_ms)
    moment = _dt(instant)
    reading = ClockReading(
        observed_at=moment,
        trusted_time_at=moment,
        wall_clock_at=_dt(wall_clock) if wall_clock else moment,
        monotonic_elapsed_ms=elapsed_ms,
        uncertainty_ms=uncertainty_ms,
    )
    outcome = monitor.assess(
        reading,
        assessment_id=_uuid(assessment_number),
        created_at=instant,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    return monitor, outcome


def test_alpaca_adapter_converts_new_york_times_across_dst() -> None:
    rows = [
        {"date": "2025-03-07", "open": "09:30", "close": "16:00"},
        {"date": "2025-03-10", "open": "09:30", "close": "16:00"},
    ]

    sessions = AlpacaCalendarAdapter().normalize_rows(
        rows, valid_from="2025-03-07", valid_through="2025-03-10"
    )

    assert sessions[0].opens_at == "2025-03-07T14:30:00Z"
    assert sessions[1].opens_at == "2025-03-10T13:30:00Z"


def test_alpaca_adapter_preserves_early_close_and_requires_boundary_coverage() -> None:
    adapter = AlpacaCalendarAdapter()
    rows = [
        {"date": "2025-07-03", "open": "09:30", "close": "13:00"},
        {"date": "2025-07-07", "open": "09:30", "close": "16:00"},
    ]

    sessions = adapter.normalize_rows(rows, valid_from="2025-07-03", valid_through="2025-07-07")
    assert sessions[0].closes_at == "2025-07-03T17:00:00Z"

    with pytest.raises(CalendarUnavailable, match="provider_calendar_boundary_unavailable"):
        adapter.normalize_rows(rows[:1], valid_from="2025-07-03", valid_through="2025-07-07")


@pytest.mark.parametrize(
    ("day", "opening", "closing", "error_code"),
    [
        ("2025-03-09", "02:30", "03:30", "provider_local_time_nonexistent"),
        ("2025-11-02", "01:30", "02:30", "provider_local_time_ambiguous"),
    ],
)
def test_adapter_rejects_nonexistent_and_ambiguous_local_times(
    day: str, opening: str, closing: str, error_code: str
) -> None:
    with pytest.raises(CalendarAuthorityError, match=error_code):
        AlpacaCalendarAdapter().normalize_rows(
            [{"date": day, "open": opening, "close": closing}],
            valid_from=day,
            valid_through=day,
        )


def test_provider_rows_reject_duplicate_dates_and_unexpected_fields() -> None:
    adapter = AlpacaCalendarAdapter()
    row = {"date": "2025-03-07", "open": "09:30", "close": "16:00"}
    with pytest.raises(CalendarAuthorityError, match="provider_session_duplicate"):
        adapter.normalize_rows([row, row], valid_from="2025-03-07", valid_through="2025-03-07")
    with pytest.raises(CalendarAuthorityError, match="provider_calendar_row_shape_invalid"):
        adapter.normalize_rows(
            [{**row, "timezone": "UTC"}],
            valid_from="2025-03-07",
            valid_through="2025-03-07",
        )


def test_manifest_hash_and_market_session_inventory_are_validated() -> None:
    rows = [
        {"date": "2025-03-07", "open": "09:30", "close": "16:00"},
        {"date": "2025-03-10", "open": "09:30", "close": "16:00"},
    ]
    authority, manifest, _, sessions, evidence_event = _make_calendar(
        rows, "2025-03-07", "2025-03-10"
    )

    verify_content_hash("CalendarManifest", manifest)
    assert authority.scheduled_sessions("2025-03-07", "2025-03-10") == (
        "2025-03-07",
        "2025-03-10",
    )
    with pytest.raises(CalendarUnavailable, match="calendar_session_inventory_incomplete"):
        CalendarAuthority(
            manifest=manifest,
            revisions=[authority.revisions[0]],
            sessions=sessions[:1],
            supporting_objects=[("EvidenceEvent", evidence_event)],
        )


def test_unresolved_source_evidence_blocks_calendar_use() -> None:
    authority, manifest, revision, sessions, _ = _make_calendar(
        [
            {"date": "2025-03-07", "open": "09:30", "close": "16:00"},
            {"date": "2025-03-10", "open": "09:30", "close": "16:00"},
        ],
        "2025-03-07",
        "2025-03-10",
    )
    with pytest.raises(CalendarAuthorityError, match="calendar_reference_integrity_failed"):
        CalendarAuthority(
            manifest=manifest,
            revisions=[revision],
            sessions=sessions,
        )
    assert authority.session_ids


def test_modified_supporting_evidence_hash_blocks_calendar_use() -> None:
    _, manifest, revision, sessions, evidence_event = _make_calendar(
        [
            {"date": "2025-03-07", "open": "09:30", "close": "16:00"},
            {"date": "2025-03-10", "open": "09:30", "close": "16:00"},
        ],
        "2025-03-07",
        "2025-03-10",
    )
    tampered_evidence = dict(evidence_event)
    tampered_evidence["event_hash"] = "d" * 64

    with pytest.raises(CalendarAuthorityError, match="calendar_reference_integrity_failed"):
        CalendarAuthority(
            manifest=manifest,
            revisions=[revision],
            sessions=sessions,
            supporting_objects=[("EvidenceEvent", tampered_evidence)],
        )


def test_each_session_uses_the_revision_effective_on_its_date() -> None:
    rows = [
        {"date": "2025-03-07", "open": "09:30", "close": "16:00"},
        {"date": "2025-03-10", "open": "09:30", "close": "16:00"},
    ]
    _, manifest, revision_one, sessions, evidence_event = _make_calendar(
        rows, "2025-03-07", "2025-03-10"
    )
    revision_two = dict(revision_one)
    revision_two.update(
        {
            "id": _uuid(4),
            "created_at": "2025-03-08T00:00:00Z",
            "revision_number": 2,
            "effective_session": "2025-03-10",
            "reason": "Synthetic fixture revision for the second scheduled session.",
        }
    )
    session_rows = [dict(row) for row in sessions]
    session_rows[1]["calendar_revision_ref"] = {
        "target_schema_name": "qc2.time_operation.CalendarRevision.v1",
        "target_id": revision_two["id"],
    }

    authority = CalendarAuthority(
        manifest=manifest,
        revisions=[revision_one, revision_two],
        sessions=session_rows,
        supporting_objects=[("EvidenceEvent", evidence_event)],
    )

    assert authority.scheduled_sessions("2025-03-07", "2025-03-10") == (
        "2025-03-07",
        "2025-03-10",
    )


def test_holiday_and_exceptional_closure_are_closed_not_missing() -> None:
    holiday_calendar, _, _, _, _ = _make_calendar(
        [
            {"date": "2025-07-03", "open": "09:30", "close": "13:00"},
            {"date": "2025-07-07", "open": "09:30", "close": "16:00"},
        ],
        "2025-07-03",
        "2025-07-07",
    )
    assert holiday_calendar.phase_at("2025-07-04T14:00:00Z").phase == "CLOSED"

    exceptional_calendar, _, _, _, _ = _make_calendar(
        [
            {"date": "2026-01-09", "open": "09:30", "close": "16:00"},
            {"date": "2026-01-13", "open": "09:30", "close": "16:00"},
        ],
        "2026-01-09",
        "2026-01-13",
    )
    assert exceptional_calendar.phase_at("2026-01-12T15:00:00Z").phase == "CLOSED"
    assert exceptional_calendar.next_session("2026-01-09") == "2026-01-13"


def test_phase_and_deadline_use_early_close_not_a_fixed_close_time() -> None:
    authority, _, _, _, _ = _make_calendar(
        [
            {"date": "2025-07-03", "open": "09:30", "close": "13:00"},
            {"date": "2025-07-07", "open": "09:30", "close": "16:00"},
        ],
        "2025-07-03",
        "2025-07-07",
    )

    assert authority.phase_at("2025-07-03T16:59:00Z").phase == "REGULAR"
    assert authority.phase_at("2025-07-03T17:00:00Z").phase == "POST_CLOSE"
    assert authority.deadline_at("2025-07-03", "CLOSE") == "2025-07-03T17:00:00Z"


def test_next_session_follows_calendar_and_missing_range_is_unavailable() -> None:
    authority, _, _, _, _ = _make_calendar(
        [
            {"date": "2025-03-07", "open": "09:30", "close": "16:00"},
            {"date": "2025-03-10", "open": "09:30", "close": "16:00"},
        ],
        "2025-03-07",
        "2025-03-10",
    )

    assert authority.next_session("2025-03-07") == "2025-03-10"
    assert authority.phase_at("2025-03-11T14:00:00Z").reason_code == "calendar_expired"
    with pytest.raises(CalendarUnavailable, match="calendar_range_unavailable"):
        authority.scheduled_sessions("2025-03-07", "2025-03-11")
    with pytest.raises(CalendarUnavailable, match="calendar_range_unavailable"):
        authority.next_session("2025-03-10")


def test_deadline_gate_allows_only_a_certain_pre_deadline_clock() -> None:
    authority, _, _, _, _ = _make_calendar(
        [
            {"date": "2025-03-07", "open": "09:30", "close": "16:00"},
            {"date": "2025-03-10", "open": "09:30", "close": "16:00"},
        ],
        "2025-03-07",
        "2025-03-10",
    )
    _, before = _clock("2025-03-07T14:00:00Z")
    _, near = _clock("2025-03-07T14:29:59.950Z", assessment_number=21)

    assert before.status == "TRUSTED"
    assert authority.deadline_gate(session_id="2025-03-07", boundary="OPEN", clock=before).allowed
    uncertain = authority.deadline_gate(session_id="2025-03-07", boundary="OPEN", clock=near)
    assert not uncertain.allowed
    assert uncertain.reason_code == "deadline_uncertain"


def test_backward_jump_is_latched_and_blocks_deadline_sensitive_action() -> None:
    authority, _, _, _, _ = _make_calendar(
        [
            {"date": "2025-03-07", "open": "09:30", "close": "16:00"},
            {"date": "2025-03-10", "open": "09:30", "close": "16:00"},
        ],
        "2025-03-07",
        "2025-03-10",
    )
    monitor = ClockMonitor(max_uncertainty_ms=250)
    first = _dt("2025-03-07T14:00:00Z")
    monitor.assess(
        ClockReading(first, first, first, 0, 100),
        assessment_id=_uuid(30),
        created_at="2025-03-07T14:00:00Z",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    second = _dt("2025-03-07T14:00:01Z")
    jumped = monitor.assess(
        ClockReading(
            observed_at=second,
            trusted_time_at=second,
            wall_clock_at=_dt("2025-03-07T14:00:00.500Z"),
            monotonic_elapsed_ms=1000,
            uncertainty_ms=100,
        ),
        assessment_id=_uuid(31),
        created_at="2025-03-07T14:00:01Z",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    recovered = monitor.assess(
        ClockReading(second, second, second, 1000, 100),
        assessment_id=_uuid(32),
        created_at="2025-03-07T14:00:02Z",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )

    assert jumped.status == "BACKWARD_JUMP"
    assert recovered.status == "BACKWARD_JUMP"
    decision = authority.deadline_gate(session_id="2025-03-07", boundary="OPEN", clock=jumped)
    assert not decision.allowed
    assert decision.reason_code == "clock_backward_jump"


def test_missing_clock_limit_and_expired_calendar_both_block_deadlines() -> None:
    authority, _, _, _, _ = _make_calendar(
        [
            {"date": "2025-03-07", "open": "09:30", "close": "16:00"},
            {"date": "2025-03-10", "open": "09:30", "close": "16:00"},
        ],
        "2025-03-07",
        "2025-03-10",
    )
    _, unbounded = _clock(
        "2025-03-07T14:00:00Z",
        assessment_number=40,
        max_uncertainty_ms=None,
    )
    assert unbounded.status == "UNAVAILABLE"
    assert not authority.deadline_gate(
        session_id="2025-03-07", boundary="OPEN", clock=unbounded
    ).allowed

    _, trusted_after_expiry = _clock("2025-03-11T14:00:00Z", assessment_number=41)
    expired = authority.deadline_gate(
        session_id="2025-03-10", boundary="CLOSE", clock=trusted_after_expiry
    )
    assert not expired.allowed
    assert expired.reason_code == "calendar_expired"


def test_uncertainty_over_policy_limit_is_not_trusted() -> None:
    _, outcome = _clock(
        "2025-03-07T14:00:00Z",
        max_uncertainty_ms=50,
        uncertainty_ms=100,
    )

    assert outcome.status == "UNCERTAIN"
    assert outcome.reason_code == "clock_uncertainty_exceeds_limit"


def test_provider_snapshot_builder_rejects_mismatched_boundaries() -> None:
    sessions = AlpacaCalendarAdapter().normalize_rows(
        [{"date": "2025-03-07", "open": "09:30", "close": "16:00"}],
        valid_from="2025-03-07",
        valid_through="2025-03-07",
    )
    with pytest.raises(CalendarAuthorityError, match="calendar_manifest_bounds_mismatch"):
        build_calendar_records(
            sessions,
            calendar_id=_uuid(50),
            revision_id=_uuid(51),
            calendar_version=1,
            revision_number=1,
            valid_from="2025-03-07",
            valid_through="2025-03-10",
            effective_session="2025-03-07",
            revision_reason="Synthetic fixture revision.",
            created_at="2025-01-01T00:00:00Z",
            evidence_class="SYNTHETIC_FIXTURE",
            environment_namespace="test",
            source_evidence_ref={
                "target_schema_name": EVIDENCE_SCHEMA,
                "target_id": _uuid(52),
                "content_hash": "a" * 64,
            },
        )
