"""Atomic Champion transition protocol and its in-memory reference store.

Real owner approval remains disabled. The test-namespace store exercises the
same compare-and-swap, one-use approval, receipt, outbox, and readiness rules
without granting fixture identities authority over a live epoch.
"""

from __future__ import annotations

import copy
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from qc2_contracts.runtime import (
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

PRODUCTION_APPROVAL_ENABLED = False
POINTER_HASH_DOMAIN = "qc2.governance_owner.champion_pointer.v1"
TRANSITION_EVENT_DOMAIN = "qc2.governance_owner.champion_transition_event.v1"
LOAD_OUTBOX_DOMAIN = "qc2.promotion.champion_load_request.v1"
_UUID7 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class TransitionKind(StrEnum):
    INITIAL_BOOTSTRAP = "initial_bootstrap"
    PROMOTION = "promotion"
    FORWARD_ROLLBACK = "forward_rollback"


class TransitionErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    NOT_ELIGIBLE = "not_eligible"
    INVALID_APPROVAL = "invalid_approval"
    APPROVAL_DISABLED = "real_approval_disabled"
    STALE_GENERATION = "stale_generation"
    NONCE_ALREADY_CONSUMED = "nonce_already_consumed"
    NO_CHAMPION = "no_champion"
    LOAD_NOT_CONFIRMED = "load_not_confirmed"
    FAULT_INJECTED = "fault_injected"
    COMMIT_OUTCOME_UNKNOWN = "commit_outcome_unknown"


class ChampionTransitionError(ValueError):
    def __init__(self, code: TransitionErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class CommitOutcomeUnknown(RuntimeError):
    """The transaction committed, but the caller lost its acknowledgment."""

    def __init__(self, receipt_id: str) -> None:
        super().__init__("transition committed; recover its durable receipt by ID")
        self.receipt_id = receipt_id


class ApprovalTicketLike(Protocol):
    nonce: str
    request_hash: str
    expected_champion_hash: str | None
    expected_generation: int
    idempotency_key: str
    envelope_hash: str
    decision_ref: Any
    promotion_challenge_ref: Any


class ApprovalRecheckPort(Protocol):
    def recheck_for_commit(self, decision_id: str, *, now: datetime) -> Any: ...


class PromotionTransitionTransaction(Protocol):
    """Implemented by the commit transaction, matching the owner API boundary."""

    def consume_owner_approval(self, ticket: ApprovalTicketLike) -> None: ...


class TransitionSnapshotSource(Protocol):
    def capture_transition_snapshot(
        self, epoch_ref: Mapping[str, Any], session_id: str
    ) -> "PredictionReadinessSnapshot":
        """Return prediction inputs, current pointer, and load status in one DB snapshot."""


@dataclass(frozen=True, slots=True)
class CandidateState:
    model_ref: Mapping[str, Any]
    lifecycle_state: str
    retained: bool
    compatibility_verified: bool


@dataclass(frozen=True, slots=True)
class OperatingSlot:
    epoch_id: str
    slot_state: str
    pointer: Mapping[str, Any] | None
    generation: int
    pointer_hash: str | None


@dataclass(frozen=True, slots=True)
class PreparedTransition:
    kind: TransitionKind
    request: Mapping[str, Any]
    decision: Mapping[str, Any]
    bundle: Mapping[str, Any]
    ticket: ApprovalTicketLike
    expected_slot_state: str
    expected_generation: int
    expected_pointer_hash: str | None
    target: CandidateState
    prepared_at: str


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    id: str
    logical_operation_id: str
    message_type: str
    payload_hash: str
    payload: Mapping[str, Any]
    status: str = "PENDING"


@dataclass(frozen=True, slots=True)
class LoadConfirmation:
    id: str
    epoch_id: str
    pointer_id: str
    generation: int
    pointer_hash: str
    model_id: str
    model_hash: str
    worker_id: str
    status: str
    checked_at: str
    receipt_hash: str
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class PredictionReadinessSnapshot:
    bindings: Any
    pointer: Mapping[str, Any]
    latest_load_confirmation: LoadConfirmation | None


@dataclass(slots=True)
class _StoreState:
    slots: dict[str, OperatingSlot] = field(default_factory=dict)
    models: dict[tuple[str, str], CandidateState] = field(default_factory=dict)
    pointers: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    receipts: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    receipt_by_decision: dict[str, str] = field(default_factory=dict)
    approval_nonces: dict[str, str] = field(default_factory=dict)
    lifecycle_events: list[Mapping[str, Any]] = field(default_factory=list)
    evidence_events: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    outbox: dict[str, OutboxMessage] = field(default_factory=dict)
    load_confirmations: dict[str, list[LoadConfirmation]] = field(default_factory=dict)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return copy.deepcopy(value)


def _utc_text(value: datetime | str) -> str:
    if isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT, "transition time must be an ISO UTC instant"
            ) from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_INPUT, "transition time must be an ISO UTC instant"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_INPUT, "transition time must include a UTC offset"
        )
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _reference(
    value: Any, expected_schema: str, name: str, *, content_hash: bool = True
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_INPUT, f"{name} must be a typed reference"
        )
    result = _thaw(value)
    if result.get("target_schema_name") != expected_schema:
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_INPUT, f"{name} targets the wrong contract"
        )
    if not isinstance(result.get("target_id"), str) or not _UUID7.fullmatch(result["target_id"]):
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_INPUT, f"{name} has an invalid UUIDv7 identity"
        )
    if content_hash and (
        not isinstance(result.get("content_hash"), str)
        or not _SHA256.fullmatch(result["content_hash"])
    ):
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_INPUT, f"{name} must pin its content hash"
        )
    return result


