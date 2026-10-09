"""Synthetic strategy profiles for isolated tests; never activation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any

from qc2_contracts.runtime import canonical_content_hash, validate_contract

from .framework import (
    ALLOCATION_ORDER,
    CANCELLATION_POLICY,
    COMPETING_ACTION_RULE,
    DRAWDOWN_RESPONSE,
    ENTRY_WINDOW,
    EXTERNAL_ACTIVITY_POLICY,
    GAP_NO_FILL_POLICY,
    PRICE_CAP_RULE,
    RANK_RULE,
    REENTRY_POLICY,
    RESERVATION_POLICY,
    STOP_RULE,
    TARGET_RULE,
)
from .models import StrategyRules

_FIXTURE_DATE = "2026-01-01T00:00:00Z"
_FIXTURE_NAMESPACE = "test"


@dataclass(frozen=True, slots=True)
class FixtureStrategyProfile:
    name: str
    strategy_manifest: dict[str, Any]
    capital_policy: dict[str, Any]
    rules: StrategyRules


def _fixture_uuid(number: int) -> str:
    return f"018f0000-0000-7000-8000-{number:012d}"


def _content_address(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash(name, payload)
    validate_contract(name, payload)
    return payload


def _profile(
    *,
    number: int,
    name: str,
    selection_k: int,
    starting_capital: str,
    maximum_position_cost: str,
    maximum_position_fraction: str,
    maximum_gross_exposure: str,
    cash_reserve: str,
    maximum_positions: int,
    daily_loss_limit: str,
    participation_limit: str,
    price_buffer: str,
    cost_buffer: str,
    entry_ceiling: str,
    stop_fraction: str,
    target_fraction: str,
    maximum_holding_sessions: int,
    cooldown_sessions: int,
) -> FixtureStrategyProfile:
    config_hash = sha256(f"fixture:{name}:configuration".encode("utf-8")).hexdigest()
    strategy_id = _fixture_uuid(number)
    policy_id = _fixture_uuid(number + 1)
    configuration_id = _fixture_uuid(number + 2)
    owner_receipt_id = _fixture_uuid(number + 3)
    manifest = {
        "schema_name": "qc2.execution.StrategyManifest.v1",
        "schema_version": "1.0",
        "id": strategy_id,
        "created_at": _FIXTURE_DATE,
        "owning_authority": "strategy",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": _FIXTURE_NAMESPACE,
        "source_refs": [],
        "content_hash": "0" * 64,
        "strategy_key": name,
        "version": 1,
        "selection_k": selection_k,
        "rank_rule": RANK_RULE,
        "entry_window": ENTRY_WINDOW,
        "allocation_order": ALLOCATION_ORDER,
        "price_cap_rule": PRICE_CAP_RULE,
        "quantity_rounding": "WHOLE_SHARES_FLOOR",
        "stop_rule": STOP_RULE,
        "target_rule": TARGET_RULE,
        "trailing_rule": None,
        "maximum_holding_sessions": maximum_holding_sessions,
        "reentry_policy": REENTRY_POLICY,
        "reservation_policy": RESERVATION_POLICY,
        "cancellation_policy": CANCELLATION_POLICY,
        "gap_no_fill_policy": GAP_NO_FILL_POLICY,
        "competing_action_rule": COMPETING_ACTION_RULE,
        "configuration_ref": {
            "target_schema_name": "qc2.integrity_build.ConfigurationManifest.v1",
            "target_id": configuration_id,
            "content_hash": config_hash,
        },
    }
    policy = {
        "schema_name": "qc2.execution.CapitalPolicy.v1",
        "schema_version": "1.0",
        "id": policy_id,
        "created_at": _FIXTURE_DATE,
        "owning_authority": "configuration",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": _FIXTURE_NAMESPACE,
        "source_refs": [],
        "content_hash": "0" * 64,
        "paper_starting_capital": starting_capital,
        "currency": "USD",
        "maximum_position_cost": maximum_position_cost,
        "maximum_position_fraction": maximum_position_fraction,
        "maximum_gross_exposure": maximum_gross_exposure,
        "cash_reserve": cash_reserve,
        "maximum_concurrent_positions": maximum_positions,
        "daily_loss_limit": daily_loss_limit,
        "drawdown_response": DRAWDOWN_RESPONSE,
        "participation_limit": participation_limit,
        "external_activity_policy": EXTERNAL_ACTIVITY_POLICY,
        "owner_approval_ref": {
            "target_schema_name": "qc2.governance_owner.OwnerCommandReceipt.v1",
            "target_id": owner_receipt_id,
        },
    }
    manifest = _content_address("StrategyManifest", manifest)
    policy = _content_address("CapitalPolicy", policy)
    rules = StrategyRules(
        configuration_hash=config_hash,
        selection_k=selection_k,
        price_cap_buffer_fraction=Decimal(price_buffer),
        cost_buffer_fraction=Decimal(cost_buffer),
        per_entry_notional_ceiling=Decimal(entry_ceiling),
        stop_loss_fraction=Decimal(stop_fraction),
        target_gain_fraction=Decimal(target_fraction),
        trailing_stop_fraction=None,
        maximum_holding_sessions=maximum_holding_sessions,
        cooldown_sessions=cooldown_sessions,
        fixture_only=True,
    )
    return FixtureStrategyProfile(name, manifest, policy, rules)


def fixture_profiles() -> tuple[FixtureStrategyProfile, ...]:
    """Return explicit synthetic examples; none is a production default."""
    return (
        _profile(
            number=440,
            name="test_only_micro_example",
            selection_k=2,
            starting_capital="10000.00",
            maximum_position_cost="1200.00",
            maximum_position_fraction="0.150000000000",
            maximum_gross_exposure="7000.00",
            cash_reserve="500.00",
            maximum_positions=4,
            daily_loss_limit="300.00",
            participation_limit="0.050000000000",
            price_buffer="0.020",
            cost_buffer="0.001",
            entry_ceiling="1000.00",
            stop_fraction="0.050",
            target_fraction="0.100",
            maximum_holding_sessions=5,
            cooldown_sessions=2,
        ),
        _profile(
            number=450,
            name="test_only_owner_cap_stress",
            selection_k=1,
            starting_capital="10000.00",
            maximum_position_cost="100.00",
            maximum_position_fraction="0.020000000000",
            maximum_gross_exposure="500.00",
            cash_reserve="50.00",
            maximum_positions=2,
            daily_loss_limit="10.00",
            participation_limit="0.010000000000",
            price_buffer="0.010",
            cost_buffer="0.001",
            entry_ceiling="100000.00",
            stop_fraction="0.050",
            target_fraction="0.100",
            maximum_holding_sessions=3,
            cooldown_sessions=1,
        ),
    )
