"""Single-owner enrollment, session, recovery, and signed-command authority.

The in-memory repository is a test fixture only. Production callers must inject a
durable repository whose operations preserve the atomic checks documented by
IdentityRepositoryPort.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import re
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from qc2_contracts.runtime import (
    CONTRACTS,
    canonical_content_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
    validate_contract,
)

from .approval import IdentityBinding

BOOTSTRAP_SIGNING_PREFIX = b"QC2_OWNER_ENROLLMENT_CHALLENGE_V1\x00"
ADDITIONAL_DEVICE_SIGNING_PREFIX = b"QC2_OWNER_DEVICE_ENROLLMENT_V1\x00"
RECOVERY_SIGNING_PREFIX = b"QC2_OWNER_RECOVERY_V1\x00"
COMMAND_SIGNING_PREFIX = b"QC2_OWNER_SIGNED_COMMAND_V1\x00"

_ENVIRONMENTS = frozenset({"development", "test", "research", "production"})
_SECURITY_LEVELS = frozenset({"SOFTWARE", "TEE", "STRONGBOX", "UNKNOWN"})
_COMMAND_SCOPES = frozenset(
    {"PROMOTION", "EPOCH_ACTIVATION", "PAUSE", "RESUME", "ALERT", "DEVICE_ADMIN"}
)
_COMMAND_SCOPE_BY_TYPE = {
    "PROMOTION": "PROMOTION",
    "EPOCH_ACTIVATION": "EPOCH_ACTIVATION",
    "PAUSE_NEW_ENTRIES": "PAUSE",
    "RESUME_REQUEST": "RESUME",
    "ACKNOWLEDGE_ALERT": "ALERT",
    "DEVICE_ACTION": "DEVICE_ADMIN",
}
_SLUG = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")


class IdentityErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    NOT_PROVISIONED = "not_provisioned"
    INVALID_BOOTSTRAP = "invalid_bootstrap"
    BOOTSTRAP_CONSUMED = "bootstrap_consumed"
    UNKNOWN_CHALLENGE = "unknown_challenge"
    EXPIRED = "expired"
    REPLAY = "replay"
    INVALID_KEY = "invalid_key"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_IDENTITY = "invalid_identity"
    IDENTITY_REVOKED = "identity_revoked"
    INVALID_REFRESH = "invalid_refresh"
    REFRESH_REPLAY = "refresh_replay"
    SCOPE_MISMATCH = "scope_mismatch"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    RECOVERY_DENIED = "recovery_denied"
    RECOVERY_HOLD = "recovery_hold"
    FIXTURE_ONLY = "fixture_only"
    INVALID_SECURITY_EVIDENCE = "invalid_security_evidence"


class IdentityAuthorityError(ValueError):
    """Stable machine-readable rejection from the owner identity boundary."""

    def __init__(self, code: IdentityErrorCode, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code.value)


@dataclass(frozen=True, slots=True)
class IdentityPolicy:
    """Required deployment policy; no production TTL or command scope is guessed."""

    enrollment_challenge_lifetime_seconds: int
    command_challenge_lifetime_seconds: int
    recovery_challenge_lifetime_seconds: int
    access_session_lifetime_seconds: int
    refresh_credential_lifetime_seconds: int
    initial_scope_refs: tuple[str, ...]
    recovery_scope_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        durations = (
            self.enrollment_challenge_lifetime_seconds,
            self.command_challenge_lifetime_seconds,
            self.recovery_challenge_lifetime_seconds,
            self.access_session_lifetime_seconds,
            self.refresh_credential_lifetime_seconds,
        )
        if any(type(value) is not int or value <= 0 for value in durations):
            raise ValueError("identity lifetimes must be positive configured integers")
        if not self.initial_scope_refs or any(
            scope not in _COMMAND_SCOPES and scope != "OWNER_READ"
            for scope in self.initial_scope_refs
        ) or len(self.initial_scope_refs) != len(set(self.initial_scope_refs)):
            raise ValueError("initial scopes must be explicit owner command scopes")
        if not self.recovery_scope_refs or any(
            scope not in {"OWNER_READ", "DEVICE_ADMIN"}
            for scope in self.recovery_scope_refs
        ) or len(self.recovery_scope_refs) != len(set(self.recovery_scope_refs)):
            raise ValueError("recovery sessions may only read or administer devices")


@dataclass(frozen=True, slots=True)
class EnrollmentChallenge:
    challenge: dict[str, Any]
    signing_bytes: bytes


@dataclass(frozen=True, slots=True)
class DeviceEnrollmentChallenge:
    challenge: dict[str, Any]
    signing_bytes: bytes


@dataclass(frozen=True, slots=True)
class RecoveryChallenge:
    challenge: dict[str, Any]
    signing_bytes: bytes


@dataclass(frozen=True, slots=True)
class SignedCommandChallenge:
    challenge: dict[str, Any]
    signing_bytes: bytes


@dataclass(frozen=True, slots=True)
class SessionTokens:
    session_record: dict[str, Any]
    access_token: str
    refresh_token: str
    recovery_material: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityStatus:
    environment_namespace: str
    owner_binding: str
    enrolled_devices: tuple[dict[str, Any], ...]
    promotion_hold: bool
    entry_hold: bool
    reconciliation_required: bool


class SecurityLevelVerifier(Protocol):
    def verify(
        self,
        *,
        public_key_fingerprint: str,
        claimed_level: str,
        evidence: bytes | None,
        environment_namespace: str,
    ) -> str: ...


class IdentityRepositoryPort(Protocol):
    """Atomic repository boundary for the identity authority.

    `complete_bootstrap`, `complete_recovery`, `rotate_refresh`, and
    `commit_owner_command` must lock and recheck current namespace, challenge,
    device, session, generation, and revocation state in the same transaction as
    their writes. A recovery commit must append evidence and persist its holds
    atomically. Implementations must store token verifiers, never raw tokens.
    """

    fixture_only: bool

    def bootstrap_state(self, environment_namespace: str) -> dict[str, Any]: ...

    def store_enrollment_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], pending: dict[str, Any]
    ) -> None: ...

    def get_enrollment_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> dict[str, Any]: ...

    def store_additional_enrollment_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], pending: dict[str, Any]
    ) -> None: ...

    def get_additional_enrollment_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> dict[str, Any]: ...

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
    ) -> None: ...

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
    ) -> None: ...

    def resolve_access(
        self, environment_namespace: str, access_token_hash: str, *, now: datetime
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def refresh_context(
        self, environment_namespace: str, refresh_token_hash: str, *, now: datetime
    ) -> dict[str, Any]: ...

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
    ) -> None: ...

    def store_command_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], binding: dict[str, Any]
    ) -> None: ...

    def get_command_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def commit_owner_command(
        self,
        *,
        environment_namespace: str,
        challenge_id: str,
        owner_command: dict[str, Any],
        idempotency_key: str,
        target_device_id: str | None,
        now: datetime,
    ) -> dict[str, Any]: ...

    def verify_recovery_material(
        self, environment_namespace: str, recovery_verifier_hash: str
    ) -> None: ...

    def issue_recovery_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], pending: dict[str, Any]
    ) -> None: ...

    def get_recovery_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> dict[str, Any]: ...

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
    ) -> None: ...

    def resolve_session(
        self, environment_namespace: str, session_record_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], str | None, str | None]: ...

    def status(self, environment_namespace: str) -> IdentityStatus: ...


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "UTC datetime required")
    return value.astimezone(UTC)


def _format_instant(value: datetime) -> str:
    value = _utc(value)
    precision = "microseconds" if value.microsecond else "seconds"
    return value.isoformat(timespec=precision).replace("+00:00", "Z")


def _parse_instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _utc(parsed)
    except (AttributeError, TypeError, ValueError) as exc:
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "invalid UTC instant") from exc


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not _BASE64URL.fullmatch(value):
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "invalid base64url")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, base64.binascii.Error) as exc:
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "invalid base64url") from exc
    if _b64url_encode(decoded) != value:
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "non-canonical base64url")
    return decoded


def _token_hash(token: str, domain: str) -> str:
    if not isinstance(token, str) or len(token.encode("utf-8")) < 32:
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "high-entropy token required")
    return domain_separated_sha256(domain, token.encode("utf-8"))


def new_offline_secret() -> str:
    """Generate one high-entropy token; the caller must deliver/store it securely."""
    return secrets.token_urlsafe(32)


def _fingerprint(public_key_der: bytes) -> str:
    return hashlib.sha256(public_key_der).hexdigest()


def _load_p256_public_key(public_key_der: bytes) -> EllipticCurvePublicKey:
    try:
        key = serialization.load_der_public_key(public_key_der)
    except (TypeError, ValueError) as exc:
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_KEY) from exc
    if not isinstance(key, EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_KEY)
    return key


def _verify_p256(public_key_der: bytes, signed_bytes: bytes, signature: bytes) -> None:
    key = _load_p256_public_key(public_key_der)
    try:
        key.verify(signature, signed_bytes, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_SIGNATURE) from exc


def _contract(name: str, value: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_contract(name, value)
    except (TypeError, ValueError) as exc:
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, f"invalid {name} contract") from exc
    if name in {"OwnerCommand"}:
        try:
            if value["content_hash"] != canonical_content_hash(name, value):
                raise ValueError("content hash mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            raise IdentityAuthorityError(
                IdentityErrorCode.INVALID_INPUT, f"invalid {name} content hash"
            ) from exc
    return copy.deepcopy(value)


def _record_ref(name: str, record: dict[str, Any]) -> dict[str, str]:
    return {
        "target_schema_name": CONTRACTS[name][1],
        "target_id": record["id"],
    }


def _device_ref(device: dict[str, Any]) -> dict[str, str]:
    return _record_ref("OwnerDevice", device)


def _session_ref(session: dict[str, Any]) -> dict[str, str]:
    return _record_ref("OwnerSession", session)


def _evidence_class(environment_namespace: str) -> str:
    return "SYNTHETIC_FIXTURE" if environment_namespace == "test" else "FORWARD_OPERATIONAL"


def _check_environment(environment_namespace: str) -> None:
    if environment_namespace not in _ENVIRONMENTS:
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "unknown environment namespace")


def _make_device_record(
    *,
    environment_namespace: str,
    owner_binding: str,
    key_id: str,
    public_key_der: bytes,
    security_level: str,
    app_version: str,
    proof_hash: str,
    now: datetime,
) -> dict[str, Any]:
    device = {
        "schema_name": CONTRACTS["OwnerDevice"][1],
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": _format_instant(now),
        "owning_authority": "identity",
        "evidence_class": _evidence_class(environment_namespace),
        "environment_namespace": environment_namespace,
        "source_refs": [],
        "owner_key_id": key_id,
        "public_key": _b64url_encode(public_key_der),
        "signing_algorithm": "ECDSA_P256_SHA256",
        "security_level": security_level,
        "enrollment_proof_hash": proof_hash,
        "owner_binding": owner_binding,
        "app_version": app_version,
        "revocation_state": "ENROLLED",
        "enrolled_at": _format_instant(now),
        "revoked_at": None,
    }
    return _contract("OwnerDevice", device)


def _make_session_record(
    *,
    environment_namespace: str,
    device: dict[str, Any],
    session_id: str,
    issued_at: datetime,
    expires_at: datetime,
    scope_refs: tuple[str, ...],
    refresh_generation: int,
) -> dict[str, Any]:
    session = {
        "schema_name": CONTRACTS["OwnerSession"][1],
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": _format_instant(issued_at),
        "owning_authority": "identity",
        "evidence_class": _evidence_class(environment_namespace),
        "environment_namespace": environment_namespace,
        "source_refs": [],
        "device_ref": _device_ref(device),
        "session_id": session_id,
        "issued_at": _format_instant(issued_at),
        "expires_at": _format_instant(expires_at),
        "revoked_at": None,
        "scope_refs": list(scope_refs),
        "refresh_generation": refresh_generation,
    }
    return _contract("OwnerSession", session)


@dataclass(slots=True)
class _OwnerState:
    environment_namespace: str
    owner_binding: str
    bootstrap_verifier_hash: str
    bootstrap_consumed: bool = False
    recovery_verifier_hash: str | None = None
    promotion_hold: bool = False
    entry_hold: bool = False
    reconciliation_required: bool = False
    devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    device_revocations: dict[str, datetime] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    current_session_by_family: dict[str, str] = field(default_factory=dict)
    access_index: dict[str, str] = field(default_factory=dict)
    refresh_index: dict[str, tuple[str, str, bool]] = field(default_factory=dict)
    enrollment_challenges: dict[str, dict[str, Any]] = field(default_factory=dict)
    additional_enrollment_challenges: dict[str, dict[str, Any]] = field(default_factory=dict)
    recovery_challenges: dict[str, dict[str, Any]] = field(default_factory=dict)
    command_challenges: dict[str, dict[str, Any]] = field(default_factory=dict)
    commands: dict[str, dict[str, Any]] = field(default_factory=dict)
    idempotency: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    recovery_events: list[dict[str, Any]] = field(default_factory=list)


class InMemoryIdentityRepository:
    """Thread-safe test fixture. It is intentionally unusable outside test."""

    fixture_only = True

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._owners: dict[str, _OwnerState] = {}

    def provision_fixture_bootstrap(
        self, *, environment_namespace: str, owner_binding: str, bootstrap_verifier_hash: str
    ) -> None:
        if environment_namespace != "test":
            raise IdentityAuthorityError(IdentityErrorCode.FIXTURE_ONLY)
        if not _SLUG.fullmatch(owner_binding) or not _SHA256.fullmatch(bootstrap_verifier_hash):
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT)
        with self._lock:
            if environment_namespace in self._owners:
                raise IdentityAuthorityError(IdentityErrorCode.NOT_PROVISIONED, "already provisioned")
            self._owners[environment_namespace] = _OwnerState(
                environment_namespace, owner_binding, bootstrap_verifier_hash
            )

    def bootstrap_state(self, environment_namespace: str) -> dict[str, Any]:
        with self._lock:
            state = self._owner(environment_namespace)
            return {
                "owner_binding": state.owner_binding,
                "bootstrap_verifier_hash": state.bootstrap_verifier_hash,
                "bootstrap_consumed": state.bootstrap_consumed,
            }

    def store_enrollment_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], pending: dict[str, Any]
    ) -> None:
        with self._lock:
            state = self._owner(environment_namespace)
            if state.bootstrap_consumed or state.devices:
                raise IdentityAuthorityError(IdentityErrorCode.BOOTSTRAP_CONSUMED)
            challenge_id = challenge["id"]
            if challenge_id in state.enrollment_challenges:
                raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
            for prior in state.enrollment_challenges.values():
                prior["consumed"] = True
            state.enrollment_challenges[challenge_id] = {
                "contract": copy.deepcopy(challenge),
                "pending": copy.deepcopy(pending),
                "consumed": False,
            }

    def get_enrollment_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> dict[str, Any]:
        with self._lock:
            state = self._owner(environment_namespace)
            try:
                return copy.deepcopy(state.enrollment_challenges[challenge_id])
            except KeyError as exc:
                raise IdentityAuthorityError(IdentityErrorCode.UNKNOWN_CHALLENGE) from exc

    def store_additional_enrollment_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], pending: dict[str, Any]
    ) -> None:
        with self._lock:
            state = self._owner(environment_namespace)
            owner_session = state.sessions.get(pending["authorized_session_record_id"])
            if owner_session is None:
                raise IdentityAuthorityError(IdentityErrorCode.IDENTITY_REVOKED)
            self._assert_live_binding(state, owner_session, _parse_instant(challenge["issued_at"]))
            owner_device_id = owner_session["record"]["device_ref"]["target_id"]
            if (
                owner_device_id != pending["authorized_device_id"]
                or "DEVICE_ADMIN" not in owner_session["record"]["scope_refs"]
                or pending["owner_binding"] != state.owner_binding
            ):
                raise IdentityAuthorityError(IdentityErrorCode.SCOPE_MISMATCH)
            challenge_id = challenge["id"]
            if challenge_id in state.additional_enrollment_challenges:
                raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
            state.additional_enrollment_challenges[challenge_id] = {
                "challenge": copy.deepcopy(challenge),
                "pending": copy.deepcopy(pending),
                "consumed": False,
            }

    def get_additional_enrollment_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> dict[str, Any]:
        with self._lock:
            state = self._owner(environment_namespace)
            try:
                return copy.deepcopy(state.additional_enrollment_challenges[challenge_id])
            except KeyError as exc:
                raise IdentityAuthorityError(IdentityErrorCode.UNKNOWN_CHALLENGE) from exc

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
        now = _utc(now)
        with self._lock:
            state = self._owner(environment_namespace)
            entry = state.additional_enrollment_challenges.get(challenge_id)
            if entry is None:
                raise IdentityAuthorityError(IdentityErrorCode.UNKNOWN_CHALLENGE)
            if entry["consumed"]:
                raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
            pending, challenge = entry["pending"], entry["challenge"]
            if _parse_instant(challenge["expires_at"]) <= now:
                raise IdentityAuthorityError(IdentityErrorCode.EXPIRED)
            if (
                pending["authorized_session_record_id"] != authorized_session_record_id
                or pending["authorized_device_id"] != authorized_device_id
                or pending["environment_namespace"] != environment_namespace
                or pending["owner_binding"] != state.owner_binding
                or pending["public_key_fingerprint"]
                != _fingerprint(_b64url_decode(device_record["public_key"]))
                or session_record["scope_refs"] != pending["scope_refs"]
            ):
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
            owner_session = state.sessions.get(authorized_session_record_id)
            if owner_session is None:
                raise IdentityAuthorityError(IdentityErrorCode.IDENTITY_REVOKED)
            self._assert_live_binding(state, owner_session, now)
            if (
                owner_session["record"]["device_ref"]["target_id"] != authorized_device_id
                or "DEVICE_ADMIN" not in owner_session["record"]["scope_refs"]
            ):
                raise IdentityAuthorityError(IdentityErrorCode.SCOPE_MISMATCH)
            self._assert_new_device(state, device_record)
            self._assert_new_session(state, session_record, device_record)
            entry["consumed"] = True
            self._insert_device(state, device_record)
            self._insert_session(
                state,
                session_record,
                access_token_hash=access_token_hash,
                refresh_token_hash=refresh_token_hash,
                refresh_expires_at=refresh_expires_at,
            )

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
        now = _utc(now)
        with self._lock:
            state = self._owner(environment_namespace)
            entry = state.enrollment_challenges.get(challenge_id)
            if entry is None:
                raise IdentityAuthorityError(IdentityErrorCode.UNKNOWN_CHALLENGE)
            if (
                state.bootstrap_consumed
                or state.devices
                or entry["consumed"]
                or not hmac.compare_digest(state.bootstrap_verifier_hash, bootstrap_verifier_hash)
            ):
                raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
            if _parse_instant(
                state.enrollment_challenges[challenge_id]["contract"]["expires_at"]
            ) <= now:
                raise IdentityAuthorityError(IdentityErrorCode.EXPIRED)
            pending = entry["pending"]
            if (
                pending["environment_namespace"] != environment_namespace
                or pending["owner_binding"] != state.owner_binding
                or pending["public_key_fingerprint"]
                != _fingerprint(_b64url_decode(device_record["public_key"]))
            ):
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
            self._assert_new_device(state, device_record)
            self._assert_new_session(state, session_record, device_record)
            if not _SHA256.fullmatch(recovery_verifier_hash):
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT)
            entry["consumed"] = True
            state.bootstrap_consumed = True
            state.recovery_verifier_hash = recovery_verifier_hash
            self._insert_device(state, device_record)
            self._insert_session(
                state,
                session_record,
                access_token_hash=access_token_hash,
                refresh_token_hash=refresh_token_hash,
                refresh_expires_at=refresh_expires_at,
            )

    def resolve_access(
        self, environment_namespace: str, access_token_hash: str, *, now: datetime
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._lock:
            state = self._owner(environment_namespace)
            session_id = state.access_index.get(access_token_hash)
            if session_id is None:
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
            session = state.sessions[session_id]
            self._assert_live_binding(state, session, _utc(now))
            device = state.devices[session["record"]["device_ref"]["target_id"]]
            return copy.deepcopy(device), copy.deepcopy(session["record"])

    def refresh_context(
        self, environment_namespace: str, refresh_token_hash: str, *, now: datetime
    ) -> dict[str, Any]:
        now = _utc(now)
        with self._lock:
            state = self._owner(environment_namespace)
            indexed = state.refresh_index.get(refresh_token_hash)
            if indexed is None:
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_REFRESH)
            family_id, record_id, was_used = indexed
            if was_used:
                self._revoke_family(state, family_id, now)
                raise IdentityAuthorityError(IdentityErrorCode.REFRESH_REPLAY)
            session = state.sessions.get(record_id)
            if session is None or state.current_session_by_family.get(family_id) != record_id:
                self._revoke_family(state, family_id, now)
                raise IdentityAuthorityError(IdentityErrorCode.REFRESH_REPLAY)
            device = state.devices.get(session["record"]["device_ref"]["target_id"])
            if (
                session.get("revoked_at") is not None
                or device is None
                or device["revocation_state"] != "ENROLLED"
                or device["environment_namespace"] != environment_namespace
                or session["refresh_expires_at"] <= now
            ):
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_REFRESH)
            return {
                "device_record": copy.deepcopy(device),
                "session_record": copy.deepcopy(session["record"]),
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
        now = _utc(now)
        with self._lock:
            state = self._owner(environment_namespace)
            indexed = state.refresh_index.get(refresh_token_hash)
            if indexed is None:
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_REFRESH)
            family_id, old_record_id, was_used = indexed
            if was_used:
                self._revoke_family(state, family_id, now)
                raise IdentityAuthorityError(IdentityErrorCode.REFRESH_REPLAY)
            old_session = state.sessions.get(old_record_id)
            if old_session is None:
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_REFRESH)
            if old_session.get("revoked_at") is not None:
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_REFRESH)
            if state.current_session_by_family.get(family_id) != old_record_id:
                self._revoke_family(state, family_id, now)
                raise IdentityAuthorityError(IdentityErrorCode.REFRESH_REPLAY)
            device = state.devices[old_session["record"]["device_ref"]["target_id"]]
            if (
                device["revocation_state"] != "ENROLLED"
                or device["environment_namespace"] != environment_namespace
                or old_session["refresh_expires_at"] <= now
            ):
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_REFRESH)
            self._assert_new_session(state, session_record, device)
            if session_record["session_id"] != family_id:
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
            old_session["revoked_at"] = now
            state.refresh_index[refresh_token_hash] = (family_id, old_record_id, True)
            state.access_index.pop(old_session["access_token_hash"], None)
            state.current_session_by_family.pop(family_id, None)
            self._insert_session(
                state,
                session_record,
                access_token_hash=access_token_hash,
                refresh_token_hash=new_refresh_token_hash,
                refresh_expires_at=refresh_expires_at,
            )

    def store_command_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], binding: dict[str, Any]
    ) -> None:
        with self._lock:
            state = self._owner(environment_namespace)
            session = state.sessions.get(binding["session_record_id"])
            if session is None:
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
            self._assert_live_binding(state, session, _parse_instant(challenge["issued_at"]))
            if challenge["id"] in state.command_challenges:
                raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
            state.command_challenges[challenge["id"]] = {
                "challenge": copy.deepcopy(challenge),
                "binding": copy.deepcopy(binding),
                "consumed": False,
            }

    def get_command_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._lock:
            state = self._owner(environment_namespace)
            try:
                entry = state.command_challenges[challenge_id]
            except KeyError as exc:
                raise IdentityAuthorityError(IdentityErrorCode.UNKNOWN_CHALLENGE) from exc
            return copy.deepcopy(entry["challenge"]), copy.deepcopy(entry["binding"])

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
        now = _utc(now)
        with self._lock:
            state = self._owner(environment_namespace)
            entry = state.command_challenges.get(challenge_id)
            if entry is None:
                raise IdentityAuthorityError(IdentityErrorCode.UNKNOWN_CHALLENGE)
            if entry["consumed"]:
                raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
            binding = entry["binding"]
            session = state.sessions.get(binding["session_record_id"])
            if session is None:
                raise IdentityAuthorityError(IdentityErrorCode.IDENTITY_REVOKED)
            challenge = entry["challenge"]
            if _parse_instant(challenge["expires_at"]) <= now:
                raise IdentityAuthorityError(IdentityErrorCode.EXPIRED)
            self._assert_live_binding(state, session, now)
            device_id = owner_command["device_ref"]["target_id"]
            if (
                session["record"]["device_ref"]["target_id"] != device_id
                or binding["device_id"] != device_id
                or owner_command["environment_namespace"] != environment_namespace
                or owner_command["issued_at"] != challenge["issued_at"]
                or owner_command["command_id"] != challenge["command_id"]
                or owner_command["command_type"] != challenge["command_type"]
                or owner_command["idempotency_key"] != idempotency_key
                or owner_command["request_body_hash"] != challenge["request_body_hash"]
                or owner_command["scope"] != challenge["scope"]
            ):
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
            existing = state.idempotency.get(idempotency_key)
            if existing is not None:
                existing_hash, record = existing
                if (
                    existing_hash != owner_command["request_body_hash"]
                    or record["device_ref"]["target_id"] != device_id
                    or record["command_type"] != owner_command["command_type"]
                    or record["scope"] != owner_command["scope"]
                ):
                    raise IdentityAuthorityError(IdentityErrorCode.IDEMPOTENCY_CONFLICT)
                entry["consumed"] = True
                return copy.deepcopy(record)
            if target_device_id is not None:
                target = state.devices.get(target_device_id)
                if target is None or target["environment_namespace"] != environment_namespace:
                    raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
                self._revoke_device_locked(state, target_device_id, now)
            entry["consumed"] = True
            command_id = owner_command["id"]
            state.commands[command_id] = copy.deepcopy(owner_command)
            state.idempotency[idempotency_key] = (
                owner_command["request_body_hash"],
                copy.deepcopy(owner_command),
            )
            return copy.deepcopy(owner_command)

    def issue_recovery_challenge(
        self, environment_namespace: str, challenge: dict[str, Any], pending: dict[str, Any]
    ) -> None:
        with self._lock:
            state = self._owner(environment_namespace)
            if state.recovery_verifier_hash is None:
                raise IdentityAuthorityError(IdentityErrorCode.RECOVERY_DENIED)
            if challenge["id"] in state.recovery_challenges:
                raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
            state.recovery_challenges[challenge["id"]] = {
                "challenge": copy.deepcopy(challenge),
                "pending": copy.deepcopy(pending),
                "consumed": False,
            }

    def verify_recovery_material(
        self, environment_namespace: str, recovery_verifier_hash: str
    ) -> None:
        with self._lock:
            state = self._owner(environment_namespace)
            if (
                state.recovery_verifier_hash is None
                or not hmac.compare_digest(state.recovery_verifier_hash, recovery_verifier_hash)
            ):
                raise IdentityAuthorityError(IdentityErrorCode.RECOVERY_DENIED)

    def get_recovery_challenge(
        self, environment_namespace: str, challenge_id: str
    ) -> dict[str, Any]:
        with self._lock:
            state = self._owner(environment_namespace)
            try:
                return copy.deepcopy(state.recovery_challenges[challenge_id])
            except KeyError as exc:
                raise IdentityAuthorityError(IdentityErrorCode.UNKNOWN_CHALLENGE) from exc

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
        now = _utc(now)
        with self._lock:
            state = copy.deepcopy(self._owner(environment_namespace))
            challenge_entry = state.recovery_challenges.get(challenge_id)
            if challenge_entry is None:
                raise IdentityAuthorityError(IdentityErrorCode.UNKNOWN_CHALLENGE)
            if (
                challenge_entry["consumed"]
                or state.recovery_verifier_hash is None
                or not hmac.compare_digest(state.recovery_verifier_hash, recovery_verifier_hash)
                or not hmac.compare_digest(
                    challenge_entry["pending"]["recovery_verifier_hash"],
                    recovery_verifier_hash,
                )
            ):
                raise IdentityAuthorityError(IdentityErrorCode.RECOVERY_DENIED)
            pending = challenge_entry["pending"]
            if (
                pending["environment_namespace"] != environment_namespace
                or pending["owner_binding"] != state.owner_binding
                or pending["public_key_fingerprint"]
                != _fingerprint(_b64url_decode(replacement_device["public_key"]))
            ):
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
            self._assert_new_device(state, replacement_device)
            self._assert_new_session(state, replacement_session, replacement_device)
            prior_devices = [
                copy.deepcopy(device)
                for device in state.devices.values()
                if device["owner_binding"] == state.owner_binding
                and device["environment_namespace"] == environment_namespace
            ]
            event = copy.deepcopy(recovery_event)
            event["prior_device_refs"] = [_device_ref(device) for device in prior_devices]
            event["replacement_device_ref"] = _device_ref(replacement_device)
            validate_contract("RecoveryEvent", event)

            for device in prior_devices:
                self._revoke_device_locked(state, device["id"], now)
            self._revoke_all_sessions(state, now)
            challenge_entry["consumed"] = True
            state.recovery_verifier_hash = next_recovery_verifier_hash
            state.promotion_hold = True
            state.entry_hold = True
            state.reconciliation_required = True
            self._insert_device(state, replacement_device)
            self._insert_session(
                state,
                replacement_session,
                access_token_hash=access_token_hash,
                refresh_token_hash=refresh_token_hash,
                refresh_expires_at=refresh_expires_at,
            )
            state.recovery_events.append(event)
            self._owners[environment_namespace] = state

    def resolve_session(
        self, environment_namespace: str, session_record_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], str | None, str | None]:
        with self._lock:
            state = self._owner(environment_namespace)
            session = state.sessions.get(session_record_id)
            if session is None:
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
            device = state.devices[session["record"]["device_ref"]["target_id"]]
            return (
                copy.deepcopy(device),
                copy.deepcopy(session["record"]),
                _format_instant(session["revoked_at"]) if session.get("revoked_at") else None,
                _format_instant(state.device_revocations[device["id"]])
                if device["id"] in state.device_revocations
                else None,
            )

    def status(self, environment_namespace: str) -> IdentityStatus:
        with self._lock:
            state = self._owner(environment_namespace)
            return IdentityStatus(
                environment_namespace=environment_namespace,
                owner_binding=state.owner_binding,
                enrolled_devices=tuple(copy.deepcopy(tuple(state.devices.values()))),
                promotion_hold=state.promotion_hold,
                entry_hold=state.entry_hold,
                reconciliation_required=state.reconciliation_required,
            )

    def _owner(self, environment_namespace: str) -> _OwnerState:
        _check_environment(environment_namespace)
        try:
            return self._owners[environment_namespace]
        except KeyError as exc:
            raise IdentityAuthorityError(IdentityErrorCode.NOT_PROVISIONED) from exc

    @staticmethod
    def _assert_new_device(state: _OwnerState, device: dict[str, Any]) -> None:
        if (
            device["environment_namespace"] != state.environment_namespace
            or device["owner_binding"] != state.owner_binding
            or device["revocation_state"] != "ENROLLED"
        ):
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
        fingerprint = _fingerprint(_b64url_decode(device["public_key"]))
        if any(
            _fingerprint(_b64url_decode(existing["public_key"])) == fingerprint
            and existing["revocation_state"] == "ENROLLED"
            for existing in state.devices.values()
        ):
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY, "key already enrolled")

    @staticmethod
    def _assert_new_session(
        state: _OwnerState, session: dict[str, Any], device: dict[str, Any]
    ) -> None:
        if (
            session["environment_namespace"] != state.environment_namespace
            or session["device_ref"]["target_id"] != device["id"]
            or session["revoked_at"] is not None
        ):
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)

    @staticmethod
    def _insert_device(state: _OwnerState, device: dict[str, Any]) -> None:
        if device["id"] in state.devices:
            raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
        state.devices[device["id"]] = copy.deepcopy(device)

    @staticmethod
    def _insert_session(
        state: _OwnerState,
        session: dict[str, Any],
        *,
        access_token_hash: str,
        refresh_token_hash: str,
        refresh_expires_at: datetime,
    ) -> None:
        if session["id"] in state.sessions or session["session_id"] in state.current_session_by_family:
            raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
        if access_token_hash in state.access_index or refresh_token_hash in state.refresh_index:
            raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
        record = copy.deepcopy(session)
        state.sessions[session["id"]] = {
            "record": record,
            "access_token_hash": access_token_hash,
            "refresh_token_hash": refresh_token_hash,
            "refresh_expires_at": refresh_expires_at,
            "revoked_at": None,
        }
        state.current_session_by_family[session["session_id"]] = session["id"]
        state.access_index[access_token_hash] = session["id"]
        state.refresh_index[refresh_token_hash] = (
            session["session_id"],
            session["id"],
            False,
        )

    @classmethod
    def _assert_live_binding(
        cls, state: _OwnerState, session: dict[str, Any], now: datetime
    ) -> None:
        record = session["record"]
        device = state.devices.get(record["device_ref"]["target_id"])
        if (
            session.get("revoked_at") is not None
            or device is None
            or device["revocation_state"] != "ENROLLED"
            or device["environment_namespace"] != state.environment_namespace
            or record["environment_namespace"] != state.environment_namespace
            or not _parse_instant(record["issued_at"]) <= now < _parse_instant(record["expires_at"])
        ):
            raise IdentityAuthorityError(IdentityErrorCode.IDENTITY_REVOKED)

    @staticmethod
    def _revoke_family(state: _OwnerState, family_id: str, at: datetime) -> None:
        for session in state.sessions.values():
            if session["record"]["session_id"] == family_id and session.get("revoked_at") is None:
                session["revoked_at"] = at
                state.access_index.pop(session["access_token_hash"], None)
                state.refresh_index[session["refresh_token_hash"]] = (
                    family_id,
                    session["record"]["id"],
                    True,
                )

    @classmethod
    def _revoke_all_sessions(cls, state: _OwnerState, at: datetime) -> None:
        for family_id in tuple(state.current_session_by_family):
            cls._revoke_family(state, family_id, at)
        state.current_session_by_family.clear()

    @classmethod
    def _revoke_device_locked(cls, state: _OwnerState, device_id: str, at: datetime) -> None:
        device = state.devices.get(device_id)
        if device is None:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
        if device["environment_namespace"] != state.environment_namespace:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
        if device_id in state.device_revocations:
            return
        state.device_revocations[device_id] = at
        device["revocation_state"] = "REVOKED"
        for session in state.sessions.values():
            if session["record"]["device_ref"]["target_id"] == device_id:
                cls._revoke_family(state, session["record"]["session_id"], at)


class IdentityAuthority:
    """Verifies owner proofs and delegates durable one-time transitions to a repository."""

    def __init__(
        self,
        *,
        repository: IdentityRepositoryPort,
        environment_namespace: str,
        policy: IdentityPolicy,
        security_level_verifier: SecurityLevelVerifier | None = None,
    ) -> None:
        _check_environment(environment_namespace)
        if repository.fixture_only and environment_namespace != "test":
            raise IdentityAuthorityError(IdentityErrorCode.FIXTURE_ONLY)
        self.repository = repository
        self.environment_namespace = environment_namespace
        self.policy = policy
        self.security_level_verifier = security_level_verifier

    def issue_bootstrap_challenge(
        self,
        *,
        bootstrap_secret: str,
        owner_key_id: str,
        public_key_der: bytes,
        app_version: str,
        now: datetime,
        ttl_seconds: int | None = None,
        claimed_security_level: str = "UNKNOWN",
        security_evidence: bytes | None = None,
    ) -> EnrollmentChallenge:
        now = _utc(now)
        _check_key_id(owner_key_id)
        _check_app_version(app_version)
        public_key = _load_p256_public_key(public_key_der)
        del public_key
        secret_hash = _token_hash(bootstrap_secret, "qc2.owner.bootstrap.v1")
        state = self.repository.bootstrap_state(self.environment_namespace)
        if state["bootstrap_consumed"]:
            raise IdentityAuthorityError(IdentityErrorCode.BOOTSTRAP_CONSUMED)
        if not hmac.compare_digest(state["bootstrap_verifier_hash"], secret_hash):
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_BOOTSTRAP)
        fingerprint = _fingerprint(public_key_der)
        security_level = self._verified_security_level(
            fingerprint, claimed_security_level, security_evidence
        )
        lifetime = self._challenge_lifetime(
            ttl_seconds, self.policy.enrollment_challenge_lifetime_seconds
        )
        challenge_id = new_uuidv7()
        nonce = f"n{secrets.token_hex(32)}"
        expires_at = now + timedelta(seconds=lifetime)
        payload = {
            "schema_name": "qc2.owner_api.OwnerEnrollmentChallenge.v1",
            "schema_version": "1.0",
            "environment_namespace": self.environment_namespace,
            "challenge_id": challenge_id,
            "owner_binding": state["owner_binding"],
            "owner_key_id": owner_key_id,
            "public_key_fingerprint": fingerprint,
            "signing_algorithm": "ECDSA_P256_SHA256",
            "security_level": security_level,
            "app_version": app_version,
            "nonce": nonce,
            "issued_at": _format_instant(now),
            "expires_at": _format_instant(expires_at),
        }
        signing_bytes = BOOTSTRAP_SIGNING_PREFIX + canonical_json_bytes(payload)
        contract = {
            "schema_name": CONTRACTS["EnrollmentChallenge"][1],
            "schema_version": "1.0",
            "id": challenge_id,
            "created_at": _format_instant(now),
            "owning_authority": "identity",
            "evidence_class": _evidence_class(self.environment_namespace),
            "environment_namespace": self.environment_namespace,
            "source_refs": [],
            "owner_binding": state["owner_binding"],
            "bootstrap_verifier_hash": secret_hash,
            "nonce": nonce,
            "issued_at": _format_instant(now),
            "expires_at": _format_instant(expires_at),
            "single_use": True,
            "consumed_at": None,
        }
        _contract("EnrollmentChallenge", contract)
        self.repository.store_enrollment_challenge(
            self.environment_namespace,
            contract,
            {
                **payload,
                "bootstrap_verifier_hash": secret_hash,
                "public_key_der": _b64url_encode(public_key_der),
            },
        )
        return EnrollmentChallenge(payload, signing_bytes)

    def complete_bootstrap_enrollment(
        self,
        *,
        challenge_id: str,
        bootstrap_secret: str,
        signature: bytes,
        now: datetime,
    ) -> SessionTokens:
        now = _utc(now)
        secret_hash = _token_hash(bootstrap_secret, "qc2.owner.bootstrap.v1")
        entry = self.repository.get_enrollment_challenge(self.environment_namespace, challenge_id)
        contract = entry["contract"]
        pending = entry["pending"]
        if entry["consumed"]:
            raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
        if _parse_instant(contract["expires_at"]) <= now:
            raise IdentityAuthorityError(IdentityErrorCode.EXPIRED)
        if not hmac.compare_digest(contract["bootstrap_verifier_hash"], secret_hash):
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_BOOTSTRAP)
        public_key_der = _b64url_decode(pending["public_key_der"])
        signed_bytes = BOOTSTRAP_SIGNING_PREFIX + canonical_json_bytes(
            {key: value for key, value in pending.items() if key not in {"bootstrap_verifier_hash", "public_key_der"}}
        )
        _verify_p256(public_key_der, signed_bytes, signature)
        proof_hash = domain_separated_sha256(
            "qc2.owner.enrollment-proof.v1", signed_bytes + signature
        )
        device = _make_device_record(
            environment_namespace=self.environment_namespace,
            owner_binding=contract["owner_binding"],
            key_id=pending["owner_key_id"],
            public_key_der=public_key_der,
            security_level=pending["security_level"],
            app_version=pending["app_version"],
            proof_hash=proof_hash,
            now=now,
        )
        session_id = f"session-{new_uuidv7().replace('-', '')}"
        tokens = self._new_tokens()
        session = _make_session_record(
            environment_namespace=self.environment_namespace,
            device=device,
            session_id=session_id,
            issued_at=now,
            expires_at=now + timedelta(seconds=self.policy.access_session_lifetime_seconds),
            scope_refs=self.policy.initial_scope_refs,
            refresh_generation=1,
        )
        recovery_material = new_offline_secret()
        self.repository.complete_bootstrap(
            environment_namespace=self.environment_namespace,
            challenge_id=challenge_id,
            bootstrap_verifier_hash=secret_hash,
            device_record=device,
            session_record=session,
            access_token_hash=_token_hash(tokens[0], "qc2.owner.access.v1"),
            refresh_token_hash=_token_hash(tokens[1], "qc2.owner.refresh.v1"),
            refresh_expires_at=now
            + timedelta(seconds=self.policy.refresh_credential_lifetime_seconds),
            recovery_verifier_hash=_token_hash(recovery_material, "qc2.owner.recovery.v1"),
            now=now,
        )
        return SessionTokens(session, tokens[0], tokens[1], recovery_material)

    def issue_additional_device_challenge(
        self,
        *,
        access_token: str,
        owner_key_id: str,
        candidate_public_key_der: bytes,
        app_version: str,
        scope_refs: tuple[str, ...],
        now: datetime,
        ttl_seconds: int | None = None,
        claimed_security_level: str = "UNKNOWN",
        security_evidence: bytes | None = None,
    ) -> DeviceEnrollmentChallenge:
        now = _utc(now)
        _check_key_id(owner_key_id)
        _check_app_version(app_version)
        _load_p256_public_key(candidate_public_key_der)
        if (
            not scope_refs
            or len(scope_refs) != len(set(scope_refs))
        ):
            raise IdentityAuthorityError(IdentityErrorCode.SCOPE_MISMATCH)
        device, session = self.repository.resolve_access(
            self.environment_namespace,
            _token_hash(access_token, "qc2.owner.access.v1"),
            now=now,
        )
        self._assert_current_identity(device, session, now)
        if any(scope not in session["scope_refs"] for scope in scope_refs):
            raise IdentityAuthorityError(IdentityErrorCode.SCOPE_MISMATCH)
        if "DEVICE_ADMIN" not in session["scope_refs"]:
            raise IdentityAuthorityError(IdentityErrorCode.SCOPE_MISMATCH)
        fingerprint = _fingerprint(candidate_public_key_der)
        security_level = self._verified_security_level(
            fingerprint, claimed_security_level, security_evidence
        )
        lifetime = self._challenge_lifetime(
            ttl_seconds, self.policy.enrollment_challenge_lifetime_seconds
        )
        challenge = {
            "schema_name": "qc2.owner_api.OwnerDeviceEnrollmentChallenge.v1",
            "schema_version": "1.0",
            "environment_namespace": self.environment_namespace,
            "id": new_uuidv7(),
            "owner_binding": device["owner_binding"],
            "authorized_by_device_ref": _device_ref(device),
            "authorized_by_session_ref": _session_ref(session),
            "owner_key_id": owner_key_id,
            "public_key_fingerprint": fingerprint,
            "signing_algorithm": "ECDSA_P256_SHA256",
            "security_level": security_level,
            "app_version": app_version,
            "scope_refs": list(scope_refs),
            "nonce": f"n{secrets.token_hex(32)}",
            "issued_at": _format_instant(now),
            "expires_at": _format_instant(
                now + timedelta(seconds=lifetime)
            ),
        }
        signing_bytes = ADDITIONAL_DEVICE_SIGNING_PREFIX + canonical_json_bytes(challenge)
        self.repository.store_additional_enrollment_challenge(
            self.environment_namespace,
            challenge,
            {
                **challenge,
                "authorized_session_record_id": session["id"],
                "authorized_device_id": device["id"],
                "public_key_der": _b64url_encode(candidate_public_key_der),
            },
        )
        return DeviceEnrollmentChallenge(challenge, signing_bytes)

    def complete_additional_device_enrollment(
        self,
        *,
        access_token: str,
        challenge_id: str,
        owner_signature: bytes,
        candidate_signature: bytes,
        now: datetime,
    ) -> SessionTokens:
        now = _utc(now)
        entry = self.repository.get_additional_enrollment_challenge(
            self.environment_namespace, challenge_id
        )
        if entry["consumed"]:
            raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
        challenge, pending = entry["challenge"], entry["pending"]
        if _parse_instant(challenge["expires_at"]) <= now:
            raise IdentityAuthorityError(IdentityErrorCode.EXPIRED)
        owner_device, owner_session = self.repository.resolve_access(
            self.environment_namespace,
            _token_hash(access_token, "qc2.owner.access.v1"),
            now=now,
        )
        if (
            owner_device["id"] != pending["authorized_device_id"]
            or owner_session["id"] != pending["authorized_session_record_id"]
            or owner_device["owner_binding"] != challenge["owner_binding"]
        ):
            raise IdentityAuthorityError(IdentityErrorCode.SCOPE_MISMATCH)
        self._assert_current_identity(owner_device, owner_session, now)
        signing_bytes = ADDITIONAL_DEVICE_SIGNING_PREFIX + canonical_json_bytes(challenge)
        _verify_p256(
            _b64url_decode(owner_device["public_key"]), signing_bytes, owner_signature
        )
        public_key_der = _b64url_decode(pending["public_key_der"])
        if _fingerprint(public_key_der) != challenge["public_key_fingerprint"]:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_KEY)
        _verify_p256(public_key_der, signing_bytes, candidate_signature)
        proof_hash = domain_separated_sha256(
            "qc2.owner.additional-enrollment-proof.v1",
            signing_bytes + owner_signature + candidate_signature,
        )
        device = _make_device_record(
            environment_namespace=self.environment_namespace,
            owner_binding=challenge["owner_binding"],
            key_id=challenge["owner_key_id"],
            public_key_der=public_key_der,
            security_level=challenge["security_level"],
            app_version=challenge["app_version"],
            proof_hash=proof_hash,
            now=now,
        )
        tokens = self._new_tokens()
        session = _make_session_record(
            environment_namespace=self.environment_namespace,
            device=device,
            session_id=f"session-{new_uuidv7().replace('-', '')}",
            issued_at=now,
            expires_at=now + timedelta(seconds=self.policy.access_session_lifetime_seconds),
            scope_refs=tuple(challenge["scope_refs"]),
            refresh_generation=1,
        )
        self.repository.complete_additional_enrollment(
            environment_namespace=self.environment_namespace,
            challenge_id=challenge_id,
            authorized_session_record_id=owner_session["id"],
            authorized_device_id=owner_device["id"],
            device_record=device,
            session_record=session,
            access_token_hash=_token_hash(tokens[0], "qc2.owner.access.v1"),
            refresh_token_hash=_token_hash(tokens[1], "qc2.owner.refresh.v1"),
            refresh_expires_at=now
            + timedelta(seconds=self.policy.refresh_credential_lifetime_seconds),
            now=now,
        )
        return SessionTokens(session, tokens[0], tokens[1])

    def refresh_session(self, *, refresh_token: str, now: datetime) -> SessionTokens:
        now = _utc(now)
        old_hash = _token_hash(refresh_token, "qc2.owner.refresh.v1")
        # The repository consumes the old verifier and inserts the next generation
        # atomically. The returned contract uses the same session family identifier.
        current = self.repository.refresh_context(
            self.environment_namespace, old_hash, now=now
        )
        device = current["device_record"]
        old_session = current["session_record"]
        if (
            device["revocation_state"] != "ENROLLED"
            or device["environment_namespace"] != self.environment_namespace
            or old_session["revoked_at"] is not None
            or old_session["device_ref"]["target_id"] != device["id"]
        ):
            raise IdentityAuthorityError(IdentityErrorCode.IDENTITY_REVOKED)
        tokens = self._new_tokens()
        next_session = _make_session_record(
            environment_namespace=self.environment_namespace,
            device=device,
            session_id=old_session["session_id"],
            issued_at=now,
            expires_at=now + timedelta(seconds=self.policy.access_session_lifetime_seconds),
            scope_refs=tuple(old_session["scope_refs"]),
            refresh_generation=old_session["refresh_generation"] + 1,
        )
        self.repository.rotate_refresh(
            environment_namespace=self.environment_namespace,
            refresh_token_hash=old_hash,
            session_record=next_session,
            access_token_hash=_token_hash(tokens[0], "qc2.owner.access.v1"),
            new_refresh_token_hash=_token_hash(tokens[1], "qc2.owner.refresh.v1"),
            refresh_expires_at=now
            + timedelta(seconds=self.policy.refresh_credential_lifetime_seconds),
            now=now,
        )
        return SessionTokens(next_session, tokens[0], tokens[1])

    def issue_signed_command_challenge(
        self,
        *,
        access_token: str,
        command_type: str,
        request_body: dict[str, Any],
        idempotency_key: str,
        now: datetime,
        ttl_seconds: int | None = None,
    ) -> SignedCommandChallenge:
        now = _utc(now)
        required_scope = _COMMAND_SCOPE_BY_TYPE.get(command_type)
        if required_scope is None:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "unsupported command type")
        if not _SLUG.fullmatch(idempotency_key):
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "invalid idempotency key")
        if not isinstance(request_body, dict):
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "command body must be an object")
        self._validate_command_body(command_type, request_body)
        device, session = self.repository.resolve_access(
            self.environment_namespace,
            _token_hash(access_token, "qc2.owner.access.v1"),
            now=now,
        )
        self._assert_current_identity(device, session, now)
        if required_scope not in session["scope_refs"]:
            raise IdentityAuthorityError(IdentityErrorCode.SCOPE_MISMATCH)
        lifetime = self._challenge_lifetime(
            ttl_seconds, self.policy.command_challenge_lifetime_seconds
        )
        issued = _format_instant(now)
        challenge = {
            "schema_name": "qc2.owner_api.OwnerSignedCommandChallenge.v1",
            "schema_version": "1.0",
            "environment_namespace": self.environment_namespace,
            "id": new_uuidv7(),
            "command_id": f"cmd-{new_uuidv7().replace('-', '')}",
            "command_type": command_type,
            "idempotency_key": idempotency_key,
            "request_body_hash": domain_separated_sha256(
                "qc2.owner.command-body.v1", canonical_json_bytes(request_body)
            ),
            "device_ref": _device_ref(device),
            "session_ref": _session_ref(session),
            "owner_key_id": device["owner_key_id"],
            "public_key_fingerprint": _fingerprint(_b64url_decode(device["public_key"])),
            "scope": required_scope,
            "nonce": f"n{secrets.token_hex(32)}",
            "issued_at": issued,
            "expires_at": _format_instant(now + timedelta(seconds=lifetime)),
        }
        signing_bytes = COMMAND_SIGNING_PREFIX + canonical_json_bytes(challenge)
        self.repository.store_command_challenge(
            self.environment_namespace,
            challenge,
            {
                "device_id": device["id"],
                "session_record_id": session["id"],
                "session_id": session["session_id"],
                "request_body_hash": challenge["request_body_hash"],
            },
        )
        return SignedCommandChallenge(challenge, signing_bytes)

    def submit_signed_command(
        self,
        *,
        access_token: str,
        challenge_id: str,
        request_body: dict[str, Any],
        signature: bytes,
        now: datetime,
    ) -> dict[str, Any]:
        now = _utc(now)
        challenge, binding = self.repository.get_command_challenge(
            self.environment_namespace, challenge_id
        )
        if _parse_instant(challenge["expires_at"]) <= now:
            raise IdentityAuthorityError(IdentityErrorCode.EXPIRED)
        if domain_separated_sha256(
            "qc2.owner.command-body.v1", canonical_json_bytes(request_body)
        ) != challenge["request_body_hash"]:
            raise IdentityAuthorityError(IdentityErrorCode.SCOPE_MISMATCH)
        device, session = self.repository.resolve_access(
            self.environment_namespace,
            _token_hash(access_token, "qc2.owner.access.v1"),
            now=now,
        )
        if (
            device["id"] != binding["device_id"]
            or session["id"] != binding["session_record_id"]
            or challenge["device_ref"]["target_id"] != device["id"]
            or challenge["session_ref"]["target_id"] != session["id"]
        ):
            raise IdentityAuthorityError(IdentityErrorCode.SCOPE_MISMATCH)
        self._assert_current_identity(device, session, now)
        public_key_der = _b64url_decode(device["public_key"])
        signed_bytes = COMMAND_SIGNING_PREFIX + canonical_json_bytes(challenge)
        _verify_p256(public_key_der, signed_bytes, signature)
        command = {
            "schema_name": CONTRACTS["OwnerCommand"][1],
            "schema_version": "1.0",
            "id": new_uuidv7(),
            "created_at": _format_instant(now),
            "owning_authority": "owner_api",
            "evidence_class": _evidence_class(self.environment_namespace),
            "environment_namespace": self.environment_namespace,
            "source_refs": [],
            "command_id": challenge["command_id"],
            "command_type": challenge["command_type"],
            "idempotency_key": challenge["idempotency_key"],
            "request_body_hash": challenge["request_body_hash"],
            "issued_at": challenge["issued_at"],
            "device_ref": _device_ref(device),
            "signature": _b64url_encode(signature),
            "scope": challenge["scope"],
            "content_hash": "0" * 64,
        }
        command["content_hash"] = canonical_content_hash("OwnerCommand", command)
        command = _contract("OwnerCommand", command)
        target_device = None
        if command["command_type"] == "DEVICE_ACTION":
            payload = request_body["payload"]
            if payload["action"] == "REVOKE_DEVICE":
                target_device = payload["device_id"]
        return self.repository.commit_owner_command(
            environment_namespace=self.environment_namespace,
            challenge_id=challenge_id,
            owner_command=command,
            idempotency_key=challenge["idempotency_key"],
            target_device_id=target_device,
            now=now,
        )

    def issue_recovery_challenge(
        self,
        *,
        recovery_material: str,
        replacement_key_id: str,
        replacement_public_key_der: bytes,
        app_version: str,
        now: datetime,
        ttl_seconds: int | None = None,
        claimed_security_level: str = "UNKNOWN",
        security_evidence: bytes | None = None,
    ) -> RecoveryChallenge:
        now = _utc(now)
        _check_key_id(replacement_key_id)
        _check_app_version(app_version)
        _load_p256_public_key(replacement_public_key_der)
        verifier = _token_hash(recovery_material, "qc2.owner.recovery.v1")
        self.repository.verify_recovery_material(self.environment_namespace, verifier)
        fingerprint = _fingerprint(replacement_public_key_der)
        security_level = self._verified_security_level(
            fingerprint, claimed_security_level, security_evidence
        )
        lifetime = self._challenge_lifetime(
            ttl_seconds, self.policy.recovery_challenge_lifetime_seconds
        )
        challenge = {
            "schema_name": "qc2.owner_api.OwnerRecoveryChallenge.v1",
            "schema_version": "1.0",
            "environment_namespace": self.environment_namespace,
            "id": new_uuidv7(),
            "owner_binding": self.repository.bootstrap_state(self.environment_namespace)[
                "owner_binding"
            ],
            "owner_key_id": replacement_key_id,
            "public_key_fingerprint": fingerprint,
            "signing_algorithm": "ECDSA_P256_SHA256",
            "security_level": security_level,
            "app_version": app_version,
            "nonce": f"n{secrets.token_hex(32)}",
            "issued_at": _format_instant(now),
            "expires_at": _format_instant(now + timedelta(seconds=lifetime)),
        }
        signed_bytes = RECOVERY_SIGNING_PREFIX + canonical_json_bytes(challenge)
        self.repository.issue_recovery_challenge(
            self.environment_namespace,
            challenge,
            {
                **challenge,
                "recovery_verifier_hash": verifier,
                "public_key_der": _b64url_encode(replacement_public_key_der),
            },
        )
        return RecoveryChallenge(challenge, signed_bytes)

    def complete_recovery(
        self,
        *,
        challenge_id: str,
        recovery_material: str,
        signature: bytes,
        now: datetime,
    ) -> SessionTokens:
        now = _utc(now)
        verifier = _token_hash(recovery_material, "qc2.owner.recovery.v1")
        entry = self.repository.get_recovery_challenge(self.environment_namespace, challenge_id)
        if entry["consumed"]:
            raise IdentityAuthorityError(IdentityErrorCode.REPLAY)
        challenge, pending = entry["challenge"], entry["pending"]
        if _parse_instant(challenge["expires_at"]) <= now:
            raise IdentityAuthorityError(IdentityErrorCode.EXPIRED)
        if not hmac.compare_digest(pending["recovery_verifier_hash"], verifier):
            raise IdentityAuthorityError(IdentityErrorCode.RECOVERY_DENIED)
        public_key_der = _b64url_decode(pending["public_key_der"])
        signed_bytes = RECOVERY_SIGNING_PREFIX + canonical_json_bytes(challenge)
        _verify_p256(public_key_der, signed_bytes, signature)
        proof_hash = domain_separated_sha256(
            "qc2.owner.recovery-proof.v1", signed_bytes + signature
        )
        device = _make_device_record(
            environment_namespace=self.environment_namespace,
            owner_binding=challenge["owner_binding"],
            key_id=challenge["owner_key_id"],
            public_key_der=public_key_der,
            security_level=challenge["security_level"],
            app_version=challenge["app_version"],
            proof_hash=proof_hash,
            now=now,
        )
        tokens = self._new_tokens()
        session = _make_session_record(
            environment_namespace=self.environment_namespace,
            device=device,
            session_id=f"session-{new_uuidv7().replace('-', '')}",
            issued_at=now,
            expires_at=now + timedelta(seconds=self.policy.access_session_lifetime_seconds),
            scope_refs=self.policy.recovery_scope_refs,
            refresh_generation=1,
        )
        next_recovery_material = new_offline_secret()
        event = {
            "schema_name": CONTRACTS["RecoveryEvent"][1],
            "schema_version": "1.0",
            "id": new_uuidv7(),
            "created_at": _format_instant(now),
            "owning_authority": "identity",
            "evidence_class": _evidence_class(self.environment_namespace),
            "environment_namespace": self.environment_namespace,
            "source_refs": [],
            "event_kind": "DEVICE_LOST",
            "prior_device_refs": [],
            "replacement_device_ref": None,
            "effective_at": _format_instant(now),
            "promotion_hold": True,
            "entry_hold": True,
            "reconciliation_required": True,
            "evidence_ref": {
                "target_schema_name": "qc2.integrity_build.EvidenceEvent.v1",
                "target_id": new_uuidv7(),
                "content_hash": "0" * 64,
            },
        }
        validate_contract("RecoveryEvent", event)
        self.repository.complete_recovery(
            environment_namespace=self.environment_namespace,
            challenge_id=challenge_id,
            recovery_verifier_hash=verifier,
            replacement_device=device,
            replacement_session=session,
            access_token_hash=_token_hash(tokens[0], "qc2.owner.access.v1"),
            refresh_token_hash=_token_hash(tokens[1], "qc2.owner.refresh.v1"),
            refresh_expires_at=now
            + timedelta(seconds=self.policy.refresh_credential_lifetime_seconds),
            next_recovery_verifier_hash=_token_hash(
                next_recovery_material, "qc2.owner.recovery.v1"
            ),
            recovery_event=event,
            now=now,
        )
        return SessionTokens(session, tokens[0], tokens[1], next_recovery_material)

    def revoke_device(
        self,
        *,
        access_token: str,
        challenge_id: str,
        device_id: str,
        signature: bytes,
        now: datetime,
    ) -> dict[str, Any]:
        return self.submit_signed_command(
            access_token=access_token,
            challenge_id=challenge_id,
            request_body={
                "schema_name": "qc2.owner_api.OwnerCommandRequest.v1",
                "schema_version": "1.0",
                "command_type": "DEVICE_ACTION",
                "payload": {"action": "REVOKE_DEVICE", "device_id": device_id},
            },
            signature=signature,
            now=now,
        )

    def status(self) -> IdentityStatus:
        return self.repository.status(self.environment_namespace)

    def _verified_security_level(
        self, fingerprint: str, claimed: str, evidence: bytes | None
    ) -> str:
        if claimed not in _SECURITY_LEVELS:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "unknown device security level")
        if self.security_level_verifier is None:
            if claimed != "UNKNOWN" or evidence is not None:
                raise IdentityAuthorityError(IdentityErrorCode.INVALID_SECURITY_EVIDENCE)
            return "UNKNOWN"
        try:
            verified = self.security_level_verifier.verify(
                public_key_fingerprint=fingerprint,
                claimed_level=claimed,
                evidence=evidence,
                environment_namespace=self.environment_namespace,
            )
        except Exception as exc:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_SECURITY_EVIDENCE) from exc
        if verified not in _SECURITY_LEVELS or verified != claimed:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_SECURITY_EVIDENCE)
        return verified

    @staticmethod
    def _challenge_lifetime(requested: int | None, configured: int) -> int:
        if requested is None:
            return configured
        if type(requested) is not int or requested <= 0 or requested > configured:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "challenge lifetime exceeds policy")
        return requested

    @staticmethod
    def _new_tokens() -> tuple[str, str]:
        return new_offline_secret(), new_offline_secret()

    @staticmethod
    def _assert_current_identity(
        device: dict[str, Any], session: dict[str, Any], now: datetime
    ) -> None:
        _contract("OwnerDevice", device)
        _contract("OwnerSession", session)
        if (
            device["revocation_state"] != "ENROLLED"
            or device["revoked_at"] is not None
            or session["revoked_at"] is not None
            or device["environment_namespace"] != session["environment_namespace"]
            or session["device_ref"]["target_id"] != device["id"]
            or session["evidence_class"] == "SYNTHETIC_FIXTURE"
            and session["environment_namespace"] != "test"
            or not _parse_instant(session["issued_at"]) <= now < _parse_instant(session["expires_at"])
        ):
            raise IdentityAuthorityError(IdentityErrorCode.IDENTITY_REVOKED)

    @staticmethod
    def _validate_command_body(command_type: str, body: dict[str, Any]) -> None:
        if (
            set(body) != {"schema_name", "schema_version", "command_type", "payload"}
            or body.get("schema_name") != "qc2.owner_api.OwnerCommandRequest.v1"
            or body.get("schema_version") != "1.0"
            or body.get("command_type") != command_type
            or not isinstance(body.get("payload"), dict)
        ):
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT)

        payload = body["payload"]
        uuid7_pattern = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
        )

        def typed_reference(
            value: Any, schema_name: str, *, content_addressed: bool
        ) -> bool:
            if not isinstance(value, dict):
                return False
            expected_keys = {"target_schema_name", "target_id"}
            if content_addressed:
                expected_keys.add("content_hash")
            return (
                set(value) == expected_keys
                and value.get("target_schema_name") == schema_name
                and isinstance(value.get("target_id"), str)
                and uuid7_pattern.fullmatch(value["target_id"]) is not None
                and (
                    not content_addressed
                    or isinstance(value.get("content_hash"), str)
                    and _SHA256.fullmatch(value["content_hash"]) is not None
                )
            )

        safe_integer = (1 << 53) - 1
        valid = False
        if command_type == "PROMOTION":
            valid = (
                set(payload) == {"challenge_ref", "decision", "request_hash"}
                and typed_reference(
                    payload.get("challenge_ref"),
                    "qc2.governance_owner.PromotionChallenge.v1",
                    content_addressed=True,
                )
                and isinstance(payload.get("decision"), str)
                and payload["decision"] in {"APPROVE", "HOLD", "REJECT"}
                and isinstance(payload.get("request_hash"), str)
                and _SHA256.fullmatch(payload["request_hash"]) is not None
            )
        elif command_type == "EPOCH_ACTIVATION":
            valid = (
                set(payload)
                == {"challenge_ref", "epoch_manifest_hash", "decision"}
                and typed_reference(
                    payload.get("challenge_ref"),
                    "qc2.governance_owner.EpochActivationChallenge.v1",
                    content_addressed=True,
                )
                and isinstance(payload.get("decision"), str)
                and payload["decision"] in {"APPROVE", "REJECT"}
                and isinstance(payload.get("epoch_manifest_hash"), str)
                and _SHA256.fullmatch(payload["epoch_manifest_hash"]) is not None
            )
        elif command_type == "PAUSE_NEW_ENTRIES":
            generation = payload.get("expected_generation")
            valid = (
                set(payload) == {"expected_generation", "reason_code"}
                and isinstance(generation, int)
                and not isinstance(generation, bool)
                and 0 <= generation <= safe_integer
                and isinstance(payload.get("reason_code"), str)
                and _SLUG.fullmatch(payload["reason_code"]) is not None
            )
        elif command_type == "RESUME_REQUEST":
            generation = payload.get("expected_pause_generation")
            valid = (
                set(payload) == {"expected_pause_generation"}
                and isinstance(generation, int)
                and not isinstance(generation, bool)
                and 1 <= generation <= safe_integer
            )
        elif command_type == "ACKNOWLEDGE_ALERT":
            sequence = payload.get("expected_projection_sequence")
            valid = (
                set(payload) == {"alert_ref", "expected_projection_sequence"}
                and typed_reference(
                    payload.get("alert_ref"),
                    "qc2.governance_owner.Alert.v1",
                    content_addressed=False,
                )
                and isinstance(sequence, int)
                and not isinstance(sequence, bool)
                and 1 <= sequence <= safe_integer
            )
        elif command_type == "DEVICE_ACTION":
            device_id = payload.get("device_id")
            valid = (
                set(payload) == {"action", "device_id"}
                and payload.get("action") == "REVOKE_DEVICE"
                and isinstance(device_id, str)
                and uuid7_pattern.fullmatch(device_id) is not None
            )

        if not valid:
            raise IdentityAuthorityError(
                IdentityErrorCode.INVALID_INPUT,
                "unsupported or malformed owner command request",
            )


def _check_key_id(value: str) -> None:
    if not isinstance(value, str) or not _SLUG.fullmatch(value):
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "invalid key ID")


def _check_app_version(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 128 or "\x00" in value:
        raise IdentityAuthorityError(IdentityErrorCode.INVALID_INPUT, "invalid app version")


class IdentityProvider:
    """Approval-provider adapter that resolves and refreshes identity from storage."""

    def __init__(
        self, repository: IdentityRepositoryPort, *, environment_namespace: str
    ) -> None:
        _check_environment(environment_namespace)
        if repository.fixture_only and environment_namespace != "test":
            raise IdentityAuthorityError(IdentityErrorCode.FIXTURE_ONLY)
        self.repository = repository
        self.environment_namespace = environment_namespace

    def resolve_session(
        self, *, session_record_id: str, environment_namespace: str, now: datetime
    ) -> IdentityBinding:
        _utc(now)
        if environment_namespace != self.environment_namespace:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
        device, session, session_revoked_at, device_revoked_at = self.repository.resolve_session(
            environment_namespace, session_record_id
        )
        if device["environment_namespace"] != environment_namespace:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
        if session["device_ref"]["target_id"] != device["id"]:
            raise IdentityAuthorityError(IdentityErrorCode.INVALID_IDENTITY)
        if session_revoked_at is not None:
            session["revoked_at"] = session_revoked_at
        if device_revoked_at is not None:
            device["revocation_state"] = "REVOKED"
            device["revoked_at"] = device_revoked_at
        return IdentityBinding(
            device_record=device,
            session_record=session,
            owner_binding=device["owner_binding"],
            fixture_identity=(
                environment_namespace == "test"
                and session["evidence_class"] == "SYNTHETIC_FIXTURE"
            ),
        )

    def recheck_for_commit(
        self, binding: IdentityBinding, *, now: datetime
    ) -> IdentityBinding:
        return self.resolve_session(
            session_record_id=binding.session_record["id"],
            environment_namespace=binding.session_record["environment_namespace"],
            now=now,
        )
