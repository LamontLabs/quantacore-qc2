import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from qc2_position_state.contracts import (
    broker_event_from_contract,
    corporate_action_from_contract,
    correction_from_contract,
    execution_episode_from_contract,
    fill_from_contract,
    order_from_contracts,
)


def _contracts() -> dict[str, dict]:
    path = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "contracts"
        / "fixtures"
        / "v1"
        / "valid.json"
    )
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row["contract"]: row["payload"] for row in rows}


def test_canonical_contract_adapters_preserve_episode_and_order_identity():
    contracts = _contracts()
    episode_payload = contracts["ExecutionEpisode"]
    referenced_position_ids = {
        ref["target_id"] for ref in episode_payload["opening_position_refs"]
    }
    position_payloads = tuple(
        payload
        for name, payload in contracts.items()
        if name == "Position" and payload["id"] in referenced_position_ids
    )
    episode = execution_episode_from_contract(episode_payload, position_payloads)
    order = order_from_contracts(
        contracts["BrokerOrder"],
        contracts["PaperOrderIntent"],
        episode,
    )

    assert episode.episode_id == episode_payload["id"]
    assert episode.content_hash == episode_payload["content_hash"]
    assert order.episode_id == episode.episode_id
    assert order.instrument_id == contracts["PaperOrderIntent"]["instrument_ref"]["target_id"]
    assert order.quantity == 1


def test_canonical_event_fill_correction_and_corporate_action_adapters():
    contracts = _contracts()
    event = broker_event_from_contract(contracts["BrokerOrderEvent"])
    fill = fill_from_contract(contracts["Fill"])
    correction = correction_from_contract(contracts["FillCorrection"])
    action = corporate_action_from_contract(
        contracts["CorporateActionRecord"],
        currency="USD",
        effective_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
        share_ratio=Decimal("1"),
        cash_per_share=Decimal("0"),
        adjustment_id="normalized-action-adjustment",
    )

    assert event.provider_event_id == "fixture"
    assert fill.provider_fill_id == "fixture"
    assert correction.correction_kind == "BUST"
    assert action.corporate_action_id == contracts["CorporateActionRecord"]["id"]
    assert action.share_ratio == 1
