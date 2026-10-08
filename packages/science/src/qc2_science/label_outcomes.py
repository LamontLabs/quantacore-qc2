"""Calendar-fixed, mature-only label outcome formulas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any

from .label_models import (
    DailyLabelBar,
    FieldValidity,
    LabelDefinitionSpec,
    LabelInput,
    LabelInputError,
    LabelOutcome,
    SessionMonsterMeasurement,
)
from .models import as_utc
from .label_registry import (
    LabelProductionActivationGrant,
    LabelRegistryBundle,
    assert_label_registry_registrable,
)

_METRIC_FIELDS = (
    "reference_price",
    "next_open_reference_price",
    "endpoint_return",
    "max_high_return",
    "min_low_return",
    "mfe",
    "mae",
    "max_high_price",
    "max_high_session",
    "max_high_session_offset",
    "min_low_price",
    "min_low_session",
    "min_low_session_offset",
    "opening_gap_return",
    "next_open_proxy_endpoint_return",
    "next_open_proxy_max_high_return",
    "next_open_proxy_min_low_return",
    "next_open_proxy_mfe",
    "next_open_proxy_mae",
)
_RETURN_QUANTUM = Decimal("0.000000000001")


def _fractional_return(numerator: Decimal, denominator: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(
            96,
            len(numerator.as_tuple().digits)
            + len(denominator.as_tuple().digits)
            + 32,
        )
        value = numerator / denominator - Decimal(1)
        rounded = value.quantize(_RETURN_QUANTUM, rounding=ROUND_HALF_EVEN)
    return abs(rounded) if rounded.is_zero() else rounded


def _empty_metrics(reference_price: Decimal) -> dict[str, Decimal | str | int | None]:
    values: dict[str, Decimal | str | int | None] = {name: None for name in _METRIC_FIELDS}
    values["reference_price"] = reference_price
    return values


def _field_validity(
    metrics: dict[str, Decimal | str | int | None],
    *,
    resolved: bool,
    missing_bar: bool,
    censored: bool = False,
    reason_code: str | None = None,
) -> tuple[FieldValidity, ...]:
    result = []
    for name in _METRIC_FIELDS:
        value = metrics[name]
        if value is not None:
            result.append(FieldValidity(name, "VALID", None))
        elif censored:
            result.append(FieldValidity(name, "CENSORED", reason_code or "terminal_event_unresolved"))
        elif missing_bar:
            result.append(FieldValidity(name, "UNRESOLVED", reason_code or "missing_horizon_session_bar"))
        elif resolved:
            result.append(FieldValidity(name, "NOT_APPLICABLE", "metric_not_available_for_state"))
        else:
            result.append(FieldValidity(name, "UNRESOLVED", reason_code or "full_horizon_not_released"))
    return tuple(result)


def _target_unavailable_status(spec: LabelDefinitionSpec) -> str | None:
    if spec.target_event not in {"EXPANSION_RUNNER", "SESSION_MONSTER"}:
        return "UNAVAILABLE_LABEL"
    if spec.threshold is None:
        return "UNAVAILABLE_THRESHOLD"
    return None


def _unresolved_result(
    registry: LabelRegistryBundle,
    spec: LabelDefinitionSpec,
    label_input: LabelInput,
    expected_sessions: tuple[Any, ...],
    created_at: datetime,
    *,
    state: str,
    reason_code: str,
    missing_bar: bool = False,
    censored: bool = False,
    first_bar: DailyLabelBar | None = None,
) -> LabelOutcome:
    reference = label_input.prediction_bar
    metrics = _empty_metrics(reference.close_price)
    if (
        first_bar is not None
        and first_bar.finalized_at is not None
        and label_input.corporate_action_status == "FINALIZED"
    ):
        if first_bar.finalized_at > created_at:
            raise LabelInputError("label created_at precedes next-session bar finalization")
        metrics["next_open_reference_price"] = first_bar.open_price
        metrics["opening_gap_return"] = _fractional_return(
            first_bar.open_price,
            reference.close_price,
        )
    validity = _field_validity(
        metrics,
        resolved=False,
        missing_bar=missing_bar,
        censored=censored,
        reason_code=reason_code,
    )
    semantic_status = _target_unavailable_status(spec)
    if semantic_status is None:
        semantic_status = {
            "PENDING_MATURITY": "UNAVAILABLE_MATURITY",
            "PARTIALLY_RESOLVABLE": "UNRESOLVED_DATA",
            "UNRESOLVED_DATA": "UNRESOLVED_DATA",
            "CORPORATE_ACTION_REVIEW": "CORPORATE_ACTION_REVIEW",
            "CENSORED_TERMINAL_EVENT": "CENSORED_TERMINAL_EVENT",
        }[state]
    sources = [label_input.calendar_ref, reference.source_ref]
    definition_ref = registry.definition_ref(spec.stable_key)
    registry_ref = registry.registry_ref
    sources.extend((registry_ref, definition_ref))
    if first_bar is not None:
        sources.append(first_bar.source_ref)
    return LabelOutcome(
        definition_key=spec.stable_key,
        horizon_sessions=spec.horizon_sessions,
        expected_session_ids=expected_sessions,
        outcome_state=state,
        metrics=metrics,
        field_validity=validity,
        target_value=None,
        target_status=semantic_status,
        session_monster_measurements=(),
        label_ref=definition_ref,
        registry_ref=registry_ref,
        reference_bar_ref=reference.source_ref,
        next_open_bar_ref=first_bar.source_ref if first_bar else None,
        source_refs=tuple(sources),
        reason_codes=(reason_code,),
        available_for_learning_at=None,
    )


def resolve_label_outcome(
    registry: LabelRegistryBundle,
    definition_key: str,
    label_input: LabelInput,
    *,
    created_at: datetime | str,
    activation_grant: LabelProductionActivationGrant | None = None,
) -> LabelOutcome:
    """Compute one label only from its frozen calendar window and finalized inputs."""
    if not isinstance(registry, LabelRegistryBundle) or not isinstance(label_input, LabelInput):
        raise LabelInputError("resolve_label_outcome requires a registry bundle and typed input")
    if not isinstance(definition_key, str):
        raise LabelInputError("definition_key must be a registered stable_key")
    assert_label_registry_registrable(
        registry,
        target_environment=registry.environment_namespace,
        activation_grant=activation_grant,
    )
    try:
        spec = next(spec for spec in registry.definitions if spec.stable_key == definition_key)
    except StopIteration as exc:
        raise LabelInputError(f"unknown label definition: {definition_key}") from exc
    created = as_utc(created_at, "label created_at")
    evidence_instants = [
        label_input.prediction_bar.finalized_at,
        *(bar.finalized_at for bar in label_input.future_bars),
        label_input.corporate_action_finalized_at,
        label_input.data_finalization_complete_at,
        label_input.label_release_transaction_complete_at,
    ]
    if any(instant is not None and instant > created for instant in evidence_instants):
        raise LabelInputError("label created_at cannot precede evidence supplied to the resolver")
    prediction_session = label_input.prediction_bar.session_id
    prediction_index = label_input.calendar_sessions.index(prediction_session)
    start = prediction_index + 1
    end = start + spec.horizon_sessions
    if end > len(label_input.calendar_sessions):
        raise LabelInputError("frozen calendar does not contain the complete registered horizon")
    expected_sessions = tuple(label_input.calendar_sessions[start:end])
    if (
        label_input.terminal_event_session is not None
        and label_input.terminal_event_session in expected_sessions
    ):
        return _unresolved_result(
            registry,
            spec,
            label_input,
            expected_sessions,
            created,
            state="CENSORED_TERMINAL_EVENT",
            reason_code="terminal_consideration_not_resolved",
            censored=True,
            first_bar=next(
                (
                    bar
                    for bar in label_input.future_bars
                    if bar.session_id == expected_sessions[0]
                ),
                None,
            ),
        )
    if label_input.observation_session < expected_sessions[-1]:
        first = next(
            (bar for bar in label_input.future_bars if bar.session_id == expected_sessions[0]),
            None,
        )
        return _unresolved_result(
            registry,
            spec,
            label_input,
            expected_sessions,
            created,
            state="PENDING_MATURITY",
            reason_code="horizon_sessions_not_elapsed",
            first_bar=first,
        )

    bar_by_session = {bar.session_id: bar for bar in label_input.future_bars}
    first_bar = bar_by_session.get(expected_sessions[0])
    if label_input.corporate_action_status != "FINALIZED":
        return _unresolved_result(
            registry,
            spec,
            label_input,
            expected_sessions,
            created,
            state="CORPORATE_ACTION_REVIEW",
            reason_code="corporate_action_basis_not_final",
            first_bar=first_bar,
        )
    if label_input.corporate_action_finalized_at is None:
        raise LabelInputError("FINALIZED corporate-action state requires its finalization instant")
    if label_input.corporate_action_finalized_at > created:
        raise LabelInputError("label created_at precedes corporate-action finalization")

    missing_sessions = tuple(session for session in expected_sessions if session not in bar_by_session)
    if missing_sessions:
        partial = first_bar is not None and first_bar.finalized_at is not None
        return _unresolved_result(
            registry,
            spec,
            label_input,
            expected_sessions,
            created,
            state="PARTIALLY_RESOLVABLE" if partial else "UNRESOLVED_DATA",
            reason_code="missing_horizon_session_bar",
            missing_bar=True,
            first_bar=first_bar,
        )

    horizon_bars = tuple(bar_by_session[session] for session in expected_sessions)
    if any(bar.finalized_at is None for bar in horizon_bars):
        return _unresolved_result(
            registry,
            spec,
            label_input,
            expected_sessions,
            created,
            state="PENDING_MATURITY",
            reason_code="bar_finalization_pending",
            first_bar=first_bar,
        )
    for bar in horizon_bars:
        if bar.finalized_at > created:
            raise LabelInputError("label created_at precedes a horizon bar finalization")
    if label_input.data_finalization_complete_at is None:
        return _unresolved_result(
            registry,
            spec,
            label_input,
            expected_sessions,
            created,
            state="PENDING_MATURITY",
            reason_code="data_finalization_pending",
            first_bar=first_bar,
        )
    if label_input.data_finalization_complete_at > created:
        raise LabelInputError("label created_at precedes data-finalization completion")
    if label_input.label_release_transaction_complete_at is None:
        return _unresolved_result(
            registry,
            spec,
            label_input,
            expected_sessions,
            created,
            state="PENDING_MATURITY",
            reason_code="label_release_transaction_pending",
            first_bar=first_bar,
        )
    if label_input.label_release_transaction_complete_at > created:
        raise LabelInputError("label created_at precedes label release transaction")

    reference = label_input.prediction_bar
    reference_close = reference.close_price
    first_open = horizon_bars[0].open_price
    high_prices = tuple(bar.high_price for bar in horizon_bars)
    low_prices = tuple(bar.low_price for bar in horizon_bars)
    max_high_price = max(high_prices)
    min_low_price = min(low_prices)
    max_high_index = high_prices.index(max_high_price)
    min_low_index = low_prices.index(min_low_price)
    max_high_return = _fractional_return(max_high_price, reference_close)
    min_low_return = _fractional_return(min_low_price, reference_close)
    proxy_max_high_return = _fractional_return(max(high_prices), first_open)
    proxy_min_low_return = _fractional_return(min(low_prices), first_open)
    endpoint_return = _fractional_return(horizon_bars[-1].close_price, reference_close)
    proxy_endpoint_return = _fractional_return(horizon_bars[-1].close_price, first_open)
    metrics: dict[str, Decimal | str | int | None] = {
        "reference_price": reference_close,
        "next_open_reference_price": first_open,
        "endpoint_return": endpoint_return,
        "max_high_return": max_high_return,
        "min_low_return": min_low_return,
        "mfe": max(Decimal(0), max_high_return),
        "mae": min(Decimal(0), min_low_return),
        "max_high_price": max_high_price,
        "max_high_session": expected_sessions[max_high_index].isoformat(),
        "max_high_session_offset": max_high_index + 1,
        "min_low_price": min_low_price,
        "min_low_session": expected_sessions[min_low_index].isoformat(),
        "min_low_session_offset": min_low_index + 1,
        "opening_gap_return": _fractional_return(first_open, reference_close),
        "next_open_proxy_endpoint_return": proxy_endpoint_return,
        "next_open_proxy_max_high_return": proxy_max_high_return,
        "next_open_proxy_min_low_return": proxy_min_low_return,
        "next_open_proxy_mfe": max(Decimal(0), proxy_max_high_return),
        "next_open_proxy_mae": min(Decimal(0), proxy_min_low_return),
    }

    monster_measurements: tuple[SessionMonsterMeasurement, ...] = ()
    if spec.target_event == "SESSION_MONSTER":
        previous_close = reference_close
        rows = []
        for offset, bar in enumerate(horizon_bars, start=1):
            rows.append(
                SessionMonsterMeasurement(
                    session_id=bar.session_id,
                    session_offset=offset,
                    monster_return=_fractional_return(bar.high_price, previous_close),
                    open_to_high_return=_fractional_return(bar.high_price, bar.open_price),
                    opening_gap_return=_fractional_return(bar.open_price, previous_close),
                )
            )
            previous_close = bar.close_price
        monster_measurements = tuple(rows)

    target_status = _target_unavailable_status(spec)
    target_value: bool | None = None
    if target_status is None:
        if spec.target_event == "EXPANSION_RUNNER":
            target_value = max_high_return >= spec.threshold
        elif spec.target_event == "SESSION_MONSTER":
            target_value = any(
                row.monster_return >= spec.threshold for row in monster_measurements
            )
        target_status = "AVAILABLE"

    finalization_times = [
        reference.finalized_at,
        *(bar.finalized_at for bar in horizon_bars),
        label_input.corporate_action_finalized_at,
        label_input.data_finalization_complete_at,
        label_input.label_release_transaction_complete_at,
    ]
    if any(value is None for value in finalization_times):
        raise LabelInputError("resolved labels require every finalization timestamp")
    available_at = max(finalization_times)
    if available_at > created:
        raise LabelInputError("label release timestamp is after created_at")
    learning_at = available_at if target_status == "AVAILABLE" else None
    sources = [label_input.calendar_ref, reference.source_ref]
    sources.extend(bar.source_ref for bar in horizon_bars)
    definition_ref = registry.definition_ref(spec.stable_key)
    registry_ref = registry.registry_ref
    sources.extend((registry_ref, definition_ref))
    return LabelOutcome(
        definition_key=spec.stable_key,
        horizon_sessions=spec.horizon_sessions,
        expected_session_ids=expected_sessions,
        outcome_state="RESOLVED",
        metrics=metrics,
        field_validity=_field_validity(metrics, resolved=True, missing_bar=False),
        target_value=target_value,
        target_status=target_status,
        session_monster_measurements=monster_measurements,
        label_ref=definition_ref,
        registry_ref=registry_ref,
        reference_bar_ref=reference.source_ref,
        next_open_bar_ref=horizon_bars[0].source_ref,
        source_refs=tuple(sources),
        reason_codes=(),
        available_for_learning_at=learning_at,
    )
