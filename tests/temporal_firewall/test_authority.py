from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from qc2_temporal_firewall import (
    TemporalArtifact,
    TemporalFirewall,
    TemporalMode,
    TemporalOperation,
    TemporalPermission,
    TemporalQuery,
    TemporalResultCache,
    TemporalViolation,
)

T0 = "2026-01-01T00:00:00Z"
T1 = "2026-01-02T00:00:00Z"
T2 = "2026-01-03T00:00:00Z"
T3 = "2026-01-04T00:00:00Z"
T4 = "2026-01-05T00:00:00Z"
T5 = "2026-01-06T00:00:00Z"


def artifact(
    artifact_id: str,
    kind: str,
    *,
    created_at: str = T0,
    known_at: str = T0,
    evidence_class: str = "FORWARD_OPERATIONAL",
    **fields: object,
) -> TemporalArtifact:
    return TemporalArtifact(
        artifact_id=artifact_id,
        artifact_kind=kind,
        revision_id="revision-1",
        content_hash=hashlib.sha256(artifact_id.encode("utf-8")).hexdigest(),
        created_at=created_at,
        known_at=known_at,
        evidence_class=evidence_class,
        **fields,
    )


def query(
    artifact_id: str,
    *,
    cutoff: str = T4,
    mode: TemporalMode = TemporalMode.FORWARD,
    operation: TemporalOperation = TemporalOperation.QUERY,
    training_cutoff: str | None = None,
) -> TemporalQuery:
    return TemporalQuery(
        cutoff=cutoff,
        mode=mode,
        operation=operation,
        artifact_ids=(artifact_id,),
        training_cutoff=training_cutoff,
    )


def permission(
    *kinds: str,
    operations: tuple[TemporalOperation, ...] = (
        TemporalOperation.QUERY,
        TemporalOperation.EXPORT,
    ),
    reconstructed: bool = False,
) -> TemporalPermission:
    return TemporalPermission(
        operations=frozenset(operations),
        artifact_kinds=frozenset(kinds),
        allow_historical_reconstructed=reconstructed,
    )


@pytest.mark.parametrize(
    "kind",
    (
        "DailyBar",
        "Label",
        "Genome",
        "Embedding",
        "Normalizer",
        "Calibrator",
    ),
)
def test_forward_query_blocks_future_bars_labels_and_learned_artifacts(kind: str) -> None:
    row = artifact(f"future-{kind}", kind, known_at=T2)
    firewall = TemporalFirewall([row], catalog_revision="catalog-1")

    with pytest.raises(TemporalViolation) as error:
        firewall.query(
            query(row.artifact_id, cutoff=T1),
            permission(kind),
        )

    assert error.value.reason_code == "artifact_unavailable_at_cutoff"


def test_query_never_exposes_protected_outcomes_and_future_learning_labels() -> None:
    outcome = artifact("outcome", "Outcome", known_at=T0)
    immature_label = artifact(
        "immature-label",
        "Label",
        known_at=T0,
        available_for_learning_at=T2,
    )
    firewall = TemporalFirewall([outcome, immature_label], catalog_revision="catalog-1")

    with pytest.raises(TemporalViolation):
        firewall.query(query("outcome"), permission("Outcome"))

    with pytest.raises(TemporalViolation):
        firewall.export(
            query(
                "immature-label",
                cutoff=T4,
                operation=TemporalOperation.EXPORT,
                training_cutoff=T1,
            ),
            permission("Label"),
        )


def test_future_metadata_alias_and_unavailable_alias_target_are_blocked() -> None:
    target = artifact("target", "DailyBar")
    future_alias = artifact(
        "future-alias",
        "MetadataAlias",
        known_at=T2,
        logical_key="latest-bar",
        alias_target=target.artifact_id,
    )
    firewall = TemporalFirewall([target, future_alias], catalog_revision="catalog-1")

    with pytest.raises(TemporalViolation) as error:
        firewall.query(
            TemporalQuery(
                cutoff=T1,
                mode=TemporalMode.FORWARD,
                operation=TemporalOperation.QUERY,
                logical_keys=("latest-bar",),
            ),
            permission("MetadataAlias", "DailyBar"),
        )
    assert error.value.reason_code == "artifact_unavailable_at_cutoff"

    current_alias = replace(future_alias, known_at=T0, created_at=T0)
    future_target = replace(target, known_at=T2)
    firewall = TemporalFirewall(
        [future_target, current_alias],
        catalog_revision="catalog-2",
    )
    with pytest.raises(TemporalViolation) as error:
        firewall.query(
            TemporalQuery(
                cutoff=T1,
                mode=TemporalMode.FORWARD,
                operation=TemporalOperation.QUERY,
                logical_keys=("latest-bar",),
            ),
            permission("MetadataAlias", "DailyBar"),
        )
    assert error.value.reason_code == "alias_target_unavailable_at_cutoff"


