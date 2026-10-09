"""DB-API adapter for the least-privilege PostgreSQL identity functions."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from .identity import (
    IdentityAuthorityError,
    IdentityErrorCode,
    IdentityStatus,
    _format_instant,
)


class PostgresIdentityRepository:
    """Durable identity repository; the injected connection must use qc2_runtime_identity."""

    fixture_only = False

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        if not callable(connection_factory):
            raise TypeError("connection_factory must be callable")
        self._connection_factory = connection_factory

    def bootstrap_state(self, environment_namespace: str) -> dict[str, Any]:
        result = self._call(
            "SELECT qc2_governance_owner.identity_bootstrap_state(%s::text) AS result",
            (environment_namespace,),
        )
        self._require_status(result, "FOUND")
        return result

    def store_enrollment_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], pending: dict[str, Any]
    ) -> None:
        self._call(
            """
            SELECT qc2_governance_owner.identity_store_bootstrap_challenge(
              %s::text, %s::jsonb, %s::jsonb
            ) AS result
            """,
            (environment_namespace, _json(challenge), _json(pending)),
        )

    def get_enrollment_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> dict[str, Any]:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_get_bootstrap_challenge(
              %s::text, %s::uuid
            ) AS result
            """,
            (environment_namespace, challenge_id),
        )
        self._require_status(result, "FOUND")
        return result

    def complete_bootstrap(
        self,
        *,
        environment_namespace: str,
        challenge_id: str,
        bootstrap_verifier_hash: str,
        device_record: dict[str, Any],
        session_record: dict[str, Any],
        access_token_hash: str,
        refresh_token_hash: str,
        refresh_expires_at: datetime,
        recovery_verifier_hash: str,
        now: datetime,
    ) -> None:
        self._call(
            """
            SELECT qc2_governance_owner.identity_complete_bootstrap(
              %s::text, %s::uuid, %s::text, %s::jsonb, %s::jsonb,
              %s::text, %s::text, %s::timestamptz, %s::text, %s::timestamptz
            ) AS result
            """,
            (
                environment_namespace,
                challenge_id,
                bootstrap_verifier_hash,
                _json(device_record),
                _json(session_record),
                access_token_hash,
                refresh_token_hash,
                _format_instant(refresh_expires_at),
                recovery_verifier_hash,
                _format_instant(now),
            ),
        )

    def resolve_access(
        self, environment_namespace: str, access_token_hash: str, *, now: datetime
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_resolve_access(
              %s::text, %s::text, %s::timestamptz
            ) AS result
            """,
            (environment_namespace, access_token_hash, _format_instant(now)),
        )
        self._require_status(result, "VALID")
        return result["device_record"], result["session_record"]

    def refresh_context(
        self, environment_namespace: str, refresh_token_hash: str, *, now: datetime
    ) -> dict[str, Any]:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_refresh_context(
              %s::text, %s::text, %s::timestamptz
            ) AS result
            """,
            (environment_namespace, refresh_token_hash, _format_instant(now)),
        )
        self._require_status(result, "VALID")
        return {
            "device_record": result["device_record"],
            "session_record": result["session_record"],
        }

    def rotate_refresh(
        self,
        *,
        environment_namespace: str,
        refresh_token_hash: str,
        session_record: dict[str, Any],
        access_token_hash: str,
        new_refresh_token_hash: str,
        refresh_expires_at: datetime,
        now: datetime,
    ) -> None:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_rotate_refresh(
              %s::text, %s::text, %s::jsonb, %s::text, %s::text,
              %s::timestamptz, %s::timestamptz
            ) AS result
            """,
            (
                environment_namespace,
                refresh_token_hash,
                _json(session_record),
                access_token_hash,
                new_refresh_token_hash,
                _format_instant(refresh_expires_at),
                _format_instant(now),
            ),
        )
        self._require_status(result, "ROTATED")

    def store_command_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], binding: dict[str, Any]
    ) -> None:
        self._call(
            """
            SELECT qc2_governance_owner.identity_store_command_challenge(
              %s::text, %s::jsonb, %s::jsonb
            ) AS result
            """,
            (environment_namespace, _json(challenge), _json(binding)),
        )

    def get_command_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_get_command_challenge(
              %s::text, %s::uuid
            ) AS result
            """,
            (environment_namespace, challenge_id),
        )
        self._require_status(result, "FOUND")
        return result["challenge"], result["binding"]

    def commit_owner_command(
        self,
        *,
        environment_namespace: str,
        challenge_id: str,
        owner_command: dict[str, Any],
        idempotency_key: str,
        target_device_id: str | None,
        now: datetime,
    ) -> dict[str, Any]:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_commit_owner_command(
              %s::text, %s::uuid, %s::jsonb, %s::text, %s::uuid,
              %s::timestamptz
            ) AS result
            """,
            (
                environment_namespace,
                challenge_id,
                _json(owner_command),
                idempotency_key,
                target_device_id,
                _format_instant(now),
            ),
        )
        self._require_status(result, "COMMITTED", "DUPLICATE")
        return result["owner_command"]

    def verify_recovery_material(
        self, environment_namespace: str, recovery_verifier_hash: str
    ) -> None:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_verify_recovery_material(
              %s::text, %s::text
            ) AS result
            """,
            (environment_namespace, recovery_verifier_hash),
        )
        self._require_status(result, "VALID")

    def issue_recovery_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], pending: dict[str, Any]
    ) -> None:
        self._call(
            """
            SELECT qc2_governance_owner.identity_store_recovery_challenge(
              %s::text, %s::jsonb, %s::jsonb
            ) AS result
            """,
            (environment_namespace, _json(challenge), _json(pending)),
        )

    def get_recovery_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> dict[str, Any]:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_get_recovery_challenge(
              %s::text, %s::uuid
            ) AS result
            """,
            (environment_namespace, challenge_id),
        )
        self._require_status(result, "FOUND")
        return result

    def complete_recovery(
        self,
        *,
        environment_namespace: str,
        challenge_id: str,
        recovery_verifier_hash: str,
        replacement_device: dict[str, Any],
        replacement_session: dict[str, Any],
        access_token_hash: str,
        refresh_token_hash: str,
        refresh_expires_at: datetime,
        next_recovery_verifier_hash: str,
        recovery_event: dict[str, Any],
        now: datetime,
    ) -> None:
        self._call(
            """
            SELECT qc2_governance_owner.identity_complete_recovery(
              %s::text, %s::uuid, %s::text, %s::jsonb, %s::jsonb,
              %s::text, %s::text, %s::timestamptz, %s::text, %s::jsonb,
              %s::timestamptz
            ) AS result
            """,
            (
                environment_namespace,
                challenge_id,
                recovery_verifier_hash,
                _json(replacement_device),
                _json(replacement_session),
                access_token_hash,
                refresh_token_hash,
                _format_instant(refresh_expires_at),
                next_recovery_verifier_hash,
                _json(recovery_event),
                _format_instant(now),
            ),
        )

    def store_additional_enrollment_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], pending: dict[str, Any]
    ) -> None:
        self._call(
            """
            SELECT qc2_governance_owner.identity_store_additional_enrollment_challenge(
              %s::text, %s::jsonb, %s::jsonb
            ) AS result
            """,
            (environment_namespace, _json(challenge), _json(pending)),
        )

    def get_additional_enrollment_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> dict[str, Any]:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_get_additional_enrollment_challenge(
              %s::text, %s::uuid
            ) AS result
            """,
            (environment_namespace, challenge_id),
        )
        self._require_status(result, "FOUND")
        return result

    def complete_additional_enrollment(
        self,
        *,
        environment_namespace: str,
        challenge_id: str,
        authorized_session_record_id: str,
        authorized_device_id: str,
        device_record: dict[str, Any],
        session_record: dict[str, Any],
        access_token_hash: str,
        refresh_token_hash: str,
        refresh_expires_at: datetime,
        now: datetime,
    ) -> None:
        self._call(
            """
            SELECT qc2_governance_owner.identity_complete_additional_enrollment(
              %s::text, %s::uuid, %s::uuid, %s::uuid, %s::jsonb, %s::jsonb,
              %s::text, %s::text, %s::timestamptz, %s::timestamptz
            ) AS result
            """,
            (
                environment_namespace,
                challenge_id,
                authorized_session_record_id,
                authorized_device_id,
                _json(device_record),
                _json(session_record),
                access_token_hash,
                refresh_token_hash,
                _format_instant(refresh_expires_at),
                _format_instant(now),
            ),
        )

    def resolve_session(
        self, environment_namespace: str, session_record_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], str | None, str | None]:
        result = self._call(
            """
            SELECT qc2_governance_owner.identity_resolve_session(
              %s::text, %s::uuid
            ) AS result
            """,
            (environment_namespace, session_record_id),
        )
        self._require_status(result, "FOUND")
        return (
            result["device_record"],
            result["session_record"],
            result.get("session_revoked_at"),
            result.get("device_revoked_at"),
        )

    def status(self, environment_namespace: str) -> IdentityStatus:
        result = self._call(
            "SELECT qc2_governance_owner.identity_status(%s::text) AS result",
            (environment_namespace,),
        )
        self._require_status(result, "FOUND")
        return IdentityStatus(
            environment_namespace=environment_namespace,
            owner_binding=result["owner_binding"],
            enrolled_devices=tuple(result["enrolled_devices"]),
            promotion_hold=bool(result["promotion_hold"]),
            entry_hold=bool(result["entry_hold"]),
            reconciliation_required=bool(result["reconciliation_required"]),
        )

    def _call(self, statement: str, parameters: tuple[Any, ...]) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, parameters)
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("identity database function returned no result")
                if isinstance(row, Mapping):
                    result = row["result"]
                else:
                    result = row[0]
                if isinstance(result, str):
                    result = json.loads(result)
                if not isinstance(result, dict):
                    raise TypeError("identity database result must be a JSON object")
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
    def _require_status(result: dict[str, Any], *allowed: str) -> None:
        status = result.get("status")
        if status in allowed:
            return
        error_codes = {
            "NOT_PROVISIONED": IdentityErrorCode.NOT_PROVISIONED,
            "INVALID_BOOTSTRAP": IdentityErrorCode.INVALID_BOOTSTRAP,
            "BOOTSTRAP_CONSUMED": IdentityErrorCode.BOOTSTRAP_CONSUMED,
            "UNKNOWN_CHALLENGE": IdentityErrorCode.UNKNOWN_CHALLENGE,
            "EXPIRED": IdentityErrorCode.EXPIRED,
            "REPLAY": IdentityErrorCode.REPLAY,
            "INVALID_IDENTITY": IdentityErrorCode.INVALID_IDENTITY,
            "IDENTITY_REVOKED": IdentityErrorCode.IDENTITY_REVOKED,
            "INVALID_REFRESH": IdentityErrorCode.INVALID_REFRESH,
            "REFRESH_REPLAY": IdentityErrorCode.REFRESH_REPLAY,
            "SCOPE_MISMATCH": IdentityErrorCode.SCOPE_MISMATCH,
            "IDEMPOTENCY_CONFLICT": IdentityErrorCode.IDEMPOTENCY_CONFLICT,
            "RECOVERY_DENIED": IdentityErrorCode.RECOVERY_DENIED,
            "INVALID_INPUT": IdentityErrorCode.INVALID_INPUT,
        }
        raise IdentityAuthorityError(
            error_codes.get(str(status), IdentityErrorCode.INVALID_IDENTITY),
            str(result.get("reason") or status or "identity database rejected the request"),
        )


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
