"""Narrow PostgreSQL adapter for rebuilding owner read-model snapshots."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from .read_models import (
    OwnerReadErrorCode,
    OwnerReadModelError,
    ProjectionSnapshot,
)


class PostgresOwnerReadModelWriter:
    """Persists only the isolated owner projection, watermark, and export-audit functions."""

    fixture_only = False

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        if not callable(connection_factory):
            raise TypeError("connection_factory must be callable")
        self._connection_factory = connection_factory

    def advance_source(
        self, environment_namespace: str, view_name: str, source_highwater_sequence: int
    ) -> dict[str, Any]:
        result = self._call(
            """
            SELECT qc2_owner_api.owner_projection_advance_source(
              %s::text, %s::text, %s::bigint
            ) AS result
            """,
            (environment_namespace, view_name, source_highwater_sequence),
        )
        self._require_status(result, "ADVANCED")
        return result

    def persist(self, snapshot: ProjectionSnapshot) -> dict[str, Any]:
        result = self._call(
            """
            SELECT qc2_owner_api.owner_projection_rebuild(
              %s::text, %s::text, %s::bigint, %s::bigint, %s::bigint,
              %s::timestamptz, %s::timestamptz, %s::jsonb, %s::jsonb, %s::text
            ) AS result
            """,
            (
                snapshot.environment_namespace,
                snapshot.view_name,
                snapshot.projection_sequence,
                snapshot.source_sequence,
                snapshot.source_highwater_sequence,
                snapshot.built_at,
                snapshot.freshness_deadline,
                _json(snapshot.source_refs),
                _json(snapshot.items),
                snapshot.snapshot_hash,
            ),
        )
        self._require_status(result, "BUILT")
        if result.get("projection_sequence") != snapshot.projection_sequence:
            raise RuntimeError("owner projection database sequence mismatch")
        return result

    def record_export(
        self,
        *,
        environment_namespace: str,
        session_record_id: str,
        view_name: str,
        projection_sequence: int,
        item_count: int,
        response_bytes: int,
    ) -> None:
        result = self._call(
            """
            SELECT qc2_owner_api.owner_projection_record_export(
              %s::text, %s::uuid, %s::text, %s::bigint, %s::integer, %s::integer
            ) AS result
            """,
            (
                environment_namespace,
                session_record_id,
                view_name,
                projection_sequence,
                item_count,
                response_bytes,
            ),
        )
        self._require_status(result, "RECORDED")

    def _call(self, statement: str, parameters: tuple[Any, ...]) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, parameters)
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("owner projection function returned no result")
                result = row["result"] if isinstance(row, Mapping) else row[0]
                if isinstance(result, str):
                    result = json.loads(result)
                if not isinstance(result, dict):
                    raise TypeError("owner projection database result must be an object")
                connection.commit()
                return result
            finally:
                cursor.close()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _require_status(result: dict[str, Any], expected: str) -> None:
        if result.get("status") != expected:
            raise OwnerReadModelError(OwnerReadModelErrorCode.INVALID_INPUT)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
