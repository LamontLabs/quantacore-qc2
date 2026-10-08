from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest

from qc2_contracts.runtime import artifact_inventory_hash
from qc2_apexlab import (
    GenomeDraft,
    RunnerGenomeRecord,
    RunnerGenomeStore,
    contract_artifact,
)
from qc2_apexlab.models import seal_content_addressed_contract
from qc2_temporal_firewall import (
    TemporalArtifact,
    TemporalFirewall,
    TemporalMode,
    TemporalOperation,
    TemporalPermission,
    TemporalQuery,
    TemporalViolation,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = {
    item["contract"]: item["payload"]
    for item in json.loads(
        (ROOT / "packages" / "contracts" / "fixtures" / "v1" / "valid.json").read_text(
            encoding="utf-8"
        )
    )
}

RUNNER_EVENT_SCHEMA = "qc2.outcomes_research.RunnerEvent.v1"
OUTCOME_SCHEMA = "qc2.outcomes_research.Outcome.v1"
MARKET_SNAPSHOT_SCHEMA = "qc2.identity_market.MarketSnapshot.v1"
FEATURE_SNAPSHOT_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
ARTIFACT_MANIFEST_SCHEMA = "qc2.integrity_build.ArtifactManifest.v1"
DAILY_BAR_SCHEMA = "qc2.identity_market.DailyBar.v1"
LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
CALENDAR_SCHEMA = "qc2.time_operation.CalendarManifest.v1"
REGISTRY_SCHEMA = "qc2.scientific_definitions.FeatureRegistry.v1"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"

def _uuid7(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    rand_a = random_bits >> 62
    rand_b = random_bits & ((1 << 62) - 1)
    timestamp_ms = 1_767_225_600_000
    value = (
        (timestamp_ms << 80)
        | (7 << 76)
        | (rand_a << 64)
        | (2 << 62)
        | rand_b
    )
    return str(UUID(int=value))


INSTRUMENT_ID = _uuid7("shared-instrument")
LABEL_ID = _uuid7("shared-label")
LABEL_HASH = "a" * 64
BAR_ID = _uuid7("shared-bar")
CALENDAR_ID = _uuid7("shared-calendar")
REGISTRY_ID = _uuid7("feature-registry")
TEST_EVENT_TIME = "2026-04-10T20:00:00Z"
APRIL_11_CUTOFF = "2026-04-11T23:59:59Z"
APRIL_15_CUTOFF = "2026-04-15T23:59:59Z"
TODAY = "2026-10-08T14:00:00Z"


def _ref(schema_name: str, artifact_id: str, content_hash: str | None = None) -> dict[str, str]:
    result = {"target_schema_name": schema_name, "target_id": artifact_id}
    if content_hash is not None:
        result["content_hash"] = content_hash
    return result


def _stub(
    artifact_id: str,
    artifact_kind: str,
    *,
    evidence_class: str,
    actual_at: str,
    historical_available_at: str | None = None,
    historical_learning_at: str | None = None,
) -> TemporalArtifact:
    return TemporalArtifact(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        revision_id=f"fixture:{artifact_id}",
        content_hash=hashlib.sha256(artifact_id.encode("utf-8")).hexdigest(),
        created_at=actual_at,
        known_at=actual_at,
        evidence_class=evidence_class,
        historical_assumed_available_at=historical_available_at,
        historical_assumed_available_for_learning_at=historical_learning_at,
    )


def _historical_times() -> tuple[str, str]:
    return "2026-04-09T20:00:00Z", "2026-04-09T20:00:00Z"


def _add_temporal_stubs(
    store: RunnerGenomeStore,
    *,
    evidence_class: str,
    actual_at: str,
) -> None:
    dependencies = (
        (BAR_ID, DAILY_BAR_SCHEMA, "2026-04-09T20:00:00Z"),
        (LABEL_ID, LABEL_SCHEMA, "2026-04-09T20:00:00Z"),
        (CALENDAR_ID, CALENDAR_SCHEMA, "2026-04-09T20:00:00Z"),
    )
    for artifact_id, artifact_kind, historic_time in dependencies:
        historical_available, historical_learning = (
            _historical_times()
            if evidence_class == "HISTORICAL_RECONSTRUCTED"
            else (None, None)
        )
        if evidence_class != "HISTORICAL_RECONSTRUCTED":
            historical_available = None
            historical_learning = None
        store.add_temporal_dependency(
            _stub(
                artifact_id,
                artifact_kind,
                evidence_class=evidence_class,
                actual_at=actual_at,
                historical_available_at=historical_available,
                historical_learning_at=historical_learning,
            )
        )


def _outcome_contract(
    key: str,
    *,
    evidence_class: str,
    created_at: str,
    available_for_learning_at: str,
) -> dict[str, object]:
    payload = deepcopy(FIXTURES["Outcome"])
    daily_bar_ref = _ref(DAILY_BAR_SCHEMA, BAR_ID)
    payload.update(
        {
            "id": _uuid7(f"{key}:outcome"),
            "created_at": created_at,
            "evidence_class": evidence_class,
            "environment_namespace": "test",
            "source_refs": [daily_bar_ref],
            "instrument_ref": _ref(INSTRUMENT_SCHEMA, INSTRUMENT_ID),
            "session_id": "2026-04-10",
            "label_ref": _ref(LABEL_SCHEMA, LABEL_ID, LABEL_HASH),
            "reference_bar_ref": daily_bar_ref,
            "outcome_state": "RESOLVED",
            "endpoint_return": "0.030000000000",
            "max_high_return": "0.050000000000",
            "min_low_return": "-0.010000000000",
            "mfe": "0.050000000000",
            "mae": "-0.010000000000",
            "max_high_price": "105",
            "max_high_session": "2026-04-15",
            "max_high_session_offset": 5,
            "min_low_price": "99",
            "min_low_session": "2026-04-11",
            "min_low_session_offset": 1,
            "available_for_learning_at": available_for_learning_at,
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
    return seal_content_addressed_contract("Outcome", payload)


def _snapshot_contract(
    key: str, *, evidence_class: str, created_at: str
) -> dict[str, object]:
    payload = deepcopy(FIXTURES["MarketSnapshot"])
    payload.update(
        {
            "id": _uuid7(f"{key}:snapshot"),
            "created_at": created_at,
            "evidence_class": evidence_class,
            "environment_namespace": "test",
            "session_id": "2026-04-09",
            "decision_cutoff": "2026-04-09T20:00:00Z",
            "sealed_at": created_at,
            "dependency_refs": [_ref(CALENDAR_SCHEMA, CALENDAR_ID, LABEL_HASH)],
        }
    )
    return payload


def _event_contract(
    key: str,
    *,
    evidence_class: str,
    created_at: str,
    outcome: dict[str, object],
) -> dict[str, object]:
    payload = deepcopy(FIXTURES["RunnerEvent"])
    payload.update(
        {
            "id": _uuid7(f"{key}:event"),
            "created_at": created_at,
            "evidence_class": evidence_class,
            "environment_namespace": "test",
            "instrument_ref": _ref(INSTRUMENT_SCHEMA, INSTRUMENT_ID),
            "event_type": "EXPANSION_RUNNER",
            "start_session": "2026-04-10",
            "end_session": "2026-04-15",
            "label_ref": outcome["label_ref"],
            "outcome_ref": _ref(
                OUTCOME_SCHEMA, outcome["id"], outcome["content_hash"]
            ),
            "detected_at": TEST_EVENT_TIME,
            "source_refs": [],
            "evidence_refs": [],
        }
    )
    return payload


def _build_genome(
    store: RunnerGenomeStore,
    key: str,
    *,
    historical: bool = False,
) -> RunnerGenomeRecord:
    evidence_class = (
        "HISTORICAL_RECONSTRUCTED" if historical else "SYNTHETIC_FIXTURE"
    )
    source_actual_at = TODAY if historical else "2026-04-09T20:00:00Z"
    outcome_created_at = "2026-10-08T15:00:00Z" if historical else "2026-04-15T16:00:00Z"
    outcome_learning_at = "2026-10-08T15:10:00Z" if historical else "2026-04-15T16:10:00Z"
    event_created_at = "2026-10-08T15:20:00Z" if historical else "2026-04-15T16:20:00Z"
    genome_created_at = "2026-10-08T16:00:00Z" if historical else "2026-04-16T12:00:00Z"
    review_completed_at = "2026-10-08T15:50:00Z" if historical else "2026-04-16T11:00:00Z"
    outcome = _outcome_contract(
        key,
        evidence_class=evidence_class,
        created_at=outcome_created_at,
        available_for_learning_at=outcome_learning_at,
    )
    snapshot = _snapshot_contract(
        key,
        evidence_class=evidence_class,
        created_at=source_actual_at,
    )
    event = _event_contract(
        key,
        evidence_class=evidence_class,
        created_at=event_created_at,
        outcome=outcome,
    )
    _add_temporal_stubs(
        store,
        evidence_class=evidence_class,
        actual_at=source_actual_at,
    )
    for payload, known_at, hist_available, hist_learning in (
        (
            outcome,
            outcome_created_at,
            "2026-04-15T16:10:00Z" if historical else None,
            "2026-04-15T16:10:00Z" if historical else None,
        ),
        (
            snapshot,
            source_actual_at,
            "2026-04-09T20:00:00Z" if historical else None,
            "2026-04-09T20:00:00Z" if historical else None,
        ),
        (
            event,
            event_created_at,
            "2026-04-15T16:10:00Z" if historical else None,
            "2026-04-15T16:10:00Z" if historical else None,
        ),
    ):
        store.add_source(
            contract_artifact(
                payload,
                known_at=known_at,
                historical_assumed_available_at=hist_available,
                historical_assumed_available_for_learning_at=hist_learning,
            )
        )
    return store.create_runner_genome(
        GenomeDraft(
            event_id=event["id"],
            pre_event_snapshot_ids=(snapshot["id"],),
            prediction_ids=(),
            outcome_ids=(outcome["id"],),
            provenance_ids=(),
            event_time=TEST_EVENT_TIME,
            created_at=genome_created_at,
            review_completed_at=review_completed_at,
            curation_version=1,
            historical_assumed_available_at=(
                "2026-04-15T16:10:00Z" if historical else None
            ),
            historical_assumed_available_for_learning_at=(
                "2026-04-15T16:10:00Z" if historical else None
            ),
        )
    )


def _add_feature_test_stubs(
    artifacts: list[TemporalArtifact],
    *,
    actual_at: str,
) -> None:
    for artifact_id, artifact_kind in (
        (LABEL_ID, LABEL_SCHEMA),
        (BAR_ID, DAILY_BAR_SCHEMA),
        (REGISTRY_ID, REGISTRY_SCHEMA),
    ):
        artifacts.append(
            _stub(
                artifact_id,
                artifact_kind,
                evidence_class="SYNTHETIC_FIXTURE",
                actual_at=actual_at,
            )
        )


def test_april_15_success_is_not_visible_to_april_11_decision() -> None:
    store = RunnerGenomeStore()
    early_index = store.build_memory_index(
        cutoff=APRIL_11_CUTOFF,
        created_at=TODAY,
        evidence_class="HISTORICAL_RECONSTRUCTED",
        environment_namespace="test",
        mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
        historical_assumed_available_at=APRIL_11_CUTOFF,
        historical_assumed_available_for_learning_at=APRIL_11_CUTOFF,
    )
    early_lookup_before = store.lookup_memory_index(
        early_index.contract["id"],
        cutoff=APRIL_11_CUTOFF,
        mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
    )

    genome = _build_genome(store, "april-success", historical=True)
    early_lookup_after = store.lookup_memory_index(
        early_index.contract["id"],
        cutoff=APRIL_11_CUTOFF,
        mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
    )
    assert early_lookup_after.members == ()
    assert early_lookup_after.eligibility_proof_hash == early_lookup_before.eligibility_proof_hash
    assert early_lookup_after.catalog_revision == early_lookup_before.catalog_revision
    with pytest.raises(TemporalViolation):
        store.lookup_genome(
            genome.contract["id"],
            cutoff=APRIL_11_CUTOFF,
            mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
        )

    april_15_index = store.build_memory_index(
        cutoff=APRIL_15_CUTOFF,
        created_at="2026-10-08T17:00:00Z",
        evidence_class="HISTORICAL_RECONSTRUCTED",
        environment_namespace="test",
        mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
        historical_assumed_available_at=APRIL_15_CUTOFF,
        historical_assumed_available_for_learning_at=APRIL_15_CUTOFF,
    )
    april_15_lookup = store.lookup_memory_index(
        april_15_index.contract["id"],
        cutoff=APRIL_15_CUTOFF,
        mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
    )
    assert [member.contract["id"] for member in april_15_lookup.members] == [
        genome.contract["id"]
    ]
    assert genome.prediction_capture_status == "ABSENT"
    assert genome.contract["prediction_refs"] == []
    assert genome.temporal_artifact.known_at == genome.contract["created_at"]
    assert genome.contract["available_for_learning_at"] == "2026-10-08T16:00:00Z"
    assert (
        genome.temporal_artifact.historical_assumed_available_for_learning_at
        == "2026-04-15T16:10:00Z"
    )


def test_changed_index_membership_changes_hash_and_replay_dependency() -> None:
    cutoff = "2026-04-20T23:59:59Z"
    created_at = "2026-04-20T20:00:00Z"

    one_member_store = RunnerGenomeStore()
    _build_genome(one_member_store, "index-member-a")
    one_member_index = one_member_store.build_memory_index(
        cutoff=cutoff,
        created_at=created_at,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )

    two_member_store = RunnerGenomeStore()
    _build_genome(two_member_store, "index-member-a")
    _build_genome(two_member_store, "index-member-b")
    two_member_index = two_member_store.build_memory_index(
        cutoff=cutoff,
        created_at=created_at,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )

    assert len(one_member_index.contract["member_refs"]) == 1
    assert len(two_member_index.contract["member_refs"]) == 2
    assert (
        one_member_index.contract["member_inventory_hash"]
        != two_member_index.contract["member_inventory_hash"]
    )
    assert one_member_index.contract["content_hash"] != two_member_index.contract["content_hash"]
    assert one_member_index.replay_dependency_ref != two_member_index.replay_dependency_ref
    one_member_lookup = one_member_store.lookup_memory_index(
        one_member_index.contract["id"], cutoff=cutoff
    )
    two_member_lookup = two_member_store.lookup_memory_index(
        two_member_index.contract["id"], cutoff=cutoff
    )
    assert len(one_member_lookup.members) == 1
    assert len(two_member_lookup.members) == 2


def test_outcome_derived_embedding_is_rejected_from_earlier_feature_view() -> None:
    outcome = _outcome_contract(
        "future-embedding-outcome",
        evidence_class="SYNTHETIC_FIXTURE",
        created_at="2026-04-15T16:00:00Z",
        available_for_learning_at="2026-04-15T16:10:00Z",
    )
    outcome_artifact = contract_artifact(
        outcome,
        known_at="2026-04-15T16:00:00Z",
    )
    manifest = deepcopy(FIXTURES["ArtifactManifest"])
    manifest.update(
        {
            "id": _uuid7("outcome-derived-embedding"),
            "created_at": "2026-04-10T19:00:00Z",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "source_refs": [
                _ref(OUTCOME_SCHEMA, outcome["id"], outcome["content_hash"])
            ],
        }
    )
    manifest["inventory_hash"] = artifact_inventory_hash(manifest["files"])
    manifest = seal_content_addressed_contract("ArtifactManifest", manifest)
    manifest_artifact = contract_artifact(
        manifest,
        known_at="2026-04-10T19:00:00Z",
    )
    feature = deepcopy(FIXTURES["FeatureSnapshot"])
    feature.update(
        {
            "id": _uuid7("early-feature-snapshot"),
            "created_at": "2026-04-10T20:00:00Z",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "session_id": "2026-04-10",
            "registry_ref": _ref(REGISTRY_SCHEMA, REGISTRY_ID, LABEL_HASH),
            "transform_refs": [
                _ref(
                    ARTIFACT_MANIFEST_SCHEMA,
                    manifest["id"],
                    manifest["content_hash"],
                )
            ],
            "decision_cutoff": "2026-04-11T20:00:00Z",
        }
    )
    feature = seal_content_addressed_contract("FeatureSnapshot", feature)
    feature_artifact = contract_artifact(
        feature,
        known_at="2026-04-10T20:00:00Z",
    )
    artifacts = [feature_artifact, manifest_artifact, outcome_artifact]
    _add_feature_test_stubs(artifacts, actual_at="2026-04-09T20:00:00Z")

    firewall = TemporalFirewall(
        artifacts,
        catalog_revision=hashlib.sha256(b"apexlab-test-catalog").hexdigest(),
    )
    with pytest.raises(TemporalViolation, match="not proven available"):
        firewall.query(
            TemporalQuery(
                cutoff="2026-04-11T20:00:00Z",
                mode=TemporalMode.FORWARD,
                operation=TemporalOperation.QUERY,
                artifact_ids=(feature["id"],),
            ),
            TemporalPermission(
                operations=frozenset({TemporalOperation.QUERY}),
                artifact_kinds=frozenset({FEATURE_SNAPSHOT_SCHEMA}),
            ),
        )

    store = RunnerGenomeStore()
    store.add_temporal_dependency(
        _stub(
            BAR_ID,
            DAILY_BAR_SCHEMA,
            evidence_class="SYNTHETIC_FIXTURE",
            actual_at="2026-04-09T20:00:00Z",
        )
    )
    store.add_temporal_dependency(
        _stub(
            LABEL_ID,
            LABEL_SCHEMA,
            evidence_class="SYNTHETIC_FIXTURE",
            actual_at="2026-04-09T20:00:00Z",
        )
    )
    store.add_source(outcome_artifact)
    store.add_source(manifest_artifact)
    index = store.build_memory_index(
        cutoff="2026-04-11T23:59:59Z",
        created_at="2026-04-10T21:00:00Z",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
        embedding_artifact_id=manifest["id"],
    )
    with pytest.raises(TemporalViolation, match="not proven available"):
        store.lookup_memory_index(
            index.contract["id"],
            cutoff="2026-04-11T23:59:59Z",
        )
