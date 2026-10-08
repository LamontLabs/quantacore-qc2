"""Immutable inputs and outputs for independent Ground Truth resolution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from qc2_contracts.runtime import (
    CONTENT_ADDRESSED,
    canonical_content_hash,
    validate_contract,
    verify_content_hash,
)

from .label_models import LabelInput
from .models import ContractRef, as_date, as_utc

OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
OUTCOME_REVISION_SCHEMA = "qc2.outcomes_research.OutcomeRevision.v1"
RUNNER_EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
SYMBOL_ASSIGNMENT_SCHEMA = "qc2.identity_market.SymbolAssignment.v1"
CORPORATE_ACTION_SCHEMA = "qc2.identity_market.CorporateActionRecord.v1"
MARKET_SNAPSHOT_REVISION_SCHEMA = "qc2.identity_market.MarketSnapshotRevision.v1"
CONFIGURATION_MANIFEST_SCHEMA = "qc2.integrity_build.ConfigurationManifest.v1"

_SLUG = re.compile(r"^[a-z][a-z0-9_.:-]{0,159}$")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9./-]{0,31}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class GroundTruthError(ValueError):
    """Ground Truth inputs or append-only interfaces violate their contracts."""


@dataclass(frozen=True, slots=True)
class FrozenContractRecord:
    """A validated contract retained as canonical immutable JSON bytes."""

    contract_name: str
    canonical_json: str

    def __post_init__(self) -> None:
        try:
            payload = json.loads(self.canonical_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise GroundTruthError("frozen contract must contain canonical JSON") from exc
        if not isinstance(payload, dict):
            raise GroundTruthError("frozen contract payload must be an object")
        validate_contract(self.contract_name, payload)
        if self.contract_name in CONTENT_ADDRESSED:
            verify_content_hash(self.contract_name, payload)
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        if canonical != self.canonical_json:
            raise GroundTruthError("frozen contract JSON is not canonical")

    @property
    def payload(self) -> dict[str, Any]:
        """Return a detached JSON value; callers cannot mutate the stored record."""
        return json.loads(self.canonical_json)

    @property
    def ref(self) -> ContractRef:
        payload = self.payload
        if self.contract_name not in CONTENT_ADDRESSED:
            raise GroundTruthError(
                f"{self.contract_name} is not content-addressed and has no immutable ref"
            )
        return ContractRef(payload["schema_name"], payload["id"], payload["content_hash"])


def freeze_contract_record(
    contract_name: str,
    payload: dict[str, Any],
) -> FrozenContractRecord:
    """Validate, content-address, and freeze a contract payload."""
    if not isinstance(payload, dict):
        raise GroundTruthError("contract payload must be an object")
    record = json.loads(json.dumps(payload, ensure_ascii=False))
    if contract_name in CONTENT_ADDRESSED:
        record["content_hash"] = "0" * 64
        record["content_hash"] = canonical_content_hash(contract_name, record)
    else:
        record.pop("content_hash", None)
    validate_contract(contract_name, record)
    if contract_name in CONTENT_ADDRESSED:
        verify_content_hash(contract_name, record)
    return FrozenContractRecord(
        contract_name,
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
    )


def utc_text(value: datetime | str, field_name: str) -> str:
    return as_utc(value, field_name).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class SymbolAssignmentEvidence:
    """A stable-instrument symbol interval used to resolve ticker changes."""

    assignment_ref: ContractRef
    instrument_ref: ContractRef
    symbol: str
    effective_from: date | str
    effective_to_exclusive: date | str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.assignment_ref, ContractRef)
            or self.assignment_ref.target_schema_name != SYMBOL_ASSIGNMENT_SCHEMA
        ):
            raise GroundTruthError("assignment_ref must reference SymbolAssignment")
        if (
            not isinstance(self.instrument_ref, ContractRef)
            or self.instrument_ref.target_schema_name != INSTRUMENT_SCHEMA
        ):
            raise GroundTruthError("instrument_ref must reference Instrument")
        if not isinstance(self.symbol, str) or not _SYMBOL.fullmatch(self.symbol):
            raise GroundTruthError("symbol must be a normalized uppercase symbol")
        start = as_date(self.effective_from, "symbol effective_from")
        end = (
            as_date(self.effective_to_exclusive, "symbol effective_to_exclusive")
            if self.effective_to_exclusive is not None
            else None
        )
        if end is not None and end <= start:
            raise GroundTruthError("symbol assignment interval must be nonempty")
        object.__setattr__(self, "effective_from", start)
        object.__setattr__(self, "effective_to_exclusive", end)

    def contains(self, session_id: date) -> bool:
        return self.effective_from <= session_id and (
            self.effective_to_exclusive is None or session_id < self.effective_to_exclusive
        )


@dataclass(frozen=True, slots=True)
class TerminalEventEvidence:
    """Terminal cash value per share, normalized to the label reference share basis."""

    event_session: date | str
    status: str
    corporate_action_ref: ContractRef
    cash_consideration_per_share: Decimal | str | int | None = None
    share_basis_key: str | None = None
    currency: str | None = None
    finalized_at: datetime | str | None = None
    evidence_refs: tuple[ContractRef, ...] = ()

    def __post_init__(self) -> None:
        event_session = as_date(self.event_session, "terminal event_session")
        if self.status not in {"VERIFIED_CASH_CONSIDERATION", "UNRESOLVED"}:
            raise GroundTruthError("terminal event status is unsupported")
        if (
            not isinstance(self.corporate_action_ref, ContractRef)
            or self.corporate_action_ref.target_schema_name != CORPORATE_ACTION_SCHEMA
        ):
            raise GroundTruthError("terminal event must reference CorporateActionRecord")
        evidence_refs = tuple(self.evidence_refs)
        if any(not isinstance(ref, ContractRef) for ref in evidence_refs):
            raise GroundTruthError("terminal evidence_refs must be ContractRefs")
        if self.status == "VERIFIED_CASH_CONSIDERATION":
            if (
                self.cash_consideration_per_share is None
                or self.share_basis_key is None
                or self.currency is None
                or self.finalized_at is None
            ):
                raise GroundTruthError(
                    "verified terminal consideration requires per-share amount, share basis, "
                    "currency, and finalization"
                )
            from .models import as_decimal

            amount = as_decimal(
                self.cash_consideration_per_share,
                "cash_consideration_per_share",
            )
            if amount < 0:
                raise GroundTruthError("cash_consideration_per_share cannot be negative")
            if not isinstance(self.share_basis_key, str) or not self.share_basis_key.strip():
                raise GroundTruthError("verified terminal consideration requires a share basis key")
            if not isinstance(self.currency, str) or not _CURRENCY.fullmatch(self.currency):
                raise GroundTruthError("terminal currency must be a three-letter uppercase code")
            object.__setattr__(self, "cash_consideration_per_share", amount)
            object.__setattr__(self, "finalized_at", as_utc(self.finalized_at, "terminal finalized_at"))
        elif any(
            value is not None
            for value in (
                self.cash_consideration_per_share,
                self.share_basis_key,
                self.currency,
                self.finalized_at,
            )
        ):
            raise GroundTruthError("unresolved terminal consideration cannot carry a verified value")
        object.__setattr__(self, "event_session", event_session)
        object.__setattr__(self, "evidence_refs", evidence_refs)


@dataclass(frozen=True, slots=True)
class GroundTruthEligibleRow:
    """One independently eligible instrument/session/label input, without model fields."""

    row_key: str
    definition_key: str
    label_input: LabelInput
    symbol_assignments: tuple[SymbolAssignmentEvidence, ...]
    corporate_action_refs: tuple[ContractRef, ...] = ()
    market_snapshot_refs: tuple[ContractRef, ...] = ()
    terminal_event: TerminalEventEvidence | None = None
    reference_currency: str = "USD"

    def __post_init__(self) -> None:
        if not isinstance(self.row_key, str) or not _SLUG.fullmatch(self.row_key):
            raise GroundTruthError("row_key must be a stable lowercase key")
        if not isinstance(self.definition_key, str) or not _SLUG.fullmatch(self.definition_key):
            raise GroundTruthError("definition_key must be a stable lowercase key")
        if not isinstance(self.label_input, LabelInput):
            raise GroundTruthError("label_input must be a typed LabelInput")
        assignments = tuple(self.symbol_assignments)
        if not assignments or any(
            not isinstance(item, SymbolAssignmentEvidence) for item in assignments
        ):
            raise GroundTruthError("symbol assignment evidence is required")
        instrument_ref = self.label_input.prediction_bar.instrument_ref
        if any(item.instrument_ref != instrument_ref for item in assignments):
            raise GroundTruthError("symbol assignments must resolve to the stable instrument")
        actions = tuple(self.corporate_action_refs)
        if any(
            not isinstance(ref, ContractRef) or ref.target_schema_name != CORPORATE_ACTION_SCHEMA
            for ref in actions
        ):
            raise GroundTruthError("corporate_action_refs must reference CorporateActionRecord")
        snapshots = tuple(self.market_snapshot_refs)
        if any(
            not isinstance(ref, ContractRef)
            or ref.target_schema_name != MARKET_SNAPSHOT_REVISION_SCHEMA
            for ref in snapshots
        ):
            raise GroundTruthError("market_snapshot_refs must reference MarketSnapshotRevision")
        if self.terminal_event is not None:
            if not isinstance(self.terminal_event, TerminalEventEvidence):
                raise GroundTruthError("terminal_event must be typed TerminalEventEvidence")
            if self.label_input.terminal_event_session != self.terminal_event.event_session:
                raise GroundTruthError(
                    "terminal event evidence must match LabelInput.terminal_event_session"
                )
            if (
                self.terminal_event.status == "VERIFIED_CASH_CONSIDERATION"
                and self.terminal_event.share_basis_key
                != self.label_input.prediction_bar.share_basis_key
            ):
                raise GroundTruthError(
                    "terminal cash consideration must use the label reference share basis"
                )
            if self.terminal_event.corporate_action_ref not in actions:
                actions = (*actions, self.terminal_event.corporate_action_ref)
        if not isinstance(self.reference_currency, str) or not _CURRENCY.fullmatch(
            self.reference_currency
        ):
            raise GroundTruthError("reference_currency must be a three-letter uppercase code")
        object.__setattr__(self, "symbol_assignments", assignments)
        object.__setattr__(self, "corporate_action_refs", actions)
        object.__setattr__(self, "market_snapshot_refs", snapshots)


@dataclass(frozen=True, slots=True)
class GroundTruthRowResolution:
    row_key: str
    definition_key: str
    outcome: FrozenContractRecord

    def __post_init__(self) -> None:
        if not isinstance(self.row_key, str) or not _SLUG.fullmatch(self.row_key):
            raise GroundTruthError("row_key must be a stable lowercase key")
        if not isinstance(self.definition_key, str) or not _SLUG.fullmatch(
            self.definition_key
        ):
            raise GroundTruthError("definition_key must be a stable lowercase key")
        if not isinstance(self.outcome, FrozenContractRecord) or self.outcome.contract_name != "Outcome":
            raise GroundTruthError("row resolution must contain a frozen Outcome")


@dataclass(frozen=True, slots=True)
class ActionReviewCase:
    case_id: str
    row_key: str
    outcome_ref: ContractRef
    instrument_ref: ContractRef
    session_id: date
    review_type: str
    reason_code: str
    opened_at: datetime
    evidence_refs: tuple[ContractRef, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not _UUID7.fullmatch(self.case_id):
            raise GroundTruthError("action review case_id must be UUIDv7")
        if not isinstance(self.row_key, str) or not _SLUG.fullmatch(self.row_key):
            raise GroundTruthError("action review row_key must be stable")
        if (
            not isinstance(self.outcome_ref, ContractRef)
            or self.outcome_ref.target_schema_name != OUTCOME_SCHEMA
        ):
            raise GroundTruthError("action review must reference an Outcome")
        if (
            not isinstance(self.instrument_ref, ContractRef)
            or self.instrument_ref.target_schema_name != INSTRUMENT_SCHEMA
        ):
            raise GroundTruthError("action review must reference an Instrument")
        object.__setattr__(self, "session_id", as_date(self.session_id, "review session_id"))
        if self.review_type not in {"CORPORATE_ACTION", "TERMINAL_EVENT"}:
            raise GroundTruthError("action review type is unsupported")
        if not isinstance(self.reason_code, str) or not re.fullmatch(
            r"^[a-z][a-z0-9_-]{0,95}$", self.reason_code
        ):
            raise GroundTruthError("action review reason must be a lowercase code")
        object.__setattr__(self, "opened_at", as_utc(self.opened_at, "review opened_at"))
        refs = tuple(self.evidence_refs)
        if any(not isinstance(ref, ContractRef) for ref in refs):
            raise GroundTruthError("action review evidence must contain ContractRefs")
        object.__setattr__(self, "evidence_refs", refs)


@dataclass(frozen=True, slots=True)
class ActionReviewDecision:
    """A separate review disposition; it never mutates or replaces an Outcome."""

    case_id: str
    decision: str
    evidence_refs: tuple[ContractRef, ...]
    decided_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not _UUID7.fullmatch(self.case_id):
            raise GroundTruthError("action review decision must reference a UUIDv7 case")
        if self.decision not in {
            "ACTION_CONFIRMED",
            "NO_ACTION_CONFIRMED",
            "REMAIN_UNRESOLVED",
        }:
            raise GroundTruthError("action review decision is unsupported")
        refs = tuple(self.evidence_refs)
        if not refs or any(not isinstance(ref, ContractRef) for ref in refs):
            raise GroundTruthError("action review decision requires typed evidence")
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "decided_at", as_utc(self.decided_at, "decision decided_at"))

@dataclass(frozen=True, slots=True)
class GroundTruthBatchResult:
    """All rows supplied to a resolution run, including unresolved outcomes."""

    rows: tuple[GroundTruthRowResolution, ...]
    runner_events: tuple[FrozenContractRecord, ...]
    action_reviews: tuple[ActionReviewCase, ...]

    def __post_init__(self) -> None:
        rows = tuple(self.rows)
        events = tuple(self.runner_events)
        reviews = tuple(self.action_reviews)
        if any(not isinstance(item, GroundTruthRowResolution) for item in rows):
            raise GroundTruthError("GroundTruthBatchResult rows are invalid")
        if any(
            not isinstance(item, FrozenContractRecord) or item.contract_name != "RunnerEvent"
            for item in events
        ):
            raise GroundTruthError("GroundTruthBatchResult events are invalid")
        if any(not isinstance(item, ActionReviewCase) for item in reviews):
            raise GroundTruthError("GroundTruthBatchResult action reviews are invalid")
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "runner_events", events)
        object.__setattr__(self, "action_reviews", reviews)
