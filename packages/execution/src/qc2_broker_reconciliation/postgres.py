"""PostgreSQL persistence for stable reconciliation checkpoints and explicit holds."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping

from qc2_contracts.runtime import validate_contract

from .reconcile import ReconciliationDraft


@dataclass(frozen=True, slots=True)
class PersistedReconciliation:
    checkpoint_id: str
    checkpoint_hash: str
    generation: int
    report_contract: Mapping[str, Any]
    active_finding_keys: tuple[str, ...]
    already_recorded: bool


class PostgresReconciliationStore:
    """Narrow persistence boundary; SQL routines own holds and idempotency."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        if not callable(connection_factory):
            raise ValueError("connection_factory must be callable")
        self._connection_factory = connection_factory

    def record(self, draft: ReconciliationDraft) -> PersistedReconciliation:
        result = self._query_one(
            """
            SELECT qc2_control.record_broker_reconciliation(%s::jsonb) AS result
            """,
            (_json_text(draft.persistence_payload()),),
        )
        if result is None:
            raise RuntimeError("reconciliation persistence returned no result")
        payload = _json_value(result["result"])
        if not isinstance(payload, Mapping):
            raise RuntimeError("reconciliation persistence returned an invalid result")
        report = payload.get("report_contract")
        if not isinstance(report, Mapping):
            raise RuntimeError("reconciliation persistence omitted the report contract")
        validate_contract("ReconciliationReport", dict(report))
        if report.get("id") != payload.get("checkpoint_id"):
            raise RuntimeError("report ID and stable checkpoint ID do not match")
        if payload.get("checkpoint_hash") != draft.checkpoint_hash:
            raise RuntimeError("persisted checkpoint hash does not match the input snapshot")
        generation = payload.get("generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise RuntimeError("persisted checkpoint generation is invalid")
        active = payload.get("active_finding_keys")
        if not isinstance(active, list) or any(not isinstance(item, str) for item in active):
            raise RuntimeError("persisted active finding list is invalid")
        return PersistedReconciliation(
            checkpoint_id=str(payload["checkpoint_id"]),
            checkpoint_hash=str(payload["checkpoint_hash"]),
            generation=generation,
            report_contract=dict(report),
            active_finding_keys=tuple(active),
            already_recorded=bool(payload.get("already_recorded", False)),
        )

    def resolve_finding(
        self,
        *,
        episode_id: str,
        finding_key: str,
        resolution_code: str,
        resolution_note: str,
        evidence_ref: Mapping[str, Any],
    ) -> bool:
        if not isinstance(evidence_ref, Mapping):
            raise ValueError("resolution evidence_ref must be a typed EvidenceEvent reference")
        payload = _json_text(dict(evidence_ref))
        row = self._query_one(
            """
            SELECT qc2_control.resolve_broker_reconciliation_finding(
              %s::uuid, %s::text, %s::text, %s::text, %s::jsonb
            ) AS resolved
            """,
            (
                episode_id,
                finding_key,
                resolution_code,
                resolution_note,
                payload,
            ),
        )
        return row is not None and bool(row.get("resolved"))

    def _query_one(
        self, statement: str, parameters: tuple[Any, ...]
    ) -> dict[str, Any] | None:
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
                description.name
                if hasattr(description, "name")
                else description[0]
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


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value
