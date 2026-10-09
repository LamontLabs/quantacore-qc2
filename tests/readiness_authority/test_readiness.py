from __future__ import annotations

from dataclasses import fields, replace

from qc2_readiness_authority import (
    DependencyAvailability,
    EvidenceFact,
    GateState,
    ModelLoadBinding,
    ModelQualification,
    PredictionReadinessInputs,
    ReadinessContext,
    ReadinessStage,
    RegistryCompatibility,
    SealCapability,
    SourceReference,
    TemporalDependencyAssessment,
    assess_ingestion_preflight,
    assess_prediction_ready,
    assess_snapshot_ready,
)

NOW = "2026-10-09T16:00:00Z"
OBSERVED = "2026-10-09T15:59:00Z"
FRESH_UNTIL = "2026-10-09T16:30:00Z"
GENERATION = 7
HASH_A = "a" * 64
HASH_B = "b" * 64


def _ref(schema: str, index: int, content_hash: str = HASH_A) -> SourceReference:
    return SourceReference(
        target_schema_name=schema,
        target_id=f"00000000-0000-7000-8000-{index:012x}",
        content_hash=content_hash,
    )


def _fact(
    schema: str,
    index: int,
    *,
    status: GateState = GateState.PASS,
    version: str | None = "v1",
    observed_at: str | None = OBSERVED,
    freshness_deadline: str | None = FRESH_UNTIL,
    reason_codes: tuple[str, ...] = (),
) -> EvidenceFact:
    return EvidenceFact(
        status=status,
        observed_at=observed_at,
        freshness_deadline=freshness_deadline,
        version=version,
        source_refs=(_ref(schema, index),),
        reason_codes=reason_codes,
        input_generation=GENERATION,
    )


def _context() -> ReadinessContext:
    return ReadinessContext(evaluated_at=NOW, input_generation=GENERATION)


def _ingestion(clock: EvidenceFact | None = None):
    return assess_ingestion_preflight(
        _context(),
        installation=_fact("qc2.time_operation.DeploymentCapabilityManifest.v1", 1),
        clock_calendar=clock
        or _fact("qc2.time_operation.ClockAssessment.v1", 2, version="clock-r4"),
        data_capability=_fact("qc2.identity_market.DataCapabilityManifest.v1", 3),
        storage_evidence_write=_fact("qc2.integrity_build.EvidenceEvent.v1", 4),
        bounded_resources=_fact("qc2.integrity_build.ResourceBudget.v1", 5),
    )


def _snapshot(ingestion, *, acquisition: EvidenceFact | None = None):
    return assess_snapshot_ready(
        _context(),
        ingestion_preflight=ingestion,
        declared_acquisition=acquisition or _fact("qc2.identity_market.RequestManifest.v1", 6),
        semantic_provenance=_fact("qc2.identity_market.BarSemanticsManifest.v1", 7),
        universe_coverage=_fact("qc2.identity_market.UniverseManifest.v1", 8),
        durable_snapshot_dependencies=_fact("qc2.identity_market.MarketSnapshotRevision.v1", 9),
    )


