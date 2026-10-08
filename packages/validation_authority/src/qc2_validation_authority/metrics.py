"""Independent, exact metric calculations over locked qualification slices."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from .models import (
    MetricEstimate,
    OutcomeObservation,
    PredictionObservation,
    SessionMetricBundle,
    SHA256_PATTERN,
    ValidationAuthorityError,
    decimal_12,
    exact_decimal,
    session_date,
)

PRIMARY_K = 10
PRIMARY_LABEL = "five-session Expansion Runner"


@dataclass(frozen=True, slots=True)
class MetricSpecification:
    metric_key: str
    estimand: str
    unit: str
    direction: str
    missingness_policy: str
    tie_handling: str


METRIC_SPECIFICATIONS = (
    MetricSpecification(
        metric_key="operating_expansion_runner_precision_at_10",
        estimand=(
            "Per exchange session, expansion-runner outcomes among the first ten "
            "eligible operating predictions, divided by ten."
        ),
        unit="fraction",
        direction="HIGHER_IS_BETTER",
        missingness_policy="EXPLICIT_REASON",
        tie_handling="Use the sealed prediction rank; tied scores must already use the pinned tie rule.",
    ),
    MetricSpecification(
        metric_key="comparator_expansion_runner_precision_at_10",
        estimand=(
            "Per exchange session, expansion-runner outcomes among the first ten "
            "transparent-composite predictions, divided by ten."
        ),
        unit="fraction",
        direction="HIGHER_IS_BETTER",
        missingness_policy="EXPLICIT_REASON",
        tie_handling="Use the sealed prediction rank; tied scores must already use the pinned tie rule.",
    ),
    MetricSpecification(
        metric_key="operating_expansion_runner_recall_at_10",
        estimand=(
            "Per exchange session, known expansion-runner events among the first ten "
            "eligible predictions divided by all expansion-runner events in the eligible universe."
        ),
        unit="fraction",
        direction="HIGHER_IS_BETTER",
        missingness_policy="EXPLICIT_REASON",
        tie_handling="Use the sealed prediction rank; tied scores must already use the pinned tie rule.",
    ),
    MetricSpecification(
        metric_key="comparator_expansion_runner_recall_at_10",
        estimand=(
            "Per exchange session, known expansion-runner events among the first ten "
            "transparent-composite predictions divided by all expansion-runner events in the eligible universe."
        ),
        unit="fraction",
        direction="HIGHER_IS_BETTER",
        missingness_policy="EXPLICIT_REASON",
        tie_handling="Use the sealed prediction rank; tied scores must already use the pinned tie rule.",
    ),
    MetricSpecification(
        metric_key="operating_eligible_prediction_coverage",
        estimand="Scored eligible instruments divided by all census-eligible instruments in the session.",
        unit="fraction",
        direction="DESCRIPTIVE",
        missingness_policy="EXPLICIT_REASON",
        tie_handling="Not applicable; coverage uses the complete eligible instrument denominator.",
    ),
    MetricSpecification(
        metric_key="comparator_eligible_prediction_coverage",
        estimand="Transparent-composite scored eligible instruments divided by all census-eligible instruments in the session.",
        unit="fraction",
        direction="DESCRIPTIVE",
        missingness_policy="EXPLICIT_REASON",
        tie_handling="Not applicable; coverage uses the complete eligible instrument denominator.",
    ),
    MetricSpecification(
        metric_key="paired_precision_difference_at_10",
        estimand=(
            "Operating expansion-runner Precision@10 minus transparent-composite "
            "Precision@10, paired by the same exchange session and instrument labels."
        ),
        unit="fraction",
        direction="HIGHER_IS_BETTER",
        missingness_policy="EXPLICIT_REASON",
        tie_handling="Use each sealed role's pinned rank; shared instrument outcomes cancel in the paired bound.",
    ),
    MetricSpecification(
        metric_key="expansion_runner_precision_lift_at_10",
        estimand=(
            "Operating expansion-runner Precision@10 divided by transparent-composite "
            "Precision@10; undefined when the comparator precision can be zero."
        ),
        unit="ratio",
        direction="HIGHER_IS_BETTER",
        missingness_policy="EXPLICIT_REASON",
        tie_handling="Use the sealed prediction rank; tied scores must already use the pinned tie rule.",
    ),
)


def _estimate(
    metric_key: str,
    status: str,
    value: Decimal | None,
    lower: Decimal | None,
    upper: Decimal | None,
    denominator: int,
    missing: int,
    reason: str | None = None,
) -> MetricEstimate:
    for label, bound in (("lower_bound", lower), ("upper_bound", upper), ("value", value)):
        if bound is not None and not bound.is_finite():
            raise ValidationAuthorityError(f"{label} must be finite")
    if lower is not None and upper is not None and lower > upper:
        raise ValidationAuthorityError("metric lower bound cannot exceed upper bound")
    if denominator < 0 or missing < 0 or missing > denominator:
        raise ValidationAuthorityError("metric denominator and missing count are inconsistent")
    return MetricEstimate(
        metric_key=metric_key,
        status=status,
        value=value,
        lower_bound=lower,
        upper_bound=upper,
        denominator=denominator,
        missing_count=missing,
        reason_code=reason,
    )


def _validate_ranked_rows(
    rows: Sequence[PredictionObservation],
    *,
    eligible_ids: set[str],
    role: str,
) -> tuple[dict[str, PredictionObservation], str]:
    by_id: dict[str, PredictionObservation] = {}
    for row in rows:
        if row.split_stage != "QUALIFICATION":
            raise ValidationAuthorityError(
                f"{role} metrics may only use the locked QUALIFICATION split"
            )
        if row.instrument_id in by_id:
            raise ValidationAuthorityError(f"{role} contains duplicate instrument rows")
        if row.instrument_id not in eligible_ids:
            raise ValidationAuthorityError(f"{role} contains an instrument outside the census")
        if not isinstance(row.feed_hash, str) or not SHA256_PATTERN.fullmatch(row.feed_hash):
            raise ValidationAuthorityError(f"{role} feed_hash must be lowercase SHA-256")
        if row.rank is not None and (
            isinstance(row.rank, bool) or not isinstance(row.rank, int) or row.rank < 1
        ):
            raise ValidationAuthorityError(f"{role} ranks must be positive integers or null")
        by_id[row.instrument_id] = row
    if set(by_id) != eligible_ids:
        raise ValidationAuthorityError(
            f"{role} denominator is incomplete: every eligible instrument requires one row"
        )
    scored_ranks = sorted(row.rank for row in by_id.values() if row.rank is not None)
    if scored_ranks != list(range(1, len(scored_ranks) + 1)):
        raise ValidationAuthorityError(f"{role} ranks must be unique and contiguous from one")
    feed_hashes = {row.feed_hash for row in by_id.values()}
    if len(feed_hashes) != 1:
        raise ValidationAuthorityError(f"{role} cannot mix market-feed snapshots")
    return by_id, next(iter(feed_hashes))


def _precision(
    metric_key: str,
    selected: Sequence[str],
    outcomes: Mapping[str, OutcomeObservation],
) -> MetricEstimate:
    if len(selected) != PRIMARY_K:
        return _estimate(
            metric_key,
            "INSUFFICIENT_DENOMINATOR",
            None,
            None,
            None,
            PRIMARY_K,
            max(0, PRIMARY_K - len(selected)),
            "fewer_than_ten_scoreable_predictions",
        )
    known_successes = sum(outcomes[instrument_id].is_event is True for instrument_id in selected)
    missing = sum(outcomes[instrument_id].is_event is None for instrument_id in selected)
    lower = Decimal(known_successes) / Decimal(PRIMARY_K)
    upper = Decimal(known_successes + missing) / Decimal(PRIMARY_K)
    return _estimate(
        metric_key,
        "DEFINED" if missing == 0 else "BOUNDED_UNKNOWN",
        lower if missing == 0 else None,
        lower,
        upper,
        PRIMARY_K,
        missing,
        None if missing == 0 else "selected_outcomes_unresolved",
    )


def _recall(
    metric_key: str,
    selected: Sequence[str],
    eligible_ids: set[str],
    outcomes: Mapping[str, OutcomeObservation],
) -> MetricEstimate:
    if len(selected) != PRIMARY_K:
        return _estimate(
            metric_key,
            "INSUFFICIENT_DENOMINATOR",
            None,
            None,
            None,
            len(eligible_ids),
            0,
            "fewer_than_ten_scoreable_predictions",
        )
    known_events = {instrument_id for instrument_id in eligible_ids
                    if outcomes[instrument_id].is_event is True}
    unknown = {instrument_id for instrument_id in eligible_ids
               if outcomes[instrument_id].is_event is None}
    if not known_events and not unknown:
        return _estimate(
            metric_key,
            "UNDEFINED",
            None,
            None,
            None,
            0,
            0,
            "zero_events",
        )
    hits = len(set(selected) & known_events)
    unknown_selected = len(set(selected) & unknown)
    unknown_unselected = len(unknown) - unknown_selected
    if not known_events:
        lower = Decimal(0)
        upper = Decimal(1) if unknown else Decimal(0)
    else:
        lower_denominator = len(known_events) + unknown_unselected
        upper_denominator = len(known_events) + unknown_selected
        lower = (
            Decimal(hits) / Decimal(lower_denominator)
            if lower_denominator
            else Decimal(0)
        )
        upper = (
            Decimal(hits + unknown_selected) / Decimal(upper_denominator)
            if upper_denominator
            else Decimal(1)
        )
    missing = len(unknown)
    point = Decimal(hits) / Decimal(len(known_events)) if not missing else None
    return _estimate(
        metric_key,
        "DEFINED" if not missing else "BOUNDED_UNKNOWN",
        point,
        lower,
        upper,
        len(known_events) + missing,
        missing,
        None if not missing else "unresolved_event_denominator",
    )


def _paired_difference(
    operating_selected: Sequence[str],
    comparator_selected: Sequence[str],
    outcomes: Mapping[str, OutcomeObservation],
) -> MetricEstimate:
    if len(operating_selected) != PRIMARY_K or len(comparator_selected) != PRIMARY_K:
        return _estimate(
            "paired_precision_difference_at_10",
            "INSUFFICIENT_DENOMINATOR",
            None,
            None,
            None,
            2 * PRIMARY_K,
            0,
            "fewer_than_ten_scoreable_predictions",
        )
    operating_ids = set(operating_selected)
    comparator_ids = set(comparator_selected)
    known_effect = Decimal(0)
    lower = Decimal(0)
    upper = Decimal(0)
    unresolved_in_union = 0
    for instrument_id, outcome in outcomes.items():
        coefficient = Decimal(
            int(instrument_id in operating_ids) - int(instrument_id in comparator_ids)
        ) / Decimal(PRIMARY_K)
        if coefficient == 0:
            continue
        if outcome.is_event is None:
            unresolved_in_union += 1
            lower += min(Decimal(0), coefficient)
            upper += max(Decimal(0), coefficient)
        elif outcome.is_event:
            known_effect += coefficient
    lower += known_effect
    upper += known_effect
    return _estimate(
        "paired_precision_difference_at_10",
        "DEFINED" if lower == upper else "BOUNDED_UNKNOWN",
        lower if lower == upper else None,
        lower,
        upper,
        2 * PRIMARY_K,
        unresolved_in_union,
        None if lower == upper else "paired_selected_outcomes_unresolved",
    )


def _coverage(metric_key: str, scored: int, eligible: int) -> MetricEstimate:
    value = Decimal(scored) / Decimal(eligible) if eligible else None
    return _estimate(
        metric_key,
        "DEFINED" if eligible else "UNDEFINED",
        value,
        value,
        value,
        eligible,
        eligible - scored,
        None if eligible else "missing_eligible_denominator",
    )


def _precision_lift(
    operating: MetricEstimate,
    comparator: MetricEstimate,
) -> MetricEstimate:
    if (
        operating.lower_bound is None
        or operating.upper_bound is None
        or comparator.lower_bound is None
        or comparator.upper_bound is None
        or comparator.lower_bound <= 0
    ):
        reason = (
            "zero_comparator_precision"
            if comparator.lower_bound == comparator.upper_bound == 0
            else "comparator_precision_may_be_zero"
        )
        return _estimate(
            "expansion_runner_precision_lift_at_10",
            "UNDEFINED",
            None,
            None,
            None,
            2 * PRIMARY_K,
            operating.missing_count + comparator.missing_count,
            reason,
        )
    lower = operating.lower_bound / comparator.upper_bound
    upper = operating.upper_bound / comparator.lower_bound
    complete = operating.value is not None and comparator.value is not None
    value = operating.value / comparator.value if complete else None
    return _estimate(
        "expansion_runner_precision_lift_at_10",
        "DEFINED" if complete else "BOUNDED_UNKNOWN",
        value,
        lower,
        upper,
        2 * PRIMARY_K,
        operating.missing_count + comparator.missing_count,
        None if complete else "precision_inputs_unresolved",
    )


def compute_session_metrics(
    *,
    session_id: str,
    eligible_instrument_ids: Sequence[str],
    operating_rows: Sequence[PredictionObservation],
    comparator_rows: Sequence[PredictionObservation],
    outcomes: Sequence[OutcomeObservation],
) -> SessionMetricBundle:
    """Compute all primary session metrics from one complete, paired census.

    Missing labels remain unknown and produce worst/best-case bounds. Missing
    denominator rows and mixed feeds are rejected rather than silently dropped.
    """
    session_date(session_id)
    if isinstance(eligible_instrument_ids, (str, bytes)) or not eligible_instrument_ids:
        raise ValidationAuthorityError("eligible_instrument_ids must be a non-empty census")
    eligible_ids = set(eligible_instrument_ids)
    if len(eligible_ids) != len(eligible_instrument_ids) or any(not item for item in eligible_ids):
        raise ValidationAuthorityError("eligible instrument IDs must be unique and non-empty")
    operating_by_id, operating_feed = _validate_ranked_rows(
        operating_rows, eligible_ids=eligible_ids, role="operating"
    )
    comparator_by_id, comparator_feed = _validate_ranked_rows(
        comparator_rows, eligible_ids=eligible_ids, role="comparator"
    )
    if operating_feed != comparator_feed:
        raise ValidationAuthorityError("operating and comparator predictions use different feeds")

    outcome_by_id: dict[str, OutcomeObservation] = {}
    for outcome in outcomes:
        if outcome.split_stage != "QUALIFICATION":
            raise ValidationAuthorityError("metrics cannot read training or validation labels")
        if outcome.instrument_id in outcome_by_id:
            raise ValidationAuthorityError("outcomes contain duplicate instrument rows")
        if outcome.instrument_id not in eligible_ids:
            raise ValidationAuthorityError("outcome instrument is outside the eligible census")
        if not isinstance(outcome.label_registry_hash, str) or not SHA256_PATTERN.fullmatch(
            outcome.label_registry_hash
        ):
            raise ValidationAuthorityError("outcomes require a pinned label registry hash")
        if outcome.is_event is not None and not isinstance(outcome.is_event, bool):
            raise ValidationAuthorityError("outcome labels must be true, false, or unknown")
        outcome_by_id[outcome.instrument_id] = outcome
    if set(outcome_by_id) != eligible_ids:
        raise ValidationAuthorityError(
            "outcome denominator is incomplete: each eligible instrument needs a known or unknown row"
        )
    label_hashes = {item.label_registry_hash for item in outcome_by_id.values()}
    if len(label_hashes) != 1:
        raise ValidationAuthorityError("a session cannot mix label-registry revisions")
    label_hash = next(iter(label_hashes))

    operating_selected = [
        instrument_id
        for instrument_id, _ in sorted(
            (
                (instrument_id, row.rank)
                for instrument_id, row in operating_by_id.items()
                if row.rank is not None
            ),
            key=lambda item: item[1],
        )[:PRIMARY_K]
    ]
    comparator_selected = [
        instrument_id
        for instrument_id, _ in sorted(
            (
                (instrument_id, row.rank)
                for instrument_id, row in comparator_by_id.items()
                if row.rank is not None
            ),
            key=lambda item: item[1],
        )[:PRIMARY_K]
    ]
    operating_precision = _precision(
        "operating_expansion_runner_precision_at_10", operating_selected, outcome_by_id
    )
    comparator_precision = _precision(
        "comparator_expansion_runner_precision_at_10", comparator_selected, outcome_by_id
    )
    paired = _paired_difference(operating_selected, comparator_selected, outcome_by_id)
    operating_recall = _recall(
        "operating_expansion_runner_recall_at_10",
        operating_selected,
        eligible_ids,
        outcome_by_id,
    )
    comparator_recall = _recall(
        "comparator_expansion_runner_recall_at_10",
        comparator_selected,
        eligible_ids,
        outcome_by_id,
    )
    return SessionMetricBundle(
        session_id=session_id,
        feed_hash=operating_feed,
        label_registry_hash=label_hash,
        operating_precision_at_10=operating_precision,
        comparator_precision_at_10=comparator_precision,
        paired_precision_difference=paired,
        operating_recall_at_10=operating_recall,
        comparator_recall_at_10=comparator_recall,
        operating_coverage=_coverage(
            "operating_eligible_prediction_coverage",
            sum(row.rank is not None for row in operating_by_id.values()),
            len(eligible_ids),
        ),
        comparator_coverage=_coverage(
            "comparator_eligible_prediction_coverage",
            sum(row.rank is not None for row in comparator_by_id.values()),
            len(eligible_ids),
        ),
        precision_lift=_precision_lift(operating_precision, comparator_precision),
    )


def mean_session_estimates(
    metric_key: str,
    estimates: Sequence[MetricEstimate],
) -> MetricEstimate:
    """Average session-level results equally, never weighting by row counts."""
    if not estimates:
        return _estimate(metric_key, "INSUFFICIENT_EVIDENCE", None, None, None, 0, 0,
                         "no_qualifying_sessions")
    if any(
        estimate.lower_bound is None or estimate.upper_bound is None
        for estimate in estimates
    ):
        return _estimate(
            metric_key,
            "INSUFFICIENT_EVIDENCE",
            None,
            None,
            None,
            len(estimates),
            sum(item.status != "DEFINED" for item in estimates),
            "session_metric_bounds_unavailable",
        )
    count = Decimal(len(estimates))
    lower = sum((item.lower_bound for item in estimates if item.lower_bound is not None), Decimal(0)) / count
    upper = sum((item.upper_bound for item in estimates if item.upper_bound is not None), Decimal(0)) / count
    complete_values = [item.value for item in estimates]
    point = (
        sum((item for item in complete_values if item is not None), Decimal(0)) / count
        if all(item is not None for item in complete_values)
        else None
    )
    return _estimate(
        metric_key,
        "DEFINED" if point is not None else "BOUNDED_UNKNOWN",
        point,
        lower,
        upper,
        len(estimates),
        sum(item.value is None for item in estimates),
        None if point is not None else "one_or_more_session_labels_unresolved",
    )


def normalized_metric_value(value: Decimal | None) -> str | None:
    """Return the exact twelve-place decimal form used by MetricResult.v1."""
    return None if value is None else decimal_12(exact_decimal(value, "metric value"))
