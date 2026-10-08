"""Immutable model registry records, lifecycle facts, retention links, and pointers."""

from __future__ import annotations

import hashlib
import threading
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from qc2_contracts.catalog import STATE_MACHINES
from qc2_contracts.runtime import (
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

from .artifacts import (
    ARTIFACT_SCHEMA,
    MODEL_SCHEMA,
    ArtifactBlobStore,
    ArtifactBundle,
    ArtifactVerificationError,
    VerifiedArtifactBundle,
    artifact_verification_hash,
    storage_acknowledgment,
    verify_artifact_bundle,
)


MODEL_REGISTRY_ROLE = "qc2_runtime_model_registry"
VALIDATION_ROLE = "qc2_runtime_validation"
PREDICTION_ROLE = "qc2_runtime_prediction"
PROMOTION_ROLE = "qc2_runtime_promotion"

_SCHEMA_NAMES = {
    "ArtifactManifest": ARTIFACT_SCHEMA,
    "ModelManifest": MODEL_SCHEMA,
    "ArtifactDependency": "qc2.integrity_build.ArtifactDependency.v1",
    "ChampionPointer": "qc2.governance_owner.ChampionPointer.v1",
    "CandidateEvaluation": "qc2.outcomes_research.CandidateEvaluation.v1",
    "ChallengerEvaluation": "qc2.outcomes_research.ChallengerEvaluation.v1",
    "ShadowPredictionSet": "qc2.models_prediction.ShadowPredictionSet.v1",
    "ValidationReport": "qc2.validation.ValidationReport.v1",
    "PromotionReceipt": "qc2.governance_owner.PromotionReceipt.v1",
    "Prediction": "qc2.models_prediction.Prediction.v1",
    "PredictionSeal": "qc2.models_prediction.PredictionSeal.v1",
}
_MODEL_LIFECYCLE = STATE_MACHINES["ModelManifest"]
_PRODUCTION_ENVIRONMENT = "production"
_FORWARD_EVIDENCE = "FORWARD_SEALED"


class RegistryError(ValueError):
    """A registry mutation or model load violates a QC2 boundary."""


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    sequence: int
    model_ref: Mapping[str, Any]
    prior_state: str
    next_state: str
    evidence_ref: Mapping[str, Any]
    runtime_role: str
    transitioned_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_ref", _freeze_json(self.model_ref))
        object.__setattr__(self, "evidence_ref", _freeze_json(self.evidence_ref))


@dataclass(frozen=True, slots=True)
class RetentionLink:
    model_ref: Mapping[str, Any]
    retaining_ref: Mapping[str, Any]
    purpose: str
    linked_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_ref", _freeze_json(self.model_ref))
        object.__setattr__(self, "retaining_ref", _freeze_json(self.retaining_ref))


@dataclass(frozen=True, slots=True)
class OperatingPointerState:
    state: str
    pointer: Mapping[str, Any] | None
    generation: int

    def __post_init__(self) -> None:
        if self.pointer is not None:
            object.__setattr__(self, "pointer", _freeze_json(self.pointer))


@dataclass(frozen=True, slots=True)
class _ModelRecord:
    manifest: Mapping[str, Any]
    lifecycle_state: str
    artifact_refs: tuple[Mapping[str, Any], ...]
    verified_artifacts: Mapping[tuple[str, str, str], VerifiedArtifactBundle]
    storage_receipts: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest", _freeze_json(self.manifest))
        object.__setattr__(
            self,
            "artifact_refs",
            tuple(_freeze_json(ref) for ref in self.artifact_refs),
        )
        object.__setattr__(self, "verified_artifacts", MappingProxyType(dict(self.verified_artifacts)))
        object.__setattr__(
            self,
            "storage_receipts",
            tuple(_freeze_json(receipt) for receipt in self.storage_receipts),
        )


class PointerStore:
    """One immutable ChampionPointer schema with explicit empty operating slots."""

    def __init__(self, eligible_model: Callable[[Mapping[str, Any], str], bool]) -> None:
        self._eligible_model = eligible_model
        self._operating: dict[str, Mapping[str, Any]] = {}
        self._reference: dict[str, Mapping[str, Any]] = {}
        self._lock = threading.RLock()

    def state(self, epoch_ref: Mapping[str, Any]) -> OperatingPointerState:
        epoch_id = _reference_id(epoch_ref, "epoch_ref")
        with self._lock:
            pointer = self._operating.get(epoch_id)
            if pointer is None:
                return OperatingPointerState("NO_CHAMPION", None, 0)
            if not _ref_equal(pointer["epoch_ref"], epoch_ref):
                raise RegistryError("operating pointer is bound to a different epoch reference")
            return OperatingPointerState(
                "CHAMPION_SET",
                pointer,
                int(pointer["generation"]),
            )

    def reference(self, epoch_ref: Mapping[str, Any]) -> Mapping[str, Any] | None:
        epoch_id = _reference_id(epoch_ref, "epoch_ref")
        with self._lock:
            pointer = self._reference.get(epoch_id)
            if pointer is not None and not _ref_equal(pointer["epoch_ref"], epoch_ref):
                raise RegistryError("Reference pointer is bound to a different epoch reference")
            return pointer

    def append(self, pointer: Mapping[str, Any], *, runtime_role: str) -> Mapping[str, Any]:
        payload = _as_object(pointer, "ChampionPointer")
        try:
            validate_contract("ChampionPointer", payload)
        except (TypeError, ValueError, KeyError) as exc:
            raise RegistryError(f"ChampionPointer contract is invalid: {exc}") from exc
        if runtime_role != PROMOTION_ROLE:
            raise RegistryError("only Promotion may write the operating/reference pointer record")
        if payload["owning_authority"] != "promotion":
            raise RegistryError("ChampionPointer must be owned by Promotion")
        if payload["generation"] != 1:
            raise RegistryError(
                "only the bootstrap pointer generation is supported; pointer transitions are "
                "reserved for the Promotion authority"
            )
        epoch_id = _reference_id(payload["epoch_ref"], "ChampionPointer.epoch_ref")
        role = payload["role"]
        if role not in {"OPERATING", "REFERENCE"}:
            raise RegistryError("ChampionPointer role is not recognized")
        if not self._eligible_model(payload["model_ref"], role):
            raise RegistryError("ChampionPointer model is not registered and lifecycle-eligible")

        with self._lock:
            destination = self._operating if role == "OPERATING" else self._reference
            if epoch_id in destination:
                if role == "REFERENCE":
                    raise RegistryError("Reference pointer is immutable and already exists")
                raise RegistryError(
                    "an operating pointer already exists; replacement requires an atomic "
                    "Promotion transition"
                )
            destination[epoch_id] = _freeze_json(payload)
            return destination[epoch_id]


class ModelRegistry:
    """In-process acceptance registry; production loading is closed without durable adapters."""

    def __init__(
        self,
        blob_store: ArtifactBlobStore,
        *,
        signature_verifier: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None,
    ) -> None:
        self.blob_store = blob_store
        # This in-process implementation is for fixtures only. The PostgreSQL
        # migration is the durable source of truth; no local flag can promote this
        # cache into production authority.
        self.metadata_durable = False
        self.signature_verifier = signature_verifier
        self._models: dict[tuple[str, str], _ModelRecord] = {}
        self._artifacts: dict[tuple[str, str, str], VerifiedArtifactBundle] = {}
        self._artifact_files: dict[tuple[str, str, str], Mapping[str, bytes]] = {}
        self._dependencies: dict[
            tuple[tuple[str, str, str], tuple[str, str, str], str],
            Mapping[str, Any],
        ] = {}
        self._retention: dict[tuple[tuple[str, str], tuple[str, str, str]], RetentionLink] = {}
        self._events: dict[tuple[str, str], list[LifecycleEvent]] = defaultdict(list)
        self._lock = threading.RLock()
        self.pointers = PointerStore(self._pointer_model_is_eligible)

    def register_model(
        self,
        model_manifest: Mapping[str, Any],
        artifact_bundles: Sequence[ArtifactBundle],
        *,
        max_artifact_bytes: int,
        runtime_role: str,
        artifact_dependencies: Sequence[Mapping[str, Any]] = (),
    ) -> Mapping[str, Any]:
        """Verify and stage all model bytes before recording immutable registry references."""
        if runtime_role != MODEL_REGISTRY_ROLE:
            raise RegistryError("model registration requires the model_registry runtime role")
        model = _as_object(model_manifest, "ModelManifest")
        try:
            validate_contract("ModelManifest", model)
            verify_content_hash("ModelManifest", model)
        except (TypeError, ValueError, KeyError) as exc:
            raise RegistryError(f"ModelManifest verification failed: {exc}") from exc
        if model["owning_authority"] != "model_registry":
            raise RegistryError("ModelManifest must be owned by model_registry")
        if model["safe_format"] != "json":
            raise RegistryError("only the verified JSON model format is supported")
        state = model["lifecycle_state"]
        if state != "RESEARCH" and not _fixture_snapshot(model):
            raise RegistryError("non-RESEARCH initial lifecycle state is fixture-only")
        if model["environment_namespace"] == _PRODUCTION_ENVIRONMENT:
            if model["evidence_class"] != _FORWARD_EVIDENCE:
                raise RegistryError("production model records require FORWARD_SEALED evidence")
            if not self.metadata_durable or not self.blob_store.durable:
                raise RegistryError(
                    "production model references require durable registry metadata and blob storage"
                )

        primary_ref = model["artifact_manifest_ref"]
        required_refs = _required_artifact_refs(model)
        supplied: dict[tuple[str, str, str], ArtifactBundle] = {}
        for bundle in artifact_bundles:
            manifest = _as_object(bundle.manifest, "ArtifactManifest")
            ref = _contract_ref(ARTIFACT_SCHEMA, manifest)
            key = _reference_key(ref)
            if key in supplied:
                raise RegistryError("artifact bundle repeats an ArtifactManifest reference")
            supplied[key] = bundle
        missing_refs = required_refs - set(supplied)
        if missing_refs:
            raise RegistryError("one or more ModelManifest artifact dependencies were not staged")
        extra_refs = set(supplied) - required_refs
        if extra_refs:
            raise RegistryError("artifact bundle is not referenced by this ModelManifest")

        verified: dict[tuple[str, str, str], VerifiedArtifactBundle] = {}
        for ref_key, bundle in supplied.items():
            manifest = _as_object(bundle.manifest, "ArtifactManifest")
            is_primary = _reference_key(_contract_ref(ARTIFACT_SCHEMA, manifest)) == _reference_key(
                primary_ref
            )
            try:
                verified[ref_key] = verify_artifact_bundle(
                    manifest,
                    bundle.files,
                    max_artifact_bytes=max_artifact_bytes,
                    model_manifest=model if is_primary else None,
                )
            except ArtifactVerificationError as exc:
                raise RegistryError(str(exc)) from exc
            if (
                manifest["evidence_class"] != model["evidence_class"]
                or manifest["environment_namespace"] != model["environment_namespace"]
            ):
                raise RegistryError("artifact evidence context differs from ModelManifest")

        model_key = _model_key(model)
        with self._lock:
            if model_key in self._models or any(existing_id == model["id"] for existing_id, _ in self._models):
                raise RegistryError("ModelManifest identity already exists")
            candidate_edges = self._make_dependency_edges(
                model,
                artifact_dependencies,
                set(supplied),
            )
            self._assert_acyclic(candidate_edges)

            write_receipts_by_ref: dict[tuple[str, str, str], list[Any]] = {}
            for ref_key, bundle in supplied.items():
                bundle_receipts = []
                for path in sorted(bundle.files):
                    digest = hashlib.sha256(bundle.files[path]).hexdigest()
                    receipt = self.blob_store.put(digest, bundle.files[path])
                    if (
                        receipt.digest != digest
                        or receipt.object_key != digest
                        or receipt.backend != self.blob_store.backend_name
                        or receipt.durable is not self.blob_store.durable
                    ):
                        raise RegistryError("blob store returned a mismatched content-address receipt")
                    bundle_receipts.append(receipt)
                write_receipts_by_ref[ref_key] = bundle_receipts
            if model["environment_namespace"] == _PRODUCTION_ENVIRONMENT and any(
                storage_acknowledgment(receipts) is None
                for receipts in write_receipts_by_ref.values()
            ):
                raise RegistryError(
                    "production artifact reference requires a durable storage acknowledgment"
                )
            if (
                model["environment_namespace"] == _PRODUCTION_ENVIRONMENT
                and self.signature_verifier is None
            ):
                raise RegistryError("production artifact verification requires a signature verifier")
            if model["environment_namespace"] == _PRODUCTION_ENVIRONMENT:
                for manifest in (bundle.manifest for bundle in artifact_bundles):
                    signature = _as_object(manifest, "ArtifactManifest").get("detached_signature")
                    if not signature or not self.signature_verifier(manifest, model):
                        raise RegistryError("production artifact signature verification failed")

            storage_receipts = []
            for ref_key, verified_bundle in verified.items():
                manifest = verified_bundle.manifest
                blob_receipts = write_receipts_by_ref[ref_key]
                durability_receipt = storage_acknowledgment(blob_receipts)
                blob_receipt_rows = []
                for path, digest in sorted(verified_bundle.blob_hashes.items()):
                    write_receipt = next(
                        (
                            receipt
                            for receipt in blob_receipts
                            if receipt.digest == digest
                        ),
                        None,
                    )
                    if write_receipt is None:
                        raise RegistryError("verified artifact lacks its storage receipt")
                    blob_receipt_rows.append(
                        {
                            "sha256": digest,
                            "byte_count": len(supplied[ref_key].files[path]),
                            "storage_backend": write_receipt.backend,
                            "object_key": write_receipt.object_key,
                            "durability_receipt": write_receipt.durability_receipt,
                            "staged_at": write_receipt.staged_at,
                        }
                    )
                storage_receipts.append(
                    {
                        "manifest_id": manifest["id"],
                        "manifest_hash": manifest["content_hash"],
                        "storage_backend": self.blob_store.backend_name,
                        "durability_receipt": durability_receipt,
                        "verification_state": "FULL_VERIFIED",
                        "verification_hash": artifact_verification_hash(
                            manifest,
                            storage_backend=self.blob_store.backend_name,
                            durability_receipt=durability_receipt,
                        ),
                        "blob_receipts": blob_receipt_rows,
                    }
                )
                self._artifacts[ref_key] = verified_bundle
                self._artifact_files[ref_key] = _freeze_json(
                    dict(supplied[ref_key].files)
                )
            for key, link in candidate_edges.items():
                self._dependencies[key] = _freeze_json(link)
            record = _ModelRecord(
                manifest=model,
                lifecycle_state=state,
                artifact_refs=tuple(_contract_ref(ARTIFACT_SCHEMA, _as_object(bundle.manifest, "ArtifactManifest"))
                                    for bundle in artifact_bundles),
                verified_artifacts=verified,
                storage_receipts=tuple(storage_receipts),
            )
            self._models[model_key] = record
            self._events[model_key] = []
            return _freeze_json(model)

    def model(self, model_ref: Mapping[str, Any]) -> Mapping[str, Any]:
        with self._lock:
            record = self._get_model(model_ref)
            result = _thaw_json(record.manifest)
            result["lifecycle_state"] = record.lifecycle_state
            return _freeze_json(result)

    def lifecycle_events(self, model_ref: Mapping[str, Any]) -> tuple[LifecycleEvent, ...]:
        with self._lock:
            return tuple(self._events[_model_ref_key(model_ref)])

    def transition_lifecycle(
        self,
        model_ref: Mapping[str, Any],
        next_state: str,
        evidence: Mapping[str, Any],
        *,
        runtime_role: str,
        transitioned_at: str,
    ) -> LifecycleEvent:
        ref_key = _model_ref_key(model_ref)
        payload = _as_object(evidence, "lifecycle evidence")
        evidence_name = _contract_name(payload.get("schema_name"))
        if evidence_name is None:
            raise RegistryError("lifecycle evidence uses an unsupported contract")
        try:
            validate_contract(evidence_name, payload)
        except (TypeError, ValueError, KeyError) as exc:
            raise RegistryError(f"lifecycle evidence contract is invalid: {exc}") from exc

        with self._lock:
            record = self._models.get(ref_key)
            if record is None:
                raise RegistryError("lifecycle transition references an unknown model")
            prior_state = record.lifecycle_state
            if next_state not in _MODEL_LIFECYCLE.get(prior_state, ()):
                raise RegistryError(f"illegal model lifecycle transition: {prior_state} -> {next_state}")
            self._verify_transition_evidence(
                record,
                next_state,
                evidence_name,
                payload,
                runtime_role,
            )
            if next_state == "CHAMPION":
                raise RegistryError(
                    "Champion lifecycle and operating-pointer changes require Promotion's "
                    "atomic transition, which is outside QC2-037"
                )
            evidence_ref = _evidence_ref(evidence_name, payload)
            event = LifecycleEvent(
                sequence=len(self._events[ref_key]) + 1,
                model_ref=_contract_ref(MODEL_SCHEMA, record.manifest),
                prior_state=prior_state,
                next_state=next_state,
                evidence_ref=evidence_ref,
                runtime_role=runtime_role,
                transitioned_at=transitioned_at,
            )
            self._events[ref_key].append(event)
            self._models[ref_key] = _ModelRecord(
                manifest=record.manifest,
                lifecycle_state=next_state,
                artifact_refs=record.artifact_refs,
                verified_artifacts=record.verified_artifacts,
                storage_receipts=record.storage_receipts,
            )
            return event

    def add_artifact_dependency(
        self,
        dependency: Mapping[str, Any],
        *,
        runtime_role: str,
    ) -> Mapping[str, Any]:
        if runtime_role != MODEL_REGISTRY_ROLE:
            raise RegistryError("artifact dependency links are written by model_registry")
        payload = _as_object(dependency, "ArtifactDependency")
        try:
            validate_contract("ArtifactDependency", payload)
        except (TypeError, ValueError, KeyError) as exc:
            raise RegistryError(f"ArtifactDependency contract is invalid: {exc}") from exc
        if payload["owning_authority"] != "model_registry":
            raise RegistryError("ArtifactDependency must be owned by model_registry")
        parent = _reference_key(payload["parent_ref"])
        child = _reference_key(payload["dependency_ref"])
        if parent[0] != ARTIFACT_SCHEMA or child[0] != ARTIFACT_SCHEMA:
            raise RegistryError("ArtifactDependency endpoints must be ArtifactManifest references")
        edge_key = (parent, child, payload["dependency_role"])
        with self._lock:
            if parent not in self._artifacts or child not in self._artifacts:
                raise RegistryError("ArtifactDependency endpoint has not been verified and staged")
            if edge_key in self._dependencies:
                raise RegistryError("ArtifactDependency link already exists")
            self._assert_acyclic({**self._dependencies, edge_key: payload})
            self._dependencies[edge_key] = _freeze_json(payload)
            return self._dependencies[edge_key]

    def dependency_links(self) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            return tuple(self._dependencies.values())

    def persistence_receipts(self, model_ref: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return verified storage receipts for the PostgreSQL commit boundary."""
        with self._lock:
            record = self._get_model(model_ref)
            stored = [_thaw_json(receipt) for receipt in record.storage_receipts]
            storage_receipts = [
                {
                    key: value
                    for key, value in receipt.items()
                    if key != "blob_receipts"
                }
                for receipt in stored
            ]
            blob_receipts = [
                {
                    **blob,
                    "manifest_id": receipt["manifest_id"],
                    "manifest_hash": receipt["manifest_hash"],
                }
                for receipt in stored
                for blob in receipt["blob_receipts"]
            ]
            return {
                "blob_receipts": blob_receipts,
                "storage_receipts": storage_receipts,
            }

    def link_retained_prediction(
        self,
        model_ref: Mapping[str, Any],
        prediction_ref: Mapping[str, Any],
        *,
        purpose: str,
        linked_at: str,
        runtime_role: str,
    ) -> RetentionLink:
        if runtime_role != MODEL_REGISTRY_ROLE:
            raise RegistryError("retention links are recorded by model_registry")
        ref_key = _model_ref_key(model_ref)
        retaining_ref = _as_object(prediction_ref, "retaining reference")
        if retaining_ref.get("target_schema_name") not in {
            _SCHEMA_NAMES["Prediction"],
            _SCHEMA_NAMES["PredictionSeal"],
        }:
            raise RegistryError("retention link target must be a Prediction or PredictionSeal")
        _validate_typed_reference(retaining_ref)
        with self._lock:
            self._get_model(model_ref)
            key = (ref_key, _reference_key(retaining_ref))
            if key in self._retention:
                existing = self._retention[key]
                if existing.purpose == purpose:
                    return existing
                raise RegistryError("retention reference already exists with a different purpose")
            link = RetentionLink(
                model_ref=model_ref,
                retaining_ref=retaining_ref,
                purpose=purpose,
                linked_at=linked_at,
            )
            self._retention[key] = link
            return link

    def retained_model_artifact(
        self,
        model_ref: Mapping[str, Any],
        retaining_ref: Mapping[str, Any],
        relative_path: str,
    ) -> bytes:
        ref_key = _model_ref_key(model_ref)
        retaining_key = _reference_key(retaining_ref)
        with self._lock:
            record = self._get_model(model_ref)
            if (ref_key, retaining_key) not in self._retention:
                raise RegistryError("model artifact is not retained by this prediction")
            artifact_refs = tuple(_reference_key(ref) for ref in record.artifact_refs)
            for artifact_key in artifact_refs:
                artifact = self._artifact_files.get(artifact_key)
                if artifact is not None and relative_path in artifact:
                    digest = record.verified_artifacts[artifact_key].blob_hashes[relative_path]
                    return self.blob_store.get(digest)
        raise RegistryError("retained model artifact path does not exist")

    def register_pointer(
        self,
        pointer: Mapping[str, Any],
        *,
        runtime_role: str,
    ) -> Mapping[str, Any]:
        if runtime_role != PROMOTION_ROLE:
            raise RegistryError("only Promotion may register an operating or Reference pointer")
        payload = _as_object(pointer, "ChampionPointer")
        model_ref = payload.get("model_ref")
        with self._lock:
            model = self._get_model(model_ref)
            if (
                model.manifest["evidence_class"] != payload.get("evidence_class")
                or model.manifest["environment_namespace"] != payload.get("environment_namespace")
            ):
                raise RegistryError("pointer evidence context differs from its registered model")
            return self.pointers.append(payload, runtime_role=runtime_role)

    def operating_pointer_state(self, epoch_ref: Mapping[str, Any]) -> OperatingPointerState:
        return self.pointers.state(epoch_ref)

    def reference_pointer(self, epoch_ref: Mapping[str, Any]) -> Mapping[str, Any] | None:
        return self.pointers.reference(epoch_ref)

    def load_for_production(
        self,
        model_ref: Mapping[str, Any],
        epoch_ref: Mapping[str, Any],
        *,
        runtime_role: str,
    ) -> Any:
        """Load only an exact sealed Champion through independently verified durable storage."""
        if runtime_role != "qc2_runtime_inference":
            raise RegistryError("production model loading requires the inference runtime role")
        with self._lock:
            record = self._get_model(model_ref)
            pointer_state = self.pointers.state(epoch_ref)
            if pointer_state.state != "CHAMPION_SET" or pointer_state.pointer is None:
                raise RegistryError("NO_CHAMPION: production inference has no operating model pointer")
            if record.lifecycle_state != "CHAMPION":
                raise RegistryError("production inference requires a CHAMPION lifecycle state")
            pointer = pointer_state.pointer
            if not _ref_equal(pointer["model_ref"], _contract_ref(MODEL_SCHEMA, record.manifest)):
                raise RegistryError("operating pointer does not select the requested model")
            if (
                record.manifest["environment_namespace"] != _PRODUCTION_ENVIRONMENT
                or record.manifest["evidence_class"] != _FORWARD_EVIDENCE
            ):
                raise RegistryError("fixture or non-production evidence cannot be loaded for production")
            if not self.metadata_durable or not self.blob_store.durable:
                raise RegistryError("production loading requires durable registry metadata and blobs")
            if self.signature_verifier is None:
                raise RegistryError("production loading requires an artifact signature verifier")
            primary_ref = _reference_key(record.manifest["artifact_manifest_ref"])
            primary = record.verified_artifacts.get(primary_ref)
            if primary is None:
                raise RegistryError("registered primary artifact manifest is missing")
            manifest = _thaw_json(primary.manifest)
            if not self.signature_verifier(manifest, record.manifest):
                raise RegistryError("registered artifact signature did not verify")
            files: dict[str, bytes] = {}
            for path, digest in primary.blob_hashes.items():
                files[path] = self.blob_store.get(digest)
            safe_bundle = verify_artifact_bundle(
                manifest,
                files,
                max_artifact_bytes=sum(len(data) for data in files.values()),
                model_manifest=record.manifest,
            )
            if safe_bundle.total_bytes <= 0:
                raise RegistryError("empty production model artifact bundle")
            from qc2_candidate_evaluator.inference import load_candidate_model

            return load_candidate_model(
                files["model.json"],
                record.manifest,
                record.manifest["dataset_ref"],
                record.manifest["split_ref"],
            )

    def _pointer_model_is_eligible(self, model_ref: Mapping[str, Any], role: str) -> bool:
        try:
            key = _model_ref_key(model_ref)
        except (KeyError, RegistryError):
            return False
        record = self._models.get(key)
        if record is None:
            return False
        if role == "OPERATING":
            return record.lifecycle_state in {"PROMOTION_ELIGIBLE", "CHAMPION"}
        return record.lifecycle_state in {"PROMOTION_ELIGIBLE", "CHAMPION", "RETIRED"}

    def _get_model(self, model_ref: Mapping[str, Any]) -> _ModelRecord:
        key = _model_ref_key(model_ref)
        record = self._models.get(key)
        if record is None:
            raise RegistryError("model reference is not registered")
        return record

    def _verify_transition_evidence(
        self,
        record: _ModelRecord,
        next_state: str,
        evidence_name: str,
        evidence: Mapping[str, Any],
        runtime_role: str,
    ) -> None:
        expected_model_ref = _contract_ref(MODEL_SCHEMA, record.manifest)
        if next_state == "CANDIDATE":
            if (
                runtime_role != VALIDATION_ROLE
                or evidence_name != "CandidateEvaluation"
                or evidence["verdict"] != "PASS"
                or not _ref_equal(evidence["candidate_ref"], expected_model_ref)
            ):
                raise RegistryError("CANDIDATE requires a passing independent CandidateEvaluation")
        elif next_state == "CHALLENGER":
            if (
                runtime_role != VALIDATION_ROLE
                or evidence_name != "ChallengerEvaluation"
                or evidence["verdict"] != "PASS"
                or not _ref_equal(evidence["challenger_ref"], expected_model_ref)
            ):
                raise RegistryError("CHALLENGER requires a passing independent comparison")
        elif next_state == "SHADOW":
            if (
                runtime_role != PREDICTION_ROLE
                or evidence_name != "ShadowPredictionSet"
                or not _ref_equal(evidence["model_ref"], expected_model_ref)
            ):
                raise RegistryError("SHADOW requires a model-bound ShadowPredictionSet")
        elif next_state == "PROMOTION_ELIGIBLE":
            report_refs = evidence.get("source_refs", ())
            if (
                runtime_role != VALIDATION_ROLE
                or evidence_name != "ValidationReport"
                or evidence.get("verdict") != "PASS"
                or not any(_ref_equal(ref, expected_model_ref) for ref in report_refs)
            ):
                raise RegistryError(
                    "PROMOTION_ELIGIBLE requires a passing ValidationReport bound to the model"
                )
        elif next_state == "REJECTED":
            if runtime_role != VALIDATION_ROLE or evidence_name not in {
                "CandidateEvaluation",
                "ChallengerEvaluation",
                "ValidationReport",
            }:
                raise RegistryError("REJECTED requires non-passing validation evidence")
            if evidence.get("verdict") == "PASS":
                raise RegistryError("passing evidence cannot reject a model")
            evidence_ref = (
                evidence.get("candidate_ref")
                or evidence.get("challenger_ref")
                or evidence.get("model_ref")
            )
            if evidence_ref is not None and not _ref_equal(evidence_ref, expected_model_ref):
                raise RegistryError("rejection evidence refers to a different model")
        elif next_state == "RETIRED":
            if runtime_role not in {MODEL_REGISTRY_ROLE, PROMOTION_ROLE}:
                raise RegistryError("retirement requires model_registry or Promotion authority")
            if runtime_role == PROMOTION_ROLE and evidence_name != "PromotionReceipt":
                raise RegistryError("Champion retirement requires a PromotionReceipt")
            if runtime_role == MODEL_REGISTRY_ROLE and record.lifecycle_state == "CHAMPION":
                raise RegistryError("model_registry cannot retire the operating Champion")

    def _make_dependency_edges(
        self,
        model: Mapping[str, Any],
        requested_links: Sequence[Mapping[str, Any]],
        staged_keys: set[tuple[str, str, str]],
    ) -> dict[tuple[tuple[str, str], tuple[str, str], str], Mapping[str, Any]]:
        primary_ref = model["artifact_manifest_ref"]
        references = _artifact_reference_values(model).values()
        automatically_linked = {
            _reference_key(ref): role
            for ref, role in (
                *((ref, "hyperparameters") for ref in model["hyperparameter_refs"]
                  if ref.get("target_schema_name") == ARTIFACT_SCHEMA),
                *((model["calibration_ref"], "calibration")
                  for _ in (0,) if model["calibration_ref"] is not None),
                *((ref, "learned_dependency") for ref in model["learned_dependency_refs"]
                  if ref.get("target_schema_name") == ARTIFACT_SCHEMA),
            )
        }
        edges: dict[
            tuple[tuple[str, str, str], tuple[str, str, str], str],
            Mapping[str, Any],
        ] = {}
        for dependency_ref in references:
            dependency_key = _reference_key(dependency_ref)
            primary_key = _reference_key(primary_ref)
            if dependency_key == primary_key:
                continue
            role = automatically_linked.get(dependency_key, "model_artifact")
            payload = {
                "schema_name": _SCHEMA_NAMES["ArtifactDependency"],
                "schema_version": "1.0",
                "id": new_uuidv7(),
                "created_at": _utc_now(),
                "owning_authority": "model_registry",
                "evidence_class": model["evidence_class"],
                "environment_namespace": model["environment_namespace"],
                "source_refs": [_contract_ref(MODEL_SCHEMA, model)],
                "parent_ref": primary_ref,
                "dependency_ref": dependency_ref,
                "dependency_role": role,
                "required_for_retention": True,
                "discovered_at": _utc_now(),
            }
            try:
                validate_contract("ArtifactDependency", payload)
            except (TypeError, ValueError, KeyError) as exc:
                raise RegistryError(f"derived ArtifactDependency is invalid: {exc}") from exc
            edge_key = (primary_key, dependency_key, role)
            edges[edge_key] = payload
        for raw_link in requested_links:
            payload = _as_object(raw_link, "ArtifactDependency")
            try:
                validate_contract("ArtifactDependency", payload)
            except (TypeError, ValueError, KeyError) as exc:
                raise RegistryError(f"ArtifactDependency contract is invalid: {exc}") from exc
            parent = _reference_key(payload["parent_ref"])
            child = _reference_key(payload["dependency_ref"])
            if parent[0] != ARTIFACT_SCHEMA or child[0] != ARTIFACT_SCHEMA:
                raise RegistryError("ArtifactDependency endpoints must be ArtifactManifest references")
            if parent not in staged_keys and parent not in self._artifacts:
                raise RegistryError("ArtifactDependency parent is not verified and staged")
            if child not in staged_keys and child not in self._artifacts:
                raise RegistryError("ArtifactDependency child is not verified and staged")
            edge_key = (parent, child, payload["dependency_role"])
            if edge_key in edges or edge_key in self._dependencies:
                raise RegistryError("ArtifactDependency link already exists")
            edges[edge_key] = payload
        return edges

    def _assert_acyclic(
        self,
        proposed: Mapping[
            tuple[tuple[str, str, str], tuple[str, str, str], str],
            Mapping[str, Any],
        ],
    ) -> None:
        graph: dict[tuple[str, str, str], set[tuple[str, str, str]]] = defaultdict(set)
        for edge_key in (*self._dependencies.keys(), *proposed.keys()):
            parent, child, _ = edge_key
            graph[parent].add(child)
        visiting: set[tuple[str, str, str]] = set()
        visited: set[tuple[str, str, str]] = set()

        def visit(node: tuple[str, str, str]) -> None:
            if node in visiting:
                raise RegistryError("ArtifactDependency graph contains a retention cycle")
            if node in visited:
                return
            visiting.add(node)
            for child in graph[node]:
                visit(child)
            visiting.remove(node)
            visited.add(node)

        for start in tuple(graph):
            visit(start)


def _required_artifact_refs(model: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    return set(_artifact_reference_values(model))


def _artifact_reference_values(
    model: Mapping[str, Any],
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    refs: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    candidates = [model["artifact_manifest_ref"]]
    candidates.extend(ref for ref in model["hyperparameter_refs"] if ref.get("target_schema_name") == ARTIFACT_SCHEMA)
    if model["calibration_ref"] is not None:
        candidates.append(model["calibration_ref"])
    candidates.extend(
        ref
        for ref in model["learned_dependency_refs"]
        if ref.get("target_schema_name") == ARTIFACT_SCHEMA
    )
    candidates.extend(
        ref
        for ref in model["source_refs"]
        if ref.get("target_schema_name") == ARTIFACT_SCHEMA
    )
    for ref in candidates:
        if ref.get("target_schema_name") != ARTIFACT_SCHEMA:
            raise RegistryError("ModelManifest artifact dependency has the wrong reference schema")
        refs[_reference_key(ref)] = ref
    primary_key = _reference_key(model["artifact_manifest_ref"])
    if primary_key not in refs:
        raise RegistryError("ModelManifest primary artifact reference is missing")
    return refs


def _model_key(model: Mapping[str, Any]) -> tuple[str, str]:
    return str(model["id"]), str(model["content_hash"])


def _model_ref_key(model_ref: Mapping[str, Any]) -> tuple[str, str]:
    ref = _as_object(model_ref, "ModelManifest reference")
    if ref.get("target_schema_name") != MODEL_SCHEMA:
        raise RegistryError("reference does not target a ModelManifest")
    _validate_typed_reference(ref)
    return str(ref["target_id"]), str(ref["content_hash"])


def _reference_key(ref: Mapping[str, Any]) -> tuple[str, str, str]:
    value = _as_object(ref, "typed reference")
    _validate_typed_reference(value)
    return str(value["target_schema_name"]), str(value["target_id"]), str(value["content_hash"])


def _reference_id(ref: Mapping[str, Any], name: str) -> str:
    value = _as_object(ref, name)
    if "target_id" not in value:
        raise RegistryError(f"{name} is missing target_id")
    _validate_typed_reference(value)
    return str(value["target_id"])


def _validate_typed_reference(ref: Mapping[str, Any]) -> None:
    schema_name = ref.get("target_schema_name")
    target_id = ref.get("target_id")
    content_hash = ref.get("content_hash")
    if not isinstance(schema_name, str) or not schema_name.startswith("qc2."):
        raise RegistryError("typed reference target schema name is invalid")
    if not isinstance(target_id, str) or not _is_uuidv7(target_id):
        raise RegistryError("typed reference target_id must be UUIDv7")
    if (
        not isinstance(content_hash, str)
        or len(content_hash) != 64
        or any(character not in "0123456789abcdef" for character in content_hash)
    ):
        raise RegistryError("typed reference content_hash must be lowercase SHA-256")


def _is_uuidv7(value: str) -> bool:
    parts = value.split("-")
    return (
        len(parts) == 5
        and [len(part) for part in parts] == [8, 4, 4, 4, 12]
        and all(character in "0123456789abcdef" for character in value.replace("-", ""))
        and parts[2][0] == "7"
        and parts[3][0] in "89ab"
    )


def _ref_equal(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    try:
        return _reference_key(actual) == _reference_key(expected)
    except (KeyError, RegistryError, TypeError):
        return False


def _contract_ref(schema_name: str, payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": str(payload["id"]),
        "content_hash": str(payload["content_hash"]),
    }


def _evidence_ref(name: str, payload: Mapping[str, Any]) -> dict[str, str]:
    digest = payload.get("content_hash") or payload.get("report_hash")
    if not isinstance(digest, str):
        raise RegistryError("lifecycle evidence does not carry an immutable hash")
    return {
        "target_schema_name": _SCHEMA_NAMES[name],
        "target_id": str(payload["id"]),
        "content_hash": digest,
    }


def _contract_name(schema_name: Any) -> str | None:
    if not isinstance(schema_name, str):
        return None
    return next((name for name, value in _SCHEMA_NAMES.items() if value == schema_name), None)


def _fixture_snapshot(model: Mapping[str, Any]) -> bool:
    return (
        model.get("environment_namespace") == "test"
        and model.get("evidence_class") == "SYNTHETIC_FIXTURE"
    )


def _as_object(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise RegistryError(f"{name} must be an object")
    return _thaw_json(raw)


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
