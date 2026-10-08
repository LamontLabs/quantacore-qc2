from __future__ import annotations

import asyncio
import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

import pytest

from qc2_contracts.runtime import (
    canonical_content_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    validate_contract,
    verify_content_hash,
)
from qc2_integrity_build.verification import (
    CHECKPOINT_ARTIFACT_ROOT_DOMAIN,
    CHECKPOINT_HASH_DOMAIN,
    CheckpointRecord,
)
from qc2_prediction_authority import (
    FeatureRow,
    PredictionAnchorError,
    PredictionAuthority,
    PredictionAuthorityError,
    PredictionBindings,
    RetryPolicy,
    ScoreResult,
    anchor_prediction_seal,
)

SESSION = "2026-10-08"
CREATED_AT = "2026-10-08T19:30:00Z"
SCHEDULED_AT = "2026-10-08T19:00:00Z"
DECISION_DEADLINE = "2026-10-08T21:00:00Z"
SEAL_DEADLINE = "2026-10-08T21:05:00Z"
NEXT_OPEN = "2026-10-09T13:30:00Z"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def id_for(number: int) -> str:
    return f"018f0000-0000-7000-8000-{number:012x}"


def ref(schema: str, number: int, content_hash: str | None = None) -> dict[str, str]:
    result = {
        "target_schema_name": schema,
        "target_id": id_for(number),
    }
    if content_hash is not None:
        result["content_hash"] = content_hash
    return result


class IdFactory:
    def __init__(self) -> None:
        self.value = 10_000
        self.lock = threading.Lock()

    def __call__(self) -> str:
        with self.lock:
            self.value += 1
            return id_for(self.value)


def make_bindings(
    *,
    generation: int = 1,
    evidence_class: str = "SYNTHETIC_FIXTURE",
    environment_namespace: str = "test",
) -> PredictionBindings:
    epoch_ref = ref("qc2.validation.ValidationEpoch.v1", 1, HASH_A)
    operating_model_ref = ref("qc2.models_prediction.ModelManifest.v1", 9, HASH_B)
    pointer = {
        "schema_name": "qc2.governance_owner.ChampionPointer.v1",
        "schema_version": "1.0",
        "id": id_for(20 + generation),
        "created_at": "2026-10-08T18:00:00Z",
        "owning_authority": "promotion",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": [],
        "epoch_ref": copy.deepcopy(epoch_ref),
        "role": "OPERATING",
        "model_ref": copy.deepcopy(operating_model_ref),
        "generation": generation,
        "transitioned_at": "2026-10-08T18:15:00Z",
        "transition_receipt_ref": ref("qc2.governance_owner.PromotionReceipt.v1", 21),
        "pointer_hash": f"{generation:064x}",
    }
    validate_contract("ChampionPointer", pointer)
    bindings = PredictionBindings(
        epoch_ref=epoch_ref,
        snapshot_ref=ref("qc2.identity_market.MarketSnapshot.v1", 2, HASH_A),
        census_ref=ref("qc2.identity_market.CandidateCensus.v1", 3, HASH_A),
        universe_ref=ref("qc2.identity_market.UniverseManifest.v1", 4, HASH_A),
        feature_registry_ref=ref("qc2.scientific_definitions.FeatureRegistry.v1", 5, HASH_A),
        protocol_registry_ref=ref(
            "qc2.scientific_definitions.RunnerProtocolRegistry.v1", 6, HASH_A
        ),
        label_registry_ref=ref("qc2.scientific_definitions.LabelRegistry.v1", 7, HASH_A),
        score_manifest_ref=ref("qc2.scientific_definitions.ScoreManifest.v1", 8, HASH_A),
        operating_champion_pointer=pointer,
        operating_model_ref=operating_model_ref,
        reference_model_ref=ref("qc2.models_prediction.ModelManifest.v1", 10, HASH_C),
        shadow_prediction_set_refs=(
            ref("qc2.models_prediction.ShadowPredictionSet.v1", 11, HASH_A),
        ),
        baseline_manifest_refs=(
            ref("qc2.scientific_definitions.BaselineManifest.v1", 12, HASH_B),
        ),
        calendar_ref=ref("qc2.time_operation.CalendarManifest.v1", 13, HASH_C),
        memory_index_refs=(
            ref("qc2.outcomes_research.MemoryIndexManifest.v1", 14, HASH_C),
        ),
        scientific_code_ref=ref("qc2.integrity_build.ArtifactManifest.v1", 15, HASH_C),
        eligible_instrument_refs=(
            ref("qc2.identity_market.Instrument.v1", 101, HASH_A),
            ref("qc2.identity_market.Instrument.v1", 102, HASH_B),
            ref("qc2.identity_market.Instrument.v1", 103, HASH_C),
        ),
        session_id=SESSION,
        regime="trending",
        decision_deadline=DECISION_DEADLINE,
        seal_deadline=SEAL_DEADLINE,
        next_regular_session_open_at=NEXT_OPEN,
        evidence_class=evidence_class,
        environment_namespace=environment_namespace,
        retry_policy=RetryPolicy(2, ("temporary_io",)),
    )
    bindings.normalized()
    return bindings


