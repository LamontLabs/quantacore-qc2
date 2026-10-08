from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from qc2_contracts.runtime import new_uuidv7, verify_content_hash
from qc2_science import (
    ContractRef,
    DailyLabelBar,
    LabelDefinitionSpec,
    LabelInput,
    LabelInputError,
    ProbabilityTargetUnavailable,
    ProductionActivationDenied,
    PRIMARY_LABEL_KEY,
    SUPPORTED_HORIZONS,
    build_label_definition_specs,
    materialize_label_registry,
    require_probability_target,
    resolve_label_outcome,
)

UTC = timezone.utc
CALENDAR = tuple(
    date.fromisoformat(session)
    for session in (
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
    )
)
CREATED_FULL = datetime(2026, 5, 20, 12, tzinfo=UTC)
REGISTRY_CREATED = datetime(2026, 5, 1, 12, tzinfo=UTC)


def _ref(schema_name: str) -> ContractRef:
    return ContractRef(schema_name, new_uuidv7(), "a" * 64)


def _bar(
    offset: int,
    values: tuple[int, int, int, int] | None = None,
    *,
    share_basis_key: str = "split-basis-2026-05",
    adjustment_ref: ContractRef | None = None,
) -> DailyLabelBar:
    defaults = {
        1: (104, 115, 94, 101),
        2: (100, 115, 90, 99),
        3: (99, 110, 96, 100),
        4: (101, 111, 93, 100),
        5: (100, 110, 97, 101),
    }
    open_price, high_price, low_price, close_price = values or defaults.get(
        offset, (100, 105, 95, 100)
    )
    session = CALENDAR[offset]
    finalized_at = datetime(2026, 5, session.day, 22, tzinfo=UTC)
    return DailyLabelBar(
        session_id=session,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        source_ref=_ref("qc2.identity_market.DailyBar.v1"),
        instrument_ref=INSTRUMENT_REF,
        adjustment_ref=adjustment_ref or ADJUSTMENT_REF,
        share_basis_key=share_basis_key,
        finalized_at=finalized_at,
    )


INSTRUMENT_REF = _ref("qc2.identity_market.Instrument.v1")
ADJUSTMENT_REF = _ref("qc2.identity_market.AdjustmentManifest.v1")
REFERENCE_BAR = DailyLabelBar(
    session_id=CALENDAR[0],
    open_price=100,
    high_price=102,
    low_price=99,
    close_price=100,
    source_ref=_ref("qc2.identity_market.DailyBar.v1"),
    instrument_ref=INSTRUMENT_REF,
    adjustment_ref=ADJUSTMENT_REF,
    share_basis_key="split-basis-2026-05",
    finalized_at=datetime(2026, 5, 4, 22, tzinfo=UTC),
)


def _input(
    *,
    offsets: tuple[int, ...] = tuple(range(1, 11)),
    observation_offset: int = 10,
    flat: bool = False,
    corporate_action_status: str = "FINALIZED",
    corporate_action_finalized_at: datetime | None = datetime(2026, 5, 19, 21, tzinfo=UTC),
    data_finalization_complete_at: datetime | None = datetime(2026, 5, 19, 22, tzinfo=UTC),
    label_release_transaction_complete_at: datetime | None = datetime(
        2026, 5, 19, 23, tzinfo=UTC
    ),
    terminal_event_session: date | None = None,
    future_bars: tuple[DailyLabelBar, ...] | None = None,
) -> LabelInput:
    selected_bars = future_bars
    if selected_bars is None:
        selected_bars = tuple(
            _bar(
                offset,
                (100, 100, 100, 100) if flat else None,
            )
            for offset in offsets
        )
    return LabelInput(
        prediction_bar=REFERENCE_BAR,
        calendar_ref=_ref("qc2.time_operation.CalendarManifest.v1"),
        calendar_sessions=CALENDAR,
        observation_session=CALENDAR[observation_offset],
        future_bars=selected_bars,
        corporate_action_status=corporate_action_status,
        corporate_action_finalized_at=corporate_action_finalized_at,
        data_finalization_complete_at=data_finalization_complete_at,
        label_release_transaction_complete_at=label_release_transaction_complete_at,
        terminal_event_session=terminal_event_session,
    )


def _registry_ids():
    keys = {spec.stable_key for spec in build_label_definition_specs()}
    return {key: new_uuidv7() for key in keys}


def _registry(key: str | None = None, threshold: str | None = None):
    thresholds = {} if threshold is None else {key: threshold}
    return materialize_label_registry(
        definition_ids=_registry_ids(),
        registry_id=new_uuidv7(),
        created_at=REGISTRY_CREATED,
        effective_from=CALENDAR[0],
        thresholds=thresholds,
    )


def _resolve(
    key: str,
    label_input: LabelInput,
    *,
    threshold: str | None = None,
    created_at: datetime = CREATED_FULL,
):
    return resolve_label_outcome(
        _registry(key, threshold),
        key,
        label_input,
        created_at=created_at,
    )


