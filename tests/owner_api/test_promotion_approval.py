from __future__ import annotations

import base64
import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from qc2_contracts.runtime import (
    CONTRACTS,
    CONTENT_ADDRESSED,
    canonical_content_hash,
    new_uuidv7,
    validate_contract,
)
from qc2_owner_api.approval import (
    APPROVAL_ACTION,
    APPROVAL_DOMAIN,
    PRODUCTION_APPROVAL_ENABLED,
    ApprovalAuthority,
    ApprovalAuthorityError,
    ApprovalErrorCode,
    ContractRef,
    IdentityBinding,
    InMemoryApprovalLedger,
    PromotionSnapshot,
    decision_signing_bytes,
)

NOW = datetime(2026, 10, 8, 17, 0, tzinfo=UTC)


def _instant(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _contract(name: str, **fields: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_name": CONTRACTS[name][1],
        "schema_version": "1.0",
        "id": new_uuidv7(),
        "created_at": _instant(NOW),
        "owning_authority": "identity" if name in {"OwnerDevice", "OwnerSession"} else "promotion",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        **fields,
    }
    if name in CONTENT_ADDRESSED:
        record["content_hash"] = "0" * 64
        record["content_hash"] = canonical_content_hash(name, record)
    validate_contract(name, record)
    return record


def _record_ref(name: str, record: dict[str, object]) -> dict[str, str]:
    result = {
        "target_schema_name": CONTRACTS[name][1],
        "target_id": str(record["id"]),
    }
    if "content_hash" in record:
        result["content_hash"] = str(record["content_hash"])
    return result


def _ref(name: str, record: dict[str, object]) -> ContractRef:
    return ContractRef(
        target_schema_name=CONTRACTS[name][1],
        target_id=str(record["id"]),
        content_hash=str(record["content_hash"]),
    )


def _fixture_identity() -> tuple[IdentityBinding, ec.EllipticCurvePrivateKey]:
    private_key = ec.derive_private_key(0x123456789ABCDEF, ec.SECP256R1())
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    device = _contract(
        "OwnerDevice",
        owner_key_id="owner_fixture_key",
        public_key=_b64url(public_der),
        signing_algorithm="ECDSA_P256_SHA256",
        security_level="SOFTWARE",
        enrollment_proof_hash="a" * 64,
        owner_binding="fixture_owner",
        app_version="fixture-1",
        revocation_state="ENROLLED",
        enrolled_at=_instant(NOW - timedelta(minutes=2)),
        revoked_at=None,
    )
    session = _contract(
        "OwnerSession",
        device_ref=_record_ref("OwnerDevice", device),
        session_id="fixture_session",
        issued_at=_instant(NOW - timedelta(minutes=1)),
        expires_at=_instant(NOW + timedelta(minutes=30)),
        revoked_at=None,
        scope_refs=["PROMOTION"],
        refresh_generation=1,
    )
    return (
        IdentityBinding(
            device_record=device,
            session_record=session,
            owner_binding="fixture_owner",
            fixture_identity=True,
        ),
        private_key,
    )


def _snapshot() -> PromotionSnapshot:
    request = {
        "id": new_uuidv7(),
        "content_hash": "1" * 64,
    }
    epoch = {
        "id": new_uuidv7(),
        "content_hash": "2" * 64,
    }
    registry = {
        "id": new_uuidv7(),
        "content_hash": "3" * 64,
    }
    policy = {
        "id": new_uuidv7(),
        "content_hash": "4" * 64,
    }
    return PromotionSnapshot(
        request_ref=ContractRef(
            CONTRACTS["PromotionRequest"][1], request["id"], request["content_hash"]
        ),
        request_hash="5" * 64,
        bundle_hash="6" * 64,
        candidate_hash="7" * 64,
        expected_champion_hash="8" * 64,
        expected_generation=4,
        epoch_ref=ContractRef(CONTRACTS["ValidationEpoch"][1], epoch["id"], epoch["content_hash"]),
        registry_refs=(
            ContractRef(CONTRACTS["FeatureRegistry"][1], registry["id"], registry["content_hash"]),
        ),
        policy_ref=ContractRef(
            CONTRACTS["PromotionPolicy"][1], policy["id"], policy["content_hash"]
        ),
        eligible_for_owner_review=True,
    )


class FixtureIdentityProvider:
    def __init__(self, binding: IdentityBinding) -> None:
        self.binding = binding

    def resolve_session(
        self, *, session_record_id: str, environment_namespace: str, now: datetime
    ) -> IdentityBinding:
        del now
        assert environment_namespace == "test"
        assert session_record_id == self.binding.session_record["id"]
        return copy.deepcopy(self.binding)

    def recheck_for_commit(self, binding: IdentityBinding, *, now: datetime) -> IdentityBinding:
        del now
        assert binding.session_record["id"] == self.binding.session_record["id"]
        return copy.deepcopy(self.binding)

    def revoke_device(self, at: datetime) -> None:
        self.binding.device_record["revocation_state"] = "REVOKED"
        self.binding.device_record["revoked_at"] = _instant(at)

    def revoke_session(self, at: datetime) -> None:
        self.binding.session_record["revoked_at"] = _instant(at)


class FixtureStateReader:
    def __init__(self, snapshot: PromotionSnapshot) -> None:
        self.snapshot = snapshot

    def current_snapshot(self, request_id: str) -> PromotionSnapshot:
        assert request_id == self.snapshot.request_ref.target_id
        return self.snapshot


@pytest.fixture
def rig():
    identity, private_key = _fixture_identity()
    state = FixtureStateReader(_snapshot())
    ledger = InMemoryApprovalLedger()
    authority = ApprovalAuthority(
        identity_provider=FixtureIdentityProvider(identity),
        state_reader=state,
        ledger=ledger,
        environment_namespace="test",
        max_challenge_lifetime_seconds=300,
    )
    issued = authority.issue_challenge(
        request_id=state.snapshot.request_ref.target_id,
        owner_session_id=identity.session_record["id"],
        ttl_seconds=120,
        now=NOW,
    )
    return authority, issued, private_key, identity, state, ledger


def _signed_envelope(
    issued,
    private_key: ec.EllipticCurvePrivateKey,
    *,
    decision: str = "APPROVE",
    idempotency_key: str = "idem_fixture_1",
    signed_at: datetime = NOW + timedelta(seconds=1),
) -> dict[str, object]:
    scoped = issued.scoped_challenge
    envelope: dict[str, object] = {
        "schema_name": "qc2.owner_api.OwnerDecisionEnvelope.v1",
        "schema_version": "1.0",
        "domain": APPROVAL_DOMAIN,
        "action": APPROVAL_ACTION,
        "environment_namespace": scoped["environment_namespace"],
        "challenge_ref": {
            "target_schema_name": scoped["schema_name"],
            "target_id": scoped["id"],
            "content_hash": scoped["content_hash"],
        },
        "promotion_challenge_ref": copy.deepcopy(scoped["promotion_challenge_ref"]),
        "decision": decision,
        "request_hash": scoped["request_hash"],
        "nonce": scoped["nonce"],
        "signed_by_device_ref": copy.deepcopy(scoped["device_ref"]),
        "owner_session_ref": copy.deepcopy(scoped["owner_session_ref"]),
        "key_id": scoped["key_id"],
        "device_key_fingerprint": scoped["device_key_fingerprint"],
        "owner_session_binding_hash": scoped["owner_session_binding_hash"],
        "idempotency_key": idempotency_key,
        "signing_algorithm": "ECDSA_P256_SHA256",
        "signed_at": _instant(signed_at),
        "signature": "AA",
    }
    envelope["signature"] = _b64url(
        private_key.sign(
            decision_signing_bytes(envelope),
            ec.ECDSA(hashes.SHA256()),
        )
    )
    return envelope


def _assert_code(code: ApprovalErrorCode, call) -> None:
    with pytest.raises(ApprovalAuthorityError) as caught:
        call()
    assert caught.value.code == code


def test_approval_record_is_canonical_and_exact_retry_is_idempotent(rig) -> None:
    authority, issued, private_key, _, _, ledger = rig
    envelope = _signed_envelope(issued, private_key)

    first = authority.submit_decision(envelope, now=NOW + timedelta(seconds=3))
    retry = authority.submit_decision(envelope, now=NOW + timedelta(seconds=4))

    assert first.decision_record["schema_name"] == CONTRACTS["PromotionDecision"][1]
    assert first.decision_record["decision"] == "APPROVE"
    assert first.is_approval
    assert first.idempotent_replay is False
    assert retry.idempotent_replay is True
    assert retry.decision_record["id"] == first.decision_record["id"]
    assert retry.nonce_state.value == "RESERVED_FOR_COMMIT"
    assert ledger.get_challenge(first.challenge_hash)[2].value == "RESERVED_FOR_COMMIT"


def test_nonce_cannot_be_submitted_under_a_second_idempotency_key(rig) -> None:
    authority, issued, private_key, _, _, _ = rig
    envelope = _signed_envelope(issued, private_key)
    authority.submit_decision(envelope, now=NOW + timedelta(seconds=3))

    replay = _signed_envelope(
        issued,
        private_key,
        idempotency_key="idem_fixture_2",
    )
    _assert_code(
        ApprovalErrorCode.REPLAY,
        lambda: authority.submit_decision(replay, now=NOW + timedelta(seconds=4)),
    )


def test_idempotency_key_cannot_alias_a_different_signed_decision(rig) -> None:
    authority, issued, private_key, _, _, _ = rig
    envelope = _signed_envelope(issued, private_key)
    authority.submit_decision(envelope, now=NOW + timedelta(seconds=3))
    changed = _signed_envelope(
        issued,
        private_key,
        decision="HOLD",
        idempotency_key="idem_fixture_1",
    )
    _assert_code(
        ApprovalErrorCode.IDEMPOTENCY_CONFLICT,
        lambda: authority.submit_decision(changed, now=NOW + timedelta(seconds=4)),
    )


def test_expired_challenge_is_rejected(rig) -> None:
    authority, issued, private_key, _, _, ledger = rig
    envelope = _signed_envelope(issued, private_key)
    _assert_code(
        ApprovalErrorCode.EXPIRED,
        lambda: authority.submit_decision(envelope, now=NOW + timedelta(seconds=121)),
    )
    assert ledger.get_challenge(issued.scoped_challenge["content_hash"])[2].value == "EXPIRED"


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("candidate_hash", "9" * 64, ApprovalErrorCode.CANDIDATE_CHANGED),
        ("expected_champion_hash", "9" * 64, ApprovalErrorCode.CHAMPION_CHANGED),
        ("expected_generation", 5, ApprovalErrorCode.CHAMPION_CHANGED),
        ("bundle_hash", "9" * 64, ApprovalErrorCode.BUNDLE_CHANGED),
        ("epoch_ref", "epoch", ApprovalErrorCode.EPOCH_CHANGED),
        ("policy_ref", "policy", ApprovalErrorCode.POLICY_CHANGED),
    ],
)
def test_exact_state_changes_reject_the_signed_decision(
    rig, field: str, value: object, expected: ApprovalErrorCode
) -> None:
    authority, issued, private_key, _, state, _ = rig
    snapshot = state.snapshot
    if field == "epoch_ref":
        snapshot = replace(snapshot, epoch_ref=replace(snapshot.epoch_ref, content_hash="9" * 64))
    elif field == "policy_ref":
        snapshot = replace(snapshot, policy_ref=replace(snapshot.policy_ref, content_hash="9" * 64))
    else:
        snapshot = replace(snapshot, **{field: value})
    state.snapshot = snapshot
    envelope = _signed_envelope(issued, private_key)
    _assert_code(
        expected,
        lambda: authority.submit_decision(envelope, now=NOW + timedelta(seconds=3)),
    )


