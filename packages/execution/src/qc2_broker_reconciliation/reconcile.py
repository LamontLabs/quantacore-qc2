"""Deterministic comparison of frozen local and broker inventory fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, Mapping

from qc2_contracts.runtime import canonical_json_bytes, validate_contract

from .models import (
    BrokerInventorySnapshot,
    LocalInventorySnapshot,
    LocalOrder,
    UnknownSubmission,
    decimal_text,
)


_LOCAL_HASH_DOMAIN = (
    b"QC2-HASH-V1\x00qc2.execution.broker-reconciliation.local-inventory.v1\x00"
)
_BROKER_HASH_DOMAIN = (
    b"QC2-HASH-V1\x00qc2.execution.broker-reconciliation.broker-inventory.v1\x00"
)
_CHECKPOINT_HASH_DOMAIN = (
    b"QC2-HASH-V1\x00qc2.execution.broker-reconciliation.checkpoint.v1\x00"
)
_ACTIVE_LOCAL_ORDER_STATES = {
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "CANCEL_REQUESTED",
    "SUBMISSION_UNKNOWN",
}


@dataclass(frozen=True, slots=True)
class Finding:
    finding_key: str
    reason_code: str
    detail: str

    def as_json(self) -> dict[str, str]:
        return {
            "finding_key": self.finding_key,
            "reason_code": self.reason_code,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class UnknownResolutionCandidate:
    attempt_id: str
    intent_id: str
    client_order_key: str
    broker_order_id: str | None
    absence_proof_eligible: bool


@dataclass(frozen=True, slots=True)
class ReconciliationDraft:
    episode_ref: Mapping[str, str]
    expected_account_fingerprint: str
    observed_account_fingerprint: str
    local_snapshot_hash: str
    broker_snapshot_hash: str
    checkpoint_hash: str
    status: str
    findings: tuple[Finding, ...]
    unknown_resolution_candidates: tuple[UnknownResolutionCandidate, ...]
    broker_order_refs: tuple[Mapping[str, str], ...]
    position_refs: tuple[Mapping[str, str], ...]
    checked_sources: tuple[str, ...]

    @property
    def discrepancies(self) -> tuple[str, ...]:
        return tuple(row.finding_key for row in self.findings)

    def persistence_payload(self) -> dict[str, Any]:
        """Return the minimal JSON payload accepted by the QC2-049 DB boundary."""
        return {
            "episode_ref": dict(self.episode_ref),
            "expected_account_fingerprint": self.expected_account_fingerprint,
            "observed_account_fingerprint": self.observed_account_fingerprint,
            "local_snapshot_hash": self.local_snapshot_hash,
            "broker_snapshot_hash": self.broker_snapshot_hash,
            "checkpoint_hash": self.checkpoint_hash,
            "status": self.status,
            "source_refs": [],
            "broker_order_refs": [dict(ref) for ref in self.broker_order_refs],
            "position_refs": [dict(ref) for ref in self.position_refs],
            "discrepancies": list(self.discrepancies),
            "findings": [row.as_json() for row in self.findings],
            "checked_sources": list(self.checked_sources),
            "event_payload": {
                "episode_ref": dict(self.episode_ref),
                "expected_account_fingerprint": self.expected_account_fingerprint,
                "observed_account_fingerprint": self.observed_account_fingerprint,
                "local_snapshot_hash": self.local_snapshot_hash,
                "broker_snapshot_hash": self.broker_snapshot_hash,
                "checkpoint_hash": self.checkpoint_hash,
                "status": self.status,
                "findings": [row.as_json() for row in self.findings],
                "checked_sources": list(self.checked_sources),
            },
        }


def local_inventory_hash(snapshot: LocalInventorySnapshot) -> str:
    payload = {
        "episode_ref": dict(snapshot.episode_ref),
        "paper_account_fingerprint": snapshot.paper_account_fingerprint,
        # A storage/control generation can advance because this reconciliation
        # placed a hold. Only inventory facts belong in the stable snapshot hash.
        "orders": [
            {
                "order_ref": dict(row.order_ref),
                "broker_order_id": row.broker_order_id,
                "intent_id": row.intent_id,
                "client_order_key": row.client_order_key,
                "symbol": row.symbol,
                "side": row.side,
                "quantity": decimal_text(row.quantity),
                "filled_quantity": decimal_text(row.filled_quantity),
                "order_type": row.order_type,
                "time_in_force": row.time_in_force,
                "limit_price": decimal_text(row.limit_price),
                "state": row.state,
            }
            for row in sorted(snapshot.orders, key=lambda item: item.broker_order_id)
        ],
        "fills": [
            {
                "provider_activity_id": row.provider_activity_id,
                "broker_order_id": row.broker_order_id,
                "quantity": decimal_text(row.quantity),
                "price": decimal_text(row.price),
            }
            for row in sorted(snapshot.fills, key=lambda item: item.provider_activity_id)
        ],
        "positions": [
            {
                "position_ref": dict(row.position_ref),
                "instrument_id": row.instrument_id,
                "symbol": row.symbol,
                "quantity": decimal_text(row.quantity),
                "average_cost": decimal_text(row.average_cost),
                "currency": row.currency,
            }
            for row in sorted(snapshot.positions, key=lambda item: item.instrument_id)
        ],
        "cash": [
            {"currency": row.currency, "balance": decimal_text(row.balance)}
            for row in sorted(snapshot.cash, key=lambda item: item.currency)
        ],
        "unknown_submissions": [
            {
                "attempt_id": row.attempt_id,
                "intent_id": row.intent_id,
                "account_fingerprint": row.account_fingerprint,
                "client_order_key": row.client_order_key,
                "normalized_request_hash": row.normalized_request_hash,
                "expected_request": _json_value(row.expected_request),
            }
            for row in sorted(snapshot.unknown_submissions, key=lambda item: item.attempt_id)
        ],
        "symbol_to_instrument": dict(sorted(snapshot.symbol_to_instrument.items())),
    }
    return sha256(_LOCAL_HASH_DOMAIN + canonical_json_bytes(payload)).hexdigest()


def broker_inventory_hash(snapshot: BrokerInventorySnapshot) -> str:
    payload = {
        "account_fingerprint": snapshot.account_fingerprint,
        "read_token": snapshot.read_token,
        "orders_complete": snapshot.orders_complete,
        "fills_complete": snapshot.fills_complete,
        "positions_complete": snapshot.positions_complete,
        "cash_complete": snapshot.cash_complete,
        "consistency_window_closed": snapshot.consistency_window_closed,
        "checked_sources": sorted(snapshot.checked_sources),
        "orders": [
            {
                "broker_order_id": row.broker_order_id,
                "client_order_key": row.client_order_key,
                "state": row.state.value,
                "provider_status": row.provider_status,
                "symbol": row.symbol,
                "side": row.side,
                "quantity": decimal_text(row.quantity),
                "filled_quantity": decimal_text(row.filled_quantity),
                "remaining_quantity": decimal_text(row.remaining_quantity),
                "order_type": row.order_type,
                "time_in_force": row.time_in_force,
                "limit_price": decimal_text(row.limit_price),
                "submitted_at": _utc_text(row.submitted_at),
                "updated_at": _utc_text(row.updated_at),
                "filled_average_price": (
                    None
                    if row.filled_average_price is None
                    else decimal_text(row.filled_average_price)
                ),
            }
            for row in sorted(snapshot.orders, key=lambda item: item.broker_order_id)
        ],
        "fills": [
            {
                "provider_activity_id": row.provider_activity_id,
                "broker_order_id": row.broker_order_id,
                "event_type": row.event_type.value,
                "symbol": row.symbol,
                "side": row.side,
                "quantity": decimal_text(row.quantity),
                "cumulative_quantity": decimal_text(row.cumulative_quantity),
                "remaining_quantity": decimal_text(row.remaining_quantity),
                "price": decimal_text(row.price),
                "filled_at": _utc_text(row.filled_at),
            }
            for row in sorted(snapshot.fills, key=lambda item: item.provider_activity_id)
        ],
        "positions": [
            {
                "symbol": row.symbol,
                "quantity": decimal_text(row.quantity),
                "average_cost": decimal_text(row.average_cost),
                "currency": row.currency,
            }
            for row in sorted(snapshot.positions, key=lambda item: item.symbol)
        ],
        "cash": [
            {"currency": row.currency, "balance": decimal_text(row.balance)}
            for row in sorted(snapshot.cash, key=lambda item: item.currency)
        ],
    }
    return sha256(_BROKER_HASH_DOMAIN + canonical_json_bytes(payload)).hexdigest()


def compare_inventories(
    local: LocalInventorySnapshot,
    broker: BrokerInventorySnapshot,
) -> ReconciliationDraft:
    """Compare two already-collected snapshots without querying or mutating a broker."""
    findings: dict[str, Finding] = {}
    candidates: list[UnknownResolutionCandidate] = []

    def add(key: str, reason_code: str, detail: str) -> None:
        findings.setdefault(key, Finding(key, reason_code, detail))

    local_hash = local_inventory_hash(local)
    remote_hash = broker_inventory_hash(broker)
    checkpoint_material = {
        "episode_ref": dict(local.episode_ref),
        "expected_account_fingerprint": local.paper_account_fingerprint,
        "observed_account_fingerprint": broker.account_fingerprint,
        "local_snapshot_hash": local_hash,
        "broker_snapshot_hash": remote_hash,
    }
    checkpoint_hash = sha256(
        _CHECKPOINT_HASH_DOMAIN + canonical_json_bytes(checkpoint_material)
    ).hexdigest()

    if broker.account_fingerprint != local.paper_account_fingerprint:
        add(
            "account_reset",
            "ACCOUNT_RESET_DETECTED",
            "Broker identity differs from the episode account; remote emptiness is not a closure signal.",
        )
        return _draft(
            local,
            broker,
            local_hash,
            remote_hash,
            checkpoint_hash,
            findings,
            candidates,
            status="HOLD",
        )

    for source_name, complete in (
        ("orders", broker.orders_complete),
        ("fills", broker.fills_complete),
        ("positions", broker.positions_complete),
        ("cash", broker.cash_complete),
    ):
        if not complete:
            add(
                f"inventory_incomplete:{source_name}",
                "BROKER_INVENTORY_INCOMPLETE",
                f"The broker {source_name} fixture is not declared complete.",
            )

    local_by_broker_id = {row.broker_order_id: row for row in local.orders}
    local_by_client_key: dict[str, list[LocalOrder]] = {}
    for row in local.orders:
        local_by_client_key.setdefault(row.client_order_key, []).append(row)
    for client_key, rows in local_by_client_key.items():
        if len(rows) > 1:
            add(
                f"duplicate_local_client_order_key:{client_key}",
                "DUPLICATE_LOCAL_CLIENT_ORDER_KEY",
                "More than one local order uses this client order key.",
            )
    unknown_by_client_key: dict[str, list[UnknownSubmission]] = {}
    for row in local.unknown_submissions:
        unknown_by_client_key.setdefault(row.client_order_key, []).append(row)
        if row.account_fingerprint != local.paper_account_fingerprint:
            add(
                f"unknown_submission_account_mismatch:{row.attempt_id}",
                "UNKNOWN_SUBMISSION_ACCOUNT_MISMATCH",
                "The unresolved attempt is bound to a different paper account.",
            )
    for client_key in unknown_by_client_key.keys() & local_by_client_key.keys():
        add(
            f"local_unknown_client_order_key_collision:{client_key}",
            "LOCAL_UNKNOWN_CLIENT_ORDER_KEY_COLLISION",
            "A local order and unresolved submission share one client order key.",
        )

    remote_by_client_key: dict[str, list[Any]] = {}
    remote_order_ids = {row.broker_order_id for row in broker.orders}
    for row in broker.orders:
        remote_by_client_key.setdefault(row.client_order_key, []).append(row)
    for client_key, rows in remote_by_client_key.items():
        if len(rows) > 1:
            add(
                f"duplicate_remote_client_order_key:{client_key}",
                "DUPLICATE_REMOTE_CLIENT_ORDER_KEY",
                "More than one broker order uses this client order key.",
            )

    for row in broker.orders:
        known = local_by_broker_id.get(row.broker_order_id)
        known_by_key_rows = local_by_client_key.get(row.client_order_key, [])
        if (
            known is not None
            and known_by_key_rows
            and known not in known_by_key_rows
        ):
            add(
                f"order_identity_mismatch:{row.broker_order_id}",
                "BROKER_ORDER_IDENTITY_MISMATCH",
                "Broker order ID and client key identify different local orders.",
            )
            continue
        if known is None:
            if len(known_by_key_rows) == 1:
                known = known_by_key_rows[0]
            elif len(known_by_key_rows) > 1:
                continue
        if known is not None:
            _compare_order_terms(known, row, add)
            if known.broker_order_id != row.broker_order_id:
                add(
                    f"broker_order_id_changed:{known.intent_id}",
                    "BROKER_ORDER_ID_CHANGED",
                    "The known client key is attached to a different broker order ID.",
                )
            continue

        unknowns = unknown_by_client_key.get(row.client_order_key, [])
        if len(unknowns) == 1:
            attempt = unknowns[0]
            if order_matches_expected_request(row, attempt.expected_request):
                candidates.append(
                    UnknownResolutionCandidate(
                        attempt.attempt_id,
                        attempt.intent_id,
                        attempt.client_order_key,
                        row.broker_order_id,
                        False,
                    )
                )
                add(
                    f"submission_resolution_pending:{attempt.attempt_id}",
                    "UNKNOWN_SUBMISSION_RESOLUTION_PENDING",
                    "A matching remote order exists; explicit evidence-bound resolution is still required.",
                )
            else:
                add(
                    f"unknown_submission_terms_mismatch:{attempt.attempt_id}",
                    "UNKNOWN_SUBMISSION_TERMS_MISMATCH",
                    "The remote order uses the unresolved attempt key but does not match its sealed request.",
                )
            continue
        if len(unknowns) > 1:
            add(
                f"duplicate_unknown_client_key:{row.client_order_key}",
                "DUPLICATE_UNKNOWN_CLIENT_KEY",
                "More than one local unknown attempt uses this client order key.",
            )
            continue
        add(
            f"manual_order:{row.broker_order_id}",
            "UNMAPPED_REMOTE_ORDER",
            "The broker order has no matching local intent or unresolved submission.",
        )

    if broker.orders_complete:
        for row in local.orders:
            if (
                row.state in _ACTIVE_LOCAL_ORDER_STATES
                and row.broker_order_id not in remote_order_ids
                and row.client_order_key not in remote_by_client_key
            ):
                add(
                    f"local_order_missing_remotely:{row.intent_id}",
                    "LOCAL_ORDER_MISSING_REMOTELY",
                    "An active local order is absent from the complete broker order fixture.",
                )

    local_fill_by_id = {row.provider_activity_id: row for row in local.fills}
    local_broker_ids = set(local_by_broker_id)
    for row in broker.fills:
        local_fill = local_fill_by_id.get(row.provider_activity_id)
        if local_fill is not None:
            if (
                local_fill.broker_order_id != row.broker_order_id
                or local_fill.quantity != row.quantity
                or local_fill.price != row.price
            ):
                add(
                    f"fill_details_mismatch:{row.provider_activity_id}",
                    "BROKER_FILL_DETAILS_MISMATCH",
                    "A broker fill reuses a local provider activity ID with different immutable terms.",
                )
            continue
        if row.broker_order_id not in local_broker_ids:
            add(
                f"unknown_remote_fill:{row.provider_activity_id}",
                "UNKNOWN_REMOTE_FILL",
                "A broker fill references no locally known broker order.",
            )
        else:
            add(
                f"missing_local_fill:{row.provider_activity_id}",
                "BROKER_FILL_MISSING_LOCALLY",
                "A broker fill is not present in the local append-only fill ledger.",
            )
    if broker.fills_complete:
        remote_fill_ids = {row.provider_activity_id for row in broker.fills}
        for row in local.fills:
            if row.provider_activity_id not in remote_fill_ids:
                add(
                    f"local_fill_missing_remotely:{row.provider_activity_id}",
                    "LOCAL_FILL_MISSING_REMOTELY",
                    "A local fill is absent from the complete broker activity fixture.",
                )

    if broker.positions_complete:
        instrument_by_symbol = dict(local.symbol_to_instrument)
        for row in local.positions:
            prior = instrument_by_symbol.setdefault(row.symbol, row.instrument_id)
            if prior != row.instrument_id:
                add(
                    f"symbol_assignment_ambiguous:{row.symbol}",
                    "SYMBOL_ASSIGNMENT_AMBIGUOUS",
                    "The local fixture maps one broker symbol to multiple instruments.",
                )
        local_by_instrument = {row.instrument_id: row for row in local.positions}
        seen_instruments: set[str] = set()
        for remote_position in broker.positions:
            instrument_id = instrument_by_symbol.get(remote_position.symbol)
            if instrument_id is None:
                add(
                    f"unknown_remote_position:{remote_position.symbol}",
                    "UNKNOWN_REMOTE_POSITION",
                    "The remote position symbol has no pinned local instrument assignment.",
                )
                continue
            seen_instruments.add(instrument_id)
            local_position = local_by_instrument.get(instrument_id)
            if local_position is None:
                add(
                    f"unexpected_remote_position:{instrument_id}",
                    "UNEXPECTED_REMOTE_POSITION",
                    "The broker reports a position with no matching local position projection.",
                )
                continue
            if remote_position.currency != local_position.currency:
                add(
                    f"position_currency_mismatch:{instrument_id}",
                    "POSITION_CURRENCY_MISMATCH",
                    "Local and broker position currencies differ.",
                )
            if remote_position.quantity != local_position.quantity:
                add(
                    f"position_quantity_mismatch:{instrument_id}",
                    "POSITION_QUANTITY_MISMATCH",
                    "Local and broker position quantities differ.",
                )
            if remote_position.average_cost != local_position.average_cost:
                add(
                    f"position_cost_mismatch:{instrument_id}",
                    "POSITION_COST_MISMATCH",
                    "Local and broker position average costs differ.",
                )
        for row in local.positions:
            if row.instrument_id not in seen_instruments:
                add(
                    f"local_position_missing_remotely:{row.instrument_id}",
                    "LOCAL_POSITION_MISSING_REMOTELY",
                    "A local position is absent from the complete broker position fixture.",
                )

    if broker.cash_complete:
        local_cash = {row.currency: row.balance for row in local.cash}
        remote_cash = {row.currency: row.balance for row in broker.cash}
        for currency in sorted(set(local_cash) | set(remote_cash)):
            if currency not in local_cash or currency not in remote_cash:
                add(
                    f"cash_currency_missing:{currency}",
                    "CASH_CURRENCY_MISSING",
                    "A currency appears on only one side of the account inventory.",
                )
            elif local_cash[currency] != remote_cash[currency]:
                add(
                    f"cash_balance_mismatch:{currency}",
                    "CASH_BALANCE_MISMATCH",
                    "Local cash ledger and broker cash balance differ.",
                )

    for attempt in local.unknown_submissions:
        matches = remote_by_client_key.get(attempt.client_order_key, [])
        if matches:
            continue
        absence_eligible = (
            broker.orders_complete
            and broker.consistency_window_closed
            and len(broker.checked_sources) >= 2
        )
        candidates.append(
            UnknownResolutionCandidate(
                attempt.attempt_id,
                attempt.intent_id,
                attempt.client_order_key,
                None,
                absence_eligible,
            )
        )
        key = (
            f"submission_absence_needs_evidence:{attempt.attempt_id}"
            if absence_eligible
            else f"submission_unknown:{attempt.attempt_id}"
        )
        add(
            key,
            "UNKNOWN_SUBMISSION_UNRESOLVED",
            "No matching remote order is present; absence remains blocking until evidence proves otherwise.",
        )

    status = "HOLD" if findings else "RECONCILED"
    if not all(
        (
            broker.orders_complete,
            broker.fills_complete,
            broker.positions_complete,
            broker.cash_complete,
        )
    ):
        status = "UNKNOWN"
    return _draft(
        local,
        broker,
        local_hash,
        remote_hash,
        checkpoint_hash,
        findings,
        candidates,
        status=status,
    )


def build_reconciliation_report(
    draft: ReconciliationDraft,
    *,
    report_id: str,
    created_at: datetime,
    evidence_ref: Mapping[str, Any],
    status: str | None = None,
    additional_discrepancies: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build and validate the existing immutable ReconciliationReport contract."""
    report_status = status or draft.status
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    contract = {
        "schema_name": "qc2.execution.ReconciliationReport.v1",
        "schema_version": "1.0",
        "id": report_id,
        "created_at": _utc_text(created_at),
        "owning_authority": "execution",
        "evidence_class": "SYNTHETIC_FIXTURE",
        "environment_namespace": "test",
        "source_refs": [],
        "episode_ref": dict(draft.episode_ref),
        "paper_account_fingerprint": draft.expected_account_fingerprint,
        "reconciled_at": _utc_text(created_at),
        "broker_order_refs": [dict(ref) for ref in draft.broker_order_refs],
        "position_refs": [dict(ref) for ref in draft.position_refs],
        "discrepancies": sorted(
            set(draft.discrepancies) | set(additional_discrepancies)
        ),
        "status": report_status,
        "evidence_ref": dict(evidence_ref),
    }
    validate_contract("ReconciliationReport", contract)
    return contract


