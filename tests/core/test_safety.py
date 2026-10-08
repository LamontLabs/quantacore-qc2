from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from qc2_contracts.runtime import (
    ContractValidationError,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)
from qc2_core.safety import (
    ActionPolicy,
    CapabilityDomain,
    GateObservation,
    GateStatus,
    ReadinessStatus,
    SafetyAction,
    SafetyGatePolicy,
    SafetyViolation,
    UnavailableCapabilityPort,
    WarningPolicy,
    evaluate_readiness,
    policy_for_action,
    readiness_assessment_payload,
    safety_protocol_definition_payload,
    safety_protocol_result_payload,
)
from qc2_core.safety.evaluator import _evaluate_readiness
from qc2_core.safety.policies import DEFAULT_ACTION_POLICIES

NOW = "2026-10-08T06:00:00Z"
LATER = "2026-10-08T06:01:00Z"
EARLIER = "2026-10-08T05:59:00Z"
GENERATION = 7


def _reference() -> dict[str, str]:
    return {
        "target_schema_name": "qc2.time_operation.ClockAssessment.v1",
        "target_id": new_uuidv7(),
        "content_hash": "a" * 64,
    }


def _gate(
    action: SafetyAction = SafetyAction.PREDICT,
    *,
    gate_id: str = "data_gate",
    domain: CapabilityDomain = CapabilityDomain.DATA,
    warning_policy: WarningPolicy = WarningPolicy.NOT_ALLOWED,
) -> SafetyGatePolicy:
    return SafetyGatePolicy(
        gate_id=gate_id,
        action=action,
        domain=domain,
        rule="The declared evidence is available and fresh.",
        required_evidence=("capability_evidence",),
        warning_policy=warning_policy,
    )


def _observation(
    policy: SafetyGatePolicy,
    *,
    status: GateStatus = GateStatus.PASS,
    evaluated_at: str = EARLIER,
    freshness_deadline: str = LATER,
    input_generation: int = GENERATION,
    evidence_keys: tuple[str, ...] | None = None,
    reason_codes: tuple[str, ...] = (),
    source_refs: tuple[dict[str, str], ...] | None = None,
) -> GateObservation:
    if status in {GateStatus.BLOCK, GateStatus.UNKNOWN, GateStatus.UNAVAILABLE} and not reason_codes:
        reason_codes = ("FIXTURE_STATE",)
    return GateObservation(
        gate_id=policy.gate_id,
        action=policy.action,
        domain=policy.domain,
        status=status,
        evaluated_at=evaluated_at,
        freshness_deadline=freshness_deadline,
        input_generation=input_generation,
        evidence_keys=(
            policy.required_evidence if evidence_keys is None else evidence_keys
        ),
        reason_codes=reason_codes,
        source_refs=(_reference(),) if source_refs is None else source_refs,
        observed_versions=("fixture-v1",),
    )


