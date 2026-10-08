from __future__ import annotations

import copy
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
for package in ("contracts", "prediction_authority"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))
sys.path.insert(0, str(ROOT / "tests" / "prediction_authority"))

from qc2_contracts.runtime import (  # noqa: E402
    canonical_content_hash,
    canonical_json_bytes,
    domain_separated_sha256,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)
from qc2_prediction_authority.models import (  # noqa: E402
    PredictionAuthorityError,
    ScoreResult,
)
from qc2_prediction_authority.shadow import (  # noqa: E402
    ShadowEngine,
    ShadowSessionInput,
)
from test_prediction_authority import (  # noqa: E402
    IdFactory,
    PredictionAuthority,
    evidence_ref,
    make_bindings,
    rank_run,
    start_run,
)

MODEL_SCHEMA = "qc2.models_prediction.ModelManifest.v1"
SHADOW_SCHEMA = "qc2.models_prediction.ShadowPredictionSet.v1"
LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"
RUN_SCHEMA = "qc2.models_prediction.PredictionRun.v1"
SNAPSHOT_SCHEMA = "qc2.identity_market.MarketSnapshot.v1"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
REGISTERED_AT = "2026-10-06T21:00:00Z"
ELIGIBLE_AT = "2026-10-07T20:00:00Z"
SESSION_IDS = ("2026-10-08", "2026-10-09")
INSTRUMENTS = (
    {
        "target_schema_name": INSTRUMENT_SCHEMA,
        "target_id": "018f0000-0000-7000-8000-000000000065",
        "content_hash": "a" * 64,
    },
    {
        "target_schema_name": INSTRUMENT_SCHEMA,
        "target_id": "018f0000-0000-7000-8000-000000000066",
        "content_hash": "b" * 64,
    },
    {
        "target_schema_name": INSTRUMENT_SCHEMA,
        "target_id": "018f0000-0000-7000-8000-000000000067",
        "content_hash": "c" * 64,
    },
)


def _valid_contract(name: str) -> dict[str, Any]:
    rows = json.loads(
        (ROOT / "packages/contracts/fixtures/v1/valid.json").read_text(encoding="utf-8")
    )
    return copy.deepcopy(next(row["payload"] for row in rows if row["contract"] == name))


