from __future__ import annotations

import copy
import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
for package in (
    "contracts",
    "temporal_firewall",
    "apexlab",
    "candidate_evaluator",
    "model_registry",
):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))
sys.path.insert(0, str(ROOT / "tests" / "candidate_evaluator"))

from test_independent_evaluator import (  # noqa: E402
    _build_candidate,
    _evaluator,
    _valid_contract,
)
from qc2_contracts.runtime import (  # noqa: E402
    artifact_inventory_hash,
    canonical_content_hash,
    new_uuidv7,
    validate_contract,
)
from qc2_candidate_evaluator.models import thaw_json  # noqa: E402
from qc2_model_registry import (  # noqa: E402
    ArtifactBundle,
    ArtifactVerificationError,
    FileSystemArtifactBlobStore,
    MemoryArtifactBlobStore,
    ModelRegistry,
    RegistryError,
    artifact_verification_hash,
    verify_artifact_bundle,
)
from qc2_model_registry.artifacts import ARTIFACT_SCHEMA, MODEL_SCHEMA  # noqa: E402
from qc2_model_registry.registry import MODEL_REGISTRY_ROLE  # noqa: E402


def _bundles(candidate: Any) -> list[ArtifactBundle]:
    return [
        ArtifactBundle(candidate.artifact_manifest, candidate.artifact_files),
        ArtifactBundle(
            candidate.hyperparameter_manifest,
            {"hyperparameters.json": candidate.hyperparameter_bytes},
        ),
    ]


def _register(
    registry: ModelRegistry,
    candidate: Any,
    *,
    lifecycle_state: str | None = None,
) -> Mapping[str, Any]:
    model = thaw_json(candidate.model_manifest)
    if lifecycle_state is not None:
        # ModelManifest lifecycle_state is mutable state, excluded from its content hash.
        model["lifecycle_state"] = lifecycle_state
    return registry.register_model(
        model,
        _bundles(candidate),
        max_artifact_bytes=candidate.resource_budget["max_artifact_bytes"],
        runtime_role=MODEL_REGISTRY_ROLE,
    )


def _ref(schema_name: str, contract: Mapping[str, Any]) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": contract["id"],
        "content_hash": contract["content_hash"],
    }


def _model_ref(model: Mapping[str, Any]) -> dict[str, str]:
    return _ref(MODEL_SCHEMA, model)


def _reseal_artifact_manifest(
    template: Mapping[str, Any],
    content: bytes,
    *,
    media_type: str = "application/json",
) -> dict[str, Any]:
    manifest = thaw_json(template)
    files = [copy.deepcopy(record) for record in manifest["files"]]
    assert len(files) == 1
    files[0]["length_bytes"] = len(content)
    files[0]["media_type"] = media_type
    files[0]["sha256"] = hashlib.sha256(content).hexdigest()
    manifest["files"] = files
    manifest["inventory_hash"] = artifact_inventory_hash(files)
    manifest["content_hash"] = "0" * 64
    manifest["content_hash"] = canonical_content_hash("ArtifactManifest", manifest)
    validate_contract("ArtifactManifest", manifest)
    return manifest


def _pointer(
    model: Mapping[str, Any],
    epoch_ref: Mapping[str, Any],
    *,
    role: str,
) -> dict[str, Any]:
    pointer = copy.deepcopy(_valid_contract("ChampionPointer"))
    pointer.update(
        {
            "id": new_uuidv7(),
            "created_at": "2026-10-08T18:00:00Z",
            "owning_authority": "promotion",
            "evidence_class": model["evidence_class"],
            "environment_namespace": model["environment_namespace"],
            "epoch_ref": dict(epoch_ref),
            "role": role,
            "model_ref": _model_ref(model),
            "generation": 1,
            "transitioned_at": "2026-10-08T18:15:00Z",
            "pointer_hash": hashlib.sha256(f"{role}:{model['id']}".encode()).hexdigest(),
        }
    )
    validate_contract("ChampionPointer", pointer)
    return pointer


