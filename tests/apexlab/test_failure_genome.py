from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from qc2_apexlab import (
    FailureCategory,
    FailureGenomeDraft,
    FailureGenomeStore,
    contract_artifact,
    failure_category_for_type,
)
from qc2_apexlab.models import seal_content_addressed_contract
from qc2_temporal_firewall import TemporalViolation
from test_runner_genome import (
    APRIL_11_CUTOFF,
    FIXTURES,
    TEST_EVENT_TIME,
    _add_temporal_stubs,
    _event_contract,
    _outcome_contract,
    _ref,
    _snapshot_contract,
    _uuid7,
)

EVIDENCE_EVENT_SCHEMA = "qc2.integrity_build.EvidenceEvent.v1"
OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
APRIL_09 = "2026-04-09T20:00:00Z"
APRIL_16 = "2026-04-16T20:00:00Z"
APRIL_17 = "2026-04-17T20:00:00Z"
APRIL_18 = "2026-04-18T20:00:00Z"
APRIL_19_CUTOFF = "2026-04-19T23:59:59Z"


def _evidence_event(key: str, *, created_at: str) -> dict[str, Any]:
    payload = deepcopy(FIXTURES["EvidenceEvent"])
    payload.update(
        {
            "id": _uuid7(f"{key}:evidence"),
            "created_at": created_at,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "event_type": "failure_genome_adjudication",
            "dependency_refs": [],
        }
    )
    return seal_content_addressed_contract("EvidenceEvent", payload)


def _add_contract(store: FailureGenomeStore, payload: dict[str, Any]) -> None:
    store.add_source(contract_artifact(payload, known_at=payload["created_at"]))


def _add_failure_case(
    store: FailureGenomeStore,
    key: str,
    *,
    event_type: str = "FAILURE",
    unresolved: bool = False,
    created_at: str = APRIL_16,
) -> dict[str, Any]:
    _add_temporal_stubs(
        store,
        evidence_class="SYNTHETIC_FIXTURE",
        actual_at=APRIL_09,
    )
    if unresolved:
        daily_bar_ref = _ref(
            "qc2.identity_market.DailyBar.v1",
            _uuid7("shared-bar"),
        )
        outcome = deepcopy(FIXTURES["Outcome"])
        outcome.update(
            {
                "id": _uuid7(f"{key}:outcome"),
                "created_at": created_at,
                "evidence_class": "SYNTHETIC_FIXTURE",
                "environment_namespace": "test",
                "source_refs": [daily_bar_ref],
                "instrument_ref": _ref(
                    "qc2.identity_market.Instrument.v1",
                    _uuid7("shared-instrument"),
                ),
                "session_id": "2026-04-10",
                "label_ref": _ref(
                    "qc2.scientific_definitions.LabelDefinition.v1",
                    _uuid7("shared-label"),
                    "a" * 64,
                ),
                "reference_bar_ref": daily_bar_ref,
                "outcome_state": "UNRESOLVED_DATA",
                "reason_codes": ["awaiting_resolution"],
                "available_for_learning_at": None,
            }
        )
        outcome = seal_content_addressed_contract("Outcome", outcome)
    else:
        outcome = _outcome_contract(
            key,
            evidence_class="SYNTHETIC_FIXTURE",
            created_at=created_at,
            available_for_learning_at=created_at,
        )

    snapshot = _snapshot_contract(
        key,
        evidence_class="SYNTHETIC_FIXTURE",
        created_at=APRIL_09,
    )
    evidence = _evidence_event(f"{key}:adjudication", created_at=created_at)
    event = _event_contract(
        key,
        evidence_class="SYNTHETIC_FIXTURE",
        created_at=created_at,
        outcome=outcome,
    )
    event["event_type"] = event_type
    event["detected_at"] = created_at
    event["evidence_refs"] = [
        _ref(EVIDENCE_EVENT_SCHEMA, evidence["id"], evidence["content_hash"])
    ]

    for payload in (outcome, snapshot, evidence, event):
        _add_contract(store, payload)
    return {
        "event": event,
        "outcome": outcome,
        "snapshot": snapshot,
        "evidence": evidence,
    }