class StaticInputPort:
    def __init__(self, bindings: PredictionBindings) -> None:
        self.bindings = bindings
        self.calls = 0

    def capture_bindings(
        self, epoch_ref: dict[str, Any], session_id: str
    ) -> PredictionBindings:
        assert epoch_ref["target_id"] == id_for(1)
        assert session_id == SESSION
        self.calls += 1
        return copy.deepcopy(self.bindings)


def make_features() -> tuple[FeatureRow, ...]:
    rows = []
    for number, price in ((101, "10.25"), (102, "20.50"), (103, "30.75")):
        rows.append(
            FeatureRow(
                instrument_ref=ref("qc2.identity_market.Instrument.v1", number, HASH_A),
                reference_kind="PREDICTION_SESSION_DAILY_CLOSE",
                reference_price=price,
                horizon_label_refs=(
                    ref("qc2.scientific_definitions.LabelDefinition.v1", 30, HASH_B),
                ),
                head_output_refs=(
                    ref("qc2.models_prediction.ModelHeadOutput.v1", number + 100, HASH_C),
                ),
                feature_snapshot_ref=ref(
                    "qc2.scientific_definitions.FeatureSnapshot.v1", number + 200, HASH_A
                ),
                protocol_result_refs=(
                    ref(
                        "qc2.scientific_definitions.RunnerProtocolResult.v1",
                        number + 300,
                        HASH_B,
                    ),
                ),
                learned_memory_refs=(),
            )
        )
    return tuple(rows)


def start_run(
    *,
    bindings: PredictionBindings | None = None,
    authority: PredictionAuthority | None = None,
    source: StaticInputPort | None = None,
) -> tuple[PredictionAuthority, StaticInputPort, str, str]:
    bindings = bindings or make_bindings()
    authority = authority or PredictionAuthority(id_factory=IdFactory())
    source = source or StaticInputPort(bindings)
    scheduled = authority.schedule_sessions(
        epoch_ref=bindings.epoch_ref,
        session_ids=(SESSION,),
        deadlines={SESSION: "2026-10-08T19:30:00Z"},
        created_at=SCHEDULED_AT,
        evidence_class=bindings.evidence_class,
        environment_namespace=bindings.environment_namespace,
    )[0]
    run = authority.create_run(
        scheduled_attempt_id=scheduled["id"],
        source=source,
        created_at=CREATED_AT,
    )
    return authority, source, scheduled["id"], run["contract"]["id"]


def rank_run(
    authority: PredictionAuthority,
    run_id: str,
    *,
    retry: bool = False,
) -> tuple[dict[str, Any], ...]:
    instrument_ids = [id_for(number) for number in (101, 102, 103)]
    authority.record_feature_rows(run_id=run_id, feature_rows=make_features())
    authority.record_scores(
        run_id=run_id,
        score_results={
            instrument_ids[0]: ScoreResult("0.850000"),
            instrument_ids[1]: ScoreResult("0.850000"),
            instrument_ids[2]: ScoreResult(
                None,
                "temporary_io" if retry else "missing_head",
            ),
        },
        completed_at="2026-10-08T19:40:00Z",
    )
    if retry:
        authority.begin_repair_attempt(
            run_id=run_id,
            instrument_ids=(instrument_ids[2],),
            started_at="2026-10-08T19:41:00Z",
        )
        authority.complete_repair_attempt(
            run_id=run_id,
            score_results={instrument_ids[2]: ScoreResult("0.250000")},
            completed_at="2026-10-08T19:42:00Z",
        )
    return authority.rank(run_id=run_id, created_at="2026-10-08T19:43:00Z")


def evidence_ref() -> dict[str, str]:
    return ref("qc2.integrity_build.EvidenceEvent.v1", 500, HASH_C)


