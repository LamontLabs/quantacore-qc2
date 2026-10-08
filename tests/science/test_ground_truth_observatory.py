from __future__ import annotations

import ast
import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from qc2_contracts.runtime import new_uuidv7
from qc2_science import (
    ContractRef,
    DailyLabelBar,
    GroundTruthError,
    LabelInput,
    ObservatoryCensusInput,
    ObservatoryCensusMember,
    build_label_definition_specs,
    materialize_label_registry,
    scan_runner_observatory,
)
from qc2_science.ground_truth_models import (
    GroundTruthEligibleRow,
    SymbolAssignmentEvidence,
    freeze_contract_record,
)

UTC = timezone.utc
CALENDAR = tuple(
    date.fromisoformat(value)
    for value in (
        "2026-05-04",
        "2026-05-05",
        "2026-05-06",
        "2026-05-07",
        "2026-05-08",
        "2026-05-11",
        "2026-05-12",
        "2026-05-13",
        "2026-05-14",
        "2026-05-15",
        "2026-05-18",
        "2026-05-19",
    )
)
CREATED = datetime(2026, 5, 20, 12, tzinfo=UTC)
_BAR_VALUES = {
    0: (100, 102, 98, 100),
    1: (100, 105, 97, 103),
    2: (103, 115, 100, 110),
    3: (110, 120, 105, 118),
    4: (118, 119, 112, 115),
    5: (115, 117, 110, 116),
    6: (116, 120, 112, 118),
    7: (118, 132, 116, 127),
    8: (127, 130, 121, 125),
    9: (125, 129, 122, 126),
    10: (126, 128, 120, 124),
    11: (124, 127, 121, 125),
}


def _ref(schema_name: str) -> ContractRef:
    return ContractRef(schema_name, new_uuidv7(), "a" * 64)


def _bar(
    index: int,
    instrument_ref: ContractRef,
    adjustment_ref: ContractRef,
) -> DailyLabelBar:
    open_price, high_price, low_price, close_price = _BAR_VALUES[index]
    session = CALENDAR[index]
    return DailyLabelBar(
        session_id=session,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        source_ref=_ref("qc2.identity_market.DailyBar.v1"),
        instrument_ref=instrument_ref,
        adjustment_ref=adjustment_ref,
        share_basis_key="basis-2026-05",
        finalized_at=datetime(session.year, session.month, session.day, 22, tzinfo=UTC),
    )


def _label_input(
    instrument_ref: ContractRef,
    *,
    anchor_index: int = 0,
    future_indices: tuple[int, ...] | None = None,
) -> LabelInput:
    adjustment_ref = _ref("qc2.identity_market.AdjustmentManifest.v1")
    prediction = _bar(anchor_index, instrument_ref, adjustment_ref)
    indices = future_indices or tuple(range(anchor_index + 1, anchor_index + 6))
    return LabelInput(
        prediction_bar=prediction,
        calendar_ref=_ref("qc2.time_operation.CalendarManifest.v1"),
        calendar_sessions=CALENDAR,
        observation_session=CALENDAR[-1],
        future_bars=tuple(_bar(index, instrument_ref, adjustment_ref) for index in indices),
        corporate_action_status="FINALIZED",
        corporate_action_finalized_at=datetime(2026, 5, 19, 10, tzinfo=UTC),
        data_finalization_complete_at=datetime(2026, 5, 19, 11, tzinfo=UTC),
        label_release_transaction_complete_at=datetime(2026, 5, 19, 12, tzinfo=UTC),
    )


def _row(
    row_key: str,
    instrument_ref: ContractRef,
    definition_key: str,
    *,
    anchor_index: int = 0,
    future_indices: tuple[int, ...] | None = None,
    label_input: LabelInput | None = None,
):
    label_input = label_input or _label_input(
        instrument_ref, anchor_index=anchor_index, future_indices=future_indices
    )
    assignment = _ref("qc2.identity_market.SymbolAssignment.v1")
    return GroundTruthEligibleRow(
        row_key=row_key,
        definition_key=definition_key,
        label_input=label_input,
        symbol_assignments=(
            SymbolAssignmentEvidence(
                assignment_ref=assignment,
                instrument_ref=instrument_ref,
                symbol="TEST",
                effective_from=CALENDAR[0] - timedelta(days=30),
            ),
        ),
    )


