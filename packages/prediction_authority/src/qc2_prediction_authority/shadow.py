"""Prospective, candidate-isolated Shadow prediction and coverage authority."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any, Protocol

from qc2_contracts.runtime import (
    canonical_content_hash,
    canonical_json_bytes,
    canonical_decimal_text,
    domain_separated_sha256,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)

from .authority import BINDING_HASH_DOMAIN
from .models import (
    PredictionAuthorityError,
    ScoreResult,
    _reference,
    _references,
    utc_instant,
    utc_text,
)

SHADOW_SET_SCHEMA = "qc2.models_prediction.ShadowPredictionSet.v1"
MODEL_SCHEMA = "qc2.models_prediction.ModelManifest.v1"
RUN_SCHEMA = "qc2.models_prediction.PredictionRun.v1"
SNAPSHOT_SCHEMA = "qc2.identity_market.MarketSnapshot.v1"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
LABEL_SCHEMA = "qc2.scientific_definitions.LabelDefinition.v1"

REGISTRATION_HASH_DOMAIN = "qc2.shadow-registration.v1"
INPUT_HASH_DOMAIN = "qc2.shadow-input.v1"
WINDOW_HASH_DOMAIN = "qc2.shadow-window.v1"
PREDICTION_HASH_DOMAIN = "qc2.shadow-prediction.v1"
ATTEMPT_HASH_DOMAIN = "qc2.shadow-attempt.v1"
SEAL_HASH_DOMAIN = "qc2.shadow-seal.v1"
LEDGER_EVENT_HASH_DOMAIN = "qc2.shadow-ledger-event.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SLUG = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z")
_COMPARATOR_SCHEMAS = {
    MODEL_SCHEMA,
    "qc2.scientific_definitions.BaselineManifest.v1",
    "qc2.governance_owner.ChampionPointer.v1",
}


class ShadowLifecyclePort(Protocol):
    """The model-registry transition required to make a candidate a Shadow."""

    def transition_to_shadow(
        self,
        model_ref: Mapping[str, Any],
        shadow_set: Mapping[str, Any],
        transitioned_at: str,
    ) -> Any:
        """Record the model-registry CHALLENGER -> SHADOW transition."""


class ModelRegistryShadowLifecycle:
    """Structural adapter for the existing model-registry lifecycle API."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def transition_to_shadow(
        self,
        model_ref: Mapping[str, Any],
        shadow_set: Mapping[str, Any],
        transitioned_at: str,
    ) -> Any:
        return self._registry.transition_lifecycle(
            model_ref,
            "SHADOW",
            shadow_set,
            runtime_role="qc2_runtime_prediction",
            transitioned_at=transitioned_at,
        )


ShadowPredictor = Callable[
    [Mapping[str, str], Mapping[str, Any]],
    Mapping[str, ScoreResult],
]


@dataclass(frozen=True, slots=True)
class ShadowSessionInput:
    """The immutable, candidate-independent input snapshot shared by Shadows."""

    session_id: str
    started_at: str
    operating_run: Mapping[str, Any]
    snapshot_ref: Mapping[str, Any]
    eligible_instrument_refs: Sequence[Mapping[str, Any]]
    model_inputs: Mapping[str, Any]


@dataclass(slots=True)
class _ShadowTrial:
    registration: dict[str, Any]
    model_manifest: dict[str, Any]
    training_cutoff: str
    lifecycle_event: Any
    window_plan: dict[str, Any] | None = None
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    dropped_event: dict[str, Any] | None = None


