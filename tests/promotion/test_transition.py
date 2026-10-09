from __future__ import annotations

import copy
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from qc2_contracts.runtime import canonical_content_hash, new_uuidv7
from qc2_prediction_authority.authority import PredictionAuthority
from qc2_prediction_authority.models import PredictionBindings, RetryPolicy
from qc2_promotion.transition import (
    PRODUCTION_APPROVAL_ENABLED,
    ChampionTransitionError,
    CommitOutcomeUnknown,
    InMemoryChampionTransitionStore,
    PredictionReadinessSnapshot,
    PromotionReadinessGuard,
    TransitionErrorCode,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "contracts"
    / "fixtures"
    / "v1"
    / "valid.json"
)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
TRANSITION_TIME = "2026-10-08T18:00:00Z"


@lru_cache(maxsize=1)
def _fixtures() -> dict[str, dict[str, Any]]:
    return {
        entry["contract"]: entry["payload"]
        for entry in json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    }


def _contract(name: str) -> dict[str, Any]:
    return copy.deepcopy(_fixtures()[name])


def _ref(schema_name: str, number: int, content_hash: str = HASH_A) -> dict[str, str]:
    return {
        "target_schema_name": schema_name,
        "target_id": f"018f0000-0000-7000-8000-{number:012x}",
        "content_hash": content_hash,
    }


def _model_ref() -> dict[str, str]:
    model = _contract("ModelManifest")
    model["id"] = new_uuidv7()
    model["created_at"] = TRANSITION_TIME
    model["content_hash"] = canonical_content_hash("ModelManifest", model)
    return {
        "target_schema_name": model["schema_name"],
        "target_id": model["id"],
        "content_hash": model["content_hash"],
    }


class _ApprovalRecheck:
    def __init__(self, ticket: Any) -> None:
        self.ticket = ticket
        self.calls = 0

    def recheck_for_commit(self, decision_id: str, *, now: Any) -> Any:
        self.calls += 1
        return SimpleNamespace(
            checks_passed=True,
            action_authorized=True,
            decision_id=decision_id,
            ticket=self.ticket,
        )


def _prepare(
    store: InMemoryChampionTransitionStore,
    model_ref: dict[str, str],
    *,
    kind: str = "initial_bootstrap",
    prior_champion_ref: dict[str, str] | None = None,
    environment_namespace: str = "test",
    nonce: str | None = None,
) -> tuple[Any, _ApprovalRecheck]:
    epoch_ref = _ref("qc2.validation.ValidationEpoch.v1", 1)
    bundle = _contract("PromotionBundleManifest")
    bundle.update(
        id=new_uuidv7(),
        created_at=TRANSITION_TIME,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace=environment_namespace,
        candidate_model_ref=copy.deepcopy(model_ref),
        prior_champion_ref=copy.deepcopy(prior_champion_ref),
        epoch_ref=copy.deepcopy(epoch_ref),
        transition_intent=kind,
        expires_at="2026-10-09T18:00:00Z",
    )
    bundle["content_hash"] = canonical_content_hash("PromotionBundleManifest", bundle)

    request = _contract("PromotionRequest")
    request_hash = hashlib.sha256(f"request:{new_uuidv7()}".encode()).hexdigest()
    request.update(
        id=new_uuidv7(),
        created_at=TRANSITION_TIME,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace=environment_namespace,
        bundle_ref={
            "target_schema_name": bundle["schema_name"],
            "target_id": bundle["id"],
            "content_hash": bundle["content_hash"],
        },
        candidate_model_ref=copy.deepcopy(model_ref),
        expected_champion_ref=copy.deepcopy(prior_champion_ref),
        epoch_ref=copy.deepcopy(epoch_ref),
        requested_at=TRANSITION_TIME,
        expires_at="2026-10-09T18:00:00Z",
        request_hash=request_hash,
    )

    decision = _contract("PromotionDecision")
    decision.update(
        id=new_uuidv7(),
        created_at=TRANSITION_TIME,
        signed_at=TRANSITION_TIME,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace=environment_namespace,
        request_hash=request_hash,
    )
    decision["content_hash"] = canonical_content_hash("PromotionDecision", decision)
    challenge_ref = decision["challenge_ref"]
    ticket = SimpleNamespace(
        nonce=nonce or f"approval-{new_uuidv7()}",
        request_hash=request_hash,
        expected_champion_hash=(
            store.slot(epoch_ref["target_id"]).pointer_hash
        ),
        expected_generation=store.slot(epoch_ref["target_id"]).generation,
        idempotency_key=f"idempotency-{request['id']}",
        envelope_hash=HASH_C,
        decision_ref=SimpleNamespace(
            target_schema_name=decision["schema_name"],
            target_id=decision["id"],
            content_hash=decision["content_hash"],
        ),
        promotion_challenge_ref=SimpleNamespace(**challenge_ref),
    )
    verification = SimpleNamespace(
        eligible_for_owner_review=True,
        bundle=SimpleNamespace(manifest=bundle),
        gate_receipts=(SimpleNamespace(status="PASS"),),
    )
    prepared = store.prepare(
        request,
        decision,
        verification,
        ticket,
        prepared_at=TRANSITION_TIME,
    )
    return prepared, _ApprovalRecheck(ticket)


