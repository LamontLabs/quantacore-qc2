from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import pytest

from qc2_execution import (
    AttemptRecord,
    AttemptState,
    BrokerResult,
    ExecutionAuthority,
    ExecutionSnapshot,
    FencedLeaseLost,
    OutboxDelivery,
    ReadinessAssessmentSnapshot,
    SubmissionOutcome,
    build_paper_order_intent,
)


NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
ACCOUNT = "a" * 64
WORKER_ID = "018f0000-0000-7000-8000-000000000001"
WORKER_ID_2 = "018f0000-0000-7000-8000-000000000002"
MESSAGE_ID = "018f0000-0000-7000-8000-000000000003"
ATTEMPT_ID = "018f0000-0000-7000-8000-000000000004"
RESERVATION_ID = "018f0000-0000-7000-8000-000000000005"
PRIOR_ID = "018f0000-0000-7000-8000-000000000006"
ASSESSMENT_ID = "018f0000-0000-7000-8000-000000000007"
INSTRUMENT_ID = "018f0000-0000-7000-8000-000000000008"
ASSIGNMENT_ID = "018f0000-0000-7000-8000-000000000009"


def _reference(schema_name: str, target_id: str, content_hash: str | None = None):
    result = {"target_schema_name": schema_name, "target_id": target_id}
    if content_hash is not None:
        result["content_hash"] = content_hash
    return result


def _make_intent(
    fixture: dict[str, Any],
    *,
    key: str,
    intent_id: str,
    action: str = "OPEN_LONG",
    side: str = "BUY",
    state: str = "QUEUED_FOR_SUBMISSION",
    source_ref: dict[str, Any] | None = None,
    reservation_id: str | None = RESERVATION_ID,
) -> dict[str, Any]:
    payload = deepcopy(fixture)
    payload.update(
        {
            "id": intent_id,
            "created_at": "2026-10-08T11:55:00Z",
            "paper_account_fingerprint": ACCOUNT,
            "account_mode": "PAPER",
            "action_kind": action,
            "side": side,
            "quantity_whole_shares": 2,
            "limit_price": "10",
            "expires_at": "2026-10-08T12:30:00Z",
            "idempotency_key": key,
            "intent_state": "CREATED",
            "reservation_ref": (
                None
                if action == "CANCEL_PENDING_ENTRY"
                else _reference("qc2.execution.Reservation.v1", reservation_id or RESERVATION_ID)
            ),
            "instrument_ref": _reference(
                "qc2.identity_market.Instrument.v1", INSTRUMENT_ID
            ),
            "symbol_assignment_ref": _reference(
                "qc2.identity_market.SymbolAssignment.v1", ASSIGNMENT_ID
            ),
            "content_hash": "0" * 64,
        }
    )
    if source_ref is not None:
        payload["source_ref"] = source_ref
    intent = build_paper_order_intent(
        payload,
        expected_account_fingerprint=ACCOUNT,
        now=NOW,
    )
    result = intent.payload
    result["intent_state"] = state
    return result


def _prior_intent(fixture: dict[str, Any], *, state: str = "ACKNOWLEDGED"):
    intent = _make_intent(
        fixture,
        key="prior-entry",
        intent_id=PRIOR_ID,
        state=state,
    )
    return intent


def _snapshot(
    intent: dict[str, Any],
    *,
    paused: bool = False,
    prior_state: str | None = None,
    prior_reservation_active: bool | None = None,
    current_session: str | None = None,
) -> ExecutionSnapshot:
    action = {
        "OPEN_LONG": "NEW_ENTRY",
        "CANCEL_PENDING_ENTRY": "CANCEL_ENTRY",
        "REPLACE_ORDER": "NEW_ENTRY",
    }[intent["action_kind"]]
    return ExecutionSnapshot(
        paper_account_fingerprint=ACCOUNT,
        account_mode="PAPER",
        paper_endpoint_verified=True,
        entry_paused=paused,
        current_session=current_session
        if current_session is not None
        else intent["target_execution_session"],
        session_open=True,
        reservation_active=True,
        symbol_assignment_id=ASSIGNMENT_ID,
        broker_symbol="XYZ",
        readiness=(
            ReadinessAssessmentSnapshot(
                assessment_id=ASSESSMENT_ID,
                action=action,
                status="READY",
                input_generation=1,
                freshness_deadline=NOW + timedelta(minutes=5),
            ),
        ),
        prior_intent_state=prior_state,
        prior_reservation_active=prior_reservation_active,
        prior_broker_order_id="broker-prior-17" if prior_state else None,
    )


