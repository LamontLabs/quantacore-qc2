from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

from qc2_contracts.runtime import (
    canonical_content_hash,
    canonical_json_bytes,
    validate_contract,
    verify_content_hash,
)
from qc2_temporal_firewall.authority import TemporalFirewall
from qc2_temporal_firewall.models import (
    TemporalArtifact,
    TemporalMode,
    TemporalOperation,
    TemporalPermission,
    TemporalQuery,
    TemporalViolation,
)

from .dataset_models import (
    DatasetBuildPlan,
    DatasetBuildResult,
    DatasetSourceRow,
    FoldFeatureTransform,
    FoldPreparedData,
    FoldTrainingIndex,
    PreparedDatasetRow,
    QualificationFeatureRow,
)

_MANIFEST_SCHEMA = "qc2.outcomes_research.DatasetManifest.v1"
_LINEAGE_SCHEMA = "qc2.outcomes_research.DatasetRowLineage.v1"
_SPLIT_SCHEMA = "qc2.outcomes_research.SplitManifest.v1"
_FEATURE_SNAPSHOT_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
_OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
_RUNNER_EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"
_INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
_LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
_ADJUSTMENT_SCHEMA = "qc2.identity_market.AdjustmentManifest.v1"
_FIDELITIES = ("PIT_VERIFIED", "SURVIVORSHIP_LIMITED", "UNKNOWN")
_UNAVAILABLE_REASONS = {
    "artifact_unavailable_at_cutoff",
    "dependency_unavailable_at_cutoff",
    "learning_artifact_unavailable_at_cutoff",
}


class DatasetBuilderError(ValueError):
    """Fail-closed dataset assembly, provenance, or fold-policy error."""


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


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(_plain(value))).hexdigest()


def _ref_id(ref: Mapping[str, Any]) -> str:
    target = ref.get("target_id", ref.get("artifact_id", ref.get("id")))
    if not isinstance(target, str) or not target:
        raise DatasetBuilderError("reference is missing a target ID")
    return target


def _ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(ref.get("target_schema_name", "")),
        _ref_id(ref),
        str(ref.get("content_hash", "")),
    )


def _require_ref(ref: Mapping[str, Any], schema_name: str, label: str) -> None:
    if ref.get("target_schema_name") != schema_name:
        raise DatasetBuilderError(f"{label} must reference {schema_name}")
    _ref_id(ref)
    content_hash = ref.get("content_hash")
    if content_hash is not None and (
        not isinstance(content_hash, str)
        or len(content_hash) != 64
        or any(character not in "0123456789abcdef" for character in content_hash)
    ):
        raise DatasetBuilderError(f"{label} has an invalid content hash")