def _registry():
    thresholds = {
        "expansion_runner_5_session": "0.100000000000",
        "session_monster_5_session": "0.100000000000",
    }
    specs = build_label_definition_specs(thresholds)
    return materialize_label_registry(
        definition_ids={spec.stable_key: new_uuidv7() for spec in specs},
        registry_id=new_uuidv7(),
        created_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
        effective_from=CALENDAR[0],
        environment_namespace="test",
        evidence_class="SYNTHETIC_FIXTURE",
        thresholds=thresholds,
    )


def _census(session_index: int, instruments: tuple[ContractRef, ...]):
    ordered = tuple(sorted(instruments, key=lambda item: item.target_id))
    membership_material = (
        "qc2-candidate-membership-v1\n"
        + "\n".join(item.target_id for item in ordered)
    )
    return freeze_contract_record(
        "CandidateCensus",
        {
            "schema_name": "qc2.identity_market.CandidateCensus.v1",
            "schema_version": "1.0",
            "id": new_uuidv7(),
            "created_at": datetime(2026, 5, 1, 12, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
            "owning_authority": "instrument_universe",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [],
            "session_id": CALENDAR[session_index].isoformat(),
            "instrument_refs": [item.to_payload() for item in ordered],
            "cutoff": datetime(
                CALENDAR[session_index].year,
                CALENDAR[session_index].month,
                CALENDAR[session_index].day,
                12,
                tzinfo=UTC,
            ).isoformat().replace("+00:00", "Z"),
            "source_manifest_refs": [],
            "membership_hash": hashlib.sha256(
                membership_material.encode("ascii")
            ).hexdigest(),
        },
    )


def _census_input(
    session_index: int,
    instruments: tuple[ContractRef, ...],
    members: tuple[ObservatoryCensusMember, ...],
) -> ObservatoryCensusInput:
    return ObservatoryCensusInput(
        candidate_census=_census(session_index, instruments),
        members=members,
    )


def test_low_ranked_and_unpredicted_eligible_runners_are_discovered():
    registry = _registry()
    low_ranked = _ref("qc2.identity_market.Instrument.v1")
    unpredicted = _ref("qc2.identity_market.Instrument.v1")
    census = _census_input(
        0,
        (low_ranked, unpredicted),
        (
            ObservatoryCensusMember(
                low_ranked,
                "SCIENTIFICALLY_ELIGIBLE",
                (
                    _row("low-ranked-runner-expansion", low_ranked, "expansion_runner_5_session"),
                    _row("low-ranked-runner-monster", low_ranked, "session_monster_5_session"),
                ),
            ),
            ObservatoryCensusMember(
                unpredicted,
                "SCIENTIFICALLY_ELIGIBLE",
                (
                    _row("unpredicted-runner-expansion", unpredicted, "expansion_runner_5_session"),
                    _row("unpredicted-runner-monster", unpredicted, "session_monster_5_session"),
                ),
            ),
        ),
    )

    result = scan_runner_observatory(
        registry,
        (census,),
        definition_keys=("expansion_runner_5_session", "session_monster_5_session"),
        created_at=CREATED,
    )

    found_instruments = {
        item.instrument_ref.target_id
        for item in result.event_queue.items
        if item.status == "EVENT_DISCOVERED"
    }
    assert found_instruments == {low_ranked.target_id, unpredicted.target_id}
    assert len(result.runner_events) == 4
    assert {event.payload["event_type"] for event in result.runner_events} == {
        "EXPANSION_RUNNER",
        "SESSION_MONSTER",
    }
    expected_events = {
        (
            instrument_id,
            event_type,
            CALENDAR[2].isoformat(),
            CALENDAR[3].isoformat()
            if event_type == "EXPANSION_RUNNER"
            else CALENDAR[2].isoformat(),
        )
        for instrument_id in (low_ranked.target_id, unpredicted.target_id)
        for event_type in ("EXPANSION_RUNNER", "SESSION_MONSTER")
    }
    observed_events = {
        (
            event.payload["instrument_ref"]["target_id"],
            event.payload["event_type"],
            event.payload["start_session"],
            event.payload["end_session"],
        )
        for event in result.runner_events
    }
    assert observed_events == expected_events
    assert all(item.status == "EVENT_DISCOVERED" for item in result.event_queue.items)


def test_missing_census_data_is_visible_and_market_completeness_is_not_claimed():
    registry = _registry()
    eligible = _ref("qc2.identity_market.Instrument.v1")
    excluded = _ref("qc2.identity_market.Instrument.v1")
    unverified = _ref("qc2.identity_market.Instrument.v1")
    unobserved = _ref("qc2.identity_market.Instrument.v1")
    census = _census_input(
        0,
        (eligible, excluded, unverified, unobserved),
        (
            ObservatoryCensusMember(
                eligible,
                "SCIENTIFICALLY_ELIGIBLE",
                (_row("eligible-expansion-only", eligible, "expansion_runner_5_session"),),
            ),
            ObservatoryCensusMember(
                excluded,
                "SCIENTIFICALLY_EXCLUDED",
                reason_code="classification_not_eligible",
            ),
            ObservatoryCensusMember(
                unverified,
                "ELIGIBILITY_UNVERIFIED",
                reason_code="classification_missing",
            ),
        ),
    )

    result = scan_runner_observatory(
        registry,
        (census,),
        definition_keys=("expansion_runner_5_session", "session_monster_5_session"),
        created_at=CREATED,
    )

    coverage = result.coverage[0]
    assert coverage.census_member_count == 4
    assert coverage.member_record_count == 3
    assert coverage.unobserved_member_count == 1
    assert coverage.scientifically_excluded_member_count == 1
    assert coverage.eligibility_unverified_member_count == 1
    assert coverage.expected_label_scan_count == 2
    assert coverage.label_input_count == 1
    assert coverage.missing_label_input_count == 1
    assert coverage.coverage_scope == "DECLARED_CANDIDATE_CENSUS_ONLY"
    assert not coverage.market_completeness_established
    assert not result.market_completeness_established
    assert result.event_queue.content_hash
    statuses = {item.status for item in result.event_queue.items}
    assert {
        "EVENT_DISCOVERED",
        "DATA_MISSING",
        "SCIENTIFICALLY_EXCLUDED",
        "ELIGIBILITY_UNVERIFIED",
        "CENSUS_MEMBER_UNOBSERVED",
    } <= statuses
    assert any(item.instrument_ref.target_id == unobserved.target_id for item in result.event_queue.items)


def test_unscorable_rows_remain_in_the_discovery_queue():
    registry = _registry()
    instrument = _ref("qc2.identity_market.Instrument.v1")
    missing_bar = _row(
        "partial-outcome",
        instrument,
        "expansion_runner_5_session",
        future_indices=(1, 3, 4, 5),
    )
    census = _census_input(
        0,
        (instrument,),
        (
            ObservatoryCensusMember(
                instrument,
                "SCIENTIFICALLY_ELIGIBLE",
                (missing_bar,),
            ),
        ),
    )

    result = scan_runner_observatory(
        registry,
        (census,),
        definition_keys=("expansion_runner_5_session",),
        created_at=CREATED,
    )

    item = result.event_queue.items[0]
    assert item.status == "UNSCORABLE"
    assert item.outcome_ref is not None
    assert "missing_horizon_session_bar" in item.reason_codes
    assert result.coverage[0].unscorable_target_count == 1


def test_resolved_negative_is_kept_as_a_no_event_queue_item():
    registry = _registry()
    instrument = _ref("qc2.identity_market.Instrument.v1")
    flat = _label_input(instrument)
    flat = replace(
        flat,
        future_bars=tuple(
            replace(
                bar,
                open_price=100,
                high_price=102,
                low_price=98,
                close_price=100,
            )
            for bar in flat.future_bars
        ),
    )
    census = _census_input(
        0,
        (instrument,),
        (
            ObservatoryCensusMember(
                instrument,
                "SCIENTIFICALLY_ELIGIBLE",
                (
                    _row(
                        "confirmed-no-event",
                        instrument,
                        "expansion_runner_5_session",
                        label_input=flat,
                    ),
                ),
            ),
        ),
    )

    result = scan_runner_observatory(
        registry,
        (census,),
        definition_keys=("expansion_runner_5_session",),
        created_at=CREATED,
    )

    item = result.event_queue.items[0]
    assert item.status == "NO_EVENT"
    assert item.outcome_ref is not None
    assert not item.event_ids
    assert not result.runner_events


def test_overlapping_target_windows_share_a_frozen_episode_identity():
    registry = _registry()
    instrument = _ref("qc2.identity_market.Instrument.v1")
    first = _census_input(
        0,
        (instrument,),
        (
            ObservatoryCensusMember(
                instrument,
                "SCIENTIFICALLY_ELIGIBLE",
                (_row("window-one", instrument, "expansion_runner_5_session", anchor_index=0),),
            ),
        ),
    )
    second = _census_input(
        1,
        (instrument,),
        (
            ObservatoryCensusMember(
                instrument,
                "SCIENTIFICALLY_ELIGIBLE",
                (_row("window-two", instrument, "expansion_runner_5_session", anchor_index=1),),
            ),
        ),
    )

    result = scan_runner_observatory(
        registry,
        (first, second),
        definition_keys=("expansion_runner_5_session",),
        created_at=CREATED,
    )

    assert len(result.runner_events) == 2
    assert len(result.episodes) == 1
    episode = result.episodes[0]
    assert set(episode.event_ids) == {
        event.payload["id"] for event in result.runner_events
    }
    event_queue_items = [
        item for item in result.event_queue.items if item.status == "EVENT_DISCOVERED"
    ]
    assert len(event_queue_items) == 2
    assert event_queue_items[0].episode_ids == event_queue_items[1].episode_ids == (
        episode.episode_id,
    )
    assert episode.target_window_start == CALENDAR[1]
    assert episode.target_window_end == CALENDAR[6]
    assert "inclusive-transitive-overlap" in episode.episode_rule


def test_unfrozen_ancillary_label_is_queued_as_unscorable_not_as_a_failure_event():
    registry = _registry()
    instrument = _ref("qc2.identity_market.Instrument.v1")
    census = _census_input(
        0,
        (instrument,),
        (
            ObservatoryCensusMember(
                instrument,
                "SCIENTIFICALLY_ELIGIBLE",
                (_row("undefined-failure", instrument, "failure_5_session"),),
            ),
        ),
    )

    result = scan_runner_observatory(
        registry,
        (census,),
        definition_keys=("failure_5_session",),
        created_at=CREATED,
    )

    item = result.event_queue.items[0]
    assert item.status == "UNSCORABLE"
    assert item.reason_codes == ("label_semantics_not_frozen",)
    assert not result.runner_events


def test_census_membership_hash_is_verified_and_scanner_has_no_ranking_imports():
    registry = _registry()
    instrument = _ref("qc2.identity_market.Instrument.v1")
    valid = _census(0, (instrument,)).payload
    valid["membership_hash"] = "b" * 64
    invalid = freeze_contract_record("CandidateCensus", valid)
    scan_input = ObservatoryCensusInput(
        candidate_census=invalid,
        members=(
            ObservatoryCensusMember(instrument, "SCIENTIFICALLY_ELIGIBLE", ()),
        ),
    )
    with pytest.raises(GroundTruthError, match="membership_hash"):
        scan_runner_observatory(
            registry,
            (scan_input,),
            definition_keys=("expansion_runner_5_session",),
            created_at=CREATED,
        )

    module = Path(__file__).resolve().parents[2] / (
        "packages/science/src/qc2_science/ground_truth_observatory.py"
    )
    tree = ast.parse(module.read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(
        name.startswith(("qc2.models_prediction", "qc2_score", "qc2_strategy"))
        for name in imported
    )
