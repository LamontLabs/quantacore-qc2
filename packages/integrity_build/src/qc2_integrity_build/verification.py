from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, Protocol, Sequence

from qc2_contracts.runtime import (
    ContractValidationError,
    artifact_inventory_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    parse_json_strict,
    validate_contract,
    verify_content_hash,
)

LOCAL_PROOF_LEVEL = "BACKEND_LOCAL_TAMPER_EVIDENT"
INDEPENDENT_PROOF_LEVEL = "INDEPENDENT_PREOUTCOME_ANCHORED"
EVENT_HASH_DOMAIN = "qc2.evidence-event.v1"
PAYLOAD_HASH_DOMAIN = "qc2.evidence-payload.v1"
CHECKPOINT_HASH_DOMAIN = "qc2.checkpoint-root.v1"
CHECKPOINT_ARTIFACT_ROOT_DOMAIN = "qc2.checkpoint-artifact-roots.v1"


class VerificationStatus(StrEnum):
    FULL_VERIFIED = "FULL_VERIFIED"
    PARTIAL_SCAN = "PARTIAL_SCAN"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class EvidenceEventRecord:
    event_contract: Mapping[str, Any]
    payload_bytes: bytes


@dataclass(frozen=True)
class EvidenceVerification:
    status: VerificationStatus
    proof_level: str
    checked_count: int
    issues: tuple[str, ...] = ()

    @property
    def passes(self) -> bool:
        return self.status is VerificationStatus.FULL_VERIFIED


@dataclass(frozen=True)
class CheckpointRecord:
    checkpoint_contract: Mapping[str, Any]
    artifact_refs: Sequence[Mapping[str, Any]]
    previous_checkpoint_hash: str | None


@dataclass(frozen=True)
class ExternalCheckpoint:
    stream_id: str
    evidence_class: str
    checkpoint_hash: str
    head_sequence: int
    head_hash: str
    event_count: int
    externally_verified: bool


@dataclass(frozen=True)
class ArtifactObject:
    relative_path: str
    content: bytes | None
    kind: str = "file"
    executable: bool = False
    media_type: str | None = None


