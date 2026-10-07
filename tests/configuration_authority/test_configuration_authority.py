from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qc2_configuration_authority import (
    ConfigurationPolicyError,
    assess_configuration,
    assess_resource_budget,
    assert_secret_free_output,
    safe_configuration_audit_payload,
    validate_change_request_boundary,
    validate_research_capital_limits,
)

ROOT = Path(__file__).resolve().parents[2]
SETTING_SCHEMA = "qc2.integrity_build.ConfigurationSetting.v1"
SECRET_SCHEMA = "qc2.integrity_build.SecretReference.v1"
BUDGET_SCHEMA = "qc2.integrity_build.ResourceBudget.v1"
DECISION_SCHEMA = "qc2.integrity_build.UnknownDecision.v1"
SESSION = "2026-10-07"


def _reference(schema_name: str, target_id: str, content_hash: str = "a" * 64) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": target_id,
        "content_hash": content_hash,
    }


def _setting(
    key: str,
    target_id: str,
    *,
    domain: str = "RESEARCH",
    evidence_class: str = "FORWARD_OPERATIONAL",
    fixture_only: bool = False,
    value_class: str = "ARCHITECTURAL_CONSTANT",
    required_capabilities: list[str] | None = None,
    secret_reference_ref: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "id": target_id,
        "setting_key": key,
        "configuration_domain": domain,
        "environment_namespace": "production",
        "effective_from": "2026-10-01",
        "version": 1,
        "value_hash": "b" * 64,
        "value_class": value_class,
        "value_authority": "configuration",
        "required_capabilities": required_capabilities or [],
        "production_required": True,
        "fixture_only": fixture_only,
        "evidence_class": evidence_class,
        "source_refs": [{"target_schema_name": "qc2.integrity_build.EvidenceEvent.v1"}]
        if value_class == "CAPABILITY_MEASUREMENT_REQUIRED"
        else [],
        "secret_reference_ref": secret_reference_ref,
        "resource_budget_ref": None,
        "owner_approval_ref": {"target_schema_name": "qc2.governance_owner.OwnerCommandReceipt.v1"}
        if value_class == "OWNER_POLICY_REQUIRED"
        else None,
        "content_hash": "c" * 64,
    }


def _manifest(
    domain: str,
    capability: str,
    required_keys: list[str],
    settings: list[dict[str, Any]],
    *,
    evidence_class: str = "FORWARD_OPERATIONAL",
    fixture_only: bool = False,
    decision_refs: list[dict[str, str]] | None = None,
    budget_refs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"018f0000-0000-7000-8000-000000000{len(capability):03d}",
        "configuration_domain": domain,
        "environment_namespace": "production",
        "effective_from": "2026-10-01",
        "version": 1,
        "capability_scope": [capability],
        "required_setting_keys": required_keys,
        "setting_refs": [
            _reference(SETTING_SCHEMA, setting["id"], setting["content_hash"])
            for setting in settings
            if setting["configuration_domain"] == domain
        ],
        "resource_budget_refs": budget_refs or [],
        "unresolved_decision_refs": decision_refs or [],
        "policy_hash": "d" * 64,
        "content_hash": "e" * 64,
        "evidence_class": evidence_class,
        "fixture_only": fixture_only,
        "signed_by_owner": False,
    }


def _resource_budget(target_id: str) -> dict[str, Any]:
    return {
        "id": target_id,
        "configuration_domain": "RESEARCH",
        "environment_namespace": "production",
        "effective_from": "2026-10-01",
        "budget_key": "research_compute",
        "version": 1,
        "max_experiments": 3,
        "max_concurrent_jobs": 2,
        "max_elapsed_seconds": 600,
        "max_cpu_seconds": 1200,
        "max_memory_bytes": 2_000_000,
        "max_artifact_bytes": 500_000,
        "authorized_cost_minor_units": 0,
        "owner_approval_ref": None,
        "fixture_only": False,
        "evidence_class": "FORWARD_OPERATIONAL",
        "content_hash": "f" * 64,
    }


def _assess(
    manifests: list[dict[str, Any]],
    settings: list[dict[str, Any]],
    *,
    capabilities: list[str],
    decisions: list[dict[str, Any]] | None = None,
    secret_references: list[dict[str, Any]] | None = None,
    resource_budgets: list[dict[str, Any]] | None = None,
    available_secret_key_names: list[str] | None = None,
):
    return assess_configuration(
        manifests=manifests,
        settings=settings,
        decisions=decisions or [],
        secret_references=secret_references or [],
        resource_budgets=resource_budgets or [],
        required_capabilities=capabilities,
        environment_namespace="production",
        effective_session=SESSION,
        available_secret_key_names=available_secret_key_names,
    )


