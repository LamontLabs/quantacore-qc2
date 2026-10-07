from __future__ import annotations

import asyncio
import hashlib
from copy import deepcopy
from typing import Any, Mapping

import pytest

from qc2_contracts.runtime import (
    artifact_inventory_hash,
    canonical_content_hash,
    canonical_json_bytes,
    domain_separated_sha256,
)
from qc2_integrity_build.verification import (
    CHECKPOINT_ARTIFACT_ROOT_DOMAIN,
    CHECKPOINT_HASH_DOMAIN,
    EVENT_HASH_DOMAIN,
    LOCAL_PROOF_LEVEL,
    PAYLOAD_HASH_DOMAIN,
    ArtifactObject,
    AnchorPort,
    CheckpointRecord,
    EvidenceEventRecord,
    ExternalCheckpoint,
    VerificationStatus,
    assess_anchor_receipt,
    compare_independent_checkpoint,
    verify_artifact_inventory,
    verify_checkpoint_chain,
    verify_evidence_scan,
)

UUIDS = [
    "018f0000-0000-7000-8000-000000000001",
    "018f0000-0000-7000-8000-000000000002",
    "018f0000-0000-7000-8000-000000000003",
    "018f0000-0000-7000-8000-000000000004",
]


def make_event(
    sequence: int,
    previous_hash: str | None,
    *,
    event_id: str | None = None,
    payload: dict[str, Any] | None = None,
    source_refs: list[dict[str, Any]] | None = None,
) -> EvidenceEventRecord:
    event_id = event_id or (
        UUIDS[sequence - 1]
        if sequence <= len(UUIDS)
        else f"018f0000-0000-7{sequence:03x}-8000-{sequence:012x}"
    )
    payload = payload or {
        "installation_id": "fixture-installation",
        "stream_id": "fixture-stream",
        "sequence": sequence,
    }
    payload_bytes = canonical_json_bytes(payload)
    payload_hash = domain_separated_sha256(PAYLOAD_HASH_DOMAIN, payload_bytes)
    created_at = f"2026-10-07T20:00:{sequence % 60:02d}Z"
    body: dict[str, Any] = {
        "schema_name": "qc2.integrity_build.EvidenceEvent.v1",
        "schema_version": "1.0",
        "id": event_id,
        "created_at": created_at,
        "owning_authority": "evidence",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": source_refs or [],
        "installation_id": "fixture-installation",
        "stream_id": "fixture-stream",
        "sequence": sequence,
        "event_type": "stream_genesis" if sequence == 1 else "fixture_mutation",
        "actor_identity": "evidence" if sequence == 1 else "execution",
        "authorized_command_ref": None,
        "correlation_id": f"fixture-{sequence}",
        "payload_hash": payload_hash,
        "dependency_refs": [],
        "previous_event_hash": previous_hash,
        "wall_clock_at": created_at,
        "monotonic_generation": 0,
    }
    event_hash = domain_separated_sha256(
        EVENT_HASH_DOMAIN,
        canonical_json_bytes(body),
    )
    event = {
        **body,
        "event_hash": event_hash,
        "content_hash": "0" * 64,
    }
    event["content_hash"] = canonical_content_hash("EvidenceEvent", event)
    return EvidenceEventRecord(event, payload_bytes)


def make_checkpoint(
    sequence: int,
    head_hash: str,
    *,
    checkpoint_id: str,
    previous_checkpoint_hash: str | None,
    artifact_refs: list[dict[str, Any]] | None = None,
) -> CheckpointRecord:
    refs = artifact_refs or []
    ordered_refs = sorted(refs, key=lambda ref: ref["target_id"].encode("utf-8"))
    created_at = f"2026-10-07T20:10:0{sequence}Z"
    artifact_root = domain_separated_sha256(
        CHECKPOINT_ARTIFACT_ROOT_DOMAIN,
        canonical_json_bytes(ordered_refs),
    )
    checkpoint: dict[str, Any] = {
        "schema_name": "qc2.integrity_build.Checkpoint.v1",
        "schema_version": "1.0",
        "id": checkpoint_id,
        "created_at": created_at,
        "owning_authority": "evidence",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": ordered_refs,
        "stream_id": "fixture-stream",
        "head_sequence": sequence,
        "head_hash": head_hash,
        "event_count": sequence,
        "artifact_root_hash": artifact_root,
        "checkpoint_hash": "0" * 64,
        "content_hash": "0" * 64,
    }
    checkpoint["checkpoint_hash"] = domain_separated_sha256(
        CHECKPOINT_HASH_DOMAIN,
        canonical_json_bytes(
            {
                key: value
                for key, value in checkpoint.items()
                if key not in {"checkpoint_hash", "content_hash"}
            }
        ),
    )
    checkpoint["content_hash"] = canonical_content_hash("Checkpoint", checkpoint)
    return CheckpointRecord(checkpoint, ordered_refs, previous_checkpoint_hash)


