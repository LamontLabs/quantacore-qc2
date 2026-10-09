"""Fixture-gated exact-state owner decisions for promotion.

This module validates owner approval evidence only. It has no Champion writer,
broker route, production identity adapter, or production-enabled setting.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import re
import secrets
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from qc2_contracts.runtime import (
    CONTRACTS,
    CONTENT_ADDRESSED,
    canonical_content_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

APPROVAL_DOMAIN = "promotion"
APPROVAL_ACTION = "PROMOTION_DECISION"
PRODUCTION_APPROVAL_ENABLED = False
_SIGNING_PREFIX = b"QC2_OWNER_DECISION_ENVELOPE_V1\x00"
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")
_SUPPORTED_FIXTURE_ENVIRONMENTS = frozenset({"development", "test"})
_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "v1"
_SCHEMA_FILES = {
    "challenge": "PromotionApprovalChallenge.schema.json",
    "decision": "OwnerDecisionEnvelope.schema.json",
}


class ApprovalErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    INVALID_CONTRACT = "invalid_contract"
    INVALID_IDENTITY = "invalid_identity"
    IDENTITY_REVOKED = "identity_revoked"
    INVALID_SIGNATURE = "invalid_signature"
    EXPIRED = "expired"
    REPLAY = "replay"
    STALE_REQUEST = "stale_request"
    BUNDLE_CHANGED = "bundle_changed"
    CANDIDATE_CHANGED = "candidate_changed"
    CHAMPION_CHANGED = "champion_changed"
    EPOCH_CHANGED = "epoch_changed"
    REGISTRY_CHANGED = "registry_changed"
    POLICY_CHANGED = "policy_changed"
    NOT_ELIGIBLE = "not_eligible"
    SCOPE_MISMATCH = "scope_mismatch"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    UNKNOWN_CHALLENGE = "unknown_challenge"
    UNKNOWN_DECISION = "unknown_decision"
    DECISION_NOT_APPROVAL = "decision_not_approval"
    NONCE_NOT_RESERVED = "nonce_not_reserved"
    REAL_AUTHORITY_DISABLED = "real_authority_disabled"


class ApprovalAuthorityError(ValueError):
    """Stable machine-readable rejection from the owner approval boundary."""

    def __init__(self, code: ApprovalErrorCode, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code.value)


class NonceState(StrEnum):
    ISSUED = "ISSUED"
    RESERVED_FOR_COMMIT = "RESERVED_FOR_COMMIT"
    CONSUMED_IN_TRANSITION = "CONSUMED_IN_TRANSITION"
    CONSUMED_NO_TRANSITION = "CONSUMED_NO_TRANSITION"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ContractRef:
    target_schema_name: str
    target_id: str
    content_hash: str

    def as_dict(self) -> dict[str, str]:
        return {
            "target_schema_name": self.target_schema_name,
            "target_id": self.target_id,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class PromotionSnapshot:
    """Exact, independently read promotion state bound by an approval challenge."""

    request_ref: ContractRef
    request_hash: str
    bundle_hash: str
    candidate_hash: str
    expected_champion_hash: str | None
    expected_generation: int
    epoch_ref: ContractRef
    registry_refs: tuple[ContractRef, ...]
    policy_ref: ContractRef
    eligible_for_owner_review: bool


@dataclass(frozen=True, slots=True)
class IdentityBinding:
    """Public identity facts returned by the identity-provider port."""

    device_record: dict[str, Any]
    session_record: dict[str, Any]
    owner_binding: str
    fixture_identity: bool


class IdentityProviderPort(Protocol):
    """Identity adapter; real enrollment and session providers are intentionally absent.

    Resolution is by the server-side session ID and must refuse non-owner sessions;
    it must not trust a caller-supplied device or owner identity. Commit rechecks
    must read current revocation/session state rather than echo the saved binding.
    """

    def resolve_session(
        self,
        *,
        session_record_id: str,
        environment_namespace: str,
        now: datetime,
    ) -> IdentityBinding: ...

    def recheck_for_commit(self, binding: IdentityBinding, *, now: datetime) -> IdentityBinding: ...


class PromotionStateReader(Protocol):
    """Read-only port for the currently authoritative promotion state."""

    def current_snapshot(self, request_id: str) -> PromotionSnapshot: ...


class ApprovalLedgerPort(Protocol):
    """Persistence boundary; writes must serialize idempotency and nonce reservation."""

    def store_challenge(
        self,
        scoped_challenge: dict[str, Any],
        promotion_challenge: dict[str, Any],
    ) -> None: ...

    def get_challenge(
        self, digest: str
    ) -> tuple[dict[str, Any], dict[str, Any], NonceState] | None: ...

    def lookup_idempotency(self, key: str, envelope_hash: str) -> DecisionSubmission | None: ...

    def mark_expired(self, challenge_hash: str) -> None: ...

    def record_decision_once(
        self,
        *,
        challenge_hash: str,
        envelope_hash: str,
        idempotency_key: str,
        signed_envelope: dict[str, Any],
        decision_record: dict[str, Any],
        identity_binding: IdentityBinding,
    ) -> DecisionSubmission: ...

    def get_decision_context(
        self, decision_id: str
    ) -> tuple[DecisionSubmission, IdentityBinding] | None: ...


class PromotionTransitionTransaction(Protocol):
    """QC2-043 must consume the ticket in its Champion pointer transaction."""

    def consume_owner_approval(self, ticket: PromotionApprovalTicket) -> None: ...


@dataclass(frozen=True, slots=True)
class IssuedApprovalChallenge:
    scoped_challenge: dict[str, Any]
    promotion_challenge: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DecisionSubmission:
    decision_record: dict[str, Any]
    signed_envelope: dict[str, Any]
    challenge_hash: str
    envelope_hash: str
    idempotency_key: str
    nonce_state: NonceState
    idempotent_replay: bool

    @property
    def is_approval(self) -> bool:
        return self.decision_record["decision"] == "APPROVE"


@dataclass(frozen=True, slots=True)
class PromotionApprovalTicket:
    """Internal commit token; the caller must consume it inside its transition transaction."""

    scoped_challenge_ref: ContractRef
    promotion_challenge_ref: ContractRef
    decision_ref: ContractRef
    nonce: str
    request_hash: str
    idempotency_key: str
    envelope_hash: str
    expected_champion_hash: str | None
    expected_generation: int


@dataclass(frozen=True, slots=True)
class CommitTimeRecheck:
    checks_passed: bool
    action_authorized: bool
    reason_code: str
    nonce_state: NonceState | None
    decision_id: str
    ticket: PromotionApprovalTicket | None = None


@dataclass(slots=True)
class _ChallengeEntry:
    scoped_challenge: dict[str, Any]
    promotion_challenge: dict[str, Any]
    nonce_state: NonceState = NonceState.ISSUED


@dataclass(frozen=True, slots=True)
class _DecisionEntry:
    submission: DecisionSubmission
    identity_binding: IdentityBinding


class InMemoryApprovalLedger:
    """Non-durable fixture ledger. It is never an authority for production."""

    fixture_only = True

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._challenges: dict[str, _ChallengeEntry] = {}
        self._nonce_index: dict[str, str] = {}
        self._idempotency: dict[str, tuple[str, DecisionSubmission]] = {}
        self._decisions: dict[str, _DecisionEntry] = {}

    def store_challenge(
        self,
        scoped_challenge: dict[str, Any],
        promotion_challenge: dict[str, Any],
    ) -> None:
        digest = scoped_challenge["content_hash"]
        nonce = scoped_challenge["nonce"]
        with self._lock:
            if digest in self._challenges or nonce in self._nonce_index:
                raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_INPUT, "nonce collision")
            self._challenges[digest] = _ChallengeEntry(
                copy.deepcopy(scoped_challenge),
                copy.deepcopy(promotion_challenge),
            )
            self._nonce_index[nonce] = digest

    def get_challenge(
        self, digest: str
    ) -> tuple[dict[str, Any], dict[str, Any], NonceState] | None:
        with self._lock:
            entry = self._challenges.get(digest)
            if entry is None:
                return None
            return (
                copy.deepcopy(entry.scoped_challenge),
                copy.deepcopy(entry.promotion_challenge),
                entry.nonce_state,
            )

    def lookup_idempotency(self, key: str, envelope_hash: str) -> DecisionSubmission | None:
        with self._lock:
            previous = self._idempotency.get(key)
            if previous is None:
                return None
            old_hash, submission = previous
            if old_hash != envelope_hash:
                raise ApprovalAuthorityError(ApprovalErrorCode.IDEMPOTENCY_CONFLICT)
            return replace(copy.deepcopy(submission), idempotent_replay=True)

    def mark_expired(self, challenge_hash: str) -> None:
        with self._lock:
            challenge = self._challenges.get(challenge_hash)
            if challenge is not None and challenge.nonce_state in {
                NonceState.ISSUED,
                NonceState.RESERVED_FOR_COMMIT,
            }:
                challenge.nonce_state = NonceState.EXPIRED

    def record_decision_once(
        self,
        *,
        challenge_hash: str,
        envelope_hash: str,
        idempotency_key: str,
        signed_envelope: dict[str, Any],
        decision_record: dict[str, Any],
        identity_binding: IdentityBinding,
    ) -> DecisionSubmission:
        with self._lock:
            previous = self._idempotency.get(idempotency_key)
            if previous is not None:
                old_hash, submission = previous
                if old_hash != envelope_hash:
                    raise ApprovalAuthorityError(ApprovalErrorCode.IDEMPOTENCY_CONFLICT)
                return replace(copy.deepcopy(submission), idempotent_replay=True)

            challenge = self._challenges.get(challenge_hash)
            if challenge is None:
                raise ApprovalAuthorityError(ApprovalErrorCode.UNKNOWN_CHALLENGE)
            if challenge.nonce_state != NonceState.ISSUED:
                raise ApprovalAuthorityError(ApprovalErrorCode.REPLAY)

            nonce_state = (
                NonceState.RESERVED_FOR_COMMIT
                if decision_record["decision"] == "APPROVE"
                else NonceState.CONSUMED_NO_TRANSITION
            )
            challenge.nonce_state = nonce_state
            submission = DecisionSubmission(
                decision_record=copy.deepcopy(decision_record),
                signed_envelope=copy.deepcopy(signed_envelope),
                challenge_hash=challenge_hash,
                envelope_hash=envelope_hash,
                idempotency_key=idempotency_key,
                nonce_state=nonce_state,
                idempotent_replay=False,
            )
            decision_id = decision_record["id"]
            self._idempotency[idempotency_key] = (envelope_hash, submission)
            self._decisions[decision_id] = _DecisionEntry(
                copy.deepcopy(submission),
                copy.deepcopy(identity_binding),
            )
            return copy.deepcopy(submission)

    def get_decision_context(
        self, decision_id: str
    ) -> tuple[DecisionSubmission, IdentityBinding] | None:
        with self._lock:
            entry = self._decisions.get(decision_id)
            if entry is None:
                return None
            return copy.deepcopy(entry.submission), copy.deepcopy(entry.identity_binding)


def _thaw(value: Any) -> Any:
    """Convert immutable contract mappings/tuples into JSON-native dicts/lists."""
    if isinstance(value, dict):
        return {key: _thaw(child) for key, child in value.items()}
    if hasattr(value, "items"):
        return {str(key): _thaw(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(child) for child in value]
    return value


def _load_validator(filename: str) -> Draft202012Validator:
    schema = json.loads((_SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


_CHALLENGE_VALIDATOR = _load_validator(_SCHEMA_FILES["challenge"])
_DECISION_VALIDATOR = _load_validator(_SCHEMA_FILES["decision"])


def _validate_local(
    validator: Draft202012Validator,
    payload: dict[str, Any],
    code: ApprovalErrorCode = ApprovalErrorCode.INVALID_INPUT,
) -> None:
    try:
        validator.validate(payload)
    except ValidationError as exc:
        raise ApprovalAuthorityError(code, exc.message) from exc


def _now_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_INPUT, "UTC datetime required")
    if value.utcoffset() != timedelta(0):
        raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_INPUT, "UTC datetime required")
    return value.astimezone(UTC)


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ApprovalAuthorityError(
            ApprovalErrorCode.INVALID_INPUT, "invalid UTC instant"
        ) from exc
    return _now_utc(parsed)


def _format_instant(value: datetime) -> str:
    value = _now_utc(value)
    timespec = "microseconds" if value.microsecond else "seconds"
    return value.isoformat(timespec=timespec).replace("+00:00", "Z")


def _contract_record(name: str, value: Any) -> dict[str, Any]:
    record = _thaw(value)
    if not isinstance(record, dict):
        raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_CONTRACT)
    try:
        validate_contract(name, record)
        if name in CONTENT_ADDRESSED:
            verify_content_hash(name, record)
    except (TypeError, ValueError) as exc:
        raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_CONTRACT, f"{name}: {exc}") from exc
    return record


def _typed_ref(name: str, record: dict[str, Any]) -> dict[str, str]:
    result = {
        "target_schema_name": CONTRACTS[name][1],
        "target_id": record["id"],
    }
    if name in CONTENT_ADDRESSED and isinstance(record.get("content_hash"), str):
        result["content_hash"] = record["content_hash"]
    return result


def _scope_hash(domain: str, payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "content_hash"}
    return domain_separated_sha256(domain, canonical_json_bytes(body))


def decision_signing_bytes(envelope: dict[str, Any]) -> bytes:
    """Canonical P-256 message; scope and every non-signature field are signed."""
    body = {key: value for key, value in _thaw(envelope).items() if key != "signature"}
    return _SIGNING_PREFIX + canonical_json_bytes(body)


def _decode_base64url(value: str) -> bytes:
    if not isinstance(value, str) or _BASE64URL.fullmatch(value) is None:
        raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_INPUT, "invalid base64url value")
    try:
        decoded = base64.b64decode(
            value + "=" * ((4 - len(value) % 4) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, binascii.Error) as exc:
        raise ApprovalAuthorityError(
            ApprovalErrorCode.INVALID_INPUT, "invalid base64url value"
        ) from exc
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if canonical != value:
        raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_INPUT, "noncanonical base64url")
    return decoded


def _device_key_fingerprint(device_record: dict[str, Any]) -> str:
    return hashlib.sha256(_decode_base64url(device_record["public_key"])).hexdigest()


def _session_binding_hash(session_record: dict[str, Any]) -> str:
    return domain_separated_sha256(
        "qc2.owner_api.owner_session_binding.v1",
        canonical_json_bytes(_thaw(session_record)),
    )


def _verify_signature(envelope: dict[str, Any], identity: IdentityBinding) -> None:
    device = identity.device_record
    try:
        public_key = serialization.load_der_public_key(_decode_base64url(device["public_key"]))
        signature = _decode_base64url(envelope["signature"])
        if not isinstance(public_key, EllipticCurvePublicKey) or not isinstance(
            public_key.curve, ec.SECP256R1
        ):
            raise ApprovalAuthorityError(
                ApprovalErrorCode.INVALID_IDENTITY, "owner key is not P-256"
            )
        public_key.verify(
            signature,
            decision_signing_bytes(envelope),
            ec.ECDSA(hashes.SHA256()),
        )
    except ApprovalAuthorityError:
        raise
    except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
        raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_SIGNATURE) from exc


def _identity_reference_matches(actual: dict[str, Any], expected_ref: dict[str, Any]) -> bool:
    matches = actual.get("target_schema_name") == expected_ref.get(
        "target_schema_name"
    ) and actual.get("target_id") == expected_ref.get("target_id")
    if "content_hash" in expected_ref:
        matches = matches and actual.get("content_hash") == expected_ref["content_hash"]
    return matches


class ApprovalAuthority:
    """Creates fixture-only challenges and validates signed owner decisions."""

    def __init__(
        self,
        *,
        identity_provider: IdentityProviderPort,
        state_reader: PromotionStateReader,
        ledger: ApprovalLedgerPort,
        environment_namespace: str,
        max_challenge_lifetime_seconds: int,
    ) -> None:
        if type(max_challenge_lifetime_seconds) is not int or max_challenge_lifetime_seconds <= 0:
            raise ValueError("max_challenge_lifetime_seconds must be positive")
        self.identity_provider = identity_provider
        self.state_reader = state_reader
        self.ledger = ledger
        self.environment_namespace = environment_namespace
        self.max_challenge_lifetime_seconds = max_challenge_lifetime_seconds

    def issue_challenge(
        self,
        *,
        request_id: str,
        owner_session_id: str,
        ttl_seconds: int,
        now: datetime,
    ) -> IssuedApprovalChallenge:
        now = _now_utc(now)
        self._require_fixture_mode()
        if (
            type(ttl_seconds) is not int
            or ttl_seconds <= 0
            or ttl_seconds > self.max_challenge_lifetime_seconds
        ):
            raise ApprovalAuthorityError(
                ApprovalErrorCode.INVALID_INPUT, "invalid challenge lifetime"
            )

        snapshot = self.state_reader.current_snapshot(request_id)
        _validate_snapshot(snapshot, request_id)
        if not snapshot.eligible_for_owner_review:
            raise ApprovalAuthorityError(ApprovalErrorCode.NOT_ELIGIBLE)

        identity = self.identity_provider.resolve_session(
            session_record_id=owner_session_id,
            environment_namespace=self.environment_namespace,
            now=now,
        )
        self._validate_identity(
            identity,
            now,
            expected_session_ref={
                "target_schema_name": CONTRACTS["OwnerSession"][1],
                "target_id": owner_session_id,
            },
        )

        nonce = "n" + secrets.token_hex(32)
        expires_at = now + timedelta(seconds=ttl_seconds)
        promotion_challenge = {
            **_contract_metadata(
                "PromotionChallenge", "promotion", self.environment_namespace, now
            ),
            "request_ref": _thaw(snapshot.request_ref.as_dict()),
            "bundle_hash": snapshot.bundle_hash,
            "candidate_hash": snapshot.candidate_hash,
            "expected_champion_hash": snapshot.expected_champion_hash,
            "expected_generation": snapshot.expected_generation,
            "epoch_ref": snapshot.epoch_ref.as_dict(),
            "registry_refs": [item.as_dict() for item in snapshot.registry_refs],
            "policy_ref": snapshot.policy_ref.as_dict(),
            "nonce": nonce,
            "issued_at": _format_instant(now),
            "expires_at": _format_instant(expires_at),
            "device_ref": _typed_ref("OwnerDevice", identity.device_record),
            "key_id": identity.device_record["owner_key_id"],
        }
        promotion_challenge["content_hash"] = canonical_content_hash(
            "PromotionChallenge", promotion_challenge
        )
        _contract_record("PromotionChallenge", promotion_challenge)

        session_ref = _typed_ref("OwnerSession", identity.session_record)
        scoped_challenge: dict[str, Any] = {
            "schema_name": "qc2.owner_api.PromotionApprovalChallenge.v1",
            "schema_version": "1.0",
            "id": new_uuidv7(),
            "domain": APPROVAL_DOMAIN,
            "action": APPROVAL_ACTION,
            "environment_namespace": self.environment_namespace,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "promotion_challenge_ref": _typed_ref("PromotionChallenge", promotion_challenge),
            "device_ref": _typed_ref("OwnerDevice", identity.device_record),
            "owner_session_ref": session_ref,
            "key_id": identity.device_record["owner_key_id"],
            "device_key_fingerprint": _device_key_fingerprint(identity.device_record),
            "owner_session_binding_hash": _session_binding_hash(identity.session_record),
            "request_hash": snapshot.request_hash,
            "nonce": nonce,
            "issued_at": _format_instant(now),
            "expires_at": _format_instant(expires_at),
            "content_hash": "0" * 64,
        }
        scoped_challenge["content_hash"] = _scope_hash(
            "qc2.owner_api.promotion_approval_challenge.v1", scoped_challenge
        )
        _validate_local(_CHALLENGE_VALIDATOR, scoped_challenge)
        self.ledger.store_challenge(scoped_challenge, promotion_challenge)
        return IssuedApprovalChallenge(
            scoped_challenge=copy.deepcopy(scoped_challenge),
            promotion_challenge=copy.deepcopy(promotion_challenge),
        )

    def submit_decision(self, envelope: dict[str, Any], *, now: datetime) -> DecisionSubmission:
        now = _now_utc(now)
        envelope = _thaw(envelope)
        if not isinstance(envelope, dict):
            raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_INPUT)
        _validate_local(_DECISION_VALIDATOR, envelope)
        envelope_hash = domain_separated_sha256(
            "qc2.owner_api.owner_decision_envelope.v1",
            canonical_json_bytes(envelope),
        )
        prior = self.ledger.lookup_idempotency(envelope["idempotency_key"], envelope_hash)
        if prior is not None:
            return prior

        scoped_ref = envelope["challenge_ref"]
        stored = self.ledger.get_challenge(scoped_ref["content_hash"])
        if stored is None:
            raise ApprovalAuthorityError(ApprovalErrorCode.UNKNOWN_CHALLENGE)
        scoped_challenge, promotion_challenge, nonce_state = stored
        _validate_local(_CHALLENGE_VALIDATOR, scoped_challenge)
        promotion_challenge = _contract_record("PromotionChallenge", promotion_challenge)
        _verify_scoped_challenge(scoped_challenge, promotion_challenge)
        self._require_fixture_mode()
        self._assert_envelope_scope(envelope, scoped_challenge, promotion_challenge)
        issued_at = _instant(scoped_challenge["issued_at"])
        expires_at = _instant(scoped_challenge["expires_at"])
        signed_at = _instant(envelope["signed_at"])
        if now >= expires_at:
            self.ledger.mark_expired(scoped_challenge["content_hash"])
            raise ApprovalAuthorityError(ApprovalErrorCode.EXPIRED)
        if signed_at >= expires_at:
            raise ApprovalAuthorityError(
                ApprovalErrorCode.INVALID_INPUT, "signing time outside challenge"
            )
        if nonce_state != NonceState.ISSUED:
            raise ApprovalAuthorityError(ApprovalErrorCode.REPLAY)
        if signed_at < issued_at or signed_at > now:
            raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_INPUT, "invalid signing time")

        current = self.state_reader.current_snapshot(
            promotion_challenge["request_ref"]["target_id"]
        )
        _assert_snapshot_matches(current, scoped_challenge, promotion_challenge)
        identity = self.identity_provider.resolve_session(
            session_record_id=scoped_challenge["owner_session_ref"]["target_id"],
            environment_namespace=self.environment_namespace,
            now=now,
        )
        self._validate_identity(
            identity,
            now,
            expected_session_ref=scoped_challenge["owner_session_ref"],
            expected_device_ref=scoped_challenge["device_ref"],
            expected_key_id=scoped_challenge["key_id"],
            expected_key_fingerprint=scoped_challenge["device_key_fingerprint"],
            expected_session_binding_hash=scoped_challenge["owner_session_binding_hash"],
        )
        _verify_signature(envelope, identity)

        decision_record = {
            **_contract_metadata("PromotionDecision", "promotion", self.environment_namespace, now),
            "challenge_ref": _typed_ref("PromotionChallenge", promotion_challenge),
            "decision": envelope["decision"],
            "signed_by_device_ref": _typed_ref("OwnerDevice", identity.device_record),
            "key_id": envelope["key_id"],
            "signature": envelope["signature"],
            "signed_at": envelope["signed_at"],
            "request_hash": envelope["request_hash"],
        }
        decision_record["content_hash"] = canonical_content_hash(
            "PromotionDecision", decision_record
        )
        _contract_record("PromotionDecision", decision_record)
        return self.ledger.record_decision_once(
            challenge_hash=scoped_challenge["content_hash"],
            envelope_hash=envelope_hash,
            idempotency_key=envelope["idempotency_key"],
            signed_envelope=envelope,
            decision_record=decision_record,
            identity_binding=identity,
        )

    def recheck_for_commit(self, decision_id: str, *, now: datetime) -> CommitTimeRecheck:
        now = _now_utc(now)
        context = self.ledger.get_decision_context(decision_id)
        if context is None:
            raise ApprovalAuthorityError(ApprovalErrorCode.UNKNOWN_DECISION)
        submission, prior_identity = context
        if not submission.is_approval:
            return CommitTimeRecheck(
                False,
                False,
                ApprovalErrorCode.DECISION_NOT_APPROVAL.value,
                submission.nonce_state,
                decision_id,
            )
        stored = self.ledger.get_challenge(submission.challenge_hash)
        if stored is None:
            return CommitTimeRecheck(
                False,
                False,
                ApprovalErrorCode.UNKNOWN_CHALLENGE.value,
                submission.nonce_state,
                decision_id,
            )
        scoped_challenge, promotion_challenge, nonce_state = stored
        try:
            _verify_scoped_challenge(scoped_challenge, promotion_challenge)
            decision_record = _contract_record("PromotionDecision", submission.decision_record)
            signed_envelope = _thaw(submission.signed_envelope)
            _validate_local(_DECISION_VALIDATOR, signed_envelope)
            expected_envelope_hash = domain_separated_sha256(
                "qc2.owner_api.owner_decision_envelope.v1",
                canonical_json_bytes(signed_envelope),
            )
            if (
                expected_envelope_hash != submission.envelope_hash
                or submission.challenge_hash != scoped_challenge["content_hash"]
                or signed_envelope["idempotency_key"] != submission.idempotency_key
                or decision_record["id"] != decision_id
                or decision_record["decision"] != signed_envelope["decision"]
                or decision_record["challenge_ref"]
                != _typed_ref("PromotionChallenge", promotion_challenge)
                or decision_record["signed_by_device_ref"]
                != signed_envelope["signed_by_device_ref"]
                or decision_record["key_id"] != signed_envelope["key_id"]
                or decision_record["signature"] != signed_envelope["signature"]
                or decision_record["signed_at"] != signed_envelope["signed_at"]
                or decision_record["request_hash"] != signed_envelope["request_hash"]
            ):
                raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_CONTRACT)
            self._assert_envelope_scope(signed_envelope, scoped_challenge, promotion_challenge)
            if now >= _instant(scoped_challenge["expires_at"]):
                self.ledger.mark_expired(submission.challenge_hash)
                raise ApprovalAuthorityError(ApprovalErrorCode.EXPIRED)
            if nonce_state != NonceState.RESERVED_FOR_COMMIT:
                raise ApprovalAuthorityError(ApprovalErrorCode.NONCE_NOT_RESERVED)
            current = self.state_reader.current_snapshot(
                promotion_challenge["request_ref"]["target_id"]
            )
            _assert_snapshot_matches(current, scoped_challenge, promotion_challenge)
            identity = self.identity_provider.recheck_for_commit(prior_identity, now=now)
            self._validate_identity(
                identity,
                now,
                expected_session_ref=scoped_challenge["owner_session_ref"],
                expected_device_ref=scoped_challenge["device_ref"],
                expected_key_id=scoped_challenge["key_id"],
                expected_key_fingerprint=scoped_challenge["device_key_fingerprint"],
                expected_session_binding_hash=scoped_challenge["owner_session_binding_hash"],
            )
            _verify_signature(signed_envelope, identity)
        except ApprovalAuthorityError as exc:
            return CommitTimeRecheck(False, False, exc.code.value, nonce_state, decision_id)

        # QC2-043 must consume the reserved nonce in the same transaction as its
        # compare-and-swap pointer update. This fixture-only task cannot authorize it.
        action_authorized = (
            PRODUCTION_APPROVAL_ENABLED
            and self.environment_namespace == "production"
            and not identity.fixture_identity
        )
        reason = (
            "ready_for_transition"
            if action_authorized
            else ApprovalErrorCode.REAL_AUTHORITY_DISABLED.value
        )
        ticket = (
            _commit_ticket(submission, scoped_challenge, promotion_challenge)
            if action_authorized
            else None
        )
        return CommitTimeRecheck(
            checks_passed=True,
            action_authorized=action_authorized,
            reason_code=reason,
            nonce_state=nonce_state,
            decision_id=decision_id,
            ticket=ticket,
        )

    def _require_fixture_mode(self) -> None:
        if not PRODUCTION_APPROVAL_ENABLED and self.environment_namespace == "production":
            raise ApprovalAuthorityError(ApprovalErrorCode.REAL_AUTHORITY_DISABLED)
        if self.environment_namespace not in _SUPPORTED_FIXTURE_ENVIRONMENTS:
            raise ApprovalAuthorityError(ApprovalErrorCode.REAL_AUTHORITY_DISABLED)

    def _validate_identity(
        self,
        binding: IdentityBinding,
        now: datetime,
        *,
        expected_session_ref: dict[str, Any] | None = None,
        expected_device_ref: dict[str, Any] | None = None,
        expected_key_id: str | None = None,
        expected_key_fingerprint: str | None = None,
        expected_session_binding_hash: str | None = None,
    ) -> None:
        device = _contract_record("OwnerDevice", binding.device_record)
        session = _contract_record("OwnerSession", binding.session_record)
        if device["revocation_state"] != "ENROLLED" or device["revoked_at"] is not None:
            raise ApprovalAuthorityError(ApprovalErrorCode.IDENTITY_REVOKED)
        if session["revoked_at"] is not None:
            raise ApprovalAuthorityError(ApprovalErrorCode.IDENTITY_REVOKED)
        if (
            device["environment_namespace"] != self.environment_namespace
            or session["environment_namespace"] != self.environment_namespace
            or not _instant(session["issued_at"]) <= now < _instant(session["expires_at"])
            or "PROMOTION" not in session["scope_refs"]
            or session["device_ref"]["target_id"] != device["id"]
            or binding.owner_binding != device["owner_binding"]
        ):
            raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_IDENTITY)
        if (
            binding.fixture_identity is not True
            or device["evidence_class"] != "SYNTHETIC_FIXTURE"
            or session["evidence_class"] != "SYNTHETIC_FIXTURE"
            or self.environment_namespace not in _SUPPORTED_FIXTURE_ENVIRONMENTS
        ):
            raise ApprovalAuthorityError(ApprovalErrorCode.REAL_AUTHORITY_DISABLED)
        if device["signing_algorithm"] != "ECDSA_P256_SHA256":
            raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_IDENTITY)
        if expected_session_ref is not None and not _identity_reference_matches(
            _typed_ref("OwnerSession", session), expected_session_ref
        ):
            raise ApprovalAuthorityError(ApprovalErrorCode.SCOPE_MISMATCH)
        if expected_device_ref is not None and not _identity_reference_matches(
            _typed_ref("OwnerDevice", device), expected_device_ref
        ):
            raise ApprovalAuthorityError(ApprovalErrorCode.SCOPE_MISMATCH)
        if expected_key_id is not None and device["owner_key_id"] != expected_key_id:
            raise ApprovalAuthorityError(ApprovalErrorCode.SCOPE_MISMATCH)
        if (
            expected_key_fingerprint is not None
            and _device_key_fingerprint(device) != expected_key_fingerprint
        ):
            raise ApprovalAuthorityError(ApprovalErrorCode.SCOPE_MISMATCH)
        if (
            expected_session_binding_hash is not None
            and _session_binding_hash(session) != expected_session_binding_hash
        ):
            raise ApprovalAuthorityError(ApprovalErrorCode.SCOPE_MISMATCH)
        try:
            key = serialization.load_der_public_key(_decode_base64url(device["public_key"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_IDENTITY) from exc
        if not isinstance(key, EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_IDENTITY)

    def _assert_envelope_scope(
        self,
        envelope: dict[str, Any],
        scoped_challenge: dict[str, Any],
        promotion_challenge: dict[str, Any],
    ) -> None:
        expected_challenge_ref = {
            "target_schema_name": scoped_challenge["schema_name"],
            "target_id": scoped_challenge["id"],
            "content_hash": scoped_challenge["content_hash"],
        }
        if (
            envelope["domain"] != scoped_challenge["domain"]
            or envelope["action"] != scoped_challenge["action"]
            or envelope["environment_namespace"] != self.environment_namespace
            or envelope["environment_namespace"] != scoped_challenge["environment_namespace"]
            or envelope["challenge_ref"] != expected_challenge_ref
            or envelope["promotion_challenge_ref"] != scoped_challenge["promotion_challenge_ref"]
            or envelope["request_hash"] != scoped_challenge["request_hash"]
            or envelope["nonce"] != scoped_challenge["nonce"]
            or envelope["signed_by_device_ref"] != scoped_challenge["device_ref"]
            or envelope["owner_session_ref"] != scoped_challenge["owner_session_ref"]
            or envelope["key_id"] != scoped_challenge["key_id"]
            or envelope["device_key_fingerprint"] != scoped_challenge["device_key_fingerprint"]
            or envelope["owner_session_binding_hash"]
            != scoped_challenge["owner_session_binding_hash"]
            or promotion_challenge["environment_namespace"]
            != scoped_challenge["environment_namespace"]
        ):
            raise ApprovalAuthorityError(ApprovalErrorCode.SCOPE_MISMATCH)


def _contract_metadata(
    name: str, authority: str, environment_namespace: str, now: datetime
) -> dict[str, Any]:
    return {
        "schema_name": CONTRACTS[name][1],
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": _format_instant(now),
        "owning_authority": authority,
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": environment_namespace,
        "source_refs": [],
        "content_hash": "0" * 64,
    }


def _commit_ticket(
    submission: DecisionSubmission,
    scoped_challenge: dict[str, Any],
    promotion_challenge: dict[str, Any],
) -> PromotionApprovalTicket:
    return PromotionApprovalTicket(
        scoped_challenge_ref=ContractRef(
            scoped_challenge["schema_name"],
            scoped_challenge["id"],
            scoped_challenge["content_hash"],
        ),
        promotion_challenge_ref=ContractRef(
            promotion_challenge["schema_name"],
            promotion_challenge["id"],
            promotion_challenge["content_hash"],
        ),
        decision_ref=ContractRef(
            submission.decision_record["schema_name"],
            submission.decision_record["id"],
            submission.decision_record["content_hash"],
        ),
        nonce=scoped_challenge["nonce"],
        request_hash=scoped_challenge["request_hash"],
        idempotency_key=submission.idempotency_key,
        envelope_hash=submission.envelope_hash,
        expected_champion_hash=promotion_challenge["expected_champion_hash"],
        expected_generation=promotion_challenge["expected_generation"],
    )


def _validate_snapshot(snapshot: PromotionSnapshot, request_id: str) -> None:
    if not isinstance(snapshot, PromotionSnapshot):
        raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_INPUT)
    hashes = (
        snapshot.request_hash,
        snapshot.bundle_hash,
        snapshot.candidate_hash,
        snapshot.epoch_ref.content_hash,
        snapshot.policy_ref.content_hash,
    )
    if (
        snapshot.request_ref.target_id != request_id
        or any(_HEX_SHA256.fullmatch(value) is None for value in hashes)
        or (
            snapshot.expected_champion_hash is not None
            and _HEX_SHA256.fullmatch(snapshot.expected_champion_hash) is None
        )
        or type(snapshot.expected_generation) is not int
        or snapshot.expected_generation < 0
        or not snapshot.registry_refs
        or any(_HEX_SHA256.fullmatch(ref.content_hash) is None for ref in snapshot.registry_refs)
    ):
        raise ApprovalAuthorityError(ApprovalErrorCode.INVALID_INPUT, "invalid promotion snapshot")


def _verify_scoped_challenge(scoped: dict[str, Any], promotion: dict[str, Any]) -> None:
    _validate_local(_CHALLENGE_VALIDATOR, scoped)
    promotion = _contract_record("PromotionChallenge", promotion)
    expected_hash = _scope_hash("qc2.owner_api.promotion_approval_challenge.v1", scoped)
    if (
        scoped["evidence_class"] != "SYNTHETIC_FIXTURE"
        or promotion["evidence_class"] != "SYNTHETIC_FIXTURE"
        or scoped["content_hash"] != expected_hash
        or scoped["promotion_challenge_ref"] != _typed_ref("PromotionChallenge", promotion)
        or scoped["device_ref"] != _plain_contract_ref(promotion, "device_ref")
        or scoped["nonce"] != promotion["nonce"]
        or scoped["key_id"] != promotion["key_id"]
        or scoped["environment_namespace"] != promotion["environment_namespace"]
        or scoped["issued_at"] != promotion["issued_at"]
        or scoped["expires_at"] != promotion["expires_at"]
    ):
        raise ApprovalAuthorityError(
            ApprovalErrorCode.INVALID_CONTRACT, "challenge binding mismatch"
        )


def _assert_snapshot_matches(
    current: PromotionSnapshot,
    scoped: dict[str, Any],
    promotion: dict[str, Any],
) -> None:
    _validate_snapshot(current, promotion["request_ref"]["target_id"])
    if not current.eligible_for_owner_review:
        raise ApprovalAuthorityError(ApprovalErrorCode.NOT_ELIGIBLE)
    if (
        current.request_hash != scoped["request_hash"]
        or current.request_ref.as_dict() != promotion["request_ref"]
    ):
        raise ApprovalAuthorityError(ApprovalErrorCode.STALE_REQUEST)
    if current.bundle_hash != promotion["bundle_hash"]:
        raise ApprovalAuthorityError(ApprovalErrorCode.BUNDLE_CHANGED)
    if current.candidate_hash != promotion["candidate_hash"]:
        raise ApprovalAuthorityError(ApprovalErrorCode.CANDIDATE_CHANGED)
    if (
        current.expected_champion_hash != promotion["expected_champion_hash"]
        or current.expected_generation != promotion["expected_generation"]
    ):
        raise ApprovalAuthorityError(ApprovalErrorCode.CHAMPION_CHANGED)
    if current.epoch_ref.as_dict() != promotion["epoch_ref"]:
        raise ApprovalAuthorityError(ApprovalErrorCode.EPOCH_CHANGED)
    if [item.as_dict() for item in current.registry_refs] != promotion["registry_refs"]:
        raise ApprovalAuthorityError(ApprovalErrorCode.REGISTRY_CHANGED)
    if current.policy_ref.as_dict() != promotion["policy_ref"]:
        raise ApprovalAuthorityError(ApprovalErrorCode.POLICY_CHANGED)


def _plain_contract_ref(contract: dict[str, Any], field: str) -> dict[str, Any]:
    reference = contract[field]
    result = {
        "target_schema_name": reference["target_schema_name"],
        "target_id": reference["target_id"],
    }
    if "content_hash" in reference:
        result["content_hash"] = reference["content_hash"]
    return result