class MemoryStore:
    def __init__(
        self,
        intent: dict[str, Any],
        *,
        prior: dict[str, Any] | None = None,
    ) -> None:
        self.intent = deepcopy(intent)
        self.prior = deepcopy(prior)
        self.delivery = OutboxDelivery(
            message_id=MESSAGE_ID,
            logical_operation_id=intent["id"],
            message_type="paper_order_submission",
            payload_hash=intent["content_hash"],
            worker_id=WORKER_ID,
            fencing_generation=1,
            lease_expires_at=NOW + timedelta(minutes=1),
        )
        self.current_generation = 1
        self.attempt: AttemptRecord | None = None
        self.request: dict[str, Any] | None = None
        self.request_hash: str | None = None
        self.completed = False
        self.deferred_reason: str | None = None
        self.prior_reservation_active = prior is not None
        self.stale_on_authorize = False

    def claim_next(self, worker_id: str, lease_seconds: int):
        return replace(
            self.delivery,
            worker_id=worker_id,
            fencing_generation=self.current_generation,
            lease_expires_at=NOW + timedelta(seconds=lease_seconds),
        )

    def load_intent(self, intent_id: str):
        return deepcopy(self.intent) if self.intent["id"] == intent_id else None

    def load_attempt(self, intent_id: str):
        return self.attempt if self.attempt and self.attempt.intent_id == intent_id else None

    def load_attempt_by_id(self, attempt_id: str):
        return self.attempt if self.attempt and self.attempt.attempt_id == attempt_id else None

    def load_intent_by_attempt(self, attempt_id: str):
        if self.attempt is None or self.attempt.attempt_id != attempt_id:
            return None
        return deepcopy(self.intent)

    def load_prior_intent(self, intent_id: str):
        return deepcopy(self.prior) if self.prior and self.prior["id"] == intent_id else None

    def enqueue(self, intent_id: str):
        assert intent_id == self.intent["id"]
        return MESSAGE_ID

    def begin_attempt(self, delivery, intent, request, request_hash, snapshot):
        self.request = deepcopy(dict(request))
        self.request_hash = request_hash
        if self.attempt:
            return replace(self.attempt, created=False)
        self.attempt = AttemptRecord(
            attempt_id=ATTEMPT_ID,
            intent_id=intent["id"],
            attempt_number=1,
            state=AttemptState.STARTED,
            created=True,
            client_order_key=intent["idempotency_key"],
            normalized_request_hash=request_hash,
            started_at=NOW,
        )
        self.intent["intent_state"] = "SUBMISSION_STARTED"
        return self.attempt

    def authorize_attempt(self, delivery, attempt_id, snapshot):
        if self.stale_on_authorize:
            self.current_generation += 1
            return False
        return self._current(delivery) and self.attempt is not None

    def mark_blocked(self, delivery, intent, reason_code, snapshot, attempt_id=None):
        if not self._current(delivery):
            return False
        if self.attempt and attempt_id == self.attempt.attempt_id:
            self.attempt = replace(self.attempt, state=AttemptState.BLOCKED)
            self.intent["intent_state"] = "REJECTED"
        else:
            self.intent["intent_state"] = "CANCELLED"
        return True

    def finish_attempt(
        self,
        delivery,
        attempt_id,
        outcome,
        *,
        broker_order_id=None,
        order_state=None,
        uncertainty_code=None,
    ):
        if not self._current(delivery) or self.attempt is None:
            return False
        outcome = SubmissionOutcome(outcome)
        self.attempt = replace(
            self.attempt,
            state=AttemptState(outcome.value),
            broker_order_id=broker_order_id,
        )
        self.intent["intent_state"] = outcome.value
        if (
            self.intent["action_kind"] == "CANCEL_PENDING_ENTRY"
            and outcome == SubmissionOutcome.ACKNOWLEDGED
            and order_state == "CANCELLED"
        ):
            self.prior_reservation_active = False
        return True

    def mark_unknown(self, delivery, attempt_id):
        if not self._current(delivery) or self.attempt is None:
            return False
        self.attempt = replace(
            self.attempt, state=AttemptState.SUBMISSION_UNKNOWN
        )
        self.intent["intent_state"] = "SUBMISSION_UNKNOWN"
        return True

    def complete_delivery(self, delivery):
        if not self._current(delivery):
            return False
        self.completed = True
        return True

    def defer_delivery(self, delivery, reason_code):
        if not self._current(delivery):
            return False
        self.deferred_reason = reason_code
        return True

    def resolve_unknown(self, attempt_id, disposition, evidence):
        return self.attempt is not None and self.attempt.attempt_id == attempt_id

    def reclaim(self):
        self.current_generation += 1
        self.completed = False
        self.delivery = replace(
            self.delivery,
            worker_id=WORKER_ID_2,
            fencing_generation=self.current_generation,
        )

    def _current(self, delivery):
        return delivery.fencing_generation == self.current_generation


