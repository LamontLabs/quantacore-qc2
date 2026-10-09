"""Pure, fail-closed paper strategy planning with no broker or label side effects."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import Decimal, ROUND_FLOOR, localcontext
import re
from typing import Any

from qc2_contracts.runtime import (
    canonical_json_bytes,
    domain_separated_sha256,
    validate_contract,
    verify_content_hash,
)

from .models import (
    ActivationReadiness,
    AllocationContext,
    AllocationPlan,
    CandidateDecision,
    CandidateDisposition,
    CompletedDailyBar,
    ExecutionFillFeedback,
    ExitAssessment,
    ExitSignal,
    FillClassification,
    InstrumentTradingEligibility,
    PlannedReservation,
    PositionSnapshot,
    ProposedActionKind,
    ProposedPaperAction,
    StrategyCandidate,
    StrategyRules,
)

RANK_RULE = "PREDICTION_AUTHORITY_RANK_ASC"
ALLOCATION_ORDER = "RANK_ASC_THEN_INSTRUMENT_ID_ASC"
ENTRY_WINDOW = "NEXT_EXCHANGE_SESSION_REGULAR_SESSION"
PRICE_CAP_RULE = "SEALED_SESSION_CLOSE_TIMES_ONE_PLUS_CONFIGURED_BUFFER"
STOP_RULE = "CALIBRATED_FRACTION_BELOW_ENTRY"
TARGET_RULE = "CALIBRATED_FRACTION_ABOVE_ENTRY"
TRAILING_RULE = "PRIOR_SESSION_PEAK_TRAILING_STOP"
REENTRY_POLICY = "COOLDOWN_BY_EXCHANGE_SESSION_COUNT"
RESERVATION_POLICY = "LIMIT_NOTIONAL_PLUS_CONFIGURED_COST_BUFFER"
CANCELLATION_POLICY = "CANCEL_UNFILLED_DAY_ENTRY_AT_SESSION_EXPIRY"
GAP_NO_FILL_POLICY = "DO_NOT_CHASE_OR_UPGRADE_ORDER_TYPE"
COMPETING_ACTION_RULE = "EXIT_BEFORE_ENTRY; NO_PYRAMIDING"
DRAWDOWN_RESPONSE = "HALT_NEW_ENTRIES_AT_DAILY_LOSS_LIMIT"
EXTERNAL_ACTIVITY_POLICY = "BLOCK_NEW_ENTRIES_ON_UNRECONCILED_EXTERNAL_ACTIVITY"
_CLOSE_REFERENCE_KIND = "PREDICTION_SESSION_DAILY_CLOSE"


def _contract_payload(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} must be a mapping")
    result = dict(payload)
    validate_contract(name, result)
    verify_content_hash(name, result)
    return result


def _decimal(payload: Mapping[str, Any], field: str) -> Decimal:
    value = payload[field]
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an exact decimal string")
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def _validate_capital_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
    policy = _contract_payload("CapitalPolicy", payload)
    positive_fields = (
        "paper_starting_capital",
        "maximum_position_cost",
        "maximum_gross_exposure",
        "daily_loss_limit",
    )
    if any(_decimal(policy, field) <= 0 for field in positive_fields):
        raise ValueError("CapitalPolicy monetary limits must be positive")
    if _decimal(policy, "cash_reserve") < 0:
        raise ValueError("CapitalPolicy cash_reserve cannot be negative")
    fraction_fields = ("maximum_position_fraction", "participation_limit")
    if any(not Decimal(0) <= _decimal(policy, field) <= Decimal(1) for field in fraction_fields):
        raise ValueError("CapitalPolicy fractions must be within [0, 1]")
    if policy["drawdown_response"] != DRAWDOWN_RESPONSE:
        raise ValueError("Unsupported drawdown response; new entries must halt at the loss limit")
    if policy["external_activity_policy"] != EXTERNAL_ACTIVITY_POLICY:
        raise ValueError("Unsupported external activity policy; unresolved account activity blocks")
    return policy


def _validate_strategy_rules(payload: Mapping[str, Any], rules: StrategyRules) -> dict[str, Any]:
    manifest = _contract_payload("StrategyManifest", payload)
    expected_literals = {
        "rank_rule": RANK_RULE,
        "entry_window": ENTRY_WINDOW,
        "allocation_order": ALLOCATION_ORDER,
        "price_cap_rule": PRICE_CAP_RULE,
        "quantity_rounding": "WHOLE_SHARES_FLOOR",
        "reentry_policy": REENTRY_POLICY,
        "reservation_policy": RESERVATION_POLICY,
        "cancellation_policy": CANCELLATION_POLICY,
        "gap_no_fill_policy": GAP_NO_FILL_POLICY,
        "competing_action_rule": COMPETING_ACTION_RULE,
    }
    for field, expected in expected_literals.items():
        if manifest[field] != expected:
            raise ValueError(f"Unsupported StrategyManifest rule for {field}")
    if rules.selection_k != manifest["selection_k"]:
        raise ValueError("Resolved selection_k does not match StrategyManifest")
    if rules.maximum_holding_sessions != manifest["maximum_holding_sessions"]:
        raise ValueError("Resolved holding period does not match StrategyManifest")
    if rules.configuration_hash != manifest["configuration_ref"]["content_hash"]:
        raise ValueError("Resolved rules are not bound to StrategyManifest configuration")
    expected_optional_rules = (
        ("stop_rule", rules.stop_loss_fraction, STOP_RULE),
        ("target_rule", rules.target_gain_fraction, TARGET_RULE),
        ("trailing_rule", rules.trailing_stop_fraction, TRAILING_RULE),
    )
    for field, value, expected in expected_optional_rules:
        declared = manifest[field]
        if (value is None) != (declared is None):
            raise ValueError(f"Resolved {field} does not match StrategyManifest")
        if value is not None and declared != expected:
            raise ValueError(f"Unsupported StrategyManifest rule for {field}")
    if rules.selection_k < 1 or rules.maximum_holding_sessions < 1:
        raise ValueError("Selection and holding session counts must be positive")
    if rules.cooldown_sessions < 0:
        raise ValueError("Cooldown cannot be negative")
    if rules.per_entry_notional_ceiling <= 0:
        raise ValueError("Per-entry notional ceiling must be positive")
    if rules.price_cap_buffer_fraction < 0 or rules.cost_buffer_fraction < 0:
        raise ValueError("Price and cost buffers cannot be negative")
    for value in (
        rules.stop_loss_fraction,
        rules.target_gain_fraction,
        rules.trailing_stop_fraction,
    ):
        if value is not None and not Decimal(0) < value < Decimal(1):
            raise ValueError("Stop, target, and trailing fractions must be in (0, 1)")
    return manifest


def strategy_rules_hash(rules: StrategyRules) -> str:
    """Hash the exact resolved settings passed to strategy and calibration gates."""
    payload = {
        "configuration_hash": rules.configuration_hash,
        "selection_k": rules.selection_k,
        "price_cap_buffer_fraction": format(rules.price_cap_buffer_fraction, "f"),
        "cost_buffer_fraction": format(rules.cost_buffer_fraction, "f"),
        "per_entry_notional_ceiling": format(rules.per_entry_notional_ceiling, "f"),
        "stop_loss_fraction": (
            None if rules.stop_loss_fraction is None else format(rules.stop_loss_fraction, "f")
        ),
        "target_gain_fraction": (
            None if rules.target_gain_fraction is None else format(rules.target_gain_fraction, "f")
        ),
        "trailing_stop_fraction": (
            None
            if rules.trailing_stop_fraction is None
            else format(rules.trailing_stop_fraction, "f")
        ),
        "maximum_holding_sessions": rules.maximum_holding_sessions,
        "cooldown_sessions": rules.cooldown_sessions,
    }
    return domain_separated_sha256("qc2.strategy-resolved-rules.v1", canonical_json_bytes(payload))


def prediction_to_candidate(
    prediction: Mapping[str, Any],
    *,
    verify_sealed_prediction: Callable[[Mapping[str, Any]], bool],
    resolve_trading_eligibility: Callable[[str, str], InstrumentTradingEligibility | None],
) -> StrategyCandidate:
    """Project a contract-validated, sealed Prediction into the strategy boundary."""
    item = _contract_payload("Prediction", prediction)
    if not verify_sealed_prediction(item):
        raise ValueError("Prediction is not verified as a member of a sealed prediction set")
    instrument_id = item["instrument_ref"]["target_id"]
    eligibility = resolve_trading_eligibility(instrument_id, item["session_id"])
    if (
        eligibility is None
        or eligibility.instrument_id != instrument_id
        or eligibility.session_id != item["session_id"]
        or eligibility.classification != "US_COMMON_EQUITY"
        or not eligibility.classification_verified
        or eligibility.currency != "USD"
        or not eligibility.symbol_mapping_verified
    ):
        raise ValueError("Prediction instrument lacks verified US-common-equity USD eligibility")
    rank = item["rank"]
    if item["disposition"] == "SCORED" and rank is None:
        raise ValueError("A SCORED Prediction must have a rank")
    return StrategyCandidate(
        prediction_id=item["id"],
        instrument_id=instrument_id,
        asset_class=eligibility.classification,
        session_id=item["session_id"],
        rank=rank,
        disposition=item["disposition"],
        reference_kind=item["reference_kind"],
        reference_price=Decimal(item["reference_price"]),
        currency=eligibility.currency,
    )


def assess_activation_readiness(
    strategy_manifest: Mapping[str, Any],
    capital_policy: Mapping[str, Any],
    rules: StrategyRules,
    *,
    verify_owner_approval: Callable[[str, Mapping[str, Any]], bool] | None,
    verify_calibration: Callable[[str, Mapping[str, Any], str], bool] | None,
) -> ActivationReadiness:
    """Report readiness only; this function never activates or persists a strategy."""
    try:
        manifest = _validate_strategy_rules(strategy_manifest, rules)
        policy = _validate_capital_policy(capital_policy)
    except (ValueError, TypeError, ArithmeticError):
        return ActivationReadiness(False, ("INVALID_OR_UNVERIFIED_CONTRACT",))

    fixture_or_nonproduction = (
        rules.fixture_only
        or manifest["evidence_class"] not in {"FORWARD_OPERATIONAL", "FORWARD_SEALED"}
        or policy["evidence_class"] not in {"FORWARD_OPERATIONAL", "FORWARD_SEALED"}
        or manifest["environment_namespace"] != "production"
        or policy["environment_namespace"] != "production"
    )
    if fixture_or_nonproduction:
        return ActivationReadiness(False, ("FIXTURE_OR_NONPRODUCTION_INPUT",))

    manifest_hash = manifest["content_hash"]
    policy_hash = policy["content_hash"]
    blockers: list[str] = []
    try:
        approval_ok = verify_owner_approval is not None and verify_owner_approval(
            policy_hash, policy["owner_approval_ref"]
        )
    except Exception:
        approval_ok = False
    if not approval_ok:
        blockers.append("SIGNED_OWNER_CAPITAL_POLICY_NOT_VERIFIED")
    try:
        calibration_ok = verify_calibration is not None and verify_calibration(
            manifest_hash,
            manifest["configuration_ref"],
            strategy_rules_hash(rules),
        )
    except Exception:
        calibration_ok = False
    if not calibration_ok:
        blockers.append("STRATEGY_CALIBRATION_NOT_VERIFIED")
    return ActivationReadiness(not blockers, tuple(blockers))


def _session_is_valid(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except (TypeError, ValueError):
        return False


def _floor_whole_shares(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _precision(*values: Decimal) -> int:
    return max(50, sum(len(value.as_tuple().digits) for value in values) + 20)


def _multiply(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _precision(left, right)
        return left * right


def _floor_ratio(numerator: Decimal, denominator: Decimal) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("Share allocation requires nonnegative budget and positive unit cost")
    with localcontext() as context:
        context.prec = _precision(numerator, denominator)
        return int((numerator / denominator).to_integral_value(rounding=ROUND_FLOOR))


def _context_blockers(context: AllocationContext, policy: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not _session_is_valid(context.decision_session) or not _session_is_valid(
        context.target_execution_session
    ):
        blockers.append("INVALID_SESSION_ID")
    elif context.target_execution_session <= context.decision_session:
        blockers.append("EXECUTION_SESSION_NOT_AFTER_DECISION_SESSION")
    if not context.is_next_exchange_session:
        blockers.append("NEXT_EXCHANGE_SESSION_NOT_VERIFIED")
    if not context.execution_episode_verified or not re.fullmatch(
        r"[0-9a-f]{64}", context.execution_episode_hash
    ):
        blockers.append("SEALED_PAPER_EXECUTION_EPISODE_NOT_VERIFIED")
    if not context.reconciliation_current:
        blockers.append("ACCOUNT_RECONCILIATION_NOT_CURRENT")
    if not context.cooldown_history_complete:
        blockers.append("COOLDOWN_HISTORY_NOT_COMPLETE")
    if not context.exit_actions_resolved:
        blockers.append("PRIOR_EXIT_ACTIONS_NOT_RESOLVED")
    if context.external_activity_unreconciled:
        blockers.append("EXTERNAL_ACCOUNT_ACTIVITY_UNRECONCILED")
    if not context.day_limit_capability_verified:
        blockers.append("DAY_LIMIT_CAPABILITY_NOT_VERIFIED")
    if not context.regular_session_window_verified:
        blockers.append("REGULAR_SESSION_WINDOW_NOT_VERIFIED")
    if not context.price_tick_verified or context.price_tick <= 0:
        blockers.append("PRICE_TICK_NOT_VERIFIED")
    if context.daily_loss_consumed < 0:
        blockers.append("INVALID_DAILY_LOSS_STATE")
    elif context.daily_loss_consumed >= _decimal(policy, "daily_loss_limit"):
        blockers.append("DAILY_LOSS_LIMIT_REACHED")
    if any(
        value < 0
        for value in (
            context.cash_balance,
            context.active_cash_reservations,
            context.position_gross_exposure,
            context.active_entry_gross_reservations,
        )
    ):
        blockers.append("INVALID_RECONCILED_CAPITAL_STATE")
    if context.current_position_count < 0 or context.active_entry_reservation_count < 0:
        blockers.append("INVALID_POSITION_OR_RESERVATION_COUNT")
    return blockers


def _plan_digest(
    strategy_hash: str,
    capital_policy_hash: str,
    input_hash: str,
    execution_episode_hash: str,
    decision_session: str,
    target_session: str,
    decisions: Sequence[CandidateDecision],
) -> str:
    rows = []
    for decision in decisions:
        action = decision.proposed_action
        rows.append(
            {
                "prediction_id": decision.prediction_id,
                "instrument_id": decision.instrument_id,
                "rank": decision.prediction_rank,
                "disposition": decision.disposition.value,
                "reason_codes": list(decision.reason_codes),
                "quantity": None if action is None else action.quantity_whole_shares,
                "sealed_reference_close": (
                    None if action is None else format(action.sealed_reference_close, "f")
                ),
                "price_cap_ceiling": (
                    None if action is None else format(action.price_cap_ceiling, "f")
                ),
                "limit_price": None if action is None else format(action.limit_price, "f"),
                "reserved_cash": (
                    None if action is None else format(action.reservation.reserved_cash, "f")
                ),
                "reservation_key": (None if action is None else action.reservation.reservation_key),
                "action_kind": None if action is None else action.action_kind.value,
                "side": None if action is None else action.side,
                "order_type": None if action is None else action.order_type,
                "time_in_force": None if action is None else action.time_in_force,
                "session_restriction": (None if action is None else action.session_restriction),
                "extended_hours": None if action is None else action.extended_hours,
                "currency": None if action is None else action.currency,
                "rule_trace": [] if action is None else list(action.rule_trace),
                "reference_kind": None if action is None else action.reference_kind,
            }
        )
    payload = {
        "strategy_hash": strategy_hash,
        "capital_policy_hash": capital_policy_hash,
        "input_hash": input_hash,
        "execution_episode_hash": execution_episode_hash,
        "decision_session": decision_session,
        "target_execution_session": target_session,
        "decisions": rows,
    }
    return domain_separated_sha256("qc2.strategy-allocation-plan.v1", canonical_json_bytes(payload))


def _allocation_inputs_hash(
    candidates: Sequence[StrategyCandidate], context: AllocationContext
) -> str:
    ordered_candidates = sorted(
        candidates,
        key=lambda item: (
            item.rank is None,
            item.rank if item.rank is not None else 0,
            item.instrument_id,
            item.prediction_id,
        ),
    )
    candidate_rows = [
        {
            "prediction_id": item.prediction_id,
            "instrument_id": item.instrument_id,
            "asset_class": item.asset_class,
            "session_id": item.session_id,
            "rank": item.rank,
            "disposition": item.disposition,
            "reference_kind": item.reference_kind,
            "reference_price": format(item.reference_price, "f"),
            "currency": item.currency,
        }
        for item in ordered_candidates
    ]
    context_payload = {
        "decision_session": context.decision_session,
        "target_execution_session": context.target_execution_session,
        "execution_episode_hash": context.execution_episode_hash,
        "execution_episode_verified": context.execution_episode_verified,
        "is_next_exchange_session": context.is_next_exchange_session,
        "cash_balance": format(context.cash_balance, "f"),
        "active_cash_reservations": format(context.active_cash_reservations, "f"),
        "position_gross_exposure": format(context.position_gross_exposure, "f"),
        "active_entry_gross_reservations": format(context.active_entry_gross_reservations, "f"),
        "current_position_count": context.current_position_count,
        "active_entry_reservation_count": context.active_entry_reservation_count,
        "occupied_instrument_ids": sorted(context.occupied_instrument_ids),
        "sessions_since_exit": sorted(
            [instrument_id, count] for instrument_id, count in context.sessions_since_exit
        ),
        "cooldown_history_complete": context.cooldown_history_complete,
        "prior_completed_session_volume": sorted(
            [instrument_id, volume]
            for instrument_id, volume in context.prior_completed_session_volume
        ),
        "daily_loss_consumed": format(context.daily_loss_consumed, "f"),
        "reconciliation_current": context.reconciliation_current,
        "exit_actions_resolved": context.exit_actions_resolved,
        "external_activity_unreconciled": context.external_activity_unreconciled,
        "day_limit_capability_verified": context.day_limit_capability_verified,
        "regular_session_window_verified": context.regular_session_window_verified,
        "price_tick_verified": context.price_tick_verified,
        "price_tick": format(context.price_tick, "f"),
    }
    return domain_separated_sha256(
        "qc2.strategy-allocation-inputs.v1",
        canonical_json_bytes({"candidates": candidate_rows, "context": context_payload}),
    )


def build_allocation_plan(
    candidates: Sequence[StrategyCandidate],
    strategy_manifest: Mapping[str, Any],
    capital_policy: Mapping[str, Any],
    rules: StrategyRules,
    context: AllocationContext,
) -> AllocationPlan:
    """Plan capped long-only DAY-limit actions from sealed close prices only."""
    manifest = _validate_strategy_rules(strategy_manifest, rules)
    policy = _validate_capital_policy(capital_policy)
    if len({candidate.prediction_id for candidate in candidates}) != len(candidates):
        raise ValueError("Prediction IDs in an allocation request must be unique")
    for candidate in candidates:
        if (
            isinstance(candidate.rank, bool)
            or (
                candidate.rank is not None
                and (not isinstance(candidate.rank, int) or candidate.rank < 1)
            )
            or candidate.reference_price <= 0
        ):
            raise ValueError("Prediction rank and sealed reference price must be positive")
    global_blockers = _context_blockers(context, policy)
    if any(
        candidate.disposition == "SCORED" and candidate.rank is None for candidate in candidates
    ):
        global_blockers.append("SCORED_PREDICTION_MISSING_RANK")
    if any(
        candidate.disposition == "SCORED" and candidate.session_id != context.decision_session
        for candidate in candidates
    ):
        global_blockers.append("PREDICTION_SESSION_MISMATCH")

    ordered = sorted(
        candidates,
        key=lambda item: (
            item.rank is None,
            item.rank if item.rank is not None else 0,
            item.instrument_id,
            item.prediction_id,
        ),
    )
    scored = [item for item in ordered if item.disposition == "SCORED" and item.rank is not None]
    selected_prediction_ids = {item.prediction_id for item in scored[: manifest["selection_k"]]}
    cash_room = max(
        Decimal(0),
        context.cash_balance - context.active_cash_reservations - _decimal(policy, "cash_reserve"),
    )
    gross_room = max(
        Decimal(0),
        _decimal(policy, "maximum_gross_exposure")
        - context.position_gross_exposure
        - context.active_entry_gross_reservations,
    )
    slots = max(
        0,
        policy["maximum_concurrent_positions"]
        - context.current_position_count
        - context.active_entry_reservation_count,
    )
    occupied = set(context.occupied_instrument_ids)
    sessions_since_exit = dict(context.sessions_since_exit)
    volumes = dict(context.prior_completed_session_volume)
    if len(sessions_since_exit) != len(context.sessions_since_exit) or len(volumes) != len(
        context.prior_completed_session_volume
    ):
        raise ValueError("Allocation context maps cannot contain duplicate keys")

    decisions: list[CandidateDecision] = []
    reservations: list[PlannedReservation] = []
    for candidate in ordered:
        reason_codes: list[str] = []
        if candidate.disposition != "SCORED":
            reason_codes.append("PREDICTION_NOT_SCORED")
        elif candidate.prediction_id not in selected_prediction_ids:
            reason_codes.append("OUTSIDE_SELECTION_K")
        elif global_blockers:
            reason_codes.extend(global_blockers)
        elif candidate.reference_kind != _CLOSE_REFERENCE_KIND:
            reason_codes.append("REFERENCE_IS_NOT_SEALED_SESSION_CLOSE")
        elif candidate.asset_class != "US_COMMON_EQUITY":
            reason_codes.append("ASSET_CLASS_NOT_SUPPORTED")
        elif candidate.currency != policy["currency"]:
            reason_codes.append("CURRENCY_MISMATCH")
        elif candidate.instrument_id in occupied:
            reason_codes.append("POSITION_OR_RESERVATION_ALREADY_EXISTS")
        elif sessions_since_exit.get(candidate.instrument_id, rules.cooldown_sessions + 1) <= (
            rules.cooldown_sessions
        ):
            reason_codes.append("REENTRY_COOLDOWN_ACTIVE")
        elif slots <= 0:
            reason_codes.append("MAXIMUM_CONCURRENT_POSITIONS_REACHED")
        elif candidate.instrument_id not in volumes or volumes[candidate.instrument_id] <= 0:
            reason_codes.append("PRIOR_SESSION_VOLUME_UNAVAILABLE")

        if reason_codes:
            decisions.append(
                CandidateDecision(
                    candidate.prediction_id,
                    candidate.instrument_id,
                    candidate.rank,
                    CandidateDisposition.BLOCKED,
                    tuple(reason_codes),
                    None,
                )
            )
            continue

        raw_limit = _multiply(
            candidate.reference_price, Decimal(1) + rules.price_cap_buffer_fraction
        )
        limit_price = _multiply(
            Decimal(_floor_ratio(raw_limit, context.price_tick)), context.price_tick
        )
        if limit_price <= 0 or limit_price > raw_limit:
            reason_codes.append("PRICE_CAP_NOT_REPRESENTABLE")
        else:
            per_share_reserved = _multiply(limit_price, Decimal(1) + rules.cost_buffer_fraction)
            position_ceiling = min(
                _decimal(policy, "maximum_position_cost"),
                _multiply(
                    _decimal(policy, "paper_starting_capital"),
                    _decimal(policy, "maximum_position_fraction"),
                ),
                rules.per_entry_notional_ceiling,
            )
            budget = min(position_ceiling, cash_room, gross_room)
            budget_quantity = _floor_ratio(budget, per_share_reserved)
            participation_quantity = _floor_whole_shares(
                _multiply(
                    Decimal(volumes[candidate.instrument_id]),
                    _decimal(policy, "participation_limit"),
                )
            )
            quantity = min(budget_quantity, participation_quantity)
            while quantity > 0 and _multiply(per_share_reserved, Decimal(quantity)) > budget:
                quantity -= 1
            if quantity <= 0:
                reason_codes.append("OWNER_CAP_OR_PARTICIPATION_PREVENTS_ENTRY")

        if reason_codes:
            decisions.append(
                CandidateDecision(
                    candidate.prediction_id,
                    candidate.instrument_id,
                    candidate.rank,
                    CandidateDisposition.BLOCKED,
                    tuple(reason_codes),
                    None,
                )
            )
            continue

        reserved_cash = _multiply(per_share_reserved, Decimal(quantity))
        key_payload = {
            "strategy_hash": manifest["content_hash"],
            "capital_policy_hash": policy["content_hash"],
            "execution_episode_hash": context.execution_episode_hash,
            "prediction_id": candidate.prediction_id,
            "instrument_id": candidate.instrument_id,
            "target_execution_session": context.target_execution_session,
            "quantity": quantity,
            "limit_price": format(limit_price, "f"),
        }
        reservation = PlannedReservation(
            reservation_key="sr_"
            + domain_separated_sha256(
                "qc2.strategy-reservation.v1", canonical_json_bytes(key_payload)
            ),
            prediction_id=candidate.prediction_id,
            instrument_id=candidate.instrument_id,
            quantity_whole_shares=quantity,
            limit_price=limit_price,
            reserved_cash=reserved_cash,
            currency=policy["currency"],
        )
        action = ProposedPaperAction(
            action_kind=ProposedActionKind.OPEN_LONG,
            prediction_id=candidate.prediction_id,
            instrument_id=candidate.instrument_id,
            prediction_rank=candidate.rank,
            execution_episode_hash=context.execution_episode_hash,
            account_mode="PAPER",
            side="BUY",
            quantity_whole_shares=quantity,
            reference_kind=candidate.reference_kind,
            sealed_reference_close=candidate.reference_price,
            price_cap_ceiling=raw_limit,
            limit_price=limit_price,
            order_type="LIMIT",
            time_in_force="DAY",
            session_restriction="REGULAR_SESSION_ONLY",
            target_execution_session=context.target_execution_session,
            extended_hours=False,
            currency=policy["currency"],
            reason_codes=(
                "RANK_SELECTED",
                "SEALED_CLOSE_PRICE_CAP",
                "WHOLE_SHARE_FLOOR",
                "OWNER_CAP_INTERSECTION",
                "NO_SHORT_OR_PYRAMIDING",
            ),
            rule_trace=(
                RANK_RULE,
                ALLOCATION_ORDER,
                PRICE_CAP_RULE,
                RESERVATION_POLICY,
            ),
            reservation=reservation,
        )
        decisions.append(
            CandidateDecision(
                candidate.prediction_id,
                candidate.instrument_id,
                candidate.rank,
                CandidateDisposition.PROPOSED,
                action.reason_codes,
                action,
            )
        )
        reservations.append(reservation)
        occupied.add(candidate.instrument_id)
        cash_room -= reserved_cash
        gross_room -= reserved_cash
        slots -= 1

    input_hash = _allocation_inputs_hash(candidates, context)
    plan_hash = _plan_digest(
        manifest["content_hash"],
        policy["content_hash"],
        input_hash,
        context.execution_episode_hash,
        context.decision_session,
        context.target_execution_session,
        decisions,
    )
    return AllocationPlan(
        strategy_hash=manifest["content_hash"],
        capital_policy_hash=policy["content_hash"],
        input_hash=input_hash,
        execution_episode_hash=context.execution_episode_hash,
        decision_session=context.decision_session,
        target_execution_session=context.target_execution_session,
        decisions=tuple(decisions),
        reservations=tuple(reservations),
        plan_hash=plan_hash,
    )


def assess_daily_exit(
    position: PositionSnapshot,
    bar: CompletedDailyBar,
    rules: StrategyRules,
) -> ExitAssessment:
    """Classify daily-bar exit triggers without asserting an intraday fill sequence."""
    if not bar.complete:
        raise ValueError("Exit assessment requires a completed daily bar")
    if bar.instrument_id != position.instrument_id:
        raise ValueError("Exit bar instrument does not match the held position")
    if rules.maximum_holding_sessions < 1 or (
        rules.cooldown_sessions < 0
        or any(
            value is not None and not Decimal(0) < value < Decimal(1)
            for value in (
                rules.stop_loss_fraction,
                rules.target_gain_fraction,
                rules.trailing_stop_fraction,
            )
        )
    ):
        raise ValueError("Exit assessment received unresolved or invalid strategy rules")
    if position.owned_shares <= 0 or position.entry_price <= 0:
        raise ValueError("Exit assessment requires a positive long position")
    if bar.session_ordinal <= position.entry_session_ordinal:
        raise ValueError("Exit bar must follow the position entry session")
    if not _session_is_valid(bar.session_id) or position.completed_sessions_held < 0:
        raise ValueError("Exit assessment requires a valid session and holding count")
    if any(
        value <= 0
        for value in (
            bar.open_price,
            bar.high_price,
            bar.low_price,
            bar.close_price,
        )
    ):
        raise ValueError("Daily bar prices must be positive")
    if bar.high_price < max(bar.open_price, bar.close_price, bar.low_price):
        raise ValueError("Daily bar high is inconsistent")
    if bar.low_price > min(bar.open_price, bar.close_price, bar.high_price):
        raise ValueError("Daily bar low is inconsistent")

    stop_levels: list[Decimal] = []
    if rules.stop_loss_fraction is not None:
        stop_levels.append(position.entry_price * (Decimal(1) - rules.stop_loss_fraction))
    if rules.trailing_stop_fraction is not None:
        if position.prior_peak_price is None or position.prior_peak_price <= 0:
            raise ValueError("Trailing exit requires a peak from prior completed sessions")
        stop_levels.append(position.prior_peak_price * (Decimal(1) - rules.trailing_stop_fraction))
    stop_level = max(stop_levels) if stop_levels else None
    target_level = (
        None
        if rules.target_gain_fraction is None
        else position.entry_price * (Decimal(1) + rules.target_gain_fraction)
    )
    stop_touched = stop_level is not None and bar.low_price <= stop_level
    target_touched = target_level is not None and bar.high_price >= target_level
    if stop_touched and target_touched:
        stop_return = stop_level / position.entry_price - Decimal(1)
        target_return = target_level / position.entry_price - Decimal(1)
        return ExitAssessment(
            signal=ExitSignal.INTRADAY_PATH_AMBIGUOUS,
            possible_triggers=("STOP", "TARGET"),
            threshold_price=None,
            conservative_scenario_return=min(stop_return, target_return),
        )
    if stop_touched:
        return ExitAssessment(
            signal=ExitSignal.STOP_LEVEL_CROSSED,
            possible_triggers=("STOP",),
            threshold_price=stop_level,
            conservative_scenario_return=stop_level / position.entry_price - Decimal(1),
        )
    if target_touched:
        return ExitAssessment(
            signal=ExitSignal.TARGET_LEVEL_CROSSED,
            possible_triggers=("TARGET",),
            threshold_price=target_level,
            conservative_scenario_return=target_level / position.entry_price - Decimal(1),
        )
    if position.completed_sessions_held >= rules.maximum_holding_sessions:
        return ExitAssessment(
            signal=ExitSignal.TIME_EXIT_DUE,
            possible_triggers=("MAXIMUM_HOLDING_SESSIONS",),
            threshold_price=None,
            conservative_scenario_return=None,
        )
    return ExitAssessment(ExitSignal.HOLD, (), None, None)


def classify_fill_feedback(requested_shares: int, filled_shares: int) -> ExecutionFillFeedback:
    """Classify an execution result only; no prediction or scientific label is accepted."""
    if (
        not isinstance(requested_shares, int)
        or not isinstance(filled_shares, int)
        or isinstance(requested_shares, bool)
        or isinstance(filled_shares, bool)
        or requested_shares <= 0
        or filled_shares < 0
        or filled_shares > requested_shares
    ):
        raise ValueError("Fill quantities must be whole shares within the requested quantity")
    if filled_shares == 0:
        classification = FillClassification.NO_FILL
    elif filled_shares == requested_shares:
        classification = FillClassification.FULL_FILL
    else:
        classification = FillClassification.PARTIAL_FILL
    return ExecutionFillFeedback(
        classification=classification,
        requested_shares=requested_shares,
        filled_shares=filled_shares,
        unfilled_shares=requested_shares - filled_shares,
    )