def test_label_registry_has_primary_and_secondary_horizons_and_valid_contracts():
    specs = build_label_definition_specs()
    event_specs = [item for item in specs if item.target_event in {"EXPANSION_RUNNER", "SESSION_MONSTER"}]
    assert {item.horizon_sessions for item in event_specs} == set(SUPPORTED_HORIZONS)
    assert next(item for item in specs if item.stable_key == PRIMARY_LABEL_KEY).horizon_sessions == 5
    assert all(item.threshold is None for item in event_specs)

    bundle = materialize_label_registry(
        definition_ids=_registry_ids(),
        registry_id=new_uuidv7(),
        created_at=REGISTRY_CREATED,
        effective_from=CALENDAR[0],
    )
    verify_content_hash("LabelRegistry", bundle.registry_contract)
    assert bundle.registry_contract["primary_label_ref"]["target_id"] == (
        bundle.definition_contracts[PRIMARY_LABEL_KEY]["id"]
    )
    assert all(record["environment_namespace"] == "test" for record in bundle.definition_contracts.values())
    assert all(record["threshold"] is None for record in bundle.definition_contracts.values())


def test_unresolved_thresholds_block_production_registration():
    with pytest.raises(ProductionActivationDenied, match="unresolved thresholds"):
        materialize_label_registry(
            definition_ids=_registry_ids(),
            registry_id=new_uuidv7(),
            created_at=REGISTRY_CREATED,
            effective_from=CALENDAR[0],
            environment_namespace="production",
            evidence_class="FORWARD_SEALED",
        )


def test_actual_fill_and_next_open_proxy_cannot_be_label_reference_prices():
    for price_reference in (
        "ACTUAL_PAPER_FILL",
        "NEXT_SESSION_DAILY_OPEN_PROXY",
    ):
        with pytest.raises(LabelInputError, match="requires price_reference"):
            LabelDefinitionSpec(
                stable_key="expansion_runner_5_session",
                target_event="EXPANSION_RUNNER",
                horizon_sessions=5,
                price_reference=price_reference,
                threshold=None,
                threshold_unit="fractional_return",
                maturity_rule="frozen calendar",
                release_policy="mature only",
            )


def test_early_threshold_hit_does_not_release_a_full_horizon_label():
    label_input = _input(
        offsets=(1,),
        observation_offset=1,
        corporate_action_finalized_at=datetime(2026, 5, 5, 23, tzinfo=UTC),
        data_finalization_complete_at=None,
        label_release_transaction_complete_at=None,
    )
    outcome = _resolve(
        "expansion_runner_5_session",
        label_input,
        threshold="0.150000000000",
        created_at=datetime(2026, 5, 6, 12, tzinfo=UTC),
    )

    assert outcome.outcome_state == "PENDING_MATURITY"
    assert outcome.target_value is None
    assert outcome.available_for_learning_at is None
    assert outcome.metrics["max_high_return"] is None
    assert outcome.expected_session_ids[-1] == CALENDAR[5]
    with pytest.raises(ProbabilityTargetUnavailable):
        require_probability_target(outcome)


def test_missing_fifth_session_does_not_extend_horizon_to_a_later_bar():
    label_input = _input(
        offsets=(),
        observation_offset=6,
        future_bars=tuple(_bar(offset) for offset in (1, 2, 3, 4, 6)),
    )
    outcome = _resolve(
        "expansion_runner_5_session",
        label_input,
        threshold="0.150000000000",
    )

    assert outcome.outcome_state == "PARTIALLY_RESOLVABLE"
    assert outcome.expected_session_ids == CALENDAR[1:6]
    assert outcome.expected_session_ids[-1] == CALENDAR[5]
    assert outcome.metrics["endpoint_return"] is None
    assert outcome.metrics["opening_gap_return"] == Decimal("0.04")
    assert outcome.available_for_learning_at is None
    assert {item.reason_code for item in outcome.field_validity if item.status == "UNRESOLVED"} == {
        "missing_horizon_session_bar"
    }
    with pytest.raises(ProbabilityTargetUnavailable):
        require_probability_target(outcome)


