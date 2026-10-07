"""Construction and validation of canonical calendar wire records."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from qc2_contracts.runtime import (
    canonical_content_hash,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

from .errors import CalendarAuthorityError
from .provider import ProviderSession

CALENDAR_SCHEMA = "qc2.time_operation.CalendarManifest.v1"
REVISION_SCHEMA = "qc2.time_operation.CalendarRevision.v1"
SESSION_SCHEMA = "qc2.time_operation.MarketSession.v1"
EVIDENCE_SCHEMA = "qc2.integrity_build.EvidenceEvent.v1"


def build_calendar_records(
    provider_sessions: Sequence[ProviderSession],
    *,
    calendar_id: str,
    revision_id: str,
    calendar_version: int,
    revision_number: int,
    valid_from: str,
    valid_through: str,
    effective_session: str,
    revision_reason: str,
    created_at: str,
    evidence_class: str,
    environment_namespace: str,
    source_evidence_ref: Mapping[str, Any],
    manifest_source_refs: Sequence[Mapping[str, Any]] = (),
    revision_source_refs: Sequence[Mapping[str, Any]] = (),
    session_source_refs: Sequence[Mapping[str, Any]] = (),
    id_factory: Callable[[], str] = new_uuidv7,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Build one immutable manifest, one provenance revision, and its sessions.

    Source evidence is supplied by Evidence Authority; this function does not
    invent or persist evidence.
    """
    if not provider_sessions:
        raise CalendarAuthorityError("calendar_sessions_empty")
    session_ids = [row.session_id for row in provider_sessions]
    if session_ids != sorted(set(session_ids)):
        raise CalendarAuthorityError("calendar_sessions_not_sorted_unique")
    if valid_from != session_ids[0] or valid_through != session_ids[-1]:
        raise CalendarAuthorityError("calendar_manifest_bounds_mismatch")
    if effective_session not in session_ids:
        raise CalendarAuthorityError("calendar_revision_effective_session_missing")
    if source_evidence_ref.get("target_schema_name") != EVIDENCE_SCHEMA:
        raise CalendarAuthorityError("calendar_revision_evidence_reference_invalid")

    manifest: dict[str, Any] = {
        "schema_name": CALENDAR_SCHEMA,
        "schema_version": "1.0",
        "id": calendar_id,
        "created_at": created_at,
        "owning_authority": "calendar",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [dict(ref) for ref in manifest_source_refs],
        "content_hash": "0" * 64,
        "calendar_version": calendar_version,
        "timezone": "America/New_York",
        "valid_from": valid_from,
        "valid_through": valid_through,
        "sessions": session_ids,
    }
    manifest["content_hash"] = canonical_content_hash("CalendarManifest", manifest)
    verify_content_hash("CalendarManifest", manifest)

    manifest_ref = {
        "target_schema_name": CALENDAR_SCHEMA,
        "target_id": calendar_id,
        "content_hash": manifest["content_hash"],
    }
    revision: dict[str, Any] = {
        "schema_name": REVISION_SCHEMA,
        "schema_version": "1.0",
        "id": revision_id,
        "created_at": created_at,
        "owning_authority": "calendar",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [dict(ref) for ref in revision_source_refs],
        "calendar_ref": manifest_ref,
        "revision_number": revision_number,
        "effective_session": effective_session,
        "reason": revision_reason,
        "source_evidence_ref": dict(source_evidence_ref),
    }
    validate_contract("CalendarRevision", revision)

    revision_ref = {
        "target_schema_name": REVISION_SCHEMA,
        "target_id": revision_id,
    }
    sessions: list[dict[str, Any]] = []
    for row in provider_sessions:
        record = {
            "schema_name": SESSION_SCHEMA,
            "schema_version": "1.0",
            "id": id_factory(),
            "created_at": created_at,
            "owning_authority": "calendar",
            "evidence_class": evidence_class,
            "environment_namespace": environment_namespace,
            "source_refs": [dict(ref) for ref in session_source_refs],
            "session_id": row.session_id,
            "phase": "REGULAR",
            "opens_at": row.opens_at,
            "closes_at": row.closes_at,
            "calendar_revision_ref": revision_ref,
        }
        validate_contract("MarketSession", record)
        sessions.append(record)
    return manifest, revision, sessions
