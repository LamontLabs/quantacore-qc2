from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from qc2_apexlab import (
    FalseMonsterCandidate,
    FalseMonsterCategory,
    FalseMonsterUncertaintyReason,
    FrozenFalseMonsterPolicy,
    GenomeError,
    ReviewArtifactRef,
    append_research_hypothesis_annotation,
    build_false_monster_review_queue,
    verify_research_annotation_chain,
)
from qc2_apexlab.models import seal_content_addressed_contract
from qc2_contracts.runtime import validate_contract
from test_runner_genome import FIXTURES, _outcome_contract, _ref, _uuid7

LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
SCORE_SCHEMA = "qc2.scientific_definitions.ScoreManifest.v1"
HEAD_SCHEMA = "qc2.models_prediction.ModelHeadDefinition.v1"
HEAD_OUTPUT_SCHEMA = "qc2.models_prediction.ModelHeadOutput.v1"
PREDICTION_SCHEMA = "qc2.models_prediction.Prediction.v1"
OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"
GENOME_SCHEMA = "qc2.outcomes_research.FailureGenome.v1"
EVIDENCE_SCHEMA = "qc2.integrity_build.EvidenceEvent.v1"
REVISION_SCHEMA = "qc2.outcomes_research.OutcomeRevision.v1"
START = "2026-04-09T19:00:00Z"
PREDICTION_AT = "2026-04-10T20:00:00Z"
OUTCOME_AT = "2026-04-16T20:00:00Z"
REVIEWED_AT = "2026-04-20T20:00:00Z"


def _ref_for(contract: dict[str, object]) -> dict[str, str]:
    result = {
        "target_schema_name": str(contract["schema_name"]),
        "target_id": str(contract["id"]),
    }
    if isinstance(contract.get("content_hash"), str):
        result["content_hash"] = str(contract["content_hash"])
    return result


def _base_sources() -> dict[str, dict[str, object]]:
    label = deepcopy(FIXTURES["LabelDefinition"])
    label.update(
        {
            "id": _uuid7("false-monster:label"),
            "created_at": START,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "stable_key": "false-monster-fixture",
            "target_event": "EXPANSION_RUNNER",
            "horizon_sessions": 5,
        }
    )
    label = seal_content_addressed_contract("LabelDefinition", label)

    score_manifest = deepcopy(FIXTURES["ScoreManifest"])
    score_manifest.update(
        {
            "id": _uuid7("false-monster:score-manifest"),
            "created_at": START,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
        }
    )
    score_manifest = seal_content_addressed_contract("ScoreManifest", score_manifest)

    model = deepcopy(FIXTURES["ModelManifest"])
    model.update(
        {
            "id": _uuid7("false-monster:model"),
            "created_at": START,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
        }
    )
    model = seal_content_addressed_contract("ModelManifest", model)

    head = deepcopy(FIXTURES["ModelHeadDefinition"])
    head.update(
        {
            "id": _uuid7("false-monster:head"),
            "created_at": START,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "model_ref": _ref_for(model),
            "head_name": "fixture_expansion_probability",
            "output_kind": "PROBABILITY",
            "label_ref": _ref_for(label),
            "horizon_sessions": label["horizon_sessions"],
            "availability": "AVAILABLE",
            "output_precision": 12,
        }
    )
    return {
        "label": label,
        "score_manifest": score_manifest,
        "model": model,
        "head": head,
    }


def _policy(sources: dict[str, dict[str, object]]) -> FrozenFalseMonsterPolicy:
    return FrozenFalseMonsterPolicy(
        label_definition_ref=ReviewArtifactRef.from_value(_ref_for(sources["label"])),
        score_manifest_ref=ReviewArtifactRef.from_value(
            _ref_for(sources["score_manifest"])
        ),
        probability_head_ref=ReviewArtifactRef.from_value(_ref_for(sources["head"])),
        minimum_probability="0.900000000000",
        frozen_at=START,
    )