class AnchorPort(Protocol):
    """Integration seam; production use requires an independently operated provider."""

    async def submit_checkpoint(
        self, checkpoint: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    async def verify_receipt(
        self,
        checkpoint: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> bool: ...


def _result(
    status: VerificationStatus,
    checked_count: int,
    issues: Sequence[str],
    proof_level: str = LOCAL_PROOF_LEVEL,
) -> EvidenceVerification:
    return EvidenceVerification(status, proof_level, checked_count, tuple(issues))


def _event_record(value: EvidenceEventRecord | Mapping[str, Any]) -> EvidenceEventRecord:
    if isinstance(value, EvidenceEventRecord):
        return value
    payload = value.get("payload_bytes")
    if not isinstance(payload, bytes):
        raise TypeError("payload_bytes must be raw bytes")
    contract = value.get("event_contract")
    if not isinstance(contract, Mapping):
        raise TypeError("event_contract must be an object")
    return EvidenceEventRecord(contract, payload)


def _event_hash_basis(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in event.items()
        if key not in {"content_hash", "event_hash"}
    }


def _checkpoint_hash_basis(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in checkpoint.items()
        if key not in {"content_hash", "checkpoint_hash"}
    }


def _canonical_checkpoint_refs(
    artifact_refs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    refs = [dict(ref) for ref in artifact_refs]
    refs.sort(key=lambda ref: str(ref.get("target_id", "")).encode("utf-8"))
    return refs


def _utc_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ContractValidationError("QC2 instants must be explicitly UTC")
    return parsed


async def assess_anchor_receipt(
    checkpoint: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
    anchor: AnchorPort,
    *,
    qualification_deadline: str,
    next_outcome_session_start: str,
    verified_references: set[tuple[str, str, str]] | None = None,
) -> EvidenceVerification:
    """Upgrade proof only after external receipt verification and before-outcome timing."""
    try:
        checkpoint_value = dict(checkpoint)
        checkpoint_result = verify_checkpoint_chain(
            [
                CheckpointRecord(
                    checkpoint_value,
                    checkpoint_value["source_refs"],
                    None,
                )
            ],
            verified_references=verified_references,
        )
        if checkpoint_result.status is not VerificationStatus.FULL_VERIFIED:
            return checkpoint_result
        if receipt is None:
            return _result(
                VerificationStatus.FULL_VERIFIED,
                0,
                ("No independent receipt is available; local chaining is not official proof.",),
            )
        receipt_value = dict(receipt)
        validate_contract("AnchorReceipt", receipt_value)
        reference = receipt_value["checkpoint_ref"]
        if (
            reference["target_schema_name"] != "qc2.integrity_build.Checkpoint.v1"
            or reference["target_id"] != checkpoint_value["id"]
            or reference.get("content_hash") != checkpoint_value["content_hash"]
        ):
            raise ContractValidationError("Anchor receipt references another checkpoint")
        if (
            receipt_value["evidence_class"] != checkpoint_value["evidence_class"]
            or receipt_value["environment_namespace"]
            != checkpoint_value["environment_namespace"]
        ):
            raise ContractValidationError("Anchor receipt identity differs from its checkpoint")
        accepted_at = _utc_instant(receipt_value["accepted_at"])
        observed_at = _utc_instant(receipt_value["observed_at"])
        deadline = _utc_instant(qualification_deadline)
        outcome_start = _utc_instant(next_outcome_session_start)
        if deadline >= outcome_start:
            raise ContractValidationError(
                "Anchor qualification deadline must precede the outcome session"
            )
        if observed_at < accepted_at:
            raise ContractValidationError("Anchor receipt was observed before acceptance")
    except (ContractValidationError, KeyError, TypeError, ValueError) as exc:
        return _result(VerificationStatus.FAILED, 0, (f"Anchor receipt invalid: {exc}",))

    if receipt_value["proof_level"] != INDEPENDENT_PROOF_LEVEL:
        return _result(
            VerificationStatus.FULL_VERIFIED,
            0,
            ("Receipt does not claim the independent pre-outcome proof level.",),
        )
    if checkpoint_value["evidence_class"] != "FORWARD_SEALED":
        return _result(
            VerificationStatus.FULL_VERIFIED,
            0,
            ("Only an activated FORWARD_SEALED checkpoint can qualify.",),
        )
    try:
        receipt_verified = await anchor.verify_receipt(
            checkpoint_value,
            receipt_value,
        )
    except Exception:
        return _result(
            VerificationStatus.UNAVAILABLE,
            0,
            ("Independent anchor provider is unavailable; no independent proof was established.",),
        )
    if not receipt_verified:
        return _result(
            VerificationStatus.FAILED,
            0,
            ("Independent anchor receipt verification failed.",),
        )
    if accepted_at > deadline or accepted_at >= outcome_start:
        return _result(
            VerificationStatus.FULL_VERIFIED,
            0,
            ("Late anchors cannot qualify a session retroactively.",),
        )
    return _result(
        VerificationStatus.FULL_VERIFIED,
        0,
        (),
        INDEPENDENT_PROOF_LEVEL,
    )


def verify_evidence_scan(
    events: Sequence[EvidenceEventRecord | Mapping[str, Any]],
    stream_head: Mapping[str, Any] | None,
    *,
    scan_complete: bool,
    available: bool = True,
    verified_references: set[tuple[str, str, str]] | None = None,
    references_complete: bool = True,
) -> EvidenceVerification:
    """Verify every returned event and the complete committed stream head."""
    if not available or stream_head is None:
        return _result(
            VerificationStatus.UNAVAILABLE,
            0,
            ("Evidence stream or head is unavailable.",),
        )

    issues: list[str] = []
    checked = 0
    verified: list[tuple[dict[str, Any], bytes]] = []
    referenced_objects: set[tuple[str, str, str]] = set()
    try:
        records = [_event_record(event) for event in events]
    except (TypeError, AttributeError) as exc:
        return _result(VerificationStatus.FAILED, 0, (f"Invalid scan record: {exc}",))

    sequence_values: list[int] = []
    for record in records:
        event = dict(record.event_contract)
        checked += 1
        try:
            validate_contract("EvidenceEvent", event)
            verify_content_hash("EvidenceEvent", event)
            payload = parse_json_strict(record.payload_bytes.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ContractValidationError("Evidence payload must be a JSON object")
            if canonical_json_bytes(payload) != record.payload_bytes:
                raise ContractValidationError("Evidence payload bytes are not canonical")
            payload_hash = domain_separated_sha256(
                PAYLOAD_HASH_DOMAIN,
                record.payload_bytes,
            )
            if payload_hash != event["payload_hash"]:
                raise ContractValidationError("Evidence payload hash does not match")
            event_hash = domain_separated_sha256(
                EVENT_HASH_DOMAIN,
                canonical_json_bytes(_event_hash_basis(event)),
            )
            if event_hash != event["event_hash"]:
                raise ContractValidationError("Evidence event hash does not match")
            if event["stream_id"] != stream_head.get("stream_id"):
                raise ContractValidationError("Evidence event belongs to another stream")
            if (
                "installation_id" in stream_head
                and event["installation_id"] != stream_head["installation_id"]
            ):
                raise ContractValidationError("Evidence installation identity changed")
            if (
                "environment_namespace" in stream_head
                and event["environment_namespace"] != stream_head["environment_namespace"]
            ):
                raise ContractValidationError("Evidence environment identity changed")
            for field in ("source_refs", "dependency_refs"):
                for reference in event[field]:
                    referenced_objects.add(
                        (
                            reference["target_schema_name"],
                            reference["target_id"],
                            reference.get("content_hash", ""),
                        )
                    )
            sequence_values.append(event["sequence"])
            verified.append((event, record.payload_bytes))
        except (ContractValidationError, UnicodeDecodeError, TypeError, ValueError) as exc:
            issues.append(f"Event validation failed: {exc}")

    if issues:
        return _result(VerificationStatus.FAILED, checked, issues)

    if len(sequence_values) != len(set(sequence_values)):
        issues.append("Duplicate event sequence detected.")
    if sequence_values != sorted(sequence_values):
        issues.append("Events are reordered.")
    if issues:
        return _result(VerificationStatus.FAILED, checked, issues)

    try:
        head_sequence = stream_head["head_sequence"]
        head_hash = stream_head["head_event_hash"]
        event_count = stream_head["event_count"]
        stream_id = stream_head["stream_id"]
        if (
            isinstance(head_sequence, bool)
            or not isinstance(head_sequence, int)
            or isinstance(event_count, bool)
            or not isinstance(event_count, int)
            or head_sequence < 1
            or event_count != head_sequence
            or not isinstance(head_hash, str)
            or len(head_hash) != 64
            or not isinstance(stream_id, str)
        ):
            raise ValueError("Stream head fields are invalid")
    except (KeyError, TypeError, ValueError) as exc:
        return _result(
            VerificationStatus.FAILED,
            checked,
            (f"Stream head validation failed: {exc}",),
        )

    if verified and verified[0][0]["sequence"] == 1:
        genesis = verified[0][0]
        if (
            genesis["event_type"] != "stream_genesis"
            or genesis["previous_event_hash"] is not None
        ):
            issues.append("Stream genesis is invalid.")
        else:
            try:
                payload = parse_json_strict(verified[0][1].decode("utf-8"))
                if (
                    payload.get("stream_id") != stream_id
                    or payload.get("installation_id") != genesis["installation_id"]
                ):
                    issues.append("Genesis identity does not match the stream.")
            except (AttributeError, UnicodeDecodeError, ValueError) as exc:
                issues.append(f"Genesis payload is invalid: {exc}")

    for (previous, _), (current, _) in zip(verified, verified[1:]):
        if current["sequence"] == previous["sequence"] + 1:
            if current["previous_event_hash"] != previous["event_hash"]:
                issues.append(f"Broken previous-event link at sequence {current['sequence']}.")
        elif scan_complete:
            issues.append(f"Sequence gap before event {current['sequence']}.")

    partial_reasons: list[str] = []
    if referenced_objects and verified_references is None:
        partial_reasons.append("Referenced evidence objects were not inventoried.")
    elif verified_references is not None:
        missing_references = sorted(referenced_objects - verified_references)
        if missing_references and references_complete:
            issues.append("One or more referenced evidence objects are unavailable.")
        elif missing_references:
            partial_reasons.append("Referenced-object inventory is incomplete.")
    if not references_complete:
        partial_reasons.append("Referenced-object scan did not complete.")

    if scan_complete:
        if len(verified) != event_count:
            issues.append("Complete scan count does not match the committed stream head.")
        if not verified or verified[0][0]["sequence"] != 1:
            issues.append("Complete scan does not contain the stream genesis.")
        if verified and verified[-1][0]["sequence"] != head_sequence:
            issues.append("Complete scan does not reach the committed stream head.")
        if verified and verified[-1][0]["event_hash"] != head_hash:
            issues.append("Committed stream head hash does not match the final event.")
        if issues:
            return _result(VerificationStatus.FAILED, checked, issues)
        if partial_reasons:
            return _result(VerificationStatus.PARTIAL_SCAN, checked, partial_reasons)
        return _result(VerificationStatus.FULL_VERIFIED, checked, ())

    if issues:
        return _result(VerificationStatus.FAILED, checked, issues)
    partial_reasons.append("Scan did not prove a complete inventory through the committed head.")
    return _result(
        VerificationStatus.PARTIAL_SCAN,
        checked,
        partial_reasons,
    )


def verify_checkpoint_chain(
    records: Sequence[CheckpointRecord | Mapping[str, Any]],
    *,
    verified_references: set[tuple[str, str, str]] | None = None,
    references_complete: bool = True,
) -> EvidenceVerification:
    """Check checkpoint hashes, artifact roots, and previous-checkpoint continuity."""
    if not records:
        return _result(
            VerificationStatus.UNAVAILABLE,
            0,
            ("No checkpoint records are available.",),
        )

    issues: list[str] = []
    checked = 0
    previous_hash: str | None = None
    previous_sequence = -1
    stream_id: str | None = None
    referenced_objects: set[tuple[str, str, str]] = set()

    for value in records:
        if isinstance(value, CheckpointRecord):
            record = value
        else:
            contract = value.get("checkpoint_contract")
            refs = value.get("artifact_refs")
            if not isinstance(contract, Mapping) or not isinstance(refs, Sequence):
                issues.append("Checkpoint record is missing its contract or artifact refs.")
                continue
            record = CheckpointRecord(
                contract,
                refs,
                value.get("previous_checkpoint_hash"),
            )

        checked += 1
        checkpoint = dict(record.checkpoint_contract)
        try:
            validate_contract("Checkpoint", checkpoint)
            verify_content_hash("Checkpoint", checkpoint)
            checkpoint_hash = domain_separated_sha256(
                CHECKPOINT_HASH_DOMAIN,
                canonical_json_bytes(_checkpoint_hash_basis(checkpoint)),
            )
            if checkpoint_hash != checkpoint["checkpoint_hash"]:
                raise ContractValidationError("Checkpoint root hash does not match")
            refs = _canonical_checkpoint_refs(record.artifact_refs)
            artifact_root = domain_separated_sha256(
                CHECKPOINT_ARTIFACT_ROOT_DOMAIN,
                canonical_json_bytes(refs),
            )
            if artifact_root != checkpoint["artifact_root_hash"]:
                raise ContractValidationError("Checkpoint artifact root does not match")
            if refs != checkpoint["source_refs"]:
                raise ContractValidationError("Checkpoint source refs do not match its artifact root")
            for reference in refs:
                referenced_objects.add(
                    (
                        reference["target_schema_name"],
                        reference["target_id"],
                        reference.get("content_hash", ""),
                    )
                )
            if stream_id is None:
                stream_id = checkpoint["stream_id"]
            elif checkpoint["stream_id"] != stream_id:
                raise ContractValidationError("Checkpoint chain crosses stream identities")
            if checkpoint["head_sequence"] < previous_sequence:
                raise ContractValidationError("Checkpoint sequence moved backwards")
            if record.previous_checkpoint_hash != previous_hash:
                raise ContractValidationError("Previous-checkpoint link does not match")
            previous_sequence = checkpoint["head_sequence"]
            previous_hash = checkpoint["checkpoint_hash"]
        except (ContractValidationError, TypeError, ValueError) as exc:
            issues.append(f"Checkpoint validation failed: {exc}")

    if issues:
        return _result(VerificationStatus.FAILED, checked, issues)
    if referenced_objects and verified_references is None:
        return _result(
            VerificationStatus.PARTIAL_SCAN,
            checked,
            ("Referenced artifact manifests were not inventoried.",),
        )
    if verified_references is not None:
        missing_references = referenced_objects - verified_references
        if missing_references and references_complete:
            return _result(
                VerificationStatus.FAILED,
                checked,
                ("One or more checkpoint artifact manifests are unavailable.",),
            )
        if missing_references or not references_complete:
            return _result(
                VerificationStatus.PARTIAL_SCAN,
                checked,
                ("Referenced-artifact inventory did not complete.",),
            )
    if not references_complete:
        return _result(
            VerificationStatus.PARTIAL_SCAN,
            checked,
            ("Referenced-artifact inventory did not complete.",),
        )
    return _result(VerificationStatus.FULL_VERIFIED, checked, ())


def verify_artifact_inventory(
    manifest: Mapping[str, Any],
    objects: Sequence[ArtifactObject | Mapping[str, Any]],
    *,
    listing_complete: bool,
    available: bool = True,
) -> EvidenceVerification:
    """Compare every manifest file with a complete, non-link object listing and bytes."""
    if not available:
        return _result(
            VerificationStatus.UNAVAILABLE,
            0,
            ("Artifact store is unavailable.",),
        )

    try:
        normalized_manifest = dict(manifest)
        validate_contract("ArtifactManifest", normalized_manifest)
        verify_content_hash("ArtifactManifest", normalized_manifest)
        expected_files = {
            entry["relative_path"]: entry
            for entry in normalized_manifest["files"]
        }
        if len(expected_files) != len(normalized_manifest["files"]):
            raise ContractValidationError("Manifest has duplicate file paths")
        if artifact_inventory_hash(normalized_manifest["files"]) != normalized_manifest[
            "inventory_hash"
        ]:
            raise ContractValidationError("Artifact inventory hash does not match")
    except (ContractValidationError, KeyError, TypeError, ValueError) as exc:
        return _result(
            VerificationStatus.FAILED,
            0,
            (f"Artifact manifest validation failed: {exc}",),
        )

    observed: dict[str, ArtifactObject] = {}
    issues: list[str] = []
    checked = 0
    for value in objects:
        try:
            obj = value if isinstance(value, ArtifactObject) else ArtifactObject(**value)
        except (TypeError, ValueError) as exc:
            issues.append(f"Invalid artifact listing entry: {exc}")
            continue
        checked += 1
        if obj.relative_path in observed:
            issues.append(f"Duplicate object path: {obj.relative_path}")
            continue
        observed[obj.relative_path] = obj
        if obj.kind != "file":
            issues.append(f"Unsupported object kind at {obj.relative_path}: {obj.kind}")
        if obj.executable:
            issues.append(f"Executable artifact object is not permitted: {obj.relative_path}")
        expected = expected_files.get(obj.relative_path)
        if expected is None:
            issues.append(f"Unexpected object is present: {obj.relative_path}")
            continue
        if obj.content is None:
            continue
        if len(obj.content) != expected["length_bytes"]:
            issues.append(f"Object length mismatch: {obj.relative_path}")
        if hashlib.sha256(obj.content).hexdigest() != expected["sha256"]:
            issues.append(f"Object hash mismatch: {obj.relative_path}")
        if obj.media_type is not None and obj.media_type != expected["media_type"]:
            issues.append(f"Object media type mismatch: {obj.relative_path}")

    missing = sorted(set(expected_files) - set(observed))
    if listing_complete:
        issues.extend(f"Manifest object is missing: {path}" for path in missing)
    elif issues:
        return _result(VerificationStatus.FAILED, checked, issues)

    unavailable_contents = sorted(
        path for path, obj in observed.items() if path in expected_files and obj.content is None
    )
    if issues:
        return _result(VerificationStatus.FAILED, checked, issues)
    if not listing_complete or missing or unavailable_contents:
        details = ["Artifact scan did not verify the complete manifest inventory."]
        details.extend(f"Missing from partial listing: {path}" for path in missing)
        details.extend(f"Object bytes unavailable: {path}" for path in unavailable_contents)
        return _result(VerificationStatus.PARTIAL_SCAN, checked, details)
    return _result(VerificationStatus.FULL_VERIFIED, checked, ())


def compare_independent_checkpoint(
    checkpoint: ExternalCheckpoint | None,
    local_head: Mapping[str, Any] | None,
    *,
    local_verification: EvidenceVerification | None = None,
) -> EvidenceVerification:
    """Compare a fully verified local chain with a verified external checkpoint."""
    if checkpoint is None or local_head is None:
        return _result(
            VerificationStatus.UNAVAILABLE,
            0,
            ("Independent checkpoint or local stream head is unavailable.",),
        )
    if not checkpoint.externally_verified:
        return _result(
            VerificationStatus.FAILED,
            0,
            ("Independent checkpoint receipt was not verified by its external provider.",),
        )
    try:
        if local_head["stream_id"] != checkpoint.stream_id:
            raise ValueError("Independent checkpoint belongs to another stream")
        local_sequence = local_head["head_sequence"]
        local_hash = local_head["head_event_hash"]
        local_count = local_head["event_count"]
        if (
            isinstance(local_sequence, bool)
            or not isinstance(local_sequence, int)
            or isinstance(local_count, bool)
            or not isinstance(local_count, int)
            or local_count != local_sequence
        ):
            raise ValueError("Local stream head is invalid")
        if local_sequence < checkpoint.head_sequence or local_count < checkpoint.event_count:
            raise ValueError("Local stream is older than the independently retained checkpoint")
        if local_sequence == checkpoint.head_sequence and local_hash != checkpoint.head_hash:
            raise ValueError("Local stream hash conflicts with the independent checkpoint")
    except (KeyError, TypeError, ValueError) as exc:
        return _result(VerificationStatus.FAILED, 0, (str(exc),))

    if local_verification is None:
        return _result(
            VerificationStatus.PARTIAL_SCAN,
            local_count,
            ("A complete local evidence scan is required before proof-level comparison.",),
        )
    if local_verification.status is not VerificationStatus.FULL_VERIFIED:
        return local_verification
    if checkpoint.evidence_class != "FORWARD_SEALED":
        return _result(
            VerificationStatus.FULL_VERIFIED,
            local_count,
            ("Synthetic, historical, or operational evidence cannot claim independent proof.",),
        )
    if local_sequence == checkpoint.head_sequence:
        return _result(
            VerificationStatus.FULL_VERIFIED,
            local_verification.checked_count,
            (),
            INDEPENDENT_PROOF_LEVEL,
        )
    return _result(
        VerificationStatus.FULL_VERIFIED,
        local_verification.checked_count,
        ("The external checkpoint covers a verified prefix, not the current head.",),
    )
