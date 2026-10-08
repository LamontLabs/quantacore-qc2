"""Typed inputs and outputs for QC2 label definitions and mature outcomes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from .models import ContractRef, as_date, as_decimal, as_utc, require_sha256

LABEL_DEFINITION_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
LABEL_REGISTRY_SCHEMA = "qc2.scientific_definitions.LabelRegistry.v1"
OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")


class LabelInputError(ValueError):
    """Label definitions or market inputs violate the frozen label contract."""


class ProbabilityTargetUnavailable(LabelInputError):
    """No binary training target exists for the requested label observation."""


@dataclass(frozen=True, slots=True)
class LabelDefinitionSpec:
    stable_key: str
    target_event: str
    horizon_sessions: int
    price_reference: str
    threshold: Decimal | str | int | None
    threshold_unit: str | None
    maturity_rule: str
    release_policy: str

    def __post_init__(self) -> None:
        if not isinstance(self.stable_key, str) or not _SLUG.fullmatch(self.stable_key):
            raise LabelInputError("stable_key must be a lowercase slug")
        if self.target_event not in {
            "EXPANSION_RUNNER",
            "SESSION_MONSTER",
            "CONTINUATION",
            "FAILURE",
            "TIME_TO_EXPANSION",
        }:
            raise LabelInputError("unsupported target_event")
        if type(self.horizon_sessions) is not int or self.horizon_sessions < 1:
            raise LabelInputError("horizon_sessions must be a positive integer")
        if self.price_reference not in {
            "PREDICTION_SESSION_DAILY_CLOSE",
            "NEXT_SESSION_DAILY_OPEN_PROXY",
            "ACTUAL_PAPER_FILL",
            "SPLIT_CONSISTENT_CLOSE",
            "SPLIT_CONSISTENT_HIGH",
            "SPLIT_CONSISTENT_LOW",
        }:
            raise LabelInputError("unsupported price_reference")
        expected_reference = {
            "EXPANSION_RUNNER": "PREDICTION_SESSION_DAILY_CLOSE",
            "SESSION_MONSTER": "SPLIT_CONSISTENT_CLOSE",
            "CONTINUATION": "PREDICTION_SESSION_DAILY_CLOSE",
            "FAILURE": "PREDICTION_SESSION_DAILY_CLOSE",
            "TIME_TO_EXPANSION": "PREDICTION_SESSION_DAILY_CLOSE",
        }[self.target_event]
        if self.price_reference != expected_reference:
            raise LabelInputError(
                f"{self.target_event} requires price_reference={expected_reference}"
            )
        if self.threshold is not None:
            threshold = as_decimal(self.threshold, "threshold")
            object.__setattr__(self, "threshold", threshold)
        if self.target_event in {"EXPANSION_RUNNER", "SESSION_MONSTER"}:
            if self.threshold_unit != "fractional_return":
                raise LabelInputError("runner and monster thresholds must use fractional_return")
        elif self.threshold is not None or self.threshold_unit is not None:
            raise LabelInputError("unavailable label placeholders cannot carry thresholds")
        if self.threshold_unit is not None and (
            not isinstance(self.threshold_unit, str) or not self.threshold_unit.strip()
        ):
            raise LabelInputError("threshold_unit must be nonempty text or None")
        if not isinstance(self.maturity_rule, str) or not self.maturity_rule.strip():
            raise LabelInputError("maturity_rule is required")
        if not isinstance(self.release_policy, str) or not self.release_policy.strip():
            raise LabelInputError("release_policy is required")


@dataclass(frozen=True, slots=True)
class DailyLabelBar:
    """A finalized or pending daily bar with explicit identity and share basis."""

    session_id: date | str
    open_price: Decimal | str | int
    high_price: Decimal | str | int
    low_price: Decimal | str | int
    close_price: Decimal | str | int
    source_ref: ContractRef
    instrument_ref: ContractRef
    adjustment_ref: ContractRef
    share_basis_key: str
    finalized_at: datetime | str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", as_date(self.session_id, "bar session_id"))
        for field_name in ("open_price", "high_price", "low_price", "close_price"):
            value = as_decimal(getattr(self, field_name), field_name)
            if value <= 0:
                raise LabelInputError(f"{field_name} must be positive")
            object.__setattr__(self, field_name, value)
        if self.low_price > min(self.open_price, self.close_price):
            raise LabelInputError("low_price exceeds open_price or close_price")
        if self.high_price < max(self.open_price, self.close_price):
            raise LabelInputError("high_price is below open_price or close_price")
        if self.low_price > self.high_price:
            raise LabelInputError("low_price exceeds high_price")
        expected_refs = {
            "source_ref": "qc2.identity_market.DailyBar.v1",
            "instrument_ref": "qc2.identity_market.Instrument.v1",
            "adjustment_ref": "qc2.identity_market.AdjustmentManifest.v1",
        }
        for field_name, schema_name in expected_refs.items():
            reference = getattr(self, field_name)
            if not isinstance(reference, ContractRef) or reference.target_schema_name != schema_name:
                raise LabelInputError(f"{field_name} must reference {schema_name}")
        if not isinstance(self.share_basis_key, str) or not self.share_basis_key.strip():
            raise LabelInputError("share_basis_key is required")
        if self.finalized_at is not None:
            object.__setattr__(self, "finalized_at", as_utc(self.finalized_at, "bar finalized_at"))


@dataclass(frozen=True, slots=True)
class LabelInput:
    """Calendar-bounded bars and finalization evidence for one prediction session."""

    prediction_bar: DailyLabelBar
    calendar_ref: ContractRef
    calendar_sessions: tuple[date | str, ...]
    observation_session: date | str
    future_bars: tuple[DailyLabelBar, ...]
    corporate_action_status: str
    corporate_action_finalized_at: datetime | str | None
    data_finalization_complete_at: datetime | str | None
    label_release_transaction_complete_at: datetime | str | None
    terminal_event_session: date | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.prediction_bar, DailyLabelBar):
            raise LabelInputError("prediction_bar must be a DailyLabelBar")
        if (
            not isinstance(self.calendar_ref, ContractRef)
            or self.calendar_ref.target_schema_name != "qc2.time_operation.CalendarManifest.v1"
        ):
            raise LabelInputError("calendar_ref must reference CalendarManifest")
        sessions = tuple(as_date(item, "calendar session") for item in self.calendar_sessions)
        if not sessions or any(left >= right for left, right in zip(sessions, sessions[1:])):
            raise LabelInputError("calendar_sessions must be a nonempty, strictly increasing frozen calendar")
        prediction_session = self.prediction_bar.session_id
        if prediction_session not in sessions:
            raise LabelInputError("calendar_sessions must include the prediction session")
        observation = as_date(self.observation_session, "observation_session")
        if observation not in sessions or observation < prediction_session:
            raise LabelInputError("observation_session must be on or after prediction_session in the calendar")
        bars = tuple(self.future_bars)
        if any(not isinstance(bar, DailyLabelBar) for bar in bars):
            raise LabelInputError("future_bars must contain DailyLabelBar inputs")
        bar_sessions = tuple(bar.session_id for bar in bars)
        if any(left >= right for left, right in zip(bar_sessions, bar_sessions[1:])):
            raise LabelInputError("future_bars must be strictly ordered by session")
        calendar_set = set(sessions)
        reference = self.prediction_bar
        if reference.finalized_at is None:
            raise LabelInputError("prediction-session reference bar must be finalized")
        for bar in bars:
            if bar.session_id <= prediction_session or bar.session_id > observation:
                raise LabelInputError("future bars must be after prediction and no later than observation_session")
            if bar.session_id not in calendar_set:
                raise LabelInputError("future bar is not a session in the frozen calendar")
            if bar.instrument_ref != reference.instrument_ref:
                raise LabelInputError("all bars must reference the same instrument revision")
            if bar.adjustment_ref != reference.adjustment_ref:
                raise LabelInputError("all bars must use the same adjustment manifest")
            if bar.share_basis_key != reference.share_basis_key:
                raise LabelInputError("all bars must use the same reference share basis")
        if self.corporate_action_status not in {"FINALIZED", "REVIEW", "UNRESOLVED"}:
            raise LabelInputError("corporate_action_status must be FINALIZED, REVIEW, or UNRESOLVED")
        if self.corporate_action_status == "FINALIZED":
            if self.corporate_action_finalized_at is None:
                raise LabelInputError("finalized corporate-action state requires its finalization instant")
            object.__setattr__(
                self,
                "corporate_action_finalized_at",
                as_utc(self.corporate_action_finalized_at, "corporate_action_finalized_at"),
            )
        elif self.corporate_action_finalized_at is not None:
            object.__setattr__(
                self,
                "corporate_action_finalized_at",
                as_utc(self.corporate_action_finalized_at, "corporate_action_finalized_at"),
            )
        if self.data_finalization_complete_at is not None:
            object.__setattr__(
                self,
                "data_finalization_complete_at",
                as_utc(self.data_finalization_complete_at, "data_finalization_complete_at"),
            )
        if self.label_release_transaction_complete_at is not None:
            object.__setattr__(
                self,
                "label_release_transaction_complete_at",
                as_utc(
                    self.label_release_transaction_complete_at,
                    "label_release_transaction_complete_at",
                ),
            )
        if self.terminal_event_session is not None:
            terminal = as_date(self.terminal_event_session, "terminal_event_session")
            if (
                terminal <= prediction_session
                or terminal not in calendar_set
                or terminal > observation
            ):
                raise LabelInputError(
                    "terminal_event_session must be an observed future session in the frozen calendar"
                )
            object.__setattr__(self, "terminal_event_session", terminal)
        object.__setattr__(self, "calendar_sessions", sessions)
        object.__setattr__(self, "observation_session", observation)
        object.__setattr__(self, "future_bars", bars)


@dataclass(frozen=True, slots=True)
class FieldValidity:
    field_name: str
    status: str
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class SessionMonsterMeasurement:
    session_id: date
    session_offset: int
    monster_return: Decimal
    open_to_high_return: Decimal
    opening_gap_return: Decimal


@dataclass(frozen=True, slots=True)
class LabelOutcome:
    """Pure outcome computation; not a persisted Outcome contract or production feed."""

    definition_key: str
    horizon_sessions: int
    expected_session_ids: tuple[date, ...]
    outcome_state: str
    metrics: Mapping[str, Decimal | str | int | None]
    field_validity: tuple[FieldValidity, ...]
    target_value: bool | None
    target_status: str
    session_monster_measurements: tuple[SessionMonsterMeasurement, ...]
    label_ref: ContractRef
    registry_ref: ContractRef
    reference_bar_ref: ContractRef
    next_open_bar_ref: ContractRef | None
    source_refs: tuple[ContractRef, ...]
    reason_codes: tuple[str, ...]
    available_for_learning_at: datetime | None

    def __post_init__(self) -> None:
        if self.outcome_state not in {
            "PENDING_MATURITY",
            "RESOLVED",
            "PARTIALLY_RESOLVABLE",
            "UNRESOLVED_DATA",
            "CORPORATE_ACTION_REVIEW",
            "CENSORED_TERMINAL_EVENT",
        }:
            raise LabelInputError("invalid outcome_state")
        if self.target_status not in {
            "AVAILABLE",
            "UNAVAILABLE_THRESHOLD",
            "UNAVAILABLE_LABEL",
            "UNAVAILABLE_MATURITY",
            "UNRESOLVED_DATA",
            "CORPORATE_ACTION_REVIEW",
            "CENSORED_TERMINAL_EVENT",
        }:
            raise LabelInputError("invalid target_status")
        if self.target_value is not None and type(self.target_value) is not bool:
            raise LabelInputError("target_value must be bool or None")
        if self.target_value is None and self.target_status == "AVAILABLE":
            raise LabelInputError("an available target requires an explicit boolean value")
        if self.target_value is not None and self.target_status != "AVAILABLE":
            raise LabelInputError("unavailable targets must not carry a boolean value")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


def require_probability_target(outcome: LabelOutcome) -> bool:
    """Return a binary label only when exact semantics and full maturity are available."""
    if not isinstance(outcome, LabelOutcome):
        raise ProbabilityTargetUnavailable("a typed LabelOutcome is required")
    if outcome.outcome_state != "RESOLVED":
        raise ProbabilityTargetUnavailable("full-horizon outcome is not resolved")
    if outcome.target_status != "AVAILABLE" or outcome.target_value is None:
        raise ProbabilityTargetUnavailable(
            f"probability target is unavailable: {outcome.target_status}"
        )
    if outcome.available_for_learning_at is None:
        raise ProbabilityTargetUnavailable("label has no mature learning-release instant")
    return outcome.target_value


def validate_label_reference(ref: ContractRef, field_name: str) -> None:
    if not isinstance(ref, ContractRef):
        raise LabelInputError(f"{field_name} must be a ContractRef")
    require_sha256(ref.content_hash, f"{field_name}.content_hash")
