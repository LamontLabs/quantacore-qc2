"""Fenced, action-scoped authority for paper-broker mutations.

This module deliberately defines only the broker interface. It contains no HTTP
client, provider credentials, feed access, or live-trading implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import re
from typing import Any, Callable, Mapping, Protocol

from qc2_contracts.runtime import (
    canonical_json_bytes,
    validate_contract,
    verify_content_hash,
)


_UUID7_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_HASH_DOMAIN = b"QC2-HASH-V1\x00qc2.execution.normalized-request.v1\x00"
_SUBMISSION_MESSAGE_TYPE = "paper_order_submission"


class ExecutionError(RuntimeError):
    """Base class for execution-authority failures."""


class ExecutionBlocked(ExecutionError):
    """The current action-specific gate does not authorize a broker mutation."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class ExecutionDeferred(ExecutionError):
    """The action is valid, but a serialized prior operation has not settled."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class FencedLeaseLost(ExecutionError):
    """The worker's lease or fencing generation is no longer current."""


class ReadinessAction(StrEnum):
    NEW_ENTRY = "NEW_ENTRY"
    CANCEL_ENTRY = "CANCEL_ENTRY"
    EXIT_POSITION = "EXIT_POSITION"


class SubmissionOutcome(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    REJECTED = "REJECTED"


class AttemptState(StrEnum):
    STARTED = "STARTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class ReconciliationDisposition(StrEnum):
    FOUND = "FOUND"
    ABSENCE_PROVEN = "ABSENCE_PROVEN"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class OutboxDelivery:
    message_id: str
    logical_operation_id: str
    message_type: str
    payload_hash: str
    worker_id: str
    fencing_generation: int
    lease_expires_at: datetime

    def __post_init__(self) -> None:
        if not _UUID7_PATTERN.fullmatch(self.message_id):
            raise ValueError("outbox message ID must be UUIDv7")
        if not _UUID7_PATTERN.fullmatch(self.logical_operation_id):
            raise ValueError("logical operation ID must be UUIDv7")
        if not _UUID7_PATTERN.fullmatch(self.worker_id):
            raise ValueError("worker ID must be UUIDv7")
        if not _SHA256_PATTERN.fullmatch(self.payload_hash):
            raise ValueError("outbox payload hash must be lowercase SHA-256")
        if isinstance(self.fencing_generation, bool) or self.fencing_generation < 1:
            raise ValueError("fencing generation must be positive")
        _aware_datetime(self.lease_expires_at, "lease_expires_at")


@dataclass(frozen=True, slots=True)
class ReadinessAssessmentSnapshot:
    assessment_id: str
    action: str
    status: str
    input_generation: int
    freshness_deadline: datetime

    def __post_init__(self) -> None:
        if not _UUID7_PATTERN.fullmatch(self.assessment_id):
            raise ValueError("readiness assessment ID must be UUIDv7")
        if isinstance(self.input_generation, bool) or self.input_generation < 1:
            raise ValueError("readiness input generation must be positive")
        _aware_datetime(self.freshness_deadline, "freshness_deadline")

    def as_json(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "action": self.action,
            "status": self.status,
            "input_generation": self.input_generation,
            "freshness_deadline": _utc_text(self.freshness_deadline),
        }


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot:
    """Fresh, action-scoped state read from authoritative sources."""

    paper_account_fingerprint: str
    account_mode: str
    paper_endpoint_verified: bool
    entry_paused: bool
    current_session: str | None
    session_open: bool
    reservation_active: bool
    symbol_assignment_id: str | None
    broker_symbol: str | None
    readiness: tuple[ReadinessAssessmentSnapshot, ...]
    prior_intent_state: str | None = None
    prior_reservation_active: bool | None = None
    prior_broker_order_id: str | None = None

    def __post_init__(self) -> None:
        if not _SHA256_PATTERN.fullmatch(self.paper_account_fingerprint):
            raise ValueError("paper account fingerprint must be lowercase SHA-256")
        if not isinstance(self.readiness, tuple):
            raise ValueError("readiness assessments must be an immutable tuple")
        if len({row.action for row in self.readiness}) != len(self.readiness):
            raise ValueError("readiness assessments must have unique action scopes")

    def as_json(self) -> dict[str, Any]:
        return {
            "paper_account_fingerprint": self.paper_account_fingerprint,
            "account_mode": self.account_mode,
            "paper_endpoint_verified": self.paper_endpoint_verified,
            "entry_paused": self.entry_paused,
            "current_session": self.current_session,
            "session_open": self.session_open,
            "reservation_active": self.reservation_active,
            "symbol_assignment_id": self.symbol_assignment_id,
            "broker_symbol": self.broker_symbol,
            "readiness": [row.as_json() for row in self.readiness],
            "prior_intent_state": self.prior_intent_state,
            "prior_reservation_active": self.prior_reservation_active,
            "prior_broker_order_id": self.prior_broker_order_id,
        }


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt_id: str
    intent_id: str
    attempt_number: int
    state: AttemptState
    created: bool
    client_order_key: str
    normalized_request_hash: str
    started_at: datetime
    broker_order_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", AttemptState(self.state))
        if not _UUID7_PATTERN.fullmatch(self.attempt_id):
            raise ValueError("attempt ID must be UUIDv7")
        if not _UUID7_PATTERN.fullmatch(self.intent_id):
            raise ValueError("attempt intent ID must be UUIDv7")
        if isinstance(self.attempt_number, bool) or self.attempt_number < 1:
            raise ValueError("attempt number must be positive")
        if not _SHA256_PATTERN.fullmatch(self.normalized_request_hash):
            raise ValueError("request hash must be lowercase SHA-256")
        _aware_datetime(self.started_at, "started_at")


@dataclass(frozen=True, slots=True)
class BrokerResult:
    """A normalized adapter result; UNKNOWN is never converted into a retry."""

    outcome: SubmissionOutcome
    broker_order_id: str | None = None
    order_state: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationEvidence:
    intent_id: str
    account_fingerprint: str
    client_order_key: str
    normalized_request_hash: str
    disposition: ReconciliationDisposition
    checked_sources: tuple[str, ...]
    consistency_window_closed: bool
    broker_order_id: str | None
    evidence_ref: Mapping[str, Any]


class GateProvider(Protocol):
    def snapshot(self, intent: Mapping[str, Any]) -> ExecutionSnapshot: ...


class BrokerAdapter(Protocol):
    """Injected paper adapter. Implementations must classify ambiguous sends UNKNOWN."""

    def submit_order(
        self, request: Mapping[str, Any], *, client_order_key: str
    ) -> BrokerResult: ...

    def cancel_order(
        self, request: Mapping[str, Any], *, client_order_key: str
    ) -> BrokerResult: ...


class ExecutionStore(Protocol):
    """Persistence boundary implemented by the PostgreSQL execution repository."""

    def enqueue(self, intent_id: str) -> str: ...

    def claim_next(self, worker_id: str, lease_seconds: int) -> OutboxDelivery | None: ...

    def load_intent(self, intent_id: str) -> Mapping[str, Any] | None: ...

    def load_attempt(self, intent_id: str) -> AttemptRecord | None: ...

    def load_attempt_by_id(self, attempt_id: str) -> AttemptRecord | None: ...

    def load_intent_by_attempt(self, attempt_id: str) -> Mapping[str, Any] | None: ...

    def load_prior_intent(self, intent_id: str) -> Mapping[str, Any] | None: ...

    def begin_attempt(
        self,
        delivery: OutboxDelivery,
        intent: Mapping[str, Any],
        request: Mapping[str, Any],
        request_hash: str,
        snapshot: ExecutionSnapshot,
    ) -> AttemptRecord: ...

    def authorize_attempt(
        self,
        delivery: OutboxDelivery,
        attempt_id: str,
        snapshot: ExecutionSnapshot,
    ) -> bool: ...

    def mark_blocked(
        self,
        delivery: OutboxDelivery,
        intent: Mapping[str, Any],
        reason_code: str,
        snapshot: ExecutionSnapshot | None,
        attempt_id: str | None = None,
    ) -> bool: ...

    def finish_attempt(
        self,
        delivery: OutboxDelivery,
        attempt_id: str,
        outcome: SubmissionOutcome,
        *,
        broker_order_id: str | None = None,
        order_state: str | None = None,
        uncertainty_code: str | None = None,
    ) -> bool: ...

    def mark_unknown(self, delivery: OutboxDelivery, attempt_id: str) -> bool: ...

    def complete_delivery(self, delivery: OutboxDelivery) -> bool: ...

    def defer_delivery(self, delivery: OutboxDelivery, reason_code: str) -> bool: ...

    def resolve_unknown(
        self,
        attempt_id: str,
        disposition: ReconciliationDisposition,
        evidence: ReconciliationEvidence,
    ) -> bool: ...


def required_readiness_action(intent: Mapping[str, Any]) -> ReadinessAction:
    action = intent.get("action_kind")
    side = intent.get("side")
    if action == "OPEN_LONG":
        return ReadinessAction.NEW_ENTRY
    if action == "CANCEL_PENDING_ENTRY":
        return ReadinessAction.CANCEL_ENTRY
    if action in {"REDUCE_LONG", "CLOSE_LONG"}:
        return ReadinessAction.EXIT_POSITION
    if action == "REPLACE_ORDER" and side == "BUY":
        return ReadinessAction.NEW_ENTRY
    if action == "REPLACE_ORDER" and side == "SELL":
        return ReadinessAction.EXIT_POSITION
    raise ExecutionBlocked("UNSUPPORTED_PAPER_ACTION")


def normalized_request_hash(request: Mapping[str, Any]) -> str:
    """Match qc2_integrity_build.hash_json's QC2-HASH-V1 domain separation."""
    payload = _REQUEST_HASH_DOMAIN + canonical_json_bytes(dict(request))
    return sha256(payload).hexdigest()


def validate_execution_gate(
    intent: Mapping[str, Any],
    snapshot: ExecutionSnapshot,
    *,
    now: datetime,
) -> ReadinessAssessmentSnapshot:
    """Fail closed against the current action-specific account and readiness state."""
    current = _aware_datetime(now, "now")
    try:
        thawed_intent = _thaw_json(intent)
        validate_contract("PaperOrderIntent", thawed_intent)
        verify_content_hash("PaperOrderIntent", thawed_intent)
    except (TypeError, ValueError) as exc:
        raise ExecutionBlocked("INVALID_INTENT_CONTRACT") from exc

    if intent.get("intent_state") != "QUEUED_FOR_SUBMISSION":
        raise ExecutionBlocked("INTENT_NOT_QUEUED")
    if _parse_instant(intent.get("expires_at"), "expires_at") <= current:
        raise ExecutionBlocked("INTENT_EXPIRED")
    if intent.get("account_mode") != "PAPER" or not snapshot.paper_endpoint_verified:
        raise ExecutionBlocked("PAPER_ENDPOINT_NOT_VERIFIED")
    if intent.get("paper_account_fingerprint") != snapshot.paper_account_fingerprint:
        raise ExecutionBlocked("PAPER_ACCOUNT_CHANGED")
    if snapshot.account_mode != "PAPER":
        raise ExecutionBlocked("ACCOUNT_MODE_NOT_PAPER")

    action = required_readiness_action(intent)
    if action == ReadinessAction.NEW_ENTRY and snapshot.entry_paused:
        raise ExecutionBlocked("NEW_ENTRY_PAUSED")

    assessment = next(
        (row for row in snapshot.readiness if row.action == action.value),
        None,
    )
    if assessment is None:
        raise ExecutionBlocked("ACTION_PERMISSION_MISSING")
    if assessment.status != "READY":
        raise ExecutionBlocked("ACTION_PERMISSION_NOT_READY")
    if assessment.freshness_deadline <= current:
        raise ExecutionBlocked("ACTION_PERMISSION_STALE")

    if intent.get("action_kind") == "CANCEL_PENDING_ENTRY":
        if snapshot.prior_intent_state == "SUBMISSION_STARTED":
            raise ExecutionDeferred("PRIOR_SUBMISSION_IN_FLIGHT")
        if snapshot.prior_intent_state not in {
            "SUBMISSION_UNKNOWN",
            "ACKNOWLEDGED",
            "PARTIALLY_FILLED",
        }:
            raise ExecutionBlocked("CANCEL_TARGET_NOT_PENDING")
        if not snapshot.prior_reservation_active:
            raise ExecutionBlocked("CANCEL_RESERVATION_NOT_ACTIVE")
        return assessment

    if not snapshot.reservation_active:
        raise ExecutionBlocked("EXPOSURE_RESERVATION_NOT_ACTIVE")
    if not snapshot.session_open:
        raise ExecutionBlocked("EXECUTION_SESSION_CLOSED")
    target_session = intent.get("target_execution_session")
    if not isinstance(target_session, str) or target_session != snapshot.current_session:
        raise ExecutionBlocked("EXECUTION_SESSION_CHANGED")

    assignment = intent.get("symbol_assignment_ref")
    expected_assignment = assignment.get("target_id") if isinstance(assignment, Mapping) else None
    if (
        not expected_assignment
        or snapshot.symbol_assignment_id != expected_assignment
        or not isinstance(snapshot.broker_symbol, str)
        or not snapshot.broker_symbol.strip()
    ):
        raise ExecutionBlocked("SYMBOL_ASSIGNMENT_CHANGED")

    if intent.get("action_kind") == "REPLACE_ORDER":
        if snapshot.prior_intent_state not in {"CANCELLED", "REJECTED"}:
            raise ExecutionDeferred("PRIOR_ORDER_NOT_DEFINITIVELY_TERMINAL")
        if snapshot.prior_reservation_active:
            raise ExecutionDeferred("PRIOR_ORDER_RESERVATION_STILL_ACTIVE")

    return assessment


def build_normalized_request(
    intent: Mapping[str, Any],
    snapshot: ExecutionSnapshot,
    *,
    prior_intent: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action = intent.get("action_kind")
    if action == "CANCEL_PENDING_ENTRY":
        if prior_intent is None:
            raise ExecutionBlocked("CANCEL_TARGET_MISSING")
        source_ref = intent.get("source_ref")
        if (
            not isinstance(source_ref, Mapping)
            or source_ref.get("target_id") != prior_intent.get("id")
            or prior_intent.get("paper_account_fingerprint")
            != intent.get("paper_account_fingerprint")
        ):
            raise ExecutionBlocked("CANCEL_TARGET_MISMATCH")
        return {
            "schema_name": "qc2.execution.normalized_mutation_request.v1",
            "action": "CANCEL",
            "intent_id": intent["id"],
            "account_fingerprint": intent["paper_account_fingerprint"],
            "client_order_key": intent["idempotency_key"],
            "target_intent_id": prior_intent["id"],
            "target_client_order_key": prior_intent["idempotency_key"],
            "broker_order_id": snapshot.prior_broker_order_id,
        }

    symbol = snapshot.broker_symbol
    if not isinstance(symbol, str) or not symbol.strip():
        raise ExecutionBlocked("BROKER_SYMBOL_MISSING")
    return {
        "schema_name": "qc2.execution.normalized_mutation_request.v1",
        "action": "SUBMIT",
        "intent_id": intent["id"],
        "account_fingerprint": intent["paper_account_fingerprint"],
        "client_order_key": intent["idempotency_key"],
        "instrument_id": intent["instrument_ref"]["target_id"],
        "symbol_assignment_id": snapshot.symbol_assignment_id,
        "symbol": symbol.strip(),
        "side": intent["side"],
        "quantity_whole_shares": intent["quantity_whole_shares"],
        "order_type": intent["order_type"],
        "time_in_force": intent["time_in_force"],
        "session_restriction": intent["session_restriction"],
        "limit_price": intent.get("limit_price"),
        "stop_price": intent.get("stop_price"),
        "extended_hours": False,
    }


def build_submission_attempt_contract(
    *,
    intent: Mapping[str, Any],
    attempt: AttemptRecord,
    outcome: SubmissionOutcome,
    created_at: datetime,
    evidence_ref: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the immutable v1 outcome contract for a durable pre-send attempt."""
    if attempt.intent_id != intent.get("id"):
        raise ValueError("attempt and intent identity do not match")
    contract = {
        "schema_name": "qc2.execution.SubmissionAttempt.v1",
        "schema_version": "1.0",
        "id": attempt.attempt_id,
        "created_at": _utc_text(created_at),
        "owning_authority": "execution",
        "evidence_class": intent["evidence_class"],
        "environment_namespace": intent["environment_namespace"],
        "source_refs": [],
        "intent_ref": {
            "target_schema_name": "qc2.execution.PaperOrderIntent.v1",
            "target_id": intent["id"],
            "content_hash": intent["content_hash"],
        },
        "client_order_key": intent["idempotency_key"],
        "normalized_request_hash": attempt.normalized_request_hash,
        "attempt_number": attempt.attempt_number,
        "started_at": _utc_text(attempt.started_at),
        "outcome": SubmissionOutcome(outcome).value,
        "broker_order_ref": None,
        "evidence_ref": dict(evidence_ref),
    }
    validate_contract("SubmissionAttempt", contract)
    return contract


def validate_reconciliation_evidence(
    attempt: AttemptRecord,
    intent: Mapping[str, Any],
    evidence: ReconciliationEvidence,
) -> None:
    """Require account/key/hash binding and proof beyond a single not-found query."""
    if (
        evidence.intent_id != intent.get("id")
        or evidence.account_fingerprint != intent.get("paper_account_fingerprint")
        or evidence.client_order_key != attempt.client_order_key
        or evidence.normalized_request_hash != attempt.normalized_request_hash
    ):
        raise ExecutionBlocked("RECONCILIATION_BINDING_MISMATCH")
    if evidence.disposition == ReconciliationDisposition.UNRESOLVED:
        return
    if not evidence.checked_sources or len(set(evidence.checked_sources)) != len(
        evidence.checked_sources
    ):
        raise ExecutionBlocked("RECONCILIATION_SOURCE_COVERAGE_MISSING")
    _validate_evidence_ref(evidence.evidence_ref)
    if evidence.disposition == ReconciliationDisposition.FOUND:
        if not evidence.broker_order_id:
            raise ExecutionBlocked("FOUND_ORDER_ID_MISSING")
        return
    if evidence.disposition == ReconciliationDisposition.ABSENCE_PROVEN:
        if len(evidence.checked_sources) < 2 or not evidence.consistency_window_closed:
            raise ExecutionBlocked("ABSENCE_NOT_PROVEN")
        if evidence.broker_order_id is not None:
            raise ExecutionBlocked("ABSENCE_CONFLICTS_WITH_FOUND_ORDER")
        return
    raise ExecutionBlocked("UNSUPPORTED_RECONCILIATION_DISPOSITION")


@dataclass(frozen=True, slots=True)
class ProcessResult:
    logical_operation_id: str
    state: str
    attempt_id: str | None = None
    reason_code: str | None = None


class ExecutionAuthority:
    """The sole orchestration boundary allowed to invoke broker mutation methods."""

    def __init__(
        self,
        *,
        store: ExecutionStore,
        gate_provider: GateProvider,
        broker: BrokerAdapter,
        worker_id: str,
        lease_seconds: int = 30,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not _UUID7_PATTERN.fullmatch(worker_id):
            raise ValueError("worker ID must be UUIDv7")
        if isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        self._store = store
        self._gate_provider = gate_provider
        self._broker = broker
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._clock = clock

    def process_one(self) -> ProcessResult | None:
        delivery = self._store.claim_next(self._worker_id, self._lease_seconds)
        if delivery is None:
            return None
        if delivery.message_type != _SUBMISSION_MESSAGE_TYPE:
            raise ExecutionBlocked("UNSUPPORTED_OUTBOX_MESSAGE")

        intent = self._store.load_intent(delivery.logical_operation_id)
        if intent is None:
            raise ExecutionBlocked("OUTBOX_INTENT_MISSING")
        _validate_queued_intent(delivery, intent)

        previous_attempt = self._store.load_attempt(delivery.logical_operation_id)
        if previous_attempt is not None:
            if previous_attempt.state == AttemptState.STARTED:
                self._require_fenced(
                    self._store.mark_unknown(delivery, previous_attempt.attempt_id)
                )
                self._require_fenced(self._store.complete_delivery(delivery))
                return ProcessResult(
                    delivery.logical_operation_id,
                    AttemptState.SUBMISSION_UNKNOWN.value,
                    previous_attempt.attempt_id,
                    "RECOVERED_STARTED_ATTEMPT_AS_UNKNOWN",
                )
            self._require_fenced(self._store.complete_delivery(delivery))
            return ProcessResult(
                delivery.logical_operation_id,
                previous_attempt.state.value,
                previous_attempt.attempt_id,
                "DUPLICATE_DELIVERY_ALREADY_RECORDED",
            )
        if intent.get("intent_state") in {
            "ACKNOWLEDGED",
            "SUBMISSION_UNKNOWN",
            "REJECTED",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCEL_REQUESTED",
            "CANCELLED",
            "EXPIRED",
            "REPLACED",
        }:
            self._require_fenced(self._store.complete_delivery(delivery))
            return ProcessResult(
                delivery.logical_operation_id,
                str(intent["intent_state"]),
                reason_code="INTENT_ALREADY_TERMINAL",
            )

        snapshot = self._gate_provider.snapshot(intent)
        try:
            validate_execution_gate(intent, snapshot, now=self._clock())
            prior = self._load_prior_if_required(intent)
            request = build_normalized_request(intent, snapshot, prior_intent=prior)
        except ExecutionDeferred as exc:
            self._require_fenced(self._store.defer_delivery(delivery, exc.reason_code))
            return ProcessResult(
                delivery.logical_operation_id,
                "DEFERRED",
                reason_code=exc.reason_code,
            )
        except ExecutionBlocked as exc:
            self._require_fenced(
                self._store.mark_blocked(
                    delivery, intent, exc.reason_code, snapshot
                )
            )
            self._require_fenced(self._store.complete_delivery(delivery))
            return ProcessResult(
                delivery.logical_operation_id,
                AttemptState.BLOCKED.value,
                reason_code=exc.reason_code,
            )

        request_hash = normalized_request_hash(request)
        attempt = self._store.begin_attempt(
            delivery, intent, request, request_hash, snapshot
        )
        if not attempt.created:
            if attempt.state == AttemptState.STARTED:
                self._require_fenced(self._store.mark_unknown(delivery, attempt.attempt_id))
                final_state = AttemptState.SUBMISSION_UNKNOWN.value
            else:
                final_state = attempt.state.value
            self._require_fenced(self._store.complete_delivery(delivery))
            return ProcessResult(
                delivery.logical_operation_id,
                final_state,
                attempt.attempt_id,
                "DUPLICATE_DELIVERY_ALREADY_RECORDED",
            )

        try:
            final_snapshot = self._gate_provider.snapshot(intent)
            validate_execution_gate(intent, final_snapshot, now=self._clock())
            final_prior = self._load_prior_if_required(intent)
            final_request = build_normalized_request(
                intent, final_snapshot, prior_intent=final_prior
            )
            if normalized_request_hash(final_request) != request_hash:
                raise ExecutionBlocked("REQUEST_CHANGED_BEFORE_SEND")
        except (ExecutionBlocked, ExecutionDeferred) as exc:
            self._require_fenced(
                self._store.mark_blocked(
                    delivery,
                    intent,
                    exc.reason_code,
                    final_snapshot if "final_snapshot" in locals() else None,
                    attempt.attempt_id,
                )
            )
            self._require_fenced(self._store.complete_delivery(delivery))
            return ProcessResult(
                delivery.logical_operation_id,
                AttemptState.BLOCKED.value,
                attempt.attempt_id,
                exc.reason_code,
            )

        if not self._store.authorize_attempt(
            delivery, attempt.attempt_id, final_snapshot
        ):
            reason_code = "FINAL_SEND_AUTHORIZATION_DENIED"
            self._require_fenced(
                self._store.mark_blocked(
                    delivery,
                    intent,
                    reason_code,
                    final_snapshot,
                    attempt.attempt_id,
                )
            )
            self._require_fenced(self._store.complete_delivery(delivery))
            return ProcessResult(
                delivery.logical_operation_id,
                AttemptState.BLOCKED.value,
                attempt.attempt_id,
                reason_code,
            )
        try:
            result = self._invoke_broker(intent, final_request)
            _validate_broker_result(intent, result)
            result = BrokerResult(
                SubmissionOutcome(result.outcome),
                result.broker_order_id,
                result.order_state,
            )
            uncertainty_code = None
        except Exception as exc:
            # Once a mutation method is entered, an exception cannot prove no send occurred.
            result = BrokerResult(SubmissionOutcome.SUBMISSION_UNKNOWN)
            uncertainty_code = f"ADAPTER_EXCEPTION_{type(exc).__name__.upper()}"

        self._require_fenced(
            self._store.finish_attempt(
                delivery,
                attempt.attempt_id,
                result.outcome,
                broker_order_id=result.broker_order_id,
                order_state=result.order_state,
                uncertainty_code=uncertainty_code,
            )
        )
        self._require_fenced(self._store.complete_delivery(delivery))
        return ProcessResult(
            delivery.logical_operation_id,
            result.outcome.value,
            attempt.attempt_id,
            uncertainty_code,
        )

    def accept_reconciliation(
        self, attempt_id: str, evidence: ReconciliationEvidence
    ) -> bool:
        attempt = self._store.load_attempt_by_id(attempt_id)
        intent = self._store.load_intent_by_attempt(attempt_id)
        if attempt is None or intent is None:
            raise ExecutionBlocked("UNKNOWN_ATTEMPT_NOT_FOUND")
        if attempt.state != AttemptState.SUBMISSION_UNKNOWN:
            raise ExecutionBlocked("ATTEMPT_NOT_UNKNOWN")
        validate_reconciliation_evidence(attempt, intent, evidence)
        if evidence.disposition == ReconciliationDisposition.UNRESOLVED:
            return False
        return self._store.resolve_unknown(
            attempt_id,
            evidence.disposition,
            evidence,
        )

    def _load_prior_if_required(
        self, intent: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        if intent.get("action_kind") not in {"CANCEL_PENDING_ENTRY", "REPLACE_ORDER"}:
            return None
        source_ref = intent.get("source_ref")
        if not isinstance(source_ref, Mapping):
            raise ExecutionBlocked("PRIOR_INTENT_REFERENCE_MISSING")
        prior = self._store.load_prior_intent(str(source_ref.get("target_id", "")))
        if prior is None:
            raise ExecutionBlocked("PRIOR_INTENT_MISSING")
        if prior.get("id") != source_ref.get("target_id"):
            raise ExecutionBlocked("PRIOR_INTENT_REFERENCE_MISMATCH")
        if prior.get("content_hash") != source_ref.get("content_hash"):
            raise ExecutionBlocked("PRIOR_INTENT_HASH_MISMATCH")
        return prior

    @staticmethod
    def _require_fenced(succeeded: bool) -> None:
        if not succeeded:
            raise FencedLeaseLost("execution mutation rejected by lease fencing")

    def _invoke_broker(
        self, intent: Mapping[str, Any], request: Mapping[str, Any]
    ) -> BrokerResult:
        if intent.get("action_kind") == "CANCEL_PENDING_ENTRY":
            return self._broker.cancel_order(
                request, client_order_key=str(intent["idempotency_key"])
            )
        return self._broker.submit_order(
            request, client_order_key=str(intent["idempotency_key"])
        )


def _validate_queued_intent(
    delivery: OutboxDelivery, intent: Mapping[str, Any]
) -> None:
    try:
        thawed_intent = _thaw_json(intent)
        validate_contract("PaperOrderIntent", thawed_intent)
        verify_content_hash("PaperOrderIntent", thawed_intent)
    except (TypeError, ValueError) as exc:
        raise ExecutionBlocked("INVALID_INTENT_CONTRACT") from exc
    if intent.get("id") != delivery.logical_operation_id:
        raise ExecutionBlocked("OUTBOX_LOGICAL_OPERATION_MISMATCH")
    if intent.get("content_hash") != delivery.payload_hash:
        raise ExecutionBlocked("OUTBOX_PAYLOAD_HASH_MISMATCH")


def _validate_broker_result(
    intent: Mapping[str, Any], result: BrokerResult
) -> None:
    if not isinstance(result, BrokerResult):
        raise ExecutionBlocked("ADAPTER_RESULT_INVALID")
    try:
        outcome = SubmissionOutcome(result.outcome)
    except (TypeError, ValueError) as exc:
        raise ExecutionBlocked("ADAPTER_OUTCOME_INVALID") from exc
    if result.broker_order_id is not None and (
        not isinstance(result.broker_order_id, str) or not result.broker_order_id.strip()
    ):
        raise ExecutionBlocked("ADAPTER_ORDER_ID_INVALID")
    if (
        intent.get("action_kind") == "CANCEL_PENDING_ENTRY"
        and result.order_state not in {None, "CANCEL_REQUESTED", "CANCELLED"}
    ):
        raise ExecutionBlocked("ADAPTER_CANCEL_STATE_INVALID")
    if (
        result.order_state == "CANCELLED"
        and outcome != SubmissionOutcome.ACKNOWLEDGED
    ):
        raise ExecutionBlocked("CANCELLED_WITHOUT_ACKNOWLEDGEMENT")


def _validate_evidence_ref(evidence_ref: Mapping[str, Any]) -> None:
    if (
        evidence_ref.get("target_schema_name")
        != "qc2.integrity_build.EvidenceEvent.v1"
        or not _UUID7_PATTERN.fullmatch(str(evidence_ref.get("target_id", "")))
        or not _SHA256_PATTERN.fullmatch(str(evidence_ref.get("content_hash", "")))
    ):
        raise ExecutionBlocked("RECONCILIATION_EVIDENCE_REFERENCE_INVALID")


def _aware_datetime(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be an aware datetime")
    return value.astimezone(UTC)


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    if isinstance(value, list):
        return [_thaw_json(child) for child in value]
    return value


def _parse_instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ExecutionBlocked(f"{field.upper()}_INVALID")
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise ExecutionBlocked(f"{field.upper()}_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionBlocked(f"{field.upper()}_INVALID")
    return parsed.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return _aware_datetime(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