def seal_ready_run(
    *,
    sealed_at: str,
    evidence_class: str = "SYNTHETIC_FIXTURE",
    environment_namespace: str = "test",
) -> tuple[PredictionAuthority, str, str, Any]:
    bindings = make_bindings(
        evidence_class=evidence_class,
        environment_namespace=environment_namespace,
    )
    authority, _, scheduled_id, run_id = start_run(bindings=bindings)
    rank_run(authority, run_id, retry=True)
    result = authority.seal(
        run_id=run_id,
        sealed_at=sealed_at,
        evidence_refs=(evidence_ref(),),
    )
    return authority, scheduled_id, run_id, result


def test_concurrent_run_creation_and_champion_rotation_keep_one_generation() -> None:
    original = make_bindings(generation=1)
    rotated = make_bindings(generation=2)
    source = StaticInputPort(original)
    captured = threading.Event()
    rotate_attempted = threading.Event()
    source_lock = threading.Lock()
    live_bindings = [copy.deepcopy(original)]
    source.calls = 0

    def atomic_capture(epoch_ref: dict[str, Any], session_id: str) -> PredictionBindings:
        assert epoch_ref["target_id"] == id_for(1)
        assert session_id == SESSION
        with source_lock:
            source.calls += 1
            result = copy.deepcopy(live_bindings[0])
            captured.set()
            assert rotate_attempted.wait(timeout=2)
            return result

    source.capture_bindings = atomic_capture  # type: ignore[method-assign]
    authority, _, scheduled_id, _ = start_run_without_create(source, original)

    def rotate_champion() -> None:
        assert captured.wait(timeout=2)
        rotate_attempted.set()
        with source_lock:
            live_bindings[0] = copy.deepcopy(rotated)

    def create() -> dict[str, Any] | Exception:
        try:
            return authority.create_run(
                scheduled_attempt_id=scheduled_id,
                source=source,
                created_at=CREATED_AT,
            )
        except PredictionAuthorityError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(create)
        second = pool.submit(create)
        update = pool.submit(rotate_champion)
        results = [first.result(timeout=5), second.result(timeout=5)]
        update.result(timeout=5)

    created_runs = [result for result in results if isinstance(result, dict)]
    failures = [result for result in results if isinstance(result, PredictionAuthorityError)]
    assert len(created_runs) == 1
    assert len(failures) == 1
    assert source.calls == 1
    snapshot = created_runs[0]["binding_snapshot"]
    assert snapshot["operating_champion_pointer"]["generation"] == 1
    assert (
        snapshot["operating_champion_pointer"]["model_ref"]
        == snapshot["operating_model_ref"]
    )


def start_run_without_create(
    source: StaticInputPort, bindings: PredictionBindings
) -> tuple[PredictionAuthority, StaticInputPort, str, None]:
    authority = PredictionAuthority(id_factory=IdFactory())
    scheduled = authority.schedule_sessions(
        epoch_ref=bindings.epoch_ref,
        session_ids=(SESSION,),
        deadlines={SESSION: "2026-10-08T19:30:00Z"},
        created_at=SCHEDULED_AT,
        evidence_class=bindings.evidence_class,
        environment_namespace=bindings.environment_namespace,
    )[0]
    return authority, source, scheduled["id"], None


def test_complete_inventory_tie_order_and_scientific_payload_hashes() -> None:
    authority, _, _, run_id = start_run()
    rows = rank_run(authority, run_id, retry=False)

    assert len(rows) == 3
    assert [row["instrument_ref"]["target_id"] for row in rows] == [
        id_for(101),
        id_for(102),
        id_for(103),
    ]
    assert [row["rank"] for row in rows] == [1, 2, None]
    assert [row["disposition"] for row in rows] == [
        "SCORED",
        "SCORED",
        "UNSCORABLE",
    ]
    assert rows[2]["unscorable_reason"] == "missing_head"

    # Ranking, rather than fixture insertion order, decides tied rows by stable ID.
    shuffled_authority, _, _, shuffled_id = start_run()
    shuffled_authority.record_feature_rows(
        run_id=shuffled_id,
        feature_rows=tuple(reversed(make_features())),
    )
    shuffled_authority.record_scores(
        run_id=shuffled_id,
        score_results={
            id_for(103): ScoreResult("0.850000"),
            id_for(101): ScoreResult("0.850000"),
            id_for(102): ScoreResult("0.850000"),
        },
        completed_at="2026-10-08T19:40:00Z",
    )
    ties = shuffled_authority.rank(
        run_id=shuffled_id,
        created_at="2026-10-08T19:43:00Z",
    )
    assert [row["instrument_ref"]["target_id"] for row in ties] == [
        id_for(101),
        id_for(102),
        id_for(103),
    ]


