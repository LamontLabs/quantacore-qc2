from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from typing import Any

import pytest

from qc2_contracts.runtime import canonical_content_hash, verify_content_hash
from qc2_strategy import (
    AllocationContext,
    CompletedDailyBar,
    ExitSignal,
    FillClassification,
    InstrumentTradingEligibility,
    PositionSnapshot,
    ProposedActionKind,
    StrategyCandidate,
    assess_activation_readiness,
    assess_daily_exit,
    build_allocation_plan,
    classify_fill_feedback,
    fixture_profiles,
    prediction_to_candidate,
)


def _fixture(name: str = "test_only_micro_example"):
    return next(profile for profile in fixture_profiles() if profile.name == name)


def _candidate(
    prediction_id: str,
    instrument_id: str,
    rank: int | None,
    close: str = "100.00",
    *,
    reference_kind: str = "PREDICTION_SESSION_DAILY_CLOSE",
    disposition: str = "SCORED",
) -> StrategyCandidate:
    return StrategyCandidate(
        prediction_id=prediction_id,
        instrument_id=instrument_id,
        asset_class="US_COMMON_EQUITY",
        session_id="2026-09-01",
        rank=rank,
        disposition=disposition,
        reference_kind=reference_kind,
        reference_price=Decimal(close),
        currency="USD",
    )


def _context(**changes: Any) -> AllocationContext:
    values: dict[str, Any] = {
        "decision_session": "2026-09-01",
        "target_execution_session": "2026-09-02",
        "execution_episode_hash": "e" * 64,
        "execution_episode_verified": True,
        "is_next_exchange_session": True,
        "cash_balance": Decimal("1200.00"),
        "active_cash_reservations": Decimal("0"),
        "position_gross_exposure": Decimal("0"),
        "active_entry_gross_reservations": Decimal("0"),
        "current_position_count": 0,
        "active_entry_reservation_count": 0,
        "occupied_instrument_ids": frozenset(),
        "sessions_since_exit": (),
        "cooldown_history_complete": True,
        "prior_completed_session_volume": (
            ("instrument-1", 100),
            ("instrument-2", 200),
        ),
        "daily_loss_consumed": Decimal("0"),
        "reconciliation_current": True,
        "exit_actions_resolved": True,
        "external_activity_unreconciled": False,
        "day_limit_capability_verified": True,
        "regular_session_window_verified": True,
        "price_tick_verified": True,
        "price_tick": Decimal("0.01"),
    }
    values.update(changes)
    return AllocationContext(**values)


def _prediction_payload(reference_kind: str = "PREDICTION_SESSION_DAILY_CLOSE"):
    profile_hash = sha256(b"prediction-fixture").hexdigest()

    def ref(schema_name: str, number: int, *, content_hash: str | None = None):
        result = {
            "target_schema_name": schema_name,
            "target_id": f"018f0000-0000-7000-8000-{number:012d}",
        }
        if content_hash is not None:
            result["content_hash"] = content_hash
        return result

    payload = {
        "schema_name": "qc2.models_prediction.Prediction.v1",
        "schema_version": "1.0",
        "id": "018f0000-0000-7000-8000-000000000501",
        "created_at": "2026-09-01T21:00:00Z",
        "owning_authority": "prediction",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        "content_hash": "0" * 64,
        "run_ref": ref("qc2.models_prediction.PredictionRun.v1", 502),
        "session_id": "2026-09-01",
        "instrument_ref": ref("qc2.identity_market.Instrument.v1", 503),
        "reference_kind": reference_kind,
        "reference_price": "100.00",
        "horizon_label_refs": [],
        "head_output_refs": [],
        "feature_snapshot_ref": ref(
            "qc2.scientific_definitions.FeatureSnapshot.v1",
            504,
            content_hash=profile_hash,
        ),
        "protocol_result_refs": [],
        "score_manifest_ref": ref(
            "qc2.scientific_definitions.ScoreManifest.v1",
            505,
            content_hash=profile_hash,
        ),
        "score": "75.000000",
        "rank": 1,
        "disposition": "SCORED",
        "unscorable_reason": None,
        "model_ref": ref(
            "qc2.models_prediction.ModelManifest.v1",
            506,
            content_hash=profile_hash,
        ),
        "learned_memory_refs": [],
        "epoch_ref": ref(
            "qc2.validation.ValidationEpoch.v1",
            507,
            content_hash=profile_hash,
        ),
    }
    payload["content_hash"] = canonical_content_hash("Prediction", payload)
    return payload