def _ticket_reference(value: Any, field_name: str) -> tuple[str | None, str | None]:
    schema = getattr(value, "target_schema_name", None)
    target_id = getattr(value, "target_id", None)
    content_hash = getattr(value, "content_hash", None)
    if isinstance(value, Mapping):
        schema = value.get("target_schema_name")
        target_id = value.get("target_id")
        content_hash = value.get("content_hash")
    if not isinstance(target_id, str) or not _UUID7.fullmatch(target_id):
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_APPROVAL, f"{field_name} has an invalid identity"
        )
    if content_hash is not None and (
        not isinstance(content_hash, str) or not _SHA256.fullmatch(content_hash)
    ):
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_APPROVAL, f"{field_name} has an invalid content hash"
        )
    return schema, target_id


def _model_key(model_ref: Mapping[str, Any]) -> tuple[str, str]:
    return (str(model_ref["target_id"]), str(model_ref["content_hash"]))


def _matches_ref(left: Any, right: Mapping[str, Any]) -> bool:
    if not isinstance(left, Mapping):
        return False
    return (
        left.get("target_schema_name") == right.get("target_schema_name")
        and left.get("target_id") == right.get("target_id")
        and left.get("content_hash") == right.get("content_hash")
    )


def _prior_ref_matches(prior: Any, pointer: Mapping[str, Any]) -> bool:
    if not isinstance(prior, Mapping):
        return False
    pointer_match = (
        prior.get("target_id") == pointer["id"]
        and prior.get("content_hash") in (None, pointer["pointer_hash"])
    )
    model_ref = pointer["model_ref"]
    model_match = (
        prior.get("target_id") == model_ref["target_id"]
        and prior.get("content_hash") in (None, model_ref["content_hash"])
    )
    return pointer_match or model_match


def _approval_ticket_matches(
    ticket: ApprovalTicketLike,
    *,
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    slot: OperatingSlot,
) -> None:
    if not isinstance(getattr(ticket, "nonce", None), str) or not ticket.nonce:
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_APPROVAL, "owner approval nonce is missing"
        )
    if (
        getattr(ticket, "request_hash", None) != request.get("request_hash")
        or getattr(ticket, "expected_generation", None) != slot.generation
        or getattr(ticket, "expected_champion_hash", None) != slot.pointer_hash
    ):
        raise ChampionTransitionError(
            TransitionErrorCode.STALE_GENERATION,
            "owner approval is bound to a different request or Champion generation",
        )
    decision_schema, decision_id = _ticket_reference(
        getattr(ticket, "decision_ref", None), "decision_ref"
    )
    if (
        decision_schema != "qc2.governance_owner.PromotionDecision.v1"
        or decision_id != decision["id"]
        or getattr(ticket.decision_ref, "content_hash", None) != decision["content_hash"]
    ):
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_APPROVAL, "owner approval decision does not match"
        )
    challenge_schema, challenge_id = _ticket_reference(
        getattr(ticket, "promotion_challenge_ref", None), "promotion_challenge_ref"
    )
    challenge_ref = decision.get("challenge_ref", {})
    if (
        challenge_schema != "qc2.governance_owner.PromotionChallenge.v1"
        or challenge_id != challenge_ref.get("target_id")
        or getattr(ticket.promotion_challenge_ref, "content_hash", None)
        != challenge_ref.get("content_hash")
    ):
        raise ChampionTransitionError(
            TransitionErrorCode.INVALID_APPROVAL, "owner approval challenge does not match"
        )