def _seal(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash(name, payload)
    validate_contract(name, payload)
    verify_content_hash(name, payload)
    return payload


def _model(*, training_cutoff: str = "2026-10-05T20:00:00Z") -> dict[str, Any]:
    model = _valid_contract("ModelManifest")
    model.update(
        {
            "id": new_uuidv7(),
            "created_at": "2026-10-05T20:00:00Z",
            "owning_authority": "model_registry",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "training_cutoff": training_cutoff,
            "lifecycle_state": "CHALLENGER",
        }
    )
    return _seal("ModelManifest", model)


def _reference(schema: str, *, digest: str = "c" * 64) -> dict[str, str]:
    return {
        "target_schema_name": schema,
        "target_id": new_uuidv7(),
        "content_hash": digest,
    }


def _comparators() -> tuple[dict[str, str], ...]:
    pointer = _valid_contract("ChampionPointer")
    baseline = _valid_contract("BaselineManifest")
    return (
        {
            "target_schema_name": "qc2.governance_owner.ChampionPointer.v1",
            "target_id": new_uuidv7(),
            "content_hash": pointer["pointer_hash"],
        },
        {
            "target_schema_name": "qc2.scientific_definitions.BaselineManifest.v1",
            "target_id": new_uuidv7(),
            "content_hash": baseline["content_hash"],
        },
    )


class LifecycleRecorder:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def transition_to_shadow(
        self,
        model_ref: Mapping[str, Any],
        shadow_set: Mapping[str, Any],
        transitioned_at: str,
    ) -> Any:
        event = {
            "model_ref": dict(model_ref),
            "evidence_ref": {
                "target_schema_name": shadow_set["schema_name"],
                "target_id": shadow_set["id"],
                "content_hash": shadow_set["content_hash"],
            },
            "prior_state": "CHALLENGER",
            "next_state": "SHADOW",
            "transitioned_at": transitioned_at,
        }
        self.events.append(event)
        return LifecycleEventDocument(**event)


@dataclass
class LifecycleEventDocument:
    model_ref: dict[str, Any]
    evidence_ref: dict[str, Any]
    prior_state: str
    next_state: str
    transitioned_at: str


def _register(
    engine: ShadowEngine,
    *,
    model: Mapping[str, Any] | None = None,
    registered_at: str = REGISTERED_AT,
    eligible_at: str = ELIGIBLE_AT,
) -> dict[str, Any]:
    candidate = copy.deepcopy(dict(model or _model()))
    return engine.register_shadow(
        model_manifest=candidate,
        registered_at=registered_at,
        eligible_at=eligible_at,
        target_label_refs=candidate["target_label_refs"],
        comparison_window_sessions=2,
        comparator_refs=_comparators(),
    )


def _engine() -> tuple[ShadowEngine, LifecycleRecorder]:
    lifecycle = LifecycleRecorder()
    return ShadowEngine(lifecycle), lifecycle


def _schedule(
    engine: ShadowEngine,
    shadow_sets: tuple[Mapping[str, Any], ...],
    *,
    sessions: tuple[str, ...] = SESSION_IDS,
) -> None:
    deadlines = {
        session_id: f"{session_id}T20:00:00Z"
        for session_id in sessions
    }
    for shadow_set in shadow_sets:
        engine.schedule_comparison_window(
            shadow_set["id"],
            session_start_deadlines=deadlines,
        )


def _bindings_for(shadow_sets: tuple[Mapping[str, Any], ...]) -> Any:
    original = make_bindings()
    return copy.replace(
        original,
        shadow_prediction_set_refs=tuple(
            {
                "target_schema_name": SHADOW_SCHEMA,
                "target_id": shadow_set["id"],
                "content_hash": shadow_set["content_hash"],
            }
            for shadow_set in shadow_sets
        ),
    )


def _session_input(
    operating_run: Mapping[str, Any],
    *,
    session_id: str = "2026-10-08",
    started_at: str = "2026-10-08T19:50:00Z",
) -> ShadowSessionInput:
    binding = operating_run["binding_snapshot"]
    return ShadowSessionInput(
        session_id=session_id,
        started_at=started_at,
        operating_run=operating_run,
        snapshot_ref=binding["snapshot_ref"],
        eligible_instrument_refs=binding["eligible_instrument_refs"],
        model_inputs={
            "session_id": session_id,
            "snapshot_ref": binding["snapshot_ref"],
            "eligible_instrument_refs": binding["eligible_instrument_refs"],
            "feature_inputs": {
                "feature_batch": [
                    {"instrument_ref": item, "features": ["same-session", "frozen-input"]}
                    for item in binding["eligible_instrument_refs"]
                ],
                "protocol_registry_ref": binding["protocol_registry_ref"],
            },
        },
    )


def _predictor(score: str = "0.750000"):
    return lambda _model_ref, inputs: {
        item["instrument_ref"]["target_id"]: ScoreResult(score)
        for item in inputs["feature_inputs"]["feature_batch"]
    }


def _start_backdated_run(
    bindings: Any,
    *,
    created_at: str,
    session_id: str,
) -> tuple[Any, str]:
    deadline = f"{session_id}T19:30:00Z"
    bindings = copy.replace(
        bindings,
        session_id=session_id,
        decision_deadline=f"{session_id}T21:00:00Z",
        seal_deadline=f"{session_id}T21:05:00Z",
        next_regular_session_open_at="2026-10-12T13:30:00Z",
    )

    class InputPort:
        def capture_bindings(self, epoch_ref: dict[str, Any], requested_session_id: str):
            assert requested_session_id == session_id
            assert epoch_ref == bindings.epoch_ref
            return copy.deepcopy(bindings)

    authority = PredictionAuthority(id_factory=IdFactory())
    scheduled = authority.schedule_sessions(
        epoch_ref=bindings.epoch_ref,
        session_ids=(session_id,),
        deadlines={session_id: deadline},
        created_at="2026-10-08T18:00:00Z",
        evidence_class=bindings.evidence_class,
        environment_namespace=bindings.environment_namespace,
    )[0]
    run = authority.create_run(
        scheduled_attempt_id=scheduled["id"],
        source=InputPort(),
        created_at=created_at,
    )
    return authority, run["contract"]["id"]


def test_preregistration_pins_model_labels_comparators_and_immutable_window() -> None:
    engine, lifecycle = _engine()
    model = _model()
    registration = _register(engine, model=model)
    original = copy.deepcopy(registration)
    registration["eligible_at"] = "2026-10-01T00:00:00Z"

    plan = engine.schedule_comparison_window(
        original["id"],
        session_start_deadlines={
            "2026-10-08": "2026-10-08T20:00:00Z",
            "2026-10-09": "2026-10-09T20:00:00Z",
        },
    )
    plan["sessions"].clear()

    projection = engine.report_projection()
    stored = projection["trials"][0]["registration"]
    assert stored == original
    assert stored["model_ref"]["content_hash"] == model["content_hash"]
    assert stored["registration_hash"] != "0" * 64
    assert projection["trials"][0]["coverage"]["window_sessions"] == 2
    assert lifecycle.events[0]["next_state"] == "SHADOW"
    assert lifecycle.events[0]["evidence_ref"]["content_hash"] == stored["content_hash"]
    assert all(event["next_state"] != "CHAMPION" for event in lifecycle.events)

    with pytest.raises(PredictionAuthorityError, match="immutable"):
        engine.schedule_comparison_window(
            original["id"],
            session_start_deadlines={
                "2026-10-08": "2026-10-08T20:00:00Z",
                "2026-10-10": "2026-10-10T20:00:00Z",
            },
        )


def test_future_training_and_late_registration_cannot_schedule_retroactive_evidence() -> None:
    engine, _ = _engine()
    future_trained = _model(training_cutoff="2026-10-10T20:00:00Z")
    future_registration = _register(
        engine,
        model=future_trained,
        registered_at="2026-10-11T20:30:00Z",
        eligible_at="2026-10-12T20:00:00Z",
    )
    with pytest.raises(PredictionAuthorityError, match="sessions after training and registration"):
        engine.schedule_comparison_window(
            future_registration["id"],
            session_start_deadlines={
                "2026-10-10": "2026-10-10T22:00:00Z",
                "2026-10-11": "2026-10-11T22:00:00Z",
            },
        )

    late_registration = _register(
        engine,
        registered_at="2026-10-10T21:00:00Z",
        eligible_at="2026-10-11T20:00:00Z",
    )
    with pytest.raises(PredictionAuthorityError, match="sessions after training and registration"):
        engine.schedule_comparison_window(
            late_registration["id"],
            session_start_deadlines={
                "2026-10-10": "2026-10-10T22:00:00Z",
                "2026-10-11": "2026-10-11T22:00:00Z",
            },
        )

    with pytest.raises(PredictionAuthorityError, match="eligibility must follow"):
        _register(
            engine,
            model=_model(training_cutoff="2026-10-10T20:00:00Z"),
            registered_at="2026-10-11T20:30:00Z",
            eligible_at="2026-10-10T21:00:00Z",
        )


@pytest.mark.parametrize(
    ("registered_at", "eligible_at", "run_created_at", "message"),
    (
        (
            "2026-10-08T18:45:00Z",
            "2026-10-08T20:00:00Z",
            "2026-10-08T18:30:00Z",
            "Shadow registration occurred after the operating run was bound",
        ),
        (
            "2026-10-08T18:10:00Z",
            "2026-10-08T18:45:00Z",
            "2026-10-08T18:30:00Z",
            "operating run was bound before the Shadow became eligible",
        ),
    ),
)
def test_run_bound_before_registration_or_eligibility_cannot_score_shadow(
    registered_at: str,
    eligible_at: str,
    run_created_at: str,
    message: str,
) -> None:
    engine, _ = _engine()
    shadow_set = _register(
        engine,
        registered_at=registered_at,
        eligible_at=eligible_at,
    )
    _schedule(engine, (shadow_set,), sessions=("2026-10-09", "2026-10-12"))
    bindings = _bindings_for((shadow_set,))
    authority, run_id = _start_backdated_run(
        bindings,
        created_at=run_created_at,
        session_id="2026-10-09",
    )

    with pytest.raises(PredictionAuthorityError, match=message):
        engine.score_session(
            _session_input(
                authority.get_run(run_id),
                session_id="2026-10-09",
                started_at="2026-10-09T19:50:00Z",
            ),
            predictors={shadow_set["id"]: _predictor()},
        )


def test_shadow_attempt_cannot_extend_or_outlive_operating_run_deadline() -> None:
    for deadlines, started_at, expected_error in (
        (
            {
                "2026-10-08": "2026-10-08T22:00:00Z",
                "2026-10-09": "2026-10-09T20:00:00Z",
            },
            "2026-10-08T19:50:00Z",
            "window deadline exceeds",
        ),
        (
            {
                "2026-10-08": "2026-10-08T20:00:00Z",
                "2026-10-09": "2026-10-09T20:00:00Z",
            },
            "2026-10-08T21:01:00Z",
            "started after the operating PredictionRun decision deadline",
        ),
    ):
        engine, _ = _engine()
        shadow_set = _register(engine)
        engine.schedule_comparison_window(
            shadow_set["id"],
            session_start_deadlines=deadlines,
        )
        authority, _, _, run_id = start_run(bindings=_bindings_for((shadow_set,)))
        with pytest.raises(PredictionAuthorityError, match=expected_error):
            engine.score_session(
                _session_input(authority.get_run(run_id), started_at=started_at),
                predictors={shadow_set["id"]: _predictor()},
            )
        assert engine.coverage_ledger(shadow_set["id"])["pending_sessions"] == 2


def test_every_registered_shadow_uses_the_same_pinned_inputs_and_has_its_own_seal() -> None:
    engine, lifecycle = _engine()
    shadow_sets = (_register(engine), _register(engine))
    _schedule(engine, shadow_sets)
    bindings = _bindings_for(shadow_sets)
    authority, _, _, run_id = start_run(bindings=bindings)
    operating_run = authority.get_run(run_id)
    values_seen: list[Any] = []

    def mutating_predictor(_model_ref, inputs):
        batch = inputs["feature_inputs"]["feature_batch"]
        values_seen.append(copy.deepcopy(batch))
        batch.clear()
        return {
            instrument["target_id"]: ScoreResult("0.500000")
            for instrument in INSTRUMENTS
        }

    def observing_predictor(_model_ref, inputs):
        values_seen.append(copy.deepcopy(inputs["feature_inputs"]["feature_batch"]))
        return {
            instrument["target_id"]: ScoreResult("0.750000")
            for instrument in INSTRUMENTS
        }

    with pytest.raises(PredictionAuthorityError, match="must be scored"):
        engine.score_session(
            _session_input(operating_run),
            predictors={shadow_sets[0]["id"]: mutating_predictor},
        )
    assert all(
        engine.coverage_ledger(shadow_set["id"])["pending_sessions"] == 2
        for shadow_set in shadow_sets
    )

    malformed = copy.deepcopy(_session_input(operating_run).model_inputs)
    malformed["snapshot_ref"] = _reference(SNAPSHOT_SCHEMA)
    with pytest.raises(PredictionAuthorityError, match="model_inputs use another market snapshot"):
        engine.score_session(
            copy.replace(
                _session_input(operating_run),
                model_inputs=malformed,
            ),
            predictors={
                shadow_sets[0]["id"]: mutating_predictor,
                shadow_sets[1]["id"]: observing_predictor,
            },
        )

    attempts = engine.score_session(
        _session_input(operating_run),
        predictors={
            shadow_sets[0]["id"]: mutating_predictor,
            shadow_sets[1]["id"]: observing_predictor,
        },
    )
    assert len(attempts) == 2
    assert len({item["attempt"]["input_hash"] for item in attempts}) == 1
    assert values_seen[0] == values_seen[1]
    assert all(item["status"] == "SCORED" for item in attempts)
    assert all(item["seal"]["role"] == "SHADOW" for item in attempts)
    assert len({item["seal"]["content_hash"] for item in attempts}) == 2
    assert all(len(item["prediction_rows"]) == len(INSTRUMENTS) for item in attempts)
    assert all("rank" not in row for item in attempts for row in item["prediction_rows"])
    assert all(
        row["model_ref"]["target_id"] == item["attempt"]["model_ref"]["target_id"]
        for item in attempts
        for row in item["prediction_rows"]
    )
    assert all(event["next_state"] == "SHADOW" for event in lifecycle.events)

    mobile = engine.mobile_projection()
    report = engine.report_projection()
    assert mobile["execution_capability"] == "NONE"
    assert len(mobile["items"]) == 2
    assert all("prediction_rows" not in item and "score" not in item for item in mobile["items"])
    assert report["official_rank_capability"] == "NONE"
    assert report["strategy_mutation_capability"] == "NONE"
    assert report["execution_capability"] == "NONE"
    assert len(report["trials"]) == 2
    assert all(item["lifecycle_state"] == "SHADOW" for item in report["trials"])
    assert all(
        row["content_hash"]
        for item in report["trials"]
        for attempt in item["attempt_evidence"]
        for row in attempt["prediction_rows"]
    )


def test_shadow_failures_and_drops_remain_accounted_without_changing_official_ranks() -> None:
    engine, lifecycle = _engine()
    shadow_sets = (_register(engine), _register(engine))
    _schedule(engine, shadow_sets)
    bindings = _bindings_for(shadow_sets)
    authority, _, _, run_id = start_run(bindings=bindings)
    official_rows = rank_run(authority, run_id, retry=True)
    official_before = authority.get_run(run_id)
    operating_run = authority.get_run(run_id)

    def fail(_model_ref, _inputs):
        raise RuntimeError("candidate inference failed")

    attempts = engine.score_session(
        _session_input(operating_run),
        predictors={
            shadow_sets[0]["id"]: fail,
            shadow_sets[1]["id"]: _predictor(),
        },
    )
    assert sorted(item["status"] for item in attempts) == ["FAILED", "SCORED"], [
        (item["status"], item["attempt"]["failure_code"])
        for item in attempts
    ]
    assert all(item["seal"]["role"] == "SHADOW" for item in attempts)
    assert all(item["seal"]["content_hash"] for item in attempts)
    drop_event = engine.drop_shadow(
        shadow_sets[1]["id"],
        dropped_at="2026-10-08T20:05:00Z",
        reason_code="owner_withdrew_candidate",
    )
    missed_event = engine.mark_missed(
        shadow_sets[0]["id"],
        "2026-10-09",
        observed_at="2026-10-09T20:01:00Z",
    )

    failed_ledger = engine.coverage_ledger(shadow_sets[0]["id"])
    dropped_ledger = engine.coverage_ledger(shadow_sets[1]["id"])
    assert failed_ledger["trial_state"] == "COMPLETE"
    assert failed_ledger["failed_sessions"] == 1
    assert failed_ledger["missed_sessions"] == 1
    assert failed_ledger["accounted_sessions"] == 2
    assert failed_ledger["coverage_fraction"] == 0
    assert dropped_ledger["trial_state"] == "DROPPED"
    assert dropped_ledger["successful_sessions"] == 1
    assert dropped_ledger["dropped_sessions"] == 1
    assert dropped_ledger["accounted_sessions"] == 2
    assert dropped_ledger["sessions"][1]["ledger_event"]["state"] == "DROPPED"
    assert missed_event["id"] == failed_ledger["sessions"][1]["ledger_event"]["id"]
    assert missed_event["content_hash"] == domain_separated_sha256(
        "qc2.shadow-ledger-event.v1",
        canonical_json_bytes(
            {
                key: value
                for key, value in missed_event.items()
                if key not in {"format", "content_hash"}
            }
        ),
    )
    assert all(
        item["attempt"]["failure_code"] == "predictor_runtimeerror"
        for item in engine.attempt_evidence(shadow_sets[0]["id"])
        if item["attempt"] is not None
    )
    report = engine.report_projection()
    assert len(report["trials"]) == 2
    dropped_report = next(
        item for item in report["trials"]
        if item["registration"]["id"] == shadow_sets[1]["id"]
    )
    assert dropped_report["dropped_event"] == drop_event

    # The ShadowEngine has no reference to official authority or strategy state.
    assert authority.get_run(run_id) == official_before
    sealed = authority.seal(
        run_id=run_id,
        sealed_at="2026-10-08T20:30:00Z",
        evidence_refs=(evidence_ref(),),
    )
    assert tuple(sealed.rows) == official_rows
    assert sealed.seal["role"] == "OPERATING"
    assert all(event["next_state"] == "SHADOW" for event in lifecycle.events)
    assert all(event["next_state"] != "CHAMPION" for event in lifecycle.events)
