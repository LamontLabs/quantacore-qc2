"""Immutable value objects for the pure QC2 paper-strategy framework."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class ProposedActionKind(StrEnum):
    OPEN_LONG = "OPEN_LONG"
    NO_ACTION = "NO_ACTION"


class CandidateDisposition(StrEnum):
    PROPOSED = "PROPOSED"
    BLOCKED = "BLOCKED"


class ExitSignal(StrEnum):
    HOLD = "HOLD"
    STOP_LEVEL_CROSSED = "STOP_LEVEL_CROSSED"
    TARGET_LEVEL_CROSSED = "TARGET_LEVEL_CROSSED"
    TIME_EXIT_DUE = "TIME_EXIT_DUE"
    INTRADAY_PATH_AMBIGUOUS = "INTRADAY_PATH_AMBIGUOUS"


class FillClassification(StrEnum):
    NO_FILL = "NO_FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    FULL_FILL = "FULL_FILL"


@dataclass(frozen=True, slots=True)
class StrategyRules:
    """Explicitly resolved parameters; there are no production defaults."""

    configuration_hash: str
    selection_k: int
    price_cap_buffer_fraction: Decimal
    cost_buffer_fraction: Decimal
    per_entry_notional_ceiling: Decimal
    stop_loss_fraction: Decimal | None
    target_gain_fraction: Decimal | None
    trailing_stop_fraction: Decimal | None
    maximum_holding_sessions: int
    cooldown_sessions: int
    fixture_only: bool


@dataclass(frozen=True, slots=True)
class StrategyCandidate:
    """Prediction projection; the reference price is the sealed decision close."""

    prediction_id: str
    instrument_id: str
    asset_class: str
    session_id: str
    rank: int | None
    disposition: str
    reference_kind: str
    reference_price: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class InstrumentTradingEligibility:
    instrument_id: str
    session_id: str
    classification: str
    classification_verified: bool
    currency: str
    symbol_mapping_verified: bool


@dataclass(frozen=True, slots=True)
class AllocationContext:
    """Caller-supplied reconciled state and measured paper-order capabilities."""

    decision_session: str
    target_execution_session: str
    execution_episode_hash: str
    execution_episode_verified: bool
    is_next_exchange_session: bool
    cash_balance: Decimal
    active_cash_reservations: Decimal
    position_gross_exposure: Decimal
    active_entry_gross_reservations: Decimal
    current_position_count: int
    active_entry_reservation_count: int
    occupied_instrument_ids: frozenset[str]
    sessions_since_exit: tuple[tuple[str, int], ...]
    cooldown_history_complete: bool
    prior_completed_session_volume: tuple[tuple[str, int], ...]
    daily_loss_consumed: Decimal
    reconciliation_current: bool
    exit_actions_resolved: bool
    external_activity_unreconciled: bool
    day_limit_capability_verified: bool
    regular_session_window_verified: bool
    price_tick_verified: bool
    price_tick: Decimal


@dataclass(frozen=True, slots=True)
class PlannedReservation:
    reservation_key: str
    prediction_id: str
    instrument_id: str
    quantity_whole_shares: int
    limit_price: Decimal
    reserved_cash: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class ProposedPaperAction:
    action_kind: ProposedActionKind
    prediction_id: str
    instrument_id: str
    prediction_rank: int
    execution_episode_hash: str
    account_mode: str
    side: str
    quantity_whole_shares: int
    reference_kind: str
    sealed_reference_close: Decimal
    price_cap_ceiling: Decimal
    limit_price: Decimal
    order_type: str
    time_in_force: str
    session_restriction: str
    target_execution_session: str
    extended_hours: bool
    currency: str
    reason_codes: tuple[str, ...]
    rule_trace: tuple[str, ...]
    reservation: PlannedReservation


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    prediction_id: str
    instrument_id: str
    prediction_rank: int | None
    disposition: CandidateDisposition
    reason_codes: tuple[str, ...]
    proposed_action: ProposedPaperAction | None


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    strategy_hash: str
    capital_policy_hash: str
    input_hash: str
    execution_episode_hash: str
    decision_session: str
    target_execution_session: str
    decisions: tuple[CandidateDecision, ...]
    reservations: tuple[PlannedReservation, ...]
    plan_hash: str
    submission_authorized: bool = False

    @property
    def proposed_actions(self) -> tuple[ProposedPaperAction, ...]:
        return tuple(
            decision.proposed_action
            for decision in self.decisions
            if decision.proposed_action is not None
        )


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    instrument_id: str
    owned_shares: Decimal
    entry_price: Decimal
    entry_session_ordinal: int
    completed_sessions_held: int
    prior_peak_price: Decimal | None


@dataclass(frozen=True, slots=True)
class CompletedDailyBar:
    instrument_id: str
    session_id: str
    session_ordinal: int
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    complete: bool


@dataclass(frozen=True, slots=True)
class ExitAssessment:
    signal: ExitSignal
    possible_triggers: tuple[str, ...]
    threshold_price: Decimal | None
    conservative_scenario_return: Decimal | None
    fill_price: None = None


@dataclass(frozen=True, slots=True)
class ActivationReadiness:
    eligible_for_activation: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionFillFeedback:
    classification: FillClassification
    requested_shares: int
    filled_shares: int
    unfilled_shares: int
