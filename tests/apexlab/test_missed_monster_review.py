from __future__ import annotations

from collections import Counter
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from uuid import UUID

import pytest

from qc2_apexlab import (
    FrozenMissedMonsterPolicy,
    MissedMonsterCandidate,
    MissedMonsterCategory,
    ReviewArtifactRef,
    ReviewCoverage,
    ReviewDisposition,
    RunnerGenomeStore,
    build_missed_monster_review_queue,
)
from test_runner_genome import (
    LABEL_SCHEMA,
    _build_genome,
    _uuid7,
)

EVIDENCE_EVENT_SCHEMA = "qc2.integrity_build.EvidenceEvent.v1"
RUNNER_EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"
RUNNER_GENOME_SCHEMA = "qc2.outcomes_research.RunnerGenome.v1"
OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
PREDICTION_SCHEMA = "qc2.models_prediction.Prediction.v1"
PREDICTION_RUN_SCHEMA = "qc2.models_prediction.PredictionRun.v1"
SCORE_MANIFEST_SCHEMA = "qc2.scientific_definitions.ScoreManifest.v1"
VALIDATION_EPOCH_SCHEMA = "qc2.validation.ValidationEpoch.v1"
CREATED_AT = "2026-04-19T23:00:00Z"


def _ref(schema: str, key: str, *, content_addressed: bool = True) -> ReviewArtifactRef:
    return ReviewArtifactRef(
        target_schema_name=schema,
        target_id=_uuid7(f"missed-monster:{key}"),
        content_hash=sha256(f"missed-monster:{key}".encode()).hexdigest()
        if content_addressed
        else None,
    )


def _policy(event_definition_ref: ReviewArtifactRef) -> FrozenMissedMonsterPolicy:
    return FrozenMissedMonsterPolicy(
        event_definition_ref=event_definition_ref,
        rank_rule_ref=_ref(SCORE_MANIFEST_SCHEMA, "rank-rule"),
        coverage_rule_ref=_ref(VALIDATION_EPOCH_SCHEMA, "coverage-rule"),
        max_included_rank=10,
        frozen_at="2026-04-09T19:00:00Z",
    )


def _candidate(
    policy: FrozenMissedMonsterPolicy,
    key: str,
    *,
    disposition: ReviewDisposition,
    coverage: ReviewCoverage,
    rank: int | None = None,
) -> MissedMonsterCandidate:
    event_ref = _ref(RUNNER_EVENT_SCHEMA, f"{key}:event", content_addressed=False)
    evidence_ref = _ref(EVIDENCE_EVENT_SCHEMA, f"{key}:classification")
    prediction_ref = (
        _ref(PREDICTION_SCHEMA, f"{key}:prediction")
        if disposition is ReviewDisposition.SCORED
        else None
    )
    return MissedMonsterCandidate(
        event_ref=event_ref,
        runner_genome_ref=_ref(RUNNER_GENOME_SCHEMA, f"{key}:genome"),
        event_definition_ref=policy.event_definition_ref,
        outcome_refs=(_ref(OUTCOME_SCHEMA, f"{key}:outcome"),),
        session_id="2026-04-10",
        disposition=disposition,
        coverage=coverage,
        prediction_ref=prediction_ref,
        rank=rank,
        rank_source_refs=(
            (_ref(PREDICTION_RUN_SCHEMA, f"{key}:rank-source"),)
            if disposition is ReviewDisposition.SCORED
            else ()
        ),
        status_source_refs=(evidence_ref,),
        evidence_refs=(evidence_ref,),
    )


def _build(
    candidates: tuple[MissedMonsterCandidate, ...],
    policy: FrozenMissedMonsterPolicy,
    *,
    created_at: str = CREATED_AT,
):
    return build_missed_monster_review_queue(
        candidates,
        policy=policy,
        created_at=created_at,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )


