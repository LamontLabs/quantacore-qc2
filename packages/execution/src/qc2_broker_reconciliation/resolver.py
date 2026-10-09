"""Evidence-bound resolution of unknown paper-order submissions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from qc2_execution.authority import (
    ReconciliationDisposition,
    ReconciliationEvidence,
    normalized_request_hash,
)

from .models import BrokerInventorySnapshot, UnknownSubmission
from .reconcile import order_matches_expected_request


class UnknownSubmissionAuthority(Protocol):
    """Only the existing evidence-gated resolver is used; no broker writes occur."""

    def accept_reconciliation(
        self, attempt_id: str, evidence: ReconciliationEvidence
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class UnknownResolutionResult:
    attempt_id: str
    disposition: ReconciliationDisposition
    resolved: bool
    reason_code: str
    broker_order_id: str | None = None


def resolve_unknown_submission(
    unknown: UnknownSubmission,
    broker: BrokerInventorySnapshot,
    *,
    evidence_ref: Mapping[str, Any],
    authority: UnknownSubmissionAuthority,
) -> UnknownResolutionResult:
    """Resolve one SUBMISSION_UNKNOWN attempt only from matching inventory evidence.

    A missing order remains unresolved unless the frozen observation declares a
    complete order inventory, a closed consistency window, and at least two
    distinct checked sources. This function never submits, cancels, or creates
    an order.
    """
    if unknown.normalized_request_hash != normalized_request_hash(
        unknown.expected_request
    ):
        raise ValueError("unknown submission request hash does not match its sealed request")

    matching = [
        row for row in broker.orders if row.client_order_key == unknown.client_order_key
    ]
    disposition = ReconciliationDisposition.UNRESOLVED
    broker_order_id: str | None = None
    reason_code = "UNKNOWN_SUBMISSION_UNRESOLVED"

    if broker.account_fingerprint != unknown.account_fingerprint:
        reason_code = "UNKNOWN_SUBMISSION_ACCOUNT_MISMATCH"
    elif len(matching) > 1:
        reason_code = "DUPLICATE_REMOTE_CLIENT_ORDER_KEY"
    elif len(matching) == 1:
        order = matching[0]
        if not broker.checked_sources:
            reason_code = "RECONCILIATION_SOURCE_COVERAGE_MISSING"
        elif not order_matches_expected_request(order, unknown.expected_request):
            reason_code = "UNKNOWN_SUBMISSION_TERMS_MISMATCH"
        else:
            disposition = ReconciliationDisposition.FOUND
            broker_order_id = order.broker_order_id
            reason_code = "UNKNOWN_SUBMISSION_FOUND"
    elif (
        broker.orders_complete
        and broker.consistency_window_closed
        and len(broker.checked_sources) >= 2
    ):
        disposition = ReconciliationDisposition.ABSENCE_PROVEN
        reason_code = "UNKNOWN_SUBMISSION_ABSENCE_PROVEN"

    evidence = ReconciliationEvidence(
        intent_id=unknown.intent_id,
        account_fingerprint=unknown.account_fingerprint,
        client_order_key=unknown.client_order_key,
        normalized_request_hash=unknown.normalized_request_hash,
        disposition=disposition,
        checked_sources=broker.checked_sources,
        consistency_window_closed=broker.consistency_window_closed,
        broker_order_id=broker_order_id,
        evidence_ref=dict(evidence_ref),
    )
    resolved = authority.accept_reconciliation(unknown.attempt_id, evidence)
    if disposition == ReconciliationDisposition.UNRESOLVED and resolved:
        raise RuntimeError("unresolved evidence must not change the unknown attempt")
    return UnknownResolutionResult(
        attempt_id=unknown.attempt_id,
        disposition=disposition,
        resolved=bool(resolved),
        reason_code=reason_code if resolved else f"{reason_code}_NOT_ACCEPTED",
        broker_order_id=broker_order_id,
    )
