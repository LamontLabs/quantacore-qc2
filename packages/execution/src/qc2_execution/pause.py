"""Server-side entry-pause lifecycle and durable cancellation dispatch."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
from typing import Any, Protocol

from qc2_contracts.runtime import new_uuidv7

from .authority import (
    ExecutionBlocked,
    ExecutionDeferred,
    ReadinessAction,
)
from .intents import build_paper_order_intent


_UUID7_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_REASON_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_GATE_REASON_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{0,95}$")
_CANCELABLE_ENTRY_STATES = {
    "SUBMISSION_STARTED",
    "SUBMISSION_UNKNOWN",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
}


@dataclass(frozen=True, slots=True)
class EntryPauseState:
    paused: bool
    generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.paused, bool):
            raise TypeError("entry pause state must be boolean")
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 1
        ):
            raise ValueError("entry pause generation must be positive")


@dataclass(frozen=True, slots=True)
class PauseCancellationWork:
    pause_generation: int
    target_intent_id: str
    target_state: str
    target_intent: Mapping[str, Any]
    cancel_intent_id: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.pause_generation, bool)
            or not isinstance(self.pause_generation, int)
            or self.pause_generation < 1
        ):
            raise ValueError("pause cancellation generation must be positive")
        if not _UUID7_PATTERN.fullmatch(self.target_intent_id):
            raise ValueError("pause cancellation target must be UUIDv7")
        if self.cancel_intent_id is not None and not _UUID7_PATTERN.fullmatch(
            self.cancel_intent_id
        ):
            raise ValueError("pause cancellation intent ID must be UUIDv7")
        if self.target_state not in _CANCELABLE_ENTRY_STATES:
            raise ValueError("pause cancellation target state is not actionable")
        if self.target_intent.get("id") != self.target_intent_id:
            raise ValueError("pause cancellation target payload identity mismatch")


@dataclass(frozen=True, slots=True)
class ResumeAssessmentInputs:
    readiness: "ResumeReadinessSnapshot"
    current_input_generation: int
    pending_entry_orders_clear: bool

    def __post_init__(self) -> None:
        if not isinstance(self.readiness, ResumeReadinessSnapshot):
            raise TypeError("resume input must contain a server readiness snapshot")
        if (
            isinstance(self.current_input_generation, bool)
            or not isinstance(self.current_input_generation, int)
            or self.current_input_generation < 1
        ):
            raise ValueError("current input generation must be positive")
        if not isinstance(self.pending_entry_orders_clear, bool):
            raise TypeError("pending entry-order status must be boolean")

    @classmethod
    def from_action_readiness(
        cls,
        readiness: Any,
        *,
        current_input_generation: int,
        pending_entry_orders_clear: bool,
    ) -> "ResumeAssessmentInputs":
        return cls(
            ResumeReadinessSnapshot.from_action_readiness(readiness),
            current_input_generation,
            pending_entry_orders_clear,
        )


@dataclass(frozen=True, slots=True)
class ResumeGateSnapshot:
    gate_id: str
    status: str
    reason_codes: tuple[str, ...]
    freshness_deadline: datetime

    def __post_init__(self) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(self.gate_id):
            raise ValueError("resume gate ID must be a lowercase identifier")
        if self.status not in {"PASS", "WARN", "BLOCK", "UNKNOWN", "UNAVAILABLE"}:
            raise ValueError("resume gate status is unsupported")
        if not isinstance(self.reason_codes, tuple) or any(
            not isinstance(code, str) or not _GATE_REASON_PATTERN.fullmatch(code)
            for code in self.reason_codes
        ):
            raise ValueError("resume gate reason codes must be an immutable tuple")
        _require_aware(self.freshness_deadline, "gate.freshness_deadline")


@dataclass(frozen=True, slots=True)
class ResumeReadinessSnapshot:
    """Narrow server-produced projection of the core NEW_ENTRY assessment."""

    action: str
    status: str
    input_generation: int
    evaluated_at: datetime
    freshness_deadline: datetime
    gate_results: tuple[ResumeGateSnapshot, ...]
    allowed_warning_gate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.action not in {action.value for action in ReadinessAction}:
            raise ValueError("resume readiness action is unsupported")
        if self.status not in {"READY", "BLOCKED", "UNKNOWN", "DEGRADED"}:
            raise ValueError("resume readiness status is unsupported")
        if not isinstance(self.input_generation, int) or isinstance(
            self.input_generation, bool
        ) or self.input_generation < 1:
            raise ValueError("resume readiness generation must be positive")
        if not isinstance(self.gate_results, tuple) or not self.gate_results:
            raise ValueError("resume readiness must include an immutable gate set")
        gate_ids = tuple(gate.gate_id for gate in self.gate_results)
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("resume readiness gate IDs must be unique")
        if not isinstance(self.allowed_warning_gate_ids, tuple) or not set(
            self.allowed_warning_gate_ids
        ) <= set(gate_ids):
            raise ValueError("resume readiness warning policy is malformed")
        warn_ids = {gate.gate_id for gate in self.gate_results if gate.status == "WARN"}
        if not set(self.allowed_warning_gate_ids) <= warn_ids:
            raise ValueError("resume readiness warning policy names a non-warning gate")
        _require_aware(self.evaluated_at, "evaluated_at")
        _require_aware(self.freshness_deadline, "freshness_deadline")

    @classmethod
    def from_action_readiness(cls, readiness: Any) -> "ResumeReadinessSnapshot":
        """Project the typed core result without weakening its warning policy."""
        action = _enum_text(readiness.action)
        gates = tuple(
            ResumeGateSnapshot(
                gate_id=gate.gate_id,
                status=_enum_text(gate.status),
                reason_codes=tuple(gate.reason_codes),
                freshness_deadline=_as_aware_datetime(gate.freshness_deadline),
            )
            for gate in readiness.gate_results
        )
        if any(_enum_text(gate.action) != action for gate in readiness.gate_results):
            raise ValueError("resume readiness contains a gate for another action")
        return cls(
            action=action,
            status=_enum_text(readiness.status),
            input_generation=readiness.input_generation,
            evaluated_at=_as_aware_datetime(readiness.evaluated_at),
            freshness_deadline=_as_aware_datetime(readiness.freshness_deadline),
            gate_results=gates,
            allowed_warning_gate_ids=tuple(readiness.allowed_warning_gate_ids),
        )


@dataclass(frozen=True, slots=True)
class ResumeAssessment:
    """A fresh server-side review, not an entry permission or owner approval."""

    assessment_id: str
    pause_generation: int
    input_generation: int
    evaluated_at: datetime
    freshness_deadline: datetime
    gate_results: tuple[tuple[str, str, tuple[str, ...]], ...]
    pending_entry_orders_clear: bool
    allowed_warning_gate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _UUID7_PATTERN.fullmatch(self.assessment_id):
            raise ValueError("resume assessment ID must be UUIDv7")
        if isinstance(self.pause_generation, bool) or self.pause_generation < 1:
            raise ValueError("resume assessment pause generation must be positive")
        if isinstance(self.input_generation, bool) or self.input_generation < 1:
            raise ValueError("resume assessment input generation must be positive")
        _require_aware(self.evaluated_at, "evaluated_at")
        _require_aware(self.freshness_deadline, "freshness_deadline")
        if self.freshness_deadline <= self.evaluated_at:
            raise ValueError("resume assessment must have a live freshness window")
        if not self.pending_entry_orders_clear:
            raise ValueError("pending entry orders must be clear before resume")
        gate_ids = tuple(row[0] for row in self.gate_results)
        if (
            not self.gate_results
            or len(gate_ids) != len(set(gate_ids))
            or not isinstance(self.allowed_warning_gate_ids, tuple)
            or not set(self.allowed_warning_gate_ids) <= set(gate_ids)
        ):
            raise ValueError("resume assessment gate set is malformed")
        warn_ids = {
            gate_id for gate_id, status, _reasons in self.gate_results if status == "WARN"
        }
        if not set(self.allowed_warning_gate_ids) <= warn_ids:
            raise ValueError("resume assessment warning policy names a non-warning gate")
        pause_rows = [
            row
            for row in self.gate_results
            if row[0] == "entry_pause_authority"
            and row[1] == "BLOCK"
            and "ENTRY_PAUSED" in row[2]
        ]
        if len(pause_rows) != 1:
            raise ValueError("resume assessment must contain the active pause gate")
        for gate_id, status, _reasons in self.gate_results:
            if gate_id == "entry_pause_authority":
                continue
            if status == "PASS":
                continue
            if status != "WARN" or gate_id not in self.allowed_warning_gate_ids:
                raise ValueError("resume assessment contains a failed prerequisite")

    def as_json(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "action": ReadinessAction.NEW_ENTRY.value,
            "status": "READY_TO_RESUME",
            "pause_generation": self.pause_generation,
            "input_generation": self.input_generation,
            "evaluated_at": _utc_text(self.evaluated_at),
            "freshness_deadline": _utc_text(self.freshness_deadline),
            "pending_entry_orders_clear": self.pending_entry_orders_clear,
            "allowed_warning_gate_ids": list(self.allowed_warning_gate_ids),
            "gate_results": [
                {
                    "gate_id": gate_id,
                    "status": status,
                    "reason_codes": list(reason_codes),
                }
                for gate_id, status, reason_codes in self.gate_results
            ],
        }


class EntryPauseStore(Protocol):
    def get_entry_pause_state(self) -> EntryPauseState: ...

    def pause_new_entries(
        self, request_id: str, reason_code: str
    ) -> EntryPauseState: ...

    def pending_entry_pause_cancellations(
        self,
    ) -> tuple[PauseCancellationWork, ...]: ...

    def reserve_pause_cancel_intent_id(
        self, pause_generation: int, target_intent_id: str, proposed_id: str
    ) -> str: ...

    def mark_pause_cancel_enqueued(
        self, pause_generation: int, target_intent_id: str, cancel_intent_id: str
    ) -> bool: ...

    def resume_new_entries(
        self, expected_pause_generation: int, assessment: ResumeAssessment
    ) -> EntryPauseState | None: ...

    def load_intent(self, intent_id: str) -> Mapping[str, Any] | None: ...

    def persist_intent(
        self, intent: Mapping[str, Any], expected_account_fingerprint: str
    ) -> str: ...

    def transition_intent(self, intent_id: str, next_state: str) -> bool: ...

    def reserve_intent(self, intent_id: str) -> None: ...

    def enqueue(self, intent_id: str) -> str: ...


@dataclass(frozen=True, slots=True)
class PauseDispatchResult:
    enqueued_target_ids: tuple[str, ...]
    deferred_target_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PauseRequestResult:
    state: EntryPauseState
    dispatch: PauseDispatchResult


class EntryPauseAuthority:
    """Persists pause transitions and only resumes after a fresh server review."""

    def __init__(
        self,
        *,
        store: EntryPauseStore,
        resume_assessor: Callable[[], ResumeAssessmentInputs],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._resume_assessor = resume_assessor
        self._clock = clock

    def pause_new_entries(
        self, *, request_id: str, reason_code: str
    ) -> PauseRequestResult:
        if not _UUID7_PATTERN.fullmatch(request_id):
            raise ValueError("pause request ID must be UUIDv7")
        if not _REASON_PATTERN.fullmatch(reason_code):
            raise ValueError("pause reason code must be a lowercase identifier")
        state = self._store.pause_new_entries(request_id, reason_code)
        return PauseRequestResult(
            state=state,
            dispatch=_dispatch_pause_cancellations(self._store, self._clock()),
        )

    def request_resume(self) -> EntryPauseState:
        state = self._store.get_entry_pause_state()
        if not state.paused:
            raise ExecutionBlocked("NEW_ENTRY_PAUSE_NOT_ACTIVE")
        inputs = self._resume_assessor()
        assessment = build_resume_assessment(
            inputs,
            pause_generation=state.generation,
            assessment_id=new_uuidv7(),
            now=self._clock(),
        )
        resumed = self._store.resume_new_entries(state.generation, assessment)
        if resumed is None:
            raise ExecutionBlocked("ENTRY_PAUSE_GENERATION_CHANGED")
        return resumed


def build_resume_assessment(
    inputs: ResumeAssessmentInputs,
    *,
    pause_generation: int,
    assessment_id: str,
    now: datetime,
) -> ResumeAssessment:
    """Allow only a blocked-by-pause NEW_ENTRY review with every other gate passing."""
    current = _require_aware(now, "now")
    readiness = inputs.readiness
    if readiness.action != ReadinessAction.NEW_ENTRY.value:
        raise ExecutionBlocked("RESUME_ASSESSMENT_ACTION_MISMATCH")
    if readiness.status != "BLOCKED":
        raise ExecutionBlocked("RESUME_ASSESSMENT_NOT_BLOCKED_BY_PAUSE")
    if (
        isinstance(inputs.current_input_generation, bool)
        or inputs.current_input_generation < 1
        or isinstance(readiness.input_generation, bool)
        or not isinstance(readiness.input_generation, int)
        or readiness.input_generation < 1
        or readiness.input_generation != inputs.current_input_generation
    ):
        raise ExecutionBlocked("RESUME_ASSESSMENT_GENERATION_MISMATCH")
    if not inputs.pending_entry_orders_clear:
        raise ExecutionBlocked("PENDING_ENTRY_ORDERS_NOT_CLEAR")

    evaluated_at = _require_aware(readiness.evaluated_at, "evaluated_at")
    freshness_deadline = _require_aware(
        readiness.freshness_deadline, "freshness_deadline"
    )
    if evaluated_at > current:
        raise ExecutionBlocked("RESUME_ASSESSMENT_FROM_FUTURE")
    if freshness_deadline <= current:
        raise ExecutionBlocked("RESUME_ASSESSMENT_STALE")

    pause_gates = 0
    gate_results: list[tuple[str, str, tuple[str, ...]]] = []
    allowed_warnings = set(readiness.allowed_warning_gate_ids)
    for gate in readiness.gate_results:
        if _require_aware(gate.freshness_deadline, "gate.freshness_deadline") <= current:
            raise ExecutionBlocked("RESUME_ASSESSMENT_STALE")
        status = gate.status
        reasons = tuple(gate.reason_codes)
        if gate.gate_id == "entry_pause_authority":
            pause_gates += 1
            if status != "BLOCK" or "ENTRY_PAUSED" not in reasons:
                raise ExecutionBlocked("RESUME_PAUSE_GATE_NOT_ACTIVE")
        elif status != "PASS" and not (
            status == "WARN" and gate.gate_id in allowed_warnings
        ):
            raise ExecutionBlocked("RESUME_PREREQUISITE_NOT_READY")
        gate_results.append((gate.gate_id, status, reasons))
    if pause_gates != 1:
        raise ExecutionBlocked("RESUME_PAUSE_GATE_MISSING")

    return ResumeAssessment(
        assessment_id=assessment_id,
        pause_generation=pause_generation,
        input_generation=readiness.input_generation,
        evaluated_at=evaluated_at,
        freshness_deadline=freshness_deadline,
        gate_results=tuple(gate_results),
        pending_entry_orders_clear=inputs.pending_entry_orders_clear,
        allowed_warning_gate_ids=tuple(readiness.allowed_warning_gate_ids),
    )


def build_pause_cancel_intent(
    target_intent: Mapping[str, Any],
    *,
    pause_generation: int,
    cancel_intent_id: str,
    now: datetime,
) -> dict[str, Any]:
    """Build a normal, idempotent CANCEL_PENDING_ENTRY intent from pause work."""
    if target_intent.get("action_kind") != "OPEN_LONG" or target_intent.get("side") != "BUY":
        raise ExecutionBlocked("PAUSE_CANCEL_TARGET_NOT_ENTRY")
    if target_intent.get("intent_state") not in _CANCELABLE_ENTRY_STATES:
        raise ExecutionDeferred("PAUSE_CANCEL_TARGET_NOT_BROKER_PENDING")
    if isinstance(pause_generation, bool) or pause_generation < 1:
        raise ValueError("pause generation must be positive")
    if not _UUID7_PATTERN.fullmatch(cancel_intent_id):
        raise ValueError("pause cancellation intent ID must be UUIDv7")
    current = _require_aware(now, "now")

    source_ref = {
        "target_schema_name": "qc2.execution.PaperOrderIntent.v1",
        "target_id": target_intent["id"],
        "content_hash": target_intent["content_hash"],
    }
    payload = _thaw_json(target_intent)
    source_refs = list(payload.get("source_refs", []))
    source_refs.append(source_ref)
    unique_refs: dict[str, Mapping[str, Any]] = {}
    for reference in source_refs:
        unique_refs[json.dumps(reference, sort_keys=True, separators=(",", ":"))] = reference
    payload.update(
        {
            "id": cancel_intent_id,
            "created_at": _utc_text(current),
            "content_hash": "0" * 64,
            "intent_state": "CREATED",
            "action_kind": "CANCEL_PENDING_ENTRY",
            "source_ref": source_ref,
            "source_refs": list(unique_refs.values()),
            "side": "BUY",
            "reason_code": "pause_new_entries",
            "reservation_ref": None,
            "idempotency_key": (
                f"pause_{pause_generation}_{str(target_intent['id']).replace('-', '')}"
            ),
        }
    )
    intent = build_paper_order_intent(
        payload,
        expected_account_fingerprint=str(target_intent["paper_account_fingerprint"]),
        now=current,
    )
    return intent.payload


def _dispatch_pause_cancellations(
    store: EntryPauseStore,
    now: datetime,
) -> PauseDispatchResult:
    enqueued: list[str] = []
    deferred: list[str] = []
    for work in store.pending_entry_pause_cancellations():
        proposed_id = work.cancel_intent_id or new_uuidv7()
        cancel_intent_id = store.reserve_pause_cancel_intent_id(
            work.pause_generation, work.target_intent_id, proposed_id
        )
        try:
            cancel_payload = build_pause_cancel_intent(
                work.target_intent,
                pause_generation=work.pause_generation,
                cancel_intent_id=cancel_intent_id,
                now=now,
            )
        except (ExecutionBlocked, ExecutionDeferred, ValueError):
            deferred.append(work.target_intent_id)
            continue

        persisted_id = store.persist_intent(
            cancel_payload, str(work.target_intent["paper_account_fingerprint"])
        )
        if persisted_id != cancel_intent_id:
            raise RuntimeError("pause cancellation persistence returned a different ID")
        persisted = store.load_intent(cancel_intent_id)
        if persisted is None:
            raise RuntimeError("pause cancellation intent disappeared after persistence")
        state_name = str(persisted.get("intent_state"))
        if state_name == "CREATED":
            if not store.transition_intent(cancel_intent_id, "VERIFIED"):
                raise RuntimeError("pause cancellation intent could not be verified")
            state_name = "VERIFIED"
        if state_name == "VERIFIED":
            store.reserve_intent(cancel_intent_id)
            state_name = "RESERVED"
        if state_name == "RESERVED":
            store.enqueue(cancel_intent_id)
        elif state_name not in {
            "QUEUED_FOR_SUBMISSION",
            "SUBMISSION_STARTED",
            "SUBMISSION_UNKNOWN",
            "ACKNOWLEDGED",
            "PARTIALLY_FILLED",
            "CANCEL_REQUESTED",
            "CANCELLED",
            "REJECTED",
            "EXPIRED",
        }:
            raise RuntimeError("pause cancellation intent has an unsupported state")
        if not store.mark_pause_cancel_enqueued(
            work.pause_generation, work.target_intent_id, cancel_intent_id
        ):
            raise RuntimeError("pause cancellation work could not be acknowledged")
        enqueued.append(work.target_intent_id)
    return PauseDispatchResult(tuple(enqueued), tuple(deferred))


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_json(item) for item in value]
    return value


def _require_aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TypeError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return _require_aware(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _as_aware_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _require_aware(value, "readiness timestamp")
    if isinstance(value, str):
        try:
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            return _require_aware(datetime.fromisoformat(normalized), "readiness timestamp")
        except ValueError as exc:
            raise ValueError("readiness timestamp is invalid") from exc
    raise TypeError("readiness timestamp must be a datetime or ISO-8601 string")
