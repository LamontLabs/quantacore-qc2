from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import stat
import sys
import zipfile
from collections import deque
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "promotion" / "src"))

from qc2_contracts.runtime import (  # noqa: E402
    CONTENT_ADDRESSED,
    CONTRACTS,
    SCHEMA_TO_CONTRACT,
    artifact_inventory_hash,
    canonical_content_hash,
    canonical_json_bytes,
    validate_contract,
    verify_content_hash,
)
from qc2_promotion import (  # noqa: E402
    BundleLimits,
    PromotionBundleError,
    build_promotion_bundle_archive,
    verify_promotion_bundle_archive,
)
from qc2_promotion.archive import (  # noqa: E402
    INVENTORY_PATH,
    MANIFEST_PATH,
    decode_archive,
)

NOW = "2026-10-08T20:00:00Z"
EXPIRES = "2026-10-08T20:30:00Z"
LIMITS = BundleLimits(
    max_archive_bytes=4_000_000,
    max_uncompressed_bytes=3_000_000,
    max_file_bytes=1_000_000,
    max_entries=128,
    max_compression_ratio=50,
    max_lifetime_seconds=3_600,
)
ARTIFACT_KEY_ID = "backend_packager_test"
EVALUATOR_NAME = "independent_evaluator_test"
OWNER_KEY_ID = "registered_owner_test"


def _valid_payloads() -> dict[str, dict[str, Any]]:
    rows = json.loads(
        (ROOT / "packages" / "contracts" / "fixtures" / "v1" / "valid.json").read_text(
            encoding="utf-8"
        )
    )
    return {row["contract"]: copy.deepcopy(row["payload"]) for row in rows}


