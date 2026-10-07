"""Pure, fail-closed configuration evaluation.

Callers validate wire objects and typed references with ``qc2_contracts`` before
using these cross-object authority checks. No function in this module resolves a
secret, performs I/O, or writes evidence.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
_SHA256 = r"[0-9a-f]{64}"
_BOUNDARIES = {
    "C0": re.compile(rf"^RELEASE:{_SHA256}$"),
    "C1": re.compile(rf"^RELEASE:{_SHA256}$"),
    "C2": re.compile(rf"^NEW_EPOCH:(\d{{4}}-\d{{2}}-\d{{2}}):({_SHA256})$"),
    "C3": re.compile(rf"^OWNER_APPROVAL:(\d{{4}}-\d{{2}}-\d{{2}}):({_SHA256})$"),
}
_CAPITAL_LIMIT_FIELDS = {
    "maximum_position_cost",
    "maximum_position_fraction",
    "maximum_gross_exposure",
    "daily_loss_limit",
    "maximum_concurrent_positions",
    "cash_reserve",
    "participation_limit",
}
_CAPITAL_LIMIT_DIRECTIONS = {
    "maximum_position_cost": "upper",
    "maximum_position_fraction": "upper",
    "maximum_gross_exposure": "upper",
    "daily_loss_limit": "upper",
    "maximum_concurrent_positions": "upper",
    "cash_reserve": "lower",
    "participation_limit": "upper",
}
_FIXTURE_HASHES = {"a" * 64}
_BUDGET_FIELDS = {
    "experiments": "max_experiments",
    "concurrent_jobs": "max_concurrent_jobs",
    "elapsed_seconds": "max_elapsed_seconds",
    "cpu_seconds": "max_cpu_seconds",
    "memory_bytes": "max_memory_bytes",
    "artifact_bytes": "max_artifact_bytes",
    "cost_minor_units": "authorized_cost_minor_units",
}
_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "secret_value",
    "token",
}
_ACTIONS = {
    "configuration_manifest_missing": "Publish an authoritative manifest scoped to this capability.",
    "configuration_manifest_duplicate": "Retain one effective manifest per configuration domain and capability.",
    "fixture_configuration_forbidden": "Replace fixture-only configuration with reviewed, production-qualified evidence.",
    "required_setting_missing": "Publish the required authoritative setting at or before the effective session.",
    "duplicate_authoritative_setting": "Keep exactly one effective definition for this setting key.",
    "setting_not_bound_by_manifest": "Reference the effective setting from the configuration manifest and recompute its hash.",
    "setting_domain_mismatch": "Move the setting to the manifest's configuration domain or correct the manifest reference.",
    "setting_capability_mismatch": "Scope the setting to this capability or remove it from this manifest.",
    "owner_approval_required": "Attach a verified owner-approval reference before using this owner-policy value.",
    "measurement_evidence_required": "Attach capability-measurement evidence before enabling this capability.",
    "secret_reference_missing": "Publish a versioned secret reference for this capability; never copy the secret value.",
    "secret_unavailable": "Provide the referenced secret through the configured secret store for this environment.",
    "resource_budget_missing": "Publish a bounded resource budget for this capability.",
    "resource_budget_unavailable": "Reference an effective resource budget in the configuration manifest.",
    "resource_budget_unapproved": "Obtain the required owner approval before authorizing nonzero cost.",
    "unresolved_decision": "Resolve the linked typed decision with its named authority and required evidence.",
    "decision_record_missing": "Restore the referenced typed decision record before evaluating this capability.",
    "invalid_required_keys": "Remove duplicate or malformed required keys from the configuration manifest.",
    "owner_identity_unsigned": "Obtain the required owner signature for this identity configuration.",
    "production_required_setting_unlisted": "List every production-required setting in the manifest and bind its exact version.",
}


class ConfigurationPolicyError(ValueError):
    """A stable, non-sensitive configuration policy failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CapabilityGate:
    capability_id: str
    enabled: bool
    reason_codes: tuple[str, ...]
    actions: tuple[str, ...]


@dataclass(frozen=True)
class BudgetAssessment:
    allowed: bool
    reason_codes: tuple[str, ...]
    action: str | None


def _valid_session(value: Any) -> date:
    if not isinstance(value, str):
        raise ConfigurationPolicyError("invalid_effective_session")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigurationPolicyError("invalid_effective_session") from exc
    if parsed.isoformat() != value:
        raise ConfigurationPolicyError("invalid_effective_session")
    return parsed