def _case(
    sources: dict[str, dict[str, object]],
    key: str,
    *,
    failure_type: str | None = "FALSE_MONSTER",
    event_type: str = "FAILURE",
    unresolved: bool = False,
    data_error: bool = False,
    probability: str = "0.950000000000",
    score: str = "82.250000",
) -> FalseMonsterCandidate:
    label = sources["label"]
    score_manifest = sources["score_manifest"]
    model = sources["model"]
    head = sources["head"]
    instrument_ref = _ref("qc2.identity_market.Instrument.v1", _uuid7("shared-instrument"))

    head_output = deepcopy(FIXTURES["ModelHeadOutput"])
    head_output.update(
        {
            "id": _uuid7(f"{key}:head-output"),
            "created_at": PREDICTION_AT,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "head_ref": _ref_for(head),
            "instrument_ref": instrument_ref,
            "session_id": "2026-04-10",
            "output_value": probability,
            "output_unit": "probability",
            "availability": "AVAILABLE",
            "reason_code": None,
        }
    )

    prediction = deepcopy(FIXTURES["Prediction"])
    prediction.update(
        {
            "id": _uuid7(f"{key}:prediction"),
            "created_at": PREDICTION_AT,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "session_id": "2026-04-10",
            "instrument_ref": instrument_ref,
            "horizon_label_refs": [_ref_for(label)],
            "head_output_refs": [_ref_for(head_output)],
            "score_manifest_ref": _ref_for(score_manifest),
            "score": score,
            "rank": 1,
            "disposition": "SCORED",
            "unscorable_reason": None,
            "model_ref": _ref_for(model),
        }
    )
    prediction = seal_content_addressed_contract("Prediction", prediction)

    if data_error:
        prior_outcome = _outcome_contract(
            f"{key}:prior",
            evidence_class="SYNTHETIC_FIXTURE",
            created_at=OUTCOME_AT,
            available_for_learning_at=OUTCOME_AT,
        )
        prior_outcome["label_ref"] = _ref_for(label)
        prior_outcome = seal_content_addressed_contract("Outcome", prior_outcome)
        outcome = _outcome_contract(
            f"{key}:replacement",
            evidence_class="SYNTHETIC_FIXTURE",
            created_at="2026-04-18T20:00:00Z",
            available_for_learning_at="2026-04-18T20:00:00Z",
        )
        outcome["label_ref"] = _ref_for(label)
        outcome = seal_content_addressed_contract("Outcome", outcome)
    elif unresolved:
        prior_outcome = None
        outcome = deepcopy(FIXTURES["Outcome"])
        outcome.update(
            {
                "id": _uuid7(f"{key}:outcome"),
                "created_at": OUTCOME_AT,
                "evidence_class": "SYNTHETIC_FIXTURE",
                "environment_namespace": "test",
                "instrument_ref": instrument_ref,
                "session_id": "2026-04-10",
                "label_ref": _ref_for(label),
                "outcome_state": "UNRESOLVED_DATA",
                "available_for_learning_at": None,
                "reason_codes": ["awaiting_resolution"],
            }
        )
        outcome = seal_content_addressed_contract("Outcome", outcome)
    else:
        prior_outcome = None
        outcome = _outcome_contract(
            f"{key}:outcome",
            evidence_class="SYNTHETIC_FIXTURE",
            created_at=OUTCOME_AT,
            available_for_learning_at=OUTCOME_AT,
        )
        outcome["label_ref"] = _ref_for(label)
        outcome["instrument_ref"] = instrument_ref
        outcome = seal_content_addressed_contract("Outcome", outcome)

    event_outcome = prior_outcome if data_error else outcome
    event = deepcopy(FIXTURES["RunnerEvent"])
    event.update(
        {
            "id": _uuid7(f"{key}:event"),
            "created_at": OUTCOME_AT,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "instrument_ref": instrument_ref,
            "event_type": event_type,
            "start_session": "2026-04-10",
            "end_session": None,
            "label_ref": _ref_for(label),
            "outcome_ref": _ref_for(event_outcome),
            "detected_at": OUTCOME_AT,
            "source_refs": [],
            "evidence_refs": [],
        }
    )

    revision = None
    if data_error:
        evidence = deepcopy(FIXTURES["EvidenceEvent"])
        evidence.update(
            {
                "id": _uuid7(f"{key}:revision-evidence"),
                "created_at": "2026-04-18T20:00:00Z",
                "evidence_class": "SYNTHETIC_FIXTURE",
                "environment_namespace": "test",
                "event_type": "outcome_revision_review",
                "dependency_refs": [],
            }
        )
        evidence = seal_content_addressed_contract("EvidenceEvent", evidence)

        revision = deepcopy(FIXTURES["OutcomeRevision"])
        revision.update(
            {
                "id": _uuid7(f"{key}:revision"),
                "created_at": "2026-04-18T20:00:00Z",
                "discovered_at": "2026-04-18T20:00:00Z",
                "evidence_class": "SYNTHETIC_FIXTURE",
                "environment_namespace": "test",
                "source_refs": [_ref_for(evidence)],
                "prior_outcome_ref": _ref_for(prior_outcome),
                "replacement_outcome_ref": _ref_for(outcome),
                "revision_reason": "corrected_source_data",
                "correction_policy_ref": _ref(
                    "qc2.integrity_build.ConfigurationManifest.v1",
                    _uuid7(f"{key}:correction-policy"),
                    "b" * 64,
                ),
            }
        )

    genome = None
    if failure_type is not None:
        provenance_refs = []
        if revision is not None:
            provenance_refs.append(_ref_for(revision))
        genome = deepcopy(FIXTURES["FailureGenome"])
        genome.update(
            {
                "id": _uuid7(f"{key}:failure-genome"),
                "created_at": "2026-04-19T20:00:00Z",
                "evidence_class": "SYNTHETIC_FIXTURE",
                "environment_namespace": "test",
                "source_refs": [
                    _ref_for(event),
                    _ref_for(prediction),
                    _ref_for(outcome),
                    *provenance_refs,
                ],
                "event_ref": _ref_for(event),
                "failure_type": failure_type,
                "prediction_refs": [_ref_for(prediction)],
                "outcome_refs": [_ref_for(outcome)],
                "provenance_refs": provenance_refs,
                "event_time": "2026-04-10T20:00:00Z",
                "available_for_learning_at": outcome["available_for_learning_at"]
                or "2026-04-19T20:00:00Z",
                "temporal_dependency_refs": [
                    *genome["temporal_dependency_refs"],
                    _ref_for(prediction),
                    _ref_for(outcome),
                    *provenance_refs,
                ],
            }
        )
        genome = seal_content_addressed_contract("FailureGenome", genome)

    return FalseMonsterCandidate(
        prediction_contract=prediction,
        head_definition_contract=head,
        head_output_contract=head_output,
        score_manifest_contract=score_manifest,
        label_definition_contract=label,
        outcome_contract=outcome,
        runner_event_contract=event,
        failure_genome_contract=genome,
        prior_outcome_contract=prior_outcome,
        outcome_revision_contract=revision,
    )