def _draft(case: dict[str, Any], *, failure_type: str, created_at: str = APRIL_16) -> FailureGenomeDraft:
    return FailureGenomeDraft(
        failure_type=failure_type,
        event_id=case["event"]["id"],
        pre_event_snapshot_ids=(case["snapshot"]["id"],),
        prediction_ids=(),
        outcome_ids=(case["outcome"]["id"],),
        provenance_ids=(case["evidence"]["id"],),
        event_time=TEST_EVENT_TIME,
        created_at=created_at,
        review_completed_at=created_at,
        curation_version=1,
    )


@pytest.mark.parametrize(
    ("failure_type", "category"),
    [
        ("FALSE_MONSTER", FailureCategory.NON_EVENT),
        ("COLLAPSE", FailureCategory.DOWNSIDE),
        ("DATA_ERROR", FailureCategory.DATA_ERROR),
        ("TIMING_MISS", FailureCategory.TIMING_MISS),
        ("MISSED_RUNNER", FailureCategory.MISSED_RUNNER),
    ],
)
def test_failure_types_map_to_distinct_curated_categories(
    failure_type: str, category: FailureCategory
) -> None:
    assert failure_category_for_type(failure_type) is category


def test_unresolved_outcome_cannot_create_negative_training_memory() -> None:
    store = FailureGenomeStore()
    case = _add_failure_case(store, "unresolved", unresolved=True)

    with pytest.raises(ValueError, match="fully resolved outcomes"):
        store.create_failure_genome(_draft(case, failure_type="FALSE_MONSTER"))

    assert store._failures == {}


def test_future_failure_and_index_membership_are_blocked() -> None:
    store = FailureGenomeStore()
    case = _add_failure_case(store, "future")
    genome = store.create_failure_genome(_draft(case, failure_type="COLLAPSE"))
    index = store.build_failure_index(
        cutoff=APRIL_11_CUTOFF,
        created_at=APRIL_11_CUTOFF,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )

    assert index.contract["index_kind"] == "FAILURE"
    assert index.contract["member_refs"] == []
    with pytest.raises(TemporalViolation):
        store.lookup_failure_genome(genome.contract["id"], cutoff=APRIL_11_CUTOFF)
    lookup = store.lookup_failure_index(index.contract["id"], cutoff=APRIL_11_CUTOFF)
    assert lookup.members == ()
    assert lookup.eligibility_proof_hash