def test_retry_repairs_only_retryable_unscorable_rows_within_budget() -> None:
    authority, _, _, run_id = start_run()
    instrument_ids = [id_for(number) for number in (101, 102, 103)]
    authority.record_feature_rows(run_id=run_id, feature_rows=make_features())
    authority.record_scores(
        run_id=run_id,
        score_results={
            instrument_ids[0]: ScoreResult("0.850000"),
            instrument_ids[1]: ScoreResult("0.800000"),
            instrument_ids[2]: ScoreResult(None, "temporary_io"),
        },
        completed_at="2026-10-08T19:40:00Z",
    )
    with pytest.raises(PredictionAuthorityError, match="exactly the unresolved"):
        authority.begin_repair_attempt(
            run_id=run_id,
            instrument_ids=(instrument_ids[0],),
            started_at="2026-10-08T19:41:00Z",
        )
    authority.begin_repair_attempt(
        run_id=run_id,
        instrument_ids=(instrument_ids[2],),
        started_at="2026-10-08T19:41:00Z",
    )
    with pytest.raises(PredictionAuthorityError, match="coverage differs"):
        authority.complete_repair_attempt(
            run_id=run_id,
            score_results={instrument_ids[0]: ScoreResult("0.999999")},
            completed_at="2026-10-08T19:42:00Z",
        )
    authority.complete_repair_attempt(
        run_id=run_id,
        score_results={instrument_ids[2]: ScoreResult("0.250000")},
        completed_at="2026-10-08T19:42:00Z",
    )
    with pytest.raises(PredictionAuthorityError, match="budget is exhausted"):
        authority.begin_repair_attempt(
            run_id=run_id,
            instrument_ids=(instrument_ids[2],),
            started_at="2026-10-08T19:43:00Z",
        )
    run = authority.get_run(run_id)
    assert [item["attempt_event"] for item in run["attempts"]] == [
        "COMPLETED",
        "STARTED",
        "COMPLETED",
    ]


def test_seal_is_immutable_and_late_completion_is_diagnostic() -> None:
    authority, _, run_id, result = seal_ready_run(sealed_at="2026-10-08T20:59:00Z")
    assert result.seal["role"] == "OPERATING"
    assert result.on_time is True
    assert len(result.rows) == 3
    verify_content_hash("PredictionSeal", dict(result.seal))

    result.seal["role"] = "DIAGNOSTIC"  # Returned values cannot mutate the stored seal.
    stored = authority._runs[run_id].seal
    assert stored is not None and stored["role"] == "OPERATING"
    with pytest.raises(PredictionAuthorityError, match="run must be RANKED"):
        authority.seal(
            run_id=run_id,
            sealed_at="2026-10-08T21:00:00Z",
            evidence_refs=(evidence_ref(),),
        )

    late_authority, scheduled_id, late_run_id, late_result = seal_ready_run(
        sealed_at="2026-10-08T21:01:00Z"
    )
    assert late_result.seal["role"] == "DIAGNOSTIC"
    assert late_result.on_time is False
    assert late_result.production_activation_eligible is False
    assert late_authority.get_scheduled_attempt(scheduled_id)["attempt_state"] == "NONQUALIFYING"
    assert late_authority.get_run(late_run_id)["sealed"] is True


def test_fixture_evidence_cannot_create_a_production_run() -> None:
    with pytest.raises(PredictionAuthorityError, match="production runs require"):
        make_bindings(
            evidence_class="SYNTHETIC_FIXTURE",
            environment_namespace="production",
        )


