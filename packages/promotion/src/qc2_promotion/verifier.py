"""Independent eligibility, evidence, and safe-model verification."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from qc2_contracts.runtime import (
    CONTRACTS,
    SCHEMA_TO_CONTRACT,
    canonical_json_bytes,
    domain_separated_sha256,
    parse_json_strict,
)

from .archive import decode_archive
from .bundle import (
    EVALUATOR_ROLE,
    PACKAGER_ROLE,
    SAFE_ARTIFACT_SCHEMAS,
    VerifiedPromotionBundle,
    verify_promotion_bundle_archive,
)
from .errors import PromotionVerificationError, VerificationErrorCode
from .limits import BundleLimits, PromotionBundleError
from .sandbox import (
    CandidateModelUnsafeError,
    CandidateSandboxError,
    CandidateProbeResult,
    SandboxLimits,
    probe_candidate_model,
)
from .trust import KeyRole, KeyRoleRegistry

_REPORT_SCHEMA = "qc2.promotion.CandidateEvaluationReport.v1"
_ATTESTATION_SCHEMA = "qc2.promotion.CandidateEvaluationAttestation.v1"
_REPORT_PATH = "candidate-evaluation-report.json"
_ATTESTATION_PATH = "candidate-evaluation-attestation.json"
_EVALUATION_ATTESTATION_PREFIX = b"QC2-CANDIDATE-EVALUATION-REPORT-V1\x00"
_EVALUATION_POLICY = {
    "version": "qc2-independent-evaluation-v1",
    "decimal_places": 12,
    "calibration_bins": 10,
    "regression_baseline": "zero_prediction",
    "classification_baseline": "fixed_probability_0.5",
    "calibration_threshold_policy": "NOT_FROZEN",
    "performance_policy": "REGRESSION_MUST_BEAT_DECLARED_BASELINE",
}
_EVALUATION_POLICY_HASH = hashlib.sha256(
    canonical_json_bytes(_EVALUATION_POLICY)
).hexdigest()
_EVALUATION_POLICY_PAYLOAD = {
    **_EVALUATION_POLICY,
    "policy_hash": _EVALUATION_POLICY_HASH,
}
_GATE_IDS = (
    "heldout_leakage",
    "deterministic_inference",
    "resource_budget",
    "regression_performance",
    "calibration",
    "evidence_class",
    "evaluator_policy",
)
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class PromotionVerificationPolicy:
    """Verifier-owned policy; no eligibility thresholds are inferred from a bundle."""

    trusted_promotion_policy_hashes: frozenset[str]
    max_evidence_age_seconds: int
    sandbox_limits: SandboxLimits

    def __post_init__(self) -> None:
        if not self.trusted_promotion_policy_hashes:
            raise ValueError("at least one trusted PromotionPolicy hash is required")
        if any(_HEX_SHA256.fullmatch(value) is None for value in self.trusted_promotion_policy_hashes):
            raise ValueError("trusted PromotionPolicy hashes must be lowercase SHA-256 values")
        if self.max_evidence_age_seconds <= 0:
            raise ValueError("max_evidence_age_seconds must be positive")


@dataclass(frozen=True, slots=True)
class GateVerificationReceipt:
    gate_id: str
    status: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PromotionVerificationResult:
    bundle: VerifiedPromotionBundle
    gate_receipts: tuple[GateVerificationReceipt, ...]
    model_probe: CandidateProbeResult
    eligible_for_owner_review: bool


def verify_promotion_bundle(
    archive_bytes: bytes,
    *,
    key_registry: KeyRoleRegistry,
    now: str,
    limits: BundleLimits,
    policy: PromotionVerificationPolicy,
) -> PromotionVerificationResult:
    """Verify trust, compatibility, time, gates, then load only the safe JSON model."""
    try:
        _utc(now, VerificationErrorCode.TEMPORAL_VIOLATION, "verification time")
        _, _, signature, _ = decode_archive(archive_bytes, limits)
    except PromotionBundleError as exc:
        raise PromotionVerificationError(
            VerificationErrorCode.ARCHIVE_INVALID, "archive framing or signed inventory is invalid"
        ) from exc
    signer = signature.get("artifact_signer")
    if not isinstance(signer, Mapping) or signer.get("role") != PACKAGER_ROLE:
        raise PromotionVerificationError(
            VerificationErrorCode.KEY_ROLE_MISMATCH,
            "bundle signer is not registered as an artifact packager",
        )
    packager_key = key_registry.resolve(
        signer.get("key_id", ""),
        required_role=KeyRole.ARTIFACT_PACKAGER,
        now=now,
    )
    try:
        verified = verify_promotion_bundle_archive(
            archive_bytes,
            trusted_backend_public_keys={packager_key.key_id: packager_key.public_key},
            now=now,
            limits=limits,
        )
    except PromotionBundleError as exc:
        raise PromotionVerificationError(
            VerificationErrorCode.BUNDLE_INVALID,
            "bundle signature, manifest, dependency closure, or inventory is invalid",
        ) from exc

    documents, assets = _index_bundle(verified)
    manifest = _plain(verified.manifest)
    candidate = _document(manifest["candidate_model_ref"], documents)
    dataset = _document(manifest["dataset_ref"], documents)
    split = _document(manifest["split_ref"], documents)
    policy_doc = _document(manifest["policy_ref"], documents)
    _validate_policy_and_compatibility(
        manifest, candidate, dataset, split, policy_doc, policy, documents
    )
    _validate_owner_key(verified, key_registry, now)
    _validate_temporal_evidence(
        manifest,
        documents,
        now=now,
        max_age_seconds=policy.max_evidence_age_seconds,
    )

    evaluation, report, holdout, budget, model_artifact, environment_bytes, model_bytes = (
        _evaluation_evidence(
            verified,
            manifest,
            candidate,
            dataset,
            split,
            documents,
            assets,
        )
    )
    _verify_evaluator_attestation(
        verified,
        evaluation,
        report,
        documents,
        key_registry,
        now,
    )
    model_probe = _probe_candidate(
        model_bytes=model_bytes,
        environment_bytes=environment_bytes,
        model_manifest=candidate,
        dataset_ref=manifest["dataset_ref"],
        split_ref=manifest["split_ref"],
        policy=policy,
    )
    gate_receipts = _recompute_gates(
        manifest=manifest,
        candidate=candidate,
        dataset=dataset,
        evaluation=evaluation,
        report=report,
        holdout=holdout,
        budget=budget,
        model_artifact=model_artifact,
        model_bytes=model_bytes,
        environment_bytes=environment_bytes,
        probe=model_probe,
    )
    eligible = (
        dataset.get("evidence_class") == "FORWARD_OPERATIONAL"
        and all(gate.status == "PASS" for gate in gate_receipts)
    )
    return PromotionVerificationResult(
        bundle=verified,
        gate_receipts=gate_receipts,
        model_probe=model_probe,
        eligible_for_owner_review=eligible,
    )


def _index_bundle(
    bundle: VerifiedPromotionBundle,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    documents: dict[tuple[str, str], dict[str, Any]] = {}
    assets: dict[str, dict[str, Any]] = {}
    for path, raw in bundle.files.items():
        try:
            payload = parse_json_strict(raw.decode("utf-8"))
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise PromotionVerificationError(
                VerificationErrorCode.BUNDLE_INVALID, f"invalid canonical JSON at {path}"
            ) from exc
        if not isinstance(payload, dict) or canonical_json_bytes(payload) != raw:
            raise PromotionVerificationError(
                VerificationErrorCode.BUNDLE_INVALID, f"noncanonical JSON at {path}"
            )
        schema_name = payload.get("schema_name")
        if schema_name in SCHEMA_TO_CONTRACT:
            identity = (schema_name, payload.get("id"))
            documents[identity] = payload
        elif schema_name in SAFE_ARTIFACT_SCHEMAS:
            assets[path] = payload
    return documents, assets


def _document(
    reference: Mapping[str, Any],
    documents: Mapping[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(reference, Mapping):
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING, "required typed reference is missing"
        )
    payload = documents.get(
        (reference.get("target_schema_name"), reference.get("target_id"))
    )
    if payload is None:
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING,
            f"missing dependency {reference.get('target_schema_name')!r}",
        )
    return payload


def _validate_policy_and_compatibility(
    manifest: Mapping[str, Any],
    candidate: Mapping[str, Any],
    dataset: Mapping[str, Any],
    split: Mapping[str, Any],
    promotion_policy: Mapping[str, Any],
    policy: PromotionVerificationPolicy,
    documents: Mapping[tuple[str, str], dict[str, Any]],
) -> None:
    policy_hash = promotion_policy.get("content_hash")
    if policy_hash not in policy.trusted_promotion_policy_hashes:
        raise PromotionVerificationError(
            VerificationErrorCode.POLICY_UNTRUSTED,
            "PromotionPolicy hash is not in the verifier's trusted policy set",
        )
    if manifest.get("mode") not in promotion_policy.get("epoch_modes", []):
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "bundle mode is not permitted by its trusted PromotionPolicy",
        )
    if candidate.get("safe_format") not in promotion_policy.get(
        "permitted_artifact_types", []
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "candidate format is not permitted by its trusted PromotionPolicy",
        )
    if (
        not _same_ref(candidate.get("dataset_ref"), manifest.get("dataset_ref"))
        or not _same_ref(candidate.get("split_ref"), manifest.get("split_ref"))
        or not _same_ref(split.get("dataset_ref"), manifest.get("dataset_ref"))
        or candidate.get("environment_fingerprint") != manifest.get("environment_fingerprint")
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "candidate, split, and bundle bindings do not agree",
        )
    label_ref = _registry_ref(manifest.get("registry_refs", []), "LabelRegistry")
    label_registry = _document(label_ref, documents)
    if not _same_ref_in_sequence(label_registry.get("definition_refs", []), label_registry.get("primary_label_ref")):
        raise PromotionVerificationError(
            VerificationErrorCode.LABEL_MISMATCH,
            "primary label is not a member of the registered label definitions",
        )
    targets = candidate.get("target_label_refs")
    definitions = label_registry.get("definition_refs")
    primary = label_registry.get("primary_label_ref")
    if (
        not isinstance(targets, list)
        or not targets
        or not isinstance(definitions, list)
        or not _same_ref_in_sequence(targets, primary)
        or any(not _same_ref_in_sequence(definitions, target) for target in targets)
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.LABEL_MISMATCH,
            "candidate target labels do not match the selected LabelRegistry",
        )
    dataset_labels = [
        ref for ref in dataset.get("registry_refs", [])
        if isinstance(ref, Mapping)
        and ref.get("target_schema_name") == CONTRACTS["LabelRegistry"][1]
    ]
    if len(dataset_labels) != 1 or not _same_ref(dataset_labels[0], label_ref):
        raise PromotionVerificationError(
            VerificationErrorCode.LABEL_MISMATCH,
            "dataset and bundle refer to different label registries",
        )
    if (
        candidate.get("evidence_class") != dataset.get("evidence_class")
        or manifest.get("evidence_class") != dataset.get("evidence_class")
        or candidate.get("environment_namespace") != dataset.get("environment_namespace")
        or split.get("environment_namespace") != dataset.get("environment_namespace")
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "candidate, dataset, and split evidence contexts differ",
        )

def _validate_owner_key(
    bundle: VerifiedPromotionBundle,
    registry: KeyRoleRegistry,
    now: str,
) -> None:
    owner_identity = bundle.owner_identity
    key_id = owner_identity.get("owner_key_id")
    key = registry.resolve(
        key_id,
        required_role=KeyRole.OWNER_IDENTITY,
        now=now,
    )
    if hashlib.sha256(key.public_key).hexdigest() != owner_identity.get(
        "public_key_sha256"
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "registered owner key does not match the bundle's OwnerDevice",
        )


def _validate_temporal_evidence(
    manifest: Mapping[str, Any],
    documents: Mapping[tuple[str, str], dict[str, Any]],
    *,
    now: str,
    max_age_seconds: int,
) -> None:
    current = _utc(now, VerificationErrorCode.TEMPORAL_VIOLATION, "verification time")
    created = _utc(
        manifest.get("created_at"),
        VerificationErrorCode.TEMPORAL_VIOLATION,
        "bundle created_at",
    )
    if created > current:
        raise PromotionVerificationError(
            VerificationErrorCode.TEMPORAL_VIOLATION, "bundle creation time is in the future"
        )
    for payload in documents.values():
        if "created_at" in payload and _utc(
            payload["created_at"],
            VerificationErrorCode.TEMPORAL_VIOLATION,
            f"{payload.get('schema_name')}.created_at",
        ) > created:
            raise PromotionVerificationError(
                VerificationErrorCode.TEMPORAL_VIOLATION,
                "evidence was created after the signed bundle",
            )

    evaluation_refs = manifest.get("evaluation_refs", [])
    if len(evaluation_refs) != 1 or evaluation_refs[0].get(
        "target_schema_name"
    ) != CONTRACTS["CandidateEvaluation"][1]:
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "verifier requires one fully supported CandidateEvaluation report",
        )
    evaluation = _document(evaluation_refs[0], documents)
    evaluated_at = _utc(
        evaluation.get("evaluated_at"),
        VerificationErrorCode.TEMPORAL_VIOLATION,
        "CandidateEvaluation.evaluated_at",
    )
    if evaluated_at > created or evaluated_at > current:
        raise PromotionVerificationError(
            VerificationErrorCode.TEMPORAL_VIOLATION,
            "candidate evaluation is later than the bundle or verification time",
        )
    if (current - evaluated_at).total_seconds() > max_age_seconds:
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_STALE,
            "candidate evaluation is older than the verifier's configured evidence window",
        )
    if _utc(
        evaluation.get("created_at"),
        VerificationErrorCode.TEMPORAL_VIOLATION,
        "CandidateEvaluation.created_at",
    ) > created:
        raise PromotionVerificationError(
            VerificationErrorCode.TEMPORAL_VIOLATION,
            "candidate evaluation receipt was created after the bundle",
        )
    candidate = _document(manifest["candidate_model_ref"], documents)
    if _utc(
        candidate.get("training_cutoff"),
        VerificationErrorCode.TEMPORAL_VIOLATION,
        "ModelManifest.training_cutoff",
    ) > evaluated_at:
        raise PromotionVerificationError(
            VerificationErrorCode.TEMPORAL_VIOLATION,
            "candidate training cutoff is later than its evaluation",
        )
    promotion_policy = _document(manifest["policy_ref"], documents)
    if _utc(
        promotion_policy.get("frozen_at"),
        VerificationErrorCode.TEMPORAL_VIOLATION,
        "PromotionPolicy.frozen_at",
    ) > evaluated_at:
        raise PromotionVerificationError(
            VerificationErrorCode.TEMPORAL_VIOLATION,
            "evaluation predates the trusted promotion policy",
        )
    holdout_ref = _find_ref(evaluation.get("source_refs", []), "HoldoutAccessReceipt")
    holdout = _document(holdout_ref, documents)
    requested_at = _utc(
        holdout.get("requested_at"),
        VerificationErrorCode.TEMPORAL_VIOLATION,
        "HoldoutAccessReceipt.requested_at",
    )
    granted_at = _utc(
        holdout.get("granted_at"),
        VerificationErrorCode.TEMPORAL_VIOLATION,
        "HoldoutAccessReceipt.granted_at",
    )
    if requested_at > granted_at or granted_at > evaluated_at:
        raise PromotionVerificationError(
            VerificationErrorCode.TEMPORAL_VIOLATION,
            "holdout release occurred outside the evaluation interval",
        )
    if (current - granted_at).total_seconds() > max_age_seconds:
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_STALE, "holdout receipt is stale"
        )

    for ref in manifest.get("shadow_seal_refs", []):
        seal = _document(ref, documents)
        sealed_at = _utc(
            seal.get("sealed_at"),
            VerificationErrorCode.TEMPORAL_VIOLATION,
            "PredictionSeal.sealed_at",
        )
        if sealed_at > evaluated_at or sealed_at > created or sealed_at > current:
            raise PromotionVerificationError(
                VerificationErrorCode.TEMPORAL_VIOLATION,
                "Shadow seal is sealed after evaluation or bundle creation",
            )
        if (current - sealed_at).total_seconds() > max_age_seconds:
            raise PromotionVerificationError(
                VerificationErrorCode.EVIDENCE_STALE, "Shadow seal is stale"
            )
        try:
            session = date.fromisoformat(seal.get("session_id", ""))
        except (TypeError, ValueError) as exc:
            raise PromotionVerificationError(
                VerificationErrorCode.TEMPORAL_VIOLATION,
                "Shadow seal session is not a calendar date",
            ) from exc
        as_of_session = min(
            created.astimezone(ZoneInfo("America/New_York")).date(),
            evaluated_at.astimezone(ZoneInfo("America/New_York")).date(),
        )
        if session > as_of_session:
            raise PromotionVerificationError(
                VerificationErrorCode.TEMPORAL_VIOLATION,
                "Shadow seal contains a session later than the evaluation cutoff",
            )
        run = _document(seal["run_ref"], documents)
        if run.get("session_id") != seal.get("session_id"):
            raise PromotionVerificationError(
                VerificationErrorCode.TEMPORAL_VIOLATION,
                "PredictionSeal session differs from its PredictionRun",
            )


def _evaluation_evidence(
    bundle: VerifiedPromotionBundle,
    manifest: Mapping[str, Any],
    candidate: Mapping[str, Any],
    dataset: Mapping[str, Any],
    split: Mapping[str, Any],
    documents: Mapping[tuple[str, str], dict[str, Any]],
    assets: Mapping[str, dict[str, Any]],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    bytes,
    bytes,
]:
    evaluation = _document(manifest["evaluation_refs"][0], documents)
    if (
        not _same_ref(evaluation.get("candidate_ref"), manifest["candidate_model_ref"])
        or not _same_ref(evaluation.get("dataset_ref"), manifest["dataset_ref"])
        or not _same_ref(evaluation.get("split_ref"), manifest["split_ref"])
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "CandidateEvaluation does not bind the nominated model, dataset, and split",
        )
    artifact_ref = candidate.get("artifact_manifest_ref")
    model_artifact = _document(artifact_ref, documents)
    model_bytes = _artifact_file(bundle, model_artifact, "model.json", assets)
    environment_bytes = _artifact_file(bundle, model_artifact, "environment.json", assets)

    evidence_artifacts: list[dict[str, Any]] = []
    for ref in evaluation.get("source_refs", []):
        if (
            not isinstance(ref, Mapping)
            or ref.get("target_schema_name") != CONTRACTS["ArtifactManifest"][1]
        ):
            continue
        artifact = _document(ref, documents)
        files = artifact.get("files", [])
        has_report = any(
            item.get("schema_name") == _REPORT_SCHEMA
            and item.get("relative_path") == _REPORT_PATH
            for item in files
        )
        has_attestation = any(
            item.get("schema_name") == _ATTESTATION_SCHEMA
            and item.get("relative_path") == _ATTESTATION_PATH
            for item in files
        )
        if has_report or has_attestation:
            evidence_artifacts.append(artifact)
    if len(evidence_artifacts) != 1:
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING,
            "CandidateEvaluation requires one referenced report and attestation artifact",
        )
    evidence_artifact = evidence_artifacts[0]
    if {item["relative_path"] for item in evidence_artifact["files"]} != {
        _REPORT_PATH,
        _ATTESTATION_PATH,
    }:
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "evaluation artifact has extra or missing report files",
        )
    report_bytes = _artifact_file(bundle, evidence_artifact, _REPORT_PATH, assets)
    attestation_bytes = _artifact_file(
        bundle, evidence_artifact, _ATTESTATION_PATH, assets
    )
    report = _parse_asset(report_bytes, _REPORT_SCHEMA, "candidate evaluation report")
    report["attestation"] = _parse_asset(
        attestation_bytes, _ATTESTATION_SCHEMA, "candidate evaluation attestation"
    )
    holdout_ref = report.get("holdout_receipt_ref")
    evaluation_holdout_ref = _find_ref(
        evaluation.get("source_refs", []), "HoldoutAccessReceipt"
    )
    if not _same_ref(holdout_ref, evaluation_holdout_ref):
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING,
            "evaluation report holdout differs from CandidateEvaluation source refs",
        )
    holdout = _document(holdout_ref, documents)
    budget_ref = _find_ref(evaluation.get("source_refs", []), "ResourceBudget")
    budget = _document(budget_ref, documents)
    replay = _document(manifest["replay_report_ref"], documents)
    if (
        replay.get("verdict") != "MATCH"
        or replay.get("expected_count") != replay.get("actual_count")
        or replay.get("expected_hash") != replay.get("actual_hash")
        or replay.get("first_mismatch") is not None
        or replay.get("environment_fingerprint") != manifest.get("environment_fingerprint")
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "deterministic replay receipt does not match the nominated environment",
        )
    if budget.get("fixture_only") is not False:
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "fixture-only resource budgets cannot qualify a promotion",
        )
    if len(manifest.get("holdout_receipt_refs", [])) != 1 or not _same_ref(
        manifest["holdout_receipt_refs"][0], holdout_ref
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING,
            "bundle holdout receipt refs do not match the evaluation report",
        )
    if (
        holdout.get("access_scope") != "METRICS_ONLY"
        or not _same_ref(holdout.get("dataset_ref"), manifest["dataset_ref"])
        or holdout.get("evidence_class") != dataset.get("evidence_class")
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.COMPATIBILITY_MISMATCH,
            "holdout receipt is not a matching metrics-only release",
        )
    receipt_payload = {
        key: value for key, value in holdout.items() if key != "receipt_hash"
    }
    expected_receipt_hash = domain_separated_sha256(
        "qc2.candidate-evaluator-holdout.v1",
        canonical_json_bytes(receipt_payload),
    )
    if holdout.get("receipt_hash") != expected_receipt_hash:
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING,
            "holdout receipt hash does not match its immutable contents",
        )
    return (
        evaluation,
        report,
        holdout,
        budget,
        model_artifact,
        environment_bytes,
        model_bytes,
    )


def _verify_evaluator_attestation(
    bundle: VerifiedPromotionBundle,
    evaluation: Mapping[str, Any],
    report: Mapping[str, Any],
    documents: Mapping[tuple[str, str], dict[str, Any]],
    key_registry: KeyRoleRegistry,
    now: str,
) -> None:
    attestation = report.get("attestation")
    if not isinstance(attestation, Mapping):
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING, "evaluator attestation is missing"
        )
    expected_fields = {
        "schema_name",
        "schema_version",
        "evaluator_identity",
        "evaluator_key_id",
        "report_hash",
        "signature_algorithm",
        "encoding",
        "signature",
    }
    if (
        set(attestation) != expected_fields
        or attestation.get("schema_name") != _ATTESTATION_SCHEMA
        or attestation.get("schema_version") != "1.0"
        or attestation.get("signature_algorithm") != "Ed25519"
        or attestation.get("encoding") != "base64url-no-padding"
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.SIGNATURE_INVALID,
            "evaluator attestation schema or signature profile is unsupported",
        )
    report_payload = {key: value for key, value in report.items() if key != "attestation"}
    expected_report_hash = report_payload.get("report_hash")
    hash_payload = {key: value for key, value in report_payload.items() if key != "report_hash"}
    computed_hash = hashlib.sha256(canonical_json_bytes(hash_payload)).hexdigest()
    evaluator_identity = evaluation.get("evaluator_identity")
    if (
        not isinstance(expected_report_hash, str)
        or computed_hash != expected_report_hash
        or expected_report_hash != evaluation.get("report_hash")
        or expected_report_hash != bundle.evaluator_identity.get("report_hash")
        or evaluator_identity != bundle.evaluator_identity.get("identity")
        or attestation.get("evaluator_identity") != evaluator_identity
        or attestation.get("report_hash") != expected_report_hash
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.SIGNATURE_INVALID,
            "evaluation report hash or identity binding is inconsistent",
        )
    # CandidateEvaluation identity is already resolved from the signed dependency graph.
    _document(evaluation["candidate_ref"], documents)
    key = key_registry.resolve(
        attestation.get("evaluator_key_id", ""),
        required_role=KeyRole.INDEPENDENT_EVALUATOR,
        now=now,
        identity=evaluator_identity,
    )
    signature = _decode_b64url(attestation.get("signature"))
    statement = {
        "role": EVALUATOR_ROLE,
        "evaluator_identity": evaluator_identity,
        "key_id": key.key_id,
        "report_hash": expected_report_hash,
    }
    try:
        Ed25519PublicKey.from_public_bytes(key.public_key).verify(
            signature,
            _EVALUATION_ATTESTATION_PREFIX + canonical_json_bytes(statement),
        )
    except InvalidSignature as exc:
        raise PromotionVerificationError(
            VerificationErrorCode.SIGNATURE_INVALID,
            "independent evaluator signature did not verify",
        ) from exc


def _probe_candidate(
    *,
    model_bytes: bytes,
    environment_bytes: bytes,
    model_manifest: Mapping[str, Any],
    dataset_ref: Mapping[str, Any],
    split_ref: Mapping[str, Any],
    policy: PromotionVerificationPolicy,
) -> CandidateProbeResult:
    try:
        return probe_candidate_model(
            model_bytes=model_bytes,
            environment_bytes=environment_bytes,
            model_manifest=model_manifest,
            dataset_ref=dataset_ref,
            split_ref=split_ref,
            limits=policy.sandbox_limits,
        )
    except CandidateModelUnsafeError as exc:
        raise PromotionVerificationError(
            VerificationErrorCode.MODEL_UNSAFE, "safe JSON model validation failed"
        ) from exc
    except CandidateSandboxError as exc:
        raise PromotionVerificationError(
            VerificationErrorCode.SANDBOX_FAILURE, "isolated model probe failed"
        ) from exc


def _recompute_gates(
    *,
    manifest: Mapping[str, Any],
    candidate: Mapping[str, Any],
    dataset: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    report: Mapping[str, Any],
    holdout: Mapping[str, Any],
    budget: Mapping[str, Any],
    model_artifact: Mapping[str, Any],
    model_bytes: bytes,
    environment_bytes: bytes,
    probe: CandidateProbeResult,
) -> tuple[GateVerificationReceipt, ...]:
    metrics = report.get("metrics")
    usage = report.get("resource_usage")
    if not isinstance(metrics, Mapping) or not isinstance(usage, Mapping):
        _gate_mismatch("evaluation report metrics or resource usage are missing")
    if (
        report.get("schema_name") != _REPORT_SCHEMA
        or report.get("schema_version") != "1.0"
        or set(key for key in report if key != "attestation")
        != {
            "schema_name",
            "schema_version",
            "policy",
            "candidate_ref",
            "dataset_ref",
            "split_ref",
            "holdout_receipt_ref",
            "evidence_class",
            "evaluation_status",
            "qualification_row_count",
            "metrics",
            "resource_usage",
            "gate_results",
            "holdout_open_event_hash",
            "report_hash",
        }
        or report.get("policy") != _EVALUATION_POLICY_PAYLOAD
        or report.get("evaluation_status") != evaluation.get("verdict")
        or report.get("evidence_class") != dataset.get("evidence_class")
        or not _same_ref(report.get("candidate_ref"), manifest["candidate_model_ref"])
        or not _same_ref(report.get("dataset_ref"), manifest["dataset_ref"])
        or not _same_ref(report.get("split_ref"), manifest["split_ref"])
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.GATE_RECOMPUTATION_MISMATCH,
            "report context or code-owned evaluator policy differs from its receipt",
        )
    expected_metric_names = (
        {
            "observation_count",
            "rmse",
            "mae",
            "zero_baseline_rmse",
            "rmse_skill_vs_zero",
        }
        if probe.task == "REGRESSION"
        else {
            "observation_count",
            "brier",
            "fixed_0_5_baseline_brier",
            "log_loss",
            "expected_calibration_error_10_bin",
        }
    )
    if set(metrics) != expected_metric_names:
        _gate_mismatch("evaluation metric set does not match the allowlisted model task")
    try:
        observation_count = int(metrics["observation_count"])
    except (TypeError, ValueError) as exc:
        raise PromotionVerificationError(
            VerificationErrorCode.GATE_RECOMPUTATION_MISMATCH,
            "observation_count is not an integer",
        ) from exc
    if (
        observation_count <= 0
        or str(observation_count) != metrics["observation_count"]
        or observation_count != report.get("qualification_row_count")
    ):
        _gate_mismatch("observation count differs from the report's qualification inventory")

    records = report.get("gate_results")
    evaluation_records = evaluation.get("gate_results")
    manifest_records = manifest.get("gate_results")
    if (
        not isinstance(records, list)
        or not isinstance(evaluation_records, list)
        or not isinstance(manifest_records, list)
        or [item.get("gate_id") for item in records if isinstance(item, Mapping)] != list(_GATE_IDS)
        or _canonical(records) != _canonical(evaluation_records)
        or _canonical(records) != _canonical(manifest_records)
    ):
        _gate_mismatch("signed report, evaluation, and bundle gate lists do not match exactly")

    holdout_refs = [
        ref for ref in evaluation.get("source_refs", [])
        if isinstance(ref, Mapping)
        and ref.get("target_schema_name") == CONTRACTS["HoldoutAccessReceipt"][1]
    ]
    budget_refs = [
        ref for ref in evaluation.get("source_refs", [])
        if isinstance(ref, Mapping)
        and ref.get("target_schema_name") == CONTRACTS["ResourceBudget"][1]
    ]
    expected_refs = [
        _plain(evaluation["candidate_ref"]),
        _plain(evaluation["dataset_ref"]),
        _plain(evaluation["split_ref"]),
        _plain(holdout_refs[0]) if len(holdout_refs) == 1 else {},
        _plain(budget_refs[0]) if len(budget_refs) == 1 else {},
    ]
    if len(holdout_refs) != 1 or len(budget_refs) != 1:
        _gate_mismatch("evaluation does not bind exactly one holdout receipt and resource budget")
    for record in records:
        if (
            set(record)
            != {"gate_id", "status", "reason_codes", "evaluated_at", "source_refs"}
            or record.get("evaluated_at") != evaluation.get("evaluated_at")
            or _canonical(record.get("source_refs")) != _canonical(expected_refs)
        ):
            _gate_mismatch("gate receipt fields or source references are not canonical")

    if (
        holdout.get("access_scope") != "METRICS_ONLY"
        or sorted(holdout.get("released_metrics", [])) != sorted(metrics)
        or holdout.get("evaluator_identity") != evaluation.get("evaluator_identity")
        or _contains_label_field(report)
    ):
        _gate_mismatch("holdout release is not limited to the report's aggregate metrics")

    usage_keys = {"elapsed_seconds", "cpu_seconds", "peak_memory_bytes", "artifact_bytes"}
    if not usage_keys <= set(usage):
        _gate_mismatch("resource usage omits a required observed value")
    expected_artifact_bytes = len(model_bytes) + len(environment_bytes)
    if usage["artifact_bytes"] != expected_artifact_bytes:
        _gate_mismatch("reported model artifact byte count differs from verified bytes")
    resource_pass = (
        _decimal(usage["elapsed_seconds"], "elapsed_seconds")
        <= Decimal(budget["max_elapsed_seconds"])
        and _decimal(usage["cpu_seconds"], "cpu_seconds")
        <= Decimal(budget["max_cpu_seconds"])
        and _integer(usage["peak_memory_bytes"], "peak_memory_bytes")
        <= budget["max_memory_bytes"]
        and _integer(usage["artifact_bytes"], "artifact_bytes")
        <= budget["max_artifact_bytes"]
    )
    evidence_forward = dataset.get("evidence_class") not in {
        "SYNTHETIC_FIXTURE",
        "HISTORICAL_RECONSTRUCTED",
    }

    expected: list[tuple[str, str, list[str]]] = [
        (
            "heldout_leakage",
            "PASS",
            ["SEALED_MEMBERSHIP_AND_ROW_DISJOINTNESS_VERIFIED"],
        ),
        (
            "deterministic_inference",
            "PASS" if probe.deterministic else "BLOCK",
            ["INDEPENDENT_SAFE_INTERPRETER_REPEATED_IDENTICALLY"]
            if probe.deterministic
            else ["INDEPENDENT_SAFE_INTERPRETER_PROBE_MISMATCH"],
        ),
        (
            "resource_budget",
            "PASS" if resource_pass else "BLOCK",
            ["OBSERVED_RESOURCE_USE_WITHIN_FROZEN_BUDGET"]
            if resource_pass
            else ["OBSERVED_RESOURCE_USE_EXCEEDS_FROZEN_BUDGET"],
        ),
    ]
    if probe.task == "REGRESSION":
        rmse = _decimal(metrics["rmse"], "rmse")
        baseline = _decimal(metrics["zero_baseline_rmse"], "zero_baseline_rmse")
        if baseline == 0:
            expected.append(
                (
                    "regression_performance",
                    "UNKNOWN",
                    ["ZERO_BASELINE_HAS_NO_COMPARATIVE_HEADROOM"],
                )
            )
        elif rmse < baseline:
            expected.append(
                (
                    "regression_performance",
                    "PASS",
                    ["RMSE_BEATS_FROZEN_ZERO_PREDICTION_BASELINE"],
                )
            )
        else:
            expected.append(
                (
                    "regression_performance",
                    "BLOCK",
                    ["RMSE_DOES_NOT_BEAT_FROZEN_ZERO_PREDICTION_BASELINE"],
                )
            )
        expected.append(
            (
                "calibration",
                "WARN",
                ["CALIBRATION_NOT_APPLICABLE_TO_REGRESSION_TASK"],
            )
        )
    else:
        expected.extend(
            [
                (
                    "regression_performance",
                    "WARN",
                    ["REGRESSION_METRIC_NOT_APPLICABLE_TO_CLASSIFICATION_TASK"],
                ),
                (
                    "calibration",
                    "UNKNOWN",
                    ["CALIBRATION_THRESHOLD_POLICY_NOT_FROZEN"],
                ),
            ]
        )
    expected.extend(
        [
            (
                "evidence_class",
                "PASS" if evidence_forward else "UNKNOWN",
                ["FORWARD_EVIDENCE_CLASS_RECORDED"]
                if evidence_forward
                else ["NONFORWARD_EVIDENCE_CANNOT_QUALIFY_A_CANDIDATE"],
            ),
            (
                "evaluator_policy",
                "PASS",
                ["CODE_OWNED_POLICY_HASH_MATCHES_NOMINATION"],
            ),
        ]
    )
    receipts = tuple(
        GateVerificationReceipt(gate_id, status, tuple(reasons))
        for gate_id, status, reasons in expected
    )
    expected_records = [
        {
            "gate_id": gate.gate_id,
            "status": gate.status,
            "reason_codes": list(gate.reason_codes),
            "evaluated_at": evaluation["evaluated_at"],
            "source_refs": expected_refs,
        }
        for gate in receipts
    ]
    if _canonical(expected_records) != _canonical(records):
        _gate_mismatch("one or more signed gate results differ from independent recomputation")
    statuses = {gate.status for gate in receipts}
    expected_verdict = (
        "FAIL"
        if "BLOCK" in statuses
        else "INSUFFICIENT_EVIDENCE"
        if statuses.intersection({"UNKNOWN", "UNAVAILABLE"})
        else "PASS"
    )
    if evaluation.get("verdict") != expected_verdict or report.get(
        "evaluation_status"
    ) != expected_verdict:
        _gate_mismatch("signed evaluation verdict differs from recomputed gate outcomes")
    return receipts


def _artifact_file(
    bundle: VerifiedPromotionBundle,
    artifact: Mapping[str, Any],
    relative_path: str,
    assets: Mapping[str, dict[str, Any]],
) -> bytes:
    archive_path = f"artifacts/{artifact['id']}/{relative_path}"
    payload = assets.get(archive_path)
    raw = bundle.files.get(archive_path)
    if payload is None or raw is None:
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING,
            f"ArtifactManifest is missing {relative_path}",
        )
    record = next(
        (
            item for item in artifact.get("files", [])
            if item.get("relative_path") == relative_path
        ),
        None,
    )
    if (
        record is None
        or record.get("schema_name") != payload.get("schema_name")
        or hashlib.sha256(raw).hexdigest() != record.get("sha256")
        or len(raw) != record.get("length_bytes")
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.BUNDLE_INVALID,
            f"artifact file {relative_path} differs from its immutable manifest",
        )
    return raw


def _parse_asset(raw: bytes, schema_name: str, label: str) -> dict[str, Any]:
    try:
        value = parse_json_strict(raw.decode("utf-8"))
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise PromotionVerificationError(
            VerificationErrorCode.BUNDLE_INVALID, f"{label} is not strict JSON"
        ) from exc
    if (
        not isinstance(value, dict)
        or canonical_json_bytes(value) != raw
        or value.get("schema_name") != schema_name
        or value.get("schema_version") != "1.0"
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.BUNDLE_INVALID, f"{label} schema or canonical bytes are invalid"
        )
    return value


def _registry_ref(registry_refs: Sequence[Mapping[str, Any]], contract: str) -> Mapping[str, Any]:
    schema = CONTRACTS[contract][1]
    matches = [
        ref for ref in registry_refs
        if ref.get("target_schema_name") == schema
    ]
    if len(matches) != 1:
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING,
            f"bundle must bind exactly one {contract}",
        )
    return matches[0]


def _find_ref(refs: Sequence[Mapping[str, Any]], contract: str) -> Mapping[str, Any]:
    schema = CONTRACTS[contract][1]
    matches = [ref for ref in refs if ref.get("target_schema_name") == schema]
    if len(matches) != 1:
        raise PromotionVerificationError(
            VerificationErrorCode.EVIDENCE_MISSING,
            f"evidence must bind exactly one {contract}",
        )
    return matches[0]


def _same_ref(left: Any, right: Any) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    return all(
        left.get(field) == right.get(field)
        for field in ("target_schema_name", "target_id", "content_hash")
    )


def _same_ref_in_sequence(
    references: Sequence[Mapping[str, Any]], target: Any
) -> bool:
    return any(_same_ref(reference, target) for reference in references)


def _contains_label_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            key.lower() in {"label", "labels", "label_value", "outcome"}
            or _contains_label_field(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_label_field(child) for child in value)
    return False


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        _gate_mismatch(f"{field} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PromotionVerificationError(
            VerificationErrorCode.GATE_RECOMPUTATION_MISMATCH,
            f"{field} must be a finite decimal",
        ) from exc
    if not result.is_finite():
        _gate_mismatch(f"{field} must be a finite decimal")
    return result


def _integer(value: Any, field: str) -> int:
    if type(value) is not int:
        _gate_mismatch(f"{field} must be an integer")
    return value


def _utc(value: Any, code: VerificationErrorCode, field: str) -> datetime:
    if not isinstance(value, str):
        raise PromotionVerificationError(code, f"{field} must be a UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PromotionVerificationError(code, f"{field} must be a UTC instant") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise PromotionVerificationError(code, f"{field} must use UTC")
    return parsed.astimezone(UTC)


def _decode_b64url(value: Any) -> bytes:
    if not isinstance(value, str) or not value or "=" in value or not re.fullmatch(
        r"[A-Za-z0-9_-]+", value
    ):
        raise PromotionVerificationError(
            VerificationErrorCode.SIGNATURE_INVALID,
            "evaluator signature is not canonical base64url",
        )
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, base64.binascii.Error) as exc:
        raise PromotionVerificationError(
            VerificationErrorCode.SIGNATURE_INVALID,
            "evaluator signature is not valid base64url",
        ) from exc
    if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value:
        raise PromotionVerificationError(
            VerificationErrorCode.SIGNATURE_INVALID,
            "evaluator signature is not canonical base64url",
        )
    return decoded


def _canonical(value: Any) -> bytes:
    return canonical_json_bytes(_plain(value))


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _gate_mismatch(detail: str) -> None:
    raise PromotionVerificationError(
        VerificationErrorCode.GATE_RECOMPUTATION_MISMATCH, detail
    )
