from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

from qc2_contracts.runtime import canonical_json_bytes


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def fold_rows_hash(
    fold_id: str,
    cutoff_at: str,
    transform_hash: str,
    rows: tuple["PreparedDatasetRow", ...],
) -> str:
    """Bind released rows, including label maturity instants, to a fold index."""
    payload = {
        "fold_id": fold_id,
        "cutoff_at": cutoff_at,
        "transform_hash": transform_hash,
        "rows": rows,
    }
    return hashlib.sha256(canonical_json_bytes(_plain(payload))).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class DatasetSourceRow:
    """References and fold-independent identity for one candidate dataset row."""

    instrument_ref: Mapping[str, Any]
    feature_snapshot_ref: Mapping[str, Any]
    outcome_ref: Mapping[str, Any]
    target_ref: Mapping[str, Any]
    session_id: str
    horizon_sessions: int
    label_dependency_start_session: str
    label_dependency_end_session: str
    universe_fidelity: str
    sample_weight: Decimal
    sample_weight_source_ref: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in ("instrument_ref", "feature_snapshot_ref", "outcome_ref", "target_ref"):
            object.__setattr__(self, field_name, _freeze(getattr(self, field_name)))
        if self.sample_weight_source_ref is not None:
            object.__setattr__(
                self, "sample_weight_source_ref", _freeze(self.sample_weight_source_ref)
            )


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    """An explicit session-based train/development fold."""

    fold_id: str
    training_sessions: tuple[str, ...]
    validation_sessions: tuple[str, ...]
    purge_sessions: tuple[str, ...]
    embargo_sessions: tuple[str, ...]
    training_cutoff_at: str
    validation_cutoff_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "training_sessions",
            "validation_sessions",
            "purge_sessions",
            "embargo_sessions",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))


@dataclass(frozen=True, slots=True)
class DatasetBuildPlan:
    """All decisions needed to build and seal one chronological dataset."""

    created_at: str
    evidence_class: str
    environment_namespace: str
    temporal_mode: str
    session_order: tuple[str, ...]
    folds: tuple[WalkForwardFold, ...]
    qualification_sessions: tuple[str, ...]
    qualification_cutoff_at: str
    memory_cutoff: str
    target_field: str
    feature_ids: tuple[str, ...]
    universe_fidelity: str
    sampling_policy: str
    sample_weight_policy: str
    purge_policy: str
    embargo_policy: str
    source_refs: tuple[Mapping[str, Any], ...]
    snapshot_refs: tuple[Mapping[str, Any], ...]
    raw_receipt_refs: tuple[Mapping[str, Any], ...]
    action_refs: tuple[Mapping[str, Any], ...]
    registry_refs: tuple[Mapping[str, Any], ...]
    revision_refs: tuple[Mapping[str, Any], ...]
    normalization_ref: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field_name in (
            "session_order",
            "folds",
            "qualification_sessions",
            "feature_ids",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        for field_name in (
            "source_refs",
            "snapshot_refs",
            "raw_receipt_refs",
            "action_refs",
            "registry_refs",
            "revision_refs",
        ):
            object.__setattr__(
                self,
                field_name,
                tuple(_freeze(item) for item in getattr(self, field_name)),
            )
        object.__setattr__(self, "normalization_ref", _freeze(self.normalization_ref))


@dataclass(frozen=True, slots=True)
class PreparedDatasetRow:
    """One released training or development row after its fold-local transform."""

    row_key: str
    session_id: str
    instrument_id: str
    feature_values: tuple[Decimal, ...]
    target_value: Decimal
    sample_weight: Decimal | None
    label_available_at: str | None = None


@dataclass(frozen=True, slots=True)
class QualificationFeatureRow:
    """Qualification features with no label value exposed to the fold pipeline."""

    fold_id: str
    row_key: str
    session_id: str
    instrument_id: str
    feature_values: tuple[Decimal, ...]
    source_refs: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_refs", tuple(_freeze(item) for item in self.source_refs)
        )


@dataclass(frozen=True, slots=True)
class FoldFeatureTransform:
    """Training-only standardization parameters for one fold."""

    fold_id: str
    cutoff_at: str
    feature_ids: tuple[str, ...]
    means: tuple[Decimal, ...]
    scales: tuple[Decimal, ...]
    fit_row_keys: tuple[str, ...]
    transform_hash: str

    def transform(self, values: tuple[Decimal | None, ...]) -> tuple[Decimal, ...]:
        if len(values) != len(self.feature_ids):
            raise ValueError("feature vector width does not match the fitted transform")
        return tuple(
            ((self.means[index] if value is None else value) - self.means[index])
            / self.scales[index]
            for index, value in enumerate(values)
        )


@dataclass(frozen=True, slots=True)
class FoldTrainingIndex:
    """Ephemeral, fold-local row lookup; not a persisted memory/retrieval index."""

    fold_id: str
    cutoff_at: str
    member_row_keys: tuple[str, ...]
    rows: tuple[PreparedDatasetRow, ...]
    index_hash: str


@dataclass(frozen=True, slots=True)
class FoldPreparedData:
    fold_id: str
    transform: FoldFeatureTransform
    training_index: FoldTrainingIndex
    validation_rows: tuple[PreparedDatasetRow, ...]
    qualification_rows: tuple[QualificationFeatureRow, ...]
    validation_index_hash: str


@dataclass(frozen=True, slots=True)
class DatasetBuildResult:
    dataset_manifest: Mapping[str, Any]
    split_manifest: Mapping[str, Any]
    row_lineages: tuple[Mapping[str, Any], ...]
    folds: tuple[FoldPreparedData, ...]
    qualification_rows: tuple[QualificationFeatureRow, ...]
    row_assignments: tuple[Mapping[str, Any], ...]
    excluded_rows: tuple[Mapping[str, Any], ...]
    deduplicated_row_keys: tuple[str, ...]
    catalog_revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_manifest", _freeze(self.dataset_manifest))
        object.__setattr__(self, "split_manifest", _freeze(self.split_manifest))
        object.__setattr__(
            self, "row_lineages", tuple(_freeze(item) for item in self.row_lineages)
        )
        object.__setattr__(
            self, "row_assignments", tuple(_freeze(item) for item in self.row_assignments)
        )
        object.__setattr__(
            self, "excluded_rows", tuple(_freeze(item) for item in self.excluded_rows)
        )