def test_revoked_device_is_rejected_at_decision_submission(rig) -> None:
    authority, issued, private_key, identity, _, _ = rig
    authority.identity_provider.revoke_device(NOW + timedelta(seconds=2))
    envelope = _signed_envelope(issued, private_key)
    _assert_code(
        ApprovalErrorCode.IDENTITY_REVOKED,
        lambda: authority.submit_decision(envelope, now=NOW + timedelta(seconds=3)),
    )


def test_revoked_session_is_rejected_at_decision_submission(rig) -> None:
    authority, issued, private_key, _, _, _ = rig
    authority.identity_provider.revoke_session(NOW + timedelta(seconds=2))
    envelope = _signed_envelope(issued, private_key)
    _assert_code(
        ApprovalErrorCode.IDENTITY_REVOKED,
        lambda: authority.submit_decision(envelope, now=NOW + timedelta(seconds=3)),
    )


@pytest.mark.parametrize("decision", ["HOLD", "REJECT"])
def test_hold_and_reject_are_terminal_non_approval_decisions(rig, decision: str) -> None:
    authority, issued, private_key, _, _, ledger = rig
    envelope = _signed_envelope(issued, private_key, decision=decision)
    submission = authority.submit_decision(envelope, now=NOW + timedelta(seconds=3))

    assert submission.decision_record["decision"] == decision
    assert submission.is_approval is False
    assert submission.nonce_state.value == "CONSUMED_NO_TRANSITION"
    check = authority.recheck_for_commit(
        submission.decision_record["id"], now=NOW + timedelta(seconds=4)
    )
    assert check.action_authorized is False
    assert check.reason_code == ApprovalErrorCode.DECISION_NOT_APPROVAL.value
    assert ledger.get_challenge(submission.challenge_hash)[2].value == "CONSUMED_NO_TRANSITION"