def _prediction_inputs(
    ingestion=None,
    snapshot=None,
    *,
    model_binding: ModelLoadBinding | None = None,
    temporal_dependencies: TemporalDependencyAssessment | None = None,
    seal_capability: SealCapability | None = None,
    registry_compatibility: RegistryCompatibility | None = None,
) -> PredictionReadinessInputs:
    ingestion = ingestion or _ingestion()
    snapshot = snapshot or _snapshot(ingestion)
    model_ref = _ref(_MODEL_SCHEMA, 11, HASH_A)
    epoch_ref = _ref(_EPOCH_SCHEMA, 12, HASH_B)
    feature_registry = _ref("qc2.scientific_definitions.FeatureRegistry.v1", 13)
    label_registry = _ref("qc2.scientific_definitions.LabelRegistry.v1", 14)
    score_manifest = _ref("qc2.scientific_definitions.ScoreManifest.v1", 15)
    registry_refs = (feature_registry, label_registry, score_manifest)
    model_binding = model_binding or ModelLoadBinding(
        pointer_state="CHAMPION_SET",
        pointer_ref=_ref("qc2.governance_owner.ChampionPointer.v1", 16, HASH_B),
        pointer_model_ref=model_ref,
        pointer_epoch_ref=epoch_ref,
        pointer_generation=3,
        pointer_role="OPERATING",
        loaded_model_ref=model_ref,
        loaded_epoch_ref=epoch_ref,
        loaded_generation=3,
        load_confirmed=True,
        pointer_evidence_class="FORWARD_OPERATIONAL",
        pointer_environment_namespace="test",
        loaded_evidence_class="FORWARD_OPERATIONAL",
        loaded_environment_namespace="test",
        fact=_fact("qc2.models_prediction.ModelManifest.v1", 17, version="loaded-g3"),
    )
    registry_compatibility = registry_compatibility or RegistryCompatibility(
        model_ref=model_ref,
        model_registry_refs=registry_refs,
        active_registry_refs=registry_refs,
        fact=_fact("qc2.scientific_definitions.FeatureRegistry.v1", 18, version="registry-r5"),
    )
    temporal_dependencies = temporal_dependencies or TemporalDependencyAssessment(
        decision_cutoff="2026-10-09T16:05:00Z",
        dependencies=(
            DependencyAvailability(
                dependency_id="feature_snapshot",
                available_at="2026-10-09T16:03:00Z",
                source_ref=_ref("qc2.scientific_definitions.FeatureSnapshot.v1", 19),
                version="feature-snapshot-r2",
            ),
        ),
        fact=_fact("qc2.scientific_definitions.FeatureSnapshot.v1", 20),
    )
    seal_capability = seal_capability or SealCapability(
        fact=_fact("qc2.integrity_build.Checkpoint.v1", 21, version="seal-capability-r1"),
        estimated_prediction_complete_at="2026-10-09T16:06:00Z",
        decision_deadline="2026-10-09T16:10:00Z",
        estimated_sealed_at="2026-10-09T16:11:00Z",
        seal_deadline="2026-10-09T16:12:00Z",
        estimated_anchor_at="2026-10-09T16:13:00Z",
        evidence_anchor_deadline="2026-10-09T16:15:00Z",
        next_session_open="2026-10-09T16:20:00Z",
    )
    return PredictionReadinessInputs(
        context=_context(),
        ingestion_preflight=ingestion,
        snapshot_ready=snapshot,
        run_ref=_ref("qc2.models_prediction.PredictionRun.v1", 22),
        run_binding_fact=_fact(
            "qc2.models_prediction.PredictionRun.v1", 22, version="run-binding-r1"
        ),
        expected_epoch_ref=epoch_ref,
        model_binding=model_binding,
        model_qualification=ModelQualification(
            qualified_model_ref=model_ref,
            fact=_fact("qc2.validation.QualificationReceipt.v1", 23),
        ),
        registry_compatibility=registry_compatibility,
        temporal_dependencies=temporal_dependencies,
        numerical_environment=_fact(
            "qc2.time_operation.DeploymentCapabilityManifest.v1",
            24,
            version="numerical-env-r3",
        ),
        seal_capability=seal_capability,
    )


_MODEL_SCHEMA = "qc2.models_prediction.ModelManifest.v1"
_EPOCH_SCHEMA = "qc2.validation.ValidationEpoch.v1"