class _StagedApprovalTransaction:
    def __init__(self, state: _StoreState) -> None:
        self.state = state

    def consume_owner_approval(self, ticket: ApprovalTicketLike) -> None:
        nonce_hash = domain_separated_sha256(
            "qc2.owner-approval-nonce.v1",
            canonical_json_bytes({"nonce": ticket.nonce}),
        )
        if nonce_hash in self.state.approval_nonces:
            raise ChampionTransitionError(
                TransitionErrorCode.NONCE_ALREADY_CONSUMED,
                "owner approval nonce was already consumed",
            )
        self.state.approval_nonces[nonce_hash] = ticket.decision_ref.target_id


class InMemoryChampionTransitionStore:
    """Serializable reference implementation; production uses the SQL transaction."""

    def __init__(self, *, id_factory: Callable[[], str] = new_uuidv7) -> None:
        self._id_factory = id_factory
        self._lock = threading.RLock()
        self._state = _StoreState()

    def register_model(
        self,
        model_ref: Mapping[str, Any],
        *,
        lifecycle_state: str,
        retained: bool = False,
        compatibility_verified: bool = True,
    ) -> None:
        model = _reference(
            model_ref, "qc2.models_prediction.ModelManifest.v1", "model_ref"
        )
        if lifecycle_state not in {"PROMOTION_ELIGIBLE", "CHAMPION", "RETIRED"}:
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT, "model lifecycle state is unsupported"
            )
        with self._lock:
            self._state.models[_model_key(model)] = CandidateState(
                model, lifecycle_state, retained, compatibility_verified
            )

    def seed_no_champion(self, epoch_ref: Mapping[str, Any]) -> OperatingSlot:
        epoch = _reference(
            epoch_ref, "qc2.validation.ValidationEpoch.v1", "epoch_ref"
        )
        epoch_id = epoch["target_id"]
        with self._lock:
            existing = self._state.slots.get(epoch_id)
            if existing is not None:
                if existing.slot_state != "NO_CHAMPION" or existing.generation != 0:
                    raise ChampionTransitionError(
                        TransitionErrorCode.STALE_GENERATION,
                        "an operating Champion already exists for this epoch",
                    )
                return existing
            slot = OperatingSlot(epoch_id, "NO_CHAMPION", None, 0, None)
            self._state.slots[epoch_id] = slot
            return slot

    def slot(self, epoch_id: str) -> OperatingSlot:
        with self._lock:
            slot = self._state.slots.get(epoch_id)
            if slot is None:
                return OperatingSlot(epoch_id, "NO_CHAMPION", None, 0, None)
            return slot

    def prepare(
        self,
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
        verification: Any,
        ticket: ApprovalTicketLike,
        *,
        prepared_at: datetime | str,
    ) -> PreparedTransition:
        try:
            request_record = _thaw(request)
            decision_record = _thaw(decision)
            validate_contract("PromotionRequest", request_record)
            validate_contract("PromotionDecision", decision_record)
            verify_content_hash("PromotionDecision", decision_record)
        except (TypeError, ValueError, KeyError) as exc:
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT, "request or approval contract is invalid"
            ) from exc

        verified = getattr(verification, "eligible_for_owner_review", False)
        bundle = getattr(verification, "bundle", None)
        manifest = getattr(bundle, "manifest", None)
        if (
            not verified
            or not isinstance(manifest, Mapping)
            or not getattr(verification, "gate_receipts", ())
            or any(getattr(gate, "status", None) != "PASS" for gate in verification.gate_receipts)
        ):
            raise ChampionTransitionError(
                TransitionErrorCode.NOT_ELIGIBLE,
                "a fully verified, owner-review-eligible bundle is required",
            )
        bundle_record = _thaw(manifest)
        try:
            validate_contract("PromotionBundleManifest", bundle_record)
            verify_content_hash("PromotionBundleManifest", bundle_record)
        except (TypeError, ValueError, KeyError) as exc:
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT, "verified bundle manifest is invalid"
            ) from exc
        if decision_record["decision"] != "APPROVE":
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_APPROVAL, "only an exact APPROVE decision can commit"
            )

        bundle_ref = request_record["bundle_ref"]
        if (
            bundle_ref.get("target_schema_name")
            != "qc2.governance_owner.PromotionBundleManifest.v1"
            or bundle_ref.get("target_id") != bundle_record["id"]
            or bundle_ref.get("content_hash") != bundle_record["content_hash"]
            or not _matches_ref(request_record["candidate_model_ref"], bundle_record["candidate_model_ref"])
            or not _matches_ref(request_record["epoch_ref"], bundle_record["epoch_ref"])
        ):
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT,
                "request is not bound to the verified bundle, candidate, and epoch",
            )
        _reference(
            request_record["epoch_ref"],
            "qc2.validation.ValidationEpoch.v1",
            "request.epoch_ref",
        )
        _reference(
            bundle_record["epoch_ref"],
            "qc2.validation.ValidationEpoch.v1",
            "bundle.epoch_ref",
        )
        if (
            request_record["environment_namespace"] != bundle_record["environment_namespace"]
            or request_record["evidence_class"] != bundle_record["evidence_class"]
        ):
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT,
                "request and verified bundle evidence contexts differ",
            )
        if (
            decision_record["request_hash"] != request_record["request_hash"]
            or decision_record["environment_namespace"] != request_record["environment_namespace"]
        ):
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_APPROVAL, "approval is not bound to this request"
            )
        try:
            kind = TransitionKind(bundle_record["transition_intent"])
        except (KeyError, ValueError) as exc:
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT, "bundle transition intent is not recognized"
            ) from exc

        epoch_id = request_record["epoch_ref"]["target_id"]
        with self._lock:
            if epoch_id not in self._state.slots:
                raise ChampionTransitionError(
                    TransitionErrorCode.NO_CHAMPION,
                    "seed the explicit NO_CHAMPION slot before preparing bootstrap",
                )
            slot = self._state.slots[epoch_id]
        target_ref = _reference(
            bundle_record["candidate_model_ref"],
            "qc2.models_prediction.ModelManifest.v1",
            "candidate_model_ref",
        )
        with self._lock:
            target = self._state.models.get(_model_key(target_ref))
        if target is None or not target.compatibility_verified:
            raise ChampionTransitionError(
                TransitionErrorCode.NOT_ELIGIBLE,
                "candidate is not registered with fresh compatibility verification",
            )
        if kind in {TransitionKind.INITIAL_BOOTSTRAP, TransitionKind.PROMOTION}:
            if target.lifecycle_state != "PROMOTION_ELIGIBLE":
                raise ChampionTransitionError(
                    TransitionErrorCode.NOT_ELIGIBLE,
                    "bootstrap and promotion require a PROMOTION_ELIGIBLE model",
                )
        elif target.lifecycle_state != "RETIRED" or not target.retained:
            raise ChampionTransitionError(
                TransitionErrorCode.NOT_ELIGIBLE,
                "forward rollback requires a retained RETIRED artifact",
            )
        if slot.slot_state == "CHAMPION_SET":
            assert slot.pointer is not None
            if _model_key(slot.pointer["model_ref"]) == _model_key(target_ref):
                raise ChampionTransitionError(
                    TransitionErrorCode.INVALID_INPUT,
                    "a Champion transition cannot select the already-current model",
                )
            if not _prior_ref_matches(bundle_record.get("prior_champion_ref"), slot.pointer):
                raise ChampionTransitionError(
                    TransitionErrorCode.STALE_GENERATION,
                    "bundle prior Champion does not match the current pointer",
                )
            if not _prior_ref_matches(request_record.get("expected_champion_ref"), slot.pointer):
                raise ChampionTransitionError(
                    TransitionErrorCode.STALE_GENERATION,
                    "request expected Champion does not match the current pointer",
                )
        elif (
            bundle_record.get("prior_champion_ref") is not None
            or request_record.get("expected_champion_ref") is not None
        ):
            raise ChampionTransitionError(
                TransitionErrorCode.STALE_GENERATION,
                "NO_CHAMPION bootstrap cannot name a prior Champion",
            )
        expected_kind = (
            TransitionKind.INITIAL_BOOTSTRAP
            if slot.slot_state == "NO_CHAMPION"
            else TransitionKind.PROMOTION
        )
        if kind != expected_kind and kind != TransitionKind.FORWARD_ROLLBACK:
            raise ChampionTransitionError(
                TransitionErrorCode.STALE_GENERATION,
                "transition intent does not match the current operating slot",
            )
        if kind == TransitionKind.FORWARD_ROLLBACK and slot.slot_state != "CHAMPION_SET":
            raise ChampionTransitionError(
                TransitionErrorCode.STALE_GENERATION,
                "forward rollback requires an existing Champion",
            )
        _approval_ticket_matches(
            ticket, request=request_record, decision=decision_record, slot=slot
        )
        return PreparedTransition(
            kind=kind,
            request=request_record,
            decision=decision_record,
            bundle=bundle_record,
            ticket=ticket,
            expected_slot_state=slot.slot_state,
            expected_generation=slot.generation,
            expected_pointer_hash=slot.pointer_hash,
            target=target,
            prepared_at=_utc_text(prepared_at),
        )

    def commit(
        self,
        prepared: PreparedTransition,
        approval_authority: ApprovalRecheckPort,
        *,
        now: datetime | str,
        fault_at: str | None = None,
    ) -> Mapping[str, Any]:
        if prepared.bundle["environment_namespace"] != "test":
            if PRODUCTION_APPROVAL_ENABLED is False:
                raise ChampionTransitionError(
                    TransitionErrorCode.APPROVAL_DISABLED,
                    "real owner approval and non-test Champion transitions are disabled",
                )
        if (
            prepared.bundle["environment_namespace"] != "test"
            or prepared.bundle["evidence_class"] != "SYNTHETIC_FIXTURE"
            or prepared.request["environment_namespace"] != "test"
            or prepared.request["evidence_class"] != "SYNTHETIC_FIXTURE"
            or prepared.decision["environment_namespace"] != "test"
            or prepared.decision["evidence_class"] != "SYNTHETIC_FIXTURE"
        ):
            raise ChampionTransitionError(
                TransitionErrorCode.APPROVAL_DISABLED,
                "fixture transition proofs are restricted to the test namespace",
            )
        valid_faults = {
            "before_approval",
            "after_approval",
            "before_nonce_consumption",
            "after_nonce_consumption",
            "before_evidence",
            "after_evidence",
            "before_receipt",
            "after_receipt",
            "before_lifecycle",
            "after_lifecycle",
            "before_pointer",
            "after_pointer",
            "before_slot_cas",
            "after_slot_cas",
            "before_outbox",
            "after_outbox",
            "after_commit",
        }
        if fault_at is not None and fault_at not in valid_faults:
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT, "unknown transition fault point"
            )
        committed_receipt: Mapping[str, Any] | None = None
        with self._lock:
            decision_id = prepared.decision["id"]
            existing_id = self._state.receipt_by_decision.get(decision_id)
            if existing_id is not None:
                existing = self._state.receipts[existing_id]
                if (
                    existing["request_ref"]["target_id"] == prepared.request["id"]
                    and existing["decision_ref"]["content_hash"]
                    == prepared.decision["content_hash"]
                    and existing["new_generation"] > prepared.expected_generation
                ):
                    return copy.deepcopy(existing)
                raise ChampionTransitionError(
                    TransitionErrorCode.INVALID_APPROVAL,
                    "decision was already used for a different transition",
                )

            live_slot = self._state.slots.get(
                prepared.request["epoch_ref"]["target_id"],
                OperatingSlot(prepared.request["epoch_ref"]["target_id"], "NO_CHAMPION", None, 0, None),
            )
            if (
                live_slot.slot_state != prepared.expected_slot_state
                or live_slot.generation != prepared.expected_generation
                or live_slot.pointer_hash != prepared.expected_pointer_hash
            ):
                raise ChampionTransitionError(
                    TransitionErrorCode.STALE_GENERATION,
                    "operating Champion changed after prepare; no mutation was committed",
                )
            self._checkpoint(fault_at, "before_approval")
            recheck = approval_authority.recheck_for_commit(
                prepared.decision["id"],
                now=datetime.fromisoformat(_utc_text(now).replace("Z", "+00:00")),
            )
            fresh_ticket = getattr(recheck, "ticket", None)
            if (
                not getattr(recheck, "checks_passed", False)
                or not getattr(recheck, "action_authorized", False)
                or fresh_ticket is None
            ):
                raise ChampionTransitionError(
                    TransitionErrorCode.INVALID_APPROVAL,
                    "owner approval failed its commit-time identity and state recheck",
                )
            _approval_ticket_matches(
                fresh_ticket,
                request=prepared.request,
                decision=prepared.decision,
                slot=live_slot,
            )
            if fresh_ticket.nonce != prepared.ticket.nonce:
                raise ChampionTransitionError(
                    TransitionErrorCode.INVALID_APPROVAL,
                    "commit-time recheck returned a different reserved nonce",
                )
            self._checkpoint(fault_at, "after_approval")

            staged = copy.deepcopy(self._state)
            tx = _StagedApprovalTransaction(staged)
            self._checkpoint(fault_at, "before_nonce_consumption")
            tx.consume_owner_approval(fresh_ticket)
            self._checkpoint(fault_at, "after_nonce_consumption")
            timestamp = _utc_text(now)
            receipt_id = self._id_factory()
            pointer_id = self._id_factory()
            event_id = self._id_factory()
            next_generation = live_slot.generation + 1
            epoch_ref = _thaw(prepared.request["epoch_ref"])
            target_ref = _thaw(prepared.target.model_ref)
            source_refs = [
                _thaw(prepared.request["bundle_ref"]),
                {
                    "target_schema_name": "qc2.governance_owner.PromotionRequest.v1",
                    "target_id": prepared.request["id"],
                },
                {
                    "target_schema_name": "qc2.governance_owner.PromotionDecision.v1",
                    "target_id": prepared.decision["id"],
                    "content_hash": prepared.decision["content_hash"],
                },
            ]
            pointer_base = {
                "schema_name": "qc2.governance_owner.ChampionPointer.v1",
                "schema_version": "1.0",
                "id": pointer_id,
                "created_at": timestamp,
                "owning_authority": "promotion",
                "evidence_class": prepared.bundle["evidence_class"],
                "environment_namespace": prepared.bundle["environment_namespace"],
                "source_refs": source_refs,
                "epoch_ref": epoch_ref,
                "role": "OPERATING",
                "model_ref": target_ref,
                "generation": next_generation,
                "transitioned_at": timestamp,
                "transition_receipt_ref": {
                    "target_schema_name": "qc2.governance_owner.PromotionReceipt.v1",
                    "target_id": receipt_id,
                },
            }
            pointer_hash = domain_separated_sha256(
                POINTER_HASH_DOMAIN, canonical_json_bytes(pointer_base)
            )
            pointer = {**pointer_base, "pointer_hash": pointer_hash}
            try:
                validate_contract("ChampionPointer", pointer)
            except (TypeError, ValueError, KeyError) as exc:
                raise ChampionTransitionError(
                    TransitionErrorCode.INVALID_INPUT, "prepared ChampionPointer is invalid"
                ) from exc

            nonce_hash = domain_separated_sha256(
                "qc2.owner-approval-nonce.v1",
                canonical_json_bytes({"nonce": fresh_ticket.nonce}),
            )
            event_payload = {
                "transition_kind": prepared.kind.value,
                "request_id": prepared.request["id"],
                "decision_id": prepared.decision["id"],
                "epoch_id": live_slot.epoch_id,
                "prior_generation": live_slot.generation,
                "new_generation": next_generation,
                "pointer_id": pointer_id,
                "pointer_hash": pointer_hash,
                "approval_nonce_hash": nonce_hash,
            }
            event_hash = domain_separated_sha256(
                TRANSITION_EVENT_DOMAIN, canonical_json_bytes(event_payload)
            )
            event = {
                "schema_name": "qc2.integrity_build.EvidenceEvent.v1",
                "id": event_id,
                "event_type": "champion_transition_committed",
                "payload": event_payload,
                "event_hash": event_hash,
                "content_hash": domain_separated_sha256(
                    "qc2.contract-content.v1/qc2.integrity_build.evidenceevent.v1/1.0",
                    canonical_json_bytes({"id": event_id, "event_hash": event_hash}),
                ),
            }
            self._checkpoint(fault_at, "before_evidence")
            staged.evidence_events[event_id] = event
            self._checkpoint(fault_at, "after_evidence")
            evidence_ref = {
                "target_schema_name": "qc2.integrity_build.EvidenceEvent.v1",
                "target_id": event_id,
                "content_hash": event["content_hash"],
            }
            receipt = {
                "schema_name": "qc2.governance_owner.PromotionReceipt.v1",
                "schema_version": "1.0",
                "id": receipt_id,
                "created_at": timestamp,
                "owning_authority": "promotion",
                "evidence_class": prepared.bundle["evidence_class"],
                "environment_namespace": prepared.bundle["environment_namespace"],
                "source_refs": source_refs,
                "request_ref": {
                    "target_schema_name": "qc2.governance_owner.PromotionRequest.v1",
                    "target_id": prepared.request["id"],
                },
                "decision_ref": {
                    "target_schema_name": "qc2.governance_owner.PromotionDecision.v1",
                    "target_id": prepared.decision["id"],
                    "content_hash": prepared.decision["content_hash"],
                },
                "transition_state": "COMMITTED",
                "prior_generation": live_slot.generation,
                "new_generation": next_generation,
                "committed_at": timestamp,
                "evidence_ref": evidence_ref,
                "pointer_hash": pointer_hash,
            }
            try:
                validate_contract("PromotionReceipt", receipt)
            except (TypeError, ValueError, KeyError) as exc:
                raise ChampionTransitionError(
                    TransitionErrorCode.INVALID_INPUT, "PromotionReceipt is invalid"
                ) from exc
            self._checkpoint(fault_at, "before_receipt")
            staged.receipts[receipt_id] = receipt
            staged.receipt_by_decision[prepared.decision["id"]] = receipt_id
            self._checkpoint(fault_at, "after_receipt")

            self._checkpoint(fault_at, "before_lifecycle")
            if live_slot.pointer is not None:
                old_model = live_slot.pointer["model_ref"]
                old_key = _model_key(old_model)
                old_state = staged.models[old_key]
                staged.models[old_key] = CandidateState(
                    old_state.model_ref, "RETIRED", True, old_state.compatibility_verified
                )
                staged.lifecycle_events.append(
                    {"model_ref": _thaw(old_model), "prior_state": "CHAMPION",
                     "next_state": "RETIRED", "evidence_ref": evidence_ref}
                )
            staged.models[_model_key(target_ref)] = CandidateState(
                target_ref, "CHAMPION", prepared.target.retained,
                prepared.target.compatibility_verified,
            )
            staged.lifecycle_events.append(
                {
                    "model_ref": target_ref,
                    "prior_state": prepared.target.lifecycle_state,
                    "next_state": "CHAMPION",
                    "evidence_ref": evidence_ref,
                }
            )
            self._checkpoint(fault_at, "after_lifecycle")

            self._checkpoint(fault_at, "before_pointer")
            staged.pointers[pointer_id] = pointer
            self._checkpoint(fault_at, "after_pointer")
            self._checkpoint(fault_at, "before_slot_cas")
            staged.slots[live_slot.epoch_id] = OperatingSlot(
                live_slot.epoch_id, "CHAMPION_SET", pointer, next_generation, pointer_hash
            )
            self._checkpoint(fault_at, "after_slot_cas")

            payload = {
                "epoch_id": live_slot.epoch_id,
                "pointer_id": pointer_id,
                "pointer_hash": pointer_hash,
                "generation": next_generation,
                "model_id": target_ref["target_id"],
                "model_hash": target_ref["content_hash"],
            }
            outbox_id = self._id_factory()
            outbox = OutboxMessage(
                id=outbox_id,
                logical_operation_id=receipt_id,
                message_type="champion_model_load",
                payload_hash=domain_separated_sha256(
                    LOAD_OUTBOX_DOMAIN, canonical_json_bytes(payload)
                ),
                payload=payload,
            )
            self._checkpoint(fault_at, "before_outbox")
            staged.outbox[receipt_id] = outbox
            self._checkpoint(fault_at, "after_outbox")
            self._state = staged
            committed_receipt = copy.deepcopy(receipt)

        assert committed_receipt is not None
        if fault_at == "after_commit":
            raise CommitOutcomeUnknown(committed_receipt["id"])
        return committed_receipt

    def confirm_worker_load(
        self,
        *,
        epoch_id: str,
        pointer_id: str,
        generation: int,
        pointer_hash: str,
        model_id: str,
        model_hash: str,
        worker_id: str,
        status: str,
        checked_at: datetime | str,
        receipt_hash: str,
        failure_code: str | None = None,
    ) -> LoadConfirmation:
        if status not in {"LOADED", "FAILED"} or not _UUID7.fullmatch(worker_id):
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT, "worker load confirmation is invalid"
            )
        if not _SHA256.fullmatch(pointer_hash) or not _SHA256.fullmatch(receipt_hash):
            raise ChampionTransitionError(
                TransitionErrorCode.INVALID_INPUT, "worker load hashes must be SHA-256"
            )
        with self._lock:
            slot = self._state.slots.get(epoch_id)
            if (
                slot is None
                or slot.pointer is None
                or slot.pointer["id"] != pointer_id
                or slot.generation != generation
                or slot.pointer_hash != pointer_hash
                or slot.pointer["model_ref"]["target_id"] != model_id
                or slot.pointer["model_ref"]["content_hash"] != model_hash
            ):
                raise ChampionTransitionError(
                    TransitionErrorCode.STALE_GENERATION,
                    "worker confirmation does not match the current committed generation",
                )
            confirmation = LoadConfirmation(
                id=self._id_factory(),
                epoch_id=epoch_id,
                pointer_id=pointer_id,
                generation=generation,
                pointer_hash=pointer_hash,
                model_id=model_id,
                model_hash=model_hash,
                worker_id=worker_id,
                status=status,
                checked_at=_utc_text(checked_at),
                receipt_hash=receipt_hash,
                failure_code=failure_code if status == "FAILED" else None,
            )
            self._state.load_confirmations.setdefault(epoch_id, []).append(confirmation)
            return confirmation

    def latest_load_confirmation(self, epoch_id: str) -> LoadConfirmation | None:
        with self._lock:
            confirmations = self._state.load_confirmations.get(epoch_id, [])
            return copy.deepcopy(confirmations[-1]) if confirmations else None

    def receipt(self, receipt_id: str) -> Mapping[str, Any] | None:
        with self._lock:
            value = self._state.receipts.get(receipt_id)
            return copy.deepcopy(value) if value is not None else None

    def outbox_message(self, logical_operation_id: str) -> OutboxMessage | None:
        with self._lock:
            return copy.deepcopy(self._state.outbox.get(logical_operation_id))

    def committed_pointer_count(self, epoch_id: str) -> int:
        with self._lock:
            return sum(
                pointer["epoch_ref"]["target_id"] == epoch_id
                and pointer["role"] == "OPERATING"
                for pointer in self._state.pointers.values()
            )

    @staticmethod
    def _checkpoint(fault_at: str | None, name: str) -> None:
        if fault_at == name:
            raise ChampionTransitionError(
                TransitionErrorCode.FAULT_INJECTED, f"transition fault injected at {name}"
            )