def test_fixture_approval_never_authorizes_a_real_action(rig) -> None:
    authority, issued, private_key, _, _, _ = rig
    submission = authority.submit_decision(
        _signed_envelope(issued, private_key),
        now=NOW + timedelta(seconds=3),
    )
    check = authority.recheck_for_commit(
        submission.decision_record["id"], now=NOW + timedelta(seconds=4)
    )

    assert PRODUCTION_APPROVAL_ENABLED is False
    assert check.checks_passed is True
    assert check.action_authorized is False
    assert check.reason_code == ApprovalErrorCode.REAL_AUTHORITY_DISABLED.value


def test_commit_time_recheck_observes_later_revocation(rig) -> None:
    authority, issued, private_key, _, _, _ = rig
    submission = authority.submit_decision(
        _signed_envelope(issued, private_key),
        now=NOW + timedelta(seconds=3),
    )
    authority.identity_provider.revoke_device(NOW + timedelta(seconds=4))

    check = authority.recheck_for_commit(
        submission.decision_record["id"], now=NOW + timedelta(seconds=5)
    )
    assert check.checks_passed is False
    assert check.action_authorized is False
    assert check.reason_code == ApprovalErrorCode.IDENTITY_REVOKED.value


def test_commit_time_recheck_rejects_changed_champion_generation(rig) -> None:
    authority, issued, private_key, _, state, _ = rig
    submission = authority.submit_decision(
        _signed_envelope(issued, private_key),
        now=NOW + timedelta(seconds=3),
    )
    state.snapshot = replace(state.snapshot, expected_generation=5)

    check = authority.recheck_for_commit(
        submission.decision_record["id"], now=NOW + timedelta(seconds=4)
    )
    assert check.checks_passed is False
    assert check.reason_code == ApprovalErrorCode.CHAMPION_CHANGED.value