class SequenceGate:
    def __init__(self, *snapshots: ExecutionSnapshot):
        self.snapshots = list(snapshots)

    def snapshot(self, intent):
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]


class FakeBroker:
    def __init__(self, *, submit_result=None, submit_error=None, cancel_result=None):
        self.submit_result = submit_result
        self.submit_error = submit_error
        self.cancel_result = cancel_result
        self.submit_calls = 0
        self.cancel_calls = 0
        self.accepted_before_timeout = False

    def submit_order(self, request, *, client_order_key):
        self.submit_calls += 1
        if self.submit_error is not None:
            self.accepted_before_timeout = True
            raise self.submit_error
        return self.submit_result or BrokerResult(SubmissionOutcome.ACKNOWLEDGED)

    def cancel_order(self, request, *, client_order_key):
        self.cancel_calls += 1
        return self.cancel_result or BrokerResult(SubmissionOutcome.SUBMISSION_UNKNOWN)


def _authority(store, gate, broker):
    return ExecutionAuthority(
        store=store,
        gate_provider=gate,
        broker=broker,
        worker_id=WORKER_ID,
        clock=lambda: NOW,
    )


def test_timeout_after_acceptance_is_unknown_and_duplicate_is_not_resent(
    valid_intent_fixture,
):
    intent = _make_intent(
        valid_intent_fixture,
        key="timeout-after-acceptance",
        intent_id="018f0000-0000-7000-8000-000000000010",
    )
    store = MemoryStore(intent)
    snapshot = _snapshot(intent)
    broker = FakeBroker(submit_error=TimeoutError("response timed out"))
    authority = _authority(store, SequenceGate(snapshot), broker)

    first = authority.process_one()

    assert first is not None and first.state == "SUBMISSION_UNKNOWN"
    assert broker.accepted_before_timeout
    assert broker.submit_calls == 1
    assert store.attempt is not None
    assert store.attempt.state == AttemptState.SUBMISSION_UNKNOWN
    assert store.intent["intent_state"] == "SUBMISSION_UNKNOWN"

    store.reclaim()
    duplicate = authority.process_one()

    assert duplicate is not None and duplicate.state == "SUBMISSION_UNKNOWN"
    assert duplicate.reason_code == "DUPLICATE_DELIVERY_ALREADY_RECORDED"
    assert broker.submit_calls == 1


def test_just_in_time_gate_change_blocks_without_broker_mutation(valid_intent_fixture):
    intent = _make_intent(
        valid_intent_fixture,
        key="jit-pause",
        intent_id="018f0000-0000-7000-8000-000000000011",
    )
    store = MemoryStore(intent)
    broker = FakeBroker()
    gate = SequenceGate(_snapshot(intent), _snapshot(intent, paused=True))

    result = _authority(store, gate, broker).process_one()

    assert result is not None and result.state == AttemptState.BLOCKED.value
    assert result.reason_code == "NEW_ENTRY_PAUSED"
    assert broker.submit_calls == 0
    assert store.attempt is not None
    assert store.attempt.state == AttemptState.BLOCKED
    assert store.completed