def test_duplicate_authoritative_settings_block_only_their_capability() -> None:
    duplicate_a = _setting("research_budget", "018f0000-0000-7000-8000-000000000101")
    duplicate_b = _setting("research_budget", "018f0000-0000-7000-8000-000000000102")
    budget = _resource_budget("018f0000-0000-7000-8000-000000000113")
    status = _setting(
        "status_feed",
        "018f0000-0000-7000-8000-000000000103",
        domain="SYSTEM",
        required_capabilities=["read_status"],
    )
    manifests = [
        _manifest(
            "RESEARCH",
            "research_run",
            ["research_budget"],
            [duplicate_a, duplicate_b],
            budget_refs=[_reference(BUDGET_SCHEMA, budget["id"], budget["content_hash"])],
        ),
        _manifest("SYSTEM", "read_status", ["status_feed"], [status]),
    ]

    gates = _assess(
        manifests,
        [duplicate_a, duplicate_b, status],
        capabilities=["research_run", "read_status"],
        resource_budgets=[budget],
    )

    assert gates["research_run"].enabled is False
    assert "duplicate_authoritative_setting" in gates["research_run"].reason_codes
    assert gates["read_status"].enabled is True


def test_missing_setting_and_unresolved_decision_are_actionable_and_scoped() -> None:
    status = _setting(
        "status_feed",
        "018f0000-0000-7000-8000-000000000104",
        domain="SYSTEM",
        required_capabilities=["read_status"],
    )
    decision = {
        "id": "018f0000-0000-7000-8000-000000000105",
        "decision_key": "paper_capital",
        "decision_state": "UNRESOLVED",
        "affected_capabilities": ["paper_execution"],
    }
    manifests = [
        _manifest(
            "STRATEGY",
            "paper_execution",
            ["paper_capital"],
            [],
            decision_refs=[_reference(DECISION_SCHEMA, decision["id"])],
        ),
        _manifest("SYSTEM", "read_status", ["status_feed"], [status]),
    ]

    gates = _assess(
        manifests,
        [status],
        capabilities=["paper_execution", "read_status"],
        decisions=[decision],
    )

    assert gates["paper_execution"].enabled is False
    assert "required_setting_missing" in gates["paper_execution"].reason_codes
    assert "unresolved_decision" in gates["paper_execution"].reason_codes
    assert gates["paper_execution"].actions
    assert gates["read_status"].enabled is True


def test_production_rejects_fixture_hashes_even_when_manifest_is_retagged() -> None:
    fixture = _setting(
        "calibrated_threshold",
        "018f0000-0000-7000-8000-000000000106",
        domain="EPOCH_SCIENTIFIC",
        evidence_class="FORWARD_OPERATIONAL",
        fixture_only=False,
    )
    fixture["content_hash"] = "a" * 64
    manifest = _manifest(
        "EPOCH_SCIENTIFIC", "prediction_ready", ["calibrated_threshold"], [fixture]
    )
    manifest["content_hash"] = "a" * 64
    manifest["policy_hash"] = "a" * 64

    gate = _assess(
        [manifest], [fixture], capabilities=["prediction_ready"]
    )["prediction_ready"]

    assert gate.enabled is False
    assert "fixture_configuration_forbidden" in gate.reason_codes


def test_production_required_setting_cannot_be_omitted_from_manifest_keys() -> None:
    setting = _setting(
        "production_risk_cap",
        "018f0000-0000-7000-8000-000000000114",
        domain="STRATEGY",
    )
    manifest = _manifest("STRATEGY", "paper_execution", [], [setting])

    gate = _assess([manifest], [setting], capabilities=["paper_execution"])[
        "paper_execution"
    ]

    assert gate.enabled is False
    assert "production_required_setting_unlisted" in gate.reason_codes


def test_missing_research_budget_blocks_only_research_capability() -> None:
    status = _setting(
        "health_status",
        "018f0000-0000-7000-8000-000000000115",
        domain="SYSTEM",
        required_capabilities=["read_status"],
    )
    manifests = [
        _manifest("RESEARCH", "research_run", [], []),
        _manifest("SYSTEM", "read_status", ["health_status"], [status]),
    ]

    gates = _assess(
        manifests, [status], capabilities=["research_run", "read_status"]
    )

    assert gates["research_run"].enabled is False
    assert "resource_budget_missing" in gates["research_run"].reason_codes
    assert gates["read_status"].enabled is True


def test_unreferenced_setting_does_not_satisfy_a_manifest() -> None:
    setting = _setting("strategy_version", "018f0000-0000-7000-8000-000000000107")
    manifest = _manifest("RESEARCH", "research_run", ["strategy_version"], [setting])
    manifest["setting_refs"] = []

    gate = _assess([manifest], [setting], capabilities=["research_run"])["research_run"]

    assert gate.enabled is False
    assert "setting_not_bound_by_manifest" in gate.reason_codes


