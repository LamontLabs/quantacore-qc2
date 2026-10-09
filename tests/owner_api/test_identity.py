from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from qc2_owner_api.identity import (
    IdentityAuthority,
    IdentityAuthorityError,
    IdentityErrorCode,
    IdentityPolicy,
    InMemoryIdentityRepository,
    new_offline_secret,
    _token_hash,
)

NOW = datetime(2026, 10, 9, 17, 0, tzinfo=UTC)
POLICY = IdentityPolicy(
    enrollment_challenge_lifetime_seconds=300,
    command_challenge_lifetime_seconds=90,
    recovery_challenge_lifetime_seconds=600,
    access_session_lifetime_seconds=900,
    refresh_credential_lifetime_seconds=86_400,
    initial_scope_refs=(
        "OWNER_READ",
        "PROMOTION",
        "EPOCH_ACTIVATION",
        "PAUSE",
        "RESUME",
        "ALERT",
        "DEVICE_ADMIN",
    ),
    recovery_scope_refs=("OWNER_READ", "DEVICE_ADMIN"),
)


def _key_pair() -> tuple[ec.EllipticCurvePrivateKey, bytes]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_der


def _sign(private_key: ec.EllipticCurvePrivateKey, message: bytes) -> bytes:
    return private_key.sign(message, ec.ECDSA(hashes.SHA256()))


def _rig() -> tuple[InMemoryIdentityRepository, IdentityAuthority, str]:
    repository = InMemoryIdentityRepository()
    bootstrap_secret = new_offline_secret()
    repository.provision_fixture_bootstrap(
        environment_namespace="test",
        owner_binding="primary_owner",
        bootstrap_verifier_hash=_token_hash(
            bootstrap_secret, "qc2.owner.bootstrap.v1"
        ),
    )
    authority = IdentityAuthority(
        repository=repository,
        environment_namespace="test",
        policy=POLICY,
    )
    return repository, authority, bootstrap_secret


def _enroll(
    authority: IdentityAuthority,
    bootstrap_secret: str,
    private_key: ec.EllipticCurvePrivateKey,
    public_der: bytes,
    *,
    now: datetime = NOW,
):
    challenge = authority.issue_bootstrap_challenge(
        bootstrap_secret=bootstrap_secret,
        owner_key_id="primary_key",
        public_key_der=public_der,
        app_version="test-1",
        now=now,
        claimed_security_level="UNKNOWN",
    )
    tokens = authority.complete_bootstrap_enrollment(
        challenge_id=challenge.challenge["challenge_id"],
        bootstrap_secret=bootstrap_secret,
        signature=_sign(private_key, challenge.signing_bytes),
        now=now + timedelta(seconds=1),
    )
    return challenge, tokens


def test_bootstrap_binds_public_key_is_single_use_and_keeps_security_unknown() -> None:
    repository, authority, secret = _rig()
    owner_key, owner_public = _key_pair()
    wrong_key, _ = _key_pair()
    with pytest.raises(IdentityAuthorityError) as unverified_claim:
        authority.issue_bootstrap_challenge(
            bootstrap_secret=secret,
            owner_key_id="primary_key",
            public_key_der=owner_public,
            app_version="test-1",
            now=NOW,
            claimed_security_level="STRONGBOX",
        )
    assert unverified_claim.value.code is IdentityErrorCode.INVALID_SECURITY_EVIDENCE
    challenge = authority.issue_bootstrap_challenge(
        bootstrap_secret=secret,
        owner_key_id="primary_key",
        public_key_der=owner_public,
        app_version="test-1",
        now=NOW,
    )
    with pytest.raises(IdentityAuthorityError) as invalid_signature:
        authority.complete_bootstrap_enrollment(
            challenge_id=challenge.challenge["challenge_id"],
            bootstrap_secret=secret,
            signature=_sign(wrong_key, challenge.signing_bytes),
            now=NOW + timedelta(seconds=1),
        )
    assert invalid_signature.value.code is IdentityErrorCode.INVALID_SIGNATURE

    tokens = authority.complete_bootstrap_enrollment(
        challenge_id=challenge.challenge["challenge_id"],
        bootstrap_secret=secret,
        signature=_sign(owner_key, challenge.signing_bytes),
        now=NOW + timedelta(seconds=1),
    )
    assert repository.status("test").owner_binding == "primary_owner"
    enrolled_device = repository.status("test").enrolled_devices[0]
    assert enrolled_device["security_level"] == "UNKNOWN"
    assert tokens.session_record["device_ref"]["target_id"]

    with pytest.raises(IdentityAuthorityError) as replay:
        authority.complete_bootstrap_enrollment(
            challenge_id=challenge.challenge["challenge_id"],
            bootstrap_secret=secret,
            signature=_sign(owner_key, challenge.signing_bytes),
            now=NOW + timedelta(seconds=2),
        )
    assert replay.value.code is IdentityErrorCode.REPLAY
    assert repository.bootstrap_state("test")["bootstrap_consumed"] is True