class PromotionReadinessGuard:
    """PredictionInputPort decorator that blocks runs until the current generation loads."""

    def __init__(self, source: TransitionSnapshotSource) -> None:
        self._source = source

    def capture_bindings(self, epoch_ref: Mapping[str, Any], session_id: str) -> Any:
        snapshot = self._source.capture_transition_snapshot(epoch_ref, session_id)
        pointer = _thaw(snapshot.pointer)
        bindings_pointer = _thaw(snapshot.bindings.operating_champion_pointer)
        confirmation = snapshot.latest_load_confirmation
        if (
            pointer.get("role") != "OPERATING"
            or pointer.get("epoch_ref", {}).get("target_id") != epoch_ref.get("target_id")
            or pointer.get("id") != bindings_pointer.get("id")
            or pointer.get("generation") != bindings_pointer.get("generation")
            or pointer.get("pointer_hash") != bindings_pointer.get("pointer_hash")
        ):
            raise ChampionTransitionError(
                TransitionErrorCode.STALE_GENERATION,
                "prediction inputs and operating pointer are not from the same snapshot",
            )
        if (
            confirmation is None
            or confirmation.status != "LOADED"
            or confirmation.epoch_id != pointer["epoch_ref"]["target_id"]
            or confirmation.pointer_id != pointer["id"]
            or confirmation.generation != pointer["generation"]
            or confirmation.pointer_hash != pointer["pointer_hash"]
            or confirmation.model_id != pointer["model_ref"]["target_id"]
            or confirmation.model_hash != pointer["model_ref"]["content_hash"]
        ):
            raise ChampionTransitionError(
                TransitionErrorCode.LOAD_NOT_CONFIRMED,
                "the current committed Champion generation has not been confirmed loaded",
            )
        return snapshot.bindings