def _valid_slug(value: Any) -> bool:
    return isinstance(value, str) and _SLUG.fullmatch(value) is not None


def _target_id(reference: Any, schema_name: str) -> str | None:
    if not isinstance(reference, Mapping):
        return None
    if reference.get("target_schema_name") != schema_name:
        return None
    value = reference.get("target_id")
    return value if isinstance(value, str) else None


def _blocked(
    reasons: dict[str, set[str]], capability_id: str, code: str
) -> None:
    reasons[capability_id].add(code)


def _production_fixture(payload: Mapping[str, Any]) -> bool:
    if payload.get("fixture_only") is True or payload.get(
        "evidence_class"
    ) == "SYNTHETIC_FIXTURE":
        return True
    return any(
        payload.get(field) in _FIXTURE_HASHES
        for field in ("content_hash", "policy_hash", "value_hash")
    )


def assess_configuration(
    *,
    manifests: Iterable[Mapping[str, Any]],
    settings: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    secret_references: Iterable[Mapping[str, Any]],
    resource_budgets: Iterable[Mapping[str, Any]],
    required_capabilities: Iterable[str],
    environment_namespace: str,
    effective_session: str,
    available_secret_key_names: Iterable[str] | None = None,
) -> dict[str, CapabilityGate]:
    """Assess each requested capability independently.

    A configuration failure is assigned only to the affected capability scope.
    The supplied manifest, setting, decision, secret-reference, and budget
    objects must already have passed their generated schema/reference validators.
    """
    session = _valid_session(effective_session)
    capabilities = tuple(dict.fromkeys(required_capabilities))
    if any(not _valid_slug(capability) for capability in capabilities):
        raise ConfigurationPolicyError("invalid_capability_id")

    manifest_rows = [
        row
        for row in manifests
        if row.get("environment_namespace") == environment_namespace
        and _valid_session(row.get("effective_from")) <= session
    ]
    setting_rows = [
        row
        for row in settings
        if row.get("environment_namespace") == environment_namespace
        and _valid_session(row.get("effective_from")) <= session
    ]
    decision_by_id = {
        row.get("id"): row for row in decisions if isinstance(row.get("id"), str)
    }
    secret_by_id = {
        row.get("id"): row
        for row in secret_references
        if isinstance(row.get("id"), str)
    }
    budget_by_id = {
        row.get("id"): row
        for row in resource_budgets
        if isinstance(row.get("id"), str)
        and row.get("environment_namespace") == environment_namespace
        and _valid_session(row.get("effective_from")) <= session
    }
    available_secrets = (
        None
        if available_secret_key_names is None
        else frozenset(available_secret_key_names)
    )
    reasons: dict[str, set[str]] = defaultdict(set)

    for capability in capabilities:
        applicable = [
            row
            for row in manifest_rows
            if capability in row.get("capability_scope", [])
        ]
        if not applicable:
            _blocked(reasons, capability, "configuration_manifest_missing")
            continue

        by_domain: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for manifest in applicable:
            by_domain[str(manifest.get("configuration_domain"))].append(manifest)

        selected_manifests: list[Mapping[str, Any]] = []
        for domain_rows in by_domain.values():
            latest_session = max(
                _valid_session(row.get("effective_from")) for row in domain_rows
            )
            latest_rows = [
                row
                for row in domain_rows
                if _valid_session(row.get("effective_from")) == latest_session
            ]
            if len(latest_rows) != 1:
                _blocked(reasons, capability, "configuration_manifest_duplicate")
                continue
            selected_manifests.append(latest_rows[0])

        for manifest in selected_manifests:
            domain = manifest.get("configuration_domain")
            if environment_namespace == "production" and _production_fixture(manifest):
                _blocked(reasons, capability, "fixture_configuration_forbidden")

            if domain == "OWNER_IDENTITY" and manifest.get("signed_by_owner") is not True:
                _blocked(reasons, capability, "owner_identity_unsigned")

            required_keys = manifest.get("required_setting_keys", [])
            if (
                not isinstance(required_keys, list)
                or any(not _valid_slug(key) for key in required_keys)
                or len(required_keys) != len(set(required_keys))
            ):
                _blocked(reasons, capability, "invalid_required_keys")
                required_keys = []

            setting_refs = manifest.get("setting_refs", [])
            bound_ids = {
                target_id
                for reference in setting_refs
                if (
                    target_id := _target_id(
                        reference, "qc2.integrity_build.ConfigurationSetting.v1"
                    )
                )
            }
            for bound_setting in setting_rows:
                if (
                    bound_setting.get("id") in bound_ids
                    and bound_setting.get("configuration_domain") == domain
                    and bound_setting.get("production_required") is True
                    and bound_setting.get("setting_key") not in required_keys
                ):
                    _blocked(
                        reasons, capability, "production_required_setting_unlisted"
                    )

            for key in required_keys:
                key_rows = [
                    row for row in setting_rows if row.get("setting_key") == key
                ]
                domain_rows = [
                    row
                    for row in key_rows
                    if row.get("configuration_domain") == domain
                ]
                if not domain_rows:
                    code = "setting_domain_mismatch" if key_rows else "required_setting_missing"
                    _blocked(reasons, capability, code)
                    continue

                latest_session = max(
                    _valid_session(row.get("effective_from")) for row in domain_rows
                )
                latest_rows = [
                    row
                    for row in domain_rows
                    if _valid_session(row.get("effective_from")) == latest_session
                ]
                if len(latest_rows) != 1:
                    _blocked(reasons, capability, "duplicate_authoritative_setting")
                    continue
                setting = latest_rows[0]
                if setting.get("id") not in bound_ids:
                    _blocked(reasons, capability, "setting_not_bound_by_manifest")

                setting_caps = setting.get("required_capabilities", [])
                if setting_caps and capability not in setting_caps:
                    _blocked(reasons, capability, "setting_capability_mismatch")

                if environment_namespace == "production" and _production_fixture(setting):
                    _blocked(reasons, capability, "fixture_configuration_forbidden")

                if (
                    setting.get("value_class") == "OWNER_POLICY_REQUIRED"
                    and setting.get("owner_approval_ref") is None
                ):
                    _blocked(reasons, capability, "owner_approval_required")

                if (
                    setting.get("value_class") == "CAPABILITY_MEASUREMENT_REQUIRED"
                    and not setting.get("source_refs")
                ):
                    _blocked(reasons, capability, "measurement_evidence_required")

                secret_ref = setting.get("secret_reference_ref")
                if domain == "SECRETS" and secret_ref is None:
                    _blocked(reasons, capability, "secret_reference_missing")
                elif secret_ref is not None:
                    secret_id = _target_id(
                        secret_ref, "qc2.integrity_build.SecretReference.v1"
                    )
                    secret = secret_by_id.get(secret_id)
                    if (
                        secret is None
                        or secret.get("environment_namespace") != environment_namespace
                    ):
                        _blocked(reasons, capability, "secret_reference_missing")
                    elif environment_namespace == "production" and _production_fixture(
                        secret
                    ):
                        _blocked(reasons, capability, "fixture_configuration_forbidden")
                    elif (
                        environment_namespace == "production"
                        and available_secrets is None
                    ) or (
                        available_secrets is not None
                        and secret.get("secret_key_name") not in available_secrets
                    ):
                        _blocked(reasons, capability, "secret_unavailable")

                budget_ref = setting.get("resource_budget_ref")
                if (
                    setting.get("value_class") == "ENGINEERING_LIMIT_REQUIRED"
                    and budget_ref is None
                ):
                    _blocked(reasons, capability, "resource_budget_missing")
                elif budget_ref is not None:
                    budget_id = _target_id(
                        budget_ref, "qc2.integrity_build.ResourceBudget.v1"
                    )
                    budget = budget_by_id.get(budget_id)
                    if (
                        budget is None
                        or budget.get("configuration_domain") != domain
                    ):
                        _blocked(reasons, capability, "resource_budget_unavailable")
                    elif environment_namespace == "production" and _production_fixture(
                        budget
                    ):
                        _blocked(reasons, capability, "fixture_configuration_forbidden")

            if domain in {"RESEARCH", "DEPLOYMENT"}:
                budget_refs = manifest.get("resource_budget_refs", [])
                if not budget_refs:
                    _blocked(reasons, capability, "resource_budget_missing")
                for reference in budget_refs:
                    budget_id = _target_id(
                        reference, "qc2.integrity_build.ResourceBudget.v1"
                    )
                    budget = budget_by_id.get(budget_id)
                    if (
                        budget is None
                        or budget.get("configuration_domain") != domain
                        or budget.get("environment_namespace") != environment_namespace
                    ):
                        _blocked(reasons, capability, "resource_budget_unavailable")
                    elif environment_namespace == "production" and _production_fixture(
                        budget
                    ):
                        _blocked(reasons, capability, "fixture_configuration_forbidden")
                    elif (
                        budget.get("authorized_cost_minor_units", 0) > 0
                        and budget.get("owner_approval_ref") is None
                    ):
                        _blocked(reasons, capability, "resource_budget_unapproved")

            if environment_namespace == "production":
                for reference in manifest.get("unresolved_decision_refs", []):
                    decision_id = _target_id(
                        reference, "qc2.integrity_build.UnknownDecision.v1"
                    )
                    decision = decision_by_id.get(decision_id)
                    if decision is None:
                        _blocked(reasons, capability, "decision_record_missing")
                        continue
                    if _production_fixture(decision):
                        _blocked(reasons, capability, "fixture_configuration_forbidden")
                        continue
                    if decision.get("decision_state") != "UNRESOLVED":
                        continue
                    affected = decision.get("affected_capabilities", [])
                    if (
                        not affected
                        or capability in affected
                        or decision.get("decision_key") in required_keys
                    ):
                        _blocked(reasons, capability, "unresolved_decision")

    return {
        capability: CapabilityGate(
            capability_id=capability,
            enabled=not reasons[capability],
            reason_codes=tuple(sorted(reasons[capability])),
            actions=tuple(
                _ACTIONS[code]
                for code in sorted(reasons[capability])
                if code in _ACTIONS
            ),
        )
        for capability in capabilities
    }


