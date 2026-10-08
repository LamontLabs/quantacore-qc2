"""Frozen action policies; runtime results never inherit gates across actions."""

from __future__ import annotations

from .models import (
    ActionPolicy,
    CapabilityDomain,
    SafetyAction,
    SafetyGatePolicy,
    WarningPolicy,
)


def _gate(
    action: SafetyAction,
    gate_id: str,
    domain: CapabilityDomain,
    evidence_key: str,
    rule: str,
) -> SafetyGatePolicy:
    return SafetyGatePolicy(
        gate_id=gate_id,
        action=action,
        domain=domain,
        rule=rule,
        required_evidence=(evidence_key,),
        warning_policy=WarningPolicy.NOT_ALLOWED,
    )


def _policy(
    action: SafetyAction,
    rows: tuple[tuple[str, CapabilityDomain, str, str], ...],
) -> ActionPolicy:
    return ActionPolicy(
        action=action,
        gates=tuple(
            _gate(action, gate_id, domain, evidence_key, rule)
            for gate_id, domain, evidence_key, rule in rows
        ),
    )


DEFAULT_ACTION_POLICIES = (
    _policy(
        SafetyAction.PREDICT,
        (
            (
                "clock_assessment",
                CapabilityDomain.TIME,
                "clock_assessment",
                "A trusted clock assessment is present and fresh at evaluation time.",
            ),
            (
                "data_capability",
                CapabilityDomain.DATA,
                "data_capability_manifest",
                "The required data capability evidence is present and current.",
            ),
            (
                "model_qualification",
                CapabilityDomain.MODEL,
                "model_qualification",
                "The selected model has current qualification evidence.",
            ),
            (
                "registry_compatibility",
                CapabilityDomain.REGISTRY,
                "registry_compatibility",
                "The model and active registry versions are compatible.",
            ),
            (
                "configuration_integrity",
                CapabilityDomain.CONFIGURATION,
                "effective_configuration",
                "The effective configuration is identified and integrity-checked.",
            ),
            (
                "evidence_append",
                CapabilityDomain.EVIDENCE,
                "evidence_append_capability",
                "The evidence authority can record this action's safety result.",
            ),
        ),
    ),
    _policy(
        SafetyAction.NEW_ENTRY,
        (
            (
                "clock_assessment",
                CapabilityDomain.TIME,
                "clock_assessment",
                "A trusted clock assessment is present and fresh at evaluation time.",
            ),
            (
                "prediction_seal",
                CapabilityDomain.PREDICTION_SEAL,
                "sealed_prediction",
                "The prediction is sealed and bound to the current input generation.",
            ),
            (
                "data_capability",
                CapabilityDomain.DATA,
                "data_capability_manifest",
                "The required data capability evidence is present and current.",
            ),
            (
                "model_qualification",
                CapabilityDomain.MODEL,
                "model_qualification",
                "The selected model has current qualification evidence.",
            ),
            (
                "registry_compatibility",
                CapabilityDomain.REGISTRY,
                "registry_compatibility",
                "The model and active registry versions are compatible.",
            ),
            (
                "configuration_integrity",
                CapabilityDomain.CONFIGURATION,
                "effective_configuration",
                "The effective configuration is identified and integrity-checked.",
            ),
            (
                "paper_broker_capability",
                CapabilityDomain.BROKER,
                "paper_account_capability",
                "The paper-only broker capability is explicitly available.",
            ),
            (
                "reconciliation_freshness",
                CapabilityDomain.RECONCILIATION,
                "reconciliation_snapshot",
                "The account and order reconciliation snapshot is fresh.",
            ),
            (
                "entry_strategy_limits",
                CapabilityDomain.STRATEGY,
                "entry_strategy_limits",
                "The effective strategy entry limits are identified.",
            ),
            (
                "reservation_authority",
                CapabilityDomain.RESERVATION,
                "reservation_record",
                "A current reservation is available for this entry action.",
            ),
            (
                "entry_pause_authority",
                CapabilityDomain.OWNER_AUTHORITY,
                "entry_pause_state",
                "The owner-controlled entry pause state is clear.",
            ),
            (
                "idempotency_record",
                CapabilityDomain.IDEMPOTENCY,
                "idempotency_key_record",
                "The operation has a durable idempotency identity.",
            ),
            (
                "evidence_append",
                CapabilityDomain.EVIDENCE,
                "evidence_append_capability",
                "The evidence authority can record this action's safety result.",
            ),
        ),
    ),
    _policy(
        SafetyAction.EXIT_POSITION,
        (
            (
                "clock_assessment",
                CapabilityDomain.TIME,
                "clock_assessment",
                "A trusted clock assessment is present and fresh at evaluation time.",
            ),
            (
                "position_identity",
                CapabilityDomain.IDENTITY,
                "position_identity",
                "The position identity and current ownership are known.",
            ),
            (
                "exit_policy",
                CapabilityDomain.STRATEGY,
                "exit_policy",
                "The applicable exit policy is identified and authorized.",
            ),
            (
                "paper_broker_capability",
                CapabilityDomain.BROKER,
                "paper_account_capability",
                "The paper-only broker capability is explicitly available.",
            ),
            (
                "reconciliation_freshness",
                CapabilityDomain.RECONCILIATION,
                "reconciliation_snapshot",
                "The account and order reconciliation snapshot is fresh.",
            ),
            (
                "idempotency_record",
                CapabilityDomain.IDEMPOTENCY,
                "idempotency_key_record",
                "The operation has a durable idempotency identity.",
            ),
            (
                "evidence_append",
                CapabilityDomain.EVIDENCE,
                "evidence_append_capability",
                "The evidence authority can record this action's safety result.",
            ),
        ),
    ),
    _policy(
        SafetyAction.CANCEL_ENTRY,
        (
            (
                "clock_assessment",
                CapabilityDomain.TIME,
                "clock_assessment",
                "A trusted clock assessment is present and fresh at evaluation time.",
            ),
            (
                "order_identity",
                CapabilityDomain.IDENTITY,
                "order_identity",
                "The target order identity and state are known.",
            ),
            (
                "cancellation_authority",
                CapabilityDomain.OWNER_AUTHORITY,
                "cancellation_authority",
                "The cancellation request is within the owner's authority.",
            ),
            (
                "paper_broker_capability",
                CapabilityDomain.BROKER,
                "paper_account_capability",
                "The paper-only broker capability is explicitly available.",
            ),
            (
                "reconciliation_freshness",
                CapabilityDomain.RECONCILIATION,
                "reconciliation_snapshot",
                "The account and order reconciliation snapshot is fresh.",
            ),
            (
                "idempotency_record",
                CapabilityDomain.IDEMPOTENCY,
                "idempotency_key_record",
                "The operation has a durable idempotency identity.",
            ),
            (
                "evidence_append",
                CapabilityDomain.EVIDENCE,
                "evidence_append_capability",
                "The evidence authority can record this action's safety result.",
            ),
        ),
    ),
    _policy(
        SafetyAction.PROMOTE,
        (
            (
                "clock_assessment",
                CapabilityDomain.TIME,
                "clock_assessment",
                "A trusted clock assessment is present and fresh at evaluation time.",
            ),
            (
                "candidate_bundle_identity",
                CapabilityDomain.MODEL,
                "candidate_bundle",
                "The exact candidate bundle is identified.",
            ),
            (
                "qualification_evidence",
                CapabilityDomain.MODEL,
                "promotion_qualification",
                "The candidate has current promotion qualification evidence.",
            ),
            (
                "registry_compatibility",
                CapabilityDomain.REGISTRY,
                "registry_compatibility",
                "The candidate and active registry versions are compatible.",
            ),
            (
                "configuration_integrity",
                CapabilityDomain.CONFIGURATION,
                "effective_configuration",
                "The effective configuration is identified and integrity-checked.",
            ),
            (
                "owner_approval",
                CapabilityDomain.OWNER_AUTHORITY,
                "owner_approval",
                "The owner approval applies to this exact candidate bundle.",
            ),
            (
                "epoch_boundary",
                CapabilityDomain.EPOCH,
                "epoch_boundary",
                "The promotion is within an authorized epoch boundary.",
            ),
            (
                "idempotency_record",
                CapabilityDomain.IDEMPOTENCY,
                "idempotency_key_record",
                "The operation has a durable idempotency identity.",
            ),
            (
                "evidence_append",
                CapabilityDomain.EVIDENCE,
                "evidence_append_capability",
                "The evidence authority can record this action's safety result.",
            ),
        ),
    ),
)


def policy_for_action(action: SafetyAction) -> ActionPolicy:
    """Return exactly one policy; absent or duplicate policies are errors."""
    normalized = SafetyAction(action)
    matches = tuple(
        policy for policy in DEFAULT_ACTION_POLICIES if policy.action is normalized
    )
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one policy for {normalized.value}, found {len(matches)}"
        )
    return matches[0]
