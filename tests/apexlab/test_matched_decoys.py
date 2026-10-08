from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from qc2_apexlab import (
    CaliperRule,
    MatchedDecoyError,
    MatchedDecoyRiskSet,
    MatchingPolicy,
    OriginalPopulationEvidence,
    PositiveCase,
    RiskSetMember,
    contract_artifact,
    finalize_matched_decoy_set,
    match_pre_outcome,
    require_original_distribution_calibration,
)
from qc2_apexlab.models import seal_content_addressed_contract
from qc2_temporal_firewall import TemporalArtifact

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = {
    item["contract"]: item["payload"]
    for item in json.loads(
        (ROOT / "packages" / "contracts" / "fixtures" / "v1" / "valid.json").read_text()
    )
}

SESSION = "2026-04-10"
CUTOFF = "2026-04-10T13:30:00Z"
FEATURE_CUTOFF = "2026-04-10T13:25:00Z"
OUTCOME_CREATED = "2026-04-20T10:00:00Z"
OUTCOME_AVAILABLE = "2026-04-20T10:15:00Z"
EVENT_CREATED = "2026-04-20T12:00:00Z"
LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
UNIVERSE_SCHEMA = "qc2.identity_market.UniverseManifest.v1"
CENSUS_SCHEMA = "qc2.identity_market.CandidateCensus.v1"
BUNDLE_SCHEMA = "qc2.identity_market.DataBundle.v1"
REGISTRY_SCHEMA = "qc2.scientific_definitions.FeatureRegistry.v1"
MANIFEST_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"
OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"
DATASET_SCHEMA = "qc2.outcomes_research.DatasetManifest.v1"
LABEL_REF = {
    "target_schema_name": LABEL_SCHEMA,
    "target_id": "018f0000-0000-7000-8000-000000000099",
    "content_hash": "a" * 64,
}


