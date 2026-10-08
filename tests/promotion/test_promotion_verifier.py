from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "promotion" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "candidate_evaluator" / "src"))

from qc2_candidate_evaluator.policy import policy_payload  # noqa: E402
from qc2_contracts.runtime import (  # noqa: E402
    CONTENT_ADDRESSED,
    CONTRACTS,
    SCHEMA_TO_CONTRACT,
    artifact_inventory_hash,
    canonical_content_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    validate_contract,
    verify_content_hash,
)
from qc2_promotion import (  # noqa: E402
    KeyRole,
    KeyRoleRegistry,
    PromotionVerificationError,
    PromotionVerificationPolicy,
    SandboxLimits,
    VerificationErrorCode,
    VerificationKey,
    build_promotion_bundle_archive,
    verify_promotion_bundle,
)
from qc2_promotion.verifier import _EVALUATION_ATTESTATION_PREFIX  # noqa: E402
from test_promotion_bundle import (  # noqa: E402
    LIMITS,
    NOW,
    _fixture_bundle,
    _valid_payloads,
)

PACKAGER_KEY_ID = "backend_packager_test"
EVALUATOR_KEY_ID = "independent_evaluator_test"
EVALUATOR_NAME = "independent_evaluator_test"
OWNER_KEY_ID = "registered_owner_test"
REPORT_SCHEMA = "qc2.promotion.CandidateEvaluationReport.v1"
ATTESTATION_SCHEMA = "qc2.promotion.CandidateEvaluationAttestation.v1"
EVALUATION_ARTIFACT_ID = "018f0000-0000-7000-8000-000000000002"
PACKAGER_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(b"p" * 32)
EVALUATOR_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(b"e" * 32)
OWNER_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(b"o" * 32)


def _contract_key(contract: str, identifier: str) -> tuple[str, str]:
    return CONTRACTS[contract][1], identifier


def _contract_doc(
    documents: dict[tuple[str, str], dict[str, Any]], contract: str
) -> dict[str, Any]:
    schema = CONTRACTS[contract][1]
    matches = [payload for (name, _), payload in documents.items() if name == schema]
    if len(matches) != 1:
        raise AssertionError(f"expected one {contract}, found {len(matches)}")
    return matches[0]


