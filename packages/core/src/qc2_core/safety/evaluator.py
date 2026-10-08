"""Pure action-scoped safety evaluation and contract materialization."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from qc2_contracts.runtime import (
    canonical_content_hash,
    validate_contract,
    verify_content_hash,
)

from .models import (
    ActionPolicy,
    ActionReadiness,
    GateEvaluation,
    GateObservation,
    GateStatus,
    ReadinessStatus,
    SafetyAction,
    SafetyGatePolicy,
    SafetyViolation,
    WarningPolicy,
    is_sha256,
    parse_utc_instant,
)
from .policies import DEFAULT_ACTION_POLICIES

_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _plain_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json_value(item) for item in value]
    return value


def _plain_reference(reference: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _plain_json_value(value) for key, value in reference.items()}


def _normalized_observation(
    policy: SafetyGatePolicy,
    observation: GateObservation,
    *,
    evaluation_at: str,
    input_generation: int,
) -> GateEvaluation:
    status = observation.status
    reasons = list(observation.reason_codes)
    now = parse_utc_instant(evaluation_at, "evaluation_at")
    observed_at = parse_utc_instant(observation.evaluated_at, "observation.evaluated_at")
    deadline = parse_utc_instant(
        observation.freshness_deadline, "observation.freshness_deadline"
    )

    if observation.input_generation != input_generation:
        status = GateStatus.UNKNOWN
        _append_once(reasons, "INPUT_GENERATION_MISMATCH")
    elif observed_at > now:
        status = GateStatus.UNKNOWN
        _append_once(reasons, "EVIDENCE_FROM_FUTURE")
    elif now > deadline:
        status = GateStatus.UNKNOWN
        _append_once(reasons, "EVIDENCE_STALE")

    if status in {GateStatus.PASS, GateStatus.WARN}:
        missing = set(policy.required_evidence) - set(observation.evidence_keys)
        if missing or not observation.source_refs:
            status = GateStatus.UNKNOWN
            _append_once(reasons, "REQUIRED_EVIDENCE_MISSING")

    if status is GateStatus.WARN:
        if not reasons:
            status = GateStatus.UNKNOWN
            _append_once(reasons, "WARNING_REASON_MISSING")
        elif policy.warning_policy is WarningPolicy.ALLOW_WITH_EVIDENCE and (
            not observation.source_refs or not observation.evidence_keys
        ):
            status = GateStatus.UNKNOWN
            _append_once(reasons, "WARNING_EVIDENCE_MISSING")
    elif status is GateStatus.BLOCK and not reasons:
        _append_once(reasons, "GATE_BLOCKED")
    elif status is GateStatus.UNKNOWN and not reasons:
        _append_once(reasons, "GATE_STATE_UNKNOWN")
    elif status is GateStatus.UNAVAILABLE and not reasons:
        _append_once(reasons, "CAPABILITY_UNAVAILABLE")

    return GateEvaluation(
        gate_id=policy.gate_id,
        action=policy.action,
        status=status,
        reason_codes=tuple(reasons),
        evaluated_at=observation.evaluated_at,
        freshness_deadline=observation.freshness_deadline,
        source_refs=observation.source_refs,
        observed_versions=observation.observed_versions,
    )


def evaluate_readiness(
    action: SafetyAction,
    observations: Sequence[GateObservation],
    *,
    evaluated_at: str,
    input_generation: int,
) -> ActionReadiness:
    """Evaluate the named action against the frozen policies; no runtime override exists."""
    return _evaluate_readiness(
        action,
        observations,
        evaluated_at=evaluated_at,
        input_generation=input_generation,
        policies=DEFAULT_ACTION_POLICIES,
    )


def _evaluate_readiness(
    action: SafetyAction,
    observations: Sequence[GateObservation],
    *,
    evaluated_at: str,
    input_generation: int,
    policies: tuple[ActionPolicy, ...],
) -> ActionReadiness:
    """Internal evaluator for isolated policy tests; production uses frozen defaults.

    Evaluation is scoped to one action. Results belonging to other actions are ignored.
    """
    try:
        normalized_action = SafetyAction(action)
    except ValueError as exc:
        raise SafetyViolation("unsupported readiness action") from exc
    parse_utc_instant(evaluated_at, "evaluated_at")
    if (
        isinstance(input_generation, bool)
        or not isinstance(input_generation, int)
        or input_generation < 0
    ):
        raise SafetyViolation("input_generation must be a nonnegative integer")
    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
        raise SafetyViolation("observations must be a sequence")

    matching_policies = tuple(
        policy for policy in policies if policy.action is normalized_action
    )
    if len(matching_policies) != 1:
        raise SafetyViolation(
            f"expected exactly one policy for {normalized_action.value}"
        )
    policy = matching_policies[0]
    expected = {gate.gate_id: gate for gate in policy.gates}
    supplied: dict[str, GateObservation] = {}
    seen: set[tuple[SafetyAction, str]] = set()
    for observation in observations:
        if not isinstance(observation, GateObservation):
            raise SafetyViolation("observations must contain GateObservation values")
        key = (observation.action, observation.gate_id)
        if key in seen:
            raise SafetyViolation("duplicate observation for one action and gate")
        seen.add(key)
        if observation.action is not normalized_action:
            continue
        gate_policy = expected.get(observation.gate_id)
        if gate_policy is None:
            raise SafetyViolation("unexpected gate observation for this action")
        if observation.domain is not gate_policy.domain:
            raise SafetyViolation("gate observation domain does not match policy")
        supplied[observation.gate_id] = observation

    results: list[GateEvaluation] = []
    for gate_policy in policy.gates:
        observation = supplied.get(gate_policy.gate_id)
        if observation is None:
            results.append(
                GateEvaluation(
                    gate_id=gate_policy.gate_id,
                    action=normalized_action,
                    status=GateStatus.UNKNOWN,
                    reason_codes=("GATE_RESULT_MISSING",),
                    evaluated_at=evaluated_at,
                    freshness_deadline=evaluated_at,
                    source_refs=(),
                    observed_versions=(),
                )
            )
            continue
        results.append(
            _normalized_observation(
                gate_policy,
                observation,
                evaluation_at=evaluated_at,
                input_generation=input_generation,
            )
        )

    if any(result.status is GateStatus.BLOCK for result in results):
        readiness_status = ReadinessStatus.BLOCKED
    elif any(
        result.status in {GateStatus.UNKNOWN, GateStatus.UNAVAILABLE}
        for result in results
    ):
        readiness_status = ReadinessStatus.UNKNOWN
    elif any(result.status is GateStatus.WARN for result in results):
        by_gate = {gate.gate_id: gate for gate in policy.gates}
        warning_is_allowed = all(
            by_gate[result.gate_id].warning_policy
            is WarningPolicy.ALLOW_WITH_EVIDENCE
            for result in results
            if result.status is GateStatus.WARN
        )
        readiness_status = (
            ReadinessStatus.DEGRADED
            if warning_is_allowed
            else ReadinessStatus.BLOCKED
        )
    else:
        readiness_status = ReadinessStatus.READY

    deadlines = [
        parse_utc_instant(result.freshness_deadline, "freshness_deadline")
        for result in results
    ]
    freshness_deadline = min(deadlines).isoformat().replace("+00:00", "Z")
    return ActionReadiness(
        action=normalized_action,
        status=readiness_status,
        gate_results=tuple(results),
        input_generation=input_generation,
        evaluated_at=evaluated_at,
        freshness_deadline=freshness_deadline,
        allowed_warning_gate_ids=tuple(
            gate.gate_id
            for gate in policy.gates
            if gate.warning_policy is WarningPolicy.ALLOW_WITH_EVIDENCE
        ),
    )


def readiness_assessment_payload(
    readiness: ActionReadiness,
    *,
    record_id: str,
    evidence_class: str,
    environment_namespace: str,
) -> dict[str, Any]:
    """Build and validate the canonical readiness contract from an immutable result."""
    references: dict[str, dict[str, Any]] = {}
    for result in readiness.gate_results:
        for reference in result.source_refs:
            plain = _plain_reference(reference)
            key = json.dumps(plain, sort_keys=True, separators=(",", ":"))
            references[key] = plain
    payload = {
        "schema_name": "qc2.time_operation.ReadinessAssessment.v1",
        "schema_version": "1.0",
        "id": record_id,
        "created_at": readiness.evaluated_at,
        "owning_authority": "safety",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": list(references.values()),
        "action": readiness.action.value,
        "status": readiness.status.value,
        "gate_results": [
            {
                "gate_id": result.gate_id,
                "status": result.status.value,
                "reason_codes": list(result.reason_codes),
                "evaluated_at": result.evaluated_at,
                "source_refs": [
                    _plain_reference(reference) for reference in result.source_refs
                ],
            }
            for result in readiness.gate_results
        ],
        "input_generation": readiness.input_generation,
        "freshness_deadline": readiness.freshness_deadline,
    }
    validate_contract("ReadinessAssessment", payload)
    return payload


def safety_protocol_definition_payload(
    policy: SafetyGatePolicy,
    *,
    record_id: str,
    created_at: str,
    evidence_class: str,
    environment_namespace: str,
    implementation_hash: str,
    source_refs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Materialize an immutable safety rule without inspecting code or the filesystem."""
    if not is_sha256(implementation_hash):
        raise SafetyViolation("implementation_hash must be a caller-supplied SHA-256 digest")
    if isinstance(source_refs, (str, bytes)) or not isinstance(source_refs, Sequence):
        raise SafetyViolation("source_refs must be a sequence")
    payload: dict[str, Any] = {
        "schema_name": "qc2.scientific_definitions.SafetyProtocolDefinition.v1",
        "schema_version": "1.0",
        "id": record_id,
        "created_at": created_at,
        "owning_authority": "safety",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [_plain_reference(reference) for reference in source_refs],
        "content_hash": "0" * 64,
        "protocol_key": policy.protocol_key,
        "version": policy.version,
        "action": policy.action.value,
        "rule": policy.rule,
        "required_evidence": list(policy.required_evidence),
        "warning_policy": policy.warning_policy.value,
        "implementation_hash": implementation_hash,
    }
    payload["content_hash"] = canonical_content_hash(
        "SafetyProtocolDefinition", payload
    )
    validate_contract("SafetyProtocolDefinition", payload)
    verify_content_hash("SafetyProtocolDefinition", payload)
    return payload