def _seeded_store(
    model_refs: tuple[dict[str, str], ...] = (),
) -> tuple[InMemoryChampionTransitionStore, dict[str, str]]:
    store = InMemoryChampionTransitionStore()
    epoch_ref = _ref("qc2.validation.ValidationEpoch.v1", 1)
    store.seed_no_champion(epoch_ref)
    for model_ref in model_refs:
        store.register_model(model_ref, lifecycle_state="PROMOTION_ELIGIBLE")
    return store, epoch_ref


def test_seed_no_champion_is_required_before_bootstrap_prepare() -> None:
    store = InMemoryChampionTransitionStore()
    model_ref = _model_ref()
    store.register_model(model_ref, lifecycle_state="PROMOTION_ELIGIBLE")
    with pytest.raises(ChampionTransitionError) as raised:
        _prepare(store, model_ref)
    assert raised.value.code == TransitionErrorCode.NO_CHAMPION


@pytest.mark.parametrize(
    "fault_at",
    (
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
    ),
)
def test_transactional_faults_restore_all_authoritative_state(fault_at: str) -> None:
    model_ref = _model_ref()
    store, epoch_ref = _seeded_store((model_ref,))
    prepared, approval = _prepare(store, model_ref)
    before = copy.deepcopy(store._state)

    with pytest.raises(ChampionTransitionError) as raised:
        store.commit(
            prepared,
            approval,
            now=TRANSITION_TIME,
            fault_at=fault_at,
        )

    assert raised.value.code == TransitionErrorCode.FAULT_INJECTED
    assert store._state == before
    assert store.slot(epoch_ref["target_id"]).slot_state == "NO_CHAMPION"


def test_bootstrap_receipt_and_outbox_are_durable_and_idempotent() -> None:
    model_ref = _model_ref()
    store, epoch_ref = _seeded_store((model_ref,))
    prepared, approval = _prepare(store, model_ref)

    receipt = store.commit(prepared, approval, now=TRANSITION_TIME)
    replay = store.commit(prepared, approval, now=TRANSITION_TIME)

    slot = store.slot(epoch_ref["target_id"])
    assert slot.slot_state == "CHAMPION_SET"
    assert slot.generation == 1
    assert slot.pointer is not None
    assert receipt == replay
    assert receipt["transition_state"] == "COMMITTED"
    assert receipt["prior_generation"] == 0
    assert receipt["new_generation"] == 1
    assert store.receipt(receipt["id"]) == receipt
    assert store.committed_pointer_count(epoch_ref["target_id"]) == 1
    outbox = store.outbox_message(receipt["id"])
    assert outbox is not None
    assert outbox.message_type == "champion_model_load"
    assert outbox.payload["pointer_id"] == slot.pointer["id"]
    assert len(store._state.approval_nonces) == 1
    assert approval.calls == 1

    unknown_model = _model_ref()
    unknown_store, _ = _seeded_store((unknown_model,))
    unknown_prepared, unknown_approval = _prepare(unknown_store, unknown_model)
    with pytest.raises(CommitOutcomeUnknown) as unknown:
        unknown_store.commit(
            unknown_prepared,
            unknown_approval,
            now=TRANSITION_TIME,
            fault_at="after_commit",
        )
    unknown_slot = unknown_store.slot(epoch_ref["target_id"])
    assert unknown_slot.pointer is not None
    recovered = unknown_store.receipt(unknown.value.receipt_id)
    assert recovered is not None
    assert recovered["new_generation"] == 1