def _typed_refs(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if {"target_schema_name", "target_id"} <= set(value):
            result.append(value)
        else:
            for child in value.values():
                result.extend(_typed_refs(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(_typed_refs(child))
    return result


def _refresh_reference_hashes(value: Any, payloads: dict[str, dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if {"target_schema_name", "target_id"} <= set(value):
            contract_name = SCHEMA_TO_CONTRACT.get(value["target_schema_name"])
            target = payloads.get(contract_name or "")
            if target is None:
                return
            target_hash = target.get("content_hash", target.get("report_hash"))
            if target_hash is None:
                value.pop("content_hash", None)
            elif "content_hash" in value or contract_name in CONTENT_ADDRESSED:
                value["content_hash"] = target_hash
            return
        for child in value.values():
            _refresh_reference_hashes(child, payloads)
    elif isinstance(value, list):
        for child in value:
            _refresh_reference_hashes(child, payloads)


def _dependency_closure(
    root_manifest: dict[str, Any],
    owner_device_ref: dict[str, str],
    payloads: dict[str, dict[str, Any]],
) -> set[str]:
    reachable: set[str] = set()
    pending = [ref["target_schema_name"] for ref in _typed_refs(root_manifest)]
    pending.append(owner_device_ref["target_schema_name"])
    while pending:
        schema_name = pending.pop()
        contract_name = SCHEMA_TO_CONTRACT.get(schema_name)
        if contract_name is None or contract_name in reachable:
            continue
        reachable.add(contract_name)
        pending.extend(
            ref["target_schema_name"]
            for ref in _typed_refs(payloads[contract_name])
        )
    return reachable


def _fixture_bundle() -> tuple[dict[str, Any], dict[str, bytes], dict[str, Any], dict[str, Any]]:
    payloads = _valid_payloads()
    catalog = json.loads(
        (ROOT / "packages" / "contracts" / "catalog" / "v1" / "contracts.json").read_text(
            encoding="utf-8"
        )
    )
    for contract_name, payload in payloads.items():
        payload["source_refs"] = []
        for field in catalog[contract_name]["fields"]:
            if field["type"].startswith("refs<") and contract_name != "PromotionBundleManifest":
                payload[field["name"]] = []

    manifest = payloads["PromotionBundleManifest"]
    manifest["created_at"] = NOW
    manifest["expires_at"] = EXPIRES
    manifest["registry_refs"] = [
        {
            "target_schema_name": CONTRACTS[name][1],
            "target_id": payloads[name]["id"],
        }
        for name in (
            "FeatureRegistry",
            "RunnerProtocolRegistry",
            "LabelRegistry",
            "ScoreManifest",
            "BaselineManifest",
        )
    ]
    manifest["content_hash"] = "0" * 64

    model = payloads["ModelManifest"]
    model["safe_format"] = "json"
    model["environment_fingerprint"] = manifest["environment_fingerprint"]
    evaluation = payloads["CandidateEvaluation"]
    evaluation["evaluator_identity"] = EVALUATOR_NAME
    owner = payloads["OwnerDevice"]
    owner["owner_key_id"] = OWNER_KEY_ID
    owner["public_key"] = base64.urlsafe_b64encode(b"test owner public key").decode().rstrip("=")
    owner_ref = {
        "target_schema_name": CONTRACTS["OwnerDevice"][1],
        "target_id": owner["id"],
    }
    evaluator_ref = copy.deepcopy(manifest["evaluation_refs"][0])

    artifact = payloads["ArtifactManifest"]
    model_bytes = canonical_json_bytes(
        {
            "schema_name": "qc2.apexlab.SafeModelArtifact.v1",
            "schema_version": "1.0",
            "format": "json",
        }
    )
    environment_bytes = canonical_json_bytes(
        {
            "schema_name": "qc2.apexlab.TrainingEnvironment.v1",
            "schema_version": "1.0",
            "environment_fingerprint": manifest["environment_fingerprint"],
        }
    )
    asset_bytes = {
        f"artifacts/{artifact['id']}/model.json": model_bytes,
        f"artifacts/{artifact['id']}/environment.json": environment_bytes,
    }
    artifact["files"] = [
        {
            "relative_path": "model.json",
            "length_bytes": len(model_bytes),
            "media_type": "application/json",
            "schema_name": "qc2.apexlab.SafeModelArtifact.v1",
            "schema_version": "1.0",
            "sha256": hashlib.sha256(model_bytes).hexdigest(),
        },
        {
            "relative_path": "environment.json",
            "length_bytes": len(environment_bytes),
            "media_type": "application/json",
            "schema_name": "qc2.apexlab.TrainingEnvironment.v1",
            "schema_version": "1.0",
            "sha256": hashlib.sha256(environment_bytes).hexdigest(),
        },
    ]
    artifact["inventory_hash"] = artifact_inventory_hash(artifact["files"])
    artifact["content_hash"] = "0" * 64

    reachable = _dependency_closure(manifest, owner_ref, payloads)
    addressable = {
        name
        for name in reachable
        if name in CONTENT_ADDRESSED
    }
    dependency_graph = {
        name: {
            SCHEMA_TO_CONTRACT[ref["target_schema_name"]]
            for ref in _typed_refs(payloads[name])
            if SCHEMA_TO_CONTRACT.get(ref["target_schema_name"]) in addressable
        }
        for name in addressable
    }
    pending_counts = {name: len(children) for name, children in dependency_graph.items()}
    ready = deque(name for name, count in pending_counts.items() if count == 0)
    hash_order: list[str] = []
    while ready:
        name = ready.popleft()
        hash_order.append(name)
        for parent, children in dependency_graph.items():
            if name in children:
                pending_counts[parent] -= 1
                if pending_counts[parent] == 0:
                    ready.append(parent)
    if set(hash_order) != addressable:
        raise AssertionError("synthetic promotion fixture unexpectedly contains a content-hash cycle")

    for contract_name in hash_order:
        _refresh_reference_hashes(payloads[contract_name], payloads)
        payloads[contract_name]["content_hash"] = "0" * 64
        payloads[contract_name]["content_hash"] = canonical_content_hash(
            contract_name, payloads[contract_name]
        )
    for contract_name in reachable:
        _refresh_reference_hashes(payloads[contract_name], payloads)
        validate_contract(contract_name, payloads[contract_name])
        if contract_name in CONTENT_ADDRESSED:
            verify_content_hash(contract_name, payloads[contract_name])

    _refresh_reference_hashes(manifest, payloads)
    manifest["content_hash"] = canonical_content_hash("PromotionBundleManifest", manifest)
    validate_contract("PromotionBundleManifest", manifest)
    verify_content_hash("PromotionBundleManifest", manifest)

    files: dict[str, bytes] = {}
    for contract_name in reachable:
        if contract_name == "PromotionBundleManifest":
            raise AssertionError("fixture dependency graph must not include its root manifest")
        payload = payloads[contract_name]
        files[f"evidence/{contract_name}/{payload['id']}.json"] = canonical_json_bytes(payload)
    files.update(asset_bytes)
    return manifest, files, evaluator_ref, owner_ref


def _build(
    *,
    manifest: dict[str, Any] | None = None,
    files: dict[str, bytes] | None = None,
    evaluator_ref: dict[str, Any] | None = None,
    owner_ref: dict[str, Any] | None = None,
    key: Ed25519PrivateKey | None = None,
) -> tuple[bytes, Ed25519PrivateKey, dict[str, Any], dict[str, bytes]]:
    fixture_manifest, fixture_files, fixture_evaluator_ref, fixture_owner_ref = _fixture_bundle()
    active_key = key or Ed25519PrivateKey.generate()
    archive = build_promotion_bundle_archive(
        manifest or fixture_manifest,
        files or fixture_files,
        signing_key=active_key,
        signing_key_id=ARTIFACT_KEY_ID,
        evaluator_ref=evaluator_ref or fixture_evaluator_ref,
        owner_device_ref=owner_ref or fixture_owner_ref,
        now=NOW,
        limits=LIMITS,
    )
    return archive, active_key, fixture_manifest, fixture_files


def _rewrite_archive(
    archive_bytes: bytes,
    mutate: Any,
    *,
    executable_paths: set[str] | None = None,
) -> bytes:
    with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as source:
        entries = {info.filename: source.read(info) for info in source.infolist()}
    mutate(entries)
    executable_paths = executable_paths or set()
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as destination:
        for path, content in entries.items():
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            permissions = 0o700 if path in executable_paths else 0o600
            info.external_attr = (stat.S_IFREG | permissions) << 16
            destination.writestr(info, content)
    return result.getvalue()


def _verify(archive: bytes, key: Ed25519PrivateKey, *, now: str = NOW) -> Any:
    return verify_promotion_bundle_archive(
        archive,
        trusted_backend_public_keys={
            ARTIFACT_KEY_ID: key.public_key().public_bytes_raw(),
        },
        now=now,
        limits=LIMITS,
    )


def test_bundle_round_trip_signs_complete_inventory_and_separate_identities() -> None:
    archive, key, _, _ = _build()
    verified = _verify(archive, key)
    manifest, inventory, signature, files = decode_archive(archive, LIMITS)

    assert verified.manifest["inventory_hash"] == artifact_inventory_hash(inventory)
    assert manifest["content_hash"] == canonical_content_hash(
        "PromotionBundleManifest", manifest
    )
    assert verified.manifest["content_hash"] == manifest["content_hash"]
    assert set(files) == {record["relative_path"] for record in inventory}
    assert "detached_signature" not in manifest
    assert "signature" not in manifest
    assert signature["artifact_signer"] == {
        "role": "artifact_packager",
        "key_id": ARTIFACT_KEY_ID,
    }
    assert signature["evaluator_identity"]["role"] == "independent_evaluator"
    assert signature["owner_identity"]["role"] == "owner_identity"
    assert verified.artifact_signer_key_id == ARTIFACT_KEY_ID
    assert verified.evaluator_identity["identity"] == EVALUATOR_NAME
    assert verified.owner_identity["owner_key_id"] == OWNER_KEY_ID
    schemas = {
        json.loads(content)["schema_name"]
        for content in files.values()
    }
    for contract_name in (
        "DatasetManifest",
        "HoldoutAccessReceipt",
        "PredictionSeal",
        "ReplayReceipt",
        "PromotionPolicy",
    ):
        assert CONTRACTS[contract_name][1] in schemas
    assert "qc2.apexlab.TrainingEnvironment.v1" in schemas


@pytest.mark.parametrize("mutation", ["same_size_content", "larger_content", "rename_payload"])
def test_post_signing_content_size_and_path_mutations_fail(mutation: str) -> None:
    archive, key, _, _ = _build()
    _, inventory, _, files = decode_archive(archive, LIMITS)
    asset_path = next(path for path in files if path.endswith("/model.json"))

    def mutate(entries: dict[str, bytes]) -> None:
        if mutation == "rename_payload":
            entries[f"{asset_path}.renamed"] = entries.pop(asset_path)
            return
        value = json.loads(entries[asset_path])
        if mutation == "same_size_content":
            value["format"] = "js0n"
        else:
            value["extra"] = "post-signing-size-change"
        entries[asset_path] = canonical_json_bytes(value)

    altered = _rewrite_archive(archive, mutate)
    with pytest.raises(PromotionBundleError):
        _verify(altered, key)
    assert any(row["relative_path"] == asset_path for row in inventory)


def test_missing_report_and_changed_policy_are_rejected() -> None:
    manifest, files, evaluator_ref, owner_ref = _fixture_bundle()
    holdout_path = next(
        path
        for path, raw in files.items()
        if json.loads(raw)["schema_name"] == CONTRACTS["HoldoutAccessReceipt"][1]
    )
    missing = dict(files)
    del missing[holdout_path]
    key = Ed25519PrivateKey.generate()
    with pytest.raises(PromotionBundleError, match="missing immutable dependency"):
        build_promotion_bundle_archive(
            manifest,
            missing,
            signing_key=key,
            signing_key_id=ARTIFACT_KEY_ID,
            evaluator_ref=evaluator_ref,
            owner_device_ref=owner_ref,
            now=NOW,
            limits=LIMITS,
        )

    archive, key, _, _ = _build()
    _, inventory, _, original_files = decode_archive(archive, LIMITS)
    policy_path = next(
        path
        for path, raw in original_files.items()
        if json.loads(raw)["schema_name"] == CONTRACTS["PromotionPolicy"][1]
    )

    def change_policy(entries: dict[str, bytes]) -> None:
        policy = json.loads(entries[policy_path])
        policy["policy_key"] = "changed"
        policy["content_hash"] = "0" * 64
        policy["content_hash"] = canonical_content_hash("PromotionPolicy", policy)
        entries[policy_path] = canonical_json_bytes(policy)
        records = json.loads(entries[INVENTORY_PATH])
        for row in records:
            if row["relative_path"] == policy_path:
                row["length_bytes"] = len(entries[policy_path])
                row["sha256"] = hashlib.sha256(entries[policy_path]).hexdigest()
        entries[INVENTORY_PATH] = canonical_json_bytes(records)
        updated_manifest = json.loads(entries[MANIFEST_PATH])
        updated_manifest["inventory_hash"] = artifact_inventory_hash(records)
        updated_manifest["content_hash"] = "0" * 64
        updated_manifest["content_hash"] = canonical_content_hash(
            "PromotionBundleManifest", updated_manifest
        )
        entries[MANIFEST_PATH] = canonical_json_bytes(updated_manifest)

    changed_policy_archive = _rewrite_archive(archive, change_policy)
    with pytest.raises(PromotionBundleError, match="signature"):
        _verify(changed_policy_archive, key)
    assert any(row["relative_path"] == policy_path for row in inventory)


def test_expiry_and_unknown_backend_signer_fail_closed() -> None:
    archive, key, _, _ = _build()
    with pytest.raises(PromotionBundleError, match="expiry"):
        _verify(archive, key, now=EXPIRES)
    with pytest.raises(PromotionBundleError, match="unknown or not trusted"):
        verify_promotion_bundle_archive(
            archive,
            trusted_backend_public_keys={},
            now=NOW,
            limits=LIMITS,
        )


def test_manifest_signature_is_detached_and_not_self_referential() -> None:
    archive, key, _, _ = _build()
    manifest, _, signature, _ = decode_archive(archive, LIMITS)
    assert "detached_signature" not in manifest
    assert "signature" not in manifest
    assert signature["manifest_content_hash"] == manifest["content_hash"]
    assert verify_promotion_bundle_archive(
        archive,
        trusted_backend_public_keys={ARTIFACT_KEY_ID: key.public_key().public_bytes_raw()},
        now=NOW,
        limits=LIMITS,
    )


def test_unlisted_and_executable_payloads_are_rejected() -> None:
    archive, key, _, _ = _build()

    def add_unlisted(entries: dict[str, bytes]) -> None:
        entries["evidence/unlisted.json"] = canonical_json_bytes(
            {
                "schema_name": "qc2.apexlab.SafeModelArtifact.v1",
                "schema_version": "1.0",
                "format": "json",
            }
        )

    with pytest.raises(PromotionBundleError, match="inventory"):
        _verify(_rewrite_archive(archive, add_unlisted), key)

    _, _, _, files = decode_archive(archive, LIMITS)
    model_path = next(path for path in files if path.endswith("/model.json"))
    with pytest.raises(PromotionBundleError, match="executable"):
        _verify(
            _rewrite_archive(archive, lambda entries: None, executable_paths={model_path}),
            key,
        )


@pytest.mark.parametrize("kind", ["traversal", "symlink", "compression_bomb"])
def test_hostile_archive_members_are_rejected(kind: str) -> None:
    buffer = io.BytesIO()
    if kind == "compression_bomb":
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("bomb.json", b"0" * 500_000)
    else:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            path = "../escape.json" if kind == "traversal" else "linked.json"
            info = zipfile.ZipInfo(path)
            info.create_system = 3
            if kind == "symlink":
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"{}")
    with pytest.raises(PromotionBundleError):
        verify_promotion_bundle_archive(
            buffer.getvalue(),
            trusted_backend_public_keys={},
            now=NOW,
            limits=LIMITS,
        )