def test_fixture_contracts_are_valid_but_never_activation_evidence():
    profiles = fixture_profiles()
    assert {profile.name for profile in profiles} == {
        "test_only_micro_example",
        "test_only_owner_cap_stress",
    }
    for profile in profiles:
        verify_content_hash("StrategyManifest", profile.strategy_manifest)
        verify_content_hash("CapitalPolicy", profile.capital_policy)
        called = []
        assessment = assess_activation_readiness(
            profile.strategy_manifest,
            profile.capital_policy,
            profile.rules,
            verify_owner_approval=lambda *_: called.append("owner") or True,
            verify_calibration=lambda *_: called.append("calibration") or True,
        )
        assert not assessment.eligible_for_activation
        assert assessment.reason_codes == ("FIXTURE_OR_NONPRODUCTION_INPUT",)
        assert called == []


def test_sealed_prediction_projection_requires_seal_and_eligible_us_equity():
    prediction = _prediction_payload()
    eligibility = InstrumentTradingEligibility(
        instrument_id=prediction["instrument_ref"]["target_id"],
        session_id=prediction["session_id"],
        classification="US_COMMON_EQUITY",
        classification_verified=True,
        currency="USD",
        symbol_mapping_verified=True,
    )
    candidate = prediction_to_candidate(
        prediction,
        verify_sealed_prediction=lambda item: item["id"] == prediction["id"],
        resolve_trading_eligibility=lambda *_: eligibility,
    )
    assert candidate.rank == 1
    assert candidate.reference_price == Decimal("100.00")
    assert candidate.asset_class == "US_COMMON_EQUITY"

    with pytest.raises(ValueError, match="sealed prediction set"):
        prediction_to_candidate(
            prediction,
            verify_sealed_prediction=lambda _: False,
            resolve_trading_eligibility=lambda *_: eligibility,
        )
    with pytest.raises(ValueError, match="eligibility"):
        prediction_to_candidate(
            prediction,
            verify_sealed_prediction=lambda _: True,
            resolve_trading_eligibility=lambda *_: replace(
                eligibility, classification_verified=False
            ),
        )


def test_allocation_is_deterministic_long_only_and_uses_sealed_close_price():
    profile = _fixture()
    candidates = (
        _candidate("prediction-1", "instrument-1", 1, "100.00"),
        _candidate("prediction-2", "instrument-2", 2, "50.00"),
    )
    first = build_allocation_plan(
        candidates,
        profile.strategy_manifest,
        profile.capital_policy,
        profile.rules,
        _context(),
    )
    second = build_allocation_plan(
        tuple(reversed(candidates)),
        profile.strategy_manifest,
        profile.capital_policy,
        profile.rules,
        _context(),
    )
    other_episode = build_allocation_plan(
        candidates,
        profile.strategy_manifest,
        profile.capital_policy,
        profile.rules,
        _context(execution_episode_hash="f" * 64),
    )

    assert first == second
    assert first.input_hash != other_episode.input_hash
    assert first.reservations[0].reservation_key != other_episode.reservations[0].reservation_key
    assert first.plan_hash
    assert first.input_hash
    assert first.submission_authorized is False
    assert len(first.proposed_actions) == 2
    action = first.proposed_actions[0]
    assert action.action_kind is ProposedActionKind.OPEN_LONG
    assert action.side == "BUY"
    assert action.account_mode == "PAPER"
    assert action.execution_episode_hash == "e" * 64
    assert action.order_type == "LIMIT"
    assert action.time_in_force == "DAY"
    assert action.session_restriction == "REGULAR_SESSION_ONLY"
    assert action.extended_hours is False
    assert action.reference_kind == "PREDICTION_SESSION_DAILY_CLOSE"
    assert action.sealed_reference_close == Decimal("100.00")
    assert action.price_cap_ceiling == Decimal("102.00000")
    assert action.limit_price <= action.price_cap_ceiling
    assert action.quantity_whole_shares == 5
    assert action.reservation.reserved_cash <= Decimal("700.00")
    assert all(action.side == "BUY" for action in first.proposed_actions)
    assert sum(r.reserved_cash for r in first.reservations) <= Decimal("700.00")
    assert not hasattr(candidates[0], "next_open")


