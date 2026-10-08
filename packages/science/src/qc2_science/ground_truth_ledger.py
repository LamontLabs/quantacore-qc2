"""Append-only Outcome corrections and mature learning-release interfaces."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime

from .ground_truth import _deterministic_uuid7, _unique_refs
from .ground_truth_models import (
    CONFIGURATION_MANIFEST_SCHEMA,
    OUTCOME_REVISION_SCHEMA,
    OUTCOME_SCHEMA,
    FrozenContractRecord,
    GroundTruthError,
    freeze_contract_record,
    utc_text,
)
from .models import ContractRef, as_utc

_REASON = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_PREDICTION_SEAL_SCHEMA = "qc2.models_prediction.PredictionSeal.v1"


def _release_payload(
    refs: tuple[ContractRef, ...],
    policy_ref: ContractRef,
    created_at: datetime,
    available_at: datetime,
) -> dict:
    return {
        "outcome_refs": [ref.to_payload() for ref in refs],
        "release_policy_ref": policy_ref.to_payload(),
        "created_at": utc_text(created_at, "release created_at"),
        "available_for_learning_at": utc_text(available_at, "available_for_learning_at"),
    }


def _validate_outcome_record(record: FrozenContractRecord) -> dict:
    if not isinstance(record, FrozenContractRecord) or record.contract_name != "Outcome":
        raise GroundTruthError("Outcome correction requires a frozen Outcome contract")
    payload = record.payload
    if payload["schema_name"] != OUTCOME_SCHEMA:
        raise GroundTruthError("frozen record is not an Outcome")
    return payload


def _outcome_identity(payload: dict) -> tuple:
    return (
        payload["instrument_ref"]["target_schema_name"],
        payload["instrument_ref"]["target_id"],
        payload["session_id"],
        payload["label_ref"]["target_schema_name"],
        payload["label_ref"]["target_id"],
        payload["label_ref"].get("content_hash"),
        payload["horizon_sessions"],
        payload["reference_bar_ref"]["target_id"],
    )


@dataclass(frozen=True, slots=True)
class OutcomeCorrectionRequest:
    prior_outcome_ref: ContractRef
    replacement_outcome: FrozenContractRecord
    revision_reason: str
    correction_policy_ref: ContractRef
    discovered_at: datetime | str
    evidence_refs: tuple[ContractRef, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.prior_outcome_ref, ContractRef)
            or self.prior_outcome_ref.target_schema_name != OUTCOME_SCHEMA
            or not self.prior_outcome_ref.content_hash
        ):
            raise GroundTruthError("prior_outcome_ref must reference a content-addressed Outcome")
        _validate_outcome_record(self.replacement_outcome)
        if not isinstance(self.revision_reason, str) or not _REASON.fullmatch(
            self.revision_reason
        ):
            raise GroundTruthError("revision_reason must be a lowercase reason code")
        if (
            not isinstance(self.correction_policy_ref, ContractRef)
            or self.correction_policy_ref.target_schema_name != CONFIGURATION_MANIFEST_SCHEMA
        ):
            raise GroundTruthError("correction_policy_ref must reference ConfigurationManifest")
        evidence = tuple(self.evidence_refs)
        if not evidence or any(not isinstance(item, ContractRef) for item in evidence):
            raise GroundTruthError("corrections require typed evidence references")
        object.__setattr__(self, "discovered_at", as_utc(self.discovered_at, "discovered_at"))
        object.__setattr__(self, "evidence_refs", evidence)


@dataclass(frozen=True, slots=True)
class LearningReleaseRequest:
    outcome_refs: tuple[ContractRef, ...]
    release_policy_ref: ContractRef
    created_at: datetime | str

    def __post_init__(self) -> None:
        refs = tuple(self.outcome_refs)
        if not refs or any(
            not isinstance(ref, ContractRef) or ref.target_schema_name != OUTCOME_SCHEMA
            for ref in refs
        ):
            raise GroundTruthError("learning release requires Outcome references")
        if len({(ref.target_id, ref.content_hash) for ref in refs}) != len(refs):
            raise GroundTruthError("learning release Outcome references must be unique")
        if (
            not isinstance(self.release_policy_ref, ContractRef)
            or self.release_policy_ref.target_schema_name != CONFIGURATION_MANIFEST_SCHEMA
        ):
            raise GroundTruthError("release_policy_ref must reference ConfigurationManifest")
        object.__setattr__(self, "outcome_refs", refs)
        object.__setattr__(self, "created_at", as_utc(self.created_at, "release created_at"))


@dataclass(frozen=True, slots=True)
class LearningReleaseBatch:
    release_id: str
    outcome_refs: tuple[ContractRef, ...]
    release_policy_ref: ContractRef
    created_at: datetime
    available_for_learning_at: datetime
    content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.release_id, str) or not _UUID7.fullmatch(self.release_id):
            raise GroundTruthError("learning release id must be UUIDv7")
        refs = tuple(self.outcome_refs)
        if not refs or any(
            not isinstance(ref, ContractRef) or ref.target_schema_name != OUTCOME_SCHEMA
            for ref in refs
        ):
            raise GroundTruthError("learning release batch must reference Outcomes")
        if len({(ref.target_id, ref.content_hash) for ref in refs}) != len(refs):
            raise GroundTruthError("learning release batch Outcome references must be unique")
        if (
            not isinstance(self.release_policy_ref, ContractRef)
            or self.release_policy_ref.target_schema_name != CONFIGURATION_MANIFEST_SCHEMA
        ):
            raise GroundTruthError("learning release batch requires a ConfigurationManifest")
        created = as_utc(self.created_at, "release created_at")
        available = as_utc(self.available_for_learning_at, "available_for_learning_at")
        if created < available:
            raise GroundTruthError("learning release cannot precede Outcome maturity")
        refs = tuple(sorted(refs, key=lambda ref: (ref.target_id, ref.content_hash)))
        payload = _release_payload(refs, self.release_policy_ref, created, available)
        expected_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if self.content_hash != expected_hash:
            raise GroundTruthError("learning release content hash does not match its contents")
        if self.release_id != _deterministic_uuid7(created, expected_hash):
            raise GroundTruthError("learning release id is not derived from its frozen contents")
        object.__setattr__(self, "outcome_refs", refs)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "available_for_learning_at", available)


@dataclass(frozen=True, slots=True)
class OutcomeLedger:
    """Immutable ledger; Outcome and revision records are append-only tuples."""

    outcomes: tuple[FrozenContractRecord, ...] = ()
    revisions: tuple[FrozenContractRecord, ...] = ()
    sealed_prediction_refs: tuple[ContractRef, ...] = ()
    learning_releases: tuple[LearningReleaseBatch, ...] = ()

    def __post_init__(self) -> None:
        outcomes = tuple(self.outcomes)
        revisions = tuple(self.revisions)
        seals = tuple(self.sealed_prediction_refs)
        releases = tuple(self.learning_releases)
        if any(
            not isinstance(record, FrozenContractRecord) or record.contract_name != "Outcome"
            for record in outcomes
        ):
            raise GroundTruthError("OutcomeLedger.outcomes must contain frozen Outcomes")
        if len({record.ref for record in outcomes}) != len(outcomes):
            raise GroundTruthError("OutcomeLedger cannot repeat the same Outcome reference")
        if any(
            not isinstance(record, FrozenContractRecord)
            or record.contract_name != "OutcomeRevision"
            for record in revisions
        ):
            raise GroundTruthError("OutcomeLedger.revisions must contain frozen OutcomeRevisions")
        revision_ids = [record.payload["id"] for record in revisions]
        if len(set(revision_ids)) != len(revision_ids):
            raise GroundTruthError("OutcomeLedger cannot repeat an OutcomeRevision id")
        if any(
            not isinstance(ref, ContractRef)
            or ref.target_schema_name != _PREDICTION_SEAL_SCHEMA
            for ref in seals
        ):
            raise GroundTruthError("sealed_prediction_refs must reference PredictionSeal")
        if any(not isinstance(item, LearningReleaseBatch) for item in releases):
            raise GroundTruthError("learning_releases must contain LearningReleaseBatch values")
        release_ids = [item.release_id for item in releases]
        if len(set(release_ids)) != len(release_ids):
            raise GroundTruthError("OutcomeLedger cannot repeat a learning release")
        object.__setattr__(self, "outcomes", outcomes)
        object.__setattr__(self, "revisions", revisions)
        object.__setattr__(self, "sealed_prediction_refs", seals)
        object.__setattr__(self, "learning_releases", releases)


def append_outcome_revision(
    ledger: OutcomeLedger,
    correction: OutcomeCorrectionRequest,
) -> OutcomeLedger:
    """Append a corrected Outcome and OutcomeRevision without editing prior records."""
    if not isinstance(ledger, OutcomeLedger) or not isinstance(
        correction, OutcomeCorrectionRequest
    ):
        raise GroundTruthError("append_outcome_revision requires typed immutable inputs")
    replacement_payload = _validate_outcome_record(correction.replacement_outcome)
    prior_records = [
        record
        for record in ledger.outcomes
        if record.ref == correction.prior_outcome_ref
    ]
    if len(prior_records) != 1:
        raise GroundTruthError("prior Outcome is absent or ambiguous in the ledger")
    prior_record = prior_records[0]
    prior_payload = _validate_outcome_record(prior_record)
    identity = _outcome_identity(prior_payload)
    if _outcome_identity(replacement_payload) != identity:
        raise GroundTruthError("Outcome correction cannot change instrument/session/label identity")
    if (
        replacement_payload["environment_namespace"] != prior_payload["environment_namespace"]
        or replacement_payload["evidence_class"] != prior_payload["evidence_class"]
    ):
        raise GroundTruthError("Outcome correction cannot change evidence class or environment")
    if replacement_payload["content_hash"] == prior_payload["content_hash"]:
        raise GroundTruthError("Outcome correction must change the content-addressed Outcome")
    if prior_record.ref == correction.replacement_outcome.ref:
        raise GroundTruthError("Outcome correction must create a distinct replacement version")

    revision_payload = {
        "schema_name": OUTCOME_REVISION_SCHEMA,
        "schema_version": "1.0",
        "id": "",
        "created_at": utc_text(correction.discovered_at, "revision created_at"),
        "owning_authority": "ground_truth",
        "evidence_class": replacement_payload["evidence_class"],
        "environment_namespace": replacement_payload["environment_namespace"],
        "source_refs": _unique_refs(correction.evidence_refs),
        "prior_outcome_ref": correction.prior_outcome_ref.to_payload(),
        "replacement_outcome_ref": correction.replacement_outcome.ref.to_payload(),
        "revision_reason": correction.revision_reason,
        "discovered_at": utc_text(correction.discovered_at, "revision discovered_at"),
        "correction_policy_ref": correction.correction_policy_ref.to_payload(),
    }
    revision_identity = json.dumps(
        {
            "prior": correction.prior_outcome_ref.to_payload(),
            "replacement": correction.replacement_outcome.ref.to_payload(),
            "reason": correction.revision_reason,
            "discovered_at": revision_payload["discovered_at"],
            "policy": correction.correction_policy_ref.to_payload(),
            "evidence": revision_payload["source_refs"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    revision_payload["id"] = _deterministic_uuid7(
        correction.discovered_at,
        revision_identity,
    )
    revision_record = freeze_contract_record("OutcomeRevision", revision_payload)
    if revision_record in ledger.revisions:
        return ledger

    current_records = [
        record
        for record in ledger.outcomes
        if _outcome_identity(record.payload) == identity
    ]
    if not current_records or current_records[-1].ref != correction.prior_outcome_ref:
        raise GroundTruthError("correction prior Outcome is stale; append from the current version")
    if any(record.ref == correction.replacement_outcome.ref for record in ledger.outcomes):
        raise GroundTruthError("replacement Outcome already exists without its matching revision")

    return replace(
        ledger,
        outcomes=(*ledger.outcomes, correction.replacement_outcome),
        revisions=(*ledger.revisions, revision_record),
        # The revision interface has no prediction payload and preserves all seal references.
        sealed_prediction_refs=ledger.sealed_prediction_refs,
        learning_releases=ledger.learning_releases,
    )


def append_learning_release(
    ledger: OutcomeLedger,
    request: LearningReleaseRequest,
) -> tuple[OutcomeLedger, LearningReleaseBatch]:
    """Append a release manifest bound only to current, mature, resolved Outcomes."""
    if not isinstance(ledger, OutcomeLedger) or not isinstance(request, LearningReleaseRequest):
        raise GroundTruthError("append_learning_release requires typed immutable inputs")
    records_by_ref = {record.ref: record for record in ledger.outcomes}
    selected: list[dict] = []
    for reference in request.outcome_refs:
        record = records_by_ref.get(reference)
        if record is None:
            raise GroundTruthError("learning release references an absent or superseded Outcome")
        payload = _validate_outcome_record(record)
        identity = _outcome_identity(payload)
        current = [
            item
            for item in ledger.outcomes
            if _outcome_identity(item.payload) == identity
        ][-1]
        if current.ref != reference:
            raise GroundTruthError("learning release cannot use a superseded Outcome version")
        if payload["outcome_state"] != "RESOLVED":
            raise GroundTruthError("learning release requires a fully RESOLVED Outcome")
        available = payload["available_for_learning_at"]
        if available is None:
            raise GroundTruthError("learning release requires available_for_learning_at")
        if any(
            field["status"] not in {"VALID", "NOT_APPLICABLE"}
            for field in payload["field_validity"]
        ):
            raise GroundTruthError("learning release cannot contain unresolved or censored fields")
        if (
            payload["environment_namespace"] == "production"
            and payload["evidence_class"] == "SYNTHETIC_FIXTURE"
        ):
            raise GroundTruthError("synthetic fixture Outcomes cannot be released in production")
        selected.append(payload)

    available_at = max(
        as_utc(item["available_for_learning_at"], "available_for_learning_at")
        for item in selected
    )
    if request.created_at < available_at:
        raise GroundTruthError("learning release cannot precede the latest Outcome maturity")
    environments = {
        (item["environment_namespace"], item["evidence_class"]) for item in selected
    }
    if len(environments) != 1:
        raise GroundTruthError("learning release cannot mix evidence classes or environments")
    refs = tuple(sorted(request.outcome_refs, key=lambda ref: (ref.target_id, ref.content_hash)))
    release_payload = _release_payload(
        refs,
        request.release_policy_ref,
        request.created_at,
        available_at,
    )
    release_hash = hashlib.sha256(
        json.dumps(release_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    release_id = _deterministic_uuid7(request.created_at, release_hash)
    batch = LearningReleaseBatch(
        release_id=release_id,
        outcome_refs=refs,
        release_policy_ref=request.release_policy_ref,
        created_at=request.created_at,
        available_for_learning_at=available_at,
        content_hash=release_hash,
    )
    if batch in ledger.learning_releases:
        return ledger, batch
    updated = replace(ledger, learning_releases=(*ledger.learning_releases, batch))
    return updated, batch
