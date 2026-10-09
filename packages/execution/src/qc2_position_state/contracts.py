"""Adapters from canonical QC2 contracts to the immutable replay model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from qc2_contracts.runtime import validate_contract

from .model import (
    BrokerOrderEvent,
    CorporateActionAdjustment,
    ExecutionEpisodeSeed,
    Fill,
    FillCorrection,
    OpeningPosition,
    OrderSpec,
)


def _required_ref(payload: Mapping[str, Any], field: str, schema_name: str) -> str:
    ref = payload.get(field)
    if not isinstance(ref, Mapping) or ref.get("target_schema_name") != schema_name:
        raise ValueError(f"{field} must reference {schema_name}")
    target_id = ref.get("target_id")
    if not isinstance(target_id, str) or not target_id:
        raise ValueError(f"{field}.target_id is required")
    return target_id


def execution_episode_from_contract(
    payload: Mapping[str, Any],
    opening_positions: tuple[Mapping[str, Any], ...] = (),
) -> ExecutionEpisodeSeed:
    episode = dict(payload)
    validate_contract("ExecutionEpisode", episode)
    if episode["account_mode"] != "PAPER" or not episode.get("sealed_at"):
        raise ValueError("only sealed PAPER execution episodes can be replayed")

    referenced = {
        ref["target_id"]
        for ref in episode["opening_position_refs"]
        if ref["target_schema_name"] == "qc2.execution.Position.v1"
    }
    supplied: set[str] = set()
    positions: list[OpeningPosition] = []
    for source in opening_positions:
        position = dict(source)
        validate_contract("Position", position)
        if _required_ref(
            position, "episode_ref", "qc2.execution.ExecutionEpisode.v1"
        ) != episode["id"]:
            raise ValueError("opening position belongs to a different episode")
        supplied.add(position["id"])
        positions.append(
            OpeningPosition(
                instrument_id=_required_ref(
                    position, "instrument_ref", "qc2.identity_market.Instrument.v1"
                ),
                quantity=Decimal(position["quantity"]),
                average_cost=Decimal(position["average_cost"]),
                currency=position["currency"],
                source_fill_ids=tuple(
                    ref["target_id"] for ref in position["source_fill_refs"]
                ),
                corporate_action_ids=tuple(
                    ref["target_id"] for ref in position["corporate_action_refs"]
                ),
            )
        )
    if referenced != supplied:
        raise ValueError("opening position contracts must exactly match episode refs")

    return ExecutionEpisodeSeed(
        episode_id=episode["id"],
        episode_hash=episode["episode_hash"],
        content_hash=episode["content_hash"],
        account_fingerprint=episode["paper_account_fingerprint"],
        currency=episode["currency"],
        opening_cash=Decimal(episode["opening_cash"]),
        opened_at=datetime.fromisoformat(episode["opened_at"].replace("Z", "+00:00")),
        opening_positions=tuple(positions),
    )


def order_from_contracts(
    broker_order_payload: Mapping[str, Any],
    intent_payload: Mapping[str, Any],
    episode: ExecutionEpisodeSeed,
    reservation_payload: Mapping[str, Any] | None = None,
) -> OrderSpec:
    broker_order = dict(broker_order_payload)
    intent = dict(intent_payload)
    validate_contract("BrokerOrder", broker_order)
    validate_contract("PaperOrderIntent", intent)
    if _required_ref(
        broker_order, "intent_ref", "qc2.execution.PaperOrderIntent.v1"
    ) != intent["id"]:
        raise ValueError("broker order references a different intent")
    if broker_order["intent_ref"].get("content_hash") != intent["content_hash"]:
        raise ValueError("broker order intent content hash does not match")
    if _required_ref(
        intent, "episode_ref", "qc2.execution.ExecutionEpisode.v1"
    ) != episode.episode_id:
        raise ValueError("intent belongs to a different execution episode")
    if intent["episode_ref"].get("content_hash") != episode.content_hash:
        raise ValueError("intent episode contract hash does not match")
    if (
        broker_order["paper_account_fingerprint"] != episode.account_fingerprint
        or intent["paper_account_fingerprint"] != episode.account_fingerprint
    ):
        raise ValueError("broker order account does not match the episode")

    reservation_id = None
    reservation_kind = None
    reserved_amount = None
    if reservation_payload is not None:
        reservation = dict(reservation_payload)
        validate_contract("Reservation", reservation)
        if _required_ref(
            reservation, "intent_ref", "qc2.execution.PaperOrderIntent.v1"
        ) != intent["id"]:
            raise ValueError("reservation belongs to a different intent")
        if reservation["intent_ref"].get("content_hash") != intent["content_hash"]:
            raise ValueError("reservation intent hash does not match")
        if reservation["state"] not in {"ACTIVE", "PARTIALLY_CONSUMED", "HELD"}:
            raise ValueError("new orders require an active reservation")
        reservation_id = reservation["id"]
        reservation_kind = reservation["reservation_kind"]
        reserved_amount = Decimal(
            reservation["reserved_cash"]
            if reservation_kind == "CASH"
            else reservation["reserved_quantity"]
        )

    if intent["side"] not in {"BUY", "SELL"}:
        raise ValueError("paper order side is unsupported")
    return OrderSpec(
        order_id=broker_order["id"],
        episode_id=episode.episode_id,
        instrument_id=_required_ref(
            intent, "instrument_ref", "qc2.identity_market.Instrument.v1"
        ),
        side=intent["side"],
        quantity=Decimal(str(intent["quantity_whole_shares"])),
        currency=episode.currency,
        reservation_id=reservation_id,
        reservation_kind=reservation_kind,
        reserved_amount=reserved_amount,
    )


def broker_event_from_contract(payload: Mapping[str, Any]) -> BrokerOrderEvent:
    contract = dict(payload)
    validate_contract("BrokerOrderEvent", contract)
    return BrokerOrderEvent(
        event_id=contract["id"],
        order_id=_required_ref(
            contract, "broker_order_ref", "qc2.execution.BrokerOrder.v1"
        ),
        provider_event_id=contract["provider_event_id"],
        event_type=contract["event_type"],
        event_sequence=contract["event_sequence"],
        event_at=datetime.fromisoformat(contract["event_at"].replace("Z", "+00:00")),
        received_at=datetime.fromisoformat(
            contract["received_at"].replace("Z", "+00:00")
        ),
        event_payload_hash=contract["event_payload_hash"],
    )


def fill_from_contract(payload: Mapping[str, Any]) -> Fill:
    contract = dict(payload)
    validate_contract("Fill", contract)
    return Fill(
        fill_id=contract["id"],
        order_id=_required_ref(
            contract, "broker_order_ref", "qc2.execution.BrokerOrder.v1"
        ),
        provider_fill_id=contract["provider_fill_id"],
        instrument_id=_required_ref(
            contract, "instrument_ref", "qc2.identity_market.Instrument.v1"
        ),
        side=contract["side"],
        quantity=Decimal(contract["quantity"]),
        price=Decimal(contract["price"]),
        currency=contract["currency"],
        filled_at=datetime.fromisoformat(contract["filled_at"].replace("Z", "+00:00")),
        received_at=datetime.fromisoformat(
            contract["received_at"].replace("Z", "+00:00")
        ),
    )


def correction_from_contract(payload: Mapping[str, Any]) -> FillCorrection:
    contract = dict(payload)
    validate_contract("FillCorrection", contract)
    return FillCorrection(
        correction_id=contract["id"],
        original_fill_id=_required_ref(
            contract, "original_fill_ref", "qc2.execution.Fill.v1"
        ),
        source_event_id=_required_ref(
            contract, "source_event_ref", "qc2.execution.BrokerOrderEvent.v1"
        ),
        correction_kind=contract["correction_kind"],
        quantity_delta=Decimal(contract["quantity_delta"]),
        price_delta=Decimal(contract["price_delta"]),
        reason_code=contract["reason_code"],
        corrected_at=datetime.fromisoformat(
            contract["corrected_at"].replace("Z", "+00:00")
        ),
    )


def corporate_action_from_contract(
    action_payload: Mapping[str, Any],
    *,
    currency: str,
    effective_at: datetime,
    share_ratio: Decimal,
    cash_per_share: Decimal,
    adjustment_id: str,
) -> CorporateActionAdjustment:
    """Bind explicit adjustment terms to a canonical action record.

    CorporateActionRecord intentionally does not supply an executable price or
    quantity adjustment here. Callers must provide reviewed terms explicitly;
    this function never fetches provider data or infers missing terms.
    """

    action = dict(action_payload)
    validate_contract("CorporateActionRecord", action)
    return CorporateActionAdjustment(
        adjustment_id=adjustment_id,
        corporate_action_id=action["id"],
        instrument_id=_required_ref(
            action, "instrument_ref", "qc2.identity_market.Instrument.v1"
        ),
        currency=currency,
        effective_at=effective_at,
        share_ratio=share_ratio,
        cash_per_share=cash_per_share,
    )