def test_compare_and_swap_allows_only_one_prepared_racer() -> None:
    model_one, model_two = _model_ref(), _model_ref()
    store, epoch_ref = _seeded_store((model_one, model_two))
    prepared_one, approval_one = _prepare(store, model_one, nonce="racer-one")
    prepared_two, approval_two = _prepare(store, model_two, nonce="racer-two")
    barrier = threading.Barrier(3)

    def commit(prepared: Any, approval: _ApprovalRecheck) -> Any:
        barrier.wait()
        try:
            return store.commit(prepared, approval, now=TRANSITION_TIME)
        except ChampionTransitionError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(commit, prepared_one, approval_one)
        second = pool.submit(commit, prepared_two, approval_two)
        barrier.wait()
        results = (first.result(), second.result())

    successes = [result for result in results if isinstance(result, dict)]
    failures = [result for result in results if isinstance(result, TransitionErrorCode)]
    assert len(successes) == 1
    assert failures == [TransitionErrorCode.STALE_GENERATION]
    assert store.slot(epoch_ref["target_id"]).generation == 1
    assert store.committed_pointer_count(epoch_ref["target_id"]) == 1
    assert len(store._state.approval_nonces) == 1


def _prediction_bindings(
    epoch_ref: dict[str, str], pointer: dict[str, Any], session_id: str
) -> PredictionBindings:
    model_ref = copy.deepcopy(pointer["model_ref"])
    next_open = (
        "2026-10-12T13:30:00Z"
        if session_id == "2026-10-09"
        else "2026-10-09T13:30:00Z"
    )
    bindings = PredictionBindings(
        epoch_ref=copy.deepcopy(epoch_ref),
        snapshot_ref=_ref("qc2.identity_market.MarketSnapshot.v1", 2),
        census_ref=_ref("qc2.identity_market.CandidateCensus.v1", 3),
        universe_ref=_ref("qc2.identity_market.UniverseManifest.v1", 4),
        feature_registry_ref=_ref("qc2.scientific_definitions.FeatureRegistry.v1", 5),
        protocol_registry_ref=_ref(
            "qc2.scientific_definitions.RunnerProtocolRegistry.v1", 6
        ),
        label_registry_ref=_ref("qc2.scientific_definitions.LabelRegistry.v1", 7),
        score_manifest_ref=_ref("qc2.scientific_definitions.ScoreManifest.v1", 8),
        operating_champion_pointer=copy.deepcopy(pointer),
        operating_model_ref=model_ref,
        reference_model_ref=_ref("qc2.models_prediction.ModelManifest.v1", 10, HASH_C),
        shadow_prediction_set_refs=(
            _ref("qc2.models_prediction.ShadowPredictionSet.v1", 11),
        ),
        baseline_manifest_refs=(
            _ref("qc2.scientific_definitions.BaselineManifest.v1", 12, HASH_B),
        ),
        calendar_ref=_ref("qc2.time_operation.CalendarManifest.v1", 13, HASH_C),
        memory_index_refs=(
            _ref("qc2.outcomes_research.MemoryIndexManifest.v1", 14, HASH_C),
        ),
        scientific_code_ref=_ref("qc2.integrity_build.ArtifactManifest.v1", 15, HASH_C),
        eligible_instrument_refs=(
            _ref("qc2.identity_market.Instrument.v1", 101),
            _ref("qc2.identity_market.Instrument.v1", 102, HASH_B),
            _ref("qc2.identity_market.Instrument.v1", 103, HASH_C),
        ),
        session_id=session_id,
        regime="trending",
        decision_deadline=f"{session_id}T19:30:00Z",
        seal_deadline=f"{session_id}T20:00:00Z",
        next_regular_session_open_at=next_open,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
        retry_policy=RetryPolicy(2, ("temporary_io",)),
    )
    bindings.normalized()
    return bindings