def test_signed_mae_unclamped_extrema_split_basis_and_earliest_tie_peak():
    outcome = _resolve(
        "expansion_runner_5_session",
        _input(),
        threshold="0.150000000000",
    )

    assert outcome.outcome_state == "RESOLVED"
    assert outcome.metrics["max_high_return"] == Decimal("0.15")
    assert outcome.metrics["min_low_return"] == Decimal("-0.10")
    assert outcome.metrics["mfe"] == Decimal("0.15")
    assert outcome.metrics["mae"] == Decimal("-0.10")
    assert outcome.metrics["mae"] <= 0
    assert outcome.metrics["max_high_session"] == CALENDAR[1].isoformat()
    assert outcome.metrics["max_high_session_offset"] == 1
    assert outcome.metrics["next_open_reference_price"] == Decimal(104)
    assert outcome.metrics["next_open_proxy_max_high_return"] == Decimal("0.105769230769")
    assert outcome.metrics["max_high_return"] != outcome.metrics["next_open_proxy_max_high_return"]
    assert outcome.target_value is True
    assert require_probability_target(outcome) is True
    assert outcome.available_for_learning_at == datetime(2026, 5, 19, 23, tzinfo=UTC)

    mismatched = tuple(
        _bar(
            offset,
            adjustment_ref=_ref("qc2.identity_market.AdjustmentManifest.v1"),
        )
        if offset == 2
        else _bar(offset)
        for offset in range(1, 11)
    )
    with pytest.raises(LabelInputError, match="same adjustment manifest"):
        _input(future_bars=mismatched)


def test_zero_event_is_negative_only_when_the_threshold_is_defined():
    outcome = _resolve(
        "expansion_runner_5_session",
        _input(flat=True),
        threshold="0.010000000000",
    )

    assert outcome.outcome_state == "RESOLVED"
    assert outcome.metrics["max_high_return"] == 0
    assert outcome.metrics["min_low_return"] == 0
    assert outcome.metrics["mfe"] == 0
    assert outcome.metrics["mae"] == 0
    assert outcome.target_status == "AVAILABLE"
    assert outcome.target_value is False
    assert require_probability_target(outcome) is False


def test_session_monster_uses_previous_close_and_keeps_gap_distinct():
    outcome = _resolve(
        "session_monster_5_session",
        _input(),
        threshold="0.150000000000",
    )

    first = outcome.session_monster_measurements[0]
    second = outcome.session_monster_measurements[1]
    assert first.monster_return == Decimal("0.15")
    assert first.opening_gap_return == Decimal("0.04")
    assert first.open_to_high_return == Decimal("0.105769230769")
    assert second.monster_return == Decimal("0.138613861386")
    assert second.monster_return != second.open_to_high_return
    assert outcome.target_value is True


@pytest.mark.parametrize(
    "key",
    (
        "continuation_5_session",
        "failure_5_session",
        "time_to_expansion_5_session",
    ),
)
def test_undefined_target_semantics_cannot_produce_probability_labels(key: str):
    outcome = _resolve(
        key,
        _input(),
    )

    assert outcome.outcome_state == "RESOLVED"
    assert outcome.target_status == "UNAVAILABLE_LABEL"
    assert outcome.target_value is None
    assert outcome.available_for_learning_at is None
    with pytest.raises(ProbabilityTargetUnavailable, match="UNAVAILABLE_LABEL"):
        require_probability_target(outcome)


def test_missing_event_threshold_is_not_encoded_as_zero_or_negative():
    outcome = _resolve(
        "expansion_runner_5_session",
        _input(),
    )

    assert outcome.outcome_state == "RESOLVED"
    assert outcome.target_status == "UNAVAILABLE_THRESHOLD"
    assert outcome.target_value is None
    assert outcome.available_for_learning_at is None
    with pytest.raises(ProbabilityTargetUnavailable, match="UNAVAILABLE_THRESHOLD"):
        require_probability_target(outcome)


def test_maturity_field_validity_corporate_action_and_terminal_states():
    incomplete_finalization = _input(
        data_finalization_complete_at=None,
        label_release_transaction_complete_at=None,
    )
    pending = _resolve(
        "expansion_runner_5_session",
        incomplete_finalization,
        threshold="0.150000000000",
    )
    assert pending.outcome_state == "PENDING_MATURITY"
    assert pending.available_for_learning_at is None

    review = _resolve(
        "expansion_runner_5_session",
        _input(
            corporate_action_status="REVIEW",
            corporate_action_finalized_at=None,
        ),
        threshold="0.150000000000",
    )
    assert review.outcome_state == "CORPORATE_ACTION_REVIEW"
    assert review.target_value is None

    censored = _resolve(
        "expansion_runner_5_session",
        _input(terminal_event_session=CALENDAR[2]),
        threshold="0.150000000000",
    )
    assert censored.outcome_state == "CENSORED_TERMINAL_EVENT"
    assert censored.target_value is None
    assert any(item.status == "CENSORED" for item in censored.field_validity)
    assert all(item.status in {"VALID", "CENSORED"} for item in censored.field_validity)
    with pytest.raises(ProbabilityTargetUnavailable):
        require_probability_target(censored)


def test_label_created_before_finalization_evidence_is_rejected():
    with pytest.raises(LabelInputError, match="cannot precede evidence"):
        _resolve(
            "expansion_runner_5_session",
            _input(),
            threshold="0.150000000000",
            created_at=datetime(2026, 5, 10, 12, tzinfo=UTC),
        )