def test_corrections_append_versions_and_preserve_old_index_membership() -> None:
    store = FailureGenomeStore()
    case = _add_failure_case(store, "correction")
    original = store.create_failure_genome(_draft(case, failure_type="FALSE_MONSTER"))
    original_json = original.canonical_json
    original_ref = original.replay_dependency_ref
    first_index = store.build_failure_index(
        cutoff=APRIL_17,
        created_at=APRIL_17,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )

    corrected_evidence = _evidence_event("correction:second-review", created_at=APRIL_18)
    _add_contract(store, corrected_evidence)
    correction = FailureGenomeDraft(
        failure_type="COLLAPSE",
        event_id=case["event"]["id"],
        pre_event_snapshot_ids=(case["snapshot"]["id"],),
        prediction_ids=(),
        outcome_ids=(case["outcome"]["id"],),
        provenance_ids=(corrected_evidence["id"],),
        event_time=TEST_EVENT_TIME,
        created_at=APRIL_18,
        review_completed_at=APRIL_18,
        curation_version=2,
    )
    revised = store.append_correction(original.contract["id"], correction)
    assert original.canonical_json == original_json
    assert revised.contract["id"] != original.contract["id"]
    assert revised.contract["curation_version"] == 2
    assert original_ref in revised.contract["source_refs"]

    old_lookup = store.lookup_failure_index(first_index.contract["id"], cutoff=APRIL_17)
    assert [member.contract["id"] for member in old_lookup.members] == [
        original.contract["id"]
    ]

    second_index = store.build_failure_index(
        cutoff=APRIL_19_CUTOFF,
        created_at=APRIL_19_CUTOFF,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    new_lookup = store.lookup_failure_index(
        second_index.contract["id"],
        cutoff=APRIL_19_CUTOFF,
    )
    assert [member.contract["id"] for member in new_lookup.members] == [
        revised.contract["id"]
    ]
    assert len(store._failures) == 2


def test_missed_runner_keeps_positive_truth_out_of_negative_examples() -> None:
    store = FailureGenomeStore()
    case = _add_failure_case(store, "missed-runner", event_type="SESSION_MONSTER")
    genome = store.create_failure_genome(_draft(case, failure_type="MISSED_RUNNER"))
    lookup = store.lookup_failure_genome(genome.contract["id"], cutoff=APRIL_17)

    assert genome.category is FailureCategory.MISSED_RUNNER
    assert lookup.is_negative_training_example is False


def test_data_error_requires_a_resolved_outcome_revision() -> None:
    store = FailureGenomeStore()
    case = _add_failure_case(store, "data-error")

    with pytest.raises(ValueError, match="DATA_ERROR requires a linked OutcomeRevision"):
        store.create_failure_genome(_draft(case, failure_type="DATA_ERROR"))


def test_data_error_with_revision_is_diagnostic_not_a_negative_example() -> None:
    store = FailureGenomeStore()
    case = _add_failure_case(store, "data-error-valid")
    replacement = _outcome_contract(
        "data-error-valid:replacement",
        evidence_class="SYNTHETIC_FIXTURE",
        created_at=APRIL_18,
        available_for_learning_at=APRIL_18,
    )
    evidence = _evidence_event("data-error-valid:revision-review", created_at=APRIL_18)
    policy = deepcopy(FIXTURES["ConfigurationManifest"])
    policy.update(
        {
            "id": _uuid7("data-error-valid:policy"),
            "created_at": APRIL_09,
            "effective_from": "2026-04-09",
            "environment_namespace": "test",
            "evidence_class": "SYNTHETIC_FIXTURE",
        }
    )
    policy = seal_content_addressed_contract("ConfigurationManifest", policy)

    revision = deepcopy(FIXTURES["OutcomeRevision"])
    revision.update(
        {
            "id": _uuid7("data-error-valid:revision"),
            "created_at": APRIL_18,
            "discovered_at": APRIL_18,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [
                _ref(EVIDENCE_EVENT_SCHEMA, evidence["id"], evidence["content_hash"])
            ],
            "prior_outcome_ref": _ref(
                OUTCOME_SCHEMA,
                case["outcome"]["id"],
                case["outcome"]["content_hash"],
            ),
            "replacement_outcome_ref": _ref(
                OUTCOME_SCHEMA,
                replacement["id"],
                replacement["content_hash"],
            ),
            "revision_reason": "corrected_source_data",
            "correction_policy_ref": _ref(
                "qc2.integrity_build.ConfigurationManifest.v1",
                policy["id"],
                policy["content_hash"],
            ),
        }
    )
    for payload in (replacement, evidence, policy, revision):
        _add_contract(store, payload)

    draft = FailureGenomeDraft(
        failure_type="DATA_ERROR",
        event_id=case["event"]["id"],
        pre_event_snapshot_ids=(case["snapshot"]["id"],),
        prediction_ids=(),
        outcome_ids=(replacement["id"],),
        provenance_ids=(evidence["id"], revision["id"]),
        event_time=TEST_EVENT_TIME,
        created_at=APRIL_18,
        review_completed_at=APRIL_18,
        curation_version=1,
    )
    genome = store.create_failure_genome(draft)
    with pytest.raises(TemporalViolation):
        store.lookup_failure_genome(genome.contract["id"], cutoff=APRIL_17)
    lookup = store.lookup_failure_genome(genome.contract["id"], cutoff=APRIL_19_CUTOFF)
    assert lookup.is_negative_training_example is False

    early_index = store.build_failure_index(
        cutoff=APRIL_17,
        created_at=APRIL_17,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    assert early_index.contract["member_refs"] == []
    index = store.build_failure_index(
        cutoff=APRIL_19_CUTOFF,
        created_at=APRIL_19_CUTOFF,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    index_lookup = store.lookup_failure_index(
        index.contract["id"],
        cutoff=APRIL_19_CUTOFF,
    )
    assert [member.contract["id"] for member in index_lookup.members] == [
        genome.contract["id"]
    ]
    assert index_lookup.negative_training_members == ()