def test_bootstrap_checks_expiry_again_at_completion_time() -> None:
    _, authority, secret = _rig()
    owner_key, owner_public = _key_pair()
    challenge = authority.issue_bootstrap_challenge(
        bootstrap_secret=secret,
        owner_key_id="primary_key",
        public_key_der=owner_public,
        app_version="test-1",
        now=NOW,
        ttl_seconds=1,
    )

    with pytest.raises(IdentityAuthorityError) as expired:
        authority.complete_bootstrap_enrollment(
            challenge_id=challenge.challenge["challenge_id"],
            bootstrap_secret=secret,
            signature=_sign(owner_key, challenge.signing_bytes),
            now=NOW + timedelta(seconds=1),
        )
    assert expired.value.code is IdentityErrorCode.EXPIRED


def test_additional_enrollment_requires_both_owner_and_candidate_signatures() -> None:
    _, authority, secret = _rig()
    owner_key, owner_public = _key_pair()
    _, owner_tokens = _enroll(authority, secret, owner_key, owner_public)
    candidate_key, candidate_public = _key_pair()
    challenge = authority.issue_additional_device_challenge(
        access_token=owner_tokens.access_token,
        owner_key_id="travel_key",
        candidate_public_key_der=candidate_public,
        app_version="test-1",
        scope_refs=("OWNER_READ", "DEVICE_ADMIN"),
        now=NOW + timedelta(seconds=2),
    )
    owner_signature = _sign(owner_key, challenge.signing_bytes)

    with pytest.raises(IdentityAuthorityError) as bad_candidate:
        authority.complete_additional_device_enrollment(
            access_token=owner_tokens.access_token,
            challenge_id=challenge.challenge["id"],
            owner_signature=owner_signature,
            candidate_signature=_sign(owner_key, challenge.signing_bytes),
            now=NOW + timedelta(seconds=3),
        )
    assert bad_candidate.value.code is IdentityErrorCode.INVALID_SIGNATURE

    additional = authority.complete_additional_device_enrollment(
        access_token=owner_tokens.access_token,
        challenge_id=challenge.challenge["id"],
        owner_signature=owner_signature,
        candidate_signature=_sign(candidate_key, challenge.signing_bytes),
        now=NOW + timedelta(seconds=3),
    )
    assert additional.session_record["scope_refs"] == ["OWNER_READ", "DEVICE_ADMIN"]
    assert additional.session_record["device_ref"]["target_id"] != owner_tokens.session_record[
        "device_ref"
    ]["target_id"]


def test_refresh_rotation_consumes_previous_credential_and_replay_revokes_family() -> None:
    _, authority, secret = _rig()
    owner_key, owner_public = _key_pair()
    _, original = _enroll(authority, secret, owner_key, owner_public)

    rotated = authority.refresh_session(
        refresh_token=original.refresh_token,
        now=NOW + timedelta(seconds=2),
    )
    assert rotated.session_record["session_id"] == original.session_record["session_id"]
    assert rotated.session_record["refresh_generation"] == 2
    with pytest.raises(IdentityAuthorityError) as old_access:
        authority.repository.resolve_access(
            "test",
            _token_hash(original.access_token, "qc2.owner.access.v1"),
            now=NOW + timedelta(seconds=3),
        )
    assert old_access.value.code is IdentityErrorCode.INVALID_IDENTITY

    with pytest.raises(IdentityAuthorityError) as replay:
        authority.refresh_session(
            refresh_token=original.refresh_token,
            now=NOW + timedelta(seconds=4),
        )
    assert replay.value.code is IdentityErrorCode.REFRESH_REPLAY
    with pytest.raises(IdentityAuthorityError) as revoked_new_access:
        authority.repository.resolve_access(
            "test",
            _token_hash(rotated.access_token, "qc2.owner.access.v1"),
            now=NOW + timedelta(seconds=5),
        )
    assert revoked_new_access.value.code is IdentityErrorCode.INVALID_IDENTITY