def test_approval_expires_before_commit_and_nonce_becomes_terminal(rig) -> None:
    authority, issued, private_key, _, _, ledger = rig
    submission = authority.submit_decision(
        _signed_envelope(issued, private_key),
        now=NOW + timedelta(seconds=3),
    )

    check = authority.recheck_for_commit(
        submission.decision_record["id"], now=NOW + timedelta(seconds=121)
    )
    assert check.checks_passed is False
    assert check.reason_code == ApprovalErrorCode.EXPIRED.value
    assert ledger.get_challenge(submission.challenge_hash)[2].value == "EXPIRED"


@pytest.mark.parametrize(
    ("field", "value"),
    [("domain", "epoch"), ("action", "EPOCH_ACTIVATION")],
)
def test_decision_cannot_be_reused_for_another_domain_or_action(
    rig, field: str, value: str
) -> None:
    authority, issued, private_key, _, _, _ = rig
    envelope = _signed_envelope(issued, private_key)
    envelope[field] = value
    _assert_code(
        ApprovalErrorCode.INVALID_INPUT,
        lambda: authority.submit_decision(envelope, now=NOW + timedelta(seconds=3)),
    )


def test_invalid_signature_is_rejected(rig) -> None:
    authority, issued, private_key, _, _, _ = rig
    envelope = _signed_envelope(issued, private_key)
    envelope["signature"] = _b64url(b"not-a-valid-ecdsa-signature")
    _assert_code(
        ApprovalErrorCode.INVALID_SIGNATURE,
        lambda: authority.submit_decision(envelope, now=NOW + timedelta(seconds=3)),
    )


