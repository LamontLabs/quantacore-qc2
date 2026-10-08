"""Census-scoped outcome discovery, coverage accounting, and event episodes."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Iterable

from .ground_truth import (
    _deterministic_uuid7,
    _expected_sessions,
    resolve_eligible_rows,
)
from .ground_truth_models import (
    FrozenContractRecord,
    GroundTruthBatchResult,
    GroundTruthEligibleRow,
    GroundTruthError,
    utc_text,
)
from .label_registry import LabelRegistryBundle
from .models import ContractRef, as_date, as_utc

CANDIDATE_CENSUS_SCHEMA = "qc2.identity_market.CandidateCensus.v1"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
LABEL_DEFINITION_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
RUNNER_EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"

_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SLUG = re.compile(r"^[a-z][a-z0-9_.:-]{0,159}$")
_DEFINED_EVENT_TYPES = {"EXPANSION_RUNNER", "SESSION_MONSTER"}
_QUEUE_STATUSES = {
    "EVENT_DISCOVERED",
    "NO_EVENT",
    "UNSCORABLE",
    "DATA_MISSING",
    "SCIENTIFICALLY_EXCLUDED",
    "ELIGIBILITY_UNVERIFIED",
    "CENSUS_MEMBER_UNOBSERVED",
}
EPISODE_IDENTITY_RULE = (
    "inclusive-transitive-overlap-of-future-exchange-session-windows;"
    "same-instrument-event-type-label-definition;"
    "adjacent-nonoverlapping-windows-remain-distinct;v1"
)
_COVERAGE_SCOPE = "DECLARED_CANDIDATE_CENSUS_ONLY"


def _require_uuid7(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _UUID7.fullmatch(value):
        raise GroundTruthError(f"{field_name} must be UUIDv7")
    return value


def _require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise GroundTruthError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _require_reason_code(value: str, field_name: str = "reason_code") -> str:
    if not isinstance(value, str) or not re.fullmatch(r"^[a-z][a-z0-9_-]{0,95}$", value):
        raise GroundTruthError(f"{field_name} must be a lowercase reason code")
    return value


def _coverage_fraction(numerator: int, denominator: int) -> str | None:
    if denominator == 0:
        return None
    value = (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.000000000001"),
        rounding=ROUND_HALF_EVEN,
    )
    return f"{value:.12f}"


def _record_reference(record: FrozenContractRecord) -> "CensusReference":
    payload = record.payload
    if record.contract_name != "CandidateCensus":
        raise GroundTruthError("observatory input must be a CandidateCensus contract")
    canonical_hash = hashlib.sha256(record.canonical_json.encode("utf-8")).hexdigest()
    return CensusReference(
        census_id=payload["id"],
        canonical_sha256=canonical_hash,
        session_id=as_date(payload["session_id"], "CandidateCensus session_id"),
    )


def _instrument_ref(payload: dict[str, str]) -> ContractRef:
    try:
        schema_name = payload["target_schema_name"]
        target_id = payload["target_id"]
        content_hash = payload.get("content_hash", "0" * 64)
    except (KeyError, TypeError) as exc:
        raise GroundTruthError("CandidateCensus instrument reference is malformed") from exc
    if schema_name != INSTRUMENT_SCHEMA:
        raise GroundTruthError("CandidateCensus members must reference Instrument")
    try:
        return ContractRef(schema_name, target_id, content_hash)
    except ValueError as exc:
        raise GroundTruthError("CandidateCensus instrument reference is invalid") from exc


@dataclass(frozen=True, slots=True)
class CensusReference:
    """Exact local-byte identity for a CandidateCensus contract."""

    census_id: str
    canonical_sha256: str
    session_id: date | str

    def __post_init__(self) -> None:
        _require_uuid7(self.census_id, "census_id")
        _require_sha256(self.canonical_sha256, "census canonical_sha256")
        object.__setattr__(self, "session_id", as_date(self.session_id, "census session_id"))


@dataclass(frozen=True, slots=True)
class ObservatoryCensusMember:
    """Declared scientific disposition and label inputs for one census member."""

    instrument_ref: ContractRef
    eligibility_status: str
    label_rows: tuple[GroundTruthEligibleRow, ...] = ()
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.instrument_ref, ContractRef)
            or self.instrument_ref.target_schema_name != INSTRUMENT_SCHEMA
        ):
            raise GroundTruthError("observatory member must reference an Instrument")
        if self.eligibility_status not in {
            "SCIENTIFICALLY_ELIGIBLE",
            "SCIENTIFICALLY_EXCLUDED",
            "ELIGIBILITY_UNVERIFIED",
        }:
            raise GroundTruthError("observatory member eligibility status is unsupported")
        rows = tuple(self.label_rows)
        if any(not isinstance(row, GroundTruthEligibleRow) for row in rows):
            raise GroundTruthError("observatory member label_rows must be GroundTruthEligibleRow values")
        if any(
            row.label_input.prediction_bar.instrument_ref != self.instrument_ref
            for row in rows
        ):
            raise GroundTruthError("member label rows must match the member Instrument reference")
        definitions = [row.definition_key for row in rows]
        if len(definitions) != len(set(definitions)):
            raise GroundTruthError("member label rows must have unique definition keys")
        if self.eligibility_status == "SCIENTIFICALLY_ELIGIBLE":
            if self.reason_code is not None:
                raise GroundTruthError("eligible census members cannot carry an exclusion reason")
        else:
            if rows:
                raise GroundTruthError("excluded or unverified members cannot carry label rows")
            if self.reason_code is None:
                raise GroundTruthError("excluded or unverified members require a reason code")
            _require_reason_code(self.reason_code)
        object.__setattr__(self, "label_rows", rows)


@dataclass(frozen=True, slots=True)
class ObservatoryCensusInput:
    """One frozen candidate census and the coverage information currently available."""

    candidate_census: FrozenContractRecord
    members: tuple[ObservatoryCensusMember, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_census, FrozenContractRecord)
            or self.candidate_census.contract_name != "CandidateCensus"
        ):
            raise GroundTruthError("candidate_census must be a frozen CandidateCensus contract")
        members = tuple(self.members)
        if any(not isinstance(item, ObservatoryCensusMember) for item in members):
            raise GroundTruthError("census members must be ObservatoryCensusMember values")
        ids = [item.instrument_ref.target_id for item in members]
        if len(ids) != len(set(ids)):
            raise GroundTruthError("census member dispositions must be unique by Instrument")
        object.__setattr__(self, "members", members)


@dataclass(frozen=True, slots=True)
class ObservatoryCoverage:
    """Counts and ratios bounded to one declared CandidateCensus."""

    census_ref: CensusReference
    coverage_scope: str
    market_completeness_established: bool
    census_member_count: int
    member_record_count: int
    unobserved_member_count: int
    eligible_member_count: int
    scientifically_excluded_member_count: int
    eligibility_unverified_member_count: int
    definition_count: int
    expected_label_scan_count: int
    label_input_count: int
    missing_label_input_count: int
    resolved_target_count: int
    unscorable_target_count: int
    member_record_coverage_fraction: str | None
    label_input_coverage_fraction: str | None
    resolved_target_coverage_fraction: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.census_ref, CensusReference):
            raise GroundTruthError("coverage census_ref is invalid")
        if self.coverage_scope != _COVERAGE_SCOPE or self.market_completeness_established:
            raise GroundTruthError("coverage cannot claim scope beyond the declared census")
        counts = (
            self.census_member_count,
            self.member_record_count,
            self.unobserved_member_count,
            self.eligible_member_count,
            self.scientifically_excluded_member_count,
            self.eligibility_unverified_member_count,
            self.definition_count,
            self.expected_label_scan_count,
            self.label_input_count,
            self.missing_label_input_count,
            self.resolved_target_count,
            self.unscorable_target_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise GroundTruthError("coverage counts must be nonnegative integers")
        if self.member_record_count + self.unobserved_member_count != self.census_member_count:
            raise GroundTruthError("coverage must account for every declared census member")
        if (
            self.eligible_member_count
            + self.scientifically_excluded_member_count
            + self.eligibility_unverified_member_count
            != self.member_record_count
        ):
            raise GroundTruthError("coverage member dispositions do not reconcile")
        if self.expected_label_scan_count != self.eligible_member_count * self.definition_count:
            raise GroundTruthError("coverage expected scan count is inconsistent")
        if self.label_input_count + self.missing_label_input_count != self.expected_label_scan_count:
            raise GroundTruthError("coverage label-input counts do not reconcile")
        if (
            self.resolved_target_count
            + self.unscorable_target_count
            + self.missing_label_input_count
            != self.expected_label_scan_count
        ):
            raise GroundTruthError("coverage target-resolution counts do not reconcile")
        for field_name in (
            "member_record_coverage_fraction",
            "label_input_coverage_fraction",
            "resolved_target_coverage_fraction",
        ):
            value = getattr(self, field_name)
            expected_ratio = {
                "member_record_coverage_fraction": _coverage_fraction(
                    self.member_record_count,
                    self.census_member_count,
                ),
                "label_input_coverage_fraction": _coverage_fraction(
                    self.label_input_count,
                    self.expected_label_scan_count,
                ),
                "resolved_target_coverage_fraction": _coverage_fraction(
                    self.resolved_target_count,
                    self.expected_label_scan_count,
                ),
            }[field_name]
            if value != expected_ratio:
                raise GroundTruthError(f"{field_name} does not match its coverage counts")
            if value is not None:
                try:
                    ratio = Decimal(value)
                except (TypeError, ValueError) as exc:
                    raise GroundTruthError(f"{field_name} must be an exact decimal") from exc
                if not ratio.is_finite() or ratio < 0 or ratio > 1:
                    raise GroundTruthError(f"{field_name} must be between zero and one")


@dataclass(frozen=True, slots=True)
class EventEpisode:
    """A deterministic transitive component of overlapping qualifying target windows."""

    episode_id: str
    policy_hash: str
    episode_rule: str
    instrument_ref: ContractRef
    event_type: str
    label_ref: ContractRef
    target_window_start: date | str
    target_window_end: date | str
    event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.episode_id, "episode_id")
        _require_sha256(self.policy_hash, "episode policy_hash")
        if self.episode_rule != EPISODE_IDENTITY_RULE:
            raise GroundTruthError("episode identity rule is not the frozen rule")
        if (
            not isinstance(self.instrument_ref, ContractRef)
            or self.instrument_ref.target_schema_name != INSTRUMENT_SCHEMA
        ):
            raise GroundTruthError("episode must reference an Instrument")
        if self.event_type not in {"EXPANSION_RUNNER", "SESSION_MONSTER", "NEAR_RUNNER", "FAILURE"}:
            raise GroundTruthError("episode event_type is unsupported")
        if (
            not isinstance(self.label_ref, ContractRef)
            or self.label_ref.target_schema_name != LABEL_DEFINITION_SCHEMA
        ):
            raise GroundTruthError("episode must reference a LabelDefinition")
        start = as_date(self.target_window_start, "episode target_window_start")
        end = as_date(self.target_window_end, "episode target_window_end")
        if end < start:
            raise GroundTruthError("episode target window must be nonempty")
        event_ids = tuple(sorted(set(self.event_ids)))
        if not event_ids:
            raise GroundTruthError("an event episode requires at least one RunnerEvent")
        for event_id in event_ids:
            _require_uuid7(event_id, "episode event_id")
        object.__setattr__(self, "target_window_start", start)
        object.__setattr__(self, "target_window_end", end)
        object.__setattr__(self, "event_ids", event_ids)


@dataclass(frozen=True, slots=True)
class EventDiscoveryQueueItem:
    """A confirmed, negative, missing, excluded, or unscorable census scan result."""

    queue_id: str
    queued_at: str
    census_ref: CensusReference
    instrument_ref: ContractRef
    definition_key: str
    definition_ref: ContractRef
    status: str
    reason_codes: tuple[str, ...]
    outcome_ref: ContractRef | None
    event_ids: tuple[str, ...]
    episode_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_uuid7(self.queue_id, "queue_id")
        if not isinstance(self.queued_at, str) or not self.queued_at.endswith("Z"):
            raise GroundTruthError("queued_at must be a canonical UTC instant")
        try:
            if utc_text(as_utc(self.queued_at, "queued_at"), "queued_at") != self.queued_at:
                raise GroundTruthError("queued_at must use canonical UTC formatting")
        except ValueError as exc:
            raise GroundTruthError("queued_at must be a canonical UTC instant") from exc
        if not isinstance(self.census_ref, CensusReference):
            raise GroundTruthError("queue item census_ref is invalid")
        if (
            not isinstance(self.instrument_ref, ContractRef)
            or self.instrument_ref.target_schema_name != INSTRUMENT_SCHEMA
        ):
            raise GroundTruthError("queue item must reference an Instrument")
        if not isinstance(self.definition_key, str) or not _SLUG.fullmatch(self.definition_key):
            raise GroundTruthError("queue item definition_key is invalid")
        if (
            not isinstance(self.definition_ref, ContractRef)
            or self.definition_ref.target_schema_name != LABEL_DEFINITION_SCHEMA
        ):
            raise GroundTruthError("queue item must reference a LabelDefinition")
        if self.status not in _QUEUE_STATUSES:
            raise GroundTruthError("queue item status is unsupported")
        reasons = tuple(self.reason_codes)
        for reason in reasons:
            _require_reason_code(reason, "reason_code")
        event_ids = tuple(sorted(set(self.event_ids)))
        episode_ids = tuple(sorted(set(self.episode_ids)))
        for event_id in event_ids:
            _require_uuid7(event_id, "queue item event_id")
        for episode_id in episode_ids:
            _require_sha256(episode_id, "queue item episode_id")
        if self.outcome_ref is not None and (
            not isinstance(self.outcome_ref, ContractRef)
            or self.outcome_ref.target_schema_name != OUTCOME_SCHEMA
        ):
            raise GroundTruthError("queue item outcome_ref must reference an Outcome")
        if self.status == "EVENT_DISCOVERED":
            if self.outcome_ref is None or not event_ids or reasons:
                raise GroundTruthError("discovered events require an outcome and event records")
        elif self.status == "NO_EVENT":
            if self.outcome_ref is None or event_ids or reasons:
                raise GroundTruthError("resolved non-events require an outcome and no event records")
        elif self.status == "UNSCORABLE":
            if self.outcome_ref is None or event_ids or not reasons:
                raise GroundTruthError("unscorable scans require an outcome and reason")
        elif self.status == "DATA_MISSING":
            if self.outcome_ref is not None or event_ids or not reasons:
                raise GroundTruthError("missing data scans require a reason and no outcome")
        elif self.status == "SCIENTIFICALLY_EXCLUDED":
            if self.outcome_ref is not None or event_ids or not reasons:
                raise GroundTruthError("excluded scans require a reason and no outcome")
        elif self.status == "ELIGIBILITY_UNVERIFIED":
            if self.outcome_ref is not None or event_ids or not reasons:
                raise GroundTruthError("unverified scans require a reason and no outcome")
        elif self.status == "CENSUS_MEMBER_UNOBSERVED":
            if self.outcome_ref is not None or event_ids or not reasons:
                raise GroundTruthError("unobserved census members require a reason and no outcome")
        if not event_ids and episode_ids:
            raise GroundTruthError("only event queue items may reference episodes")
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(self, "event_ids", event_ids)
        object.__setattr__(self, "episode_ids", episode_ids)


@dataclass(frozen=True, slots=True)
class EventDiscoveryQueue:
    """Immutable research-consumer queue snapshot with deterministic replay identity."""

    policy_hash: str
    episode_rule: str
    census_refs: tuple[CensusReference, ...]
    items: tuple[EventDiscoveryQueueItem, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.policy_hash, "queue policy_hash")
        if self.episode_rule != EPISODE_IDENTITY_RULE:
            raise GroundTruthError("queue episode identity rule is not the frozen rule")
        census_refs = tuple(self.census_refs)
        if any(not isinstance(item, CensusReference) for item in census_refs):
            raise GroundTruthError("queue census_refs are invalid")
        census_ids = [item.census_id for item in census_refs]
        if len(census_ids) != len(set(census_ids)):
            raise GroundTruthError("queue census_refs must be unique")
        items = tuple(self.items)
        if any(not isinstance(item, EventDiscoveryQueueItem) for item in items):
            raise GroundTruthError("queue items are invalid")
        if any(item.census_ref.census_id not in set(census_ids) for item in items):
            raise GroundTruthError("queue item refers to a census outside this queue")
        queue_ids = [item.queue_id for item in items]
        if len(queue_ids) != len(set(queue_ids)):
            raise GroundTruthError("queue ids must be unique")
        object.__setattr__(self, "census_refs", census_refs)
        object.__setattr__(self, "items", items)

    @property
    def content_hash(self) -> str:
        payload = {
            "policy_hash": self.policy_hash,
            "censuses": [
                {
                    "census_id": item.census_id,
                    "canonical_sha256": item.canonical_sha256,
                    "session_id": item.session_id.isoformat(),
                }
                for item in self.census_refs
            ],
            "items": [
                {
                    "queue_id": item.queue_id,
                    "census_id": item.census_ref.census_id,
                    "instrument_id": item.instrument_ref.target_id,
                    "definition_key": item.definition_key,
                    "status": item.status,
                    "reason_codes": item.reason_codes,
                    "outcome_ref": (
                        item.outcome_ref.to_payload() if item.outcome_ref is not None else None
                    ),
                    "event_ids": item.event_ids,
                    "episode_ids": item.episode_ids,
                }
                for item in self.items
            ],
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class RunnerObservatoryResult:
    """Census-bound outcomes, coverage, event records, episodes, and discovery queue."""

    policy_hash: str
    coverage: tuple[ObservatoryCoverage, ...]
    ground_truth_batches: tuple[GroundTruthBatchResult, ...]
    runner_events: tuple[FrozenContractRecord, ...]
    episodes: tuple[EventEpisode, ...]
    event_queue: EventDiscoveryQueue
    market_completeness_established: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.policy_hash, "observatory policy_hash")
        if self.market_completeness_established:
            raise GroundTruthError("Runner Observatory cannot claim all-market completeness")
        coverage = tuple(self.coverage)
        batches = tuple(self.ground_truth_batches)
        events = tuple(self.runner_events)
        episodes = tuple(self.episodes)
        if any(not isinstance(item, ObservatoryCoverage) for item in coverage):
            raise GroundTruthError("Runner Observatory coverage is invalid")
        if any(not isinstance(item, GroundTruthBatchResult) for item in batches):
            raise GroundTruthError("Runner Observatory Ground Truth batches are invalid")
        if any(
            not isinstance(item, FrozenContractRecord) or item.contract_name != "RunnerEvent"
            for item in events
        ):
            raise GroundTruthError("Runner Observatory event records are invalid")
        if any(not isinstance(item, EventEpisode) for item in episodes):
            raise GroundTruthError("Runner Observatory episodes are invalid")
        if (
            not isinstance(self.event_queue, EventDiscoveryQueue)
            or self.event_queue.policy_hash != self.policy_hash
        ):
            raise GroundTruthError("Runner Observatory event queue policy is inconsistent")
        if len(coverage) != len(self.event_queue.census_refs):
            raise GroundTruthError("Runner Observatory coverage must account for every census")
        object.__setattr__(self, "coverage", coverage)
        object.__setattr__(self, "ground_truth_batches", batches)
        object.__setattr__(self, "runner_events", events)
        object.__setattr__(self, "episodes", episodes)


def _policy_hash(
    registry: LabelRegistryBundle,
    definition_keys: tuple[str, ...],
) -> str:
    definitions = []
    for key in sorted(definition_keys):
        try:
            spec = next(item for item in registry.definitions if item.stable_key == key)
            contract = registry.definition_contracts[key]
        except (KeyError, StopIteration) as exc:
            raise GroundTruthError(f"unknown observatory label definition: {key}") from exc
        definitions.append(
            {
                "stable_key": key,
                "definition_ref": {
                    "target_schema_name": LABEL_DEFINITION_SCHEMA,
                    "target_id": contract["id"],
                    "content_hash": contract["content_hash"],
                },
                "target_event": spec.target_event,
                "horizon_sessions": spec.horizon_sessions,
                "threshold": str(spec.threshold) if spec.threshold is not None else None,
            }
        )
    payload = {
        "policy_name": "qc2-runner-observatory",
        "version": 1,
        "episode_rule": EPISODE_IDENTITY_RULE,
        "definitions": definitions,
        "scope": _COVERAGE_SCOPE,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _candidate_instruments(
    record: FrozenContractRecord,
) -> tuple[dict[str, ContractRef], CensusReference]:
    if record.contract_name != "CandidateCensus":
        raise GroundTruthError("Runner Observatory only accepts CandidateCensus records")
    payload = record.payload
    reference = _record_reference(record)
    refs = [_instrument_ref(item) for item in payload["instrument_refs"]]
    by_id = {item.target_id: item for item in refs}
    if len(by_id) != len(refs):
        raise GroundTruthError("CandidateCensus contains duplicate Instrument members")
    ordered_ids = sorted(by_id)
    membership_material = "qc2-candidate-membership-v1\n" + "\n".join(ordered_ids)
    expected_hash = hashlib.sha256(membership_material.encode("ascii")).hexdigest()
    if payload["membership_hash"] != expected_hash:
        raise GroundTruthError("CandidateCensus membership_hash does not match its members")
    return by_id, reference


def _outcome_ref(record: FrozenContractRecord) -> ContractRef:
    payload = record.payload
    if record.contract_name != "Outcome":
        raise GroundTruthError("expected a frozen Outcome record")
    return ContractRef(payload["schema_name"], payload["id"], payload["content_hash"])


def _definition_ref(registry: LabelRegistryBundle, definition_key: str) -> ContractRef:
    return registry.definition_ref(definition_key)


def _queue_item(
    *,
    created_at: datetime,
    census_ref: CensusReference,
    instrument_ref: ContractRef,
    definition_key: str,
    definition_ref: ContractRef,
    status: str,
    reason_codes: tuple[str, ...] = (),
    outcome_ref: ContractRef | None = None,
    event_ids: tuple[str, ...] = (),
) -> EventDiscoveryQueueItem:
    identity_payload = {
        "census_id": census_ref.census_id,
        "census_sha256": census_ref.canonical_sha256,
        "instrument_id": instrument_ref.target_id,
        "definition_key": definition_key,
        "definition_ref": definition_ref.to_payload(),
        "status": status,
        "reasons": reason_codes,
        "outcome_ref": outcome_ref.to_payload() if outcome_ref is not None else None,
        "event_ids": tuple(sorted(event_ids)),
    }
    identity = json.dumps(identity_payload, sort_keys=True, separators=(",", ":"))
    queue_id = _deterministic_uuid7(created_at, f"observatory-queue-v1:{identity}")
    return EventDiscoveryQueueItem(
        queue_id=queue_id,
        queued_at=utc_text(created_at, "event queue queued_at"),
        census_ref=census_ref,
        instrument_ref=instrument_ref,
        definition_key=definition_key,
        definition_ref=definition_ref,
        status=status,
        reason_codes=reason_codes,
        outcome_ref=outcome_ref,
        event_ids=event_ids,
        episode_ids=(),
    )


def _episode_groups(
    event_windows: list[
        tuple[EventDiscoveryQueueItem, ContractRef, str, date, date, str]
    ],
    policy_hash: str,
) -> tuple[tuple[EventEpisode, ...], dict[str, set[str]]]:
    grouped: dict[
        tuple[str, str, str],
        list[tuple[EventDiscoveryQueueItem, str, date, date]],
    ] = {}
    for queue_item, instrument_ref, event_type, start, end, event_id in event_windows:
        definition_id = queue_item.definition_ref.target_id
        key = (instrument_ref.target_id, event_type, definition_id)
        grouped.setdefault(key, []).append((queue_item, event_id, start, end))

    episodes: list[EventEpisode] = []
    queue_episodes: dict[str, set[str]] = {}
    for (instrument_id, event_type, definition_id), windows in sorted(grouped.items()):
        windows.sort(
            key=lambda item: (
                item[2],
                item[3],
                item[0].census_ref.session_id,
                item[1],
            )
        )
        components: list[list[tuple[EventDiscoveryQueueItem, str, date, date]]] = []
        component_end: date | None = None
        for window in windows:
            if not components or component_end is None or window[2] > component_end:
                components.append([window])
                component_end = window[3]
            else:
                components[-1].append(window)
                component_end = max(component_end, window[3])
        for component in components:
            first = min(item[2] for item in component)
            last = max(item[3] for item in component)
            event_ids = tuple(sorted({item[1] for item in component}))
            first_queue = component[0][0]
            identity = {
                "policy_hash": policy_hash,
                "instrument_id": instrument_id,
                "event_type": event_type,
                "label_definition_id": definition_id,
                "root_target_window_session": first.isoformat(),
            }
            episode_id = hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            label_ref = first_queue.definition_ref
            instrument_ref = next(
                item[0].instrument_ref
                for item in component
                if item[0].instrument_ref.target_id == instrument_id
            )
            episode = EventEpisode(
                episode_id=episode_id,
                policy_hash=policy_hash,
                episode_rule=EPISODE_IDENTITY_RULE,
                instrument_ref=instrument_ref,
                event_type=event_type,
                label_ref=label_ref,
                target_window_start=first,
                target_window_end=last,
                event_ids=event_ids,
            )
            episodes.append(episode)
            for queue_item, _, _, _ in component:
                queue_episodes.setdefault(queue_item.queue_id, set()).add(episode_id)
    episodes.sort(
        key=lambda item: (
            item.instrument_ref.target_id,
            item.event_type,
            item.label_ref.target_id,
            item.target_window_start,
            item.episode_id,
        )
    )
    return tuple(episodes), queue_episodes


def scan_runner_observatory(
    registry: LabelRegistryBundle,
    census_inputs: Iterable[ObservatoryCensusInput],
    *,
    definition_keys: Iterable[str],
    created_at: datetime | str,
) -> RunnerObservatoryResult:
    """Scan every declared eligible census member without model or rank inputs.

    A batch may contain multiple session censuses so overlapping target windows
    can be grouped into stable event episodes. Missing members and label inputs
    stay in the discovery queue; unresolved outcomes are never dropped.
    """
    if not isinstance(registry, LabelRegistryBundle):
        raise GroundTruthError("Runner Observatory requires a validated LabelRegistryBundle")
    census_batches = tuple(census_inputs)
    if not census_batches or any(
        not isinstance(item, ObservatoryCensusInput) for item in census_batches
    ):
        raise GroundTruthError("at least one ObservatoryCensusInput is required")
    keys = tuple(definition_keys)
    if not keys or any(not isinstance(key, str) or not _SLUG.fullmatch(key) for key in keys):
        raise GroundTruthError("definition_keys must name at least one frozen label definition")
    if len(keys) != len(set(keys)):
        raise GroundTruthError("definition_keys must be unique")
    policy_hash = _policy_hash(registry, keys)
    created = as_utc(created_at, "Runner Observatory created_at")

    prepared: list[
        tuple[
            ObservatoryCensusInput,
            dict[str, ContractRef],
            CensusReference,
            dict[str, ObservatoryCensusMember],
        ]
    ] = []
    seen_sessions: set[date] = set()
    seen_census_ids: set[str] = set()
    for census_input in census_batches:
        census_members, census_ref = _candidate_instruments(census_input.candidate_census)
        if census_ref.session_id in seen_sessions:
            raise GroundTruthError("Runner Observatory accepts only one CandidateCensus per session")
        if census_ref.census_id in seen_census_ids:
            raise GroundTruthError("Runner Observatory census ids must be unique")
        seen_sessions.add(census_ref.session_id)
        seen_census_ids.add(census_ref.census_id)
        member_by_id = {item.instrument_ref.target_id: item for item in census_input.members}
        for member_id, member in member_by_id.items():
            declared_ref = census_members.get(member_id)
            if declared_ref is None:
                raise GroundTruthError("observatory member is outside the CandidateCensus")
            if (
                declared_ref.content_hash != "0" * 64
                and declared_ref.content_hash != member.instrument_ref.content_hash
            ):
                raise GroundTruthError("observatory member Instrument revision differs from census")
            if member.eligibility_status == "SCIENTIFICALLY_ELIGIBLE":
                for row in member.label_rows:
                    if row.definition_key not in keys:
                        raise GroundTruthError(
                            "eligible label row uses a definition outside the frozen scan policy"
                        )
                    if row.label_input.prediction_bar.session_id != census_ref.session_id:
                        raise GroundTruthError("label row session differs from CandidateCensus")
        prepared.append((census_input, census_members, census_ref, member_by_id))
    prepared.sort(key=lambda item: (item[2].session_id, item[2].census_id))

    definition_specs = {
        key: next(item for item in registry.definitions if item.stable_key == key)
        for key in keys
    }
    coverage_rows: list[ObservatoryCoverage] = []
    ground_truth_batches: list[GroundTruthBatchResult] = []
    scoped_events: list[FrozenContractRecord] = []
    pending_items: list[EventDiscoveryQueueItem] = []
    event_windows: list[
        tuple[EventDiscoveryQueueItem, ContractRef, str, date, date, str]
    ] = []

    for census_input, census_members, census_ref, member_by_id in prepared:
        instrument_refs = census_members
        expected_rows: dict[tuple[str, str], GroundTruthEligibleRow] = {}
        for instrument_id, member in member_by_id.items():
            if member.eligibility_status != "SCIENTIFICALLY_ELIGIBLE":
                continue
            for row in member.label_rows:
                key = (instrument_id, row.definition_key)
                if key in expected_rows:
                    raise GroundTruthError("duplicate eligible instrument/definition scan row")
                expected_rows[key] = row

        batch = resolve_eligible_rows(
            registry,
            expected_rows.values(),
            created_at=created,
        )
        ground_truth_batches.append(batch)
        resolutions_by_row = {
            (item.row_key, item.definition_key): item for item in batch.rows
        }
        events_by_outcome: dict[str, list[FrozenContractRecord]] = {}
        for event in batch.runner_events:
            outcome_id = event.payload["outcome_ref"]["target_id"]
            events_by_outcome.setdefault(outcome_id, []).append(event)

        local_items: list[EventDiscoveryQueueItem] = []
        for instrument_id in sorted(instrument_refs):
            census_instrument_ref = instrument_refs[instrument_id]
            member = member_by_id.get(instrument_id)
            for definition_key in sorted(keys):
                definition_ref = _definition_ref(registry, definition_key)
                if member is None:
                    local_items.append(
                        _queue_item(
                            created_at=created,
                            census_ref=census_ref,
                            instrument_ref=census_instrument_ref,
                            definition_key=definition_key,
                            definition_ref=definition_ref,
                            status="CENSUS_MEMBER_UNOBSERVED",
                            reason_codes=("census_member_record_missing",),
                        )
                    )
                    continue
                if member.eligibility_status == "SCIENTIFICALLY_EXCLUDED":
                    local_items.append(
                        _queue_item(
                            created_at=created,
                            census_ref=census_ref,
                            instrument_ref=census_instrument_ref,
                            definition_key=definition_key,
                            definition_ref=definition_ref,
                            status="SCIENTIFICALLY_EXCLUDED",
                            reason_codes=(member.reason_code or "scientific_exclusion",),
                        )
                    )
                    continue
                if member.eligibility_status == "ELIGIBILITY_UNVERIFIED":
                    local_items.append(
                        _queue_item(
                            created_at=created,
                            census_ref=census_ref,
                            instrument_ref=census_instrument_ref,
                            definition_key=definition_key,
                            definition_ref=definition_ref,
                            status="ELIGIBILITY_UNVERIFIED",
                            reason_codes=(member.reason_code or "eligibility_unverified",),
                        )
                    )
                    continue

                row = expected_rows.get((instrument_id, definition_key))
                if row is None:
                    local_items.append(
                        _queue_item(
                            created_at=created,
                            census_ref=census_ref,
                            instrument_ref=census_instrument_ref,
                            definition_key=definition_key,
                            definition_ref=definition_ref,
                            status="DATA_MISSING",
                            reason_codes=("label_input_missing",),
                        )
                    )
                    continue

                resolution = resolutions_by_row[(row.row_key, definition_key)]
                outcome = resolution.outcome
                outcome_payload = outcome.payload
                outcome_ref = _outcome_ref(outcome)
                event_records = tuple(
                    sorted(
                        events_by_outcome.get(outcome.ref.target_id, ()),
                        key=lambda item: item.payload["id"],
                    )
                )
                spec = definition_specs[definition_key]
                if event_records:
                    if spec.target_event not in _DEFINED_EVENT_TYPES:
                        raise GroundTruthError("an event was emitted for an undefined label target")
                    status = "EVENT_DISCOVERED"
                    reasons: tuple[str, ...] = ()
                elif spec.target_event not in _DEFINED_EVENT_TYPES:
                    status = "UNSCORABLE"
                    reasons = tuple(
                        dict.fromkeys(
                            (
                                "label_semantics_not_frozen",
                                *outcome_payload["reason_codes"],
                                *(
                                    (outcome_payload["outcome_state"].lower(),)
                                    if outcome_payload["outcome_state"] != "RESOLVED"
                                    else ()
                                ),
                            )
                        )
                    )
                elif spec.threshold is None:
                    status = "UNSCORABLE"
                    reasons = tuple(
                        dict.fromkeys(
                            (
                                "threshold_not_frozen",
                                *outcome_payload["reason_codes"],
                                *(
                                    (outcome_payload["outcome_state"].lower(),)
                                    if outcome_payload["outcome_state"] != "RESOLVED"
                                    else ()
                                ),
                            )
                        )
                    )
                elif outcome_payload["outcome_state"] != "RESOLVED":
                    status = "UNSCORABLE"
                    reasons = tuple(
                        dict.fromkeys(
                            [
                                *outcome_payload["reason_codes"],
                                outcome_payload["outcome_state"].lower(),
                            ]
                        )
                    )
                else:
                    status = "NO_EVENT"
                    reasons = ()

                queue_item = _queue_item(
                    created_at=created,
                    census_ref=census_ref,
                    instrument_ref=census_instrument_ref,
                    definition_key=definition_key,
                    definition_ref=definition_ref,
                    status=status,
                    reason_codes=reasons,
                    outcome_ref=outcome_ref,
                    event_ids=tuple(item.payload["id"] for item in event_records),
                )
                local_items.append(queue_item)
                if not event_records:
                    continue

                expected_sessions = _expected_sessions(registry, row)
                target_window_start = expected_sessions[0]
                target_window_end = expected_sessions[-1]
                for event in event_records:
                    scoped_events.append(event)
                    event_windows.append(
                        (
                            queue_item,
                            row.label_input.prediction_bar.instrument_ref,
                            event.payload["event_type"],
                            target_window_start,
                            target_window_end,
                            event.payload["id"],
                        )
                    )

        # Include all events, including any records not discoverable through a
        # malformed queue association, only if they still map to a known row.
        known_event_ids = {
            event_id
            for item in local_items
            for event_id in item.event_ids
        }
        for event in batch.runner_events:
            if event.payload["id"] not in known_event_ids:
                raise GroundTruthError("RunnerEvent was not represented in the discovery queue")

        pending_items.extend(local_items)
        eligible_count = sum(
            item.eligibility_status == "SCIENTIFICALLY_ELIGIBLE"
            for item in census_input.members
        )
        excluded_count = sum(
            item.eligibility_status == "SCIENTIFICALLY_EXCLUDED"
            for item in census_input.members
        )
        unverified_count = sum(
            item.eligibility_status == "ELIGIBILITY_UNVERIFIED"
            for item in census_input.members
        )
        expected_count = eligible_count * len(keys)
        input_count = sum(
            (instrument_id, definition_key) in expected_rows
            for instrument_id, member in member_by_id.items()
            if member.eligibility_status == "SCIENTIFICALLY_ELIGIBLE"
            for definition_key in keys
        )
        resolved_count = sum(
            item.status in {"EVENT_DISCOVERED", "NO_EVENT"} for item in local_items
        )
        unscorable_count = sum(item.status == "UNSCORABLE" for item in local_items)
        coverage_rows.append(
            ObservatoryCoverage(
                census_ref=census_ref,
                coverage_scope=_COVERAGE_SCOPE,
                market_completeness_established=False,
                census_member_count=len(instrument_refs),
                member_record_count=len(census_input.members),
                unobserved_member_count=len(instrument_refs) - len(census_input.members),
                eligible_member_count=eligible_count,
                scientifically_excluded_member_count=excluded_count,
                eligibility_unverified_member_count=unverified_count,
                definition_count=len(keys),
                expected_label_scan_count=expected_count,
                label_input_count=input_count,
                missing_label_input_count=expected_count - input_count,
                resolved_target_count=resolved_count,
                unscorable_target_count=unscorable_count,
                member_record_coverage_fraction=_coverage_fraction(
                    len(census_input.members),
                    len(instrument_refs),
                ),
                label_input_coverage_fraction=_coverage_fraction(input_count, expected_count),
                resolved_target_coverage_fraction=_coverage_fraction(
                    resolved_count,
                    expected_count,
                ),
            )
        )

    episodes, queue_episode_ids = _episode_groups(event_windows, policy_hash)
    queue_items = tuple(
        sorted(
            (
                replace(
                    item,
                    episode_ids=tuple(sorted(queue_episode_ids.get(item.queue_id, set()))),
                )
                for item in pending_items
            ),
            key=lambda item: (
                item.census_ref.session_id,
                item.census_ref.census_id,
                item.instrument_ref.target_id,
                item.definition_key,
            ),
        )
    )
    census_refs = tuple(item[2] for item in prepared)
    event_queue = EventDiscoveryQueue(
        policy_hash=policy_hash,
        episode_rule=EPISODE_IDENTITY_RULE,
        census_refs=census_refs,
        items=queue_items,
    )
    unique_events: dict[str, FrozenContractRecord] = {}
    for event in scoped_events:
        unique_events[event.payload["id"]] = event
    ordered_events = tuple(unique_events[key] for key in sorted(unique_events))
    return RunnerObservatoryResult(
        policy_hash=policy_hash,
        coverage=tuple(coverage_rows),
        ground_truth_batches=tuple(ground_truth_batches),
        runner_events=ordered_events,
        episodes=episodes,
        event_queue=event_queue,
        market_completeness_established=False,
    )