def _uuid7(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    rand_a = random_bits >> 62
    rand_b = random_bits & ((1 << 62) - 1)
    timestamp_ms = 1_767_225_600_000
    value = (timestamp_ms << 80) | (7 << 76) | (rand_a << 64) | (2 << 62) | rand_b
    return str(UUID(int=value))


def _ref(schema: str, artifact_id: str, content_hash: str | None = None) -> dict[str, str]:
    value = {"target_schema_name": schema, "target_id": artifact_id}
    if content_hash is not None:
        value["content_hash"] = content_hash
    return value


def _stub(
    ref: dict[str, str], *, known_at: str, evidence_class: str = "SYNTHETIC_FIXTURE"
) -> TemporalArtifact:
    return TemporalArtifact(
        artifact_id=ref["target_id"],
        artifact_kind=ref["target_schema_name"],
        revision_id=f"fixture:{ref['target_id']}",
        content_hash=ref.get(
            "content_hash", hashlib.sha256(ref["target_id"].encode()).hexdigest()
        ),
        created_at=known_at,
        known_at=known_at,
        evidence_class=evidence_class,
    )


def _instrument(key: str) -> TemporalArtifact:
    payload = deepcopy(FIXTURES["Instrument"])
    payload.update(
        {
            "id": _uuid7(f"{key}:instrument"),
            "created_at": "2026-04-09T20:00:00Z",
            "owning_authority": "instrument_universe",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "stable_instrument_key": key,
            "first_known_at": "2026-04-09T20:00:00Z",
        }
    )
    return contract_artifact(payload, known_at="2026-04-09T20:00:00Z")


def _feature_snapshot(
    key: str,
    instrument: TemporalArtifact,
    values: dict[str, str],
    *,
    registry_ref: dict[str, str],
    transform_ref: dict[str, str],
    decision_cutoff: str = FEATURE_CUTOFF,
) -> TemporalArtifact:
    payload = deepcopy(FIXTURES["FeatureSnapshot"])
    feature_values = [
        {
            "feature_id": feature_id,
            "unit": "fraction",
            "output_dtype": "DECIMAL",
            "value": value,
        }
        for feature_id, value in sorted(values.items())
    ]
    payload.update(
        {
            "id": _uuid7(f"{key}:feature"),
            "created_at": "2026-04-10T13:20:00Z",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [],
            "session_id": SESSION,
            "instrument_ref": _ref(INSTRUMENT_SCHEMA, instrument.artifact_id),
            "registry_ref": registry_ref,
            "feature_values": feature_values,
            "input_hashes": ["b" * 64],
            "transform_refs": [transform_ref],
            "decision_cutoff": decision_cutoff,
            "code_hash": "c" * 64,
            "environment_fingerprint": "d" * 64,
        }
    )
    sealed = seal_content_addressed_contract("FeatureSnapshot", payload)
    return contract_artifact(sealed, known_at="2026-04-10T13:20:00Z")


def _risk_set(
    values: dict[str, dict[str, str]],
    *,
    unscorable: tuple[str, ...] = (),
    source_artifacts: tuple[TemporalArtifact, ...] = (),
    feature_cutoff: str = FEATURE_CUTOFF,
) -> tuple[MatchedDecoyRiskSet, dict[str, TemporalArtifact]]:
    instruments = {key: _instrument(key) for key in values}
    registry_ref = _ref(REGISTRY_SCHEMA, _uuid7("feature-registry"), "e" * 64)
    transform_ref = _ref(MANIFEST_SCHEMA, _uuid7("feature-transform"), "f" * 64)
    shared_sources = [
        _stub(registry_ref, known_at="2026-04-10T08:00:00Z"),
        _stub(transform_ref, known_at="2026-04-10T08:00:00Z"),
    ]
    census_ref = _ref(CENSUS_SCHEMA, _uuid7("candidate-census"))
    bundle_ref = _ref(BUNDLE_SCHEMA, _uuid7("data-bundle"))
    member_refs = [_ref(INSTRUMENT_SCHEMA, item.artifact_id) for item in instruments.values()]
    universe_payload = deepcopy(FIXTURES["UniverseManifest"])
    universe_payload.update(
        {
            "id": _uuid7("universe:" + ",".join(sorted(values))),
            "created_at": CUTOFF,
            "owning_authority": "instrument_universe",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [census_ref, bundle_ref, *member_refs],
            "session_id": SESSION,
            "census_ref": census_ref,
            "data_bundle_ref": bundle_ref,
            "eligible_instrument_refs": member_refs,
            "unscorable_instrument_refs": [
                _ref(INSTRUMENT_SCHEMA, instruments[key].artifact_id)
                for key in unscorable
            ],
            "reason_counts": [],
            "cutoff": CUTOFF,
        }
    )
    universe = contract_artifact(universe_payload, known_at=CUTOFF)
    members: list[RiskSetMember] = []
    for key, instrument in instruments.items():
        feature = _feature_snapshot(
            key,
            instrument,
            values[key],
            registry_ref=registry_ref,
            transform_ref=transform_ref,
            decision_cutoff=feature_cutoff,
        )
        members.append(RiskSetMember(instrument=instrument, feature_snapshot=feature))
    sources = (
        *shared_sources,
        _stub(census_ref, known_at="2026-04-09T20:00:00Z"),
        _stub(bundle_ref, known_at="2026-04-09T20:00:00Z"),
        *source_artifacts,
    )
    return (
        MatchedDecoyRiskSet(
            universe_manifest=universe,
            regime_id="VOL_HIGH",
            members=tuple(members),
            source_artifacts=sources,
        ),
        instruments,
    )


def _outcome(
    key: str,
    instrument: TemporalArtifact,
    *,
    positive: bool,
    created_at: str = OUTCOME_CREATED,
    available_at: str = OUTCOME_AVAILABLE,
) -> TemporalArtifact:
    payload = deepcopy(FIXTURES["Outcome"])
    bar_ref = _ref("qc2.identity_market.DailyBar.v1", _uuid7(f"{key}:bar"))
    payload.update(
        {
            "id": _uuid7(f"{key}:outcome"),
            "created_at": created_at,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [],
            "instrument_ref": _ref(INSTRUMENT_SCHEMA, instrument.artifact_id),
            "session_id": SESSION,
            "label_ref": LABEL_REF,
            "reference_bar_ref": bar_ref,
            "outcome_state": "RESOLVED",
            "endpoint_return": "0.020000000000" if positive else "-0.010000000000",
            "max_high_return": "0.200000000000" if positive else "0.010000000000",
            "min_low_return": "-0.020000000000",
            "mfe": "0.200000000000" if positive else "0.010000000000",
            "mae": "-0.020000000000",
            "max_high_price": "120" if positive else "101",
            "max_high_session": "2026-04-15",
            "max_high_session_offset": 5,
            "min_low_price": "98",
            "min_low_session": "2026-04-11",
            "min_low_session_offset": 1,
            "available_for_learning_at": available_at,
            "reason_codes": [],
        }
    )
    valid_fields = {
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
        if item["field_name"] in valid_fields:
            item["status"] = "VALID"
            item["reason_code"] = None
    sealed = seal_content_addressed_contract("Outcome", payload)
    return contract_artifact(sealed, known_at=created_at)


def _event(key: str, instrument: TemporalArtifact, outcome: TemporalArtifact) -> TemporalArtifact:
    payload = deepcopy(FIXTURES["RunnerEvent"])
    payload.update(
        {
            "id": _uuid7(f"{key}:event"),
            "created_at": EVENT_CREATED,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [],
            "instrument_ref": _ref(INSTRUMENT_SCHEMA, instrument.artifact_id),
            "event_type": "EXPANSION_RUNNER",
            "start_session": SESSION,
            "end_session": "2026-04-15",
            "label_ref": LABEL_REF,
            "outcome_ref": _ref(
                OUTCOME_SCHEMA,
                outcome.artifact_id,
                outcome.payload["content_hash"],
            ),
            "detected_at": EVENT_CREATED,
            "evidence_refs": [],
        }
    )
    return contract_artifact(payload, known_at=EVENT_CREATED)


def _population(
    risk_set: MatchedDecoyRiskSet,
    instruments: dict[str, TemporalArtifact],
    positive_keys: set[str],
) -> tuple[OriginalPopulationEvidence, dict[str, TemporalArtifact]]:
    outcomes = {
        key: _outcome(key, instrument, positive=key in positive_keys)
        for key, instrument in instruments.items()
    }
    universe_ref = _ref(UNIVERSE_SCHEMA, risk_set.universe_manifest.artifact_id)
    payload = deepcopy(FIXTURES["DatasetManifest"])
    payload.update(
        {
            "id": _uuid7("dataset:" + ",".join(sorted(instruments))),
            "created_at": EVENT_CREATED,
            "owning_authority": "apexlab",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [universe_ref],
            "universe_fidelity": "PIT_VERIFIED",
            "snapshot_refs": [],
            "raw_receipt_refs": [],
            "action_refs": [],
            "registry_refs": [],
            "memory_cutoff": EVENT_CREATED,
            "time_start": SESSION,
            "time_end": SESSION,
            "symbol_count": len(instruments),
            "missingness_counts": [],
            "revision_refs": [],
            "sampling_policy": "ORIGINAL_CENSUS",
        }
    )
    dataset = seal_content_addressed_contract("DatasetManifest", payload)
    dataset_artifact = contract_artifact(dataset, known_at=EVENT_CREATED)
    evidence = OriginalPopulationEvidence(
        dataset_manifest=dataset_artifact,
        outcome_artifacts=tuple(outcomes.values()),
    )
    return evidence, outcomes


def _case_list(
    instruments: dict[str, TemporalArtifact],
    outcomes: dict[str, TemporalArtifact],
    positive_keys: set[str],
) -> tuple[PositiveCase, ...]:
    return tuple(
        PositiveCase(event=_event(key, instruments[key], outcomes[key]))
        for key in sorted(positive_keys)
    )


def _policy(*, caliper: str = "0.20", decoys_per_case: int = 1) -> MatchingPolicy:
    return MatchingPolicy(
        rules=(
            CaliperRule(
                feature_id="prior_return",
                unit="fraction",
                scale=Decimal("1"),
                maximum_difference=Decimal(caliper),
            ),
        ),
        decoys_per_case=decoys_per_case,
    )


def test_same_stratum_matches_record_reuse_weights_and_calibration_boundary() -> None:
    risk_set, instruments = _risk_set(
        {
            "case-a": {"prior_return": "0.00"},
            "case-b": {"prior_return": "0.10"},
            "control-a": {"prior_return": "0.04"},
            "control-b": {"prior_return": "0.70"},
        }
    )
    positive_keys = {"case-a", "case-b"}
    population, outcomes = _population(risk_set, instruments, positive_keys)
    plan = match_pre_outcome(
        risk_set, _case_list(instruments, outcomes, positive_keys), _policy()
    )

    assert len(plan.assignments) == 2
    assert {row.session_id for row in plan.assignments} == {SESSION}
    assert {row.regime_id for row in plan.assignments} == {"VOL_HIGH"}
    assert {row.decoy_instrument_ref["target_id"] for row in plan.assignments} == {
        instruments["control-a"].artifact_id
    }
    assert all(row.absolute_difference == Decimal("0.04") or row.absolute_difference == Decimal("0.06")
               for assignment in plan.assignments for row in assignment.variable_distances)
    assert all(row.same_stratum_candidates == 3 for row in plan.candidate_counts)
    assert all(row.within_caliper_candidates == 2 for row in plan.candidate_counts)

    result = finalize_matched_decoy_set(
        plan, population, created_at="2026-04-21T12:00:00Z"
    )
    assert result.record.contract["schema_name"] == "qc2.outcomes_research.MatchedDecoySet.v1"
    assert len(result.record.contract["positive_event_refs"]) == 2
    assert result.record.contract["decoy_instrument_refs"] == [
        _ref(INSTRUMENT_SCHEMA, instruments["control-a"].artifact_id)
    ]
    reuse = next(row for row in result.reuse if row.instrument_ref["target_id"] == instruments["control-a"].artifact_id)
    assert reuse.pre_outcome_use_count == 2
    assert reuse.confirmed_negative_use_count == 2
    assert result.positive_population_count == 2
    assert result.negative_population_count == 2
    assert result.natural_prevalence == Decimal("0.5")
    assert result.sample_prevalence == Decimal(2) / Decimal(3)
    assert result.weight_status == "CLASS_PRIOR_CORRECTION_ONLY"
    assert [row.weight for row in result.training_sample_weights if row.sample_kind == "POSITIVE_CASE"] == [
        Decimal("0.75"),
        Decimal("0.75"),
    ]
    negative_weight = next(
        row for row in result.training_sample_weights if row.sample_kind == "UNIQUE_NEGATIVE_DECOY"
    )
    assert negative_weight.weight == Decimal("1.5")
    assert negative_weight.reuse_count == 2
    assert result.calibration_eligible is False
    assert require_original_distribution_calibration(
        result, result.original_population_ref
    ) == result.original_population_ref
    matched_set_ref = _ref(
        result.record.contract["schema_name"],
        result.record.contract["id"],
        result.record.contract["content_hash"],
    )
    with pytest.raises(MatchedDecoyError, match="original population"):
        require_original_distribution_calibration(result, matched_set_ref)


def test_hard_unmatched_positive_is_preserved_when_no_candidate_passes_calipers() -> None:
    risk_set, instruments = _risk_set(
        {
            "winner": {"prior_return": "0"},
            "distant-control": {"prior_return": "0.8"},
        }
    )
    positive_keys = {"winner"}
    population, outcomes = _population(risk_set, instruments, positive_keys)
    plan = match_pre_outcome(
        risk_set,
        _case_list(instruments, outcomes, positive_keys),
        _policy(caliper="0.05"),
    )
    result = finalize_matched_decoy_set(
        plan, population, created_at="2026-04-21T12:00:00Z"
    )

    assert plan.assignments == ()
    assert result.record.contract["positive_event_refs"] == [
        _ref(EVENT_SCHEMA, plan.cases[0].event.artifact_id)
    ]
    assert result.record.contract["decoy_instrument_refs"] == []
    assert len(result.unmatched_cases) == 1
    assert result.unmatched_cases[0].reason == "NO_SAME_STRATUM_CANDIDATE_WITHIN_CALIPERS"
    assert result.unmatched_cases[0].confirmed_negative_matches == 0
    assert result.weight_status == "NOT_ESTIMABLE_EMPTY_TRAINING_CLASS"
    assert result.training_sample_weights == ()


def test_selected_future_positive_is_not_replaced_after_outcome_membership() -> None:
    risk_set, instruments = _risk_set(
        {
            "case-a": {"prior_return": "0.00"},
            "case-b": {"prior_return": "0.01"},
            "control": {"prior_return": "0.03"},
        }
    )
    positive_keys = {"case-a", "case-b"}
    population, outcomes = _population(risk_set, instruments, positive_keys)
    plan = match_pre_outcome(
        risk_set,
        _case_list(instruments, outcomes, positive_keys),
        _policy(caliper="0.20"),
    )
    case_a_event = next(
        case.event.artifact_id
        for case in plan.cases
        if case.event.payload["instrument_ref"]["target_id"] == instruments["case-a"].artifact_id
    )
    case_a_match = next(row for row in plan.assignments if row.event_ref["target_id"] == case_a_event)
    assert case_a_match.decoy_instrument_ref["target_id"] == instruments["case-b"].artifact_id

    result = finalize_matched_decoy_set(
        plan, population, created_at="2026-04-21T12:00:00Z"
    )
    assert result.record.contract["decoy_instrument_refs"] == []
    assert any(
        row.event_ref["target_id"] == case_a_event
        and row.reason == "POST_MATCH_OUTCOME_MEMBERSHIP_REJECTED_CANDIDATES"
        for row in result.unmatched_cases
    )
    assert not any(
        row.assignment.decoy_instrument_ref["target_id"] == instruments["control"].artifact_id
        and row.retained_as_decoy
        for row in result.finalized_matches
    )


def test_outcome_variables_cannot_be_selected_and_extra_outcome_fields_do_not_change_distance() -> None:
    with pytest.raises(MatchedDecoyError, match="outcome"):
        CaliperRule("max_high_return", "fraction", Decimal(1), Decimal("0.2"))
    with pytest.raises(MatchedDecoyError, match="outcome"):
        CaliperRule("future_return_5d", "fraction", Decimal(1), Decimal("0.2"))

    base = {
        "case": {"prior_return": "0.00", "max_high_return": "100"},
        "near": {"prior_return": "0.02", "max_high_return": "-100"},
        "far": {"prior_return": "0.10", "max_high_return": "0"},
    }
    first_set, first_instruments = _risk_set(base)
    _, first_outcomes = _population(
        first_set, first_instruments, {"case"}
    )
    first_plan = match_pre_outcome(
        first_set, _case_list(first_instruments, first_outcomes, {"case"}), _policy()
    )

    changed = {
        key: {**values, "max_high_return": str(-Decimal(values["max_high_return"]))}
        for key, values in base.items()
    }
    second_set, second_instruments = _risk_set(changed)
    _, second_outcomes = _population(
        second_set, second_instruments, {"case"}
    )
    second_plan = match_pre_outcome(
        second_set, _case_list(second_instruments, second_outcomes, {"case"}), _policy()
    )
    assert first_plan.assignments[0].decoy_instrument_ref["target_id"] == first_instruments["near"].artifact_id
    assert second_plan.assignments[0].decoy_instrument_ref["target_id"] == second_instruments["near"].artifact_id
    assert first_plan.assignments[0].total_distance == second_plan.assignments[0].total_distance
    assert "max_high_return" not in _policy().feature_ids
    assert first_plan.catalog_revision != second_plan.catalog_revision


def test_feature_dependency_unavailable_at_cutoff_is_rejected() -> None:
    risk_set, instruments = _risk_set(
        {
            "case": {"prior_return": "0"},
            "control": {"prior_return": "0.01"},
        }
    )
    late_transform = next(
        source
        for source in risk_set.source_artifacts
        if source.artifact_kind == MANIFEST_SCHEMA
    )
    future = replace(
        late_transform,
        created_at="2026-04-10T14:00:00Z",
        known_at="2026-04-10T14:00:00Z",
    )
    late_set = MatchedDecoyRiskSet(
        universe_manifest=risk_set.universe_manifest,
        regime_id=risk_set.regime_id,
        members=risk_set.members,
        source_artifacts=tuple(
            future if source.artifact_id == late_transform.artifact_id else source
            for source in risk_set.source_artifacts
        ),
    )
    population, outcomes = _population(late_set, instruments, {"case"})
    with pytest.raises(MatchedDecoyError, match="cutoff-safe"):
        match_pre_outcome(
            late_set, _case_list(instruments, outcomes, {"case"}), _policy()
        )
    assert population.outcome_artifacts