def test_signed_command_rechecks_device_state_after_challenge_issuance() -> None:
    _, authority, secret = _rig()
    owner_key, owner_public = _key_pair()
    _, tokens = _enroll(authority, secret, owner_key, owner_public)
    device_id = tokens.session_record["device_ref"]["target_id"]
    pending = authority.issue_signed_command_challenge(
        access_token=tokens.access_token,
        command_type="PAUSE_NEW_ENTRIES",
        request_body={
            "schema_name": "qc2.owner_api.OwnerCommandRequest.v1",
            "schema_version": "1.0",
            "command_type": "PAUSE_NEW_ENTRIES",
            "payload": {"expected_generation": 0, "reason_code": "test"},
        },
        idempotency_key="pause-test",
        now=NOW + timedelta(seconds=2),
    )
    revoke = authority.issue_signed_command_challenge(
        access_token=tokens.access_token,
        command_type="DEVICE_ACTION",
        request_body={
            "schema_name": "qc2.owner_api.OwnerCommandRequest.v1",
            "schema_version": "1.0",
            "command_type": "DEVICE_ACTION",
            "payload": {"action": "REVOKE_DEVICE", "device_id": device_id},
        },
        idempotency_key="revoke-primary",
        now=NOW + timedelta(seconds=2),
    )
    authority.revoke_device(
        access_token=tokens.access_token,
        challenge_id=revoke.challenge["id"],
        device_id=device_id,
        signature=_sign(owner_key, revoke.signing_bytes),
        now=NOW + timedelta(seconds=3),
    )

    with pytest.raises(IdentityAuthorityError) as revoked:
        authority.submit_signed_command(
            access_token=tokens.access_token,
            challenge_id=pending.challenge["id"],
            request_body={
                "schema_name": "qc2.owner_api.OwnerCommandRequest.v1",
                "schema_version": "1.0",
                "command_type": "PAUSE_NEW_ENTRIES",
                "payload": {"expected_generation": 0, "reason_code": "test"},
            },
            signature=_sign(owner_key, pending.signing_bytes),
            now=NOW + timedelta(seconds=4),
        )
    assert revoked.value.code in {
        IdentityErrorCode.INVALID_IDENTITY,
        IdentityErrorCode.IDENTITY_REVOKED,
    }


def test_owner_command_request_bodies_are_versioned_and_allowlisted() -> None:
    challenge_ref = {
        "target_schema_name": "qc2.governance_owner.PromotionChallenge.v1",
        "target_id": "00000000-0000-7000-8000-000000000001",
        "content_hash": "a" * 64,
    }
    epoch_ref = {
        "target_schema_name": "qc2.governance_owner.EpochActivationChallenge.v1",
        "target_id": "00000000-0000-7000-8000-000000000002",
        "content_hash": "b" * 64,
    }
    alert_ref = {
        "target_schema_name": "qc2.governance_owner.Alert.v1",
        "target_id": "00000000-0000-7000-8000-000000000003",
    }
    command_requests = {
        "PROMOTION": {
            "challenge_ref": challenge_ref,
            "decision": "APPROVE",
            "request_hash": "c" * 64,
        },
        "EPOCH_ACTIVATION": {
            "challenge_ref": epoch_ref,
            "epoch_manifest_hash": "d" * 64,
            "decision": "APPROVE",
        },
        "PAUSE_NEW_ENTRIES": {
            "expected_generation": 0,
            "reason_code": "operator_request",
        },
        "RESUME_REQUEST": {"expected_pause_generation": 1},
        "ACKNOWLEDGE_ALERT": {
            "alert_ref": alert_ref,
            "expected_projection_sequence": 12,
        },
        "DEVICE_ACTION": {
            "action": "REVOKE_DEVICE",
            "device_id": "00000000-0000-7000-8000-000000000004",
        },
    }
    for command_type, payload in command_requests.items():
        IdentityAuthority._validate_command_body(
            command_type,
            {
                "schema_name": "qc2.owner_api.OwnerCommandRequest.v1",
                "schema_version": "1.0",
                "command_type": command_type,
                "payload": payload,
            },
        )

    forbidden_bodies = [
        {
            "schema_name": "qc2.owner_api.OwnerCommandRequest.v1",
            "schema_version": "1.0",
            "command_type": "PROMOTION",
            "payload": {
                "challenge_ref": challenge_ref,
                "decision": "FORCE_PROMOTE",
                "request_hash": "c" * 64,
            },
        },
        {
            "schema_name": "qc2.owner_api.OwnerCommandRequest.v1",
            "schema_version": "1.0",
            "command_type": "PAUSE_NEW_ENTRIES",
            "payload": {
                "expected_generation": 0,
                "reason_code": "operator_request",
                "safety_override": True,
            },
        },
        {"action": "BUY", "symbol": "TEST"},
    ]
    command_types = ["PROMOTION", "PAUSE_NEW_ENTRIES", "DEVICE_ACTION"]
    for command_type, body in zip(command_types, forbidden_bodies, strict=True):
        with pytest.raises(IdentityAuthorityError) as rejected:
            IdentityAuthority._validate_command_body(command_type, body)
        assert rejected.value.code is IdentityErrorCode.INVALID_INPUT