def test_all_five_categories_are_evidence_linked_and_deterministic() -> None:
    label_ref = _ref(LABEL_SCHEMA, "test-label")
    policy = _policy(label_ref)
    candidates = (
        _candidate(
            policy,
            "ranked-low",
            disposition=ReviewDisposition.SCORED,
            coverage=ReviewCoverage.OBSERVED,
            rank=11,
        ),
        _candidate(
            policy,
            "unscorable",
            disposition=ReviewDisposition.UNSCORABLE,
            coverage=ReviewCoverage.OBSERVED,
        ),
        _candidate(
            policy,
            "excluded",
            disposition=ReviewDisposition.EXCLUDED,
            coverage=ReviewCoverage.OBSERVED,
        ),
        _candidate(
            policy,
            "unobserved",
            disposition=ReviewDisposition.PENDING,
            coverage=ReviewCoverage.UNOBSERVED,
        ),
        _candidate(
            policy,
            "missed-session",
            disposition=ReviewDisposition.PENDING,
            coverage=ReviewCoverage.MISSED_SESSION,
        ),
        _candidate(
            policy,
            "inside-primary-k",
            disposition=ReviewDisposition.SCORED,
            coverage=ReviewCoverage.OBSERVED,
            rank=10,
        ),
    )

    queue = _build(candidates, policy)
    repeated = _build(tuple(reversed(candidates)), policy, created_at="2026-04-20T00:00:00Z")

    assert Counter(case.category for case in queue.cases) == Counter(
        {
            MissedMonsterCategory.RANKED_LOW: 1,
            MissedMonsterCategory.UNSCORABLE: 1,
            MissedMonsterCategory.EXCLUDED: 1,
            MissedMonsterCategory.UNOBSERVED: 1,
            MissedMonsterCategory.MISSED_SESSION: 1,
        }
    )
    assert [case.case_id for case in queue.cases] == [
        case.case_id for case in repeated.cases
    ]
    assert queue.queue_hash == repeated.queue_hash
    assert all(UUID(case.case_id).version == 7 for case in queue.cases)

    for case in queue.cases:
        payload = case.contract
        assert payload["review_kind"] == "MISSED_MONSTER"
        assert payload["id"] == case.case_id
        assert case.trigger_policy_hash == policy.policy_hash
        assert f"TRIGGER_POLICY_SHA256:{policy.policy_hash}" in payload["reason_codes"]
        assert "research-only" in case.explanation.lower()
        assert "OFFICIAL_DENOMINATORS_IMMUTABLE" in case.research_annotations
        assert not {"outcome", "rank", "denominator", "official_denominator"} & payload.keys()
        assert all(
            ref["target_id"] in case.explanation
            for ref in payload["evidence_refs"]
        )
        assert all(
            ref["target_id"] in case.explanation for ref in payload["source_refs"]
        )
        research_record = case.research_record
        assert research_record["review_case"] == payload
        assert research_record["category"] == case.category.value

    excluded = next(
        case for case in queue.cases if case.category is MissedMonsterCategory.EXCLUDED
    )
    assert excluded.contract["disposition"] == "EXCLUDED"
    assert excluded.contract["prediction_ref"] is None


def test_major_runner_genome_is_reviewed_without_prediction_or_trade() -> None:
    store = RunnerGenomeStore()
    genome = _build_genome(store, "monster-with-no-prediction")
    genome_payload = genome.contract
    event_payload = store._sources[genome_payload["event_ref"]["target_id"]].payload
    outcome_before = store._sources[
        genome_payload["outcome_refs"][0]["target_id"]
    ].payload
    event_definition_ref = ReviewArtifactRef.from_value(event_payload["label_ref"])
    policy = _policy(event_definition_ref)
    evidence_ref = _ref(EVIDENCE_EVENT_SCHEMA, "missed-schedule-evidence")

    candidate = MissedMonsterCandidate.from_runner_genome(
        genome,
        event_payload,
        session_id="2026-04-10",
        disposition=ReviewDisposition.PENDING,
        coverage=ReviewCoverage.MISSED_SESSION,
        status_source_refs=(evidence_ref,),
        evidence_refs=(evidence_ref,),
    )
    queue = _build((candidate,), policy)

    assert genome_payload["prediction_refs"] == []
    assert "trade" not in genome_payload
    assert len(queue.cases) == 1
    case = queue.cases[0]
    assert case.category is MissedMonsterCategory.MISSED_SESSION
    assert case.contract["prediction_ref"] is None
    assert case.contract["disposition"] == "PENDING"
    assert case.contract["event_ref"]["target_id"] == genome_payload["event_ref"]["target_id"]
    assert any(
        ref["target_schema_name"] == OUTCOME_SCHEMA
        and ref["target_id"] == genome_payload["outcome_refs"][0]["target_id"]
        for ref in case.contract["evidence_refs"]
    )
    assert all("trade" not in ref["target_schema_name"].lower() for ref in case.contract["source_refs"])
    assert store._sources[
        genome_payload["outcome_refs"][0]["target_id"]
    ].payload == outcome_before
    assert candidate.rank is None
    assert case.research_annotations[-1] == "NO_PREDICTION_REFERENCE"
    with pytest.raises(FrozenInstanceError):
        candidate.rank = 1  # type: ignore[misc]


def test_nonmatching_event_definition_is_not_a_trigger_match() -> None:
    policy = _policy(_ref(LABEL_SCHEMA, "frozen-label"))
    candidate = _candidate(
        policy,
        "other-label",
        disposition=ReviewDisposition.SCORED,
        coverage=ReviewCoverage.OBSERVED,
        rank=50,
    )
    candidate = replace(
        candidate,
        event_definition_ref=_ref(LABEL_SCHEMA, "different-label"),
    )

    assert _build((candidate,), policy).cases == ()


def test_candidate_requires_evidence_for_explicit_exclusion() -> None:
    policy = _policy(_ref(LABEL_SCHEMA, "strict-label"))
    with pytest.raises(ValueError):
        MissedMonsterCandidate(
            event_ref=_ref(RUNNER_EVENT_SCHEMA, "invalid:event", content_addressed=False),
            runner_genome_ref=_ref(RUNNER_GENOME_SCHEMA, "invalid:genome"),
            event_definition_ref=policy.event_definition_ref,
            outcome_refs=(_ref(OUTCOME_SCHEMA, "invalid:outcome"),),
            session_id="2026-04-10",
            disposition=ReviewDisposition.EXCLUDED,
            coverage=ReviewCoverage.OBSERVED,
        )