def test_future_open_proxy_is_rejected_and_owned_instrument_cannot_be_pyramided():
    profile = _fixture()
    future_open = _candidate(
        "prediction-open",
        "instrument-1",
        1,
        reference_kind="NEXT_SESSION_DAILY_OPEN_PROXY",
    )
    future_open_plan = build_allocation_plan(
        (future_open,),
        profile.strategy_manifest,
        profile.capital_policy,
        profile.rules,
        _context(prior_completed_session_volume=(("instrument-1", 100),)),
    )
    assert not future_open_plan.proposed_actions
    assert "REFERENCE_IS_NOT_SEALED_SESSION_CLOSE" in future_open_plan.decisions[0].reason_codes

    existing_position = _candidate("prediction-owned", "instrument-1", 1)
    no_pyramid_plan = build_allocation_plan(
        (existing_position,),
        profile.strategy_manifest,
        profile.capital_policy,
        profile.rules,
        _context(
            occupied_instrument_ids=frozenset({"instrument-1"}),
            prior_completed_session_volume=(("instrument-1", 100),),
        ),
    )
    assert not no_pyramid_plan.proposed_actions
    assert "POSITION_OR_RESERVATION_ALREADY_EXISTS" in no_pyramid_plan.decisions[0].reason_codes


def test_strategy_request_cannot_widen_owner_position_and_fraction_caps():
    profile = _fixture("test_only_owner_cap_stress")
    candidate = _candidate("prediction-cap", "instrument-1", 1, "50.00")
    plan = build_allocation_plan(
        (candidate,),
        profile.strategy_manifest,
        profile.capital_policy,
        profile.rules,
        _context(
            cash_balance=Decimal("1000"),
            prior_completed_session_volume=(("instrument-1", 1000),),
        ),
    )
    assert len(plan.reservations) == 1
    reservation = plan.reservations[0]
    assert reservation.reserved_cash <= Decimal("100.00")
    assert reservation.quantity_whole_shares == 1


def test_unverified_order_capability_and_daily_loss_block_new_entries():
    profile = _fixture()
    candidate = _candidate("prediction-blocked", "instrument-1", 1)
    for context, expected in (
        (_context(day_limit_capability_verified=False), "DAY_LIMIT_CAPABILITY_NOT_VERIFIED"),
        (_context(daily_loss_consumed=Decimal("300")), "DAILY_LOSS_LIMIT_REACHED"),
        (_context(execution_episode_verified=False), "SEALED_PAPER_EXECUTION_EPISODE_NOT_VERIFIED"),
        (_context(price_tick_verified=False), "PRICE_TICK_NOT_VERIFIED"),
    ):
        plan = build_allocation_plan(
            (candidate,),
            profile.strategy_manifest,
            profile.capital_policy,
            profile.rules,
            context,
        )
        assert not plan.proposed_actions
        assert expected in plan.decisions[0].reason_codes


