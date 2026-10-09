from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from qc2_execution.authority import AttemptState
from qc2_execution.postgres import PostgresExecutionStore


class FakeCursor:
    def __init__(self, row: Any, *, description: list[Any] | None = None) -> None:
        self.row = row
        self.description = description
        self.statement: str | None = None
        self.parameters: tuple[Any, ...] | None = None
        self.closed = False
        self.error: Exception | None = None

    def execute(self, statement: str, parameters: tuple[Any, ...]) -> None:
        self.statement = statement
        self.parameters = parameters
        if self.error is not None:
            raise self.error

    def fetchone(self) -> Any:
        return self.row

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, row: Any, *, error: Exception | None = None) -> None:
        self.cursor_instance = FakeCursor(
            row,
            description=(
                [("message_id",)]
                if isinstance(row, tuple)
                else None
            ),
        )
        self.cursor_instance.error = error
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_claim_next_maps_db_api_values_and_closes_connection() -> None:
    lease_expiry = datetime(2026, 10, 8, 12, 30, tzinfo=timezone.utc)
    connection = FakeConnection(
        {
            "message_id": "00000000-0000-7000-8000-000000000001",
            "logical_operation_id": "00000000-0000-7000-8000-000000000002",
            "message_type": "paper_order_submission",
            "payload_hash": "a" * 64,
            "worker_id": "00000000-0000-7000-8000-000000000003",
            "fencing_generation": 4,
            "lease_expires_at": lease_expiry,
        }
    )
    store = PostgresExecutionStore(lambda: connection)

    delivery = store.claim_next("00000000-0000-7000-8000-000000000003", 45)

    assert delivery is not None
    assert delivery.message_id == "00000000-0000-7000-8000-000000000001"
    assert delivery.logical_operation_id == "00000000-0000-7000-8000-000000000002"
    assert delivery.fencing_generation == 4
    assert delivery.lease_expires_at is lease_expiry
    assert "claim_paper_order_submission" in connection.cursor_instance.statement
    assert connection.cursor_instance.parameters == (
        "00000000-0000-7000-8000-000000000003",
        45,
    )
    assert connection.committed
    assert not connection.rolled_back
    assert connection.cursor_instance.closed
    assert connection.closed


def test_attempt_loader_maps_started_state_to_protocol_enum() -> None:
    started_at = datetime(2026, 10, 8, 12, 29, tzinfo=timezone.utc)
    connection = FakeConnection(
        {
            "attempt_id": "00000000-0000-7000-8000-000000000004",
            "intent_id": "00000000-0000-7000-8000-000000000002",
            "attempt_number": 1,
            "attempt_state": "SUBMISSION_STARTED",
            "created": True,
            "client_order_key": "paper-key",
            "normalized_request_hash": "b" * 64,
            "started_at": started_at,
            "broker_order_id": None,
        }
    )
    store = PostgresExecutionStore(lambda: connection)

    attempt = store.load_attempt("00000000-0000-7000-8000-000000000002")

    assert attempt is not None
    assert attempt.state is AttemptState.STARTED
    assert attempt.created
    assert attempt.intent_id == "00000000-0000-7000-8000-000000000002"
    assert "get_paper_order_attempt" in connection.cursor_instance.statement
    assert connection.cursor_instance.parameters == (
        "00000000-0000-7000-8000-000000000002",
    )
    assert connection.committed
    assert connection.closed


def test_tuple_rows_are_mapped_and_failures_roll_back() -> None:
    connection = FakeConnection(("message-2",))
    store = PostgresExecutionStore(lambda: connection)

    assert store.enqueue("intent-2") == "message-2"
    assert connection.cursor_instance.statement is not None
    assert "enqueue_paper_order_submission" in connection.cursor_instance.statement
    assert connection.committed

    failing_connection = FakeConnection(None, error=RuntimeError("database failed"))
    failing_store = PostgresExecutionStore(lambda: failing_connection)
    try:
        failing_store.enqueue("intent-3")
    except RuntimeError as error:
        assert str(error) == "database failed"
    else:
        raise AssertionError("database error should propagate")
    assert failing_connection.rolled_back
    assert not failing_connection.committed
    assert failing_connection.cursor_instance.closed
    assert failing_connection.closed
