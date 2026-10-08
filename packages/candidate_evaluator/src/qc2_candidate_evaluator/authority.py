"""Candidate nomination, isolated holdout release, and immutable evaluation receipts."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import tracemalloc
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from qc2_contracts.runtime import (
    artifact_inventory_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

from .inference import (
    SafeCandidateModel,
    infer_predictions,
    load_candidate_model,
    validate_environment_manifest,
)
from .metrics import as_decimal, compute_metrics, metric_text
from .models import (
    _EVALUATOR_ACCESS_CAPABILITY,
    VALIDATION_RUNTIME_ROLE,
    CandidateNomination,
    CandidatePackage,
    EvaluationError,
    EvaluationResult,
    InformationReleaseEvent,
    QualificationRow,
    QualificationSnapshot,
    QualificationVault,
    freeze_json,
    thaw_json,
)
from .policy import POLICY_HASH, policy_payload


_MODEL_SCHEMA = "qc2.models_prediction.ModelManifest.v1"
_DATASET_SCHEMA = "qc2.outcomes_research.DatasetManifest.v1"
_SPLIT_SCHEMA = "qc2.outcomes_research.SplitManifest.v1"
_ARTIFACT_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"
_BUDGET_SCHEMA = "qc2.integrity_build.ResourceBudget.v1"
_HOLDOUT_SCHEMA = "qc2.outcomes_research.HoldoutAccessReceipt.v1"
_EVALUATION_SCHEMA = "qc2.outcomes_research.CandidateEvaluation.v1"
_HOLDOUT_HASH_DOMAIN = "qc2.candidate-evaluator-holdout.v1"
_REQUIRED_MODEL_FILES = {"model.json", "environment.json"}
_REQUIRED_PARAMETER_FILE = "hyperparameters.json"
_CONSUMED_FIELDS = [
    "candidate_prediction_vector",
    "qualification_features",
    "qualification_labels",
    "qualification_row_membership",
    "split_assignment",
]


def _instant(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise EvaluationError(f"{field} must be a UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvaluationError(f"{field} must be a UTC instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise EvaluationError(f"{field} must use UTC")
    return parsed


def _contract(name: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    payload = thaw_json(raw)
    if not isinstance(payload, dict):
        raise EvaluationError(f"{name} must be a JSON object")
    try:
        validate_contract(name, payload)
        verify_content_hash(name, payload)
    except (TypeError, ValueError, KeyError) as exc:
        raise EvaluationError(f"{name} contract or content hash is invalid: {exc}") from exc
    return payload


def _reference(schema_name: str, payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": str(payload["id"]),
        "content_hash": str(payload["content_hash"]),
    }


def _ref_matches(
    reference: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> bool:
    return all(
        reference.get(key) == expected.get(key)
        for key in ("target_schema_name", "target_id", "content_hash")
    )


def _key(reference: Mapping[str, Any]) -> tuple[str, str]:
    return str(reference["target_id"]), str(reference["content_hash"])


def _hash_json(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(thaw_json(payload))).hexdigest()


def _model_windows(model: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for field in ("validation_window", "qualification_window"):
        raw = model.get(field)
        if not isinstance(raw, str):
            raise EvaluationError(f"ModelManifest.{field} must contain JSON text")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EvaluationError(f"ModelManifest.{field} is not valid JSON") from exc
        if not isinstance(value, dict):
            raise EvaluationError(f"ModelManifest.{field} must contain an object")
        windows.append(value)
    return windows[0], windows[1]


def _validate_artifact_files(
    candidate: CandidatePackage,
    model: Mapping[str, Any],
    artifact_manifest: Mapping[str, Any],
    max_artifact_bytes: int,
) -> tuple[SafeCandidateModel, int]:
    if not _ref_matches(
        model["artifact_manifest_ref"],
        _reference(_ARTIFACT_SCHEMA, artifact_manifest),
    ):
        raise EvaluationError("ModelManifest does not bind the supplied ArtifactManifest")
    records = artifact_manifest.get("files")
    if not isinstance(records, list):
        raise EvaluationError("ArtifactManifest file inventory is invalid")
    if set(candidate.artifact_files) != _REQUIRED_MODEL_FILES:
        raise EvaluationError("candidate artifact bundle has an unsupported file inventory")
    record_by_path: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise EvaluationError("ArtifactManifest contains an invalid file record")
        path = record.get("relative_path")
        if not isinstance(path, str) or path in record_by_path:
            raise EvaluationError("ArtifactManifest contains a duplicate or invalid path")
        record_by_path[path] = record
    if set(record_by_path) != _REQUIRED_MODEL_FILES:
        raise EvaluationError("ArtifactManifest does not contain the exact safe-model files")
    if artifact_manifest["inventory_hash"] != artifact_inventory_hash(records):
        raise EvaluationError("candidate artifact inventory hash does not match its file records")
    if (
        artifact_manifest["owning_authority"] != "model_registry"
        or artifact_manifest["evidence_class"] != model["evidence_class"]
        or artifact_manifest["environment_namespace"] != model["environment_namespace"]
    ):
        raise EvaluationError("candidate artifact manifest has the wrong authority or context")

    total_bytes = 0
    for path, data in candidate.artifact_files.items():
        record = record_by_path[path]
        if (
            record.get("length_bytes") != len(data)
            or record.get("sha256") != hashlib.sha256(data).hexdigest()
            or record.get("media_type") != "application/json"
            or record.get("schema_version") != "1.0"
        ):
            raise EvaluationError(f"candidate artifact bytes do not match {path} inventory")
        if path == "model.json" and record.get("schema_name") != "qc2.apexlab.SafeModelArtifact.v1":
            raise EvaluationError("model.json does not use the allowlisted candidate schema")
        if path == "environment.json" and record.get("schema_name") != "qc2.apexlab.TrainingEnvironment.v1":
            raise EvaluationError("environment.json does not use the expected data schema")
        total_bytes += len(data)

    parameter_manifest = candidate.hyperparameter_manifest
    parameter_bytes = candidate.hyperparameter_bytes
    parameter_refs = model.get("hyperparameter_refs")
    if (
        not isinstance(parameter_refs, list)
        or len(parameter_refs) != 1
        or parameter_manifest is None
        or parameter_bytes is None
    ):
        raise EvaluationError("candidate hyperparameter artifact is missing")
    parameter = _contract("ArtifactManifest", parameter_manifest)
    if not _ref_matches(
        parameter_refs[0],
        _reference(_ARTIFACT_SCHEMA, parameter),
    ):
        raise EvaluationError("ModelManifest does not bind the hyperparameter artifact")
    parameter_records = parameter.get("files")
    if not isinstance(parameter_records, list) or len(parameter_records) != 1:
        raise EvaluationError("hyperparameter manifest must contain one file")
    parameter_record = parameter_records[0]
    if (
        parameter_record.get("relative_path") != _REQUIRED_PARAMETER_FILE
        or parameter_record.get("length_bytes") != len(parameter_bytes)
        or parameter_record.get("sha256") != hashlib.sha256(parameter_bytes).hexdigest()
        or parameter_record.get("media_type") != "application/json"
        or parameter_record.get("schema_name") != "qc2.apexlab.FrozenHyperparameterSpace.v1"
        or parameter_record.get("schema_version") != "1.0"
    ):
        raise EvaluationError("hyperparameter bytes do not match their artifact inventory")
    if parameter["inventory_hash"] != artifact_inventory_hash(parameter_records):
        raise EvaluationError("hyperparameter inventory hash does not match its file record")
    total_bytes += len(parameter_bytes)
    if (
        parameter["owning_authority"] != "model_registry"
        or parameter["evidence_class"] != model["evidence_class"]
        or parameter["environment_namespace"] != model["environment_namespace"]
    ):
        raise EvaluationError("hyperparameter manifest has the wrong authority or context")
    if total_bytes > max_artifact_bytes:
        raise EvaluationError("candidate artifact bundle exceeds its resource budget")

    validate_environment_manifest(
        candidate.artifact_files["environment.json"],
        model,
    )
    safe_model = load_candidate_model(
        candidate.artifact_files["model.json"],
        model,
        _reference(_DATASET_SCHEMA, _contract("DatasetManifest", candidate.dataset_manifest)),
        _reference(_SPLIT_SCHEMA, _contract("SplitManifest", candidate.split_manifest)),
    )
    return safe_model, total_bytes


def _validate_candidate(
    candidate: CandidatePackage,
    approved_budgets: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    SafeCandidateModel,
    int,
]:
    model = _contract("ModelManifest", candidate.model_manifest)
    dataset = _contract("DatasetManifest", candidate.dataset_manifest)
    split = _contract("SplitManifest", candidate.split_manifest)
    artifact_manifest = _contract("ArtifactManifest", candidate.artifact_manifest)
    budget = _contract("ResourceBudget", candidate.resource_budget)
    budget_key = _key(_reference(_BUDGET_SCHEMA, budget))
    approved_budget = approved_budgets.get(budget_key)
    if approved_budget is None or budget != thaw_json(approved_budget):
        raise EvaluationError(
            "candidate resource budget is not present in the evaluator's approved catalog"
        )
    dataset_ref = _reference(_DATASET_SCHEMA, dataset)
    split_ref = _reference(_SPLIT_SCHEMA, split)
    if (
        model["owning_authority"] != "model_registry"
        or model["lifecycle_state"] not in {"RESEARCH", "CANDIDATE"}
        or model["safe_format"] != "json"
        or model["evidence_class"] != dataset["evidence_class"]
        or model["environment_namespace"] != dataset["environment_namespace"]
        or not _ref_matches(model["dataset_ref"], dataset_ref)
        or not _ref_matches(model["split_ref"], split_ref)
    ):
        raise EvaluationError("candidate model is not bound to the nominated dataset and split")
    if (
        dataset["evidence_class"] != split["evidence_class"]
        or dataset["environment_namespace"] != split["environment_namespace"]
        or dataset["id"] != split["dataset_ref"]["target_id"]
        or dataset["content_hash"] != split["dataset_ref"]["content_hash"]
    ):
        raise EvaluationError("dataset and split context does not match")
    if (
        budget["evidence_class"] != dataset["evidence_class"]
        or budget["environment_namespace"] != dataset["environment_namespace"]
        or type(budget["max_artifact_bytes"]) is not int
        or budget["max_artifact_bytes"] <= 0
        or type(budget["max_cpu_seconds"]) is not int
        or type(budget["max_elapsed_seconds"]) is not int
        or type(budget["max_memory_bytes"]) is not int
    ):
        raise EvaluationError("resource budget context or limits are invalid")
    budget_ref = _reference(_BUDGET_SCHEMA, budget)
    if budget_ref not in model["source_refs"] or budget_ref not in artifact_manifest["source_refs"]:
        raise EvaluationError("candidate provenance omits its frozen resource budget")
    expected_limits = {
        f"max_artifact_bytes={budget['max_artifact_bytes']}",
        f"max_cpu_seconds={budget['max_cpu_seconds']}",
        f"max_elapsed_seconds={budget['max_elapsed_seconds']}",
        f"max_memory_bytes={budget['max_memory_bytes']}",
    }
    if not expected_limits.issubset(set(model["resource_constraints"])):
        raise EvaluationError("model resource constraints differ from its declared budget")

    safe_model, artifact_bytes = _validate_artifact_files(
        candidate,
        model,
        artifact_manifest,
        budget["max_artifact_bytes"],
    )
    return model, dataset, split, artifact_manifest, budget, safe_model, artifact_bytes


class CandidateEvaluator:
    """Validation-role service that seals one nominee before consuming a holdout."""

    __slots__ = (
        "__vault",
        "__approved_budgets",
        "__lock",
        "__nominations",
        "__dataset_nominations",
        "__consumed_datasets",
        "__events",
    )

    def __init__(
        self,
        vault: QualificationVault,
        *,
        approved_resource_budgets: tuple[Mapping[str, Any], ...],
    ) -> None:
        if not approved_resource_budgets:
            raise EvaluationError("evaluator requires independently approved resource budgets")
        approved: dict[tuple[str, str], Mapping[str, Any]] = {}
        for raw_budget in approved_resource_budgets:
            budget = _contract("ResourceBudget", raw_budget)
            if budget["owning_authority"] != "configuration":
                raise EvaluationError("approved resource budget must be owned by configuration")
            key = _key(_reference(_BUDGET_SCHEMA, budget))
            if key in approved:
                raise EvaluationError("approved resource budget catalog contains duplicates")
            approved[key] = freeze_json(budget)
        self.__vault = vault
        self.__approved_budgets = freeze_json(approved)
        self.__lock = threading.RLock()
        self.__nominations: dict[str, tuple[CandidateNomination, CandidatePackage]] = {}
        self.__dataset_nominations: dict[tuple[str, str], str] = {}
        self.__consumed_datasets: set[tuple[str, str]] = set()
        self.__events: list[InformationReleaseEvent] = []

    @property
    def information_release_log(self) -> tuple[InformationReleaseEvent, ...]:
        with self.__lock:
            return tuple(self.__events)

    def nominate(
        self,
        candidate: CandidatePackage,
        *,
        nominated_by: str,
        nominated_at: str,
    ) -> CandidateNomination:
        _instant(nominated_at, "nominated_at")
        if nominated_by != "qc2_runtime_model_registry":
            raise EvaluationError("candidate nomination requires the model-registry runtime role")
        model, dataset, split, _, _, _, _ = _validate_candidate(
            candidate,
            self.__approved_budgets,
        )
        dataset_ref = _reference(_DATASET_SCHEMA, dataset)
        split_ref = _reference(_SPLIT_SCHEMA, split)
        candidate_ref = _reference(_MODEL_SCHEMA, model)
        key = _key(dataset_ref)
        with self.__lock:
            if key in self.__dataset_nominations:
                self.__append_event(
                    "NOMINATION_REUSE_BLOCKED",
                    nominated_at,
                    dataset_ref,
                    candidate_ref,
                    {"reason_code": "DATASET_ALREADY_NOMINATED"},
                )
                raise EvaluationError("a holdout dataset accepts only one candidate nomination")
            nomination = CandidateNomination(
                nomination_id=new_uuidv7(),
                candidate_ref=candidate_ref,
                dataset_ref=dataset_ref,
                split_ref=split_ref,
                nominated_at=nominated_at,
                nominated_by=nominated_by,
                policy_hash=POLICY_HASH,
            )
            self.__nominations[nomination.nomination_id] = (nomination, candidate)
            self.__dataset_nominations[key] = nomination.nomination_id
            self.__append_event(
                "CANDIDATE_NOMINATED",
                nominated_at,
                dataset_ref,
                candidate_ref,
                {
                    "nomination_id": nomination.nomination_id,
                    "split_ref": split_ref,
                    "nominated_by": nominated_by,
                    "policy_hash": POLICY_HASH,
                },
            )
            return nomination

    def evaluate(
        self,
        nomination: CandidateNomination,
        *,
        evaluated_at: str,
    ) -> EvaluationResult:
        evaluated_time = _instant(evaluated_at, "evaluated_at")
        with self.__lock:
            stored = self.__nominations.get(nomination.nomination_id)
            if stored is None or stored[0] != nomination:
                raise EvaluationError("candidate nomination was not issued by this evaluator")
            issued, candidate = stored
            if evaluated_time < _instant(issued.nominated_at, "nominated_at"):
                raise EvaluationError("evaluation cannot precede candidate nomination")
            key = _key(issued.dataset_ref)
            if key in self.__consumed_datasets:
                self.__append_event(
                    "HOLDOUT_REUSE_BLOCKED",
                    evaluated_at,
                    issued.dataset_ref,
                    issued.candidate_ref,
                    {"reason_code": "HOLDOUT_ALREADY_CONSUMED"},
                )
                raise EvaluationError("a consumed holdout cannot be nominated or evaluated again")
            # Consumption is recorded before the service opens labels. A failed run
            # after this point still burns the one-use holdout.
            self.__consumed_datasets.add(key)
            access_event = self.__append_event(
                "HOLDOUT_ACCESS_GRANTED",
                evaluated_at,
                issued.dataset_ref,
                issued.candidate_ref,
                {
                    "nomination_id": issued.nomination_id,
                    "runtime_role": VALIDATION_RUNTIME_ROLE,
                    "access_scope": "METRICS_ONLY",
                    "consumed_fields": list(_CONSUMED_FIELDS),
                },
            )

        try:
            model, dataset, split, artifact_manifest, budget, safe_model, artifact_bytes = (
                _validate_candidate(candidate, self.__approved_budgets)
            )
            snapshot = self.__vault._release_for_evaluation(
                issued.dataset_ref,
                issued.split_ref,
                capability=_EVALUATOR_ACCESS_CAPABILITY,
                runtime_role=VALIDATION_RUNTIME_ROLE,
            )
            self._validate_qualification_rows(
                snapshot,
                issued,
                model,
                dataset,
                safe_model,
                evaluated_at,
            )
            predictions, resource_use = self._infer_with_resource_accounting(
                safe_model,
                snapshot.qualification_rows,
            )
            labels = tuple(
                as_decimal(row.label, "qualification label")
                for row in snapshot.qualification_rows
            )
            metrics = compute_metrics(safe_model.task, labels, predictions)
            resource_pass = (
                artifact_bytes <= budget["max_artifact_bytes"]
                and resource_use["elapsed_seconds_decimal"] <= budget["max_elapsed_seconds"]
                and resource_use["cpu_seconds_decimal"] <= budget["max_cpu_seconds"]
                and resource_use["peak_memory_bytes"] <= budget["max_memory_bytes"]
            )
            resource_use["artifact_bytes"] = artifact_bytes
            holdout_receipt = self._make_holdout_receipt(
                issued,
                dataset,
                split,
                evaluated_at,
                sorted(metrics),
            )
            receipt_ref = {
                "target_schema_name": _HOLDOUT_SCHEMA,
                "target_id": holdout_receipt["id"],
                "content_hash": holdout_receipt["receipt_hash"],
            }
            refs = [
                thaw_json(issued.candidate_ref),
                thaw_json(issued.dataset_ref),
                thaw_json(issued.split_ref),
                receipt_ref,
                _reference(_BUDGET_SCHEMA, budget),
            ]
            gates = self._make_gates(
                evaluated_at=evaluated_at,
                refs=refs,
                evidence_class=dataset["evidence_class"],
                task=safe_model.task,
                metrics=metrics,
                resource_pass=resource_pass,
            )
            verdict = self._verdict(gates)
            report_payload: dict[str, Any] = {
                "schema_name": "qc2.candidate_evaluation_report.v1",
                "schema_version": "1.0",
                "policy": policy_payload(),
                "candidate_ref": thaw_json(issued.candidate_ref),
                "dataset_ref": thaw_json(issued.dataset_ref),
                "split_ref": thaw_json(issued.split_ref),
                "holdout_receipt_ref": receipt_ref,
                "evidence_class": dataset["evidence_class"],
                "evaluation_status": verdict,
                "qualification_row_count": len(snapshot.qualification_rows),
                "metrics": metrics,
                "resource_usage": {
                    key: value
                    for key, value in resource_use.items()
                    if not key.endswith("_decimal")
                },
                "gate_results": gates,
                "holdout_open_event_hash": access_event.event_hash,
            }
            report_hash = _hash_json(report_payload)
            report_payload["report_hash"] = report_hash
            evaluation = {
                "schema_name": _EVALUATION_SCHEMA,
                "schema_version": "1.0",
                "id": new_uuidv7(),
                "created_at": evaluated_at,
                "owning_authority": "validation",
                "evidence_class": dataset["evidence_class"],
                "environment_namespace": dataset["environment_namespace"],
                "source_refs": refs,
                "candidate_ref": thaw_json(issued.candidate_ref),
                "evaluator_identity": "qc2_candidate_evaluator",
                "dataset_ref": thaw_json(issued.dataset_ref),
                "split_ref": thaw_json(issued.split_ref),
                "gate_results": gates,
                "evaluated_at": evaluated_at,
                "verdict": verdict,
                "report_hash": report_hash,
            }
            try:
                validate_contract("HoldoutAccessReceipt", holdout_receipt)
                validate_contract("CandidateEvaluation", evaluation)
            except (TypeError, ValueError, KeyError) as exc:
                raise EvaluationError(f"evaluation receipt violates its QC2 contract: {exc}") from exc
            with self.__lock:
                release_event = self.__append_event(
                    "AGGREGATE_METRICS_RELEASED",
                    evaluated_at,
                    issued.dataset_ref,
                    issued.candidate_ref,
                    {
                        "nomination_id": issued.nomination_id,
                        "holdout_receipt_id": holdout_receipt["id"],
                        "holdout_receipt_hash": holdout_receipt["receipt_hash"],
                        "candidate_evaluation_id": evaluation["id"],
                        "report_hash": report_hash,
                        "metric_names": sorted(metrics),
                    },
                )
                self.__append_event(
                    "EVALUATION_RECEIPTS_ISSUED",
                    evaluated_at,
                    issued.dataset_ref,
                    issued.candidate_ref,
                    {
                        "nomination_id": issued.nomination_id,
                        "candidate_evaluation_id": evaluation["id"],
                        "candidate_evaluation_verdict": verdict,
                        "candidate_evaluation_hash": report_hash,
                        "holdout_receipt_id": holdout_receipt["id"],
                        "holdout_receipt_hash": holdout_receipt["receipt_hash"],
                        "aggregate_release_event_hash": release_event.event_hash,
                    },
                )
            return EvaluationResult(
                nomination=issued,
                holdout_receipt=holdout_receipt,
                candidate_evaluation=evaluation,
                report=report_payload,
            )
        except Exception as exc:
            with self.__lock:
                self.__append_event(
                    "EVALUATION_ABORTED_AFTER_HOLDOUT_ACCESS",
                    evaluated_at,
                    issued.dataset_ref,
                    issued.candidate_ref,
                    {
                        "nomination_id": issued.nomination_id,
                        "reason_code": (
                            "EVALUATION_INPUT_REJECTED"
                            if isinstance(exc, EvaluationError)
                            else "EVALUATION_INTERNAL_ERROR"
                        ),
                    },
                )
            raise

    @staticmethod
    def _validate_qualification_rows(
        snapshot: QualificationSnapshot,
        nomination: CandidateNomination,
        model: Mapping[str, Any],
        dataset: Mapping[str, Any],
        safe_model: SafeCandidateModel,
        evaluated_at: str,
    ) -> None:
        if (
            snapshot.dataset_ref != nomination.dataset_ref
            or snapshot.split_ref != nomination.split_ref
        ):
            raise EvaluationError("qualification source returned a different dataset or split")
        if len(set(snapshot.expected_qualification_row_keys)) != len(
            snapshot.expected_qualification_row_keys
        ):
            raise EvaluationError("qualification membership contains duplicate row keys")
        row_keys = tuple(row.row_key for row in snapshot.qualification_rows)
        training_keys = tuple(row.row_key for row in snapshot.training_rows)
        validation_keys = tuple(row.row_key for row in snapshot.validation_rows)
        if (
            len(set(row_keys)) != len(row_keys)
            or len(set(training_keys)) != len(training_keys)
            or len(set(validation_keys)) != len(validation_keys)
            or set(row_keys) != set(snapshot.expected_qualification_row_keys)
            or not row_keys
        ):
            raise EvaluationError(
                "held-out rows must match the complete sealed qualification membership"
            )
        if any(row.split_role != "QUALIFICATION" for row in snapshot.qualification_rows):
            raise EvaluationError("held-out evaluation contains a non-qualification row")
        if set(row_keys) & (set(safe_model.training_row_keys) | set(safe_model.validation_row_keys)):
            raise EvaluationError("candidate training or validation rows overlap the holdout")
        if (
            set(training_keys) != set(safe_model.training_row_keys)
            or set(validation_keys) != set(safe_model.validation_row_keys)
        ):
            raise EvaluationError(
                "candidate row inventories differ from the independently sealed split"
            )
        if (
            set(training_keys) & set(validation_keys)
            or set(training_keys) & set(row_keys)
            or set(validation_keys) & set(row_keys)
        ):
            raise EvaluationError("sealed train, validation, and qualification rows overlap")
        if set(safe_model.training_row_keys) & set(safe_model.validation_row_keys):
            raise EvaluationError("candidate training and validation inventories overlap")
        if any(set(row.features) != set(safe_model.feature_ids) for row in snapshot.qualification_rows):
            raise EvaluationError("qualification feature inventory differs from the candidate")
        if snapshot.split_assignment_hash != dataset["split_assignment_hash"]:
            raise EvaluationError("qualification split assignment hash differs from DatasetManifest")
        validation_window, qualification_window = _model_windows(model)
        if qualification_window.get("labels_released") is not False:
            raise EvaluationError("candidate declares qualification labels were released")
        if tuple(sorted(safe_model.validation_row_keys)) != tuple(
            sorted(validation_window.get("released_row_keys", []))
        ):
            raise EvaluationError("candidate validation rows differ from its declared manifest")
        cutoff = _instant(model["training_cutoff"], "ModelManifest.training_cutoff")
        evaluated = _instant(evaluated_at, "evaluated_at")
        if any(_instant(row.label_available_at, "label_available_at") > evaluated for row in snapshot.qualification_rows):
            raise EvaluationError("qualification labels were not mature at evaluation time")
        if any(cutoff >= _instant(row.label_available_at, "label_available_at") for row in snapshot.qualification_rows):
            raise EvaluationError("candidate training cutoff reaches qualification label availability")

    @staticmethod
    def _infer_with_resource_accounting(
        model: SafeCandidateModel,
        rows: tuple[QualificationRow, ...],
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        tracemalloc.reset_peak()
        initial_current, _ = tracemalloc.get_traced_memory()
        start_wall = time.perf_counter()
        start_cpu = time.process_time()
        try:
            first = infer_predictions(model, rows)
            second = infer_predictions(model, rows)
        finally:
            elapsed = time.perf_counter() - start_wall
            cpu = time.process_time() - start_cpu
            current, peak = tracemalloc.get_traced_memory()
            if not was_tracing:
                tracemalloc.stop()
        if first != second:
            raise EvaluationError("candidate inference is not deterministic")
        memory = max(0, peak - initial_current)
        use = {
            "elapsed_seconds": metric_text(as_decimal(elapsed, "elapsed time")),
            "elapsed_seconds_decimal": elapsed,
            "cpu_seconds": metric_text(as_decimal(cpu, "CPU time")),
            "cpu_seconds_decimal": cpu,
            "peak_memory_bytes": memory,
            "artifact_bytes": 0,
        }
        return first, use

    @staticmethod
    def _make_holdout_receipt(
        nomination: CandidateNomination,
        dataset: Mapping[str, Any],
        split: Mapping[str, Any],
        evaluated_at: str,
        metric_names: list[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_name": _HOLDOUT_SCHEMA,
            "schema_version": "1.0",
            "id": new_uuidv7(),
            "created_at": evaluated_at,
            "owning_authority": "validation",
            "evidence_class": dataset["evidence_class"],
            "environment_namespace": dataset["environment_namespace"],
            "source_refs": [
                thaw_json(nomination.candidate_ref),
                thaw_json(nomination.dataset_ref),
                thaw_json(nomination.split_ref),
            ],
            "dataset_ref": thaw_json(nomination.dataset_ref),
            "evaluator_identity": "qc2_candidate_evaluator",
            "access_scope": "METRICS_ONLY",
            "requested_at": evaluated_at,
            "granted_at": evaluated_at,
            "consumed_fields": list(_CONSUMED_FIELDS),
            "released_metrics": metric_names,
            "receipt_hash": "0" * 64,
        }
        payload["receipt_hash"] = domain_separated_sha256(
            _HOLDOUT_HASH_DOMAIN,
            canonical_json_bytes(thaw_json({
                key: value for key, value in payload.items() if key != "receipt_hash"
            })),
        )
        return payload

    @staticmethod
    def _make_gates(
        *,
        evaluated_at: str,
        refs: list[dict[str, str]],
        evidence_class: str,
        task: str,
        metrics: Mapping[str, str],
        resource_pass: bool,
    ) -> list[dict[str, Any]]:
        leakage_gate = {
            "gate_id": "heldout_leakage",
            "status": "PASS",
            "reason_codes": ["SEALED_MEMBERSHIP_AND_ROW_DISJOINTNESS_VERIFIED"],
        }
        deterministic_gate = {
            "gate_id": "deterministic_inference",
            "status": "PASS",
            "reason_codes": ["INDEPENDENT_SAFE_INTERPRETER_REPEATED_IDENTICALLY"],
        }
        resource_gate = {
            "gate_id": "resource_budget",
            "status": "PASS" if resource_pass else "BLOCK",
            "reason_codes": (
                ["OBSERVED_RESOURCE_USE_WITHIN_FROZEN_BUDGET"]
                if resource_pass
                else ["OBSERVED_RESOURCE_USE_EXCEEDS_FROZEN_BUDGET"]
            ),
        }
        if task == "REGRESSION":
            rmse = as_decimal(metrics["rmse"], "RMSE")
            baseline = as_decimal(metrics["zero_baseline_rmse"], "baseline RMSE")
            if baseline == 0:
                regression_status = "UNKNOWN"
                regression_reasons = ["ZERO_BASELINE_HAS_NO_COMPARATIVE_HEADROOM"]
            elif rmse < baseline:
                regression_status = "PASS"
                regression_reasons = ["RMSE_BEATS_FROZEN_ZERO_PREDICTION_BASELINE"]
            else:
                regression_status = "BLOCK"
                regression_reasons = ["RMSE_DOES_NOT_BEAT_FROZEN_ZERO_PREDICTION_BASELINE"]
            calibration_status = "WARN"
            calibration_reasons = ["CALIBRATION_NOT_APPLICABLE_TO_REGRESSION_TASK"]
        else:
            regression_status = "WARN"
            regression_reasons = ["REGRESSION_METRIC_NOT_APPLICABLE_TO_CLASSIFICATION_TASK"]
            calibration_status = "UNKNOWN"
            calibration_reasons = ["CALIBRATION_THRESHOLD_POLICY_NOT_FROZEN"]
        evidence_status = (
            "UNKNOWN"
            if evidence_class in {"SYNTHETIC_FIXTURE", "HISTORICAL_RECONSTRUCTED"}
            else "PASS"
        )
        evidence_reasons = (
            ["NONFORWARD_EVIDENCE_CANNOT_QUALIFY_A_CANDIDATE"]
            if evidence_status == "UNKNOWN"
            else ["FORWARD_EVIDENCE_CLASS_RECORDED"]
        )
        raw_gates = [
            leakage_gate,
            deterministic_gate,
            resource_gate,
            {
                "gate_id": "regression_performance",
                "status": regression_status,
                "reason_codes": regression_reasons,
            },
            {
                "gate_id": "calibration",
                "status": calibration_status,
                "reason_codes": calibration_reasons,
            },
            {
                "gate_id": "evidence_class",
                "status": evidence_status,
                "reason_codes": evidence_reasons,
            },
            {
                "gate_id": "evaluator_policy",
                "status": "PASS",
                "reason_codes": ["CODE_OWNED_POLICY_HASH_MATCHES_NOMINATION"],
            },
        ]
        return [
            {
                **gate,
                "evaluated_at": evaluated_at,
                "source_refs": refs,
            }
            for gate in raw_gates
        ]

    @staticmethod
    def _verdict(gates: list[dict[str, Any]]) -> str:
        statuses = {gate["status"] for gate in gates}
        if "BLOCK" in statuses:
            return "FAIL"
        if statuses.intersection({"UNKNOWN", "UNAVAILABLE"}):
            return "INSUFFICIENT_EVIDENCE"
        return "PASS"

    def __append_event(
        self,
        event_type: str,
        recorded_at: str,
        dataset_ref: Mapping[str, Any],
        candidate_ref: Mapping[str, Any],
        details: Mapping[str, Any],
    ) -> InformationReleaseEvent:
        prior = self.__events[-1].event_hash if self.__events else None
        payload = {
            "sequence": len(self.__events) + 1,
            "event_type": event_type,
            "recorded_at": recorded_at,
            "dataset_ref": thaw_json(dataset_ref),
            "candidate_ref": thaw_json(candidate_ref),
            "policy_hash": POLICY_HASH,
            "details": thaw_json(details),
            "prior_event_hash": prior,
        }
        serialized = canonical_json_bytes(payload).decode("utf-8")
        event = InformationReleaseEvent(
            sequence=payload["sequence"],
            event_type=event_type,
            recorded_at=recorded_at,
            payload_json=serialized,
            prior_event_hash=prior,
            event_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        )
        self.__events.append(event)
        return event