class ShadowEngine:
    """Collect forward evidence without access to official ranking or execution.

    This in-process authority is a deterministic domain implementation. Its
    lifecycle port records registration in ModelRegistry; production durability
    remains the responsibility of a persistence adapter.
    """

    def __init__(
        self,
        lifecycle: ShadowLifecyclePort,
        *,
        id_factory: Callable[[], str] = new_uuidv7,
    ) -> None:
        if not callable(getattr(lifecycle, "transition_to_shadow", None)):
            raise PredictionAuthorityError("ShadowEngine requires a model lifecycle authority")
        self._lifecycle = lifecycle
        self._id_factory = id_factory
        self._lock = RLock()
        self._trials: dict[str, _ShadowTrial] = {}
        self._model_to_shadow: dict[tuple[str, str], str] = {}

    def register_shadow(
        self,
        *,
        model_manifest: Mapping[str, Any],
        registered_at: str,
        eligible_at: str,
        target_label_refs: Sequence[Mapping[str, Any]],
        comparison_window_sessions: int,
        comparator_refs: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Freeze the model, forward boundary, labels, comparators and window."""
        model = copy.deepcopy(dict(model_manifest))
        try:
            validate_contract("ModelManifest", model)
            verify_content_hash("ModelManifest", model)
        except (TypeError, ValueError, KeyError) as exc:
            raise PredictionAuthorityError(f"Shadow model manifest is invalid: {exc}") from exc
        if model["lifecycle_state"] != "CHALLENGER":
            raise PredictionAuthorityError("only a CHALLENGER can be preregistered as a Shadow")

        registered = utc_text(utc_instant(registered_at, "registered_at"))
        eligible = utc_text(utc_instant(eligible_at, "eligible_at"))
        cutoff = utc_text(utc_instant(model["training_cutoff"], "ModelManifest.training_cutoff"))
        registered_instant = utc_instant(registered, "registered_at")
        eligible_instant = utc_instant(eligible, "eligible_at")
        cutoff_instant = utc_instant(cutoff, "ModelManifest.training_cutoff")
        if registered_instant < cutoff_instant:
            raise PredictionAuthorityError("Shadow registration predates the model training cutoff")
        if eligible_instant <= max(registered_instant, cutoff_instant):
            raise PredictionAuthorityError(
                "Shadow eligibility must follow both registration and the training cutoff"
            )
        if (
            isinstance(comparison_window_sessions, bool)
            or not isinstance(comparison_window_sessions, int)
            or comparison_window_sessions < 1
        ):
            raise PredictionAuthorityError("comparison window must contain positive sessions")

        model_ref = _reference(
            {
                "target_schema_name": MODEL_SCHEMA,
                "target_id": model["id"],
                "content_hash": model["content_hash"],
            },
            MODEL_SCHEMA,
            "model_ref",
            require_content_hash=True,
        )
        labels = _references(
            target_label_refs,
            LABEL_SCHEMA,
            "target_label_refs",
            require_content_hash=True,
        )
        model_labels = _references(
            model["target_label_refs"],
            LABEL_SCHEMA,
            "ModelManifest.target_label_refs",
            require_content_hash=True,
        )
        if not labels or labels != model_labels:
            raise PredictionAuthorityError(
                "Shadow target labels must exactly match the frozen model labels"
            )

        normalized_comparators = self._normalize_comparators(comparator_refs, model_ref)
        schema_names = {ref["target_schema_name"] for ref in normalized_comparators}
        if not {
            "qc2.governance_owner.ChampionPointer.v1",
            "qc2.scientific_definitions.BaselineManifest.v1",
        }.issubset(schema_names):
            raise PredictionAuthorityError(
                "Shadow preregistration requires pinned Champion and baseline comparators"
            )

        registration_basis = {
            "model_ref": model_ref,
            "registered_at": registered,
            "eligible_at": eligible,
            "target_label_refs": [dict(ref) for ref in labels],
            "comparison_window_sessions": comparison_window_sessions,
            "comparator_refs": [dict(ref) for ref in normalized_comparators],
        }
        registration_hash = domain_separated_sha256(
            REGISTRATION_HASH_DOMAIN,
            canonical_json_bytes(registration_basis),
        )
        registration: dict[str, Any] = {
            "schema_name": SHADOW_SET_SCHEMA,
            "schema_version": "1.0",
            "id": self._id_factory(),
            "created_at": registered,
            "owning_authority": "prediction",
            "evidence_class": model["evidence_class"],
            "environment_namespace": model["environment_namespace"],
            "source_refs": [model_ref],
            "content_hash": "0" * 64,
            "model_ref": model_ref,
            "eligible_at": eligible,
            "target_label_refs": [dict(ref) for ref in labels],
            "comparison_window_sessions": comparison_window_sessions,
            "comparator_refs": [dict(ref) for ref in normalized_comparators],
            "registration_hash": registration_hash,
        }
        registration["content_hash"] = canonical_content_hash(
            "ShadowPredictionSet",
            registration,
        )
        try:
            validate_contract("ShadowPredictionSet", registration)
            verify_content_hash("ShadowPredictionSet", registration)
        except (TypeError, ValueError, KeyError) as exc:
            raise PredictionAuthorityError(f"Shadow registration is invalid: {exc}") from exc

        key = (model_ref["target_schema_name"], model_ref["target_id"])
        with self._lock:
            if key in self._model_to_shadow:
                raise PredictionAuthorityError("model already has a registered Shadow trial")
            lifecycle_event = self._lifecycle.transition_to_shadow(
                model_ref,
                copy.deepcopy(registration),
                registered,
            )
            self._trials[registration["id"]] = _ShadowTrial(
                registration=registration,
                model_manifest=model,
                training_cutoff=cutoff,
                lifecycle_event=self._lifecycle_document(lifecycle_event),
            )
            self._model_to_shadow[key] = registration["id"]
        return copy.deepcopy(registration)

    def schedule_comparison_window(
        self,
        shadow_set_id: str,
        *,
        session_start_deadlines: Mapping[str, str],
    ) -> dict[str, Any]:
        """Freeze every session and start deadline before the first prediction."""
        with self._lock:
            trial = self._require_trial(shadow_set_id)
            if trial.dropped_event is not None:
                raise PredictionAuthorityError("a dropped Shadow cannot schedule a window")
            registration = trial.registration
            if trial.window_plan is not None:
                requested = self._normalize_window(
                    trial,
                    session_start_deadlines,
                )
                if requested != trial.window_plan["sessions"]:
                    raise PredictionAuthorityError("Shadow comparison window is immutable")
                return copy.deepcopy(trial.window_plan)

            sessions = self._normalize_window(trial, session_start_deadlines)
            if len(sessions) != registration["comparison_window_sessions"]:
                raise PredictionAuthorityError(
                    "scheduled session count must equal the preregistered comparison window"
                )
            basis = {
                "shadow_prediction_set_ref": self._shadow_ref(registration),
                "sessions": sessions,
            }
            plan = {
                **basis,
                "plan_hash": domain_separated_sha256(
                    WINDOW_HASH_DOMAIN,
                    canonical_json_bytes(basis),
                ),
            }
            trial.window_plan = plan
            trial.sessions = {
                session["session_id"]: {
                    "session_id": session["session_id"],
                    "expected_start_by": session["expected_start_by"],
                    "status": "SCHEDULED",
                    "attempt": None,
                    "prediction_rows": [],
                    "seal": None,
                    "ledger_event": None,
                }
                for session in sessions
            }
            return copy.deepcopy(plan)

    def score_session(
        self,
        session_input: ShadowSessionInput,
        *,
        predictors: Mapping[str, ShadowPredictor],
    ) -> tuple[dict[str, Any], ...]:
        """Score every active preregistered Shadow on one identical input snapshot."""
        normalized = self._normalize_session_input(session_input)
        session_id = normalized["session_id"]
        started_at = normalized["started_at"]

        with self._lock:
            scheduled = [
                (shadow_id, trial)
                for shadow_id, trial in self._trials.items()
                if trial.window_plan is not None and session_id in trial.sessions
            ]
            if not scheduled:
                raise PredictionAuthorityError("session is outside every planned Shadow window")
            pinned_refs = {
                ref["target_id"]: ref
                for ref in normalized["shadow_prediction_set_refs"]
            }
            for shadow_id, trial in scheduled:
                expected_ref = self._shadow_ref(trial.registration)
                if pinned_refs.get(expected_ref["target_id"]) != expected_ref:
                    raise PredictionAuthorityError(
                        "Shadow registration was not pinned into the operating run before scoring"
                    )
            expected = {
                shadow_id
                for shadow_id, trial in scheduled
                if trial.dropped_event is None
                and trial.sessions[session_id]["status"] == "SCHEDULED"
            }
            if set(predictors) != expected:
                raise PredictionAuthorityError(
                    "each active Shadow in the session must be scored; none may be selected out"
                )
            if not expected:
                raise PredictionAuthorityError("no pending Shadow attempts remain for this session")

            actual_start = utc_instant(started_at, "started_at")
            run_created_at = utc_instant(
                normalized["operating_run_created_at"],
                "PredictionRun.created_at",
            )
            if actual_start <= run_created_at:
                raise PredictionAuthorityError(
                    "Shadow inference must start after the operating run binds its inputs"
                )
            run_deadline = utc_instant(
                normalized["operating_run_decision_deadline"],
                "PredictionRun.decision_deadline",
            )
            if actual_start > run_deadline:
                raise PredictionAuthorityError(
                    "Shadow inference started after the operating PredictionRun decision deadline"
                )
            if actual_start.date() < date.fromisoformat(session_id):
                raise PredictionAuthorityError(
                    "Shadow inference cannot start before its exchange session date"
                )
            for shadow_id in sorted(expected):
                trial = self._trials[shadow_id]
                registration = trial.registration
                if run_created_at <= utc_instant(
                    registration["created_at"],
                    "ShadowPredictionSet.created_at",
                ):
                    raise PredictionAuthorityError(
                        "Shadow registration occurred after the operating run was bound"
                    )
                if run_created_at <= utc_instant(registration["eligible_at"], "eligible_at"):
                    raise PredictionAuthorityError(
                        "operating run was bound before the Shadow became eligible"
                    )
                if actual_start <= utc_instant(registration["created_at"], "registration.created_at"):
                    raise PredictionAuthorityError(
                        "Shadow attempt must start after its registration"
                    )
                if actual_start <= utc_instant(registration["eligible_at"], "eligible_at"):
                    raise PredictionAuthorityError(
                        "Shadow attempt must start after its eligibility boundary"
                    )
                if actual_start <= utc_instant(trial.training_cutoff, "training_cutoff"):
                    raise PredictionAuthorityError(
                        "Shadow attempt cannot precede the model training cutoff"
                    )
                if utc_instant(
                    trial.sessions[session_id]["expected_start_by"],
                    "expected_start_by",
                ) > run_deadline:
                    raise PredictionAuthorityError(
                        "Shadow window deadline exceeds the operating PredictionRun decision deadline"
                    )
                if not callable(predictors[shadow_id]):
                    raise PredictionAuthorityError("Shadow predictor must be callable")

            results: list[dict[str, Any]] = []
            for shadow_id in sorted(expected):
                trial = self._trials[shadow_id]
                registration = trial.registration
                slot = trial.sessions[session_id]
                predictor = predictors[shadow_id]
                if actual_start > utc_instant(slot["expected_start_by"], "expected_start_by"):
                    attempt = self._make_attempt(
                        trial=trial,
                        slot=slot,
                        normalized=normalized,
                        status="FAILED",
                        failure_code="late_shadow_start",
                        prediction_rows=(),
                    )
                else:
                    try:
                        output = predictor(
                            copy.deepcopy(registration["model_ref"]),
                            copy.deepcopy(normalized["model_inputs"]),
                        )
                        rows = self._prediction_rows(
                            trial=trial,
                            normalized=normalized,
                            outputs=output,
                        )
                    except Exception as exc:
                        code = self._failure_code(exc)
                        attempt = self._make_attempt(
                            trial=trial,
                            slot=slot,
                            normalized=normalized,
                            status="FAILED",
                            failure_code=code,
                            prediction_rows=(),
                        )
                    else:
                        attempt = self._make_attempt(
                            trial=trial,
                            slot=slot,
                            normalized=normalized,
                            status="SCORED",
                            failure_code=None,
                            prediction_rows=rows,
                        )
                slot["status"] = attempt["status"]
                slot["attempt"] = attempt["attempt"]
                slot["prediction_rows"] = attempt["prediction_rows"]
                slot["seal"] = attempt["seal"]
                results.append(copy.deepcopy(attempt))
            return tuple(results)

    def mark_missed(
        self,
        shadow_set_id: str,
        session_id: str,
        *,
        observed_at: str,
    ) -> dict[str, Any]:
        """Seal an explicit missed Shadow attempt after its frozen start deadline."""
        observed = utc_text(utc_instant(observed_at, "observed_at"))
        with self._lock:
            trial = self._require_trial(shadow_set_id)
            slot = self._require_pending_slot(trial, session_id)
            if utc_instant(observed, "observed_at") < utc_instant(
                slot["expected_start_by"], "expected_start_by"
            ):
                raise PredictionAuthorityError("a Shadow attempt cannot be missed before deadline")
            event = self._ledger_event(
                trial,
                session_id,
                "MISSED",
                observed,
                "not_started_by_deadline",
            )
            slot["status"] = "MISSED"
            slot["ledger_event"] = event
            return copy.deepcopy(event)

    def drop_shadow(
        self,
        shadow_set_id: str,
        *,
        dropped_at: str,
        reason_code: str,
    ) -> dict[str, Any]:
        """Record a terminal drop without removing any scheduled session."""
        if not isinstance(reason_code, str) or not _SLUG.fullmatch(reason_code):
            raise PredictionAuthorityError("drop reason must be a lowercase reason code")
        dropped = utc_text(utc_instant(dropped_at, "dropped_at"))
        with self._lock:
            trial = self._require_trial(shadow_set_id)
            if trial.dropped_event is not None:
                raise PredictionAuthorityError("Shadow trial is already dropped")
            if trial.window_plan is None:
                raise PredictionAuthorityError("drop requires an accountable comparison window")
            if all(slot["status"] != "SCHEDULED" for slot in trial.sessions.values()):
                raise PredictionAuthorityError("completed Shadow window cannot be dropped")
            event = self._ledger_event(
                trial,
                None,
                "DROPPED",
                dropped,
                reason_code,
            )
            trial.dropped_event = event
            for session_id, slot in trial.sessions.items():
                if slot["status"] == "SCHEDULED":
                    slot["status"] = "DROPPED"
                    slot["ledger_event"] = self._ledger_event(
                        trial,
                        session_id,
                        "DROPPED",
                        dropped,
                        reason_code,
                    )
            return copy.deepcopy(event)

    def coverage_ledger(self, shadow_set_id: str) -> dict[str, Any]:
        """Return all planned sessions, including failed, missed and dropped slots."""
        with self._lock:
            trial = self._require_trial(shadow_set_id)
            return copy.deepcopy(self._coverage(trial))

    def attempt_evidence(self, shadow_set_id: str) -> tuple[dict[str, Any], ...]:
        """Return immutable attempt, prediction-row and seal documents."""
        with self._lock:
            trial = self._require_trial(shadow_set_id)
            return tuple(
                {
                    "session_id": session_id,
                    "status": slot["status"],
                    "attempt": copy.deepcopy(slot["attempt"]),
                    "prediction_rows": copy.deepcopy(slot["prediction_rows"]),
                    "seal": copy.deepcopy(slot["seal"]),
                    "ledger_event": copy.deepcopy(slot["ledger_event"]),
                }
                for session_id, slot in sorted(trial.sessions.items())
            )

    def mobile_projection(self) -> dict[str, Any]:
        """Small, read-only status projection for mobile clients."""
        with self._lock:
            items = []
            for shadow_id in sorted(self._trials):
                trial = self._trials[shadow_id]
                coverage = self._coverage(trial)
                items.append(
                    {
                        "shadow_prediction_set_id": shadow_id,
                        "model_ref": copy.deepcopy(trial.registration["model_ref"]),
                        "lifecycle_state": "SHADOW",
                        "trial_state": coverage["trial_state"],
                        "window_sessions": coverage["window_sessions"],
                        "successful_sessions": coverage["successful_sessions"],
                        "failed_sessions": coverage["failed_sessions"],
                        "missed_sessions": coverage["missed_sessions"],
                        "dropped_sessions": coverage["dropped_sessions"],
                        "coverage_fraction": coverage["coverage_fraction"],
                        "execution_capability": "NONE",
                    }
                )
            return {
                "projection": "SHADOW_MOBILE",
                "execution_capability": "NONE",
                "items": items,
            }

    def report_projection(self) -> dict[str, Any]:
        """Detailed, candidate-specific evidence view; never chooses a winner."""
        with self._lock:
            trials = []
            for shadow_id in sorted(self._trials):
                trial = self._trials[shadow_id]
                trials.append(
                    {
                        "registration": copy.deepcopy(trial.registration),
                        "lifecycle_state": "SHADOW",
                        "lifecycle_event": copy.deepcopy(trial.lifecycle_event),
                        "dropped_event": copy.deepcopy(trial.dropped_event),
                        "coverage": self._coverage(trial),
                        "attempt_evidence": [
                            {
                                "session_id": session_id,
                                "status": slot["status"],
                                "attempt_hash": (
                                    slot["attempt"]["content_hash"]
                                    if slot["attempt"] is not None
                                    else None
                                ),
                                "seal_hash": (
                                    slot["seal"]["content_hash"]
                                    if slot["seal"] is not None
                                    else None
                                ),
                                "ledger_event_hash": (
                                    slot["ledger_event"]["content_hash"]
                                    if slot["ledger_event"] is not None
                                    else None
                                ),
                                "prediction_rows": copy.deepcopy(slot["prediction_rows"]),
                            }
                            for session_id, slot in sorted(trial.sessions.items())
                        ],
                    }
                )
            return {
                "projection": "SHADOW_REPORT",
                "selection_policy": "NO_PER_SESSION_WINNER",
                "official_rank_capability": "NONE",
                "strategy_mutation_capability": "NONE",
                "execution_capability": "NONE",
                "trials": trials,
            }

    def _normalize_window(
        self,
        trial: _ShadowTrial,
        session_start_deadlines: Mapping[str, str],
    ) -> list[dict[str, str]]:
        if not isinstance(session_start_deadlines, Mapping) or not session_start_deadlines:
            raise PredictionAuthorityError("comparison window requires session deadlines")
        if any(not isinstance(session_id, str) for session_id in session_start_deadlines):
            raise PredictionAuthorityError("Shadow window session IDs must be strings")
        registration = trial.registration
        cutoff_date = date.fromisoformat(trial.training_cutoff[:10])
        registered_date = date.fromisoformat(registration["created_at"][:10])
        eligible_date = date.fromisoformat(registration["eligible_at"][:10])
        normalized: list[dict[str, str]] = []
        for session_id in sorted(session_start_deadlines):
            try:
                session_date = date.fromisoformat(session_id)
            except (TypeError, ValueError) as exc:
                raise PredictionAuthorityError("Shadow window session must be an ISO date") from exc
            if session_date.isoformat() != session_id:
                raise PredictionAuthorityError("Shadow window session must be an ISO date")
            # Strictly later dates avoid relying on an exchange-local same-day cutoff.
            if session_date <= max(cutoff_date, registered_date, eligible_date):
                raise PredictionAuthorityError(
                    "Shadow window must start on sessions after training and registration"
                )
            deadline = utc_text(
                utc_instant(session_start_deadlines[session_id], "expected_start_by")
            )
            if utc_instant(deadline, "expected_start_by") <= utc_instant(
                registration["eligible_at"], "eligible_at"
            ):
                raise PredictionAuthorityError(
                    "Shadow start deadline must follow candidate eligibility"
                )
            normalized.append(
                {"session_id": session_id, "expected_start_by": deadline}
            )
        return normalized

    @staticmethod
    def _normalize_comparators(
        comparator_refs: Sequence[Mapping[str, Any]],
        model_ref: Mapping[str, str],
    ) -> list[dict[str, str]]:
        if isinstance(comparator_refs, (str, bytes)) or not isinstance(
            comparator_refs, Sequence
        ):
            raise PredictionAuthorityError("comparator_refs must be a list of pinned references")
        normalized = []
        for index, value in enumerate(comparator_refs):
            if not isinstance(value, Mapping):
                raise PredictionAuthorityError(f"comparator_refs[{index}] must be a reference")
            schema = value.get("target_schema_name")
            if not isinstance(schema, str) or schema not in _COMPARATOR_SCHEMAS:
                raise PredictionAuthorityError(f"comparator_refs[{index}] has an invalid schema")
            ref = _reference(
                value,
                schema,
                f"comparator_refs[{index}]",
                require_content_hash=True,
            )
            if schema == MODEL_SCHEMA and ref["target_id"] == model_ref["target_id"]:
                raise PredictionAuthorityError("Shadow candidate cannot compare against itself")
            normalized.append(ref)
        keys = [(ref["target_schema_name"], ref["target_id"]) for ref in normalized]
        if len(keys) != len(set(keys)):
            raise PredictionAuthorityError("comparator_refs contains duplicate identities")
        return sorted(
            normalized,
            key=lambda ref: (ref["target_schema_name"].encode(), ref["target_id"].encode()),
        )

    @staticmethod
    def _normalize_session_input(session: ShadowSessionInput) -> dict[str, Any]:
        if not isinstance(session, ShadowSessionInput):
            raise PredictionAuthorityError("Shadow scoring requires typed session inputs")
        try:
            parsed_session = date.fromisoformat(session.session_id)
        except (TypeError, ValueError) as exc:
            raise PredictionAuthorityError("session_id must be an ISO exchange session") from exc
        if parsed_session.isoformat() != session.session_id:
            raise PredictionAuthorityError("session_id must be an ISO exchange session")
        started_at = utc_text(utc_instant(session.started_at, "started_at"))
        if not isinstance(session.operating_run, Mapping):
            raise PredictionAuthorityError("operating_run must be a frozen PredictionAuthority read")
        run_record = copy.deepcopy(dict(session.operating_run))
        run_contract = run_record.get("contract")
        binding_snapshot = run_record.get("binding_snapshot")
        binding_hash = run_record.get("binding_hash")
        try:
            validate_contract("PredictionRun", run_contract)
        except (TypeError, ValueError, KeyError) as exc:
            raise PredictionAuthorityError("operating_run contains an invalid PredictionRun") from exc
        if run_contract["run_state"] not in {
            "INPUTS_BOUND",
            "FEATURES_COMPLETE",
            "SCORED",
            "RANKED",
            "SEALED",
        }:
            raise PredictionAuthorityError("Shadow inputs require a run with frozen bindings")
        if (
            not isinstance(binding_snapshot, Mapping)
            or not isinstance(binding_hash, str)
            or not _SHA256.fullmatch(binding_hash)
        ):
            raise PredictionAuthorityError("operating_run lacks its frozen binding snapshot")
        computed_binding_hash = domain_separated_sha256(
            BINDING_HASH_DOMAIN,
            canonical_json_bytes(binding_snapshot),
        )
        if computed_binding_hash != binding_hash:
            raise PredictionAuthorityError("operating_run binding snapshot hash is invalid")
        if run_contract["session_id"] != session.session_id:
            raise PredictionAuthorityError("operating_run belongs to another session")
        operating_run = _reference(
            {
                "target_schema_name": RUN_SCHEMA,
                "target_id": run_contract["id"],
            },
            RUN_SCHEMA,
            "operating_run_ref",
        )
        operating_run_created_at = utc_text(
            utc_instant(run_contract["created_at"], "PredictionRun.created_at")
        )
        snapshot = _reference(
            session.snapshot_ref,
            SNAPSHOT_SCHEMA,
            "snapshot_ref",
            require_content_hash=True,
        )
        instruments = _references(
            session.eligible_instrument_refs,
            INSTRUMENT_SCHEMA,
            "eligible_instrument_refs",
            require_content_hash=True,
        )
        if not instruments:
            raise PredictionAuthorityError("Shadow inputs require eligible instruments")
        bound_snapshot = _reference(
            binding_snapshot.get("snapshot_ref", {}),
            SNAPSHOT_SCHEMA,
            "operating_run.binding_snapshot.snapshot_ref",
            require_content_hash=True,
        )
        if bound_snapshot != snapshot:
            raise PredictionAuthorityError("Shadow snapshot differs from the frozen operating run")
        if binding_snapshot.get("session_id") != session.session_id:
            raise PredictionAuthorityError("operating run binding belongs to another session")
        decision_deadline = utc_text(
            utc_instant(run_contract["decision_deadline"], "PredictionRun.decision_deadline")
        )
        if binding_snapshot.get("decision_deadline") != decision_deadline:
            raise PredictionAuthorityError(
                "PredictionRun and binding snapshot decision deadlines disagree"
            )
        shadow_refs = _references(
            binding_snapshot.get("shadow_prediction_set_refs", ()),
            SHADOW_SET_SCHEMA,
            "operating_run.binding_snapshot.shadow_prediction_set_refs",
            require_content_hash=True,
        )
        bound_dependency_refs = run_contract.get("dependency_refs", ())
        if any(
            dict(shadow_ref) not in bound_dependency_refs
            for shadow_ref in shadow_refs
        ):
            raise PredictionAuthorityError(
                "operating run dependency inventory omits a pinned Shadow registration"
            )
        if run_contract.get("snapshot_ref") != bound_snapshot:
            raise PredictionAuthorityError("PredictionRun and binding snapshot disagree")
        if not isinstance(session.model_inputs, Mapping):
            raise PredictionAuthorityError("model_inputs must be a JSON object")
        model_inputs = copy.deepcopy(dict(session.model_inputs))
        if model_inputs.get("session_id") != session.session_id:
            raise PredictionAuthorityError("model_inputs belong to another session")
        if _reference(
            model_inputs.get("snapshot_ref", {}),
            SNAPSHOT_SCHEMA,
            "model_inputs.snapshot_ref",
            require_content_hash=True,
        ) != snapshot:
            raise PredictionAuthorityError("model_inputs use another market snapshot")
        input_instruments = _references(
            model_inputs.get("eligible_instrument_refs", ()),
            INSTRUMENT_SCHEMA,
            "model_inputs.eligible_instrument_refs",
            require_content_hash=True,
        )
        if input_instruments != instruments:
            raise PredictionAuthorityError(
                "model_inputs instrument coverage differs from the operating run"
            )
        if not isinstance(model_inputs.get("feature_inputs"), Mapping):
            raise PredictionAuthorityError("model_inputs require a JSON feature_inputs object")
        try:
            canonical_json_bytes(model_inputs)
        except (TypeError, ValueError) as exc:
            raise PredictionAuthorityError("model_inputs must be canonical JSON data") from exc
        basis = {
            "session_id": session.session_id,
            "operating_run_ref": operating_run,
            "operating_run_binding_hash": binding_hash,
            "operating_run_decision_deadline": decision_deadline,
            "snapshot_ref": snapshot,
            "shadow_prediction_set_refs": [dict(ref) for ref in shadow_refs],
            "eligible_instrument_refs": [dict(ref) for ref in instruments],
            "model_inputs": model_inputs,
        }
        input_hash = domain_separated_sha256(
            INPUT_HASH_DOMAIN,
            canonical_json_bytes(basis),
        )
        return {
            **basis,
            "started_at": started_at,
            "operating_run_created_at": operating_run_created_at,
            "input_hash": input_hash,
            "shadow_prediction_set_refs": [dict(ref) for ref in shadow_refs],
        }

    def _prediction_rows(
        self,
        *,
        trial: _ShadowTrial,
        normalized: Mapping[str, Any],
        outputs: Mapping[str, ScoreResult],
    ) -> list[dict[str, Any]]:
        if not isinstance(outputs, Mapping):
            raise PredictionAuthorityError("predictor output must map every instrument to a result")
        instruments = normalized["eligible_instrument_refs"]
        expected_ids = {ref["target_id"] for ref in instruments}
        if set(outputs) != expected_ids:
            raise PredictionAuthorityError("predictor output instrument coverage differs")
        rows = []
        for instrument_ref in instruments:
            instrument_id = instrument_ref["target_id"]
            result = self._normalize_score(outputs[instrument_id])
            disposition = "SCORED" if result.score is not None else "UNSCORABLE"
            row_id = self._id_factory()
            payload = {
                "id": row_id,
                "shadow_prediction_set_ref": self._shadow_ref(trial.registration),
                "model_ref": copy.deepcopy(trial.registration["model_ref"]),
                "operating_run_ref": copy.deepcopy(normalized["operating_run_ref"]),
                "snapshot_ref": copy.deepcopy(normalized["snapshot_ref"]),
                "session_id": normalized["session_id"],
                "input_hash": normalized["input_hash"],
                "instrument_ref": copy.deepcopy(dict(instrument_ref)),
                "target_label_refs": copy.deepcopy(trial.registration["target_label_refs"]),
                "disposition": disposition,
                "score": result.score,
                "reason_code": result.reason_code,
            }
            rows.append(
                {
                    "format": "qc2-shadow-prediction.v1",
                    **payload,
                    "content_hash": self._digest(PREDICTION_HASH_DOMAIN, payload),
                }
            )
        return rows

    def _make_attempt(
        self,
        *,
        trial: _ShadowTrial,
        slot: Mapping[str, Any],
        normalized: Mapping[str, Any],
        status: str,
        failure_code: str | None,
        prediction_rows: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        registration = trial.registration
        prediction_hashes = [
            {
                "prediction_id": row["id"],
                "content_hash": row["content_hash"],
            }
            for row in prediction_rows
        ]
        attempt_payload = {
            "id": self._id_factory(),
            "shadow_prediction_set_ref": self._shadow_ref(registration),
            "model_ref": copy.deepcopy(registration["model_ref"]),
            "session_id": normalized["session_id"],
            "status": status,
            "started_at": normalized["started_at"],
            "input_hash": normalized["input_hash"],
            "failure_code": failure_code,
            "prediction_hashes": prediction_hashes,
        }
        attempt = {
            "format": "qc2-shadow-attempt.v1",
            **attempt_payload,
            "content_hash": self._digest(ATTEMPT_HASH_DOMAIN, attempt_payload),
        }
        inventory = [
            {
                "instrument_id": row["instrument_ref"]["target_id"],
                "prediction_hash": row["content_hash"],
                "disposition": row["disposition"],
                "score": row["score"],
                "reason_code": row["reason_code"],
            }
            for row in prediction_rows
        ]
        disposition_counts = {
            "SCORED": sum(row["disposition"] == "SCORED" for row in prediction_rows),
            "UNSCORABLE": sum(row["disposition"] == "UNSCORABLE" for row in prediction_rows),
        }
        if status == "FAILED":
            disposition_counts["FAILED"] = 1
        seal_payload = {
            "id": self._id_factory(),
            "role": "SHADOW",
            "shadow_prediction_set_ref": self._shadow_ref(registration),
            "model_ref": copy.deepcopy(registration["model_ref"]),
            "operating_run_ref": copy.deepcopy(normalized["operating_run_ref"]),
            "snapshot_ref": copy.deepcopy(normalized["snapshot_ref"]),
            "session_id": normalized["session_id"],
            "status": status,
            "attempt_hash": attempt["content_hash"],
            "prediction_hashes": prediction_hashes,
            "disposition_counts": disposition_counts,
            "payload_inventory_hash": self._digest(ATTEMPT_HASH_DOMAIN, inventory),
            "deadline": slot["expected_start_by"],
            "sealed_at": normalized["started_at"],
            "input_hash": normalized["input_hash"],
        }
        seal = {
            "format": "qc2-shadow-seal.v1",
            **seal_payload,
            "content_hash": self._digest(SEAL_HASH_DOMAIN, seal_payload),
        }
        return {
            "status": status,
            "attempt": attempt,
            "prediction_rows": copy.deepcopy(list(prediction_rows)),
            "seal": seal,
        }

    def _ledger_event(
        self,
        trial: _ShadowTrial,
        session_id: str | None,
        state: str,
        occurred_at: str,
        reason_code: str,
    ) -> dict[str, Any]:
        event_id = self._id_factory()
        payload = {
            "id": event_id,
            "shadow_prediction_set_ref": self._shadow_ref(trial.registration),
            "model_ref": copy.deepcopy(trial.registration["model_ref"]),
            "session_id": session_id,
            "state": state,
            "occurred_at": occurred_at,
            "reason_code": reason_code,
        }
        return {
            "format": "qc2-shadow-ledger-event.v1",
            **payload,
            "content_hash": self._digest(LEDGER_EVENT_HASH_DOMAIN, payload),
        }

    @staticmethod
    def _normalize_score(result: ScoreResult) -> ScoreResult:
        if not isinstance(result, ScoreResult):
            raise PredictionAuthorityError("Shadow result must be a ScoreResult")
        if result.score is None:
            if not isinstance(result.reason_code, str) or not _SLUG.fullmatch(
                result.reason_code
            ):
                raise PredictionAuthorityError("unscorable Shadow rows require a reason code")
            return ScoreResult(None, result.reason_code)
        if result.reason_code is not None or not isinstance(result.score, str):
            raise PredictionAuthorityError("scored Shadow rows require one exact decimal")
        try:
            parsed = Decimal(result.score)
        except InvalidOperation as exc:
            raise PredictionAuthorityError("Shadow score is not a decimal") from exc
        if not parsed.is_finite():
            raise PredictionAuthorityError("Shadow score must be finite")
        return ScoreResult(canonical_decimal_text(result.score, precision=6))

    @staticmethod
    def _failure_code(error: Exception) -> str:
        message = str(error)
        if isinstance(error, PredictionAuthorityError) and _SLUG.fullmatch(message):
            return message
        name = re.sub(r"[^a-z0-9]+", "_", type(error).__name__.lower()).strip("_")
        return f"predictor_{name or 'error'}"

    @staticmethod
    def _digest(domain: str, payload: Any) -> str:
        return domain_separated_sha256(domain, canonical_json_bytes(payload))

    @staticmethod
    def _lifecycle_document(event: Any) -> Any:
        if event is None:
            return None
        if isinstance(event, Mapping):
            return copy.deepcopy(dict(event))
        if is_dataclass(event):
            return copy.deepcopy(asdict(event))
        return None

    @staticmethod
    def _shadow_ref(registration: Mapping[str, Any]) -> dict[str, str]:
        return {
            "target_schema_name": SHADOW_SET_SCHEMA,
            "target_id": registration["id"],
            "content_hash": registration["content_hash"],
        }

    @staticmethod
    def _coverage(trial: _ShadowTrial) -> dict[str, Any]:
        slots = list(trial.sessions.values())
        counts = {
            status: sum(slot["status"] == status for slot in slots)
            for status in ("SCHEDULED", "SCORED", "FAILED", "MISSED", "DROPPED")
        }
        total = len(slots)
        terminal = total - counts["SCHEDULED"]
        if trial.dropped_event is not None:
            trial_state = "DROPPED"
        elif trial.window_plan is None:
            trial_state = "REGISTERED"
        elif counts["SCHEDULED"]:
            trial_state = "IN_PROGRESS" if terminal else "SCHEDULED"
        else:
            trial_state = "COMPLETE"
        return {
            "shadow_prediction_set_ref": ShadowEngine._shadow_ref(trial.registration),
            "trial_state": trial_state,
            "lifecycle_state": "SHADOW",
            "window_plan_hash": (
                trial.window_plan["plan_hash"] if trial.window_plan is not None else None
            ),
            "window_sessions": total,
            "accounted_sessions": terminal,
            "successful_sessions": counts["SCORED"],
            "failed_sessions": counts["FAILED"],
            "missed_sessions": counts["MISSED"],
            "dropped_sessions": counts["DROPPED"],
            "pending_sessions": counts["SCHEDULED"],
            "coverage_fraction": (counts["SCORED"] / total if total else None),
            "attempt_accounting_fraction": (terminal / total if total else None),
            "sessions": [
                {
                    "session_id": session_id,
                    "expected_start_by": slot["expected_start_by"],
                    "status": slot["status"],
                    "attempt_hash": (
                        slot["attempt"]["content_hash"]
                        if slot["attempt"] is not None
                        else None
                    ),
                    "seal_hash": (
                        slot["seal"]["content_hash"] if slot["seal"] is not None else None
                    ),
                    "ledger_event_hash": (
                        slot["ledger_event"]["content_hash"]
                        if slot["ledger_event"] is not None
                        else None
                    ),
                    "ledger_event": copy.deepcopy(slot["ledger_event"]),
                }
                for session_id, slot in sorted(trial.sessions.items())
            ],
        }

    def _require_trial(self, shadow_set_id: str) -> _ShadowTrial:
        trial = self._trials.get(shadow_set_id)
        if trial is None:
            raise PredictionAuthorityError("ShadowPredictionSet is not registered")
        return trial

    @staticmethod
    def _require_pending_slot(trial: _ShadowTrial, session_id: str) -> dict[str, Any]:
        if trial.dropped_event is not None:
            raise PredictionAuthorityError("dropped Shadow cannot change its coverage ledger")
        slot = trial.sessions.get(session_id)
        if slot is None:
            raise PredictionAuthorityError("session is outside the preregistered Shadow window")
        if slot["status"] != "SCHEDULED":
            raise PredictionAuthorityError("Shadow session is already terminal")
        return slot