def test_reconstructed_export_keeps_actual_creation_and_receipt_times() -> None:
    row = artifact(
        "reconstructed-bar",
        "DailyBar",
        created_at=T5,
        known_at=T5,
        observed_at=T5,
        ingested_at=T5,
        event_time=T0,
        evidence_class="HISTORICAL_RECONSTRUCTED",
        historical_assumed_available_at=T0,
        payload={"close": 10.0},
    )
    firewall = TemporalFirewall([row], catalog_revision="catalog-1")

    result = firewall.export(
        query(
            row.artifact_id,
            cutoff=T1,
            mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
            operation=TemporalOperation.EXPORT,
            training_cutoff=T1,
        ),
        permission("DailyBar", reconstructed=True),
    )

    assert result.view.evidence_class == "HISTORICAL_RECONSTRUCTED"
    assert result.view.artifacts[0].created_at == T5
    assert result.view.artifacts[0].known_at == T5
    assert result.view.artifacts[0].observed_at == T5
    assert result.view.artifacts[0].ingested_at == T5
    assert b'"created_at":"2026-01-06T00:00:00Z"' in result.payload
    assert b'"known_at":"2026-01-06T00:00:00Z"' in result.payload
    assert b'"dependency_closure":{"reconstructed-bar":["reconstructed-bar"]}' in result.payload


def test_historical_mode_requires_reconstructed_evidence_and_explicit_assumption() -> None:
    operational = artifact(
        "operational",
        "DailyBar",
        known_at=T0,
        historical_assumed_available_at=T0,
    )
    reconstructed_without_assumption = artifact(
        "no-assumption",
        "DailyBar",
        created_at=T5,
        known_at=T5,
        evidence_class="HISTORICAL_RECONSTRUCTED",
    )
    firewall = TemporalFirewall(
        [operational, reconstructed_without_assumption],
        catalog_revision="catalog-1",
    )

    for artifact_id in ("operational", "no-assumption"):
        with pytest.raises(TemporalViolation):
            firewall.query(
                query(
                    artifact_id,
                    cutoff=T1,
                    mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
                ),
                permission("DailyBar", reconstructed=True),
            )

    with pytest.raises(TemporalViolation):
        firewall.query(
            query("no-assumption", cutoff=T1),
            permission("DailyBar"),
        )

    actual_forward = firewall.query(
        query("operational", cutoff=T1),
        permission("DailyBar"),
    )
    assert actual_forward.artifacts[0].known_at == T0


def test_reconstructed_learning_uses_separate_simulated_maturity_time() -> None:
    label = artifact(
        "reconstructed-label",
        "Label",
        created_at=T5,
        known_at=T5,
        evidence_class="HISTORICAL_RECONSTRUCTED",
        historical_assumed_available_at=T0,
        historical_assumed_available_for_learning_at=T2,
    )
    firewall = TemporalFirewall([label], catalog_revision="catalog-1")
    grant = permission("Label", reconstructed=True)

    with pytest.raises(TemporalViolation):
        firewall.export(
            query(
                "reconstructed-label",
                cutoff=T4,
                mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
                operation=TemporalOperation.EXPORT,
                training_cutoff=T1,
            ),
            grant,
        )

    accepted = firewall.export(
        query(
            "reconstructed-label",
            cutoff=T4,
            mode=TemporalMode.HISTORICAL_RECONSTRUCTED,
            operation=TemporalOperation.EXPORT,
            training_cutoff=T2,
        ),
        grant,
    )
    assert accepted.view.artifacts[0].known_at == T5
    assert accepted.view.artifacts[0].historical_assumed_available_for_learning_at == T2


def test_from_contract_never_uses_provider_asof_as_known_at() -> None:
    contract = {
        "id": "contract-1",
        "schema_name": "qc2.identity_market.DailyBar.v1",
        "created_at": T0,
        "asof": T0,
        "evidence_class": "FORWARD_OPERATIONAL",
    }

    with pytest.raises(TemporalViolation) as error:
        TemporalArtifact.from_contract(contract)
    assert error.value.reason_code == "known_at_required"

    row = TemporalArtifact.from_contract(contract, known_at=T1)
    assert row.known_at == T1
    assert row.content_hash == hashlib.sha256(
        b'{"asof":"2026-01-01T00:00:00Z","created_at":"2026-01-01T00:00:00Z",'
        b'"evidence_class":"FORWARD_OPERATIONAL","id":"contract-1",'
        b'"schema_name":"qc2.identity_market.DailyBar.v1"}'
    ).hexdigest()