def test_verified_content_addressed_staging_and_retention_for_retired_model() -> None:
    package, _ = _build_candidate()
    store = MemoryArtifactBlobStore()
    registry = ModelRegistry(store)
    model = _register(registry, package)

    assert model["lifecycle_state"] == "RESEARCH"
    assert len(registry.dependency_links()) == 1
    dependency = registry.dependency_links()[0]
    assert dependency["dependency_role"] == "hyperparameters"
    assert dependency["required_for_retention"] is True
    persistence = registry.persistence_receipts(_model_ref(model))
    assert len(persistence["storage_receipts"]) == 2
    assert len(persistence["blob_receipts"]) == 3
    assert all(
        receipt["verification_state"] == "FULL_VERIFIED"
        and receipt["storage_backend"] == "fixture_memory"
        and receipt["durability_receipt"] is None
        for receipt in persistence["storage_receipts"]
    )
    assert persistence["storage_receipts"][0]["verification_hash"] == (
        artifact_verification_hash(
            package.artifact_manifest,
            storage_backend="fixture_memory",
            durability_receipt=None,
        )
    )

    primary_file = package.artifact_manifest["files"][0]
    primary_bytes = package.artifact_files[primary_file["relative_path"]]
    assert store.get(primary_file["sha256"]) == primary_bytes
    with pytest.raises(ArtifactVerificationError, match="overwrite refused|do not match"):
        store.put(primary_file["sha256"], primary_bytes + b"changed")
    assert store.get(primary_file["sha256"]) == primary_bytes

    retired_registry = ModelRegistry(MemoryArtifactBlobStore())
    retired_model = _register(retired_registry, package, lifecycle_state="RETIRED")
    prediction = _valid_contract("Prediction")
    prediction_ref = _ref("qc2.models_prediction.Prediction.v1", prediction)
    retired_registry.link_retained_prediction(
        _model_ref(retired_model),
        prediction_ref,
        purpose="sealed_prediction_replay",
        linked_at="2026-10-08T18:30:00Z",
        runtime_role=MODEL_REGISTRY_ROLE,
    )
    assert retired_registry.retained_model_artifact(
        _model_ref(retired_model),
        prediction_ref,
        "model.json",
    ) == package.artifact_files["model.json"]
    with pytest.raises(RegistryError, match="not retained"):
        retired_registry.retained_model_artifact(
            _model_ref(retired_model),
            _ref("qc2.models_prediction.PredictionSeal.v1", _valid_contract("PredictionSeal")),
            "model.json",
        )


def test_actual_insufficient_evaluation_cannot_promote_and_lifecycle_fact_is_recorded() -> None:
    package, snapshot = _build_candidate()
    registry = ModelRegistry(MemoryArtifactBlobStore())
    model = _register(registry, package)
    evaluator = _evaluator(package, snapshot)
    nomination = evaluator.nominate(
        package,
        nominated_by=MODEL_REGISTRY_ROLE,
        nominated_at="2026-10-07T01:00:00Z",
    )
    result = evaluator.evaluate(nomination, evaluated_at="2026-10-07T02:00:00Z")
    evaluation = result.candidate_evaluation
    assert evaluation["verdict"] == "INSUFFICIENT_EVIDENCE"

    with pytest.raises(RegistryError, match="passing independent CandidateEvaluation"):
        registry.transition_lifecycle(
            _model_ref(model),
            "CANDIDATE",
            evaluation,
            runtime_role="qc2_runtime_validation",
            transitioned_at="2026-10-07T02:01:00Z",
        )

    event = registry.transition_lifecycle(
        _model_ref(model),
        "REJECTED",
        evaluation,
        runtime_role="qc2_runtime_validation",
        transitioned_at="2026-10-07T02:02:00Z",
    )
    assert (event.prior_state, event.next_state) == ("RESEARCH", "REJECTED")
    assert registry.model(_model_ref(model))["lifecycle_state"] == "REJECTED"
    assert len(registry.lifecycle_events(_model_ref(model))) == 1


def test_corrupt_and_unsafe_json_artifacts_are_rejected_before_registration() -> None:
    package, _ = _build_candidate()
    registry = ModelRegistry(MemoryArtifactBlobStore())
    corrupted = dict(package.artifact_files)
    corrupted["model.json"] += b"\x00"
    with pytest.raises(RegistryError, match="bytes do not match"):
        registry.register_model(
            package.model_manifest,
            [
                ArtifactBundle(package.artifact_manifest, corrupted),
                _bundles(package)[1],
            ],
            max_artifact_bytes=package.resource_budget["max_artifact_bytes"],
            runtime_role=MODEL_REGISTRY_ROLE,
        )
    assert registry._models == {}

    duplicate_key_json = (
        b'{"schema_name":"qc2.apexlab.FrozenHyperparameterSpace.v1",'
        b'"schema_name":"attacker","schema_version":"1.0"}'
    )
    unsafe_manifest = _reseal_artifact_manifest(
        package.hyperparameter_manifest,
        duplicate_key_json,
    )
    with pytest.raises(ArtifactVerificationError, match="repeats key"):
        verify_artifact_bundle(
            unsafe_manifest,
            {"hyperparameters.json": duplicate_key_json},
            max_artifact_bytes=package.resource_budget["max_artifact_bytes"],
        )

    executable = b"\x7fELF\x00not-json"
    executable_manifest = _reseal_artifact_manifest(
        package.hyperparameter_manifest,
        executable,
        media_type="application/octet-stream",
    )
    with pytest.raises(ArtifactVerificationError, match="only allowlisted JSON"):
        verify_artifact_bundle(
            executable_manifest,
            {"hyperparameters.json": executable},
            max_artifact_bytes=package.resource_budget["max_artifact_bytes"],
        )