class FakeAnchorPort:
    def __init__(self, receipt: dict[str, Any]) -> None:
        self.receipt = receipt

    async def submit_checkpoint(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        assert checkpoint["id"] == self.receipt["checkpoint_ref"]["target_id"]
        return copy.deepcopy(self.receipt)

    async def verify_receipt(
        self, checkpoint: dict[str, Any], receipt: dict[str, Any]
    ) -> bool:
        return (
            checkpoint["id"] == receipt["checkpoint_ref"]["target_id"]
            and receipt["proof_level"] == "INDEPENDENT_PREOUTCOME_ANCHORED"
        )


def make_checkpoint_record(seal: dict[str, Any]) -> CheckpointRecord:
    refs = [
        {
            "target_schema_name": seal["schema_name"],
            "target_id": seal["id"],
            "content_hash": seal["content_hash"],
        }
    ]
    created_at = (
        datetime.fromisoformat(seal["sealed_at"].replace("Z", "+00:00")) + timedelta(minutes=1)
    ).isoformat().replace("+00:00", "Z")
    common = {
        "schema_name": "qc2.integrity_build.Checkpoint.v1",
        "schema_version": "1.0",
        "id": id_for(600),
        "created_at": created_at,
        "owning_authority": "evidence",
        "evidence_class": seal["evidence_class"],
        "environment_namespace": seal["environment_namespace"],
        "source_refs": refs,
        "content_hash": "0" * 64,
        "stream_id": "prediction-authority-fixture",
        "head_sequence": 1,
        "head_hash": HASH_A,
        "event_count": 1,
        "artifact_root_hash": domain_separated_sha256(
            CHECKPOINT_ARTIFACT_ROOT_DOMAIN,
            canonical_json_bytes(refs),
        ),
        "checkpoint_hash": "0" * 64,
    }
    hash_basis = {
        key: value
        for key, value in common.items()
        if key not in {"content_hash", "checkpoint_hash"}
    }
    common["checkpoint_hash"] = domain_separated_sha256(
        CHECKPOINT_HASH_DOMAIN,
        canonical_json_bytes(hash_basis),
    )
    common["content_hash"] = canonical_content_hash("Checkpoint", common)
    validate_contract("Checkpoint", common)
    verify_content_hash("Checkpoint", common)
    return CheckpointRecord(common, refs, None)


def make_receipt(checkpoint: dict[str, Any], *, accepted_at: str) -> dict[str, Any]:
    receipt = {
        "schema_name": "qc2.integrity_build.AnchorReceipt.v1",
        "schema_version": "1.0",
        "id": id_for(601),
        "created_at": accepted_at,
        "owning_authority": "evidence",
        "evidence_class": checkpoint["evidence_class"],
        "environment_namespace": checkpoint["environment_namespace"],
        "source_refs": [],
        "checkpoint_ref": {
            "target_schema_name": checkpoint["schema_name"],
            "target_id": checkpoint["id"],
            "content_hash": checkpoint["content_hash"],
        },
        "anchor_provider": "external_test_anchor",
        "external_receipt_id": "receipt-prediction-001",
        "accepted_at": accepted_at,
        "observed_at": accepted_at,
        "verification_key_id": "test-signing-key",
        "signature": HASH_C,
        "proof_level": "INDEPENDENT_PREOUTCOME_ANCHORED",
    }
    validate_contract("AnchorReceipt", receipt)
    return receipt


def test_anchor_port_verifies_checkpoint_and_rejects_late_qualification() -> None:
    _, _, _, result = seal_ready_run(
        sealed_at="2026-10-08T20:59:00Z",
        evidence_class="FORWARD_SEALED",
        environment_namespace="production",
    )
    checkpoint = make_checkpoint_record(dict(result.seal))
    receipt = make_receipt(
        dict(checkpoint.checkpoint_contract),
        accepted_at="2026-10-08T21:01:00Z",
    )
    anchored = asyncio.run(
        anchor_prediction_seal(
            seal=dict(result.seal),
            checkpoint=checkpoint,
            anchor_port=FakeAnchorPort(receipt),
            next_outcome_session_start=NEXT_OPEN,
        )
    )
    assert anchored.signature_verified is True
    assert anchored.independent_preoutcome is True
    assert anchored.on_time is True
    assert anchored.qualification_eligible is True

    _, _, _, late_result = seal_ready_run(
        sealed_at="2026-10-08T21:01:00Z",
        evidence_class="FORWARD_SEALED",
        environment_namespace="production",
    )
    late_checkpoint = make_checkpoint_record(dict(late_result.seal))
    late_receipt = make_receipt(
        dict(late_checkpoint.checkpoint_contract),
        accepted_at="2026-10-08T21:03:00Z",
    )
    late_anchor = asyncio.run(
        anchor_prediction_seal(
            seal=dict(late_result.seal),
            checkpoint=late_checkpoint,
            anchor_port=FakeAnchorPort(late_receipt),
            next_outcome_session_start=NEXT_OPEN,
        )
    )
    assert late_anchor.signature_verified is True
    assert late_anchor.on_time is True
    assert late_anchor.operating_seal is False
    assert late_anchor.qualification_eligible is False


def test_anchor_rejects_checkpoint_without_the_exact_prediction_seal() -> None:
    _, _, _, result = seal_ready_run(sealed_at="2026-10-08T20:59:00Z")
    checkpoint = make_checkpoint_record(dict(result.seal))
    wrong_seal = copy.deepcopy(dict(result.seal))
    wrong_seal["id"] = id_for(999)
    with pytest.raises(PredictionAnchorError, match="exact seal"):
        asyncio.run(
            anchor_prediction_seal(
                seal=wrong_seal,
                checkpoint=checkpoint,
                anchor_port=FakeAnchorPort({}),
                next_outcome_session_start=NEXT_OPEN,
            )
        )
