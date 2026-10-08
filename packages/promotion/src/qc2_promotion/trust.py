"""Explicit public-key role and revocation registry for promotion verification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from collections.abc import Iterable

from .errors import PromotionVerificationError, VerificationErrorCode

_KEY_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class KeyRole(StrEnum):
    ARTIFACT_PACKAGER = "artifact_packager"
    INDEPENDENT_EVALUATOR = "independent_evaluator"
    OWNER_IDENTITY = "owner_identity"


@dataclass(frozen=True, slots=True)
class VerificationKey:
    key_id: str
    role: KeyRole
    public_key: bytes
    valid_from: str
    identity: str | None = None
    revoked_at: str | None = None


class KeyRoleRegistry:
    """Immutable trust snapshot supplied by the verifier's authority."""

    def __init__(self, records: Iterable[VerificationKey]) -> None:
        indexed: dict[str, VerificationKey] = {}
        identities: set[tuple[KeyRole, str]] = set()
        for record in records:
            if not isinstance(record, VerificationKey):
                raise TypeError("key registry entries must be VerificationKey records")
            if _KEY_ID.fullmatch(record.key_id) is None:
                raise ValueError("key registry contains an invalid key ID")
            if not isinstance(record.role, KeyRole):
                raise ValueError("key registry contains an unknown key role")
            if not isinstance(record.public_key, bytes) or len(record.public_key) != 32:
                raise ValueError("Ed25519 public keys must be exactly 32 raw bytes")
            _parse_utc(record.valid_from, "key valid_from")
            if record.revoked_at is not None:
                _parse_utc(record.revoked_at, "key revoked_at")
            if record.role is KeyRole.INDEPENDENT_EVALUATOR:
                if not isinstance(record.identity, str) or not record.identity.strip():
                    raise ValueError("independent evaluator keys require an identity")
                identity = (record.role, record.identity)
                if identity in identities:
                    raise ValueError("evaluator identity is registered more than once")
                identities.add(identity)
            if record.key_id in indexed:
                raise ValueError("key registry contains a duplicate key ID")
            indexed[record.key_id] = record
        self._records = MappingProxyType(indexed)

    @property
    def records(self) -> MappingProxyType[str, VerificationKey]:
        return self._records

    def resolve(
        self,
        key_id: str,
        *,
        required_role: KeyRole,
        now: str,
        identity: str | None = None,
    ) -> VerificationKey:
        record = self._records.get(key_id)
        if record is None:
            raise PromotionVerificationError(
                VerificationErrorCode.KEY_UNKNOWN, f"unregistered key {key_id!r}"
            )
        if record.role is not required_role:
            raise PromotionVerificationError(
                VerificationErrorCode.KEY_ROLE_MISMATCH,
                f"key {key_id!r} has role {record.role.value!r}, not {required_role.value!r}",
            )
        current = _parse_utc(now, "verification time")
        if _parse_utc(record.valid_from, "key valid_from") > current:
            raise PromotionVerificationError(
                VerificationErrorCode.KEY_NOT_ACTIVE, f"key {key_id!r} is not active yet"
            )
        if record.revoked_at is not None and _parse_utc(record.revoked_at, "key revoked_at") <= current:
            raise PromotionVerificationError(
                VerificationErrorCode.KEY_REVOKED, f"key {key_id!r} is revoked"
            )
        if identity is not None and record.identity != identity:
            raise PromotionVerificationError(
                VerificationErrorCode.EVALUATOR_IDENTITY_MISMATCH,
                f"key {key_id!r} is not registered to evaluator {identity!r}",
            )
        return record


def _parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an explicit UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an explicit UTC instant") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must use UTC")
    return parsed.astimezone(UTC)