def assess_resource_budget(
    budget: Mapping[str, Any],
    usage: Mapping[str, Any],
    *,
    environment_namespace: str,
) -> BudgetAssessment:
    """Block only the resource-consuming capability whose measured budget is invalid."""
    reasons: set[str] = set()
    if environment_namespace == "production" and _production_fixture(budget):
        reasons.add("fixture_budget_forbidden")
    if (
        budget.get("authorized_cost_minor_units", 0) > 0
        and budget.get("owner_approval_ref") is None
    ):
        reasons.add("resource_budget_unapproved")

    for usage_key, budget_key in _BUDGET_FIELDS.items():
        used = usage.get(usage_key)
        limit = budget.get(budget_key)
        if (
            not isinstance(used, int)
            or isinstance(used, bool)
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or used < 0
            or limit < 0
        ):
            reasons.add("budget_usage_unavailable")
        elif used > limit:
            reasons.add("resource_budget_exhausted")

    actions = {
        "fixture_budget_forbidden": "Replace the fixture budget with a production-qualified budget.",
        "resource_budget_unapproved": "Obtain owner approval before authorizing nonzero cost.",
        "budget_usage_unavailable": "Measure every bounded resource before starting this workload.",
        "resource_budget_exhausted": "Pause this workload, preserve evidence, and request an explicit budget revision.",
    }
    ordered = tuple(sorted(reasons))
    return BudgetAssessment(
        allowed=not ordered,
        reason_codes=ordered,
        action=actions[ordered[0]] if ordered else None,
    )