class _ReadinessSource:
    def __init__(self, store: InMemoryChampionTransitionStore) -> None:
        self.store = store

    def capture_transition_snapshot(
        self, epoch_ref: dict[str, str], session_id: str
    ) -> PredictionReadinessSnapshot:
        slot = self.store.slot(epoch_ref["target_id"])
        assert slot.pointer is not None
        pointer = copy.deepcopy(slot.pointer)
        bindings = _prediction_bindings(epoch_ref, pointer, session_id)
        return PredictionReadinessSnapshot(
            bindings=bindings,
            pointer=pointer,
            latest_load_confirmation=self.store.latest_load_confirmation(
                epoch_ref["target_id"]
            ),
        )


def _schedule_and_start(
    authority: PredictionAuthority,
    source: PromotionReadinessGuard,
    epoch_ref: dict[str, str],
    session_id: str,
) -> dict[str, Any]:
    scheduled = authority.schedule_sessions(
        epoch_ref=epoch_ref,
        session_ids=(session_id,),
        deadlines={session_id: f"{session_id}T19:30:00Z"},
        created_at=f"{session_id}T18:05:00Z",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )[0]
    return authority.create_run(
        scheduled_attempt_id=scheduled["id"],
        source=source,
        created_at=f"{session_id}T18:10:00Z",
    )


