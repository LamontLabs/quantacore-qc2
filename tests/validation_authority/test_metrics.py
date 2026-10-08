from __future__ import annotations

from decimal import Decimal

import pytest

from qc2_validation_authority import (
    MetricEstimate,
    OutcomeObservation,
    PredictionObservation,
    ValidationAuthorityError,
    compute_session_metrics,
    mean_session_estimates,
)

SESSION = "2026-10-05"
INSTRUMENTS = tuple(f"instrument-{index:02d}" for index in range(12))
FEED_HASH = "a" * 64
LABEL_HASH = "b" * 64


def observations(
    *,
    operating_stage: str = "QUALIFICATION",
    comparator_feed: str = FEED_HASH,
    labels: dict[int, bool | None] | None = None,
) -> tuple[list[PredictionObservation], list[PredictionObservation], list[OutcomeObservation]]:
    operating = [
        PredictionObservation(instrument, index + 1, FEED_HASH, operating_stage)
        for index, instrument in enumerate(INSTRUMENTS)
    ]
    comparator_ranks = [((index + 2) % len(INSTRUMENTS)) + 1 for index in range(len(INSTRUMENTS))]
    comparator = [
        PredictionObservation(instrument, comparator_ranks[index], comparator_feed, "QUALIFICATION")
        for index, instrument in enumerate(INSTRUMENTS)
    ]
    event_map = labels or {}
    outcomes = [
        OutcomeObservation(
            instrument,
            event_map.get(index, False),
            LABEL_HASH,
            "QUALIFICATION",
        )
        for index, instrument in enumerate(INSTRUMENTS)
    ]
    return operating, comparator, outcomes


def compute(
    *,
    operating_stage: str = "QUALIFICATION",
    comparator_feed: str = FEED_HASH,
    labels: dict[int, bool | None] | None = None,
    omit_operating: bool = False,
) -> object:
    operating, comparator, outcomes = observations(
        operating_stage=operating_stage,
        comparator_feed=comparator_feed,
        labels=labels,
    )
    if omit_operating:
        operating.pop()
    return compute_session_metrics(
        session_id=SESSION,
        eligible_instrument_ids=INSTRUMENTS,
        operating_rows=operating,
        comparator_rows=comparator,
        outcomes=outcomes,
    )


def test_known_paired_precision_matches_hand_calculation() -> None:
    result = compute(labels={8: True})
    assert result.operating_precision_at_10.value == Decimal("0.1")
    assert result.comparator_precision_at_10.value == Decimal(0)
    assert result.paired_precision_difference.value == Decimal("0.1")
    assert result.paired_precision_difference.lower_bound == Decimal("0.1")
    assert result.paired_precision_difference.upper_bound == Decimal("0.1")
    assert result.precision_lift.status == "UNDEFINED"
    assert result.precision_lift.reason_code == "zero_comparator_precision"


def test_unknown_selected_outcomes_produce_conservative_paired_bounds() -> None:
    result = compute(labels={8: None, 10: None})
    assert result.operating_precision_at_10.value is None
    assert result.operating_precision_at_10.lower_bound == Decimal(0)
    assert result.operating_precision_at_10.upper_bound == Decimal("0.1")
    assert result.comparator_precision_at_10.value is None
    assert result.paired_precision_difference.lower_bound == Decimal("-0.1")
    assert result.paired_precision_difference.upper_bound == Decimal("0.1")
    assert result.paired_precision_difference.missing_count == 2
    assert result.operating_recall_at_10.status == "BOUNDED_UNKNOWN"


def test_zero_events_and_zero_comparator_ratio_are_undefined() -> None:
    result = compute(labels={})
    assert result.operating_recall_at_10.status == "UNDEFINED"
    assert result.operating_recall_at_10.denominator == 0
    assert result.precision_lift.value is None
    assert result.precision_lift.status == "UNDEFINED"


def test_missing_denominator_and_fake_all_row_metrics_are_rejected() -> None:
    with pytest.raises(ValidationAuthorityError, match="denominator is incomplete"):
        compute(omit_operating=True)
    with pytest.raises(ValidationAuthorityError, match="QUALIFICATION split"):
        compute(operating_stage="TRAINING", labels={8: True})


def test_feed_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationAuthorityError, match="different feeds"):
        compute(comparator_feed="c" * 64)


def test_missing_outcome_row_is_not_dropped() -> None:
    operating, comparator, outcomes = observations()
    outcomes.pop()
    with pytest.raises(ValidationAuthorityError, match="outcome denominator is incomplete"):
        compute_session_metrics(
            session_id=SESSION,
            eligible_instrument_ids=INSTRUMENTS,
            operating_rows=operating,
            comparator_rows=comparator,
            outcomes=outcomes,
        )


def test_session_average_is_equal_weighted() -> None:
    small = MetricEstimate(
        "paired_precision_difference_at_10",
        "DEFINED",
        Decimal("0.1"),
        Decimal("0.1"),
        Decimal("0.1"),
        20,
        0,
    )
    large = MetricEstimate(
        "paired_precision_difference_at_10",
        "DEFINED",
        Decimal("0.9"),
        Decimal("0.9"),
        Decimal("0.9"),
        20,
        0,
    )
    mean = mean_session_estimates("paired_precision_difference_at_10", [small, large])
    assert mean.value == Decimal("0.5")
    assert mean.denominator == 2