def _build(
    candidates: tuple[FalseMonsterCandidate, ...],
    policy: FrozenFalseMonsterPolicy,
):
    return build_false_monster_review_queue(
        candidates,
        policy=policy,
        created_at=REVIEWED_AT,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )


def _copy_candidate(
    candidate: FalseMonsterCandidate,
    **overrides: dict[str, object] | None,
) -> FalseMonsterCandidate:
    values: dict[str, dict[str, object] | None] = {
        "prediction_contract": candidate.prediction_contract,
        "head_definition_contract": candidate.head_definition_contract,
        "head_output_contract": candidate.head_output_contract,
        "score_manifest_contract": candidate.score_manifest_contract,
        "label_definition_contract": candidate.label_definition_contract,
        "outcome_contract": candidate.outcome_contract,
        "runner_event_contract": candidate.runner_event_contract,
        "failure_genome_contract": candidate.failure_genome_contract,
        "prior_outcome_contract": candidate.prior_outcome_contract,
        "outcome_revision_contract": candidate.outcome_revision_contract,
    }
    values.update(overrides)
    return FalseMonsterCandidate(**values)  # type: ignore[arg-type]


def test_resolved_false_positive_categories_are_linked_and_reproducible() -> None:
    sources = _base_sources()
    policy = _policy(sources)
    candidates = (
        _case(sources, "non-event", failure_type="FALSE_MONSTER"),
        _case(sources, "downside", failure_type="COLLAPSE"),
        _case(sources, "timing", failure_type="TIMING_MISS"),
        _case(sources, "data-error", failure_type="DATA_ERROR", data_error=True),
    )

    queue = _build(candidates, policy)
    repeated = _build(tuple(reversed(candidates)), policy)

    assert {case.category for case in queue.cases} == {
        FalseMonsterCategory.NON_EVENT,
        FalseMonsterCategory.DOWNSIDE,
        FalseMonsterCategory.TIMING_MISS,
        FalseMonsterCategory.DATA_ERROR,
    }
    assert [case.case_id for case in queue.cases] == [
        case.case_id for case in repeated.cases
    ]
    assert queue.queue_hash == repeated.queue_hash

    for case in queue.cases:
        contract = case.contract
        validate_contract("ReviewCase", contract)
        assert contract["prediction_ref"]["target_schema_name"] == PREDICTION_SCHEMA
        assert any(
            ref["target_schema_name"] == HEAD_OUTPUT_SCHEMA
            for ref in contract["source_refs"]
        )
        assert any(
            ref["target_schema_name"] == OUTCOME_SCHEMA
            for ref in contract["evidence_refs"]
        )
        assert f"FALSE_MONSTER_POLICY_SHA256:{policy.policy_hash}" in contract["reason_codes"]
        assert case.is_negative_training_example is (
            case.category is not FalseMonsterCategory.DATA_ERROR
        )
    data_error = next(
        case for case in queue.cases if case.category is FalseMonsterCategory.DATA_ERROR
    )
    assert data_error.contract["review_kind"] == "DATA_QUALITY"
    assert "DATA_ERROR_DIAGNOSTIC_NOT_NEGATIVE_TRAINING" in data_error.contract["reason_codes"]
    assert not data_error.is_negative_training_example