def test_all_three_scientific_stages_project_reasons_versions_and_contracts() -> None:
    ingestion = _ingestion()
    snapshot = _snapshot(ingestion)
    prediction = assess_prediction_ready(_prediction_inputs(ingestion, snapshot))

    assert ingestion.status.value == "READY"
    assert snapshot.status.value == "READY"
    assert prediction.status.value == "READY"
    assert prediction.stage is ReadinessStage.PREDICTION_READY

    stages_and_actions = (
        (ingestion, "INGESTION_PREFLIGHT"),
        (snapshot, "SNAPSHOT_READY"),
        (prediction, "PREDICT"),
    )
    for index, (assessment, action) in enumerate(stages_and_actions, start=1):
        assert assessment.as_projection_payload()["action"] == action
        contract = assessment.as_contract_payload(
            record_id=f"00000000-0000-7000-8000-0000000000{index:02x}",
            evidence_class="SYNTHETIC_FIXTURE",
            environment_namespace="test",
        )
        assert contract["action"] == action

    projection = prediction.as_projection_payload()
    assert projection["action"] == "PREDICT"
    assert projection["stage"] == "PREDICTION_READY"
    assert projection["reason_codes"] == []
    assert projection["freshness_deadline"] == FRESH_UNTIL
    model_gate = next(
        gate
        for gate in projection["gate_results"]
        if gate["gate_id"] == "model_pointer_consistency"
    )
    assert "pointer-generation:3" in model_gate["observed_versions"]
    assert "loaded-generation:3" in model_gate["observed_versions"]
    seal_gate = next(
        gate for gate in projection["gate_results"] if gate["gate_id"] == "seal_capability"
    )
    assert all(item["status"] == "PASS" for item in seal_gate["deadline_assessments"])

    payload = prediction.as_contract_payload(
        record_id="00000000-0000-7000-8000-000000000099",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    assert payload["action"] == "PREDICT"
    assert payload["status"] == "READY"

    # Readiness binds a planned run before inference; it has no same-run prediction input.
    assert "prediction_ref" not in {item.name for item in fields(PredictionReadinessInputs)}


def test_broker_outage_is_outside_scientific_readiness_and_does_not_block_it() -> None:
    broker_connected = False
    result = assess_prediction_ready(_prediction_inputs())

    assert broker_connected is False
    assert result.status.value == "READY"
    assert all("broker" not in item.name.lower() for item in fields(PredictionReadinessInputs))


def test_unknown_clock_prevents_all_time_sensitive_scientific_stages_from_passing() -> None:
    unknown_clock = _fact(
        "qc2.time_operation.ClockAssessment.v1",
        2,
        status=GateState.UNKNOWN,
        version=None,
        observed_at=None,
        freshness_deadline=None,
        reason_codes=("CLOCK_UNKNOWN",),
    )
    ingestion = _ingestion(unknown_clock)
    snapshot = _snapshot(ingestion)
    prediction = assess_prediction_ready(_prediction_inputs(ingestion, snapshot))

    assert ingestion.status.value == "UNKNOWN"
    assert snapshot.status.value == "UNKNOWN"
    assert prediction.status.value == "UNKNOWN"
    assert "CLOCK_UNKNOWN" in prediction.reason_codes
    assert "CLOCK_UNTRUSTED" in prediction.reason_codes


def test_future_upstream_assessment_cannot_make_downstream_readiness_pass() -> None:
    future_ingestion = replace(
        _ingestion(),
        context=ReadinessContext(
            evaluated_at="2026-10-09T16:01:00Z",
            input_generation=GENERATION,
        ),
    )
    snapshot = _snapshot(future_ingestion)
    prediction = assess_prediction_ready(_prediction_inputs(future_ingestion, snapshot))

    assert snapshot.status.value == "UNKNOWN"
    upstream_gate = next(
        item for item in snapshot.gate_results if item.gate_id == "ingestion_preflight"
    )
    assert upstream_gate.reason_codes == ("UPSTREAM_ASSESSMENT_FROM_FUTURE",)
    assert prediction.status.value == "UNKNOWN"
    assert "UPSTREAM_ASSESSMENT_FROM_FUTURE" in prediction.reason_codes


def test_missing_snapshot_artifact_blocks_prediction_with_a_specific_reason() -> None:
    ingestion = _ingestion()
    missing_artifact = EvidenceFact(
        status=GateState.BLOCK,
        reason_codes=("ARTIFACT_MISSING",),
        input_generation=GENERATION,
    )
    snapshot = _snapshot(ingestion, acquisition=missing_artifact)
    prediction = assess_prediction_ready(_prediction_inputs(ingestion, snapshot))

    assert snapshot.status.value == "BLOCKED"
    assert prediction.status.value == "BLOCKED"
    assert "ARTIFACT_MISSING" in prediction.reason_codes


def test_illegal_temporal_dependency_blocks_prediction() -> None:
    temporal = TemporalDependencyAssessment(
        decision_cutoff="2026-10-09T16:05:00Z",
        dependencies=(
            DependencyAvailability(
                dependency_id="future_feature",
                available_at="2026-10-09T16:06:00Z",
                source_ref=_ref("qc2.scientific_definitions.FeatureSnapshot.v1", 25),
                version="future-r1",
            ),
        ),
        fact=_fact("qc2.scientific_definitions.FeatureSnapshot.v1", 26),
    )
    prediction = assess_prediction_ready(_prediction_inputs(temporal_dependencies=temporal))

    assert prediction.status.value == "BLOCKED"
    gate = next(item for item in prediction.gate_results if item.gate_id == "temporal_dependencies")
    assert gate.reason_codes == ("ILLEGAL_TEMPORAL_DEPENDENCY",)


def test_loaded_model_must_match_exact_pointer_model_and_generation() -> None:
    inputs = _prediction_inputs()
    mismatch = replace(
        inputs.model_binding,
        loaded_model_ref=_ref(_MODEL_SCHEMA, 99, HASH_B),
    )
    prediction = assess_prediction_ready(replace(inputs, model_binding=mismatch))

    assert prediction.status.value == "BLOCKED"
    gate = next(
        item for item in prediction.gate_results if item.gate_id == "model_pointer_consistency"
    )
    assert "MODEL_LOAD_MISMATCH" in gate.reason_codes


def test_missing_loaded_epoch_or_generation_remains_unknown() -> None:
    inputs = _prediction_inputs()
    for binding, reason in (
        (
            replace(inputs.model_binding, loaded_epoch_ref=None),
            "LOADED_MODEL_EPOCH_BINDING_MISSING",
        ),
        (
            replace(inputs.model_binding, loaded_generation=None),
            "MODEL_LOAD_GENERATION_MISSING",
        ),
    ):
        prediction = assess_prediction_ready(replace(inputs, model_binding=binding))
        gate = next(
            item for item in prediction.gate_results if item.gate_id == "model_pointer_consistency"
        )
        assert prediction.status.value == "UNKNOWN"
        assert reason in gate.reason_codes


def test_stale_evidence_never_produces_a_ready_ingestion_assessment() -> None:
    stale_installation = _fact(
        "qc2.time_operation.DeploymentCapabilityManifest.v1",
        1,
        freshness_deadline="2026-10-09T15:59:30Z",
    )
    result = assess_ingestion_preflight(
        _context(),
        installation=stale_installation,
        clock_calendar=_fact("qc2.time_operation.ClockAssessment.v1", 2),
        data_capability=_fact("qc2.identity_market.DataCapabilityManifest.v1", 3),
        storage_evidence_write=_fact("qc2.integrity_build.EvidenceEvent.v1", 4),
        bounded_resources=_fact("qc2.integrity_build.ResourceBudget.v1", 5),
    )

    assert result.status.value == "UNKNOWN"
    gate = next(item for item in result.gate_results if item.gate_id == "installation_capability")
    assert gate.reason_codes == ("EVIDENCE_STALE",)


def test_seal_estimate_must_fit_prediction_seal_and_anchor_deadlines() -> None:
    inputs = _prediction_inputs()
    late_seal = replace(
        inputs.seal_capability,
        estimated_sealed_at="2026-10-09T16:13:00Z",
    )
    prediction = assess_prediction_ready(replace(inputs, seal_capability=late_seal))

    assert prediction.status.value == "BLOCKED"
    gate = next(item for item in prediction.gate_results if item.gate_id == "seal_capability")
    seal_deadline = next(
        item for item in gate.deadline_assessments if item.deadline_id == "prediction_seal"
    )
    assert seal_deadline.status is GateState.BLOCK
    assert seal_deadline.reason_codes == ("SEAL_DEADLINE_UNREACHABLE",)


def test_registry_versions_must_match_the_model_declared_registry_set() -> None:
    inputs = _prediction_inputs()
    compatibility = inputs.registry_compatibility
    active_refs = (
        *compatibility.active_registry_refs[:-1],
        _ref("qc2.scientific_definitions.ScoreManifest.v1", 98, HASH_B),
    )
    changed = replace(compatibility, active_registry_refs=active_refs)
    prediction = assess_prediction_ready(replace(inputs, registry_compatibility=changed))

    assert prediction.status.value == "BLOCKED"
    gate = next(
        item for item in prediction.gate_results if item.gate_id == "registry_compatibility"
    )
    assert gate.reason_codes == ("REGISTRY_VERSION_MISMATCH",)
