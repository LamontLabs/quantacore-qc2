"""Immutable evaluator inputs and capability-separated dataset projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


VALIDATION_RUNTIME_ROLE = "qc2_runtime_validation"
TRAINER_RUNTIME_ROLE = "qc2_runtime_apexlab"
NOMINATION_RUNTIME_ROLE = "qc2_runtime_model_registry"

# This capability is intentionally not exported from the package surface.
_EVALUATOR_ACCESS_CAPABILITY = object()


class EvaluationError(ValueError):
    """A nomination or evaluation violates the independent authority boundary."""


def freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_json(item) for item in value]
    return value


def _ref_key(reference: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(reference["target_schema_name"]),
        str(reference["target_id"]),
        str(reference.get("content_hash", "")),
    )


@dataclass(frozen=True, slots=True)
class TrainingRow:
    row_key: str
    features: Mapping[str, str]
    label: str

    def __post_init__(self) -> None:
        if not self.row_key:
            raise EvaluationError("training row key is required")
        object.__setattr__(self, "features", freeze_json(self.features))


@dataclass(frozen=True, slots=True)
class QualificationRow:
    row_key: str
    split_role: str
    features: Mapping[str, str]
    label: str
    label_available_at: str

    def __post_init__(self) -> None:
        if not self.row_key:
            raise EvaluationError("qualification row key is required")
        object.__setattr__(self, "features", freeze_json(self.features))


@dataclass(frozen=True, slots=True)
class QualificationSnapshot:
    dataset_ref: Mapping[str, Any]
    split_ref: Mapping[str, Any]
    training_rows: tuple[TrainingRow, ...]
    validation_rows: tuple[TrainingRow, ...]
    qualification_rows: tuple[QualificationRow, ...]
    expected_qualification_row_keys: tuple[str, ...]
    split_assignment_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_ref", freeze_json(self.dataset_ref))
        object.__setattr__(self, "split_ref", freeze_json(self.split_ref))
        object.__setattr__(self, "training_rows", tuple(self.training_rows))
        object.__setattr__(self, "validation_rows", tuple(self.validation_rows))
        object.__setattr__(self, "qualification_rows", tuple(self.qualification_rows))
        object.__setattr__(
            self,
            "expected_qualification_row_keys",
            tuple(self.expected_qualification_row_keys),
        )


@dataclass(frozen=True, slots=True)
class TrainerDatasetView:
    """Training-role projection. Qualification rows and labels are not represented."""

    dataset_ref: Mapping[str, Any]
    split_ref: Mapping[str, Any]
    training_rows: tuple[TrainingRow, ...]
    validation_rows: tuple[TrainingRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_ref", freeze_json(self.dataset_ref))
        object.__setattr__(self, "split_ref", freeze_json(self.split_ref))
        object.__setattr__(self, "training_rows", tuple(self.training_rows))
        object.__setattr__(self, "validation_rows", tuple(self.validation_rows))


class QualificationVault:
    """Role-checked fixture/service boundary for sealed qualification rows."""

    __slots__ = ("__snapshots",)

    def __init__(self, snapshots: tuple[QualificationSnapshot, ...]) -> None:
        indexed: dict[
            tuple[tuple[str, str, str], tuple[str, str, str]],
            QualificationSnapshot,
        ] = {}
        for snapshot in snapshots:
            key = (_ref_key(snapshot.dataset_ref), _ref_key(snapshot.split_ref))
            if key in indexed:
                raise EvaluationError("qualification snapshot is duplicated")
            indexed[key] = snapshot
        self.__snapshots = MappingProxyType(indexed)

    def trainer_view(
        self,
        dataset_ref: Mapping[str, Any],
        split_ref: Mapping[str, Any],
        *,
        runtime_role: str,
    ) -> TrainerDatasetView:
        if runtime_role != TRAINER_RUNTIME_ROLE:
            raise EvaluationError("trainer data access requires the ApexLab runtime role")
        snapshot = self.__find_snapshot(dataset_ref, split_ref)
        return TrainerDatasetView(
            dataset_ref=snapshot.dataset_ref,
            split_ref=snapshot.split_ref,
            training_rows=snapshot.training_rows,
            validation_rows=snapshot.validation_rows,
        )

    def __find_snapshot(
        self,
        dataset_ref: Mapping[str, Any],
        split_ref: Mapping[str, Any],
    ) -> QualificationSnapshot:
        key = (_ref_key(dataset_ref), _ref_key(split_ref))
        snapshot = self.__snapshots.get(key)
        if snapshot is None:
            raise EvaluationError("no sealed qualification snapshot matches the references")
        return snapshot

    def _release_for_evaluation(
        self,
        dataset_ref: Mapping[str, Any],
        split_ref: Mapping[str, Any],
        *,
        capability: object,
        runtime_role: str,
    ) -> QualificationSnapshot:
        if (
            capability is not _EVALUATOR_ACCESS_CAPABILITY
            or runtime_role != VALIDATION_RUNTIME_ROLE
        ):
            raise EvaluationError("held-out labels are restricted to the validation role")
        return self.__find_snapshot(dataset_ref, split_ref)


@dataclass(frozen=True, slots=True)
class CandidatePackage:
    model_manifest: Mapping[str, Any]
    artifact_manifest: Mapping[str, Any]
    dataset_manifest: Mapping[str, Any]
    split_manifest: Mapping[str, Any]
    resource_budget: Mapping[str, Any]
    artifact_files: Mapping[str, bytes]
    hyperparameter_manifest: Mapping[str, Any] | None = None
    hyperparameter_bytes: bytes | None = None

    def __post_init__(self) -> None:
        for name in (
            "model_manifest",
            "artifact_manifest",
            "dataset_manifest",
            "split_manifest",
            "resource_budget",
        ):
            object.__setattr__(self, name, freeze_json(getattr(self, name)))
        if self.hyperparameter_manifest is not None:
            object.__setattr__(
                self,
                "hyperparameter_manifest",
                freeze_json(self.hyperparameter_manifest),
            )
        if self.hyperparameter_bytes is not None and not isinstance(
            self.hyperparameter_bytes, bytes
        ):
            raise EvaluationError("hyperparameter artifact must be immutable bytes")
        files = dict(self.artifact_files)
        if any(not isinstance(path, str) or not isinstance(data, bytes) for path, data in files.items()):
            raise EvaluationError("candidate artifacts must be a path-to-bytes mapping")
        object.__setattr__(self, "artifact_files", MappingProxyType(files))


@dataclass(frozen=True, slots=True)
class CandidateNomination:
    nomination_id: str
    candidate_ref: Mapping[str, Any]
    dataset_ref: Mapping[str, Any]
    split_ref: Mapping[str, Any]
    nominated_at: str
    nominated_by: str
    policy_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_ref", freeze_json(self.candidate_ref))
        object.__setattr__(self, "dataset_ref", freeze_json(self.dataset_ref))
        object.__setattr__(self, "split_ref", freeze_json(self.split_ref))


@dataclass(frozen=True, slots=True)
class InformationReleaseEvent:
    sequence: int
    event_type: str
    recorded_at: str
    payload_json: str
    prior_event_hash: str | None
    event_hash: str


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    nomination: CandidateNomination
    holdout_receipt: Mapping[str, Any]
    candidate_evaluation: Mapping[str, Any]
    report: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "holdout_receipt", freeze_json(self.holdout_receipt))
        object.__setattr__(
            self, "candidate_evaluation", freeze_json(self.candidate_evaluation)
        )
        object.__setattr__(self, "report", freeze_json(self.report))