def test_default_policies_cover_action_specific_contracts_without_entry_exit_inheritance() -> None:
    actions = {policy.action for policy in DEFAULT_ACTION_POLICIES}
    assert actions == {
        SafetyAction.PREDICT,
        SafetyAction.NEW_ENTRY,
        SafetyAction.EXIT_POSITION,
        SafetyAction.CANCEL_ENTRY,
        SafetyAction.PROMOTE,
    }
    domains = {
        gate.domain
        for policy in DEFAULT_ACTION_POLICIES
        for gate in policy.gates
    }
    assert {
        CapabilityDomain.TIME,
        CapabilityDomain.DATA,
        CapabilityDomain.MODEL,
        CapabilityDomain.REGISTRY,
        CapabilityDomain.CONFIGURATION,
        CapabilityDomain.EVIDENCE,
        CapabilityDomain.BROKER,
        CapabilityDomain.RECONCILIATION,
        CapabilityDomain.IDEMPOTENCY,
    } <= domains

    entry_policy = policy_for_action(SafetyAction.NEW_ENTRY)
    exit_policy = policy_for_action(SafetyAction.EXIT_POSITION)
    entry_observations = [
        _observation(
            gate,
            status=(
                GateStatus.BLOCK
                if gate.gate_id == "entry_pause_authority"
                else GateStatus.PASS
            ),
            reason_codes=(
                ("ENTRY_PAUSED",)
                if gate.gate_id == "entry_pause_authority"
                else ()
            ),
        )
        for gate in entry_policy.gates
    ]
    exit_observations = [
        _observation(gate)
        for gate in exit_policy.gates
    ]

    entry = evaluate_readiness(
        SafetyAction.NEW_ENTRY,
        entry_observations + exit_observations,
        evaluated_at=NOW,
        input_generation=GENERATION,
    )
    exit_readiness = evaluate_readiness(
        SafetyAction.EXIT_POSITION,
        entry_observations + exit_observations,
        evaluated_at=NOW,
        input_generation=GENERATION,
    )

    assert entry.status is ReadinessStatus.BLOCKED
    assert not entry.permits_action
    assert exit_readiness.status is ReadinessStatus.READY
    assert exit_readiness.permits_action
    assert "entry_pause_authority" not in {
        gate.gate_id for gate in exit_readiness.gate_results
    }


def test_required_unknown_blocks_only_its_action_and_missing_gate_is_unknown() -> None:
    first = _gate(gate_id="data_gate")
    second = _gate(gate_id="registry_gate", domain=CapabilityDomain.REGISTRY)
    second = SafetyGatePolicy(
        gate_id=second.gate_id,
        action=second.action,
        domain=second.domain,
        rule=second.rule,
        required_evidence=("registry_evidence",),
        warning_policy=second.warning_policy,
    )
    policy = ActionPolicy(SafetyAction.PREDICT, (first, second))
    result = _evaluate_readiness(
        SafetyAction.PREDICT,
        [_observation(first, status=GateStatus.UNKNOWN)],
        evaluated_at=NOW,
        input_generation=GENERATION,
        policies=(policy,),
    )

    assert result.status is ReadinessStatus.UNKNOWN
    assert not result.permits_action
    assert result.gate_results[0].status is GateStatus.UNKNOWN
    assert result.gate_results[1].reason_codes == ("GATE_RESULT_MISSING",)


def test_unknown_status_remains_consistent_when_another_gate_warns() -> None:
    unknown_gate = _gate(gate_id="unknown_gate")
    warning_gate = _gate(
        gate_id="warning_gate",
        domain=CapabilityDomain.REGISTRY,
    )
    policy = ActionPolicy(
        SafetyAction.PREDICT,
        (unknown_gate, warning_gate),
    )
    result = _evaluate_readiness(
        SafetyAction.PREDICT,
        [
            _observation(unknown_gate, status=GateStatus.UNKNOWN),
            _observation(
                warning_gate,
                status=GateStatus.WARN,
                reason_codes=("CAPABILITY_LIMITED",),
            ),
        ],
        evaluated_at=NOW,
        input_generation=GENERATION,
        policies=(policy,),
    )

    assert result.status is ReadinessStatus.UNKNOWN
    assert not result.permits_action


@pytest.mark.parametrize(
    ("warning_policy", "expected_status", "can_proceed"),
    [
        (WarningPolicy.ALLOW_WITH_EVIDENCE, ReadinessStatus.DEGRADED, True),
        (WarningPolicy.BLOCK, ReadinessStatus.BLOCKED, False),
        (WarningPolicy.NOT_ALLOWED, ReadinessStatus.BLOCKED, False),
    ],
)
def test_warning_requires_policy_reason_and_evidence(
    warning_policy: WarningPolicy,
    expected_status: ReadinessStatus,
    can_proceed: bool,
) -> None:
    policy = _gate(warning_policy=warning_policy)
    result = _evaluate_readiness(
        SafetyAction.PREDICT,
        [
            _observation(
                policy,
                status=GateStatus.WARN,
                reason_codes=("CAPABILITY_LIMITED",),
            )
        ],
        evaluated_at=NOW,
        input_generation=GENERATION,
        policies=(ActionPolicy(SafetyAction.PREDICT, (policy,)),),
    )

    assert result.status is expected_status
    assert result.permits_action is can_proceed