def _draft(
    local: LocalInventorySnapshot,
    broker: BrokerInventorySnapshot,
    local_hash: str,
    remote_hash: str,
    checkpoint_hash: str,
    findings: Mapping[str, Finding],
    candidates: list[UnknownResolutionCandidate],
    *,
    status: str,
) -> ReconciliationDraft:
    order_refs = {
        (ref["target_schema_name"], ref["target_id"]): ref
        for ref in (row.order_ref for row in local.orders)
    }
    position_refs = {
        (ref["target_schema_name"], ref["target_id"]): ref
        for ref in (row.position_ref for row in local.positions)
    }
    return ReconciliationDraft(
        episode_ref=local.episode_ref,
        expected_account_fingerprint=local.paper_account_fingerprint,
        observed_account_fingerprint=broker.account_fingerprint,
        local_snapshot_hash=local_hash,
        broker_snapshot_hash=remote_hash,
        checkpoint_hash=checkpoint_hash,
        status=status,
        findings=tuple(findings[key] for key in sorted(findings)),
        unknown_resolution_candidates=tuple(
            sorted(candidates, key=lambda row: row.attempt_id)
        ),
        broker_order_refs=tuple(order_refs[key] for key in sorted(order_refs)),
        position_refs=tuple(position_refs[key] for key in sorted(position_refs)),
        checked_sources=tuple(sorted(broker.checked_sources)),
    )


