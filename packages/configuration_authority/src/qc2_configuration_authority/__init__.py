"""Fail-closed configuration authority checks for QC2."""

from .authority import (
    BudgetAssessment,
    CapabilityGate,
    ConfigurationPolicyError,
    assess_configuration,
    assess_resource_budget,
    assert_secret_free_output,
    safe_configuration_audit_payload,
    validate_change_request_boundary,
    validate_research_capital_limits,
)

__all__ = [
    "BudgetAssessment",
    "CapabilityGate",
    "ConfigurationPolicyError",
    "assess_configuration",
    "assess_resource_budget",
    "assert_secret_free_output",
    "safe_configuration_audit_payload",
    "validate_change_request_boundary",
    "validate_research_capital_limits",
]