def test_from_contract_maps_memory_index_cutoff_without_fabricating_training_cutoff() -> None:
    row = TemporalArtifact.from_contract(
        {
            "id": "memory-index",
            "schema_name": "qc2.outcomes_research.MemoryIndexManifest.v1",
            "created_at": T0,
            "known_at": T0,
            "available_for_learning_at": T0,
            "evidence_class": "FORWARD_OPERATIONAL",
            "index_kind": "RUNNER",
            "member_refs": ["genome-1"],
            "member_inventory_hash": "a" * 64,
            "cutoff": T1,
            "embedding_artifact_ref": None,
        }
    )
    assert row.index_cutoff == T1
    assert row.index_member_refs == ("genome-1",)
    assert row.training_cutoff is None


def test_learned_dependency_closure_rejects_data_after_training_cutoff() -> None:
    training_row = artifact("late-training-row", "DailyBar", known_at=T2)
    normalizer = artifact(
        "fitted-normalizer",
        "Normalizer",
        training_cutoff=T1,
        dependency_refs=(training_row.artifact_id,),
    )
    firewall = TemporalFirewall(
        [training_row, normalizer],
        catalog_revision="catalog-1",
    )

    with pytest.raises(TemporalViolation) as error:
        firewall.query(
            query(normalizer.artifact_id, cutoff=T4),
            permission("Normalizer"),
        )
    assert error.value.reason_code == "dependency_unavailable_at_cutoff"


def test_dataset_memory_cutoff_scopes_transitive_snapshot_membership() -> None:
    future_snapshot = artifact("future-snapshot", "DailyBar", known_at=T2)
    dataset = artifact(
        "dataset",
        "DatasetManifest",
        memory_cutoff=T1,
        dependency_refs=(future_snapshot.artifact_id,),
    )
    firewall = TemporalFirewall(
        [future_snapshot, dataset],
        catalog_revision="catalog-1",
    )

    with pytest.raises(TemporalViolation) as error:
        firewall.query(
            query(dataset.artifact_id),
            permission("DatasetManifest"),
        )
    assert error.value.reason_code == "dependency_unavailable_at_cutoff"


def test_shared_dependency_is_rechecked_at_each_parent_cutoff() -> None:
    shared = artifact("shared-row", "DailyBar", known_at=T2)
    permissive = artifact(
        "permissive-calibrator",
        "Calibrator",
        training_cutoff=T3,
        available_for_learning_at=T0,
        dependency_refs=(shared.artifact_id,),
    )
    restrictive = artifact(
        "restrictive-calibrator",
        "Calibrator",
        training_cutoff=T1,
        available_for_learning_at=T0,
        dependency_refs=(shared.artifact_id,),
    )
    model = artifact(
        "model",
        "Model",
        training_cutoff=T4,
        available_for_learning_at=T0,
        dependency_refs=(permissive.artifact_id, restrictive.artifact_id),
    )
    firewall = TemporalFirewall(
        [shared, permissive, restrictive, model],
        catalog_revision="catalog-1",
    )

    with pytest.raises(TemporalViolation) as error:
        firewall.export(
            query(
                model.artifact_id,
                cutoff=T5,
                operation=TemporalOperation.EXPORT,
                training_cutoff=T4,
            ),
            permission("DailyBar", "Calibrator", "Model"),
        )
    assert error.value.reason_code == "dependency_unavailable_at_cutoff"


def test_learned_index_members_are_scoped_to_index_cutoff_not_training_cutoff() -> None:
    member = artifact(
        "late-index-member",
        "Genome",
        known_at=T2,
        available_for_learning_at=T2,
    )
    index = artifact(
        "memory-index",
        "MemoryIndexManifest",
        training_cutoff=T3,
        index_cutoff=T1,
        available_for_learning_at=T0,
        index_member_refs=(member.artifact_id,),
    )
    firewall = TemporalFirewall([member, index], catalog_revision="catalog-1")

    with pytest.raises(TemporalViolation) as error:
        firewall.export(
            query(
                index.artifact_id,
                cutoff=T4,
                operation=TemporalOperation.EXPORT,
                training_cutoff=T3,
            ),
            permission("Genome", "MemoryIndexManifest"),
        )
    assert error.value.reason_code == "dependency_unavailable_at_cutoff"