def test_lost_fencing_generation_prevents_send(valid_intent_fixture):
    intent = _make_intent(
        valid_intent_fixture,
        key="stale-fence",
        intent_id="018f0000-0000-7000-8000-000000000012",
    )
    store = MemoryStore(intent)
    store.stale_on_authorize = True
    broker = FakeBroker()
    with pytest.raises(FencedLeaseLost):
        _authority(store, SequenceGate(_snapshot(intent)), broker).process_one()

    assert broker.submit_calls == 0
    assert store.attempt is not None
    assert store.attempt.state == AttemptState.STARTED
    assert not store.completed


def test_replacement_waits_while_prior_order_or_reservation_is_active(
    valid_intent_fixture,
):
    prior = _prior_intent(valid_intent_fixture)
    replacement = _make_intent(
        valid_intent_fixture,
        key="replacement-waits",
        intent_id="018f0000-0000-7000-8000-000000000013",
        action="REPLACE_ORDER",
        source_ref=_reference(
            "qc2.execution.PaperOrderIntent.v1",
            prior["id"],
            prior["content_hash"],
        ),
    )
    store = MemoryStore(replacement, prior=prior)
    snapshot = _snapshot(
        replacement,
        prior_state="ACKNOWLEDGED",
        prior_reservation_active=True,
    )
    broker = FakeBroker()

    result = _authority(store, SequenceGate(snapshot), broker).process_one()

    assert result is not None and result.state == "DEFERRED"
    assert result.reason_code == "PRIOR_ORDER_NOT_DEFINITIVELY_TERMINAL"
    assert store.deferred_reason == result.reason_code
    assert store.prior_reservation_active
    assert store.attempt is None
    assert broker.submit_calls == 0
    assert not store.completed


@pytest.mark.parametrize(
    ("result", "expected_reservation_active"),
    [
        (BrokerResult(SubmissionOutcome.SUBMISSION_UNKNOWN), True),
        (
            BrokerResult(
                SubmissionOutcome.ACKNOWLEDGED,
                order_state="CANCELLED",
            ),
            False,
        ),
    ],
)
def test_cancel_only_releases_prior_reservation_after_definitive_cancel(
    valid_intent_fixture,
    result,
    expected_reservation_active,
):
    prior = _prior_intent(valid_intent_fixture)
    cancel = _make_intent(
        valid_intent_fixture,
        key="cancel-prior-entry",
        intent_id="018f0000-0000-7000-8000-000000000014",
        action="CANCEL_PENDING_ENTRY",
        side="BUY",
        source_ref=_reference(
            "qc2.execution.PaperOrderIntent.v1",
            prior["id"],
            prior["content_hash"],
        ),
        reservation_id=None,
    )
    store = MemoryStore(cancel, prior=prior)
    snapshot = _snapshot(
        cancel,
        prior_state="ACKNOWLEDGED",
        prior_reservation_active=True,
    )
    broker = FakeBroker(cancel_result=result)

    processed = _authority(store, SequenceGate(snapshot), broker).process_one()

    assert processed is not None
    assert broker.cancel_calls == 1
    assert store.prior_reservation_active is expected_reservation_active
    assert store.attempt is not None
    assert store.attempt.state == AttemptState(result.outcome.value)


def test_crash_after_attempt_start_recovers_as_unknown_without_retry(
    valid_intent_fixture,
):
    intent = _make_intent(
        valid_intent_fixture,
        key="crash-after-start",
        intent_id="018f0000-0000-7000-8000-000000000015",
        state="SUBMISSION_STARTED",
    )
    store = MemoryStore(intent)
    store.attempt = AttemptRecord(
        attempt_id=ATTEMPT_ID,
        intent_id=intent["id"],
        attempt_number=1,
        state=AttemptState.STARTED,
        created=True,
        client_order_key=intent["idempotency_key"],
        normalized_request_hash="b" * 64,
        started_at=NOW,
    )
    store.reclaim()
    broker = FakeBroker()

    result = _authority(
        store, SequenceGate(_snapshot(intent)), broker
    ).process_one()

    assert result is not None and result.state == "SUBMISSION_UNKNOWN"
    assert result.reason_code == "RECOVERED_STARTED_ATTEMPT_AS_UNKNOWN"
    assert broker.submit_calls == 0
    assert store.attempt.state == AttemptState.SUBMISSION_UNKNOWN