def make_manifest(data: bytes = b"fixture artifact") -> dict[str, Any]:
    files = [
        {
            "relative_path": "reports/summary.json",
            "length_bytes": len(data),
            "media_type": "application/json",
            "schema_name": "FixtureReport",
            "schema_version": "1.0",
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    ]
    manifest = {
        "schema_name": "qc2.integrity_build.ArtifactManifest.v1",
        "schema_version": "1.0",
        "id": UUIDS[0],
        "created_at": "2026-10-07T20:00:00Z",
        "owning_authority": "model_registry",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        "content_hash": "0" * 64,
        "manifest_version": 1,
        "files": files,
        "inventory_hash": artifact_inventory_hash(files),
        "detached_signature": None,
        "transport_hash": None,
    }
    manifest["content_hash"] = canonical_content_hash("ArtifactManifest", manifest)
    return manifest


def complete_head(events: list[EvidenceEventRecord]) -> dict[str, Any]:
    tail = events[-1].event_contract
    return {
        "stream_id": tail["stream_id"],
        "installation_id": tail["installation_id"],
        "environment_namespace": tail["environment_namespace"],
        "head_sequence": tail["sequence"],
        "head_event_hash": tail["event_hash"],
        "event_count": tail["sequence"],
    }


def event_fixture(count: int = 3) -> list[EvidenceEventRecord]:
    events: list[EvidenceEventRecord] = []
    previous_hash = None
    for sequence in range(1, count + 1):
        record = make_event(sequence, previous_hash)
        events.append(record)
        previous_hash = record.event_contract["event_hash"]
    return events


def test_concurrent_fixture_appends_produce_one_gap_free_chain() -> None:
    async def run() -> list[EvidenceEventRecord]:
        lock = asyncio.Lock()
        events: list[EvidenceEventRecord] = []

        async def append() -> None:
            async with lock:
                sequence = len(events) + 1
                previous_hash = (
                    events[-1].event_contract["event_hash"] if events else None
                )
                events.append(make_event(sequence, previous_hash))

        await asyncio.gather(*(append() for _ in range(24)))
        return events

    events = asyncio.run(run())
    result = verify_evidence_scan(events, complete_head(events), scan_complete=True)
    assert result.status is VerificationStatus.FULL_VERIFIED
    assert result.checked_count == 24
    assert result.proof_level == LOCAL_PROOF_LEVEL


def test_full_event_scan_checks_content_payload_and_chain_hashes() -> None:
    events = event_fixture()
    result = verify_evidence_scan(events, complete_head(events), scan_complete=True)
    assert result.status is VerificationStatus.FULL_VERIFIED
    assert result.passes


@pytest.mark.parametrize(
    "mutation",
    ["edit", "delete", "reorder", "truncate", "payload-corruption"],
)
def test_hostile_event_changes_never_pass(mutation: str) -> None:
    events = event_fixture()
    head = complete_head(events)
    if mutation == "edit":
        altered = deepcopy(events)
        altered[1].event_contract["actor_identity"] = "evidence"
        events = altered
    elif mutation == "delete":
        events = [events[0], events[2]]
    elif mutation == "reorder":
        events = [events[0], events[2], events[1]]
    elif mutation == "truncate":
        events = events[:2]
    elif mutation == "payload-corruption":
        altered = list(events)
        altered[1] = EvidenceEventRecord(
            altered[1].event_contract,
            b'{"sequence":2,"stream_id":"fixture-stream","installation_id":"changed"}',
        )
        events = altered

    result = verify_evidence_scan(events, head, scan_complete=True)
    assert result.status is VerificationStatus.FAILED
    assert not result.passes


def test_incomplete_scan_is_partial_and_unavailable_store_is_not_pass() -> None:
    events = event_fixture()
    partial = verify_evidence_scan(
        events[:2],
        complete_head(events),
        scan_complete=False,
    )
    unavailable = verify_evidence_scan(
        [],
        None,
        scan_complete=False,
        available=False,
    )
    assert partial.status is VerificationStatus.PARTIAL_SCAN
    assert not partial.passes
    assert unavailable.status is VerificationStatus.UNAVAILABLE
    assert not unavailable.passes


def test_referenced_evidence_objects_must_be_inventoried() -> None:
    reference = {
        "target_schema_name": "qc2.integrity_build.ArtifactManifest.v1",
        "target_id": UUIDS[3],
        "content_hash": "d" * 64,
    }
    first = make_event(1, None, source_refs=[reference])
    second = make_event(2, first.event_contract["event_hash"])
    events = [first, second]
    head = complete_head(events)
    not_inventoried = verify_evidence_scan(
        events,
        head,
        scan_complete=True,
    )
    missing = verify_evidence_scan(
        events,
        head,
        scan_complete=True,
        verified_references=set(),
    )
    verified = verify_evidence_scan(
        events,
        head,
        scan_complete=True,
        verified_references={
            (
                reference["target_schema_name"],
                reference["target_id"],
                reference["content_hash"],
            )
        },
    )
    assert not_inventoried.status is VerificationStatus.PARTIAL_SCAN
    assert missing.status is VerificationStatus.FAILED
    assert verified.status is VerificationStatus.FULL_VERIFIED


def test_checkpoints_bind_artifact_roots_and_form_a_continuous_chain() -> None:
    events = event_fixture()
    first = make_checkpoint(
        2,
        events[1].event_contract["event_hash"],
        checkpoint_id=UUIDS[1],
        previous_checkpoint_hash=None,
    )
    second = make_checkpoint(
        3,
        events[2].event_contract["event_hash"],
        checkpoint_id=UUIDS[2],
        previous_checkpoint_hash=first.checkpoint_contract["checkpoint_hash"],
    )
    result = verify_checkpoint_chain([first, second])
    assert result.status is VerificationStatus.FULL_VERIFIED

    tampered = deepcopy(second.checkpoint_contract)
    tampered["artifact_root_hash"] = "f" * 64
    bad_chain = [
        first,
        CheckpointRecord(
            tampered,
            second.artifact_refs,
            first.checkpoint_contract["checkpoint_hash"],
        ),
    ]
    assert verify_checkpoint_chain(bad_chain).status is VerificationStatus.FAILED


def test_checkpoint_artifact_refs_require_a_verified_inventory() -> None:
    reference = {
        "target_schema_name": "qc2.integrity_build.ArtifactManifest.v1",
        "target_id": UUIDS[3],
        "content_hash": "e" * 64,
    }
    checkpoint = make_checkpoint(
        1,
        "f" * 64,
        checkpoint_id=UUIDS[0],
        previous_checkpoint_hash=None,
        artifact_refs=[reference],
    )
    not_inventoried = verify_checkpoint_chain([checkpoint])
    missing = verify_checkpoint_chain([checkpoint], verified_references=set())
    verified = verify_checkpoint_chain(
        [checkpoint],
        verified_references={
            (
                reference["target_schema_name"],
                reference["target_id"],
                reference["content_hash"],
            )
        },
    )
    assert not_inventoried.status is VerificationStatus.PARTIAL_SCAN
    assert missing.status is VerificationStatus.FAILED
    assert verified.status is VerificationStatus.FULL_VERIFIED


def test_complete_artifact_inventory_verifies_every_object() -> None:
    data = b"fixture artifact"
    manifest = make_manifest(data)
    result = verify_artifact_inventory(
        manifest,
        [
            ArtifactObject(
                "reports/summary.json",
                data,
                media_type="application/json",
            )
        ],
        listing_complete=True,
    )
    assert result.status is VerificationStatus.FULL_VERIFIED
    assert result.checked_count == 1


@pytest.mark.parametrize(
    ("objects", "complete", "expected"),
    [
        ([ArtifactObject("reports/summary.json", b"corrupt")], True, VerificationStatus.FAILED),
        ([ArtifactObject("reports/extra.json", b"extra")], True, VerificationStatus.FAILED),
        ([ArtifactObject("reports/summary.json", b"fixture artifact", kind="symlink")], True, VerificationStatus.FAILED),
        ([ArtifactObject("reports/summary.json", b"fixture artifact", executable=True)], True, VerificationStatus.FAILED),
        ([], False, VerificationStatus.PARTIAL_SCAN),
        ([ArtifactObject("reports/summary.json", None)], True, VerificationStatus.PARTIAL_SCAN),
    ],
)
def test_corrupt_unexpected_unsafe_and_incomplete_artifacts(
    objects: list[ArtifactObject],
    complete: bool,
    expected: VerificationStatus,
) -> None:
    result = verify_artifact_inventory(
        make_manifest(),
        objects,
        listing_complete=complete,
    )
    assert result.status is expected
    assert not result.passes


def test_independent_checkpoint_detects_coordinated_local_rollback() -> None:
    events = event_fixture()
    latest = events[-1].event_contract
    external = ExternalCheckpoint(
        stream_id=latest["stream_id"],
        evidence_class=latest["evidence_class"],
        checkpoint_hash="b" * 64,
        head_sequence=3,
        head_hash=latest["event_hash"],
        event_count=3,
        externally_verified=True,
    )
    rolled_back = complete_head(events[:2])
    result = compare_independent_checkpoint(external, rolled_back)
    assert result.status is VerificationStatus.FAILED
    assert not result.passes


def test_synthetic_exact_head_match_keeps_local_proof_label() -> None:
    events = event_fixture()
    tail = events[-1].event_contract
    external = ExternalCheckpoint(
        stream_id=tail["stream_id"],
        evidence_class=tail["evidence_class"],
        checkpoint_hash="c" * 64,
        head_sequence=3,
        head_hash=tail["event_hash"],
        event_count=3,
        externally_verified=True,
    )
    local_verification = verify_evidence_scan(
        events,
        complete_head(events),
        scan_complete=True,
    )
    result = compare_independent_checkpoint(
        external,
        complete_head(events),
        local_verification=local_verification,
    )
    assert result.status is VerificationStatus.FULL_VERIFIED
    assert result.proof_level == LOCAL_PROOF_LEVEL


def test_missing_anchor_receipt_cannot_upgrade_synthetic_evidence() -> None:
    class NoAnchorConfigured(AnchorPort):
        async def submit_checkpoint(
            self,
            checkpoint: Mapping[str, Any],
        ) -> Mapping[str, Any]:
            raise AssertionError("synthetic evidence must not call an anchor provider")

        async def verify_receipt(
            self,
            checkpoint: Mapping[str, Any],
            receipt: Mapping[str, Any],
        ) -> bool:
            raise AssertionError("no receipt is available to verify")

    events = event_fixture()
    checkpoint = make_checkpoint(
        3,
        events[-1].event_contract["event_hash"],
        checkpoint_id=UUIDS[3],
        previous_checkpoint_hash=None,
    )

    def assess(
        checkpoint_contract: Mapping[str, Any],
        *,
        verified_references: set[tuple[str, str, str]] | None = None,
    ):
        return asyncio.run(
            assess_anchor_receipt(
                checkpoint_contract,
                None,
                NoAnchorConfigured(),
                qualification_deadline="2026-10-07T21:00:00Z",
                next_outcome_session_start="2026-10-08T13:30:00Z",
                verified_references=verified_references,
            )
        )

    result = assess(checkpoint.checkpoint_contract)
    assert result.status is VerificationStatus.FULL_VERIFIED
    assert result.proof_level == LOCAL_PROOF_LEVEL

    corrupt_checkpoint = deepcopy(checkpoint.checkpoint_contract)
    corrupt_checkpoint["checkpoint_hash"] = "f" * 64
    assert assess(corrupt_checkpoint).status is VerificationStatus.FAILED

    artifact_ref = {
        "target_schema_name": "qc2.integrity_build.ArtifactManifest.v1",
        "target_id": UUIDS[2],
        "content_hash": "e" * 64,
    }
    incomplete_checkpoint = make_checkpoint(
        3,
        events[-1].event_contract["event_hash"],
        checkpoint_id=UUIDS[1],
        previous_checkpoint_hash=None,
        artifact_refs=[artifact_ref],
    )
    assert (
        assess(incomplete_checkpoint.checkpoint_contract).status
        is VerificationStatus.PARTIAL_SCAN
    )
