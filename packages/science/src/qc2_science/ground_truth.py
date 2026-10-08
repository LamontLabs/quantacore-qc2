"""Independent Ground Truth resolution, event materialization, and action review."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Iterable

from .ground_truth_models import (
    ActionReviewCase,
    ActionReviewDecision,
    CORPORATE_ACTION_SCHEMA,
    FrozenContractRecord,
    GroundTruthBatchResult,
    GroundTruthEligibleRow,
    GroundTruthError,
    GroundTruthRowResolution,
    INSTRUMENT_SCHEMA,
    OUTCOME_SCHEMA,
    RUNNER_EVENT_SCHEMA,
    SYMBOL_ASSIGNMENT_SCHEMA,
    freeze_contract_record,
    utc_text,
)
from .label_models import LabelOutcome
from .label_outcomes import resolve_label_outcome
from .label_registry import LabelRegistryBundle
from .models import ContractRef, as_date, as_utc

_RETURN_QUANTUM = Decimal("0.000000000001")
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
_OUTCOME_SOURCE_SCHEMAS = {
    "qc2.identity_market.DailyBar.v1",
    CORPORATE_ACTION_SCHEMA,
    "qc2.identity_market.MarketSnapshotRevision.v1",
}


def _deterministic_uuid7(created_at: datetime, identity_key: str) -> str:
    """Create a UUIDv7 with the supplied UTC millisecond and stable hash bits."""
    instant = as_utc(created_at, "deterministic UUID created_at")
    timestamp_ms = int(instant.timestamp() * 1000) & ((1 << 48) - 1)
    digest = hashlib.sha256(identity_key.encode("utf-8")).digest()
    rand_a = int.from_bytes(digest[:2], "big") & 0x0FFF
    rand_b = int.from_bytes(digest[2:10], "big") & ((1 << 62) - 1)
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return str(uuid.UUID(int=value))


def _fractional_return(numerator: Decimal, denominator: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(
            96,
            len(numerator.as_tuple().digits)
            + len(denominator.as_tuple().digits)
            + 32,
        )
        value = (numerator / denominator - Decimal(1)).quantize(
            _RETURN_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
    return abs(value) if value.is_zero() else value


def _price_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _return_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    rounded = value.quantize(_RETURN_QUANTUM, rounding=ROUND_HALF_EVEN)
    if rounded.is_zero():
        rounded = abs(rounded)
    return f"{rounded:.12f}"


def _stable_payload(payload: dict[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key not in {"id", "content_hash"}}
    return json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _unique_refs(references: Iterable[ContractRef]) -> list[dict[str, str]]:
    by_key: dict[tuple[str, str, str], ContractRef] = {}
    for reference in references:
        if not isinstance(reference, ContractRef):
            raise GroundTruthError("source references must be ContractRefs")
        by_key[
            (
                reference.target_schema_name,
                reference.target_id,
                reference.content_hash,
            )
        ] = reference
    return [by_key[key].to_payload() for key in sorted(by_key)]


def _expected_sessions(
    registry: LabelRegistryBundle,
    row: GroundTruthEligibleRow,
) -> tuple[date, ...]:
    try:
        definition = next(
            item for item in registry.definitions if item.stable_key == row.definition_key
        )
    except StopIteration as exc:
        raise GroundTruthError(f"unknown label definition: {row.definition_key}") from exc
    sessions = row.label_input.calendar_sessions
    try:
        prediction_index = sessions.index(row.label_input.prediction_bar.session_id)
    except ValueError as exc:
        raise GroundTruthError("prediction session is absent from the frozen calendar") from exc
    start = prediction_index + 1
    end = start + definition.horizon_sessions
    if end > len(sessions):
        raise GroundTruthError("frozen calendar does not contain the registered horizon")
    return tuple(sessions[start:end])


def _validate_symbol_coverage(
    row: GroundTruthEligibleRow,
    expected_sessions: tuple[date, ...],
) -> None:
    assignments = sorted(row.symbol_assignments, key=lambda item: item.effective_from)
    for left, right in zip(assignments, assignments[1:]):
        if (
            left.effective_to_exclusive is None
            or left.effective_to_exclusive > right.effective_from
        ):
            raise GroundTruthError("symbol assignment intervals overlap")
    instrument_ref = row.label_input.prediction_bar.instrument_ref
    if instrument_ref.target_schema_name != INSTRUMENT_SCHEMA:
        raise GroundTruthError("label input must use an Instrument reference")
    checked_sessions = [row.label_input.prediction_bar.session_id, *expected_sessions]
    terminal = row.label_input.terminal_event_session
    if terminal in expected_sessions:
        checked_sessions = [
            session for session in checked_sessions if session <= terminal
        ]
    for session in checked_sessions:
        matches = [item for item in assignments if item.contains(session)]
        if len(matches) != 1:
            raise GroundTruthError(
                f"symbol assignment coverage for {session.isoformat()} is not exactly one"
            )
        if matches[0].instrument_ref != instrument_ref:
            raise GroundTruthError("symbol assignment changes the stable instrument identity")
        if matches[0].assignment_ref.target_schema_name != SYMBOL_ASSIGNMENT_SCHEMA:
            raise GroundTruthError("symbol assignment reference has an invalid schema")


def _metric_payloads(
    outcome: LabelOutcome,
    row: GroundTruthEligibleRow,
    created_at: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], str, str | None]:
    metrics = dict(outcome.metrics)
    validity = [
        {
            "field_name": item.field_name,
            "status": item.status,
            "reason_code": item.reason_code,
        }
        for item in outcome.field_validity
    ]
    reason_codes = list(outcome.reason_codes)
    state = outcome.outcome_state
    learning_at = (
        utc_text(outcome.available_for_learning_at, "available_for_learning_at")
        if outcome.available_for_learning_at is not None
        else None
    )
    terminal = row.terminal_event
    terminal_in_horizon = (
        terminal is not None and terminal.event_session in outcome.expected_session_ids
    )
    if (
        terminal_in_horizon
        and terminal.status == "VERIFIED_CASH_CONSIDERATION"
        and row.label_input.corporate_action_status == "FINALIZED"
    ):
        if terminal.finalized_at is None or terminal.finalized_at > created_at:
            raise GroundTruthError("terminal consideration was finalized after outcome creation")
        if terminal.currency != row.reference_currency:
            raise GroundTruthError("terminal cash consideration uses a different currency")
        reference_price = metrics["reference_price"]
        if not isinstance(reference_price, Decimal):
            raise GroundTruthError("terminal outcome has no valid reference price")
        metrics["endpoint_return"] = _fractional_return(
            terminal.cash_consideration_per_share,
            reference_price,
        )
        for field_name in _METRIC_FIELDS:
            if field_name not in {
                "reference_price",
                "next_open_reference_price",
                "endpoint_return",
                "opening_gap_return",
            }:
                metrics[field_name] = None
        original_validity = {item["field_name"]: item for item in validity}
        validity = []
        for field_name in _METRIC_FIELDS:
            if field_name == "endpoint_return":
                status, reason = "VALID", None
            elif field_name in {
                "reference_price",
                "next_open_reference_price",
                "opening_gap_return",
            }:
                prior = original_validity[field_name]
                status, reason = prior["status"], prior["reason_code"]
            else:
                status, reason = "CENSORED", "terminal_event_shortened_horizon"
            validity.append(
                {
                    "field_name": field_name,
                    "status": status,
                    "reason_code": reason,
                }
            )
        state = "PARTIALLY_RESOLVABLE"
        reason_codes = [
            "terminal_cash_consideration_resolved",
            "terminal_horizon_metrics_censored",
        ]
        learning_at = None
    if any(name not in metrics for name in _METRIC_FIELDS):
        raise GroundTruthError("label outcome does not supply every Outcome metric")
    return metrics, validity, reason_codes, state, learning_at


def _outcome_record(
    registry: LabelRegistryBundle,
    row: GroundTruthEligibleRow,
    label_outcome: LabelOutcome,
    created_at: datetime,
) -> FrozenContractRecord:
    metrics, validity, reason_codes, state, learning_at = _metric_payloads(
        label_outcome,
        row,
        created_at,
    )
    source_refs = [
        reference
        for reference in label_outcome.source_refs
        if reference.target_schema_name in _OUTCOME_SOURCE_SCHEMAS
    ]
    source_refs.extend(row.corporate_action_refs)
    source_refs.extend(row.market_snapshot_refs)
    payload: dict[str, Any] = {
        "schema_name": OUTCOME_SCHEMA,
        "schema_version": "1.0",
        "id": "",
        "created_at": utc_text(created_at, "outcome created_at"),
        "owning_authority": "ground_truth",
        "evidence_class": registry.evidence_class,
        "environment_namespace": registry.environment_namespace,
        "source_refs": _unique_refs(source_refs),
        "instrument_ref": row.label_input.prediction_bar.instrument_ref.to_payload(),
        "session_id": row.label_input.prediction_bar.session_id.isoformat(),
        "label_ref": label_outcome.label_ref.to_payload(),
        "horizon_sessions": label_outcome.horizon_sessions,
        "reference_bar_ref": label_outcome.reference_bar_ref.to_payload(),
        "reference_price": _price_text(metrics["reference_price"]),
        "next_open_bar_ref": (
            label_outcome.next_open_bar_ref.to_payload()
            if (
                label_outcome.next_open_bar_ref is not None
                and metrics["next_open_reference_price"] is not None
            )
            else None
        ),
        "next_open_reference_price": _price_text(metrics["next_open_reference_price"]),
        "outcome_state": state,
        "endpoint_return": _return_text(metrics["endpoint_return"]),
        "max_high_return": _return_text(metrics["max_high_return"]),
        "min_low_return": _return_text(metrics["min_low_return"]),
        "mfe": _return_text(metrics["mfe"]),
        "mae": _return_text(metrics["mae"]),
        "max_high_price": _price_text(metrics["max_high_price"]),
        "max_high_session": metrics["max_high_session"],
        "max_high_session_offset": metrics["max_high_session_offset"],
        "min_low_price": _price_text(metrics["min_low_price"]),
        "min_low_session": metrics["min_low_session"],
        "min_low_session_offset": metrics["min_low_session_offset"],
        "extrema_tie_break": "EARLIEST_SESSION",
        "opening_gap_return": _return_text(metrics["opening_gap_return"]),
        "next_open_proxy_endpoint_return": _return_text(
            metrics["next_open_proxy_endpoint_return"]
        ),
        "next_open_proxy_max_high_return": _return_text(
            metrics["next_open_proxy_max_high_return"]
        ),
        "next_open_proxy_min_low_return": _return_text(
            metrics["next_open_proxy_min_low_return"]
        ),
        "next_open_proxy_mfe": _return_text(metrics["next_open_proxy_mfe"]),
        "next_open_proxy_mae": _return_text(metrics["next_open_proxy_mae"]),
        "field_validity": validity,
        "reason_codes": reason_codes,
        "available_for_learning_at": learning_at,
    }
    identity = f"{row.row_key}:{row.definition_key}:{hashlib.sha256(_stable_payload(payload).encode()).hexdigest()}"
    payload["id"] = _deterministic_uuid7(created_at, identity)
    return freeze_contract_record("Outcome", payload)


def _runner_event_record(
    registry: LabelRegistryBundle,
    row: GroundTruthEligibleRow,
    label_outcome: LabelOutcome,
    outcome_record: FrozenContractRecord,
    *,
    event_type: str,
    start_session: date,
    end_session: date | None,
    created_at: datetime,
    event_ordinal: int,
) -> FrozenContractRecord:
    outcome_payload = outcome_record.payload
    event_sources = [
        ContractRef(
            item["target_schema_name"],
            item["target_id"],
            item.get("content_hash", "0" * 64),
        )
        for item in outcome_payload["source_refs"]
    ]
    payload: dict[str, Any] = {
        "schema_name": RUNNER_EVENT_SCHEMA,
        "schema_version": "1.0",
        "id": "",
        "created_at": utc_text(created_at, "RunnerEvent created_at"),
        "owning_authority": "ground_truth",
        "evidence_class": registry.evidence_class,
        "environment_namespace": registry.environment_namespace,
        "source_refs": _unique_refs(event_sources),
        "instrument_ref": row.label_input.prediction_bar.instrument_ref.to_payload(),
        "event_type": event_type,
        "start_session": start_session.isoformat(),
        "end_session": end_session.isoformat() if end_session else None,
        "label_ref": label_outcome.label_ref.to_payload(),
        "outcome_ref": outcome_record.ref.to_payload(),
        "detected_at": utc_text(created_at, "RunnerEvent detected_at"),
        "evidence_refs": [],
    }
    identity = (
        f"{row.row_key}:{row.definition_key}:{event_type}:{event_ordinal}:"
        f"{outcome_record.ref.content_hash}:{start_session}:{end_session}"
    )
    payload["id"] = _deterministic_uuid7(created_at, identity)
    return freeze_contract_record("RunnerEvent", payload)


def _runner_events(
    registry: LabelRegistryBundle,
    row: GroundTruthEligibleRow,
    label_outcome: LabelOutcome,
    outcome_record: FrozenContractRecord,
    created_at: datetime,
) -> tuple[FrozenContractRecord, ...]:
    if (
        label_outcome.outcome_state != "RESOLVED"
        or label_outcome.target_status != "AVAILABLE"
        or label_outcome.target_value is not True
    ):
        return ()
    try:
        definition = next(
            item for item in registry.definitions if item.stable_key == row.definition_key
        )
    except StopIteration as exc:
        raise GroundTruthError(f"unknown label definition: {row.definition_key}") from exc
    if definition.threshold is None:
        raise GroundTruthError("an available positive event requires a frozen threshold")
    if definition.target_event == "EXPANSION_RUNNER":
        reference = row.label_input.prediction_bar.close_price
        start = next(
            (
                bar.session_id
                for bar in row.label_input.future_bars
                if _fractional_return(bar.high_price, reference) >= definition.threshold
            ),
            None,
        )
        if start is None:
            raise GroundTruthError("positive Expansion Runner has no threshold-crossing session")
        peak = as_date(label_outcome.metrics["max_high_session"], "max_high_session")
        return (
            _runner_event_record(
                registry,
                row,
                label_outcome,
                outcome_record,
                event_type="EXPANSION_RUNNER",
                start_session=start,
                end_session=peak,
                created_at=created_at,
                event_ordinal=0,
            ),
        )
    if definition.target_event == "SESSION_MONSTER":
        crossing_sessions = [
            item.session_id
            for item in label_outcome.session_monster_measurements
            if item.monster_return >= definition.threshold
        ]
        return tuple(
            _runner_event_record(
                registry,
                row,
                label_outcome,
                outcome_record,
                event_type="SESSION_MONSTER",
                start_session=session,
                end_session=session,
                created_at=created_at,
                event_ordinal=ordinal,
            )
            for ordinal, session in enumerate(crossing_sessions)
        )
    return ()


def _review_case(
    row: GroundTruthEligibleRow,
    outcome_record: FrozenContractRecord,
    *,
    review_type: str,
    reason_code: str,
    created_at: datetime,
    evidence_refs: Iterable[ContractRef],
) -> ActionReviewCase:
    outcome_payload = outcome_record.payload
    identity = f"{row.row_key}:{review_type}:{reason_code}:{outcome_record.ref.content_hash}"
    return ActionReviewCase(
        case_id=_deterministic_uuid7(created_at, identity),
        row_key=row.row_key,
        outcome_ref=outcome_record.ref,
        instrument_ref=row.label_input.prediction_bar.instrument_ref,
        session_id=row.label_input.prediction_bar.session_id,
        review_type=review_type,
        reason_code=reason_code,
        opened_at=created_at,
        evidence_refs=tuple(
            ContractRef(
                item["target_schema_name"],
                item["target_id"],
                item.get("content_hash", "0" * 64),
            )
            for item in outcome_payload["source_refs"]
        )
        + tuple(evidence_refs),
    )


def resolve_eligible_rows(
    registry: LabelRegistryBundle,
    rows: Iterable[GroundTruthEligibleRow],
    *,
    created_at: datetime | str,
) -> GroundTruthBatchResult:
    """Resolve every supplied eligible row without reading predictions or model outputs."""
    if not isinstance(registry, LabelRegistryBundle):
        raise GroundTruthError("a validated LabelRegistryBundle is required")
    materialized_rows = tuple(rows)
    if any(not isinstance(row, GroundTruthEligibleRow) for row in materialized_rows):
        raise GroundTruthError("rows must contain GroundTruthEligibleRow values")
    row_keys = [(row.row_key, row.definition_key) for row in materialized_rows]
    if len(row_keys) != len(set(row_keys)):
        raise GroundTruthError("eligible row/definition keys must be unique")
    created = as_utc(created_at, "Ground Truth created_at")
    resolutions: list[GroundTruthRowResolution] = []
    events: list[FrozenContractRecord] = []
    reviews: list[ActionReviewCase] = []
    for row in sorted(materialized_rows, key=lambda item: (item.row_key, item.definition_key)):
        expected_sessions = _expected_sessions(registry, row)
        _validate_symbol_coverage(row, expected_sessions)
        terminal = row.terminal_event
        if (
            terminal is not None
            and terminal.event_session in expected_sessions
            and terminal.status == "VERIFIED_CASH_CONSIDERATION"
        ):
            if terminal.finalized_at is None or terminal.finalized_at > created:
                raise GroundTruthError("terminal evidence must be finalized before resolution")
            if terminal.currency != row.reference_currency:
                raise GroundTruthError("terminal cash consideration uses a different currency")
        label_outcome = resolve_label_outcome(
            registry,
            row.definition_key,
            row.label_input,
            created_at=created,
        )
        outcome_record = _outcome_record(registry, row, label_outcome, created)
        resolutions.append(
            GroundTruthRowResolution(
                row_key=row.row_key,
                definition_key=row.definition_key,
                outcome=outcome_record,
            )
        )
        events.extend(
            _runner_events(registry, row, label_outcome, outcome_record, created)
        )
        if row.label_input.corporate_action_status != "FINALIZED":
            reviews.append(
                _review_case(
                    row,
                    outcome_record,
                    review_type="CORPORATE_ACTION",
                    reason_code="corporate_action_basis_not_final",
                    created_at=created,
                    evidence_refs=row.corporate_action_refs,
                )
            )
        if (
            row.label_input.terminal_event_session in expected_sessions
            and (
                terminal is None
                or terminal.status != "VERIFIED_CASH_CONSIDERATION"
            )
        ):
            reviews.append(
                _review_case(
                    row,
                    outcome_record,
                    review_type="TERMINAL_EVENT",
                    reason_code="terminal_consideration_unverified",
                    created_at=created,
                    evidence_refs=(
                        (terminal.corporate_action_ref, *terminal.evidence_refs)
                        if terminal is not None
                        else row.corporate_action_refs
                    ),
                )
            )
    return GroundTruthBatchResult(
        rows=tuple(resolutions),
        runner_events=tuple(events),
        action_reviews=tuple(reviews),
    )


def record_action_review_decision(
    case: ActionReviewCase,
    *,
    decision: str,
    evidence_refs: Iterable[ContractRef],
    decided_at: datetime | str,
) -> ActionReviewDecision:
    """Record a review disposition separately; review cannot write an Outcome."""
    if not isinstance(case, ActionReviewCase):
        raise GroundTruthError("case must be a typed ActionReviewCase")
    if decision not in {"ACTION_CONFIRMED", "NO_ACTION_CONFIRMED", "REMAIN_UNRESOLVED"}:
        raise GroundTruthError("unsupported action-review decision")
    evidence = tuple(evidence_refs)
    if not evidence or any(not isinstance(item, ContractRef) for item in evidence):
        raise GroundTruthError("action-review decisions require typed evidence references")
    return ActionReviewDecision(
        case_id=case.case_id,
        decision=decision,
        evidence_refs=evidence,
        decided_at=as_utc(decided_at, "action review decided_at"),
    )