def test_unfilled_scientific_success_is_not_relabelled_prediction_failure() -> None:
    sources = _base_sources()
    policy = _policy(sources)
    candidate = _case(
        sources,
        "scientific-success-no-fill",
        failure_type=None,
        event_type="EXPANSION_RUNNER",
    )
    paper_execution_result = {"status": "UNFILLED", "filled_quantity": "0"}

    queue = _build((candidate,), policy)

    assert paper_execution_result["status"] == "UNFILLED"
    assert queue.cases == ()
    assert queue.uncertainties == ()


def test_unresolved_outcome_is_retained_as_uncertainty_not_a_training_case() -> None:
    sources = _base_sources()
    policy = _policy(sources)
    candidate = _case(
        sources,
        "uncertain-label",
        failure_type=None,
        event_type="FAILURE",
        unresolved=True,
    )

    queue = _build((candidate,), policy)

    assert queue.cases == ()
    assert len(queue.uncertainties) == 1
    unresolved = queue.uncertainties[0]
    assert unresolved.reason is FalseMonsterUncertaintyReason.OUTCOME_NOT_RESOLVED
    assert unresolved.record["outcome_state"] == "UNRESOLVED_DATA"
    assert unresolved.record["classification"] == "UNCERTAIN_NOT_FALSE_POSITIVE"
    assert not unresolved.is_negative_training_example
    assert unresolved.record["record_schema"] != "qc2.outcomes_research.ReviewCase.v1"