def _find_operating_pointer(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("schema_name") == "qc2.governance_owner.ChampionPointer.v1":
            return value
        for nested in value.values():
            found = _find_operating_pointer(nested)
            if found is not None:
                return found
    elif isinstance(value, (tuple, list)):
        for nested in value:
            found = _find_operating_pointer(nested)
            if found is not None:
                return found
    return None


def test_load_gate_blocks_runs_and_existing_run_keeps_its_generation() -> None:
    first_model, second_model = _model_ref(), _model_ref()
    store, epoch_ref = _seeded_store((first_model, second_model))
    initial, initial_approval = _prepare(store, first_model)
    first_receipt = store.commit(initial, initial_approval, now=TRANSITION_TIME)
    first_slot = store.slot(epoch_ref["target_id"])
    assert first_slot.pointer is not None
    first_pointer = copy.deepcopy(first_slot.pointer)

    worker_id = new_uuidv7()
    store.confirm_worker_load(
        epoch_id=epoch_ref["target_id"],
        pointer_id=first_pointer["id"],
        generation=1,
        pointer_hash=first_pointer["pointer_hash"],
        model_id=first_model["target_id"],
        model_hash=first_model["content_hash"],
        worker_id=worker_id,
        status="FAILED",
        checked_at="2026-10-08T18:01:00Z",
        receipt_hash=HASH_A,
        failure_code="model_load_failed",
    )
    source = PromotionReadinessGuard(_ReadinessSource(store))
    authority = PredictionAuthority()
    with pytest.raises(ChampionTransitionError) as not_loaded:
        _schedule_and_start(authority, source, epoch_ref, "2026-10-08")
    assert not_loaded.value.code == TransitionErrorCode.LOAD_NOT_CONFIRMED

    store.confirm_worker_load(
        epoch_id=epoch_ref["target_id"],
        pointer_id=first_pointer["id"],
        generation=1,
        pointer_hash=first_pointer["pointer_hash"],
        model_id=first_model["target_id"],
        model_hash=first_model["content_hash"],
        worker_id=worker_id,
        status="LOADED",
        checked_at="2026-10-08T18:02:00Z",
        receipt_hash=HASH_B,
    )
    first_run = _schedule_and_start(authority, source, epoch_ref, "2026-10-08")

    prior_champion_ref = {
        "target_schema_name": first_pointer["schema_name"],
        "target_id": first_pointer["id"],
        "content_hash": first_pointer["pointer_hash"],
    }
    promotion, promotion_approval = _prepare(
        store,
        second_model,
        kind="promotion",
        prior_champion_ref=prior_champion_ref,
        nonce="promotion-after-run",
    )
    store.commit(promotion, promotion_approval, now="2026-10-08T18:15:00Z")

    saved_run = authority.get_run(first_run["contract"]["id"])
    saved_pointer = _find_operating_pointer(saved_run["binding_snapshot"])
    assert saved_pointer is not None
    assert saved_pointer["id"] == first_pointer["id"]
    assert saved_pointer["generation"] == 1

    with pytest.raises(ChampionTransitionError) as second_generation_not_loaded:
        _schedule_and_start(authority, source, epoch_ref, "2026-10-09")
    assert second_generation_not_loaded.value.code == TransitionErrorCode.LOAD_NOT_CONFIRMED

    second_slot = store.slot(epoch_ref["target_id"])
    assert second_slot.pointer is not None
    second_pointer = copy.deepcopy(second_slot.pointer)
    store.confirm_worker_load(
        epoch_id=epoch_ref["target_id"],
        pointer_id=second_pointer["id"],
        generation=2,
        pointer_hash=second_pointer["pointer_hash"],
        model_id=second_model["target_id"],
        model_hash=second_model["content_hash"],
        worker_id=new_uuidv7(),
        status="LOADED",
        checked_at="2026-10-08T18:20:00Z",
        receipt_hash=HASH_C,
    )
    second_run = _schedule_and_start(authority, source, epoch_ref, "2026-10-09")
    second_run_pointer = _find_operating_pointer(
        authority.get_run(second_run["contract"]["id"])["binding_snapshot"]
    )
    assert second_run_pointer is not None
    assert second_run_pointer["id"] == second_pointer["id"]
    assert second_run_pointer["generation"] == 2
    assert store.receipt(first_receipt["id"]) == first_receipt


def test_forward_rollback_is_a_new_commit_to_a_retained_retired_model() -> None:
    original_model, challenger = _model_ref(), _model_ref()
    store, epoch_ref = _seeded_store((original_model, challenger))
    initial, approval = _prepare(store, original_model)
    store.commit(initial, approval, now=TRANSITION_TIME)
    original_pointer = store.slot(epoch_ref["target_id"]).pointer
    assert original_pointer is not None

    promotion, promotion_approval = _prepare(
        store,
        challenger,
        kind="promotion",
        prior_champion_ref={
            "target_schema_name": original_pointer["schema_name"],
            "target_id": original_pointer["id"],
            "content_hash": original_pointer["pointer_hash"],
        },
    )
    store.commit(promotion, promotion_approval, now="2026-10-08T18:10:00Z")
    current_pointer = store.slot(epoch_ref["target_id"]).pointer
    assert current_pointer is not None

    rollback, rollback_approval = _prepare(
        store,
        original_model,
        kind="forward_rollback",
        prior_champion_ref={
            "target_schema_name": current_pointer["schema_name"],
            "target_id": current_pointer["id"],
            "content_hash": current_pointer["pointer_hash"],
        },
    )
    receipt = store.commit(
        rollback,
        rollback_approval,
        now="2026-10-08T18:20:00Z",
    )

    slot = store.slot(epoch_ref["target_id"])
    assert slot.generation == 3
    assert slot.pointer is not None
    assert slot.pointer["model_ref"] == original_model
    assert receipt["prior_generation"] == 2
    assert receipt["new_generation"] == 3
    assert store._state.models[
        (original_model["target_id"], original_model["content_hash"])
    ].lifecycle_state == "CHAMPION"
    assert store._state.models[
        (challenger["target_id"], challenger["content_hash"])
    ].lifecycle_state == "RETIRED"


def test_synthetic_approval_cannot_commit_outside_test_namespace() -> None:
    assert PRODUCTION_APPROVAL_ENABLED is False
    model_ref = _model_ref()
    store, _ = _seeded_store((model_ref,))
    prepared, approval = _prepare(
        store,
        model_ref,
        environment_namespace="production",
    )
    with pytest.raises(ChampionTransitionError) as raised:
        store.commit(prepared, approval, now=TRANSITION_TIME)
    assert raised.value.code == TransitionErrorCode.APPROVAL_DISABLED
