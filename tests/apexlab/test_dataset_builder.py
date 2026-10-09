from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from qc2_apexlab import contract_artifact
from qc2_apexlab.dataset_builder import DatasetBuilderError, build_dataset
from qc2_apexlab.dataset_models import (
    DatasetBuildPlan,
    DatasetSourceRow,
    WalkForwardFold,
    fold_rows_hash,
)
from qc2_apexlab.models import seal_content_addressed_contract
from qc2_contracts.runtime import validate_contract
from qc2_temporal_firewall import (
    TemporalArtifact,
    TemporalFirewall,
    TemporalOperation,
    TemporalPermission,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = {
    item["contract"]: item["payload"]
    for item in json.loads(
        (ROOT / "packages" / "contracts" / "fixtures" / "v1" / "valid.json").read_text()
    )
}

BASE = "2024-01-01T00:00:00Z"
ENVIRONMENT = "test"
EVIDENCE = "SYNTHETIC_FIXTURE"
FEATURE_REGISTRY_SCHEMA = "qc2.scientific_definitions.FeatureRegistry.v1"
LABEL_REGISTRY_SCHEMA = "qc2.scientific_definitions.LabelRegistry.v1"
PROTOCOL_REGISTRY_SCHEMA = "qc2.scientific_definitions.RunnerProtocolRegistry.v1"
LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
FEATURE_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
RUNNER_EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"
ADJUSTMENT_SCHEMA = "qc2.identity_market.AdjustmentManifest.v1"
TRANSFORM_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"
DAILY_BAR_SCHEMA = "qc2.identity_market.DailyBar.v1"


def _uuid7(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    rand_a = random_bits >> 62
    rand_b = random_bits & ((1 << 62) - 1)
    timestamp_ms = 1_704_067_200_000
    value = (timestamp_ms << 80) | (7 << 76) | (rand_a << 64) | (2 << 62) | rand_b
    return str(UUID(int=value))


def _ref(schema: str, artifact_id: str, content_hash: str | None = None) -> dict[str, str]:
    result = {"target_schema_name": schema, "target_id": artifact_id}
    if content_hash is not None:
        result["content_hash"] = content_hash
    return result


def _artifact_ref(artifact: TemporalArtifact) -> dict[str, str]:
    payload = _plain(artifact.payload)
    result = _ref(str(payload["schema_name"]), str(payload["id"]))
    if isinstance(payload.get("content_hash"), str):
        result["content_hash"] = str(payload["content_hash"])
    return result


def _plain(value):
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _contract(
    name: str,
    key: str,
    updates: dict,
    *,
    known_at: str = BASE,
    content_addressed: bool = False,
) -> TemporalArtifact:
    payload = deepcopy(FIXTURES[name])
    payload.update(updates)
    if content_addressed:
        payload = seal_content_addressed_contract(name, payload)
    return contract_artifact(payload, known_at=known_at)


def _registry_sources():
    feature_definition_ref = _ref(
        "qc2.scientific_definitions.FeatureDefinition.v1",
        _uuid7("dataset-feature-definition"),
        "1" * 64,
    )
    feature_registry = _contract(
        "FeatureRegistry",
        "feature-registry",
        {
            "id": _uuid7("feature-registry"),
            "created_at": BASE,
            "owning_authority": "feature",
            "evidence_class": EVIDENCE,
            "environment_namespace": ENVIRONMENT,
            "source_refs": [],
            "definition_refs": [feature_definition_ref],
            "ordered_feature_ids": ["fixture"],
            "effective_from": "2024-01-01",
        },
        content_addressed=True,
    )
    label = _contract(
        "LabelDefinition",
        "label-definition",
        {
            "id": _uuid7("label-definition"),
            "created_at": BASE,
            "owning_authority": "label",
            "evidence_class": EVIDENCE,
            "environment_namespace": ENVIRONMENT,
            "source_refs": [],
            "stable_key": "dataset-fixture-endpoint",
            "horizon_sessions": 1,
        },
        content_addressed=True,
    )
    label_ref = _artifact_ref(label)
    label_registry = _contract(
        "LabelRegistry",
        "label-registry",
        {
            "id": _uuid7("label-registry"),
            "created_at": BASE,
            "owning_authority": "label",
            "evidence_class": EVIDENCE,
            "environment_namespace": ENVIRONMENT,
            "source_refs": [],
            "definition_refs": [label_ref],
            "primary_label_ref": label_ref,
            "effective_from": "2024-01-01",
        },
        content_addressed=True,
    )
    protocol_definition_ref = _ref(
        "qc2.scientific_definitions.RunnerProtocolDefinition.v1",
        _uuid7("dataset-protocol-definition"),
        "2" * 64,
    )
    protocol_registry = _contract(
        "RunnerProtocolRegistry",
        "protocol-registry",
        {
            "id": _uuid7("protocol-registry"),
            "created_at": BASE,
            "owning_authority": "runner_protocol",
            "evidence_class": EVIDENCE,
            "environment_namespace": ENVIRONMENT,
            "source_refs": [],
            "definition_refs": [protocol_definition_ref],
            "effective_from": "2024-01-01",
        },
        content_addressed=True,
    )
    adjustment = _contract(
        "AdjustmentManifest",
        "adjustment-manifest",
        {
            "id": _uuid7("adjustment-manifest"),
            "created_at": BASE,
            "owning_authority": "market_data",
            "evidence_class": EVIDENCE,
            "environment_namespace": ENVIRONMENT,
            "source_refs": [],
            "basis_session": "2024-01-01",
            "action_refs": [],
            "available_at": BASE,
        },
    )
    return (
        [feature_registry, label_registry, protocol_registry, adjustment, label],
        _artifact_ref(feature_registry),
        _artifact_ref(label_registry),
        _artifact_ref(protocol_registry),
        _artifact_ref(adjustment),
        label_ref,
        "fixture",
    )


def _instrument(key: str) -> TemporalArtifact:
    return _contract(
        "Instrument",
        key,
        {
            "id": _uuid7(f"{key}:instrument"),
            "created_at": BASE,
            "owning_authority": "instrument_universe",
            "evidence_class": EVIDENCE,
            "environment_namespace": ENVIRONMENT,
            "stable_instrument_key": key,
            "first_known_at": BASE,
        },
    )


def _feature_snapshot(
    key: str,
    session: str,
    instrument_ref: dict[str, str],
    registry_ref: dict[str, str],
    value: str,
) -> TemporalArtifact:
    transform_ref = _ref(
        TRANSFORM_SCHEMA,
        _uuid7("feature-transform-reference"),
        "3" * 64,
    )
    created_at = f"{session}T20:00:00Z"
    payload = deepcopy(FIXTURES["FeatureSnapshot"])
    payload.update(
        {
            "id": _uuid7(f"{key}:feature"),
            "created_at": created_at,
            "owning_authority": "feature",
            "evidence_class": EVIDENCE,
            "environment_namespace": ENVIRONMENT,
            "source_refs": [],
            "session_id": session,
            "instrument_ref": instrument_ref,
            "registry_ref": registry_ref,
            "feature_values": [
                {
                    "feature_id": "fixture",
                    "unit": "fraction",
                    "output_dtype": "DECIMAL",
                    "value": value,
                }
            ],
            "input_hashes": ["4" * 64],
            "transform_refs": [transform_ref],
            "decision_cutoff": f"{session}T16:00:00Z",
            "code_hash": "5" * 64,
            "environment_fingerprint": "6" * 64,
        }
    )
    return contract_artifact(
        seal_content_addressed_contract("FeatureSnapshot", payload),
        known_at=created_at,
    )


def _outcome(
    key: str,
    session: str,
    instrument_ref: dict[str, str],
    label_ref: dict[str, str],
    available_at: str,
    target: str,
) -> TemporalArtifact:
    payload = deepcopy(FIXTURES["Outcome"])
    bar_ref = _ref(DAILY_BAR_SCHEMA, _uuid7(f"{key}:reference-bar"))
    next_session = datetime.strptime(session, "%Y-%m-%d").date() + timedelta(days=1)
    while next_session.weekday() >= 5:
        next_session += timedelta(days=1)
    payload.update(
        {
            "id": _uuid7(f"{key}:outcome"),
            "created_at": available_at,
            "owning_authority": "ground_truth",
            "evidence_class": EVIDENCE,
            "environment_namespace": ENVIRONMENT,
            "source_refs": [bar_ref],
            "instrument_ref": instrument_ref,
            "session_id": session,
            "label_ref": label_ref,
            "horizon_sessions": 1,
            "reference_bar_ref": bar_ref,
            "outcome_state": "RESOLVED",
            "endpoint_return": format(Decimal(target), ".12f"),
            "max_high_return": "0.020000000000",
            "min_low_return": "-0.010000000000",
            "mfe": "0.020000000000",
            "mae": "-0.010000000000",
            "max_high_price": "10.20",
            "max_high_session": next_session.isoformat(),
            "max_high_session_offset": 1,
            "min_low_price": "9.90",
            "min_low_session": next_session.isoformat(),
            "min_low_session_offset": 1,
            "available_for_learning_at": available_at,
            "reason_codes": [],
        }
    )
    resolved_fields = {
        "endpoint_return",
        "max_high_return",
        "min_low_return",
        "mfe",
        "mae",
        "max_high_price",
        "max_high_session",
        "max_high_session_offset",
        "min_low_price",
        "min_low_session",
        "min_low_session_offset",
    }
    for item in payload["field_validity"]:
        if item["field_name"] in resolved_fields:
            item["status"] = "VALID"
            item["reason_code"] = None
    return contract_artifact(
        seal_content_addressed_contract("Outcome", payload),
        known_at=available_at,
    )


def _runner_event(
    key: str,
    session: str,
    instrument_ref: dict[str, str],
    outcome_ref: dict[str, str],
    label_ref: dict[str, str],
    available_at: str,
) -> TemporalArtifact:
    payload = deepcopy(FIXTURES["RunnerEvent"])
    payload.update(
        {
            "id": _uuid7(f"{key}:weight-event"),
            "created_at": available_at,
            "owning_authority": "ground_truth",
            "evidence_class": EVIDENCE,
            "environment_namespace": ENVIRONMENT,
            "source_refs": [],
            "instrument_ref": instrument_ref,
            "event_type": "EXPANSION_RUNNER",
            "start_session": session,
            "end_session": None,
            "label_ref": label_ref,
            "outcome_ref": outcome_ref,
            "detected_at": available_at,
        }
    )
    return contract_artifact(payload, known_at=available_at)


def _collect_refs(value, refs: dict[str, dict[str, str]]) -> None:
    if isinstance(value, Mapping):
        if isinstance(value.get("target_schema_name"), str) and isinstance(
            value.get("target_id"), str
        ):
            ref = {
                "target_schema_name": value["target_schema_name"],
                "target_id": value["target_id"],
            }
            if isinstance(value.get("content_hash"), str):
                ref["content_hash"] = value["content_hash"]
            refs[ref["target_id"]] = ref
        for child in value.values():
            _collect_refs(child, refs)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_refs(child, refs)


def _complete_catalog(roots: list[TemporalArtifact]) -> list[TemporalArtifact]:
    artifacts = {artifact.artifact_id: artifact for artifact in roots}
    refs: dict[str, dict[str, str]] = {}
    for artifact in roots:
        _collect_refs(artifact.payload, refs)
    pending = list(roots)
    while pending:
        artifact = pending.pop()
        for dependency_id in artifact.dependency_refs:
            if dependency_id in artifacts:
                continue
            ref = refs.get(dependency_id)
            assert ref is not None, f"missing typed dependency reference for {dependency_id}"
            known_at = BASE
            dependency = TemporalArtifact(
                artifact_id=dependency_id,
                artifact_kind=ref["target_schema_name"],
                revision_id=f"fixture:{dependency_id}",
                content_hash=ref.get(
                    "content_hash",
                    hashlib.sha256(dependency_id.encode("utf-8")).hexdigest(),
                ),
                created_at=known_at,
                known_at=known_at,
                evidence_class=EVIDENCE,
            )
            artifacts[dependency_id] = dependency
            pending.append(dependency)
    return list(artifacts.values())


def _fixture_rows(specs: list[dict]):
    (
        registry_artifacts,
        feature_registry_ref,
        label_registry_ref,
        protocol_registry_ref,
        adjustment_ref,
        label_ref,
        feature_id,
    ) = _registry_sources()
    rows = []
    artifacts = list(registry_artifacts)
    weight_ids: dict[str, str] = {}
    outcome_ids: dict[str, str] = {}
    for spec in specs:
        key = spec["key"]
        session = spec["session"]
        instrument = _instrument(key)
        instrument_ref = _artifact_ref(instrument)
        feature = _feature_snapshot(
            key,
            session,
            instrument_ref,
            feature_registry_ref,
            spec["feature"],
        )
        outcome = _outcome(
            key,
            session,
            instrument_ref,
            label_ref,
            spec["available_at"],
            spec.get("target", "0.01"),
        )
        event = _runner_event(
            key,
            session,
            instrument_ref,
            _artifact_ref(outcome),
            label_ref,
            spec["available_at"],
        )
        rows.append(
            DatasetSourceRow(
                instrument_ref=instrument_ref,
                feature_snapshot_ref=_artifact_ref(feature),
                outcome_ref=_artifact_ref(outcome),
                target_ref=label_ref,
                session_id=session,
                horizon_sessions=1,
                label_dependency_start_session=spec.get("dependency_start", session),
                label_dependency_end_session=spec.get("dependency_end", session),
                universe_fidelity=spec.get("fidelity", "PIT_VERIFIED"),
                sample_weight=Decimal(str(spec.get("weight", "1"))),
                sample_weight_source_ref=_artifact_ref(event),
            )
        )
        artifacts.extend((instrument, feature, outcome, event))
        weight_ids[key] = event.artifact_id
        outcome_ids[key] = outcome.artifact_id
    return (
        rows,
        _complete_catalog(artifacts),
        {
            "feature_registry_ref": feature_registry_ref,
            "label_registry_ref": label_registry_ref,
            "protocol_registry_ref": protocol_registry_ref,
            "normalization_ref": adjustment_ref,
            "label_ref": label_ref,
            "feature_id": feature_id,
            "weight_ids": weight_ids,
            "outcome_ids": outcome_ids,
        },
    )


def _plan(
    sessions: tuple[str, ...],
    folds: tuple[WalkForwardFold, ...],
    qualification_sessions: tuple[str, ...],
    refs: dict,
    *,
    fidelity: str = "PIT_VERIFIED",
    qualification_cutoff: str = "2024-03-05T00:00:00Z",
) -> DatasetBuildPlan:
    return DatasetBuildPlan(
        created_at="2024-03-06T00:00:00Z",
        evidence_class=EVIDENCE,
        environment_namespace=ENVIRONMENT,
        temporal_mode="FORWARD",
        session_order=sessions,
        folds=folds,
        qualification_sessions=qualification_sessions,
        qualification_cutoff_at=qualification_cutoff,
        memory_cutoff=qualification_cutoff,
        target_field="endpoint_return",
        feature_ids=(refs["feature_id"],),
        universe_fidelity=fidelity,
        sampling_policy="TRAINING_ONLY",
        sample_weight_policy="EXPLICIT_SOURCE",
        purge_policy="Remove rows whose label interval intersects a fold boundary.",
        embargo_policy="Reserve at least one exchange session after each training window.",
        source_refs=(),
        snapshot_refs=(),
        raw_receipt_refs=(),
        action_refs=(),
        registry_refs=(
            refs["feature_registry_ref"],
            refs["label_registry_ref"],
            refs["protocol_registry_ref"],
        ),
        revision_refs=(),
        normalization_ref=refs["normalization_ref"],
    )


def _firewall(catalog: list[TemporalArtifact]) -> TemporalFirewall:
    return TemporalFirewall(
        catalog,
        catalog_revision=hashlib.sha256(b"qc2-033-dataset-fixture").hexdigest(),
    )


def _permission(catalog: list[TemporalArtifact]) -> TemporalPermission:
    return TemporalPermission(
        operations=frozenset({TemporalOperation.EXPORT}),
        artifact_kinds=frozenset(artifact.artifact_kind for artifact in catalog),
    )


def test_crossing_label_intervals_are_purged_and_sessions_stay_whole():
    sessions = (
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
        "2024-01-09",
        "2024-01-10",
        "2024-01-11",
    )
    specs = [
        {"key": "train-base", "session": sessions[0], "feature": "1", "available_at": "2024-01-16T00:00:00Z"},
        {"key": "train-same-safe", "session": sessions[1], "feature": "2", "available_at": "2024-01-16T00:00:00Z"},
        {"key": "train-same-cross", "session": sessions[1], "feature": "4", "available_at": "2024-01-16T00:00:00Z", "dependency_end": sessions[4]},
        {"key": "validation-safe", "session": sessions[4], "feature": "3", "available_at": "2024-01-16T00:00:00Z"},
        {"key": "validation-cross", "session": sessions[4], "feature": "5", "available_at": "2024-01-16T00:00:00Z", "dependency_end": sessions[7]},
        {"key": "qualification", "session": sessions[7], "feature": "6", "available_at": "2024-03-10T00:00:00Z"},
    ]
    rows, catalog, refs = _fixture_rows(specs)
    fold = WalkForwardFold(
        fold_id="fold-1",
        training_sessions=(sessions[0], sessions[1]),
        validation_sessions=(sessions[4],),
        purge_sessions=(sessions[2],),
        embargo_sessions=(sessions[3],),
        training_cutoff_at="2024-01-20T00:00:00Z",
        validation_cutoff_at="2024-01-25T00:00:00Z",
    )
    plan = _plan(sessions, (fold,), (sessions[7],), refs)
    result = build_dataset(
        rows,
        plan=plan,
        firewall=_firewall(catalog),
        permission=_permission(catalog),
    )

    same_train = [item for item in result.row_assignments if item.get("session_id") == sessions[1]]
    same_validation = [item for item in result.row_assignments if item.get("session_id") == sessions[4]]
    assert len(same_train) == 2
    assert {item["stage"] for item in same_train} == {"TRAINING"}
    assert {item["status"] for item in same_train} == {"RELEASED", "EXCLUDED"}
    assert len(same_validation) == 2
    assert {item["stage"] for item in same_validation} == {"VALIDATION"}
    assert {item["status"] for item in same_validation} == {"RELEASED", "EXCLUDED"}
    assert sum(
        item["reason"] == "PURGED_LABEL_DEPENDENCY_OVERLAP"
        for item in result.excluded_rows
    ) == 2
    prepared = result.folds[0]
    assert all(row.sample_weight is None for row in prepared.validation_rows)
    assert prepared.training_index.rows
    assert all(row.label_available_at is not None for row in prepared.training_index.rows)
    assert all(row.label_available_at is not None for row in prepared.validation_rows)
    assert prepared.training_index.index_hash == fold_rows_hash(
        prepared.fold_id,
        fold.training_cutoff_at,
        prepared.transform.transform_hash,
        prepared.training_index.rows,
    )
    assert prepared.validation_index_hash == fold_rows_hash(
        prepared.fold_id,
        fold.validation_cutoff_at,
        prepared.transform.transform_hash,
        prepared.validation_rows,
    )


def test_fold_local_fit_maturity_and_weight_export_use_real_firewall_pipeline():
    sessions = (
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
        "2024-01-09",
        "2024-01-10",
        "2024-01-11",
        "2024-01-12",
        "2024-01-16",
    )
    specs = [
        {"key": "s0", "session": sessions[0], "feature": "1", "available_at": "2024-01-16T00:00:00Z", "weight": "1.25"},
        {"key": "s2", "session": sessions[2], "feature": "1000", "available_at": "2024-01-21T00:00:00Z", "weight": "2"},
        {"key": "s4", "session": sessions[4], "feature": "9", "available_at": "2024-01-31T00:00:00Z", "weight": "3"},
        {"key": "s6", "session": sessions[6], "feature": "5", "available_at": "2024-02-04T00:00:00Z", "weight": "4"},
        {"key": "s8", "session": sessions[8], "feature": "7", "available_at": "2024-02-10T00:00:00Z", "weight": "5"},
        {"key": "s9-qualification", "session": sessions[9], "feature": "11", "available_at": "2024-03-10T00:00:00Z", "weight": "6"},
    ]
    rows, catalog, refs = _fixture_rows(specs)
    folds = (
        WalkForwardFold(
            fold_id="fold-1",
            training_sessions=(sessions[0],),
            validation_sessions=(sessions[2],),
            purge_sessions=(),
            embargo_sessions=(sessions[1],),
            training_cutoff_at="2024-01-20T00:00:00Z",
            validation_cutoff_at="2024-01-25T00:00:00Z",
        ),
        WalkForwardFold(
            fold_id="fold-2",
            training_sessions=(sessions[0], sessions[2]),
            validation_sessions=(sessions[4],),
            purge_sessions=(),
            embargo_sessions=(sessions[3],),
            training_cutoff_at="2024-01-28T00:00:00Z",
            validation_cutoff_at="2024-02-02T00:00:00Z",
        ),
        WalkForwardFold(
            fold_id="fold-3",
            training_sessions=(sessions[0], sessions[2], sessions[4]),
            validation_sessions=(sessions[6],),
            purge_sessions=(),
            embargo_sessions=(sessions[5],),
            training_cutoff_at="2024-01-31T00:00:00Z",
            validation_cutoff_at="2024-02-08T00:00:00Z",
        ),
        WalkForwardFold(
            fold_id="fold-4",
            training_sessions=(sessions[0], sessions[2], sessions[4], sessions[6]),
            validation_sessions=(sessions[8],),
            purge_sessions=(),
            embargo_sessions=(sessions[7],),
            training_cutoff_at="2024-02-05T00:00:00Z",
            validation_cutoff_at="2024-02-12T00:00:00Z",
        ),
    )
    plan = _plan(sessions, folds, (sessions[9],), refs)

    class RecordingFirewall:
        def __init__(self, delegate):
            self.delegate = delegate
            self.requests = []

        def export(self, query, permission):
            self.requests.append((query.cutoff, set(query.artifact_ids)))
            return self.delegate.export(query, permission)

    firewall = RecordingFirewall(_firewall(catalog))
    result = build_dataset(
        rows,
        plan=plan,
        firewall=firewall,
        permission=_permission(catalog),
    )
    by_fold = {fold.fold_id: fold for fold in result.folds}
    assert by_fold["fold-1"].transform.means == (Decimal("1"),)
    assert by_fold["fold-1"].validation_rows[0].feature_values == (Decimal("999"),)
    assert by_fold["fold-3"].transform.means == (Decimal("500.5"),)
    assert by_fold["fold-4"].transform.means == (Decimal("253.75"),)
    assert by_fold["fold-1"].training_index.rows[0].sample_weight == Decimal("1.25")
    fold4_weights = {
        row.session_id: row.sample_weight
        for row in by_fold["fold-4"].training_index.rows
    }
    assert fold4_weights == {
        sessions[0]: Decimal("1.25"),
        sessions[2]: Decimal("2"),
        sessions[4]: Decimal("3"),
        sessions[6]: Decimal("4"),
    }

    s4_key = next(
        item["row_key"]
        for item in result.row_assignments
        if item.get("session_id") == sessions[4]
    )
    assert s4_key not in by_fold["fold-3"].training_index.member_row_keys
    assert s4_key in by_fold["fold-4"].training_index.member_row_keys
    assert all(
        row.sample_weight is None
        for fold in result.folds
        for row in fold.validation_rows
    )
    assert all(
        not hasattr(row, "target_value") and not hasattr(row, "sample_weight")
        for row in result.qualification_rows
    )
    s4_weight_source = refs["weight_ids"]["s4"]
    s9_weight_source = refs["weight_ids"]["s9-qualification"]
    s9_outcome = refs["outcome_ids"]["s9-qualification"]
    requests_at = {
        cutoff: [artifact_ids for request_cutoff, artifact_ids in firewall.requests if request_cutoff == cutoff]
        for cutoff in {item[0] for item in firewall.requests}
    }
    assert all(
        s4_weight_source not in artifact_ids
        for artifact_ids in requests_at["2024-01-31T00:00:00Z"]
    )
    assert all(
        s4_weight_source not in artifact_ids
        for artifact_ids in requests_at["2024-02-02T00:00:00Z"]
    )
    assert any(
        s4_weight_source in artifact_ids
        for artifact_ids in requests_at["2024-02-05T00:00:00Z"]
    )
    assert all(s9_outcome not in artifact_ids for _, artifact_ids in firewall.requests)
    assert all(
        s9_weight_source not in artifact_ids for _, artifact_ids in firewall.requests
    )
    qualification_key = next(row.row_key for row in result.qualification_rows)
    qualification_lineage = next(
        _plain(lineage)
        for lineage in result.row_lineages
        if lineage["row_key"] == qualification_key
    )
    assert all(
        ref["target_id"] != s9_outcome
        for ref in _plain(result.dataset_manifest["source_refs"])
    )
    assert all(
        ref["target_id"] != s9_outcome
        for ref in qualification_lineage["source_refs"]
    )
    assert all(
        ref["target_id"] != s9_outcome
        for row in result.qualification_rows
        if row.row_key == qualification_key
        for ref in row.source_refs
    )

    validate_contract("DatasetManifest", _plain(result.dataset_manifest))
    validate_contract("SplitManifest", _plain(result.split_manifest))
    for lineage in result.row_lineages:
        validate_contract("DatasetRowLineage", _plain(lineage))


def test_survivorship_limited_rows_cannot_claim_point_in_time_fidelity():
    sessions = (
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
    )
    rows, catalog, refs = _fixture_rows(
        [
            {
                "key": "survivorship-limited",
                "session": sessions[0],
                "feature": "1",
                "available_at": "2024-01-16T00:00:00Z",
                "fidelity": "SURVIVORSHIP_LIMITED",
            },
            {
                "key": "qualification",
                "session": sessions[3],
                "feature": "2",
                "available_at": "2024-03-10T00:00:00Z",
            },
        ]
    )
    fold = WalkForwardFold(
        fold_id="fold-1",
        training_sessions=(sessions[0],),
        validation_sessions=(sessions[2],),
        purge_sessions=(),
        embargo_sessions=(sessions[1],),
        training_cutoff_at="2024-01-20T00:00:00Z",
        validation_cutoff_at="2024-01-25T00:00:00Z",
    )
    plan = _plan(
        sessions,
        (fold,),
        (sessions[3],),
        refs,
        fidelity="PIT_VERIFIED",
    )
    with pytest.raises(DatasetBuilderError, match="cannot exceed the fidelity"):
        build_dataset(
            rows,
            plan=plan,
            firewall=_firewall(catalog),
            permission=_permission(catalog),
        )