def test_warning_without_its_declared_evidence_becomes_unknown() -> None:
    policy = _gate(warning_policy=WarningPolicy.ALLOW_WITH_EVIDENCE)
    result = _evaluate_readiness(
        SafetyAction.PREDICT,
        [
            _observation(
                policy,
                status=GateStatus.WARN,
                reason_codes=("CAPABILITY_LIMITED",),
                evidence_keys=(),
                source_refs=(),
            )
        ],
        evaluated_at=NOW,
        input_generation=GENERATION,
        policies=(ActionPolicy(SafetyAction.PREDICT, (policy,)),),
    )

    assert result.status is ReadinessStatus.UNKNOWN
    assert result.gate_results[0].reason_codes[-1] == "REQUIRED_EVIDENCE_MISSING"
    assert not result.permits_action


@pytest.mark.parametrize(
    ("observed_at", "deadline", "generation", "expected_reason"),
    [
        (EARLIER, "2026-10-08T05:59:59Z", GENERATION, "EVIDENCE_STALE"),
        (LATER, "2026-10-08T06:02:00Z", GENERATION, "EVIDENCE_FROM_FUTURE"),
        (EARLIER, LATER, GENERATION + 1, "INPUT_GENERATION_MISMATCH"),
    ],
)
def test_stale_future_and_mixed_generation_evidence_fail_closed(
    observed_at: str,
    deadline: str,
    generation: int,
    expected_reason: str,
) -> None:
    policy = _gate()
    result = _evaluate_readiness(
        SafetyAction.PREDICT,
        [
            _observation(
                policy,
                evaluated_at=observed_at,
                freshness_deadline=deadline,
                input_generation=generation,
            )
        ],
        evaluated_at=NOW,
        input_generation=GENERATION,
        policies=(ActionPolicy(SafetyAction.PREDICT, (policy,)),),
    )

    assert result.status is ReadinessStatus.UNKNOWN
    assert expected_reason in result.gate_results[0].reason_codes
    assert not result.permits_action