def test_dependency_cycles_and_missing_references_fail_closed() -> None:
    left = artifact("left", "FeatureSnapshot", decision_cutoff=T1, dependency_refs=("right",))
    right = artifact("right", "FeatureSnapshot", decision_cutoff=T1, dependency_refs=("left",))
    firewall = TemporalFirewall([left, right], catalog_revision="catalog-1")

    with pytest.raises(TemporalViolation) as error:
        firewall.query(query("left"), permission("FeatureSnapshot"))
    assert error.value.reason_code == "temporal_dependency_cycle"

    missing = artifact("missing-ref-root", "DailyBar", dependency_refs=("absent",))
    firewall = TemporalFirewall([missing], catalog_revision="catalog-2")
    with pytest.raises(TemporalViolation) as error:
        firewall.query(query(missing.artifact_id), permission("DailyBar"))
    assert error.value.reason_code == "temporal_dependency_missing"


def test_cache_identity_includes_cutoff_catalog_revision_and_catalog_contents() -> None:
    cache = TemporalResultCache()
    original = artifact("cache-row", "DailyBar", payload={"value": 1})
    first_firewall = TemporalFirewall(
        [original],
        catalog_revision="catalog-1",
        result_cache=cache,
    )
    scoped_query = query(original.artifact_id, cutoff=T1)
    grant = permission("DailyBar")

    first = first_firewall.query(scoped_query, grant)
    repeated = first_firewall.query(scoped_query, grant)
    assert first.cache_hit is False
    assert repeated.cache_hit is True

    changed_content = replace(original, payload={"value": 2})
    second_firewall = TemporalFirewall(
        [changed_content],
        catalog_revision="catalog-1",
        result_cache=cache,
    )
    changed = second_firewall.query(scoped_query, grant)
    assert changed.cache_hit is False
    assert changed.artifacts[0].payload["value"] == 2

    third_firewall = TemporalFirewall(
        [changed_content],
        catalog_revision="catalog-2",
        result_cache=cache,
    )
    revised = third_firewall.query(scoped_query, grant)
    assert revised.cache_hit is False

    later_cutoff = third_firewall.query(query(original.artifact_id, cutoff=T2), grant)
    assert later_cutoff.cache_hit is False


def test_query_requires_explicit_bounded_selectors_and_narrow_permissions() -> None:
    with pytest.raises(TemporalViolation):
        TemporalQuery(cutoff=T1, mode=TemporalMode.FORWARD, operation=TemporalOperation.QUERY)

    with pytest.raises(TemporalViolation):
        TemporalPermission(
            operations=frozenset({TemporalOperation.QUERY}),
            artifact_kinds=frozenset({"*"}),
        )

    row = artifact("permission-row", "DailyBar")
    firewall = TemporalFirewall([row], catalog_revision="catalog-1")
    with pytest.raises(TemporalViolation) as error:
        firewall.query(query(row.artifact_id), permission("Genome"))
    assert error.value.reason_code == "permission_denied"


def test_exchange_session_cutoff_is_enforced_and_cache_scoped() -> None:
    cache = TemporalResultCache()
    row = artifact("session-row", "DailyBar", session_id="2026-01-02")
    firewall = TemporalFirewall(
        [row],
        catalog_revision="catalog-1",
        result_cache=cache,
    )
    grant = permission("DailyBar")

    accepted = firewall.query(
        TemporalQuery(
            cutoff=T4,
            mode=TemporalMode.FORWARD,
            operation=TemporalOperation.QUERY,
            artifact_ids=(row.artifact_id,),
            session_id="2026-01-02",
        ),
        grant,
    )
    assert accepted.cache_hit is False

    with pytest.raises(TemporalViolation) as error:
        firewall.query(
            TemporalQuery(
                cutoff=T4,
                mode=TemporalMode.FORWARD,
                operation=TemporalOperation.QUERY,
                artifact_ids=(row.artifact_id,),
                session_id="2026-01-01",
            ),
            grant,
        )
    assert error.value.reason_code == "artifact_unavailable_at_cutoff"

    export_row = artifact(
        "training-session-row",
        "DailyBar",
        session_id="2026-01-03",
    )
    export_firewall = TemporalFirewall(
        [export_row],
        catalog_revision="catalog-2",
    )
    with pytest.raises(TemporalViolation) as error:
        export_firewall.export(
            TemporalQuery(
                cutoff=T4,
                mode=TemporalMode.FORWARD,
                operation=TemporalOperation.EXPORT,
                artifact_ids=(export_row.artifact_id,),
                training_cutoff=T2,
                session_id="2026-01-04",
                training_session_cutoff="2026-01-02",
            ),
            permission("DailyBar"),
        )
    assert error.value.reason_code == "artifact_unavailable_at_cutoff"
