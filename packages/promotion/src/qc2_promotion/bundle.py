"""Content-addressed promotion bundle packaging and detached signature checks."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from qc2_contracts.runtime import (
    CONTENT_ADDRESSED,
    CONTRACTS,
    SCHEMA_TO_CONTRACT,
    ContractValidationError,
    artifact_inventory_hash,
    canonical_content_hash,
    canonical_json_bytes,
    parse_json_strict,
    validate_contract,
    verify_content_hash,
)

from .archive import decode_archive, encode_archive, validate_relative_path
from .limits import BundleLimits, PromotionBundleError

SIGNATURE_PROFILE = "QC2-PROMOTION-BUNDLE-SIGNATURE-V1"
SIGNATURE_PREFIX = b"QC2-PROMOTION-BUNDLE-SIGNATURE-V1\x00"
SIGNATURE_ALGORITHM = "Ed25519"
SIGNATURE_ENCODING = "base64url-no-padding"
PACKAGER_ROLE = "artifact_packager"
EVALUATOR_ROLE = "independent_evaluator"
OWNER_ROLE = "owner_identity"
SAFE_ARTIFACT_SCHEMAS = frozenset(
    {
        "qc2.apexlab.SafeModelArtifact.v1",
        "qc2.apexlab.TrainingEnvironment.v1",
        "qc2.apexlab.FrozenHyperparameterSpace.v1",
    }
)
EXPECTED_REGISTRY_CONTRACTS = frozenset(
    {"FeatureRegistry", "RunnerProtocolRegistry", "LabelRegistry", "ScoreManifest", "BaselineManifest"}
)
MAX_KEY_ID_LENGTH = 64
_KEY_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


@dataclass(frozen=True, slots=True)
class VerifiedPromotionBundle:
    """Integrity-verified package. This is not an eligibility or approval result."""

    manifest: Mapping[str, Any]
    inventory: tuple[Mapping[str, Any], ...]
    files: Mapping[str, bytes]
    artifact_signer_key_id: str
    evaluator_identity: Mapping[str, Any]
    owner_identity: Mapping[str, Any]


def build_promotion_bundle_archive(
    raw_manifest: Mapping[str, Any],
    dependency_files: Mapping[str, bytes],
    *,
    signing_key: Ed25519PrivateKey,
    signing_key_id: str,
    evaluator_ref: Mapping[str, Any],
    owner_device_ref: Mapping[str, Any],
    now: str,
    limits: BundleLimits,
) -> bytes:
    """Seal immutable dependency bytes, compute the manifest hash, and sign detached."""
    try:
        if not isinstance(signing_key, Ed25519PrivateKey):
            raise PromotionBundleError("a backend Ed25519 private key is required")
        _validate_key_id(signing_key_id)
        manifest = _thaw_json(raw_manifest)
        if not isinstance(manifest, dict):
            raise PromotionBundleError("PromotionBundleManifest must be a JSON object")
        if not isinstance(dependency_files, Mapping) or not dependency_files:
            raise PromotionBundleError("promotion bundle dependencies must be a non-empty path map")
        files = dict(dependency_files)
        inventory, documents, assets = _build_inventory(files, limits)
        manifest["inventory_hash"] = artifact_inventory_hash(inventory)
        manifest["content_hash"] = "0" * 64
        manifest["content_hash"] = canonical_content_hash("PromotionBundleManifest", manifest)
        _validate_manifest(manifest, inventory, now, limits)
        index = _verify_dependency_graph(
            manifest,
            documents,
            assets,
            evaluator_ref=evaluator_ref,
            owner_device_ref=owner_device_ref,
        )
        evaluator_identity, owner_identity = _identity_bindings(
            manifest,
            index,
            evaluator_ref=evaluator_ref,
            owner_device_ref=owner_device_ref,
        )
        artifact_signer = {"role": PACKAGER_ROLE, "key_id": signing_key_id}
        statement = _signature_statement(
            manifest,
            artifact_signer,
            evaluator_identity,
            owner_identity,
        )
        signature = {
            **statement,
            "signature": _b64url_encode(signing_key.sign(_signature_message(statement))),
        }
        return encode_archive(manifest, inventory, signature, files, limits)
    except PromotionBundleError:
        raise
    except (ContractValidationError, KeyError, TypeError, ValueError) as exc:
        raise PromotionBundleError(f"promotion bundle could not be built: {exc}") from exc


def verify_promotion_bundle_archive(
    archive_bytes: bytes,
    *,
    trusted_backend_public_keys: Mapping[str, bytes],
    now: str,
    limits: BundleLimits,
) -> VerifiedPromotionBundle:
    """Verify archive safety, exact inventory, contract references, expiry, and signature."""
    try:
        manifest, inventory, signature, files = decode_archive(archive_bytes, limits)
        _validate_inventory(inventory, files, limits)
        _validate_manifest(manifest, inventory, now, limits)
        artifact_signer, evaluator_identity, owner_identity = _parse_signature(signature)
        key_id = artifact_signer["key_id"]
        if not isinstance(trusted_backend_public_keys, Mapping) or key_id not in trusted_backend_public_keys:
            raise PromotionBundleError("bundle signer key is unknown or not trusted")
        raw_public_key = trusted_backend_public_keys[key_id]
        if not isinstance(raw_public_key, bytes) or len(raw_public_key) != 32:
            raise PromotionBundleError("trusted Ed25519 public key must be 32 raw bytes")
        public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
        statement = _signature_statement(
            manifest,
            artifact_signer,
            evaluator_identity,
            owner_identity,
        )
        if any(signature.get(key) != value for key, value in statement.items()):
            raise PromotionBundleError("detached signature envelope does not match the signed manifest")
        try:
            public_key.verify(
                _b64url_decode(signature["signature"]),
                _signature_message(statement),
            )
        except InvalidSignature as exc:
            raise PromotionBundleError("promotion bundle detached signature did not verify") from exc

        index = _verify_dependency_graph(
            manifest,
            _contract_documents(files),
            _safe_assets(files),
            evaluator_ref=evaluator_identity["reference"],
            owner_device_ref=owner_identity["reference"],
        )
        expected_evaluator, expected_owner = _identity_bindings(
            manifest,
            index,
            evaluator_ref=evaluator_identity["reference"],
            owner_device_ref=owner_identity["reference"],
        )
        if expected_evaluator != evaluator_identity or expected_owner != owner_identity:
            raise PromotionBundleError("identity bindings do not match their immutable dependencies")
        frozen_manifest = _freeze_json(manifest)
        frozen_inventory = tuple(_freeze_json(record) for record in inventory)
        frozen_files = MappingProxyType({path: bytes(content) for path, content in files.items()})
        return VerifiedPromotionBundle(
            manifest=frozen_manifest,
            inventory=frozen_inventory,
            files=frozen_files,
            artifact_signer_key_id=key_id,
            evaluator_identity=_freeze_json(evaluator_identity),
            owner_identity=_freeze_json(owner_identity),
        )
    except PromotionBundleError:
        raise
    except (ContractValidationError, KeyError, TypeError, ValueError) as exc:
        raise PromotionBundleError(f"promotion bundle verification failed: {exc}") from exc


def _build_inventory(
    files: Mapping[str, bytes],
    limits: BundleLimits,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    if len(files) + 3 > limits.max_entries:
        raise PromotionBundleError("bundle exceeds its explicit entry-count limit")
    inventory: list[dict[str, Any]] = []
    documents: dict[tuple[str, str], dict[str, Any]] = {}
    assets: dict[str, dict[str, Any]] = {}
    seen_normalized: set[str] = set()
    total_bytes = 0
    for path, content in files.items():
        validate_relative_path(path)
        if path in seen_normalized or not isinstance(content, bytes):
            raise PromotionBundleError("dependency paths must be unique and map to immutable bytes")
        seen_normalized.add(path)
        if not path.endswith(".json"):
            raise PromotionBundleError("only strict JSON evidence and allowlisted model data are accepted")
        if len(content) > limits.max_file_bytes:
            raise PromotionBundleError("dependency exceeds its explicit per-file size limit")
        total_bytes += len(content)
        if total_bytes > limits.max_uncompressed_bytes:
            raise PromotionBundleError("dependencies exceed the explicit unpacked-size limit")
        payload = _parse_payload(content, path)
        schema_name = payload.get("schema_name")
        schema_version = payload.get("schema_version")
        if not isinstance(schema_name, str) or not isinstance(schema_version, str):
            raise PromotionBundleError(f"{path} lacks strict schema metadata")
        if schema_name in SCHEMA_TO_CONTRACT:
            contract_name = SCHEMA_TO_CONTRACT[schema_name]
            validate_contract(contract_name, payload)
            _verify_contract_hash(contract_name, payload)
            identity = (schema_name, payload["id"])
            if identity in documents:
                raise PromotionBundleError("dependency inventory repeats a contract identity")
            documents[identity] = payload
        elif schema_name in SAFE_ARTIFACT_SCHEMAS and schema_version == "1.0":
            assets[path] = payload
        else:
            raise PromotionBundleError(f"{path} is not a known QC2 contract or safe model JSON schema")
        inventory.append(
            {
                "relative_path": path,
                "length_bytes": len(content),
                "media_type": "application/json",
                "schema_name": schema_name,
                "schema_version": schema_version,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    inventory.sort(key=lambda row: row["relative_path"].encode("utf-8"))
    return inventory, documents, assets


def _validate_inventory(
    inventory: list[dict[str, Any]],
    files: Mapping[str, bytes],
    limits: BundleLimits,
) -> None:
    if not inventory or len(inventory) + 3 > limits.max_entries:
        raise PromotionBundleError("signed inventory is empty or exceeds its entry-count limit")
    try:
        expected_hash = artifact_inventory_hash(inventory)
    except (ContractValidationError, KeyError, TypeError, ValueError) as exc:
        raise PromotionBundleError(f"signed inventory is invalid: {exc}") from exc
    seen: set[str] = set()
    total = 0
    for record in inventory:
        if not isinstance(record, dict) or set(record) != {
            "relative_path",
            "length_bytes",
            "media_type",
            "schema_name",
            "schema_version",
            "sha256",
        }:
            raise PromotionBundleError("inventory records must have exactly the QC2 artifact fields")
        path = validate_relative_path(record["relative_path"])
        if path in seen:
            raise PromotionBundleError("signed inventory repeats a normalized path")
        seen.add(path)
        content = files.get(path)
        if not isinstance(content, bytes):
            raise PromotionBundleError("signed inventory has a missing payload file")
        if (
            record["media_type"] != "application/json"
            or record["length_bytes"] != len(content)
            or len(content) > limits.max_file_bytes
            or record["sha256"] != hashlib.sha256(content).hexdigest()
        ):
            raise PromotionBundleError(f"payload bytes, path, or size differ from inventory: {path}")
        payload = _parse_payload(content, path)
        if (
            payload.get("schema_name") != record["schema_name"]
            or payload.get("schema_version") != record["schema_version"]
        ):
            raise PromotionBundleError(f"payload schema differs from inventory: {path}")
        total += len(content)
        if total > limits.max_uncompressed_bytes:
            raise PromotionBundleError("dependencies exceed the explicit unpacked-size limit")
    if seen != set(files):
        raise PromotionBundleError("payload set differs from the signed inventory")
    # The value is recomputed here to reject malformed file records before manifest validation.
    if not isinstance(expected_hash, str):
        raise PromotionBundleError("signed inventory hash could not be computed")


def _validate_manifest(
    manifest: Mapping[str, Any],
    inventory: list[dict[str, Any]],
    now: str,
    limits: BundleLimits,
) -> None:
    if not isinstance(manifest, Mapping):
        raise PromotionBundleError("PromotionBundleManifest must be a JSON object")
    value = dict(manifest)
    try:
        validate_contract("PromotionBundleManifest", value)
        verify_content_hash("PromotionBundleManifest", value)
    except (ContractValidationError, TypeError, ValueError, KeyError) as exc:
        raise PromotionBundleError(f"PromotionBundleManifest verification failed: {exc}") from exc
    if value["inventory_hash"] != artifact_inventory_hash(inventory):
        raise PromotionBundleError("manifest inventory_hash does not match its signed inventory")
    required_registries = {
        CONTRACTS[name][1] for name in EXPECTED_REGISTRY_CONTRACTS
    }
    supplied_registries = [ref["target_schema_name"] for ref in value["registry_refs"]]
    if set(supplied_registries) != required_registries or len(supplied_registries) != len(required_registries):
        raise PromotionBundleError("bundle must reference each required registry exactly once")
    for field in ("holdout_receipt_refs", "evaluation_refs", "shadow_seal_refs", "gate_results"):
        if not value[field]:
            raise PromotionBundleError(f"promotion bundle is missing required {field}")
    created_at = _parse_utc(value["created_at"], "manifest created_at")
    expires_at = _parse_utc(value["expires_at"], "manifest expires_at")
    current = _parse_utc(now, "verification time")
    if expires_at <= created_at or expires_at <= current or created_at > current:
        raise PromotionBundleError("promotion bundle is not currently within its signed expiry interval")
    lifetime = (expires_at - created_at).total_seconds()
    if lifetime > limits.max_lifetime_seconds:
        raise PromotionBundleError("promotion bundle lifetime exceeds the explicit expiry policy")


def _verify_dependency_graph(
    manifest: Mapping[str, Any],
    documents: Mapping[tuple[str, str], dict[str, Any]],
    assets: Mapping[str, dict[str, Any]],
    *,
    evaluator_ref: Mapping[str, Any],
    owner_device_ref: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(evaluator_ref, Mapping) or dict(evaluator_ref) not in manifest["evaluation_refs"]:
        raise PromotionBundleError("evaluator identity must bind one declared evaluation report")
    if not isinstance(owner_device_ref, Mapping):
        raise PromotionBundleError("owner identity must reference a registered OwnerDevice")
    owner_schema = CONTRACTS["OwnerDevice"][1]
    if owner_device_ref.get("target_schema_name") != owner_schema:
        raise PromotionBundleError("owner identity binding must reference an OwnerDevice")
    root_refs = list(_typed_refs(manifest))
    root_refs.extend((dict(evaluator_ref), dict(owner_device_ref)))
    visited: set[tuple[str, str]] = set()
    pending = root_refs[:]
    while pending:
        reference = pending.pop()
        schema_name = reference.get("target_schema_name")
        target_id = reference.get("target_id")
        if not isinstance(schema_name, str) or not isinstance(target_id, str):
            raise PromotionBundleError("dependency reference has invalid identity fields")
        identity = (schema_name, target_id)
        payload = documents.get(identity)
        if payload is None:
            raise PromotionBundleError(
                f"bundle is missing immutable dependency {schema_name} {target_id}"
            )
        contract_name = SCHEMA_TO_CONTRACT[schema_name]
        expected_hash = payload.get("content_hash", payload.get("report_hash"))
        referenced_hash = reference.get("content_hash")
        if contract_name in CONTENT_ADDRESSED and referenced_hash != payload.get("content_hash"):
            raise PromotionBundleError(f"dependency content hash differs for {schema_name}")
        if referenced_hash is not None and referenced_hash != expected_hash:
            raise PromotionBundleError(f"dependency reference hash differs for {schema_name}")
        if identity not in visited:
            visited.add(identity)
            pending.extend(_typed_refs(payload))

    if visited != set(documents):
        extras = sorted(schema_name for schema_name, _ in set(documents) - visited)
        raise PromotionBundleError(f"inventory contains unreferenced contract payloads: {extras}")

    expected_assets: set[str] = set()
    for identity in visited:
        payload = documents[identity]
        contract_name = SCHEMA_TO_CONTRACT[payload["schema_name"]]
        if contract_name != "ArtifactManifest":
            continue
        try:
            verify_content_hash("ArtifactManifest", payload)
        except (ContractValidationError, KeyError, TypeError, ValueError) as exc:
            raise PromotionBundleError(f"ArtifactManifest inventory is invalid: {exc}") from exc
        for record in payload["files"]:
            path = validate_relative_path(record["relative_path"])
            archive_path = f"artifacts/{payload['id']}/{path}"
            validate_relative_path(archive_path)
            if archive_path in expected_assets:
                raise PromotionBundleError("two ArtifactManifests claim the same model file")
            expected_assets.add(archive_path)
            content = _dependency_bytes_for_asset(archive_path, assets)
            if len(content) != record["length_bytes"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
                raise PromotionBundleError(f"artifact file bytes differ from ArtifactManifest: {archive_path}")
            if record["media_type"] != "application/json" or record["schema_name"] not in SAFE_ARTIFACT_SCHEMAS:
                raise PromotionBundleError("ArtifactManifest contains a disallowed file type or schema")
            payload_file = assets[archive_path]
            if (
                payload_file.get("schema_name") != record["schema_name"]
                or payload_file.get("schema_version") != record["schema_version"]
            ):
                raise PromotionBundleError("artifact JSON schema metadata differs from its manifest")

    if expected_assets != set(assets):
        raise PromotionBundleError("archive contains missing or unlisted model artifact files")

    candidate_ref = manifest["candidate_model_ref"]
    candidate = documents[(candidate_ref["target_schema_name"], candidate_ref["target_id"])]
    if candidate.get("safe_format") != "json":
        raise PromotionBundleError("candidate model artifact format is not on the safe JSON allowlist")
    if candidate.get("environment_fingerprint") != manifest["environment_fingerprint"]:
        raise PromotionBundleError("candidate environment fingerprint differs from the bundle")
    if not _references_equal(candidate.get("dataset_ref"), manifest.get("dataset_ref")):
        raise PromotionBundleError("candidate model and bundle refer to different datasets")
    if not _references_equal(candidate.get("split_ref"), manifest.get("split_ref")):
        raise PromotionBundleError("candidate model and bundle refer to different data splits")
    feature_registry = _find_registry_ref(manifest["registry_refs"], "FeatureRegistry")
    runner_registry = _find_registry_ref(manifest["registry_refs"], "RunnerProtocolRegistry")
    if not _references_equal(candidate.get("feature_registry_ref"), feature_registry):
        raise PromotionBundleError("candidate model and bundle refer to different feature registries")
    if not _references_equal(candidate.get("protocol_registry_ref"), runner_registry):
        raise PromotionBundleError("candidate model and bundle refer to different protocol registries")

    main_artifact_ref = candidate.get("artifact_manifest_ref", {})
    main_artifact = documents[
        (main_artifact_ref["target_schema_name"], main_artifact_ref["target_id"])
    ]
    main_names = {record["relative_path"] for record in main_artifact["files"]}
    if main_names != {"model.json", "environment.json"}:
        raise PromotionBundleError("candidate artifact must contain exactly model.json and environment.json")
    environment_path = f"artifacts/{main_artifact['id']}/environment.json"
    environment = assets.get(environment_path)
    if (
        environment is None
        or environment.get("schema_name") != "qc2.apexlab.TrainingEnvironment.v1"
        or environment.get("schema_version") != "1.0"
    ):
        raise PromotionBundleError("candidate has no complete immutable environment report")
    return dict(documents)


def _identity_bindings(
    manifest: Mapping[str, Any],
    documents: Mapping[tuple[str, str], dict[str, Any]],
    *,
    evaluator_ref: Mapping[str, Any],
    owner_device_ref: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    evaluator = documents[(evaluator_ref["target_schema_name"], evaluator_ref["target_id"])]
    evaluator_name = evaluator.get("evaluator_identity", evaluator.get("owning_authority"))
    report_hash = evaluator.get("report_hash", evaluator.get("content_hash"))
    if not isinstance(evaluator_name, str) or not evaluator_name.strip():
        raise PromotionBundleError("evaluation report has no independent evaluator identity")
    if not isinstance(report_hash, str):
        raise PromotionBundleError("evaluation report has no immutable report hash")
    evaluator_binding = {
        "role": EVALUATOR_ROLE,
        "reference": dict(evaluator_ref),
        "identity": evaluator_name,
        "report_hash": report_hash,
    }

    owner = documents[(owner_device_ref["target_schema_name"], owner_device_ref["target_id"])]
    owner_key_id = owner.get("owner_key_id")
    public_key = _b64url_decode(owner.get("public_key", ""))
    if not isinstance(owner_key_id, str) or not owner_key_id:
        raise PromotionBundleError("OwnerDevice has no owner key identity")
    owner_binding = {
        "role": OWNER_ROLE,
        "reference": dict(owner_device_ref),
        "owner_key_id": owner_key_id,
        "public_key_sha256": hashlib.sha256(public_key).hexdigest(),
    }
    return evaluator_binding, owner_binding


def _parse_signature(value: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    expected_keys = {
        "profile",
        "algorithm",
        "encoding",
        "manifest_content_hash",
        "inventory_hash",
        "artifact_signer",
        "evaluator_identity",
        "owner_identity",
        "signature",
    }
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise PromotionBundleError("detached signature envelope has unknown or missing fields")
    if (
        value["profile"] != SIGNATURE_PROFILE
        or value["algorithm"] != SIGNATURE_ALGORITHM
        or value["encoding"] != SIGNATURE_ENCODING
    ):
        raise PromotionBundleError("detached signature profile, algorithm, or encoding is unsupported")
    signer = value["artifact_signer"]
    evaluator = value["evaluator_identity"]
    owner = value["owner_identity"]
    if not isinstance(signer, dict) or set(signer) != {"role", "key_id"} or signer["role"] != PACKAGER_ROLE:
        raise PromotionBundleError("bundle must have one artifact-packager signature identity")
    _validate_key_id(signer["key_id"])
    if not isinstance(evaluator, dict) or evaluator.get("role") != EVALUATOR_ROLE:
        raise PromotionBundleError("evaluator identity binding is invalid")
    if not isinstance(owner, dict) or owner.get("role") != OWNER_ROLE:
        raise PromotionBundleError("owner identity binding is invalid")
    if not isinstance(value["signature"], str):
        raise PromotionBundleError("detached signature must use canonical base64url text")
    _b64url_decode(value["signature"])
    return dict(signer), dict(evaluator), dict(owner)


def _signature_statement(
    manifest: Mapping[str, Any],
    artifact_signer: Mapping[str, Any],
    evaluator_identity: Mapping[str, Any],
    owner_identity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "profile": SIGNATURE_PROFILE,
        "algorithm": SIGNATURE_ALGORITHM,
        "encoding": SIGNATURE_ENCODING,
        "manifest_content_hash": manifest["content_hash"],
        "inventory_hash": manifest["inventory_hash"],
        "artifact_signer": dict(artifact_signer),
        "evaluator_identity": dict(evaluator_identity),
        "owner_identity": dict(owner_identity),
    }


def _signature_message(statement: Mapping[str, Any]) -> bytes:
    return SIGNATURE_PREFIX + canonical_json_bytes(dict(statement))


def _contract_documents(
    files: Mapping[str, bytes],
) -> dict[tuple[str, str], dict[str, Any]]:
    documents: dict[tuple[str, str], dict[str, Any]] = {}
    for path, content in files.items():
        payload = _parse_payload(content, path)
        schema_name = payload.get("schema_name")
        if schema_name not in SCHEMA_TO_CONTRACT:
            continue
        contract_name = SCHEMA_TO_CONTRACT[schema_name]
        validate_contract(contract_name, payload)
        _verify_contract_hash(contract_name, payload)
        identity = (schema_name, payload["id"])
        if identity in documents:
            raise PromotionBundleError("dependency inventory repeats a contract identity")
        documents[identity] = payload
    return documents


def _safe_assets(files: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = {}
    for path, content in files.items():
        payload = _parse_payload(content, path)
        if payload.get("schema_name") in SAFE_ARTIFACT_SCHEMAS:
            if payload.get("schema_version") != "1.0":
                raise PromotionBundleError("safe model artifact schema version is unsupported")
            assets[path] = payload
        elif payload.get("schema_name") not in SCHEMA_TO_CONTRACT:
            raise PromotionBundleError(f"{path} is not a known QC2 contract or safe model JSON schema")
    return assets


def _parse_payload(content: bytes, path: str) -> dict[str, Any]:
    if not isinstance(content, bytes):
        raise PromotionBundleError(f"{path} must be immutable bytes")
    try:
        value = parse_json_strict(content.decode("utf-8"))
    except (ContractValidationError, UnicodeDecodeError, TypeError, ValueError) as exc:
        raise PromotionBundleError(f"{path} is not strict UTF-8 QC2 JSON: {exc}") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != content:
        raise PromotionBundleError(f"{path} must be a canonical JSON object")
    return value


def _verify_contract_hash(contract_name: str, payload: dict[str, Any]) -> None:
    if contract_name in CONTENT_ADDRESSED:
        try:
            verify_content_hash(contract_name, payload)
        except (ContractValidationError, KeyError, TypeError, ValueError) as exc:
            raise PromotionBundleError(f"{contract_name} content hash is invalid: {exc}") from exc


def _typed_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        if {"target_schema_name", "target_id"} <= set(value):
            refs.append(dict(value))
        else:
            for child in value.values():
                refs.extend(_typed_refs(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            refs.extend(_typed_refs(child))
    return refs


def _find_registry_ref(registry_refs: list[Mapping[str, Any]], contract_name: str) -> Mapping[str, Any]:
    schema_name = CONTRACTS[contract_name][1]
    matches = [ref for ref in registry_refs if ref.get("target_schema_name") == schema_name]
    if len(matches) != 1:
        raise PromotionBundleError(f"bundle must include exactly one {contract_name} reference")
    return matches[0]


def _references_equal(left: Any, right: Any) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    keys = {"target_schema_name", "target_id", "content_hash"}
    return all(left.get(key) == right.get(key) for key in keys)


def _dependency_bytes_for_asset(
    path: str,
    assets: Mapping[str, dict[str, Any]],
) -> bytes:
    payload = assets.get(path)
    if payload is None:
        raise PromotionBundleError(f"ArtifactManifest file is missing from archive: {path}")
    return canonical_json_bytes(payload)


def _parse_utc(value: str, label: str) -> datetime:
    if not isinstance(value, str):
        raise PromotionBundleError(f"{label} must be an explicit UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PromotionBundleError(f"{label} must be an explicit UTC instant") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise PromotionBundleError(f"{label} must use the UTC timezone")
    return parsed.astimezone(UTC)


def _validate_key_id(value: Any) -> None:
    if (
        not isinstance(value, str)
        or len(value) > MAX_KEY_ID_LENGTH
        or _KEY_ID_RE.fullmatch(value) is None
    ):
        raise PromotionBundleError("artifact signer key ID is not a valid lowercase identifier")


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: Any) -> bytes:
    if not isinstance(value, str) or not value or "=" in value or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise PromotionBundleError("identity key or signature is not canonical base64url")
    try:
        result = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise PromotionBundleError("identity key or signature is not valid base64url") from exc
    if _b64url_encode(result) != value:
        raise PromotionBundleError("identity key or signature is not canonical base64url")
    return result


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