def _compare_order_terms(
    local: LocalOrder,
    remote: Any,
    add: Any,
) -> None:
    if (
        local.symbol != remote.symbol
        or local.side != remote.side
        or local.quantity != remote.quantity
        or local.order_type != remote.order_type
        or local.time_in_force != remote.time_in_force
        or local.limit_price != remote.limit_price
    ):
        add(
            f"order_terms_mismatch:{local.intent_id}",
            "BROKER_ORDER_TERMS_MISMATCH",
            "Broker order terms differ from the immutable local order.",
        )
    if local.filled_quantity != remote.filled_quantity:
        add(
            f"order_fill_quantity_mismatch:{local.intent_id}",
            "BROKER_ORDER_FILL_QUANTITY_MISMATCH",
            "Broker cumulative filled quantity differs from the local order projection.",
        )
    if local.state != remote.state.value:
        add(
            f"order_state_mismatch:{local.intent_id}",
            "BROKER_ORDER_STATE_MISMATCH",
            "Broker order state differs from the local order projection.",
        )


def order_matches_expected_request(
    remote: Any, request: Mapping[str, Any]
) -> bool:
    try:
        return (
            remote.client_order_key == request["client_order_key"]
            and remote.symbol == request["symbol"]
            and remote.side == request["side"]
            and remote.quantity == Decimal(str(request["quantity_whole_shares"]))
            and remote.order_type == request["order_type"]
            and remote.time_in_force == request["time_in_force"]
            and remote.limit_price == Decimal(str(request["limit_price"]))
            and request.get("extended_hours") is False
        )
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return False


def _utc_text(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    raise ValueError(f"unsupported value in sealed request: {type(value).__name__}")