def test_recovery_revokes_prior_credentials_sets_holds_and_restricts_replacement() -> None:
    repository, authority, secret = _rig()
    owner_key, owner_public = _key_pair()
    _, original = _enroll(authority, secret, owner_key, owner_public)
    replacement_key, replacement_public = _key_pair()
    recovery = authority.issue_recovery_challenge(
        recovery_material=original.recovery_material or "",
        replacement_key_id="recovery_key",
        replacement_public_key_der=replacement_public,
        app_version="test-2",
        now=NOW + timedelta(seconds=2),
    )
    replacement = authority.complete_recovery(
        challenge_id=recovery.challenge["id"],
        recovery_material=original.recovery_material or "",
        signature=_sign(replacement_key, recovery.signing_bytes),
        now=NOW + timedelta(seconds=3),
    )

    status = authority.status()
    assert status.promotion_hold is True
    assert status.entry_hold is True
    assert status.reconciliation_required is True
    assert replacement.session_record["scope_refs"] == ["OWNER_READ", "DEVICE_ADMIN"]
    assert len(repository._owners["test"].recovery_events) == 1
    with pytest.raises(IdentityAuthorityError) as old_access:
        authority.repository.resolve_access(
            "test",
            _token_hash(original.access_token, "qc2.owner.access.v1"),
            now=NOW + timedelta(seconds=4),
        )
    assert old_access.value.code is IdentityErrorCode.INVALID_IDENTITY

    with pytest.raises(IdentityAuthorityError) as restricted_scope:
        authority.issue_signed_command_challenge(
            access_token=replacement.access_token,
            command_type="PAUSE_NEW_ENTRIES",
            request_body={
                "schema_name": "qc2.owner_api.OwnerCommandRequest.v1",
                "schema_version": "1.0",
                "command_type": "PAUSE_NEW_ENTRIES",
                "payload": {
                    "expected_generation": 0,
                    "reason_code": "recovery_pause",
                },
            },
            idempotency_key="recovery-pause",
            now=NOW + timedelta(seconds=4),
        )
    assert restricted_scope.value.code is IdentityErrorCode.SCOPE_MISMATCH
    with pytest.raises(IdentityAuthorityError) as used_recovery_material:
        authority.issue_recovery_challenge(
            recovery_material=original.recovery_material or "",
            replacement_key_id="second_recovery_key",
            replacement_public_key_der=replacement_public,
            app_version="test-2",
            now=NOW + timedelta(seconds=4),
        )
    assert used_recovery_material.value.code is IdentityErrorCode.RECOVERY_DENIED


def test_in_memory_identity_repository_is_test_environment_only() -> None:
    with pytest.raises(IdentityAuthorityError) as fixture_only:
        IdentityAuthority(
            repository=InMemoryIdentityRepository(),
            environment_namespace="development",
            policy=POLICY,
        )
    assert fixture_only.value.code is IdentityErrorCode.FIXTURE_ONLY