def _decimal_value(value: Any) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(
        r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value
    ):
        raise ConfigurationPolicyError("invalid_exact_decimal")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ConfigurationPolicyError("invalid_exact_decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ConfigurationPolicyError("invalid_nonnegative_cap")
    return parsed


def validate_research_capital_limits(
    research_limits: Mapping[str, Any], owner_policy: Mapping[str, Any]
) -> None:
    """Reject research overrides or values above the separately owned capital policy."""
    if not research_limits:
        return
    if not set(research_limits).issubset(_CAPITAL_LIMIT_FIELDS):
        raise ConfigurationPolicyError("research_cannot_override_owner_policy")

    for field in research_limits:
        candidate = research_limits[field]
        owner_limit = owner_policy.get(field)
        if _CAPITAL_LIMIT_DIRECTIONS[field] == "upper":
            if field == "maximum_concurrent_positions":
                if (
                    not isinstance(candidate, int)
                    or isinstance(candidate, bool)
                    or not isinstance(owner_limit, int)
                    or isinstance(owner_limit, bool)
                    or candidate < 0
                    or owner_limit < 0
                ):
                    raise ConfigurationPolicyError("invalid_owner_cap")
                if candidate > owner_limit:
                    raise ConfigurationPolicyError("research_widens_owner_cap")
                continue
            if _decimal_value(candidate) > _decimal_value(owner_limit):
                raise ConfigurationPolicyError("research_widens_owner_cap")
        else:
            if field == "maximum_concurrent_positions":
                raise ConfigurationPolicyError("invalid_owner_cap")
            if (
                _decimal_value(candidate) < _decimal_value(owner_limit)
            ):
                raise ConfigurationPolicyError("research_widens_owner_cap")


def validate_change_request_boundary(
    change: Mapping[str, Any], *, current_session: str
) -> None:
    """Validate the required class-specific effective-boundary encoding."""
    now = _valid_session(current_session)

    change_class = change.get("change_class")
    boundary = change.get("effective_boundary")
    if change_class == "C4":
        if boundary != "IMMEDIATE_RESTRICTIVE" or change.get(
            "is_restrictive_only"
        ) is not True:
            raise ConfigurationPolicyError("c4_must_be_restrictive")
        return

    pattern = _BOUNDARIES.get(change_class)
    match = pattern.fullmatch(boundary) if pattern and isinstance(boundary, str) else None
    if match is None:
        raise ConfigurationPolicyError("invalid_change_boundary")

    if change_class == "C1" and not change.get("test_refs"):
        raise ConfigurationPolicyError("c1_equivalence_tests_required")
    if change_class == "C2":
        target_session = _valid_session(match.group(1))
        if target_session < now:
            raise ConfigurationPolicyError("new_epoch_boundary_is_past")
    if change_class == "C3":
        target_session = _valid_session(match.group(1))
        if target_session < now:
            raise ConfigurationPolicyError("owner_approval_boundary_is_past")
        approval_ref = change.get("owner_approval_ref")
        if (
            not isinstance(approval_ref, Mapping)
            or approval_ref.get("content_hash") != match.group(2)
        ):
            raise ConfigurationPolicyError("owner_approval_reference_mismatch")


def safe_configuration_audit_payload(
    manifest: Mapping[str, Any],
    settings: Iterable[Mapping[str, Any]],
    gates: Iterable[CapabilityGate],
) -> dict[str, Any]:
    """Build an allowlisted evidence/log payload containing hashes, never values."""
    setting_rows = []
    for setting in settings:
        row: dict[str, Any] = {
            "setting_key": setting.get("setting_key"),
            "version": setting.get("version"),
            "value_hash": setting.get("value_hash"),
            "evidence_class": setting.get("evidence_class"),
            "fixture_only": setting.get("fixture_only"),
        }
        secret_ref = setting.get("secret_reference_ref")
        if isinstance(secret_ref, Mapping) and isinstance(
            secret_ref.get("content_hash"), str
        ):
            row["secret_reference_hash"] = secret_ref["content_hash"]
        setting_rows.append(row)

    payload = {
        "event_type": "configuration_gate_assessed",
        "configuration_domain": manifest.get("configuration_domain"),
        "configuration_version": manifest.get("version"),
        "configuration_hash": manifest.get("content_hash"),
        "policy_hash": manifest.get("policy_hash"),
        "settings": setting_rows,
        "capabilities": [
            {
                "capability_id": gate.capability_id,
                "enabled": gate.enabled,
                "reason_codes": list(gate.reason_codes),
                "actions": list(gate.actions),
            }
            for gate in gates
        ],
    }
    return payload


def assert_secret_free_output(
    payload: Any, secret_values: Sequence[str] = ()
) -> None:
    """Reject secret-bearing fields or known secret material without echoing it."""
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    for secret in secret_values:
        if secret and secret in serialized:
            raise ConfigurationPolicyError("secret_material_in_output")

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                normalized = str(key).lower()
                safe_reference_key = normalized in {
                    "secret_reference_hash",
                    "secret_reference_hashes",
                }
                if not safe_reference_key and (
                    normalized in _SENSITIVE_KEYS
                    or any(
                        marker in normalized
                        for marker in ("password", "api_key", "private_key", "token")
                    )
                    or normalized.endswith("_secret_value")
                ):
                    raise ConfigurationPolicyError("sensitive_output_field")
                walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child)

    walk(payload)