def test_unavailable_score_or_probability_remains_a_linked_uncertainty() -> None:
    sources = _base_sources()
    policy = _policy(sources)
    candidate = _case(sources, "missing-head-score")

    unavailable_head = candidate.head_output_contract
    unavailable_head.update(
        {
            "availability": "UNAVAILABLE_MODEL",
            "output_value": None,
            "reason_code": "model_unavailable",
        }
    )
    head_uncertainty = _build(
        (_copy_candidate(candidate, head_output_contract=unavailable_head),),
        policy,
    ).uncertainties[0]
    assert head_uncertainty.reason is FalseMonsterUncertaintyReason.PROBABILITY_HEAD_UNAVAILABLE
    assert any(
        ref["target_schema_name"] == EVENT_SCHEMA
        for ref in head_uncertainty.record["source_refs"]
    )
    assert any(
        ref["target_schema_name"] == GENOME_SCHEMA
        for ref in head_uncertainty.record["source_refs"]
    )

    unscored_prediction = candidate.prediction_contract
    unscored_prediction.update(
        {
            "score": None,
            "rank": None,
            "disposition": "UNSCORABLE",
            "unscorable_reason": "score_unavailable",
        }
    )
    unscored_prediction = seal_content_addressed_contract(
        "Prediction", unscored_prediction
    )
    genome_for_unscored = candidate.failure_genome_contract
    assert genome_for_unscored is not None
    genome_for_unscored["prediction_refs"] = [_ref_for(unscored_prediction)]
    genome_for_unscored["source_refs"] = [
        _ref_for(candidate.runner_event_contract),
        _ref_for(unscored_prediction),
        _ref_for(candidate.outcome_contract),
    ]
    genome_for_unscored = seal_content_addressed_contract(
        "FailureGenome", genome_for_unscored
    )
    score_uncertainty = _build(
        (
            _copy_candidate(
                candidate,
                prediction_contract=unscored_prediction,
                failure_genome_contract=genome_for_unscored,
            ),
        ),
        policy,
    ).uncertainties[0]
    assert score_uncertainty.reason is FalseMonsterUncertaintyReason.PREDICTION_SCORE_UNAVAILABLE
    assert any(
        ref["target_schema_name"] == EVENT_SCHEMA
        for ref in score_uncertainty.record["source_refs"]
    )

    late_head = candidate.head_output_contract
    late_head.update(
        {
            "created_at": "2026-04-10T20:00:01Z",
            "availability": "UNAVAILABLE_MODEL",
            "output_value": None,
            "reason_code": "model_unavailable",
        }
    )
    with pytest.raises(GenomeError, match="postdates its contemporaneous Prediction"):
        _build((_copy_candidate(candidate, head_output_contract=late_head),), policy)


def test_resolved_outcome_requires_valid_core_measurements() -> None:
    sources = _base_sources()
    policy = _policy(sources)
    candidate = _case(sources, "partially-valid-outcome", failure_type=None)
    incomplete_outcome = candidate.outcome_contract
    missing_fields = {
        "max_high_return",
        "max_high_price",
        "max_high_session",
        "max_high_session_offset",
        "mfe",
    }
    for field_name in missing_fields:
        incomplete_outcome[field_name] = None
    for item in incomplete_outcome["field_validity"]:
        if item["field_name"] in missing_fields:
            item["status"] = "MISSING"
            item["reason_code"] = "source_missing"
    incomplete_outcome = seal_content_addressed_contract("Outcome", incomplete_outcome)
    incomplete_candidate = _copy_candidate(
        candidate,
        outcome_contract=incomplete_outcome,
        runner_event_contract=None,
        failure_genome_contract=None,
    )

    with pytest.raises(GenomeError, match="valid endpoint, extrema, MFE and MAE"):
        _build((incomplete_candidate,), policy)