def test_secret_reference_is_required_and_secret_values_never_enter_audit_output() -> None:
    secret_id = "018f0000-0000-7000-8000-000000000108"
    secret = {
        "id": secret_id,
        "secret_key_name": "ALPACA_API_KEY",
        "environment_namespace": "production",
        "evidence_class": "FORWARD_OPERATIONAL",
    }
    setting = _setting(
        "market_data_credential",
        "018f0000-0000-7000-8000-000000000109",
        domain="SECRETS",
        required_capabilities=["market_data"],
        secret_reference_ref=_reference(SECRET_SCHEMA, secret_id, "f" * 64),
    )
    setting["secret_value"] = "never-log-this-secret"
    manifest = _manifest("SECRETS", "market_data", ["market_data_credential"], [setting])

    gate = _assess(
        [manifest],
        [setting],
        capabilities=["market_data"],
        secret_references=[secret],
        available_secret_key_names=["ALPACA_API_KEY"],
    )["market_data"]
    payload = safe_configuration_audit_payload(manifest, [setting], [gate])

    assert gate.enabled is True
    assert "secret_value" not in json.dumps(payload)
    assert "never-log-this-secret" not in json.dumps(payload)
    assert_secret_free_output(payload, ["never-log-this-secret"])
    with pytest.raises(ConfigurationPolicyError, match="secret_material_in_output"):
        assert_secret_free_output(
            {"message": "never-log-this-secret"}, ["never-log-this-secret"]
        )

    schema = json.loads(
        (ROOT / "packages/contracts/schemas/v1/SecretReference.schema.json").read_text()
    )
    assert "secret_value" not in schema["properties"]
    assert schema["additionalProperties"] is False


def test_secret_unavailable_blocks_only_the_secret_dependent_capability() -> None:
    secret_id = "018f0000-0000-7000-8000-000000000110"
    secret = {
        "id": secret_id,
        "secret_key_name": "MARKET_FEED_TOKEN",
        "environment_namespace": "production",
    }
    setting = _setting(
        "market_feed_token",
        "018f0000-0000-7000-8000-000000000111",
        domain="SECRETS",
        required_capabilities=["market_data"],
        secret_reference_ref=_reference(SECRET_SCHEMA, secret_id),
    )
    status = _setting(
        "health_status",
        "018f0000-0000-7000-8000-000000000112",
        domain="SYSTEM",
        required_capabilities=["read_status"],
    )
    manifests = [
        _manifest("SECRETS", "market_data", ["market_feed_token"], [setting]),
        _manifest("SYSTEM", "read_status", ["health_status"], [status]),
    ]

    gates = _assess(
        manifests,
        [setting, status],
        capabilities=["market_data", "read_status"],
        secret_references=[secret],
        available_secret_key_names=[],
    )

    assert gates["market_data"].enabled is False
    assert "secret_unavailable" in gates["market_data"].reason_codes
    assert gates["read_status"].enabled is True


def test_research_limits_may_not_override_or_widen_owner_policy() -> None:
    owner_policy = {
        "maximum_position_cost": "1000.00",
        "maximum_position_fraction": "0.100000000000",
        "maximum_gross_exposure": "5000.00",
        "maximum_concurrent_positions": 4,
        "daily_loss_limit": "500.00",
        "cash_reserve": "1000.00",
        "participation_limit": "0.100000000000",
    }
    validate_research_capital_limits({}, owner_policy)
    validate_research_capital_limits(
        {
            "maximum_position_cost": "900.00",
            "maximum_position_fraction": "0.050000000000",
            "maximum_gross_exposure": "4500.00",
            "maximum_concurrent_positions": 3,
            "daily_loss_limit": "400.00",
            "cash_reserve": "1200.00",
            "participation_limit": "0.050000000000",
        },
        owner_policy,
    )

    with pytest.raises(ConfigurationPolicyError, match="research_widens_owner_cap"):
        validate_research_capital_limits(
            {"maximum_position_cost": "1000.01"}, owner_policy
        )
    with pytest.raises(ConfigurationPolicyError, match="research_widens_owner_cap"):
        validate_research_capital_limits({"cash_reserve": "999.99"}, owner_policy)
    with pytest.raises(ConfigurationPolicyError, match="research_widens_owner_cap"):
        validate_research_capital_limits({"daily_loss_limit": "500.01"}, owner_policy)
    with pytest.raises(ConfigurationPolicyError, match="research_widens_owner_cap"):
        validate_research_capital_limits(
            {"participation_limit": "0.100000000001"}, owner_policy
        )
    with pytest.raises(
        ConfigurationPolicyError, match="research_cannot_override_owner_policy"
    ):
        validate_research_capital_limits(
            {"paper_starting_capital": "100000.00"}, owner_policy
        )