def safety_protocol_result_payload(
    policy: SafetyGatePolicy,
    result: GateEvaluation,
    definition: Mapping[str, Any],
    *,
    record_id: str,
    created_at: str,
    evidence_class: str,
    environment_namespace: str,
) -> dict[str, Any]:
    """Bind a gate result to its exact definition; UNAVAILABLE stays non-PASS."""
    definition_payload = dict(definition)
    validate_contract("SafetyProtocolDefinition", definition_payload)
    verify_content_hash("SafetyProtocolDefinition", definition_payload)
    if (
        definition_payload["protocol_key"] != policy.protocol_key
        or definition_payload["version"] != policy.version
        or definition_payload["action"] != policy.action.value
        or definition_payload["rule"] != policy.rule
        or definition_payload["required_evidence"] != list(policy.required_evidence)
        or definition_payload["warning_policy"] != policy.warning_policy.value
    ):
        raise SafetyViolation("protocol result definition does not match its gate policy")
    if result.gate_id != policy.gate_id or result.action is not policy.action:
        raise SafetyViolation("protocol result does not match its action-specific gate")

    protocol_result = (
        "UNKNOWN" if result.status is GateStatus.UNAVAILABLE else result.status.value
    )
    payload: dict[str, Any] = {
        "schema_name": "qc2.scientific_definitions.SafetyProtocolResult.v1",
        "schema_version": "1.0",
        "id": record_id,
        "created_at": created_at,
        "owning_authority": "safety",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [
            _plain_reference(reference) for reference in result.source_refs
        ],
        "content_hash": "0" * 64,
        "protocol_ref": {
            "target_schema_name": (
                "qc2.scientific_definitions.SafetyProtocolDefinition.v1"
            ),
            "target_id": definition_payload["id"],
            "content_hash": definition_payload["content_hash"],
        },
        "action": result.action.value,
        "result": protocol_result,
        "reason_codes": list(result.reason_codes),
        "observed_versions": list(result.observed_versions),
        "evaluated_at": result.evaluated_at,
        "freshness_deadline": result.freshness_deadline,
    }
    payload["content_hash"] = canonical_content_hash(
        "SafetyProtocolResult", payload
    )
    validate_contract("SafetyProtocolResult", payload)
    verify_content_hash("SafetyProtocolResult", payload)
    return payload