def test_environment_is_an_independently_bound_scope_field(rig) -> None:
    authority, issued, private_key, _, _, _ = rig
    envelope = _signed_envelope(issued, private_key)
    envelope["environment_namespace"] = "development"
    envelope["signature"] = _b64url(
        private_key.sign(
            decision_signing_bytes(envelope),
            ec.ECDSA(hashes.SHA256()),
        )
    )
    _assert_code(
        ApprovalErrorCode.SCOPE_MISMATCH,
        lambda: authority.submit_decision(envelope, now=NOW + timedelta(seconds=3)),
    )


def test_production_challenge_creation_is_hard_disabled(rig) -> None:
    _, _, _, identity, state, _ = rig
    authority = ApprovalAuthority(
        identity_provider=FixtureIdentityProvider(identity),
        state_reader=state,
        ledger=InMemoryApprovalLedger(),
        environment_namespace="production",
        max_challenge_lifetime_seconds=300,
    )
    _assert_code(
        ApprovalErrorCode.REAL_AUTHORITY_DISABLED,
        lambda: authority.issue_challenge(
            request_id=state.snapshot.request_ref.target_id,
            owner_session_id=identity.session_record["id"],
            ttl_seconds=60,
            now=NOW,
        ),
    )


@pytest.mark.parametrize("ttl", [0, 301, True])
def test_challenge_lifetime_requires_a_bounded_integer(rig, ttl: object) -> None:
    authority, issued, _, _, _, _ = rig
    _assert_code(
        ApprovalErrorCode.INVALID_INPUT,
        lambda: authority.issue_challenge(
            request_id=issued.promotion_challenge["request_ref"]["target_id"],
            owner_session_id=issued.scoped_challenge["owner_session_ref"]["target_id"],
            ttl_seconds=ttl,
            now=NOW,
        ),
    )


def test_nonfixture_identity_is_disabled_even_in_test_environment(rig) -> None:
    authority, issued, _, _, _, _ = rig
    authority.identity_provider.binding = replace(
        authority.identity_provider.binding, fixture_identity=False
    )
    _assert_code(
        ApprovalErrorCode.REAL_AUTHORITY_DISABLED,
        lambda: authority.issue_challenge(
            request_id=issued.promotion_challenge["request_ref"]["target_id"],
            owner_session_id=issued.scoped_challenge["owner_session_ref"]["target_id"],
            ttl_seconds=60,
            now=NOW,
        ),
    )