def _budget(*, authorized_cost: int = 0, approval: Any = None) -> dict[str, Any]:
    return {
        "max_experiments": 3,
        "max_concurrent_jobs": 2,
        "max_elapsed_seconds": 600,
        "max_cpu_seconds": 1200,
        "max_memory_bytes": 2_000_000,
        "max_artifact_bytes": 500_000,
        "authorized_cost_minor_units": authorized_cost,
        "owner_approval_ref": approval,
        "fixture_only": False,
        "evidence_class": "FORWARD_OPERATIONAL",
    }


def _usage(**overrides: int) -> dict[str, int]:
    result = {
        "experiments": 2,
        "concurrent_jobs": 1,
        "elapsed_seconds": 300,
        "cpu_seconds": 700,
        "memory_bytes": 1_000_000,
        "artifact_bytes": 250_000,
        "cost_minor_units": 0,
    }
    result.update(overrides)
    return result


def test_resource_budget_exhaustion_and_unapproved_spend_block_work() -> None:
    budget = _budget()
    assert assess_resource_budget(
        budget, _usage(), environment_namespace="production"
    ).allowed

    exhausted = assess_resource_budget(
        budget, _usage(experiments=4), environment_namespace="production"
    )
    assert exhausted.allowed is False
    assert "resource_budget_exhausted" in exhausted.reason_codes
    assert exhausted.action

    unapproved = assess_resource_budget(
        _budget(authorized_cost=100),
        _usage(cost_minor_units=1),
        environment_namespace="production",
    )
    assert unapproved.allowed is False
    assert "resource_budget_unapproved" in unapproved.reason_codes

    approved = assess_resource_budget(
        _budget(
            authorized_cost=100,
            approval={"target_schema_name": "qc2.owner_api.OwnerCommandReceipt.v1"},
        ),
        _usage(cost_minor_units=50),
        environment_namespace="production",
    )
    assert approved.allowed is True


def test_effective_boundaries_match_change_class_and_authority() -> None:
    approval_hash = "b" * 64
    valid_changes = [
        {
            "change_class": "C0",
            "effective_boundary": f"RELEASE:{'a' * 64}",
            "status": "APPROVED",
            "test_refs": [],
            "is_restrictive_only": False,
            "owner_approval_ref": None,
        },
        {
            "change_class": "C1",
            "effective_boundary": f"RELEASE:{'a' * 64}",
            "status": "APPROVED",
            "test_refs": ["equivalence_test"],
            "is_restrictive_only": False,
            "owner_approval_ref": None,
        },
        {
            "change_class": "C2",
            "effective_boundary": f"NEW_EPOCH:2026-10-08:{'c' * 64}",
            "status": "APPROVED",
            "test_refs": [],
            "is_restrictive_only": False,
            "owner_approval_ref": None,
        },
        {
            "change_class": "C3",
            "effective_boundary": f"OWNER_APPROVAL:2026-10-08:{approval_hash}",
            "status": "APPROVED",
            "test_refs": [],
            "is_restrictive_only": False,
            "owner_approval_ref": {"content_hash": approval_hash},
        },
        {
            "change_class": "C4",
            "effective_boundary": "IMMEDIATE_RESTRICTIVE",
            "status": "PROPOSED",
            "test_refs": [],
            "is_restrictive_only": True,
            "owner_approval_ref": None,
        },
    ]
    for change in valid_changes:
        validate_change_request_boundary(change, current_session=SESSION)


@pytest.mark.parametrize(
    ("change", "error_code"),
    [
        (
            {
                "change_class": "C1",
                "effective_boundary": f"RELEASE:{'a' * 64}",
                "status": "APPROVED",
                "test_refs": [],
            },
            "c1_equivalence_tests_required",
        ),
        (
            {
                "change_class": "C2",
                "effective_boundary": f"NEW_EPOCH:2026-10-06:{'a' * 64}",
                "status": "APPROVED",
            },
            "new_epoch_boundary_is_past",
        ),
        (
            {
                "change_class": "C3",
                "effective_boundary": f"OWNER_APPROVAL:2026-10-08:{'a' * 64}",
                "status": "APPROVED",
                "owner_approval_ref": {"content_hash": "b" * 64},
            },
            "owner_approval_reference_mismatch",
        ),
        (
            {
                "change_class": "C4",
                "effective_boundary": "IMMEDIATE_RESTRICTIVE",
                "status": "APPROVED",
                "is_restrictive_only": False,
            },
            "c4_must_be_restrictive",
        ),
    ],
)
def test_invalid_change_boundaries_fail_closed(
    change: dict[str, Any], error_code: str
) -> None:
    with pytest.raises(ConfigurationPolicyError, match=error_code):
        validate_change_request_boundary(change, current_session=SESSION)