def test_incomplete_cooldown_history_or_unresolved_exits_block_entries():
    profile = _fixture()
    candidate = _candidate("prediction-wait", "instrument-1", 1)
    for context, expected in (
        (_context(cooldown_history_complete=False), "COOLDOWN_HISTORY_NOT_COMPLETE"),
        (_context(exit_actions_resolved=False), "PRIOR_EXIT_ACTIONS_NOT_RESOLVED"),
    ):
        plan = build_allocation_plan(
            (candidate,),
            profile.strategy_manifest,
            profile.capital_policy,
            profile.rules,
            context,
        )
        assert not plan.proposed_actions
        assert expected in plan.decisions[0].reason_codes


def test_reentry_cooldown_counts_exchange_sessions_and_honors_unreleased_reservations():
    profile = _fixture()
    candidate = _candidate("prediction-cooldown", "instrument-1", 1)
    blocked = build_allocation_plan(
        (candidate,),
        profile.strategy_manifest,
        profile.capital_policy,
        profile.rules,
        _context(sessions_since_exit=(("instrument-1", 2),)),
    )
    eligible = build_allocation_plan(
        (candidate,),
        profile.strategy_manifest,
        profile.capital_policy,
        profile.rules,
        _context(sessions_since_exit=(("instrument-1", 3),)),
    )
    assert "REENTRY_COOLDOWN_ACTIVE" in blocked.decisions[0].reason_codes
    assert len(eligible.proposed_actions) == 1


def test_same_bar_stop_and_target_is_ambiguous_and_never_a_fill():
    profile = _fixture()
    position = PositionSnapshot(
        instrument_id="instrument-1",
        owned_shares=Decimal("5"),
        entry_price=Decimal("100"),
        entry_session_ordinal=10,
        completed_sessions_held=1,
        prior_peak_price=None,
    )
    bar = CompletedDailyBar(
        instrument_id="instrument-1",
        session_id="2026-09-02",
        session_ordinal=11,
        open_price=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("94"),
        close_price=Decimal("101"),
        complete=True,
    )
    assessment = assess_daily_exit(position, bar, profile.rules)
    assert assessment.signal is ExitSignal.INTRADAY_PATH_AMBIGUOUS
    assert assessment.possible_triggers == ("STOP", "TARGET")
    assert assessment.conservative_scenario_return == Decimal("-0.050")
    assert assessment.fill_price is None


def test_stop_and_time_exits_are_signals_not_claimed_fills():
    profile = _fixture()
    position = PositionSnapshot(
        instrument_id="instrument-1",
        owned_shares=Decimal("2.5"),
        entry_price=Decimal("100"),
        entry_session_ordinal=10,
        completed_sessions_held=5,
        prior_peak_price=None,
    )
    bar = CompletedDailyBar(
        instrument_id="instrument-1",
        session_id="2026-09-02",
        session_ordinal=11,
        open_price=Decimal("100"),
        high_price=Decimal("105"),
        low_price=Decimal("94"),
        close_price=Decimal("98"),
        complete=True,
    )
    assessment = assess_daily_exit(position, bar, profile.rules)
    assert assessment.signal is ExitSignal.STOP_LEVEL_CROSSED
    assert assessment.threshold_price == Decimal("95.000")
    assert assessment.fill_price is None

    time_rules = replace(
        profile.rules,
        stop_loss_fraction=None,
        target_gain_fraction=None,
    )
    time_exit = assess_daily_exit(position, bar, time_rules)
    assert time_exit.signal is ExitSignal.TIME_EXIT_DUE
    assert time_exit.fill_price is None


def test_missed_fill_feedback_does_not_change_scientific_outcome():
    prediction = _prediction_payload()
    scientific_outcome = ("prediction-1", "SUCCESS")
    original_prediction = dict(prediction)
    original_outcome = scientific_outcome

    feedback = classify_fill_feedback(requested_shares=4, filled_shares=0)

    assert feedback.classification is FillClassification.NO_FILL
    assert feedback.unfilled_shares == 4
    assert prediction == original_prediction
    assert scientific_outcome == original_outcome