def test_probability_threshold_is_explicit_frozen_and_inclusive() -> None:
    sources = _base_sources()
    policy = _policy(sources)
    exact = _case(sources, "exact-threshold", probability="0.900000000000")
    below = _case(
        sources,
        "below-threshold",
        probability="0.899999999999",
        failure_type=None,
    )

    queue = _build((exact, below), policy)
    changed = FrozenFalseMonsterPolicy(
        label_definition_ref=policy.label_definition_ref,
        score_manifest_ref=policy.score_manifest_ref,
        probability_head_ref=policy.probability_head_ref,
        minimum_probability="0.910000000000",
        frozen_at=policy.frozen_at,
    )

    assert len(queue.cases) == 1
    assert queue.cases[0].policy_hash == policy.policy_hash
    assert changed.policy_hash != policy.policy_hash
    after_prediction = replace(policy, frozen_at="2026-04-11T20:00:00Z")
    with pytest.raises(GenomeError, match="frozen before prediction"):
        _build((exact,), after_prediction)


def test_annotation_ledger_is_append_only_and_cannot_mutate_case_evidence() -> None:
    sources = _base_sources()
    policy = _policy(sources)
    case = _build((_case(sources, "annotated"),), policy).cases[0]
    authoritative_before = case.canonical_json
    returned_contract = case.contract
    returned_contract["reason_codes"].clear()

    first = append_research_hypothesis_annotation(
        case,
        "Review whether the opening-gap regime explains this miss.",
        created_at="2026-04-21T20:00:00Z",
    )
    second = append_research_hypothesis_annotation(
        case,
        "Compare with the adjacent volatility stratum.",
        created_at="2026-04-22T20:00:00Z",
        ledger=first,
        supporting_refs=(
            ReviewArtifactRef(
                "qc2.integrity_build.EvidenceEvent.v1",
                _uuid7("annotation:evidence"),
                "c" * 64,
            ),
        ),
    )

    assert case.canonical_json == authoritative_before
    assert case.contract["reason_codes"]
    assert len(first.annotations) == 1
    assert len(second.annotations) == 2
    assert second.annotations[1].previous_hash == first.annotations[0].annotation_hash
    assert verify_research_annotation_chain(second)
    assert second.canonical_json
    with pytest.raises(GenomeError, match="cannot predate the preceding ledger entry"):
        append_research_hypothesis_annotation(
            case,
            "This proposal is backdated.",
            created_at="2026-04-21T20:00:00Z",
            ledger=second,
        )
    with pytest.raises(FrozenInstanceError):
        case.category = FalseMonsterCategory.DATA_ERROR  # type: ignore[misc]

    corrupt = replace(second.annotations[0], annotation_hash="0" * 64)
    with pytest.raises(GenomeError, match="hash"):
        type(second)(case_ref=second.case_ref, annotations=(corrupt, second.annotations[1]))


def test_mismatched_head_or_missing_revision_cannot_become_a_case() -> None:
    sources = _base_sources()
    policy = _policy(sources)
    candidate = _case(sources, "wrong-head")
    broken_prediction = candidate.prediction_contract
    broken_prediction["head_output_refs"] = []
    broken_prediction = seal_content_addressed_contract("Prediction", broken_prediction)
    bad_candidate = _copy_candidate(
        candidate,
        prediction_contract=broken_prediction,
    )

    with pytest.raises(GenomeError, match="does not bind the supplied ModelHeadOutput"):
        _build((bad_candidate,), policy)

    data_error_without_revision = _case(
        sources,
        "data-error-without-revision",
        failure_type="DATA_ERROR",
        data_error=True,
    )
    no_revision = _copy_candidate(
        data_error_without_revision,
        prior_outcome_contract=None,
        outcome_revision_contract=None,
    )
    with pytest.raises(GenomeError, match="OutcomeRevision"):
        _build((no_revision,), policy)