def _parse_instant(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise DatasetBuilderError(f"{field} must be an ISO-8601 UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatasetBuilderError(f"{field} must be an ISO-8601 UTC instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise DatasetBuilderError(f"{field} must include a UTC timezone")
    return parsed.astimezone(timezone.utc)


def _parse_session(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise DatasetBuilderError(f"{field} must be an ISO session date")
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise DatasetBuilderError(f"{field} must be an ISO session date") from exc


def _uuid7(created_at: str, seed: str) -> str:
    stamp = int(_parse_instant(created_at, "created_at").timestamp() * 1000)
    timestamp = stamp & ((1 << 48) - 1)
    entropy = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:10], "big")
    rand_a = (entropy >> 62) & 0x0FFF
    rand_b = entropy & ((1 << 62) - 1)
    value = (
        (timestamp << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return str(UUID(int=value))


def _seal_contract(contract_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = _plain(payload)
    result["content_hash"] = "0" * 64
    result["content_hash"] = canonical_content_hash(contract_name, result)
    validate_contract(contract_name, result)
    verify_content_hash(contract_name, result)
    return result


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise DatasetBuilderError(f"{field} must be a finite numeric value")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DatasetBuilderError(f"{field} must be a finite numeric value") from exc
    if not result.is_finite():
        raise DatasetBuilderError(f"{field} must be a finite numeric value")
    return result


def _validate_payload(
    artifact: TemporalArtifact,
    ref: Mapping[str, Any],
    schema_name: str,
) -> dict[str, Any]:
    payload = _plain(artifact.payload)
    if not isinstance(payload, dict):
        raise DatasetBuilderError(f"artifact {artifact.artifact_id} has no contract payload")
    if (
        payload.get("schema_name") != schema_name
        or payload.get("id") != _ref_id(ref)
        or payload.get("content_hash") != ref.get("content_hash")
        or artifact.artifact_id != _ref_id(ref)
    ):
        raise DatasetBuilderError(
            f"artifact {artifact.artifact_id} does not match its declared source reference"
        )
    contract_name = schema_name.split(".")[-2]
    validate_contract(contract_name, payload)
    verify_content_hash(contract_name, payload)
    return payload


def _validate_typed_payload(
    artifact: TemporalArtifact, ref: Mapping[str, Any]
) -> dict[str, Any]:
    payload = _plain(artifact.payload)
    schema_name = ref.get("target_schema_name")
    if (
        not isinstance(payload, dict)
        or payload.get("schema_name") != schema_name
        or payload.get("id") != _ref_id(ref)
        or artifact.artifact_id != _ref_id(ref)
        or artifact.content_hash != hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    ):
        raise DatasetBuilderError(
            f"artifact {artifact.artifact_id} does not match its declared source reference"
        )
    contract_name = str(schema_name).split(".")[-2]
    validate_contract(contract_name, payload)
    if "content_hash" in payload:
        verify_content_hash(contract_name, payload)
    reference_hash = ref.get("content_hash")
    if reference_hash is not None and payload.get("content_hash") != reference_hash:
        raise DatasetBuilderError(
            f"artifact {artifact.artifact_id} content hash does not match its source reference"
        )
    return payload


def _ref_list_key(refs: Iterable[Mapping[str, Any]]) -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted({_ref_key(ref) for ref in refs}))


def _source_signature(row: DatasetSourceRow) -> str:
    return _hash(
        {
            "instrument_ref": row.instrument_ref,
            "feature_snapshot_ref": row.feature_snapshot_ref,
            "outcome_ref": row.outcome_ref,
            "target_ref": row.target_ref,
            "session_id": row.session_id,
            "horizon_sessions": row.horizon_sessions,
            "dependency_start": row.label_dependency_start_session,
            "dependency_end": row.label_dependency_end_session,
            "universe_fidelity": row.universe_fidelity,
            "sample_weight": row.sample_weight,
            "sample_weight_source_ref": row.sample_weight_source_ref,
        }
    )


def _row_key(row: DatasetSourceRow, registry_refs: Sequence[Mapping[str, Any]]) -> str:
    identity = {
        "instrument": _ref_key(row.instrument_ref),
        "session_id": row.session_id,
        "horizon_sessions": row.horizon_sessions,
        "target": _ref_key(row.target_ref),
        "registry_versions": _ref_list_key(registry_refs),
    }
    return f"dsrow-v1-{_hash(identity)}"


def _feature_values(
    payload: Mapping[str, Any], feature_ids: tuple[str, ...]
) -> tuple[Decimal | None, ...]:
    raw_values = payload.get("feature_values")
    if not isinstance(raw_values, list):
        raise DatasetBuilderError("FeatureSnapshot.feature_values must be an array")
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in raw_values:
        if not isinstance(item, Mapping):
            raise DatasetBuilderError("FeatureSnapshot has a malformed feature value")
        feature_id = item.get("feature_id")
        if not isinstance(feature_id, str) or not feature_id:
            raise DatasetBuilderError("FeatureSnapshot has a feature value without an ID")
        if feature_id in by_id:
            raise DatasetBuilderError(f"FeatureSnapshot repeats feature {feature_id}")
        by_id[feature_id] = item

    values: list[Decimal | None] = []
    for feature_id in feature_ids:
        item = by_id.get(feature_id)
        if item is None:
            values.append(None)
            continue
        raw_value = item.get("value")
        if raw_value is None or item.get("missing_reason") is not None:
            values.append(None)
        else:
            values.append(_decimal(raw_value, f"feature {feature_id}"))
    return tuple(values)


def _target_value(payload: Mapping[str, Any], target_field: str) -> Decimal:
    value = payload.get(target_field)
    validity = payload.get("field_validity", ())
    status = next(
        (
            item.get("status")
            for item in validity
            if isinstance(item, Mapping) and item.get("field_name") == target_field
        ),
        None,
    )
    if status != "VALID" or value is None:
        raise DatasetBuilderError(f"Outcome field {target_field} is not valid and resolved")
    return _decimal(value, f"Outcome.{target_field}")


def _refs_for_export(
    row: DatasetSourceRow,
    plan: DatasetBuildPlan,
    *,
    include_outcome: bool,
    include_weight_source: bool,
) -> tuple[str, ...]:
    refs: list[Mapping[str, Any]] = [
        row.instrument_ref,
        row.feature_snapshot_ref,
        row.target_ref,
        *plan.source_refs,
        *plan.snapshot_refs,
        *plan.raw_receipt_refs,
        *plan.action_refs,
        *plan.registry_refs,
        *plan.revision_refs,
        plan.normalization_ref,
    ]
    if include_weight_source and row.sample_weight_source_ref is not None:
        refs.append(row.sample_weight_source_ref)
    if include_outcome:
        refs.append(row.outcome_ref)
    return tuple(dict.fromkeys(_ref_id(ref) for ref in refs))


def _export_row(
    *,
    row: DatasetSourceRow,
    plan: DatasetBuildPlan,
    firewall: TemporalFirewall,
    permission: TemporalPermission,
    cutoff_at: str,
    include_outcome: bool,
    include_weight_source: bool,
) -> tuple[dict[str, TemporalArtifact] | None, str | None, str | None]:
    try:
        mode = TemporalMode(plan.temporal_mode)
        query = TemporalQuery(
            cutoff=cutoff_at,
            training_cutoff=cutoff_at,
            mode=mode,
            operation=TemporalOperation.EXPORT,
            artifact_ids=_refs_for_export(
                row,
                plan,
                include_outcome=include_outcome,
                include_weight_source=include_weight_source,
            ),
        )
        exported = firewall.export(query, permission)
    except TemporalViolation as exc:
        if exc.reason_code in _UNAVAILABLE_REASONS:
            return None, exc.reason_code, None
        raise DatasetBuilderError(f"cutoff export failed: {exc.reason_code}: {exc}") from exc

    by_id = {artifact.artifact_id: artifact for artifact in exported.view.artifacts}
    required_refs = [row.instrument_ref, row.feature_snapshot_ref, row.target_ref]
    if include_outcome:
        required_refs.append(row.outcome_ref)
    if include_weight_source and row.sample_weight_source_ref is not None:
        required_refs.append(row.sample_weight_source_ref)
    missing = [_ref_id(ref) for ref in required_refs if _ref_id(ref) not in by_id]
    if missing:
        raise DatasetBuilderError(
            f"cutoff export omitted required dependency artifacts: {', '.join(missing)}"
        )
    return by_id, None, exported.view.catalog_revision


def _validate_plan(plan: DatasetBuildPlan, rows: Sequence[DatasetSourceRow]) -> dict[str, int]:
    if not plan.folds:
        raise DatasetBuilderError("at least one walk-forward fold is required")
    if not plan.session_order or len(plan.session_order) != len(set(plan.session_order)):
        raise DatasetBuilderError("session_order must be nonempty and contain unique sessions")
    for session in plan.session_order:
        _parse_session(session, "session_order")
    session_indexes = {session: index for index, session in enumerate(plan.session_order)}
    if tuple(sorted(plan.session_order)) != plan.session_order:
        raise DatasetBuilderError("session_order must be chronological")
    for field_name, instant in (
        ("created_at", plan.created_at),
        ("qualification_cutoff_at", plan.qualification_cutoff_at),
        ("memory_cutoff", plan.memory_cutoff),
    ):
        _parse_instant(instant, field_name)
    if plan.temporal_mode not in {item.value for item in TemporalMode}:
        raise DatasetBuilderError("temporal_mode must be FORWARD or HISTORICAL_RECONSTRUCTED")
    if not plan.target_field or not plan.feature_ids:
        raise DatasetBuilderError("target_field and feature_ids are required")
    if len(plan.feature_ids) != len(set(plan.feature_ids)):
        raise DatasetBuilderError("feature_ids must be unique")
    for field_name in (
        "evidence_class",
        "environment_namespace",
        "sampling_policy",
        "sample_weight_policy",
        "purge_policy",
        "embargo_policy",
    ):
        if not getattr(plan, field_name).strip():
            raise DatasetBuilderError(f"{field_name} must not be empty")
    if plan.universe_fidelity not in _FIDELITIES:
        raise DatasetBuilderError("universe_fidelity is not a DatasetManifest fidelity")
    if plan.sample_weight_policy not in {"EQUAL", "EXPLICIT_SOURCE"}:
        raise DatasetBuilderError("sample_weight_policy must be EQUAL or EXPLICIT_SOURCE")
    if plan.sample_weight_policy == "EQUAL" and any(
        row.sample_weight != Decimal("1") for row in rows
    ):
        raise DatasetBuilderError("EQUAL sample-weight policy requires every weight to be 1")
    if plan.sample_weight_policy == "EXPLICIT_SOURCE" and any(
        row.sample_weight_source_ref is None for row in rows
    ):
        raise DatasetBuilderError("EXPLICIT_SOURCE weights require a source reference per row")
    if not plan.registry_refs:
        raise DatasetBuilderError("registry_refs must identify the versions used by this dataset")
    registry_schema_names = {
        str(ref.get("target_schema_name")) for ref in plan.registry_refs
    }
    required_registry_schema_names = {
        "qc2.scientific_definitions.FeatureRegistry.v1",
        "qc2.scientific_definitions.LabelRegistry.v1",
        "qc2.scientific_definitions.RunnerProtocolRegistry.v1",
    }
    if not required_registry_schema_names.issubset(registry_schema_names):
        raise DatasetBuilderError(
            "registry_refs must bind feature, label, and runner-protocol registries"
        )
    _require_ref(plan.normalization_ref, _ADJUSTMENT_SCHEMA, "normalization_ref")

    for refs, label in (
        (plan.source_refs, "source_refs"),
        (plan.snapshot_refs, "snapshot_refs"),
        (plan.raw_receipt_refs, "raw_receipt_refs"),
        (plan.action_refs, "action_refs"),
        (plan.registry_refs, "registry_refs"),
        (plan.revision_refs, "revision_refs"),
    ):
        if len({_ref_key(ref) for ref in refs}) != len(refs):
            raise DatasetBuilderError(f"{label} contains duplicate references")

    qualification = tuple(plan.qualification_sessions)
    if not qualification or len(qualification) != len(set(qualification)):
        raise DatasetBuilderError("qualification_sessions must be nonempty and unique")
    if any(session not in session_indexes for session in qualification):
        raise DatasetBuilderError("qualification_sessions contain a session outside session_order")
    qualification_indexes = [session_indexes[session] for session in qualification]
    if qualification_indexes != sorted(qualification_indexes):
        raise DatasetBuilderError("qualification_sessions must be chronological")

    if len({fold.fold_id for fold in plan.folds}) != len(plan.folds):
        raise DatasetBuilderError("fold IDs must be unique")
    previous_validation: set[str] = set()
    previous_training: set[str] = set()
    previous_last_validation = -1
    for fold in plan.folds:
        if not fold.fold_id.strip():
            raise DatasetBuilderError("fold_id must not be empty")
        train = set(fold.training_sessions)
        validation = set(fold.validation_sessions)
        purge = set(fold.purge_sessions)
        embargo = set(fold.embargo_sessions)
        if not train or not validation:
            raise DatasetBuilderError(f"{fold.fold_id} needs training and validation sessions")
        if len(train) != len(fold.training_sessions) or len(validation) != len(
            fold.validation_sessions
        ):
            raise DatasetBuilderError(f"{fold.fold_id} has duplicate assigned sessions")
        if train & validation or train & set(qualification) or validation & set(qualification):
            raise DatasetBuilderError(f"{fold.fold_id} splits or reuses a session across stages")
        if (train | validation | purge | embargo) - set(session_indexes):
            raise DatasetBuilderError(f"{fold.fold_id} references an unknown session")
        if (purge | embargo) & (train | validation | set(qualification)):
            raise DatasetBuilderError(f"{fold.fold_id} purge/embargo sessions have another role")
        train_indexes = [session_indexes[item] for item in fold.training_sessions]
        validation_indexes = [session_indexes[item] for item in fold.validation_sessions]
        if train_indexes != sorted(train_indexes) or validation_indexes != sorted(validation_indexes):
            raise DatasetBuilderError(f"{fold.fold_id} sessions must be chronological")
        if max(train_indexes) >= min(validation_indexes):
            raise DatasetBuilderError(f"{fold.fold_id} training must precede validation")
        if min(validation_indexes) <= previous_last_validation:
            raise DatasetBuilderError("walk-forward validation windows must move forward")
        if not purge and not embargo:
            raise DatasetBuilderError(f"{fold.fold_id} must declare purge or embargo sessions")
        for gap_session in purge | embargo:
            gap_index = session_indexes[gap_session]
            if gap_index <= max(train_indexes) or gap_index >= min(validation_indexes):
                raise DatasetBuilderError(
                    f"{fold.fold_id} purge/embargo sessions must form a gap before validation"
                )
        if previous_validation and not previous_training.issubset(train):
            raise DatasetBuilderError("walk-forward training sets must expand monotonically")
        if previous_validation and not previous_validation.issubset(train):
            raise DatasetBuilderError(
                "later training folds may use prior validation sessions only after their cutoff"
            )
        training_cutoff = _parse_instant(fold.training_cutoff_at, "training_cutoff_at")
        validation_cutoff = _parse_instant(fold.validation_cutoff_at, "validation_cutoff_at")
        if training_cutoff >= validation_cutoff:
            raise DatasetBuilderError(f"{fold.fold_id} training cutoff must precede validation cutoff")
        if validation_cutoff >= _parse_instant(
            plan.qualification_cutoff_at, "qualification_cutoff_at"
        ):
            raise DatasetBuilderError("qualification cutoff must follow every validation cutoff")
        if max(validation_indexes) >= min(qualification_indexes):
            raise DatasetBuilderError("qualification must follow every development interval")
        previous_training = train
        previous_validation = validation
        previous_last_validation = max(validation_indexes)

    _parse_instant(plan.memory_cutoff, "memory_cutoff")
    return session_indexes


def _fit_transform(
    fold_id: str,
    cutoff_at: str,
    feature_ids: tuple[str, ...],
    training_values: Sequence[tuple[str, tuple[Decimal | None, ...]]],
) -> FoldFeatureTransform:
    if not training_values:
        raise DatasetBuilderError(f"{fold_id} has no mature, non-purged training rows")
    means: list[Decimal] = []
    scales: list[Decimal] = []
    with localcontext() as context:
        context.prec = 34
        for column, feature_id in enumerate(feature_ids):
            observed = [
                values[column]
                for _, values in training_values
                if values[column] is not None
            ]
            if not observed:
                raise DatasetBuilderError(
                    f"{fold_id} cannot fit feature {feature_id}: all training values are missing"
                )
            mean = sum(observed, Decimal("0")) / Decimal(len(observed))
            variance = sum(((value - mean) ** 2 for value in observed), Decimal("0")) / Decimal(
                len(observed)
            )
            scale = variance.sqrt()
            means.append(mean)
            scales.append(Decimal("1") if scale == 0 else scale)
    fit_keys = tuple(sorted(row_key for row_key, _ in training_values))
    transform_hash = _hash(
        {
            "fold_id": fold_id,
            "cutoff_at": cutoff_at,
            "feature_ids": feature_ids,
            "means": means,
            "scales": scales,
            "fit_row_keys": fit_keys,
        }
    )
    return FoldFeatureTransform(
        fold_id=fold_id,
        cutoff_at=cutoff_at,
        feature_ids=feature_ids,
        means=tuple(means),
        scales=tuple(scales),
        fit_row_keys=fit_keys,
        transform_hash=transform_hash,
    )


def build_dataset(
    source_rows: Sequence[DatasetSourceRow],
    *,
    plan: DatasetBuildPlan,
    firewall: TemporalFirewall,
    permission: TemporalPermission,
) -> DatasetBuildResult:
    """Build an immutable, cutoff-exported dataset with fold-local fit boundaries.

    Feature and label contracts are re-read only through TemporalFirewall.export.
    Qualification exports request features without requesting Outcome artifacts.
    """

    if not isinstance(permission, TemporalPermission):
        raise DatasetBuilderError("an explicit TemporalPermission is required")
    if TemporalOperation.EXPORT not in permission.operations:
        raise DatasetBuilderError("permission must explicitly allow EXPORT")
    session_indexes = _validate_plan(plan, source_rows)
    if not source_rows:
        raise DatasetBuilderError("at least one source row is required")

    rows_by_key: dict[str, DatasetSourceRow] = {}
    signatures: dict[str, str] = {}
    deduplicated: list[str] = []
    for row in source_rows:
        _require_ref(row.instrument_ref, _INSTRUMENT_SCHEMA, "instrument_ref")
        _require_ref(row.feature_snapshot_ref, _FEATURE_SNAPSHOT_SCHEMA, "feature_snapshot_ref")
        _require_ref(row.outcome_ref, _OUTCOME_SCHEMA, "outcome_ref")
        _require_ref(row.target_ref, _LABEL_SCHEMA, "target_ref")
        for source_ref in (
            row.feature_snapshot_ref,
            row.outcome_ref,
            row.target_ref,
        ):
            if not source_ref.get("content_hash"):
                raise DatasetBuilderError(
                    "FeatureSnapshot, Outcome, and LabelDefinition references must be content-addressed"
                )
        if row.session_id not in session_indexes:
            raise DatasetBuilderError(f"source row session {row.session_id} is not in session_order")
        if (
            row.label_dependency_start_session not in session_indexes
            or row.label_dependency_end_session not in session_indexes
        ):
            raise DatasetBuilderError("label dependency interval is outside session_order")
        _parse_session(row.label_dependency_start_session, "label_dependency_start_session")
        _parse_session(row.label_dependency_end_session, "label_dependency_end_session")
        if row.horizon_sessions < 1:
            raise DatasetBuilderError("horizon_sessions must be positive")
        if row.universe_fidelity not in _FIDELITIES:
            raise DatasetBuilderError("source row has an invalid universe fidelity")
        if (
            session_indexes[row.label_dependency_start_session] > session_indexes[row.session_id]
            or session_indexes[row.label_dependency_end_session]
            < session_indexes[row.label_dependency_start_session]
        ):
            raise DatasetBuilderError("label dependency interval is not chronological")
        weight = _decimal(row.sample_weight, "sample_weight")
        if weight <= 0:
            raise DatasetBuilderError("sample_weight must be greater than zero")
        if row.sample_weight_source_ref is not None:
            sample_source_schema = row.sample_weight_source_ref.get("target_schema_name")
            if sample_source_schema not in {_INSTRUMENT_SCHEMA, _RUNNER_EVENT_SCHEMA}:
                raise DatasetBuilderError(
                    "sample_weight_source_ref must identify the weighted Instrument or RunnerEvent"
                )
            _require_ref(
                row.sample_weight_source_ref,
                str(sample_source_schema),
                "sample_weight_source_ref",
            )
        if row.universe_fidelity != plan.universe_fidelity and (
            _FIDELITIES.index(row.universe_fidelity) > _FIDELITIES.index(plan.universe_fidelity)
        ):
            raise DatasetBuilderError(
                "dataset universe_fidelity cannot exceed the fidelity of any source row"
            )
        key = _row_key(row, plan.registry_refs)
        signature = _source_signature(row)
        if key in rows_by_key:
            if signatures[key] != signature:
                raise DatasetBuilderError(
                    f"conflicting duplicate logical row {key}; refusing to select a source"
                )
            deduplicated.append(key)
            continue
        rows_by_key[key] = row
        signatures[key] = signature

    effective_fidelity = plan.universe_fidelity

    rows_in_order = sorted(
        rows_by_key.items(),
        key=lambda item: (
            session_indexes[item[1].session_id],
            _ref_id(item[1].instrument_ref),
            item[0],
        ),
    )
    max_horizon = max(row.horizon_sessions for _, row in rows_in_order)
    for fold in plan.folds:
        if len(fold.embargo_sessions) < max_horizon:
            raise DatasetBuilderError(
                f"{fold.fold_id} embargo is shorter than the largest declared label horizon"
            )

    assignment_records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    materialized_features: dict[str, tuple[Decimal | None, ...]] = {}
    lineaged_rows: set[str] = set()
    prepared_folds: list[FoldPreparedData] = []
    qualification_rows_all: list[QualificationFeatureRow] = []
    catalog_revision: str | None = None

    def add_exclusion(row_key: str, fold_id: str, stage: str, reason: str) -> None:
        item = {
            "row_key": row_key,
            "fold_id": fold_id,
            "stage": stage,
            "session_id": rows_by_key[row_key].session_id,
            "reason": reason,
        }
        exclusions.append(item)
        assignment_records.append(
            {
                **item,
                "status": "EXCLUDED",
            }
        )

    def load_row(
        row_key: str,
        row: DatasetSourceRow,
        *,
        cutoff_at: str,
        include_outcome: bool,
        include_weight_source: bool,
        fold_id: str,
        stage: str,
    ) -> tuple[tuple[Decimal | None, ...], Decimal | None, str | None]:
        nonlocal catalog_revision
        exported, reason, export_revision = _export_row(
            row=row,
            plan=plan,
            firewall=firewall,
            permission=permission,
            cutoff_at=cutoff_at,
            include_outcome=include_outcome,
            include_weight_source=False,
        )
        if exported is None:
            return (), None, reason or "UNAVAILABLE_AT_CUTOFF"
        if catalog_revision is not None and catalog_revision != export_revision:
            raise DatasetBuilderError("TemporalFirewall catalog revision changed during assembly")
        catalog_revision = export_revision
        for ref in (
            *plan.source_refs,
            *plan.snapshot_refs,
            *plan.raw_receipt_refs,
            *plan.action_refs,
            *plan.registry_refs,
            *plan.revision_refs,
            plan.normalization_ref,
        ):
            _validate_typed_payload(exported[_ref_id(ref)], ref)
        instrument_payload = _validate_typed_payload(
            exported[_ref_id(row.instrument_ref)], row.instrument_ref
        )
        label_payload = _validate_typed_payload(
            exported[_ref_id(row.target_ref)], row.target_ref
        )
        registry_payloads = {
            _ref_id(ref): _validate_typed_payload(exported[_ref_id(ref)], ref)
            for ref in plan.registry_refs
        }
        if label_payload.get("horizon_sessions") != row.horizon_sessions:
            raise DatasetBuilderError("LabelDefinition horizon does not match the dataset row")
        feature_artifact = exported[_ref_id(row.feature_snapshot_ref)]
        feature_payload = _validate_payload(
            feature_artifact, row.feature_snapshot_ref, _FEATURE_SNAPSHOT_SCHEMA
        )
        if feature_payload.get("session_id") != row.session_id:
            raise DatasetBuilderError("FeatureSnapshot session_id does not match its dataset row")
        if _ref_key(feature_payload.get("instrument_ref", {}))[:2] != _ref_key(
            row.instrument_ref
        )[:2]:
            raise DatasetBuilderError("FeatureSnapshot instrument_ref does not match its row")
        registry_ref = feature_payload.get("registry_ref", {})
        if not any(_ref_key(registry_ref) == _ref_key(ref) for ref in plan.registry_refs):
            raise DatasetBuilderError("FeatureSnapshot registry_ref is not in the build plan")
        feature_registry = registry_payloads.get(_ref_id(registry_ref))
        if feature_registry is None or not set(plan.feature_ids).issubset(
            set(feature_registry.get("ordered_feature_ids", ()))
        ):
            raise DatasetBuilderError(
                "feature_ids are not all declared by the selected FeatureRegistry"
            )
        label_registries = [
            registry_payloads[_ref_id(ref)]
            for ref in plan.registry_refs
            if ref.get("target_schema_name")
            == "qc2.scientific_definitions.LabelRegistry.v1"
        ]
        label_ref_key = _ref_key(row.target_ref)
        if not any(
            _ref_key(payload.get("primary_label_ref", {})) == label_ref_key
            or any(
                _ref_key(item) == label_ref_key
                for item in payload.get("definition_refs", ())
            )
            for payload in label_registries
        ):
            raise DatasetBuilderError("target_ref is not registered by the selected LabelRegistry")
        if feature_artifact.evidence_class != plan.evidence_class:
            raise DatasetBuilderError("FeatureSnapshot evidence_class does not match the build plan")
        del instrument_payload
        values = _feature_values(feature_payload, plan.feature_ids)

        target: Decimal | None = None
        if include_outcome:
            outcome_artifact = exported[_ref_id(row.outcome_ref)]
            outcome_payload = _validate_payload(
                outcome_artifact, row.outcome_ref, _OUTCOME_SCHEMA
            )
            if (
                outcome_payload.get("session_id") != row.session_id
                or outcome_payload.get("horizon_sessions") != row.horizon_sessions
                or _ref_key(outcome_payload.get("instrument_ref", {}))[:2]
                != _ref_key(row.instrument_ref)[:2]
                or _ref_key(outcome_payload.get("label_ref", {})) != _ref_key(row.target_ref)
            ):
                raise DatasetBuilderError("Outcome identity does not match its dataset row")
            if outcome_artifact.evidence_class != plan.evidence_class:
                raise DatasetBuilderError("Outcome evidence_class does not match the build plan")
            if (
                outcome_payload.get("available_for_learning_at")
                != outcome_artifact.available_for_learning_at
            ):
                raise DatasetBuilderError(
                    "Outcome payload and temporal availability metadata disagree"
                )
            available_at = outcome_artifact.available_for_learning_at
            if available_at is None or _parse_instant(
                available_at, "Outcome.available_for_learning_at"
            ) >= _parse_instant(cutoff_at, "learning_cutoff"):
                return (), None, "LABEL_NOT_MATURE_BEFORE_CUTOFF"
            try:
                target = _target_value(outcome_payload, plan.target_field)
            except DatasetBuilderError:
                return (), None, "TARGET_FIELD_UNRESOLVED"
        if include_weight_source:
            if row.sample_weight_source_ref is None:
                raise DatasetBuilderError("training weight source is missing")
            weighted_export, weight_reason, weight_revision = _export_row(
                row=row,
                plan=plan,
                firewall=firewall,
                permission=permission,
                cutoff_at=cutoff_at,
                include_outcome=include_outcome,
                include_weight_source=True,
            )
            if weighted_export is None:
                return (), None, weight_reason or "WEIGHT_SOURCE_UNAVAILABLE_AT_CUTOFF"
            if weight_revision != export_revision:
                raise DatasetBuilderError(
                    "TemporalFirewall catalog revision changed between row and weight exports"
                )
            weight_artifact = weighted_export[_ref_id(row.sample_weight_source_ref)]
            weight_payload = _validate_typed_payload(
                weight_artifact, row.sample_weight_source_ref
            )
            if row.sample_weight_source_ref["target_schema_name"] == _INSTRUMENT_SCHEMA:
                if _ref_key(row.sample_weight_source_ref)[:2] != _ref_key(row.instrument_ref)[:2]:
                    raise DatasetBuilderError("instrument weight source does not match its dataset row")
            elif (
                _ref_key(weight_payload.get("instrument_ref", {}))[:2]
                != _ref_key(row.instrument_ref)[:2]
                or _ref_key(weight_payload.get("outcome_ref", {})) != _ref_key(row.outcome_ref)
            ):
                raise DatasetBuilderError(
                    "RunnerEvent weight source does not match its dataset row"
                )
        previous = materialized_features.get(row_key)
        if previous is not None and previous != values:
            raise DatasetBuilderError("one row resolved to different feature values across folds")
        materialized_features[row_key] = values
        lineaged_rows.add(row_key)
        assignment_records.append(
            {
                "row_key": row_key,
                "fold_id": fold_id,
                "stage": stage,
                "session_id": row.session_id,
                "status": "RELEASED",
                "target_released": include_outcome,
                "sample_weight_applied": stage == "TRAINING",
                "sample_weight": row.sample_weight if stage == "TRAINING" else None,
                "sample_weight_source_ref": (
                    row.sample_weight_source_ref
                    if stage == "TRAINING"
                    and plan.sample_weight_policy == "EXPLICIT_SOURCE"
                    else None
                ),
                "cutoff_at": cutoff_at,
            }
        )
        return values, target, None

    for fold_index, fold in enumerate(plan.folds):
        train_boundary = min(session_indexes[item] for item in fold.validation_sessions)
        next_validation_boundary = (
            min(session_indexes[item] for item in plan.folds[fold_index + 1].validation_sessions)
            if fold_index + 1 < len(plan.folds)
            else min(session_indexes[item] for item in plan.qualification_sessions)
        )
        gap_sessions = set(fold.purge_sessions) | set(fold.embargo_sessions)
        train_candidates: list[tuple[str, DatasetSourceRow, tuple[Decimal | None, ...], Decimal]] = []
        validation_candidates: list[
            tuple[str, DatasetSourceRow, tuple[Decimal | None, ...], Decimal]
        ] = []

        for row_key, row in rows_in_order:
            dependency_start = session_indexes[row.label_dependency_start_session]
            dependency_end = session_indexes[row.label_dependency_end_session]
            stage: str | None = None
            if row.session_id in fold.training_sessions:
                stage = "TRAINING"
                if dependency_end >= train_boundary or any(
                    dependency_start <= session_indexes[gap] <= dependency_end
                    for gap in gap_sessions
                ):
                    add_exclusion(row_key, fold.fold_id, stage, "PURGED_LABEL_DEPENDENCY_OVERLAP")
                    continue
            elif row.session_id in fold.validation_sessions:
                stage = "VALIDATION"
                if dependency_end >= next_validation_boundary:
                    add_exclusion(row_key, fold.fold_id, stage, "PURGED_LABEL_DEPENDENCY_OVERLAP")
                    continue
            if stage is None:
                continue
            values, target, error = load_row(
                row_key,
                row,
                cutoff_at=(
                    fold.training_cutoff_at if stage == "TRAINING" else fold.validation_cutoff_at
                ),
                include_outcome=True,
                include_weight_source=(
                    stage == "TRAINING"
                    and plan.sample_weight_policy == "EXPLICIT_SOURCE"
                ),
                fold_id=fold.fold_id,
                stage=stage,
            )
            if error is not None:
                add_exclusion(row_key, fold.fold_id, stage, error)
                continue
            assert target is not None
            record = (row_key, row, values, target)
            if stage == "TRAINING":
                train_candidates.append(record)
            else:
                validation_candidates.append(record)

        transform = _fit_transform(
            fold.fold_id,
            fold.training_cutoff_at,
            plan.feature_ids,
            [(row_key, values) for row_key, _, values, _ in train_candidates],
        )
        training_prepared = tuple(
            PreparedDatasetRow(
                row_key=row_key,
                session_id=row.session_id,
                instrument_id=_ref_id(row.instrument_ref),
                feature_values=transform.transform(values),
                target_value=target,
                sample_weight=row.sample_weight,
            )
            for row_key, row, values, target in train_candidates
        )
        validation_prepared = tuple(
            PreparedDatasetRow(
                row_key=row_key,
                session_id=row.session_id,
                instrument_id=_ref_id(row.instrument_ref),
                feature_values=transform.transform(values),
                target_value=target,
                sample_weight=None,
            )
            for row_key, row, values, target in validation_candidates
        )
        training_prepared = tuple(sorted(training_prepared, key=lambda item: item.row_key))
        validation_prepared = tuple(sorted(validation_prepared, key=lambda item: item.row_key))
        index_hash = _hash(
            {
                "fold_id": fold.fold_id,
                "cutoff_at": fold.training_cutoff_at,
                "transform_hash": transform.transform_hash,
                "rows": training_prepared,
            }
        )
        training_index = FoldTrainingIndex(
            fold_id=fold.fold_id,
            cutoff_at=fold.training_cutoff_at,
            member_row_keys=tuple(item.row_key for item in training_prepared),
            rows=training_prepared,
            index_hash=index_hash,
        )

        qualification_prepared: list[QualificationFeatureRow] = []
        for row_key, row in rows_in_order:
            if row.session_id not in plan.qualification_sessions:
                continue
            values, _, error = load_row(
                row_key,
                row,
                cutoff_at=plan.qualification_cutoff_at,
                include_outcome=False,
                include_weight_source=False,
                fold_id=fold.fold_id,
                stage="QUALIFICATION_FEATURES",
            )
            if error is not None:
                add_exclusion(
                    row_key, fold.fold_id, "QUALIFICATION_FEATURES", error
                )
                continue
            qualification_prepared.append(
                QualificationFeatureRow(
                    fold_id=fold.fold_id,
                    row_key=row_key,
                    session_id=row.session_id,
                    instrument_id=_ref_id(row.instrument_ref),
                    feature_values=transform.transform(values),
                    source_refs=(row.feature_snapshot_ref,),
                )
            )
        qualification_prepared.sort(key=lambda item: item.row_key)
        prepared_folds.append(
            FoldPreparedData(
                fold_id=fold.fold_id,
                transform=transform,
                training_index=training_index,
                validation_rows=validation_prepared,
                qualification_rows=tuple(qualification_prepared),
            )
        )
        qualification_rows_all.extend(qualification_prepared)

    if not lineaged_rows:
        raise DatasetBuilderError("no source row survived cutoff export and fold assignment")

    released_label_rows = {
        assignment["row_key"]
        for assignment in assignment_records
        if assignment.get("target_released") is True
    }
    lineage_records: list[dict[str, Any]] = []
    lineage_descriptors: list[dict[str, Any]] = []
    for row_key in sorted(lineaged_rows):
        row = rows_by_key[row_key]
        refs = [row.feature_snapshot_ref]
        if row_key in released_label_rows:
            refs.append(row.outcome_ref)
        descriptor = {
            "row_key": row_key,
            "instrument_ref": row.instrument_ref,
            "session_id": row.session_id,
            "horizon_sessions": row.horizon_sessions,
            "target_ref": row.target_ref,
            "source_refs": refs,
            "registry_refs": plan.registry_refs,
            "dependency_start_session": row.label_dependency_start_session,
            "dependency_end_session": row.label_dependency_end_session,
            "training_weight_sources": [
                {
                    "weight": row.sample_weight,
                    "source_ref": row.sample_weight_source_ref,
                }
                for assignment in assignment_records
                if assignment["row_key"] == row_key
                and assignment["stage"] == "TRAINING"
                and assignment["status"] == "RELEASED"
            ],
        }
        lineage_hash = _hash(descriptor)
        lineage_descriptors.append(
            {"row_key": row_key, "lineage_hash": lineage_hash}
        )
        lineage_records.append(
            {
                "schema_name": _LINEAGE_SCHEMA,
                "schema_version": "1.0",
                "id": _uuid7(plan.created_at, f"lineage:{lineage_hash}"),
                "created_at": plan.created_at,
                "owning_authority": "apexlab",
                "evidence_class": plan.evidence_class,
                "environment_namespace": plan.environment_namespace,
                "source_refs": _plain(refs),
                "dataset_ref": {},
                "row_key": row_key,
                "instrument_ref": _plain(row.instrument_ref),
                "session_id": row.session_id,
                "horizon_sessions": row.horizon_sessions,
                "target_ref": _plain(row.target_ref),
                "lineage_hash": lineage_hash,
            }
        )

    assignment_records.sort(
        key=lambda item: (
            item.get("fold_id", ""),
            item.get("stage", ""),
            item.get("row_key", ""),
        )
    )
    exclusions.sort(
        key=lambda item: (
            item.get("fold_id", ""),
            item.get("stage", ""),
            item.get("row_key", ""),
            item.get("reason", ""),
        )
    )
    fold_assignments = []
    for fold in plan.folds:
        fold_assignments.append(
            {
                "fold_id": fold.fold_id,
                "training_sessions": list(fold.training_sessions),
                "validation_sessions": list(fold.validation_sessions),
                "purge_sessions": list(fold.purge_sessions),
                "embargo_sessions": list(fold.embargo_sessions),
                "training_cutoff_at": fold.training_cutoff_at,
                "validation_cutoff_at": fold.validation_cutoff_at,
            }
        )
    qualification_assignment = {
        "sessions": list(plan.qualification_sessions),
        "cutoff_at": plan.qualification_cutoff_at,
        "row_keys": sorted(
            row_key
            for row_key in lineaged_rows
            if rows_by_key[row_key].session_id in plan.qualification_sessions
        ),
        "labels_released": False,
    }
    split_assignment_hash = _hash(
        {
            "session_order": plan.session_order,
            "folds": fold_assignments,
            "qualification": qualification_assignment,
            "row_assignments": assignment_records,
            "exclusions": exclusions,
            "purge_policy": plan.purge_policy,
            "embargo_policy": plan.embargo_policy,
        }
    )
    row_lineage_hash = _hash(lineage_descriptors)
    membership_hash = _hash(sorted(lineaged_rows))
    missingness = Counter()
    for row_key in lineaged_rows:
        for feature_id, value in zip(plan.feature_ids, materialized_features[row_key]):
            if value is None:
                missingness[feature_id] += 1
    all_sessions = [rows_by_key[row_key].session_id for row_key in lineaged_rows]
    symbol_ids = {_ref_id(rows_by_key[row_key].instrument_ref) for row_key in lineaged_rows}
    all_source_refs: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for ref in (
        *plan.source_refs,
        *plan.snapshot_refs,
        *plan.raw_receipt_refs,
        *plan.action_refs,
        *plan.revision_refs,
    ):
        all_source_refs[_ref_key(ref)] = ref
    for row_key in lineaged_rows:
        row = rows_by_key[row_key]
        for ref in (
            row.instrument_ref,
            row.feature_snapshot_ref,
            row.target_ref,
        ):
            all_source_refs[_ref_key(ref)] = ref
        if row_key in released_label_rows:
            all_source_refs[_ref_key(row.outcome_ref)] = row.outcome_ref
        if row.sample_weight_source_ref is not None and any(
            assignment["row_key"] == row_key
            and assignment["stage"] == "TRAINING"
            and assignment["status"] == "RELEASED"
            for assignment in assignment_records
        ):
            all_source_refs[_ref_key(row.sample_weight_source_ref)] = row.sample_weight_source_ref
    manifest_artifact_hash = _hash(
        {
            "row_lineage_hash": row_lineage_hash,
            "membership_hash": membership_hash,
            "split_assignment_hash": split_assignment_hash,
            "features": {
                row_key: materialized_features[row_key] for row_key in sorted(lineaged_rows)
            },
            "fold_indexes": [
                {
                    "fold_id": fold.fold_id,
                    "index_hash": fold.training_index.index_hash,
                    "transform_hash": fold.transform.transform_hash,
                    "validation_rows": fold.validation_rows,
                }
                for fold in prepared_folds
            ],
            "exclusions": exclusions,
            "deduplicated_row_keys": sorted(set(deduplicated)),
            "catalog_revision": catalog_revision,
            "target_field": plan.target_field,
        }
    )
    sample_weight_entries = [
        {
            "row_key": item["row_key"],
            "fold_id": item["fold_id"],
            "weight": item["sample_weight"],
            "source_ref": item["sample_weight_source_ref"],
        }
        for item in assignment_records
        if item["stage"] == "TRAINING"
        and item["status"] == "RELEASED"
        and item.get("sample_weight_applied", False)
    ]
    manifest_payload = {
        "schema_name": _MANIFEST_SCHEMA,
        "schema_version": "1.0",
        "id": _uuid7(plan.created_at, f"dataset:{manifest_artifact_hash}"),
        "created_at": plan.created_at,
        "owning_authority": "apexlab",
        "evidence_class": plan.evidence_class,
        "environment_namespace": plan.environment_namespace,
        "source_refs": _plain(
            [all_source_refs[key] for key in sorted(all_source_refs)]
        ),
        "universe_fidelity": effective_fidelity,
        "snapshot_refs": _plain(plan.snapshot_refs),
        "raw_receipt_refs": _plain(plan.raw_receipt_refs),
        "action_refs": _plain(plan.action_refs),
        "registry_refs": _plain(plan.registry_refs),
        "memory_cutoff": plan.memory_cutoff,
        "availability_policy": (
            "FORWARD_OBSERVED"
            if plan.temporal_mode == TemporalMode.FORWARD.value
            else "HISTORICAL_RECONSTRUCTED"
        ),
        "row_lineage_hash": row_lineage_hash,
        "membership_hash": membership_hash,
        "time_start": min(all_sessions),
        "time_end": max(all_sessions),
        "symbol_count": len(symbol_ids),
        "missingness_counts": [
            f"{feature_id}={missingness[feature_id]}" for feature_id in plan.feature_ids
        ],
        "revision_refs": _plain(plan.revision_refs),
        "split_assignment_hash": split_assignment_hash,
        "normalization_ref": _plain(plan.normalization_ref),
        "sampling_policy": json.dumps(
            _plain({
                "sampling_policy": plan.sampling_policy,
                "sample_weight_policy": plan.sample_weight_policy,
                "training_weights": sample_weight_entries,
            }),
            sort_keys=True,
            separators=(",", ":"),
        ),
        "artifact_hash": manifest_artifact_hash,
    }
    dataset_manifest = _seal_contract("DatasetManifest", manifest_payload)
    dataset_ref = {
        "target_schema_name": _MANIFEST_SCHEMA,
        "target_id": dataset_manifest["id"],
        "content_hash": dataset_manifest["content_hash"],
    }

    final_lineages: list[dict[str, Any]] = []
    for record in lineage_records:
        payload = {**record, "dataset_ref": dataset_ref}
        final_lineages.append(_seal_contract("DatasetRowLineage", payload))

    training_intervals = []
    validation_intervals = []
    for fold in plan.folds:
        training_keys = sorted(
            item["row_key"]
            for item in assignment_records
            if item["fold_id"] == fold.fold_id
            and item["stage"] == "TRAINING"
            and item["status"] == "RELEASED"
        )
        validation_keys = sorted(
            item["row_key"]
            for item in assignment_records
            if item["fold_id"] == fold.fold_id
            and item["stage"] == "VALIDATION"
            and item["status"] == "RELEASED"
        )
        training_intervals.append(
            json.dumps(
                {
                    "fold_id": fold.fold_id,
                    "sessions": list(fold.training_sessions),
                    "released_row_keys": training_keys,
                    "cutoff_at": fold.training_cutoff_at,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        validation_intervals.append(
            json.dumps(
                {
                    "fold_id": fold.fold_id,
                    "sessions": list(fold.validation_sessions),
                    "released_row_keys": validation_keys,
                    "cutoff_at": fold.validation_cutoff_at,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    split_cutoff_policy = json.dumps(
        _plain({
            "policy_version": "QC2_SESSION_WALK_FORWARD_V1",
            "session_order": list(plan.session_order),
            "folds": fold_assignments,
            "qualification": qualification_assignment,
            "row_assignments": assignment_records,
            "exclusions": exclusions,
            "purge_policy": plan.purge_policy,
            "embargo_policy": plan.embargo_policy,
        }),
        sort_keys=True,
        separators=(",", ":"),
    )
    split_payload = {
        "schema_name": _SPLIT_SCHEMA,
        "schema_version": "1.0",
        "id": _uuid7(plan.created_at, f"split:{split_assignment_hash}"),
        "created_at": plan.created_at,
        "owning_authority": "apexlab",
        "evidence_class": plan.evidence_class,
        "environment_namespace": plan.environment_namespace,
        "source_refs": _plain(
            list(
                {
                    _ref_key(ref): ref
                    for ref in (*plan.source_refs, *plan.registry_refs)
                }.values()
            )
        ),
        "dataset_ref": dataset_ref,
        "split_unit": "EXCHANGE_SESSION",
        "training_intervals": training_intervals,
        "validation_intervals": validation_intervals,
        "qualification_interval": json.dumps(
            qualification_assignment, sort_keys=True, separators=(",", ":")
        ),
        "purge_sessions": max((len(fold.purge_sessions) for fold in plan.folds), default=0),
        "embargo_sessions": max((len(fold.embargo_sessions) for fold in plan.folds), default=0),
        "cutoff_policy": split_cutoff_policy,
        "split_hash": split_assignment_hash,
    }
    split_manifest = _seal_contract("SplitManifest", split_payload)
    return DatasetBuildResult(
        dataset_manifest=dataset_manifest,
        split_manifest=split_manifest,
        row_lineages=tuple(final_lineages),
        folds=tuple(prepared_folds),
        qualification_rows=tuple(qualification_rows_all),
        row_assignments=tuple(assignment_records),
        excluded_rows=tuple(exclusions),
        deduplicated_row_keys=tuple(sorted(set(deduplicated))),
        catalog_revision=catalog_revision or "UNAVAILABLE",
    )