def test_explicit_no_champion_state_and_pointer_authority_uniqueness() -> None:
    package, _ = _build_candidate()
    registry = ModelRegistry(MemoryArtifactBlobStore())
    eligible_model = _register(registry, package, lifecycle_state="PROMOTION_ELIGIBLE")
    epoch = _valid_contract("ValidationEpoch")
    epoch_ref = _ref("qc2.validation.ValidationEpoch.v1", epoch)
    assert registry.operating_pointer_state(epoch_ref).state == "NO_CHAMPION"

    pointer = _pointer(eligible_model, epoch_ref, role="OPERATING")
    with pytest.raises(RegistryError, match="only Promotion"):
        registry.register_pointer(pointer, runtime_role="qc2_runtime_apexlab")
    accepted = registry.register_pointer(pointer, runtime_role="qc2_runtime_promotion")
    assert accepted["role"] == "OPERATING"
    assert registry.operating_pointer_state(epoch_ref).state == "CHAMPION_SET"
    with pytest.raises(RegistryError, match="already exists"):
        registry.register_pointer(
            _pointer(eligible_model, epoch_ref, role="OPERATING"),
            runtime_role="qc2_runtime_promotion",
        )

    reference = _pointer(eligible_model, epoch_ref, role="REFERENCE")
    registry.register_pointer(reference, runtime_role="qc2_runtime_promotion")
    with pytest.raises(RegistryError, match="Reference pointer is immutable"):
        registry.register_pointer(
            _pointer(eligible_model, epoch_ref, role="REFERENCE"),
            runtime_role="qc2_runtime_promotion",
        )
    assert registry.reference_pointer(epoch_ref)["id"] == reference["id"]


def test_unqualified_and_corrupted_artifacts_never_load_for_production() -> None:
    package, _ = _build_candidate()
    store = MemoryArtifactBlobStore()
    registry = ModelRegistry(store)
    research_model = _register(registry, package)
    epoch = _valid_contract("ValidationEpoch")
    epoch_ref = _ref("qc2.validation.ValidationEpoch.v1", epoch)
    with pytest.raises(RegistryError, match="NO_CHAMPION"):
        registry.load_for_production(
            _model_ref(research_model),
            epoch_ref,
            runtime_role="qc2_runtime_inference",
        )
    with pytest.raises(RegistryError, match="not registered and lifecycle-eligible"):
        registry.register_pointer(
            _pointer(research_model, epoch_ref, role="OPERATING"),
            runtime_role="qc2_runtime_promotion",
        )

    model_bundle = package.artifact_manifest
    model_file = model_bundle["files"][0]
    store._objects[model_file["sha256"]] = b"tampered"
    with pytest.raises(ArtifactVerificationError, match="do not match their content address"):
        store.get(model_file["sha256"])


def test_dependency_cycle_and_local_filesystem_cas_hostile_entries_fail(tmp_path: Path) -> None:
    package, _ = _build_candidate()
    store = MemoryArtifactBlobStore()
    registry = ModelRegistry(store)
    _register(registry, package)

    primary_ref = _ref(ARTIFACT_SCHEMA, package.artifact_manifest)
    parameter_ref = _ref(ARTIFACT_SCHEMA, package.hyperparameter_manifest)
    dependency = copy.deepcopy(_valid_contract("ArtifactDependency"))
    dependency.update(
        {
            "id": new_uuidv7(),
            "created_at": "2026-10-08T18:00:00Z",
            "owning_authority": "model_registry",
            "evidence_class": package.model_manifest["evidence_class"],
            "environment_namespace": package.model_manifest["environment_namespace"],
            "source_refs": [primary_ref, parameter_ref],
            "parent_ref": parameter_ref,
            "dependency_ref": primary_ref,
            "dependency_role": "reverse_cycle_test",
            "required_for_retention": True,
            "discovered_at": "2026-10-08T18:00:00Z",
        }
    )
    validate_contract("ArtifactDependency", dependency)
    with pytest.raises(RegistryError, match="retention cycle"):
        registry.add_artifact_dependency(dependency, runtime_role=MODEL_REGISTRY_ROLE)

    fs_store = FileSystemArtifactBlobStore(tmp_path / "cas")
    content = b"immutable"
    digest = hashlib.sha256(content).hexdigest()
    fs_store.put(digest, content)
    assert fs_store.get(digest) == content
    (tmp_path / "cas" / ("f" * 64)).symlink_to(tmp_path / "outside", target_is_directory=False)
    with pytest.raises(ArtifactVerificationError, match="unsafe"):
        fs_store.get("f" * 64)
