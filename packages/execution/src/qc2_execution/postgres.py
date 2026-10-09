"""DB-API PostgreSQL persistence for the paper execution authority.

The injected connection factory must authenticate as ``qc2_runtime_execution``.
This module does not load credentials, change roles, or open provider connections.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from .authority import (
    AttemptRecord,
    AttemptState,
    ExecutionSnapshot,
    OutboxDelivery,
    ReconciliationDisposition,
    ReconciliationEvidence,
    SubmissionOutcome,
)
from .pause import EntryPauseState, PauseCancellationWork, ResumeAssessment


class PostgresExecutionStore:
    """Bind the execution protocol to the least-privilege PostgreSQL functions."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        if not callable(connection_factory):
            raise TypeError("connection_factory must be callable")
        self._connection_factory = connection_factory

    def get_entry_pause_state(self) -> EntryPauseState:
        row = self._query_one("SELECT * FROM qc2_control.get_entry_pause_state()", ())
        if row is None:
            raise RuntimeError("entry-pause state is missing")
        return EntryPauseState(bool(row["entry_paused"]), int(row["generation"]))

    def pause_new_entries(
        self, request_id: str, reason_code: str
    ) -> EntryPauseState:
        row = self._query_one(
            """
            SELECT * FROM qc2_control.pause_new_entries(
              %s::uuid, %s::text
            )
            """,
            (request_id, reason_code),
        )
        if row is None:
            raise RuntimeError("entry-pause transition returned no state")
        return EntryPauseState(bool(row["entry_paused"]), int(row["generation"]))

    def resume_new_entries(
        self, expected_pause_generation: int, assessment: ResumeAssessment
    ) -> EntryPauseState | None:
        row = self._query_one(
            """
            SELECT * FROM qc2_control.resume_new_entries(
              %s::bigint, %s::jsonb
            )
            """,
            (
                expected_pause_generation,
                _json_text(assessment.as_json()),
            ),
        )
        if row is None:
            return None
        return EntryPauseState(bool(row["entry_paused"]), int(row["generation"]))

    def pending_entry_pause_cancellations(
        self,
    ) -> tuple[PauseCancellationWork, ...]:
        row = self._query_one(
            "SELECT qc2_control.pending_entry_pause_cancellations() AS items",
            (),
        )
        if row is None:
            raise RuntimeError("pause cancellation queue query returned no result")
        items = row["items"]
        if isinstance(items, str):
            items = json.loads(items)
        if not isinstance(items, list):
            raise TypeError("pause cancellation queue must be a JSON array")
        result: list[PauseCancellationWork] = []
        for item in items:
            value = _as_mapping(item)
            target = _as_mapping(value["target_intent"])
            result.append(
                PauseCancellationWork(
                    pause_generation=int(value["pause_generation"]),
                    target_intent_id=str(value["target_intent_id"]),
                    target_state=str(target["intent_state"]),
                    target_intent=target,
                    cancel_intent_id=(
                        None
                        if value.get("cancel_intent_id") is None
                        else str(value["cancel_intent_id"])
                    ),
                )
            )
        return tuple(result)

    def reserve_pause_cancel_intent_id(
        self, pause_generation: int, target_intent_id: str, proposed_id: str
    ) -> str:
        row = self._query_one(
            """
            SELECT qc2_control.reserve_pause_cancel_intent_id(
              %s::bigint, %s::uuid, %s::uuid
            ) AS cancel_intent_id
            """,
            (pause_generation, target_intent_id, proposed_id),
        )
        if row is None or row["cancel_intent_id"] is None:
            raise RuntimeError("pause cancellation intent ID could not be reserved")
        return str(row["cancel_intent_id"])

    def mark_pause_cancel_enqueued(
        self, pause_generation: int, target_intent_id: str, cancel_intent_id: str
    ) -> bool:
        row = self._query_one(
            """
            SELECT qc2_control.mark_pause_cancel_enqueued(
              %s::bigint, %s::uuid, %s::uuid
            ) AS marked
            """,
            (pause_generation, target_intent_id, cancel_intent_id),
        )
        return row is not None and bool(row["marked"])

    def persist_intent(
        self, intent: Mapping[str, Any], expected_account_fingerprint: str
    ) -> str:
        row = self._query_one(
            """
            SELECT qc2_control.persist_paper_order_intent(
              %s::jsonb, %s::text
            ) AS intent_id
            """,
            (_json_text(intent), expected_account_fingerprint),
        )
        if row is None or row["intent_id"] is None:
            raise RuntimeError("paper-order intent persistence returned no ID")
        return str(row["intent_id"])

    def transition_intent(self, intent_id: str, next_state: str) -> bool:
        row = self._query_one(
            """
            SELECT qc2_control.transition_paper_order_intent(
              %s::uuid, %s::text
            ) AS transitioned
            """,
            (intent_id, next_state),
        )
        return row is not None and bool(row["transitioned"])

    def reserve_intent(self, intent_id: str) -> None:
        row = self._query_one(
            """
            SELECT qc2_control.reserve_paper_order_intent(
              %s::uuid, NULL::jsonb
            ) AS reservation_id
            """,
            (intent_id,),
        )
        if row is None or row["reservation_id"] is not None:
            raise RuntimeError("cancellation intent reservation result is invalid")

    def enqueue(self, intent_id: str) -> str:
        row = self._query_one(
            "SELECT qc2_control.enqueue_paper_order_submission(%s::uuid) AS message_id",
            (intent_id,),
        )
        if row is None:
            raise RuntimeError("paper submission enqueue returned no message ID")
        return str(row["message_id"])

    def claim_next(self, worker_id: str, lease_seconds: int) -> OutboxDelivery | None:
        row = self._query_one(
            "SELECT * FROM qc2_control.claim_paper_order_submission(%s::uuid, %s::integer)",
            (worker_id, lease_seconds),
        )
        if row is None:
            return None
        return OutboxDelivery(
            message_id=str(row["message_id"]),
            logical_operation_id=str(row["logical_operation_id"]),
            message_type=str(row["message_type"]),
            payload_hash=str(row["payload_hash"]),
            worker_id=str(row["worker_id"]),
            fencing_generation=int(row["fencing_generation"]),
            lease_expires_at=_as_datetime(row["lease_expires_at"]),
        )

    def load_intent(self, intent_id: str) -> Mapping[str, Any] | None:
        row = self._query_one(
            """
            SELECT intent.intent_contract
                     || pg_catalog.jsonb_build_object(
                          'content_hash', intent.content_hash,
                          'intent_state', intent.intent_state
                        ) AS payload
            FROM qc2_execution.paper_order_intent AS intent
            WHERE intent.id = %s::uuid
            """,
            (intent_id,),
        )
        return None if row is None else _as_mapping(row["payload"])

    def load_attempt(self, intent_id: str) -> AttemptRecord | None:
        row = self._query_one(
            "SELECT * FROM qc2_control.get_paper_order_attempt(%s::uuid)",
            (intent_id,),
        )
        return None if row is None else _attempt_from_row(row)

    def load_attempt_by_id(self, attempt_id: str) -> AttemptRecord | None:
        row = self._query_one(
            "SELECT * FROM qc2_control.get_paper_order_attempt_by_id(%s::uuid)",
            (attempt_id,),
        )
        return None if row is None else _attempt_from_row(row)

    def load_intent_by_attempt(self, attempt_id: str) -> Mapping[str, Any] | None:
        row = self._query_one(
            """
            SELECT intent.intent_contract
                     || pg_catalog.jsonb_build_object(
                          'content_hash', intent.content_hash,
                          'intent_state', intent.intent_state
                        ) AS payload
            FROM qc2_execution.paper_execution_attempt AS attempt
            JOIN qc2_execution.paper_order_intent AS intent
              ON intent.id = attempt.intent_id
            WHERE attempt.id = %s::uuid
            """,
            (attempt_id,),
        )
        return None if row is None else _as_mapping(row["payload"])

    def load_prior_intent(self, intent_id: str) -> Mapping[str, Any] | None:
        return self.load_intent(intent_id)

    def begin_attempt(
        self,
        delivery: OutboxDelivery,
        intent: Mapping[str, Any],
        request: Mapping[str, Any],
        request_hash: str,
        snapshot: ExecutionSnapshot,
    ) -> AttemptRecord:
        row = self._query_one(
            """
            SELECT * FROM qc2_control.begin_paper_order_attempt(
              %s::uuid, %s::uuid, %s::bigint, %s::jsonb, %s::text, %s::jsonb
            )
            """,
            (
                delivery.message_id,
                delivery.worker_id,
                delivery.fencing_generation,
                _json_text(request),
                request_hash,
                _json_text(snapshot.as_json()),
            ),
        )
        if row is None:
            raise RuntimeError("begin_paper_order_attempt returned no attempt")
        return _attempt_from_row(row)

    def authorize_attempt(
        self,
        delivery: OutboxDelivery,
        attempt_id: str,
        snapshot: ExecutionSnapshot,
    ) -> bool:
        row = self._query_one(
            """
            SELECT qc2_control.authorize_paper_order_attempt(
              %s::uuid, %s::uuid, %s::bigint, %s::uuid, %s::jsonb
            ) AS authorized
            """,
            (
                delivery.message_id,
                delivery.worker_id,
                delivery.fencing_generation,
                attempt_id,
                _json_text(snapshot.as_json()),
            ),
        )
        return row is not None and bool(row["authorized"])

    def mark_blocked(
        self,
        delivery: OutboxDelivery,
        intent: Mapping[str, Any],
        reason_code: str,
        snapshot: ExecutionSnapshot | None,
        attempt_id: str | None = None,
    ) -> bool:
        row = self._query_one(
            """
            SELECT qc2_control.block_paper_order_attempt(
              %s::uuid, %s::uuid, %s::bigint, %s::uuid, %s::uuid, %s::text, %s::jsonb
            ) AS blocked
            """,
            (
                delivery.message_id,
                delivery.worker_id,
                delivery.fencing_generation,
                str(intent["id"]),
                attempt_id,
                reason_code,
                None if snapshot is None else _json_text(snapshot.as_json()),
            ),
        )
        return row is not None and bool(row["blocked"])

    def finish_attempt(
        self,
        delivery: OutboxDelivery,
        attempt_id: str,
        outcome: SubmissionOutcome,
        *,
        broker_order_id: str | None = None,
        order_state: str | None = None,
        uncertainty_code: str | None = None,
    ) -> bool:
        row = self._query_one(
            """
            SELECT qc2_control.finish_paper_order_attempt(
              %s::uuid, %s::uuid, %s::bigint, %s::uuid, %s::text,
              %s::text, %s::text, %s::text
            ) AS finished
            """,
            (
                delivery.message_id,
                delivery.worker_id,
                delivery.fencing_generation,
                attempt_id,
                SubmissionOutcome(outcome).value,
                broker_order_id,
                order_state,
                uncertainty_code,
            ),
        )
        return row is not None and bool(row["finished"])

    def mark_unknown(self, delivery: OutboxDelivery, attempt_id: str) -> bool:
        row = self._query_one(
            """
            SELECT qc2_control.mark_paper_order_attempt_unknown(
              %s::uuid, %s::uuid, %s::bigint, %s::uuid
            ) AS marked_unknown
            """,
            (
                delivery.message_id,
                delivery.worker_id,
                delivery.fencing_generation,
                attempt_id,
            ),
        )
        return row is not None and bool(row["marked_unknown"])

    def complete_delivery(self, delivery: OutboxDelivery) -> bool:
        row = self._query_one(
            """
            SELECT qc2_control.complete_paper_order_submission(
              %s::uuid, %s::uuid, %s::bigint
            ) AS completed
            """,
            (
                delivery.message_id,
                delivery.worker_id,
                delivery.fencing_generation,
            ),
        )
        return row is not None and bool(row["completed"])

    def defer_delivery(self, delivery: OutboxDelivery, reason_code: str) -> bool:
        row = self._query_one(
            """
            SELECT qc2_control.defer_paper_order_submission(
              %s::uuid, %s::uuid, %s::bigint, %s::text
            ) AS deferred
            """,
            (
                delivery.message_id,
                delivery.worker_id,
                delivery.fencing_generation,
                reason_code,
            ),
        )
        return row is not None and bool(row["deferred"])

    def resolve_unknown(
        self,
        attempt_id: str,
        disposition: ReconciliationDisposition,
        evidence: ReconciliationEvidence,
    ) -> bool:
        evidence_payload = {
            "intent_id": evidence.intent_id,
            "account_fingerprint": evidence.account_fingerprint,
            "client_order_key": evidence.client_order_key,
            "normalized_request_hash": evidence.normalized_request_hash,
            "disposition": ReconciliationDisposition(disposition).value,
            "checked_sources": list(evidence.checked_sources),
            "consistency_window_closed": evidence.consistency_window_closed,
            "broker_order_id": evidence.broker_order_id,
            "evidence_ref": _as_json_value(evidence.evidence_ref),
        }
        row = self._query_one(
            """
            SELECT qc2_control.resolve_paper_order_attempt_unknown(
              %s::uuid, %s::jsonb
            ) AS resolved
            """,
            (attempt_id, _json_text(evidence_payload)),
        )
        return row is not None and bool(row["resolved"])

    def _query_one(self, statement: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(statement, parameters)
            raw_row = cursor.fetchone()
            connection.commit()
            if raw_row is None:
                return None
            if isinstance(raw_row, Mapping):
                return dict(raw_row)
            columns = [
                _column_name(description)
                for description in (cursor.description or ())
            ]
            if len(columns) != len(raw_row):
                raise RuntimeError("database row shape does not match cursor metadata")
            return dict(zip(columns, raw_row, strict=True))
        except BaseException:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()


def _attempt_from_row(row: Mapping[str, Any]) -> AttemptRecord:
    state = str(row["attempt_state"])
    if state == "SUBMISSION_STARTED":
        state = AttemptState.STARTED.value
    return AttemptRecord(
        attempt_id=str(row["attempt_id"]),
        intent_id=str(row["intent_id"]),
        attempt_number=int(row["attempt_number"]),
        state=AttemptState(state),
        created=bool(row["created"]),
        client_order_key=str(row["client_order_key"]),
        normalized_request_hash=str(row["normalized_request_hash"]),
        started_at=_as_datetime(row["started_at"]),
        broker_order_id=(
            None if row.get("broker_order_id") is None else str(row["broker_order_id"])
        ),
    )


def _as_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TypeError("database timestamp must be a timezone-aware datetime")
    return value


def _column_name(description: Any) -> str:
    if hasattr(description, "name"):
        return str(description.name)
    return str(description[0])


def _as_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("database JSON value must be an object")
    return dict(value)


def _as_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _as_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_as_json_value(item) for item in value]
    return value


def _json_text(value: Any) -> str:
    return json.dumps(
        _as_json_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