def _typed_refs(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if {"target_schema_name", "target_id"} <= set(value):
            found.append(value)
        else:
            for child in value.values():
                found.extend(_typed_refs(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_typed_refs(child))
    return found


def _sync_reference_hashes(
    value: Any, documents: dict[tuple[str, str], dict[str, Any]]
) -> None:
    if isinstance(value, dict):
        if {"target_schema_name", "target_id"} <= set(value):
            schema = value["target_schema_name"]
            target = documents.get((schema, value["target_id"]))
            contract = SCHEMA_TO_CONTRACT.get(schema)
            if target is None or contract is None:
                return
            target_hash = target.get(
                "content_hash", target.get("report_hash", target.get("receipt_hash"))
            )
            if target_hash is None:
                value.pop("content_hash", None)
            elif "content_hash" in value or contract in CONTENT_ADDRESSED:
                value["content_hash"] = target_hash
            return
        for child in value.values():
            _sync_reference_hashes(child, documents)
    elif isinstance(value, list):
        for child in value:
            _sync_reference_hashes(child, documents)


def _ref(payload: dict[str, Any], *, receipt_hash: bool = False) -> dict[str, Any]:
    schema = payload["schema_name"]
    contract = SCHEMA_TO_CONTRACT[schema]
    reference = {"target_schema_name": schema, "target_id": payload["id"]}
    digest = payload.get("content_hash")
    if receipt_hash:
        digest = payload.get("receipt_hash")
    if digest is not None and contract in CONTENT_ADDRESSED | {"HoldoutAccessReceipt"}:
        reference["content_hash"] = digest
    return reference


def _hash_document(
    key: tuple[str, str], documents: dict[tuple[str, str], dict[str, Any]]
) -> None:
    payload = documents[key]
    contract = SCHEMA_TO_CONTRACT[payload["schema_name"]]
    _sync_reference_hashes(payload, documents)
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash(contract, payload)


def _hash_ready_documents(
    documents: dict[tuple[str, str], dict[str, Any]],
    *,
    excluded: set[tuple[str, str]],
    already_hashed: set[tuple[str, str]] | None = None,
) -> set[tuple[str, str]]:
    addressable = {
        key
        for key, payload in documents.items()
        if SCHEMA_TO_CONTRACT[payload["schema_name"]] in CONTENT_ADDRESSED
    }
    done = set(already_hashed or ())
    pending = addressable - excluded - done
    while pending:
        ready = []
        for key in pending:
            dependencies = {
                (ref["target_schema_name"], ref["target_id"])
                for ref in _typed_refs(documents[key])
            }
            if all(dep not in addressable or dep in done for dep in dependencies):
                ready.append(key)
        if not ready:
            break
        for key in ready:
            _hash_document(key, documents)
            done.add(key)
            pending.remove(key)
    return done


def _file_record(path: str, schema: str, content: bytes) -> dict[str, Any]:
    return {
        "relative_path": path,
        "length_bytes": len(content),
        "media_type": "application/json",
        "schema_name": schema,
        "schema_version": "1.0",
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _make_gates(
    *,
    evaluated_at: str,
    source_refs: list[dict[str, Any]],
    evidence_class: str,
) -> list[dict[str, Any]]:
    gates = [
        ("heldout_leakage", "PASS", ["SEALED_MEMBERSHIP_AND_ROW_DISJOINTNESS_VERIFIED"]),
        (
            "deterministic_inference",
            "PASS",
            ["INDEPENDENT_SAFE_INTERPRETER_REPEATED_IDENTICALLY"],
        ),
        ("resource_budget", "PASS", ["OBSERVED_RESOURCE_USE_WITHIN_FROZEN_BUDGET"]),
        (
            "regression_performance",
            "PASS",
            ["RMSE_BEATS_FROZEN_ZERO_PREDICTION_BASELINE"],
        ),
        (
            "calibration",
            "WARN",
            ["CALIBRATION_NOT_APPLICABLE_TO_REGRESSION_TASK"],
        ),
        (
            "evidence_class",
            "UNKNOWN"
            if evidence_class in {"SYNTHETIC_FIXTURE", "HISTORICAL_RECONSTRUCTED"}
            else "PASS",
            ["NONFORWARD_EVIDENCE_CANNOT_QUALIFY_A_CANDIDATE"]
            if evidence_class in {"SYNTHETIC_FIXTURE", "HISTORICAL_RECONSTRUCTED"}
            else ["FORWARD_EVIDENCE_CLASS_RECORDED"],
        ),
        (
            "evaluator_policy",
            "PASS",
            ["CODE_OWNED_POLICY_HASH_MATCHES_NOMINATION"],
        ),
    ]
    return [
        {
            "gate_id": gate_id,
            "status": status,
            "reason_codes": reasons,
            "evaluated_at": evaluated_at,
            "source_refs": copy.deepcopy(source_refs),
        }
        for gate_id, status, reasons in gates
    ]


def _verifier_fixture(
    *,
    corrupt_report_gate: bool = False,
    unsafe_model: bool = False,
    label_mismatch: bool = False,
    future_shadow: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    manifest, original_files, evaluator_ref, owner_ref = _fixture_bundle()
    documents: dict[tuple[str, str], dict[str, Any]] = {}
    assets: dict[str, bytes] = {}
    for path, raw in original_files.items():
        value = json.loads(raw.decode("utf-8"))
        if value.get("schema_name") in SCHEMA_TO_CONTRACT:
            key = (value["schema_name"], value["id"])
            documents[key] = value
        else:
            assets[path] = raw
    resource_budget_payload = _valid_payloads()["ResourceBudget"]
    resource_budget_payload["source_refs"] = []
    documents[
        (resource_budget_payload["schema_name"], resource_budget_payload["id"])
    ] = resource_budget_payload

    candidate = _contract_doc(documents, "ModelManifest")
    dataset = _contract_doc(documents, "DatasetManifest")
    split = _contract_doc(documents, "SplitManifest")
    evaluation = _contract_doc(documents, "CandidateEvaluation")
    holdout = _contract_doc(documents, "HoldoutAccessReceipt")
    budget = _contract_doc(documents, "ResourceBudget")
    promotion_policy = _contract_doc(documents, "PromotionPolicy")
    label_registry = _contract_doc(documents, "LabelRegistry")
    label_definition = _contract_doc(documents, "LabelDefinition")
    model_artifact_manifest = _contract_doc(documents, "ArtifactManifest")
    owner = _contract_doc(documents, "OwnerDevice")
    run = _contract_doc(documents, "PredictionRun")
    seal = _contract_doc(documents, "PredictionSeal")
    replay = _contract_doc(documents, "ReplayReceipt")

    evaluation_artifact_manifest = copy.deepcopy(model_artifact_manifest)
    evaluation_artifact_manifest["id"] = EVALUATION_ARTIFACT_ID
    evaluation_artifact_manifest["files"] = []
    evaluation_artifact_manifest["inventory_hash"] = "0" * 64
    evaluation_artifact_manifest["content_hash"] = "0" * 64
    evaluation_artifact_key = (
        evaluation_artifact_manifest["schema_name"],
        evaluation_artifact_manifest["id"],
    )
    documents[evaluation_artifact_key] = evaluation_artifact_manifest

    owner_public_key = OWNER_PRIVATE_KEY.public_key().public_bytes_raw()
    owner["owner_key_id"] = OWNER_KEY_ID
    owner["public_key"] = base64.urlsafe_b64encode(owner_public_key).decode("ascii").rstrip("=")
    owner_ref = _ref(owner)

    candidate["safe_format"] = "json"
    candidate["algorithm"] = "linear_regression"
    candidate["algorithm_version"] = "scikit-learn==1.9.1"
    candidate["ordered_feature_ids"] = ["fixture"]
    candidate["training_start"] = "2026-10-05"
    candidate["training_cutoff"] = "2026-10-07T20:00:00Z"
    candidate["validation_window"] = json.dumps(
        {"fold_id": "fixture-fold", "released_row_keys": ["validation-1"]},
        sort_keys=True,
        separators=(",", ":"),
    )
    candidate["qualification_window"] = json.dumps(
        {"sessions": ["2026-10-08"], "labels_released": False},
        sort_keys=True,
        separators=(",", ":"),
    )
    candidate["target_label_refs"] = [_ref(label_definition)]
    if label_mismatch:
        candidate["target_label_refs"] = []

    manifest["created_at"] = NOW
    manifest["expires_at"] = "2026-10-08T20:30:00Z"
    manifest["registry_refs"] = copy.deepcopy(manifest["registry_refs"])
    dataset["registry_refs"] = copy.deepcopy(manifest["registry_refs"])
    label_registry["definition_refs"] = [_ref(label_definition)]
    label_registry["primary_label_ref"] = _ref(label_definition)
    promotion_policy["permitted_artifact_types"] = ["json"]
    promotion_policy["epoch_modes"] = [manifest["mode"]]
    promotion_policy["frozen_at"] = "2026-10-05T20:00:00Z"
    budget.update(
        {
            "fixture_only": False,
            "max_elapsed_seconds": 120,
            "max_cpu_seconds": 120,
            "max_memory_bytes": 1_000_000_000,
            "max_artifact_bytes": 1_000_000,
        }
    )
    evaluation.update(
        {
            "created_at": NOW,
            "evaluated_at": NOW,
            "evaluator_identity": EVALUATOR_NAME,
        }
    )
    holdout.update(
        {
            "created_at": NOW,
            "evaluator_identity": EVALUATOR_NAME,
            "access_scope": "METRICS_ONLY",
            "requested_at": NOW,
            "granted_at": NOW,
            "consumed_fields": ["aggregate_metrics"],
            "released_metrics": [
                "observation_count",
                "rmse",
                "mae",
                "zero_baseline_rmse",
                "rmse_skill_vs_zero",
            ],
        }
    )
    holdout["receipt_hash"] = domain_separated_sha256(
        "qc2.candidate-evaluator-holdout.v1",
        canonical_json_bytes(
            {key: value for key, value in holdout.items() if key != "receipt_hash"}
        ),
    )
    run.update(
        {
            "created_at": NOW,
            "session_id": "2026-10-09" if future_shadow else "2026-10-08",
            "decision_deadline": NOW,
            "seal_deadline": NOW,
        }
    )
    seal.update(
        {
            "created_at": NOW,
            "session_id": run["session_id"],
            "sealed_at": NOW,
            "deadline": NOW,
        }
    )
    replay.update(
        {
            "expected_hash": "c" * 64,
            "actual_hash": "c" * 64,
            "expected_count": 2,
            "actual_count": 2,
            "environment_fingerprint": "0" * 64,
            "first_mismatch": None,
            "verdict": "MATCH",
        }
    )

    environment = {
        "schema_name": "qc2.apexlab.TrainingEnvironment.v1",
        "schema_version": "1.0",
        "python_version": "3.13.11",
        "python_implementation": "CPython",
        "platform": "test-platform",
        "package_lock_hash": "b" * 64,
        "packages": {
            "scikit-learn": "1.9.1",
            "xgboost": "3.4.1",
            "numpy": "2.3.0",
            "scipy": "1.16.0",
        },
        "native_threads_per_job": 1,
        "worker_isolation": "allowlisted_environment_with_os_resource_limits",
    }
    environment_fingerprint = hashlib.sha256(canonical_json_bytes(environment)).hexdigest()
    candidate["environment_fingerprint"] = environment_fingerprint
    candidate["package_lock_hash"] = environment["package_lock_hash"]
    manifest["environment_fingerprint"] = environment_fingerprint
    replay["environment_fingerprint"] = environment_fingerprint

    model_key = (candidate["schema_name"], candidate["id"])
    artifact_key = (
        model_artifact_manifest["schema_name"],
        model_artifact_manifest["id"],
    )
    excluded = {model_key, artifact_key, evaluation_artifact_key}
    hashed = _hash_ready_documents(documents, excluded=excluded)
    _sync_reference_hashes(holdout, documents)
    holdout["receipt_hash"] = domain_separated_sha256(
        "qc2.candidate-evaluator-holdout.v1",
        canonical_json_bytes(
            {key: value for key, value in holdout.items() if key != "receipt_hash"}
        ),
    )
    dataset_ref = _ref(dataset)
    split_ref = _ref(split)
    feature_ids = ["fixture"]
    train_keys = ["train-1", "train-2"]
    model_artifact: dict[str, Any] = {
        "schema_name": "qc2.apexlab.SafeModelArtifact.v1",
        "schema_version": "1.0",
        "model_id": candidate["id"],
        "family": "linear_regression",
        "task": "REGRESSION",
        "seed": 0,
        "parameters": {"alpha": "1"},
        "feature_ids": feature_ids,
        "estimator_state": {
            "kind": "linear_coefficients",
            "classes": [],
            "coefficient_matrix": ["2"],
            "intercept": "1",
            "n_features_in": 1,
        },
        "preprocessing_lineage": {
            "transform_hash": "c" * 64,
            "fit_row_keys": train_keys,
            "fit_cutoff": "2026-10-07T20:00:00Z",
            "means": ["0"],
            "scales": ["1"],
            "feature_order": feature_ids,
        },
        "calibration_lineage": {
            "state": "NOT_APPLIED",
            "reason_code": "CALIBRATION_OUTSIDE_MODEL_FACTORY_SCOPE",
            "calibration_ref": None,
        },
        "dataset_ref": dataset_ref,
        "split_ref": split_ref,
        "fold_id": "fixture-fold",
        "training_index_hash": "d" * 64,
        "training_row_keys": train_keys,
        "validation_row_keys": ["validation-1"],
        "environment_fingerprint": environment_fingerprint,
    }
    if unsafe_model:
        model_artifact["python_entry_point"] = "candidate.py"
    model_bytes = canonical_json_bytes(model_artifact)
    environment_bytes = canonical_json_bytes(environment)
    assets = {
        f"artifacts/{model_artifact_manifest['id']}/model.json": model_bytes,
        f"artifacts/{model_artifact_manifest['id']}/environment.json": environment_bytes,
    }
    model_artifact_manifest["files"] = [
        _file_record("model.json", model_artifact["schema_name"], model_bytes),
        _file_record("environment.json", environment["schema_name"], environment_bytes),
    ]
    model_artifact_manifest["inventory_hash"] = artifact_inventory_hash(
        model_artifact_manifest["files"]
    )
    _hash_document(artifact_key, documents)
    _sync_reference_hashes(candidate, documents)
    _hash_document(model_key, documents)

    evaluation_ref = _ref(evaluation)
    candidate_ref = _ref(candidate)
    holdout_ref = _ref(holdout, receipt_hash=True)
    budget_ref = _ref(budget)
    source_refs = [
        candidate_ref,
        dataset_ref,
        split_ref,
        holdout_ref,
        budget_ref,
    ]
    metrics = {
        "observation_count": "2",
        "rmse": "0.5",
        "mae": "0.5",
        "zero_baseline_rmse": "1",
        "rmse_skill_vs_zero": "0.5",
    }
    resource_usage = {
        "elapsed_seconds": "0.2",
        "cpu_seconds": "0.1",
        "peak_memory_bytes": 16_000_000,
        "artifact_bytes": len(model_bytes) + len(environment_bytes),
    }
    gates = _make_gates(
        evaluated_at=NOW,
        source_refs=source_refs,
        evidence_class=dataset["evidence_class"],
    )
    if corrupt_report_gate:
        report_gates = copy.deepcopy(gates)
        report_gates[5]["status"] = "PASS"
    else:
        report_gates = copy.deepcopy(gates)
    evaluation_status = "INSUFFICIENT_EVIDENCE"
    report_payload = {
        "schema_name": REPORT_SCHEMA,
        "schema_version": "1.0",
        "policy": policy_payload(),
        "candidate_ref": candidate_ref,
        "dataset_ref": dataset_ref,
        "split_ref": split_ref,
        "holdout_receipt_ref": holdout_ref,
        "evidence_class": dataset["evidence_class"],
        "evaluation_status": evaluation_status,
        "qualification_row_count": 2,
        "metrics": metrics,
        "resource_usage": resource_usage,
        "gate_results": report_gates,
        "holdout_open_event_hash": "f" * 64,
    }
    report_hash = hashlib.sha256(canonical_json_bytes(report_payload)).hexdigest()
    report_payload["report_hash"] = report_hash
    signature_statement = {
        "role": "independent_evaluator",
        "evaluator_identity": EVALUATOR_NAME,
        "key_id": EVALUATOR_KEY_ID,
        "report_hash": report_hash,
    }
    report_signature = EVALUATOR_PRIVATE_KEY.sign(
        _EVALUATION_ATTESTATION_PREFIX + canonical_json_bytes(signature_statement)
    )
    attestation = {
        "schema_name": ATTESTATION_SCHEMA,
        "schema_version": "1.0",
        "evaluator_identity": EVALUATOR_NAME,
        "evaluator_key_id": EVALUATOR_KEY_ID,
        "report_hash": report_hash,
        "signature_algorithm": "Ed25519",
        "encoding": "base64url-no-padding",
        "signature": base64.urlsafe_b64encode(report_signature)
        .decode("ascii")
        .rstrip("="),
    }
    report_bytes = canonical_json_bytes(report_payload)
    attestation_bytes = canonical_json_bytes(attestation)
    evaluation_assets = {
        f"artifacts/{evaluation_artifact_manifest['id']}/candidate-evaluation-report.json":
            report_bytes,
        f"artifacts/{evaluation_artifact_manifest['id']}/candidate-evaluation-attestation.json":
            attestation_bytes,
    }
    evaluation_artifact_manifest["files"] = [
        _file_record("candidate-evaluation-report.json", REPORT_SCHEMA, report_bytes),
        _file_record(
            "candidate-evaluation-attestation.json", ATTESTATION_SCHEMA, attestation_bytes
        ),
    ]
    evaluation_artifact_manifest["inventory_hash"] = artifact_inventory_hash(
        evaluation_artifact_manifest["files"]
    )
    _hash_document(evaluation_artifact_key, documents)
    evaluation_artifact_ref = _ref(evaluation_artifact_manifest)
    evaluation.update(
        {
            "candidate_ref": candidate_ref,
            "dataset_ref": dataset_ref,
            "split_ref": split_ref,
            "evaluator_identity": EVALUATOR_NAME,
            "source_refs": [
                *source_refs,
                evaluation_artifact_ref,
            ],
            "gate_results": gates,
            "evaluated_at": NOW,
            "verdict": evaluation_status,
            "report_hash": report_hash,
        }
    )
    manifest["evaluation_refs"] = [evaluation_ref]
    manifest["holdout_receipt_refs"] = [holdout_ref]
    manifest["gate_results"] = gates
    manifest["shadow_seal_refs"] = [_ref(seal)]
    manifest["replay_report_ref"] = _ref(replay)
    manifest["policy_ref"] = _ref(promotion_policy)
    manifest["candidate_model_ref"] = candidate_ref
    manifest["dataset_ref"] = dataset_ref
    manifest["split_ref"] = split_ref
    manifest["content_hash"] = "0" * 64
    manifest["content_hash"] = canonical_content_hash(
        "PromotionBundleManifest", manifest
    )

    hashed = _hash_ready_documents(
        documents,
        excluded=set(),
        already_hashed=hashed | {artifact_key, model_key, evaluation_artifact_key},
    )
    for key, payload in documents.items():
        _sync_reference_hashes(payload, documents)
        contract = SCHEMA_TO_CONTRACT[payload["schema_name"]]
        validate_contract(contract, payload)
        if contract in CONTENT_ADDRESSED:
            verify_content_hash(contract, payload)
    _sync_reference_hashes(manifest, documents)
    manifest["content_hash"] = canonical_content_hash("PromotionBundleManifest", manifest)
    validate_contract("PromotionBundleManifest", manifest)
    verify_content_hash("PromotionBundleManifest", manifest)

    files = {
        f"evidence/{SCHEMA_TO_CONTRACT[schema]}/{identifier}.json":
            canonical_json_bytes(payload)
        for (schema, identifier), payload in documents.items()
    }
    files.update(assets)
    files.update(evaluation_assets)
    owner_ref = _ref(owner)
    evaluator_ref = _ref(evaluation)
    archive = build_promotion_bundle_archive(
        manifest,
        files,
        signing_key=PACKAGER_PRIVATE_KEY,
        signing_key_id=PACKAGER_KEY_ID,
        evaluator_ref=evaluator_ref,
        owner_device_ref=owner_ref,
        now=NOW,
        limits=LIMITS,
    )
    return archive, {
        "policy_hash": promotion_policy["content_hash"],
        "owner_public_key": owner_public_key,
        "manifest": manifest,
    }


def _registry(
    *,
    packager_role: KeyRole = KeyRole.ARTIFACT_PACKAGER,
    revoke_evaluator: bool = False,
    include_packager: bool = True,
) -> KeyRoleRegistry:
    records = [
        VerificationKey(
            key_id=EVALUATOR_KEY_ID,
            role=KeyRole.INDEPENDENT_EVALUATOR,
            public_key=EVALUATOR_PRIVATE_KEY.public_key().public_bytes_raw(),
            valid_from="2026-10-01T00:00:00Z",
            identity=EVALUATOR_NAME,
            revoked_at=NOW if revoke_evaluator else None,
        ),
        VerificationKey(
            key_id=OWNER_KEY_ID,
            role=KeyRole.OWNER_IDENTITY,
            public_key=OWNER_PRIVATE_KEY.public_key().public_bytes_raw(),
            valid_from="2026-10-01T00:00:00Z",
        ),
    ]
    if include_packager:
        records.append(
            VerificationKey(
                key_id=PACKAGER_KEY_ID,
                role=packager_role,
                public_key=PACKAGER_PRIVATE_KEY.public_key().public_bytes_raw(),
                valid_from="2026-10-01T00:00:00Z",
                identity=(
                    "wrong-packager-role"
                    if packager_role is KeyRole.INDEPENDENT_EVALUATOR
                    else None
                ),
            )
        )
    return KeyRoleRegistry(records)


def _policy(policy_hash: str) -> PromotionVerificationPolicy:
    return PromotionVerificationPolicy(
        trusted_promotion_policy_hashes=frozenset({policy_hash}),
        max_evidence_age_seconds=14 * 24 * 60 * 60,
        sandbox_limits=SandboxLimits(
            max_wall_seconds=20,
            max_cpu_seconds=10,
            max_memory_bytes=1_000_000_000,
        ),
    )


def test_independent_verification_recomputes_gates_and_safely_probes_model() -> None:
    archive, fixture = _verifier_fixture()
    result = verify_promotion_bundle(
        archive,
        key_registry=_registry(),
        now=NOW,
        limits=LIMITS,
        policy=_policy(fixture["policy_hash"]),
    )

    assert result.model_probe.task == "REGRESSION"
    assert result.model_probe.deterministic is True
    assert [gate.gate_id for gate in result.gate_receipts] == [
        "heldout_leakage",
        "deterministic_inference",
        "resource_budget",
        "regression_performance",
        "calibration",
        "evidence_class",
        "evaluator_policy",
    ]
    assert result.gate_receipts[5].status == "UNKNOWN"
    assert result.eligible_for_owner_review is False


@pytest.mark.parametrize(
    ("registry_kwargs", "expected"),
    [
        (
            {"include_packager": False},
            VerificationErrorCode.KEY_UNKNOWN,
        ),
        (
            {"packager_role": KeyRole.INDEPENDENT_EVALUATOR},
            VerificationErrorCode.KEY_ROLE_MISMATCH,
        ),
        (
            {"revoke_evaluator": True},
            VerificationErrorCode.KEY_REVOKED,
        ),
    ],
)
def test_key_registry_enforces_unknown_roles_and_revocations(
    registry_kwargs: dict[str, Any], expected: VerificationErrorCode
) -> None:
    archive, fixture = _verifier_fixture()
    with pytest.raises(PromotionVerificationError) as raised:
        verify_promotion_bundle(
            archive,
            key_registry=_registry(**registry_kwargs),
            now=NOW,
            limits=LIMITS,
            policy=_policy(fixture["policy_hash"]),
        )
    assert raised.value.code is expected


def test_signed_but_inconsistent_gate_report_is_rejected() -> None:
    archive, fixture = _verifier_fixture(corrupt_report_gate=True)
    with pytest.raises(PromotionVerificationError) as raised:
        verify_promotion_bundle(
            archive,
            key_registry=_registry(),
            now=NOW,
            limits=LIMITS,
            policy=_policy(fixture["policy_hash"]),
        )
    assert raised.value.code is VerificationErrorCode.GATE_RECOMPUTATION_MISMATCH


@pytest.mark.parametrize(
    ("fixture_kwargs", "expected"),
    [
        ({"unsafe_model": True}, VerificationErrorCode.MODEL_UNSAFE),
        ({"label_mismatch": True}, VerificationErrorCode.LABEL_MISMATCH),
        ({"future_shadow": True}, VerificationErrorCode.TEMPORAL_VIOLATION),
    ],
)
def test_unsafe_or_incompatible_evidence_is_rejected(
    fixture_kwargs: dict[str, Any], expected: VerificationErrorCode
) -> None:
    archive, fixture = _verifier_fixture(**fixture_kwargs)
    with pytest.raises(PromotionVerificationError) as raised:
        verify_promotion_bundle(
            archive,
            key_registry=_registry(),
            now=NOW,
            limits=LIMITS,
            policy=_policy(fixture["policy_hash"]),
        )
    assert raised.value.code is expected