def test_unavailable_capability_port_is_explicit_and_never_ready() -> None:
    policy = _gate(domain=CapabilityDomain.BROKER)
    port = UnavailableCapabilityPort(CapabilityDomain.BROKER)
    observation = port.observe(
        policy,
        evaluated_at=NOW,
        input_generation=GENERATION,
    )
    readiness = _evaluate_readiness(
        SafetyAction.PREDICT,
        [observation],
        evaluated_at=NOW,
        input_generation=GENERATION,
        policies=(ActionPolicy(SafetyAction.PREDICT, (policy,)),),
    )

    assert observation.status is GateStatus.UNAVAILABLE
    assert observation.reason_codes == ("CAPABILITY_UNAVAILABLE",)
    assert readiness.status is ReadinessStatus.UNKNOWN
    assert readiness.gate_results[0].status is GateStatus.UNAVAILABLE
    assert not readiness.permits_action
    assessment = readiness_assessment_payload(
        readiness,
        record_id=new_uuidv7(),
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    assert assessment["gate_results"][0]["status"] == "UNAVAILABLE"


def test_action_mismatch_duplicate_gate_and_port_mismatch_are_rejected() -> None:
    policy = _gate()
    observation = _observation(policy)

    with pytest.raises(SafetyViolation, match="duplicate observation"):
        _evaluate_readiness(
            SafetyAction.PREDICT,
            [observation, observation],
            evaluated_at=NOW,
            input_generation=GENERATION,
            policies=(ActionPolicy(SafetyAction.PREDICT, (policy,)),),
        )

    with pytest.raises(SafetyViolation, match="does not match"):
        UnavailableCapabilityPort(CapabilityDomain.TIME).observe(
            policy,
            evaluated_at=NOW,
            input_generation=GENERATION,
        )

    with pytest.raises(FrozenInstanceError):
        observation.input_generation = 9  # type: ignore[misc]


def test_source_references_are_deeply_immutable() -> None:
    policy = _gate()
    source_ref = {"metadata": {"versions": ["source-v1"]}}
    observation = _observation(policy, source_refs=(source_ref,))

    source_ref["metadata"]["versions"].append("mutated")  # type: ignore[index]
    assert observation.source_refs[0]["metadata"]["versions"] == ("source-v1",)
    with pytest.raises(TypeError):
        observation.source_refs[0]["metadata"]["new"] = "value"  # type: ignore[index]


def test_readiness_and_protocol_contracts_are_valid_and_separate_from_features() -> None:
    policy = _gate()
    observation = _observation(policy)
    readiness = _evaluate_readiness(
        SafetyAction.PREDICT,
        [observation],
        evaluated_at=NOW,
        input_generation=GENERATION,
        policies=(ActionPolicy(SafetyAction.PREDICT, (policy,)),),
    )
    assessment = readiness_assessment_payload(
        readiness,
        record_id=new_uuidv7(),
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    validate_contract("ReadinessAssessment", assessment)
    assert assessment["owning_authority"] == "safety"
    assert assessment["status"] == "READY"
    assert "score" not in assessment
    assert "feature_values" not in assessment
    assert "model_inputs" not in assessment
    with pytest.raises(ContractValidationError):
        validate_contract("FeatureSnapshot", assessment)

    definition = safety_protocol_definition_payload(
        policy,
        record_id=new_uuidv7(),
        created_at=NOW,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
        implementation_hash="b" * 64,
        source_refs=(_reference(),),
    )
    verify_content_hash("SafetyProtocolDefinition", definition)
    result = safety_protocol_result_payload(
        policy,
        readiness.gate_results[0],
        definition,
        record_id=new_uuidv7(),
        created_at=NOW,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    verify_content_hash("SafetyProtocolResult", result)
    assert result["action"] == "PREDICT"
    assert result["result"] == "PASS"


def test_unavailable_protocol_result_is_serialized_as_unknown() -> None:
    policy = _gate(domain=CapabilityDomain.BROKER)
    observation = UnavailableCapabilityPort(CapabilityDomain.BROKER).observe(
        policy,
        evaluated_at=NOW,
        input_generation=GENERATION,
    )
    readiness = _evaluate_readiness(
        SafetyAction.PREDICT,
        [observation],
        evaluated_at=NOW,
        input_generation=GENERATION,
        policies=(ActionPolicy(SafetyAction.PREDICT, (policy,)),),
    )
    definition = safety_protocol_definition_payload(
        policy,
        record_id=new_uuidv7(),
        created_at=NOW,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
        implementation_hash="c" * 64,
    )
    result = safety_protocol_result_payload(
        policy,
        readiness.gate_results[0],
        definition,
        record_id=new_uuidv7(),
        created_at=NOW,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    assert result["result"] == "UNKNOWN"


def test_non_utc_time_and_unmatched_action_gate_are_rejected() -> None:
    policy = _gate()
    with pytest.raises(SafetyViolation, match="explicit UTC"):
        _observation(policy, evaluated_at="2026-10-08T06:00:00-07:00")

    extra_policy = _gate(gate_id="other_gate")
    with pytest.raises(SafetyViolation, match="unexpected gate"):
        _evaluate_readiness(
            SafetyAction.PREDICT,
            [_observation(extra_policy)],
            evaluated_at=NOW,
            input_generation=GENERATION,
            policies=(ActionPolicy(SafetyAction.PREDICT, (policy,)),),
        )
