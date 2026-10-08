"""Append-only ApexLab experiment, trial, budget, and evaluation-access records.

The immutable Experiment contract is the preregistration. Later trial outcomes,
resource use, interruptions, artifacts, and holdout attempts are separate,
hash-chained records; the preregistration is never edited to show a winner.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any

from qc2_contracts.runtime import (
    CONTENT_ADDRESSED,
    ContractValidationError,
    domain_separated_sha256,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)
from qc2_temporal_firewall.models import canonical_json_bytes, parse_utc_instant

from .experiment_models import (
    ComparisonRegistration,
    ExperimentLedgerError,
    HoldoutAccessAttempt,
    HoldoutConsumptionState,
    RegisteredBudget,
    RegisteredExperiment,
    ResourceReport,
    ResourceUsage,
    TrialEvent,
    TrialState,
)
from .models import _contract_dict

EXPERIMENT_SCHEMA = "qc2.outcomes_research.Experiment.v1"
RESOURCE_BUDGET_SCHEMA = "qc2.integrity_build.ResourceBudget.v1"
HOLDOUT_ACCESS_RECEIPT_SCHEMA = "qc2.outcomes_research.HoldoutAccessReceipt.v1"

_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TRIAL_EVENT_DOMAIN = "qc2.apexlab.experiment-trial-event.v1"
_COMPARISON_DOMAIN = "qc2.apexlab.experiment-comparison.v1"
_ACCESS_ATTEMPT_DOMAIN = "qc2.validation.experiment-access-attempt.v1"
_ACTIVE_TRIAL_STATES = frozenset({TrialState.RUNNING})
_TERMINAL_EVENT_STATES = {
    "TRIAL_INTERRUPTED": TrialState.INTERRUPTED,
    "TRIAL_REJECTED": TrialState.REJECTED,
    "TRIAL_FAILED": TrialState.FAILED,
    "TRIAL_COMPLETED": TrialState.COMPLETED,
}
_NONTERMINAL_EVENT_STATES = {
    "TRIAL_STARTED": TrialState.RUNNING,
    "TRIAL_RESUMED": TrialState.RUNNING,
}


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ExperimentLedgerError("contract object keys must be strings")
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _validated_contract(contract_name: str, value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        payload = _contract_dict(value)
        validate_contract(contract_name, payload)
        if contract_name in CONTENT_ADDRESSED:
            verify_content_hash(contract_name, payload)
    except (ContractValidationError, TypeError, ValueError) as exc:
        raise ExperimentLedgerError(f"invalid {contract_name} contract: {exc}") from exc
    return payload


def _timestamp(value: str, field: str) -> str:
    try:
        parse_utc_instant(value, field)
    except (TypeError, ValueError) as exc:
        raise ExperimentLedgerError(f"{field} must be a valid UTC instant") from exc
    return value


def _timestamp_order(left: str, right: str, message: str) -> None:
    if parse_utc_instant(left, "timestamp") > parse_utc_instant(right, "timestamp"):
        raise ExperimentLedgerError(message)


def _validate_ref(
    value: Mapping[str, Any],
    schema_name: str,
    *,
    content_hash_required: bool,
) -> dict[str, str]:
    ref = _plain_json(value)
    required = {"target_schema_name", "target_id"}
    allowed = required | {"content_hash"}
    if (
        not isinstance(ref, dict)
        or not required.issubset(ref)
        or not set(ref).issubset(allowed)
        or ref.get("target_schema_name") != schema_name
        or not isinstance(ref.get("target_id"), str)
        or not _UUID7.fullmatch(ref["target_id"])
    ):
        raise ExperimentLedgerError(f"reference must target {schema_name}")
    content_hash = ref.get("content_hash")
    if content_hash_required and (
        not isinstance(content_hash, str) or not _SHA256.fullmatch(content_hash)
    ):
        raise ExperimentLedgerError(f"{schema_name} reference requires a SHA-256 hash")
    if content_hash is not None and (
        not isinstance(content_hash, str) or not _SHA256.fullmatch(content_hash)
    ):
        raise ExperimentLedgerError(f"{schema_name} reference has an invalid hash")
    return ref


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return canonical_json_bytes(_plain_json(value)).decode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExperimentLedgerError(f"record is not canonical JSON: {exc}") from exc


class ExperimentLedger:
    """Thread-safe in-memory ledger with PostgreSQL-aligned append-only semantics.

    Durable deployments use the matching QC2 PostgreSQL tables and role grants.
    This class supplies deterministic domain checks and immutable records for
    local research workers and acceptance fixtures.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._budgets: dict[str, RegisteredBudget] = {}
        self._experiments: dict[str, RegisteredExperiment] = {}
        self._events: dict[str, list[TrialEvent]] = {}
        self._comparisons: dict[str, ComparisonRegistration] = {}
        self._comparison_members: dict[str, set[str]] = {}
        self._holdout_attempts: dict[tuple[str, str], list[HoldoutAccessAttempt]] = {}

    def register_budget(self, budget_contract: Mapping[str, Any]) -> RegisteredBudget:
        budget = _validated_contract("ResourceBudget", budget_contract)
        if budget["configuration_domain"] != "RESEARCH":
            raise ExperimentLedgerError("experiment budgets must use the RESEARCH domain")
        if budget["fixture_only"] and budget["environment_namespace"] == "production":
            raise ExperimentLedgerError("fixture-only budgets are not valid in production")
        if budget["fixture_only"] and budget["evidence_class"] != "SYNTHETIC_FIXTURE":
            raise ExperimentLedgerError("fixture-only budgets require synthetic evidence")
        if budget["environment_namespace"] == "production" and (
            budget["evidence_class"] == "SYNTHETIC_FIXTURE"
        ):
            raise ExperimentLedgerError("synthetic budgets cannot be registered in production")
        if budget["authorized_cost_minor_units"] > 0:
            raise ExperimentLedgerError(
                "positive paid-cost budgets remain disabled until owner approvals are verifiable"
            )
        record = RegisteredBudget(
            budget_id=budget["id"],
            content_hash=budget["content_hash"],
            contract_json=_canonical_json(budget),
        )
        with self._lock:
            existing = self._budgets.get(record.budget_id)
            if existing is not None:
                if existing.content_hash != record.content_hash:
                    raise ExperimentLedgerError("budget identity is already bound to other content")
                return existing
            for existing in self._budgets.values():
                prior = existing.contract
                if (
                    prior["environment_namespace"] == budget["environment_namespace"]
                    and prior["budget_key"] == budget["budget_key"]
                    and prior["version"] == budget["version"]
                ):
                    raise ExperimentLedgerError("budget key/version is already registered")
            self._budgets[record.budget_id] = record
        return record

    def register_experiment(
        self, experiment_contract: Mapping[str, Any]
    ) -> RegisteredExperiment:
        experiment = _validated_contract("Experiment", experiment_contract)
        budget_ref = experiment["budget_ref"]
        with self._lock:
            budget_record = self._budgets.get(budget_ref["target_id"])
            if budget_record is None:
                raise ExperimentLedgerError("experiment budget must be registered first")
            budget = budget_record.contract
            if (
                budget_ref["target_schema_name"] != RESOURCE_BUDGET_SCHEMA
                or budget_ref["content_hash"] != budget_record.content_hash
            ):
                raise ExperimentLedgerError("experiment is not bound to the registered budget")
            if experiment["environment_namespace"] != budget["environment_namespace"]:
                raise ExperimentLedgerError("experiment and budget environments must match")
            if experiment["created_at"][:10] < budget["effective_from"]:
                raise ExperimentLedgerError("experiment predates the budget effective date")
            if (
                experiment["environment_namespace"] == "production"
                and experiment["evidence_class"] == "SYNTHETIC_FIXTURE"
            ):
                raise ExperimentLedgerError("synthetic experiments are not valid in production")
            try:
                estimate = Decimal(experiment["compute_cost"])
            except (InvalidOperation, TypeError) as exc:
                raise ExperimentLedgerError("experiment compute cost is not a decimal") from exc
            if not estimate.is_finite() or estimate < 0:
                raise ExperimentLedgerError("experiment compute cost must be finite and nonnegative")
            record = RegisteredExperiment(
                experiment_id=experiment["id"],
                budget_id=budget_record.budget_id,
                content_hash=experiment["content_hash"],
                contract_json=_canonical_json(experiment),
            )
            existing = self._experiments.get(record.experiment_id)
            if existing is not None:
                if existing.content_hash != record.content_hash:
                    raise ExperimentLedgerError(
                        "experiment identity is already bound to other content"
                    )
                return existing
            registered_count = sum(
                existing.budget_id == record.budget_id
                for existing in self._experiments.values()
            )
            if registered_count >= budget["max_experiments"]:
                raise ExperimentLedgerError("experiment count budget is exhausted")
            self._experiments[record.experiment_id] = record
            self._events[record.experiment_id] = []
        return record

    def register_comparison(
        self,
        experiment_ids: Sequence[str],
        *,
        registered_at: str,
        comparison_id: str | None = None,
    ) -> ComparisonRegistration:
        at = _timestamp(registered_at, "registered_at")
        members = tuple(sorted(set(experiment_ids)))
        if len(members) < 2 or len(members) != len(experiment_ids):
            raise ExperimentLedgerError("comparison requires at least two distinct experiments")
        comparison_id = comparison_id or new_uuidv7()
        if not _UUID7.fullmatch(comparison_id):
            raise ExperimentLedgerError("comparison id must be UUIDv7")
        with self._lock:
            records = [self._require_experiment(item) for item in members]
            contracts = [record.contract for record in records]
            if any(self._state(item) is not TrialState.REGISTERED for item in members):
                raise ExperimentLedgerError(
                    "comparison must be registered before any trial starts"
                )
            if len({record.budget_id for record in records}) != 1:
                raise ExperimentLedgerError("comparison experiments must share one budget")
            if len({canonical_json_bytes(item["dataset_ref"]) for item in contracts}) != 1:
                raise ExperimentLedgerError("comparison experiments must share a dataset")
            if len({canonical_json_bytes(item["split_ref"]) for item in contracts}) != 1:
                raise ExperimentLedgerError("comparison experiments must share a split")
            if len({item["environment_namespace"] for item in contracts}) != 1:
                raise ExperimentLedgerError("comparison experiments must share an environment")
            for item in contracts:
                _timestamp_order(item["created_at"], at, "comparison predates an experiment")
            candidates: dict[str, dict[str, str]] = {}
            for item in contracts:
                for candidate_ref in item["candidate_refs"]:
                    ref = _validate_ref(
                        candidate_ref,
                        "qc2.models_prediction.ModelManifest.v1",
                        content_hash_required=True,
                    )
                    candidates[ref["target_id"]] = ref
            if len(candidates) < 2:
                raise ExperimentLedgerError("comparison requires at least two distinct candidates")
            payload: dict[str, Any] = {
                "id": comparison_id,
                "registered_at": at,
                "experiment_refs": [
                    {
                        "target_schema_name": EXPERIMENT_SCHEMA,
                        "target_id": record.experiment_id,
                        "content_hash": record.content_hash,
                    }
                    for record in records
                ],
                "dataset_ref": contracts[0]["dataset_ref"],
                "split_ref": contracts[0]["split_ref"],
                "candidate_refs": [candidates[key] for key in sorted(candidates)],
            }
            digest = domain_separated_sha256(
                _COMPARISON_DOMAIN, canonical_json_bytes(payload)
            )
            payload["registration_hash"] = digest
            record = ComparisonRegistration(
                comparison_id=comparison_id,
                experiment_ids=members,
                registration_hash=digest,
                registration_json=_canonical_json(payload),
            )
            existing = self._comparisons.get(comparison_id)
            if existing is not None:
                if existing.registration_hash != digest:
                    raise ExperimentLedgerError(
                        "comparison identity is already bound to other content"
                    )
                return existing
            self._comparisons[comparison_id] = record
            for experiment_id in members:
                self._comparison_members.setdefault(experiment_id, set()).add(comparison_id)
        return record

    def start_trial(
        self,
        experiment_id: str,
        *,
        recorded_at: str,
        anticipated_cost_minor_units: int = 0,
    ) -> TrialEvent:
        at = _timestamp(recorded_at, "recorded_at")
        if type(anticipated_cost_minor_units) is not int or anticipated_cost_minor_units < 0:
            raise ExperimentLedgerError("anticipated cost must be a nonnegative integer")
        with self._lock:
            experiment = self._require_experiment(experiment_id)
            state = self._state(experiment_id)
            if state not in (TrialState.REGISTERED, TrialState.INTERRUPTED):
                raise ExperimentLedgerError(f"cannot start a trial in {state.value} state")
            budget = self._budget_for(experiment.budget_id)
            running = sum(
                self._state(item.experiment_id) in _ACTIVE_TRIAL_STATES
                for item in self._experiments.values()
                if item.budget_id == experiment.budget_id
            )
            if running >= budget["max_concurrent_jobs"]:
                raise ExperimentLedgerError("concurrent-job budget is exhausted")
            spent = self._budget_usage(experiment.budget_id).cost_minor_units
            if spent + anticipated_cost_minor_units > budget["authorized_cost_minor_units"]:
                raise ExperimentLedgerError("authorized cost budget is exhausted")
            prior_events = self._events[experiment_id]
            attempt_number = 1 + sum(
                item.event_type in ("TRIAL_STARTED", "TRIAL_RESUMED")
                for item in prior_events
            )
            if state is TrialState.INTERRUPTED:
                interrupted = next(
                    item
                    for item in reversed(prior_events)
                    if item.event_type == "TRIAL_INTERRUPTED"
                )
                checkpoint_ref = interrupted.payload["checkpoint_ref"]
                event_type = "TRIAL_RESUMED"
                extra = {
                    "checkpoint_ref": checkpoint_ref,
                    "resume_from_event_id": interrupted.event_id,
                }
            else:
                event_type = "TRIAL_STARTED"
                extra = {"checkpoint_ref": None, "resume_from_event_id": None}
            return self._append_trial_event(
                experiment,
                event_type=event_type,
                attempt_number=attempt_number,
                recorded_at=at,
                usage=ResourceUsage(),
                extra=extra,
            )

    def reject_trial(
        self,
        experiment_id: str,
        *,
        reason: str,
        recorded_at: str,
        usage: ResourceUsage = ResourceUsage(),
        reason_code: str = "CANDIDATE_REJECTED",
    ) -> TrialEvent:
        return self._record_terminal(
            experiment_id,
            event_type="TRIAL_REJECTED",
            reason=reason,
            reason_code=reason_code,
            recorded_at=recorded_at,
            usage=usage,
            allowed_states=(TrialState.REGISTERED, TrialState.RUNNING),
        )

    def interrupt_trial(
        self,
        experiment_id: str,
        *,
        reason: str,
        checkpoint_ref: Mapping[str, Any],
        recorded_at: str,
        usage: ResourceUsage,
    ) -> TrialEvent:
        ref = _validate_ref(
            checkpoint_ref,
            "qc2.integrity_build.ArtifactManifest.v1",
            content_hash_required=True,
        )
        return self._record_terminal(
            experiment_id,
            event_type="TRIAL_INTERRUPTED",
            reason=reason,
            reason_code="WORKER_INTERRUPTED",
            recorded_at=recorded_at,
            usage=usage,
            allowed_states=(TrialState.RUNNING,),
            extra={"checkpoint_ref": ref, "artifact_refs": [ref]},
        )

    def fail_trial(
        self,
        experiment_id: str,
        *,
        reason: str,
        reason_code: str,
        recorded_at: str,
        usage: ResourceUsage,
        artifact_refs: Sequence[Mapping[str, Any]] = (),
    ) -> TrialEvent:
        refs = self._artifact_refs(artifact_refs)
        return self._record_terminal(
            experiment_id,
            event_type="TRIAL_FAILED",
            reason=reason,
            reason_code=reason_code,
            recorded_at=recorded_at,
            usage=usage,
            allowed_states=(TrialState.RUNNING,),
            extra={"artifact_refs": refs},
        )

    def complete_trial(
        self,
        experiment_id: str,
        *,
        result_ref: Mapping[str, Any],
        recorded_at: str,
        usage: ResourceUsage,
        artifact_refs: Sequence[Mapping[str, Any]] = (),
    ) -> TrialEvent:
        result = _validate_ref(
            result_ref,
            "qc2.outcomes_research.CandidateEvaluation.v1",
            content_hash_required=False,
        )
        refs = self._artifact_refs(artifact_refs)
        return self._record_terminal(
            experiment_id,
            event_type="TRIAL_COMPLETED",
            reason=None,
            reason_code=None,
            recorded_at=recorded_at,
            usage=usage,
            allowed_states=(TrialState.RUNNING,),
            extra={"result_ref": result, "artifact_refs": refs},
        )

    def register_artifact(
        self,
        experiment_id: str,
        artifact_ref: Mapping[str, Any],
        *,
        size_bytes: int,
        recorded_at: str,
    ) -> TrialEvent:
        at = _timestamp(recorded_at, "recorded_at")
        if type(size_bytes) is not int or size_bytes < 0:
            raise ExperimentLedgerError("artifact size must be a nonnegative integer")
        ref = _validate_ref(
            artifact_ref,
            "qc2.integrity_build.ArtifactManifest.v1",
            content_hash_required=True,
        )
        with self._lock:
            experiment = self._require_experiment(experiment_id)
            return self._append_trial_event(
                experiment,
                event_type="ARTIFACT_REGISTERED",
                attempt_number=self._current_attempt(experiment_id),
                recorded_at=at,
                usage=ResourceUsage(artifact_bytes=size_bytes),
                extra={"artifact_ref": ref},
            )

    def record_holdout_access_attempt(
        self,
        experiment_id: str,
        dataset_ref: Mapping[str, Any],
        *,
        requested_at: str,
        receipt_contract: Mapping[str, Any] | None = None,
        denial_reason: str | None = None,
    ) -> HoldoutAccessAttempt:
        at = _timestamp(requested_at, "requested_at")
        ref = _validate_ref(
            dataset_ref,
            "qc2.outcomes_research.DatasetManifest.v1",
            content_hash_required=True,
        )
        key = (ref["target_id"], ref["content_hash"])
        validated_receipt: dict[str, Any] | None = None
        if receipt_contract is not None:
            validated_receipt = _validated_contract("HoldoutAccessReceipt", receipt_contract)
            receipt_body = {
                name: value
                for name, value in validated_receipt.items()
                if name != "receipt_hash"
            }
            expected_hash = domain_separated_sha256(
                "qc2.validation.holdout-access.v1",
                canonical_json_bytes(receipt_body),
            )
            if validated_receipt["receipt_hash"] != expected_hash:
                raise ExperimentLedgerError("holdout receipt hash does not match its payload")
            if validated_receipt["dataset_ref"] != ref:
                raise ExperimentLedgerError("holdout receipt refers to a different dataset")
            if validated_receipt["access_scope"] not in ("METRICS_ONLY", "AGGREGATES_ONLY"):
                raise ExperimentLedgerError("trainer-ledger access cannot release holdout rows")
            if validated_receipt["requested_at"] != at:
                raise ExperimentLedgerError("holdout receipt request time does not match the attempt")
            _timestamp_order(
                validated_receipt["requested_at"],
                validated_receipt["granted_at"],
                "holdout grant predates its request",
            )
            _timestamp_order(
                validated_receipt["granted_at"],
                validated_receipt["created_at"],
                "holdout receipt predates its grant",
            )
        elif not isinstance(denial_reason, str) or not denial_reason.strip():
            raise ExperimentLedgerError("denied holdout attempts require a reason")

        with self._lock:
            experiment = self._require_experiment(experiment_id)
            if not self._comparison_members.get(experiment_id):
                raise ExperimentLedgerError(
                    "holdout access requires a preregistered comparison"
                )
            attempts = self._holdout_attempts.setdefault(key, [])
            prior_grant = next(
                (item for item in attempts if item.disposition == "GRANTED"), None
            )
            if prior_grant is not None:
                disposition = "REPEAT_BLOCKED"
                receipt_id = prior_grant.receipt_id
                reason_code = "HOLDOUT_ALREADY_CONSUMED"
                presented_receipt_id = (
                    validated_receipt["id"] if validated_receipt is not None else None
                )
            elif validated_receipt is not None:
                disposition = "GRANTED"
                receipt_id = validated_receipt["id"]
                reason_code = None
                presented_receipt_id = receipt_id
            else:
                disposition = "DENIED"
                receipt_id = None
                reason_code = "ACCESS_REFUSED"
                presented_receipt_id = None

            sequence = len(attempts) + 1
            previous_hash = attempts[-1].event_hash if attempts else None
            body: dict[str, Any] = {
                "id": new_uuidv7(),
                "experiment_ref": {
                    "target_schema_name": EXPERIMENT_SCHEMA,
                    "target_id": experiment.experiment_id,
                    "content_hash": experiment.content_hash,
                },
                "dataset_ref": ref,
                "sequence": sequence,
                "disposition": disposition,
                "requested_at": at,
                "reason_code": reason_code,
                "denial_reason": denial_reason if disposition == "DENIED" else None,
                "receipt_ref": (
                    {
                        "target_schema_name": HOLDOUT_ACCESS_RECEIPT_SCHEMA,
                        "target_id": receipt_id,
                    }
                    if receipt_id is not None
                    else None
                ),
                "presented_receipt_id": presented_receipt_id,
                "previous_event_hash": previous_hash,
            }
            event_hash = domain_separated_sha256(
                _ACCESS_ATTEMPT_DOMAIN, canonical_json_bytes(body)
            )
            payload = {**body, "event_hash": event_hash}
            attempt = HoldoutAccessAttempt(
                dataset_id=key[0],
                dataset_content_hash=key[1],
                sequence=sequence,
                experiment_id=experiment.experiment_id,
                disposition=disposition,
                receipt_id=receipt_id,
                event_hash=event_hash,
                event_json=_canonical_json(payload),
            )
            attempts.append(attempt)
        return attempt

    def holdout_consumption_state(
        self, dataset_ref: Mapping[str, Any]
    ) -> HoldoutConsumptionState:
        ref = _validate_ref(
            dataset_ref,
            "qc2.outcomes_research.DatasetManifest.v1",
            content_hash_required=True,
        )
        attempts = self._holdout_attempts.get(
            (ref["target_id"], ref["content_hash"]), []
        )
        if any(item.disposition == "REPEAT_BLOCKED" for item in attempts):
            return HoldoutConsumptionState.REPEATED_ACCESS
        if any(item.disposition == "GRANTED" for item in attempts):
            return HoldoutConsumptionState.CONSUMED
        return HoldoutConsumptionState.NOT_CONSUMED

    def holdout_access_attempts(
        self, dataset_ref: Mapping[str, Any]
    ) -> tuple[HoldoutAccessAttempt, ...]:
        ref = _validate_ref(
            dataset_ref,
            "qc2.outcomes_research.DatasetManifest.v1",
            content_hash_required=True,
        )
        with self._lock:
            return tuple(
                self._holdout_attempts.get(
                    (ref["target_id"], ref["content_hash"]), ()
                )
            )

    def trial_events(self, experiment_id: str) -> tuple[TrialEvent, ...]:
        with self._lock:
            self._require_experiment(experiment_id)
            return tuple(self._events[experiment_id])

    def experiment_state(self, experiment_id: str) -> TrialState:
        with self._lock:
            self._require_experiment(experiment_id)
            return self._state(experiment_id)

    def registered_experiment(self, experiment_id: str) -> RegisteredExperiment:
        with self._lock:
            return self._require_experiment(experiment_id)

    def verify_history(self, experiment_id: str) -> bool:
        with self._lock:
            self._require_experiment(experiment_id)
            previous_hash: str | None = None
            for expected_sequence, event in enumerate(self._events[experiment_id], start=1):
                payload = event.payload
                claimed_hash = payload.pop("event_hash", None)
                calculated_hash = domain_separated_sha256(
                    _TRIAL_EVENT_DOMAIN, canonical_json_bytes(payload)
                )
                if (
                    event.sequence != expected_sequence
                    or event.previous_event_hash != previous_hash
                    or payload.get("previous_event_hash") != previous_hash
                    or claimed_hash != calculated_hash
                    or event.event_hash != calculated_hash
                ):
                    return False
                previous_hash = event.event_hash
            return True

    def budget_report(self, budget_id: str) -> ResourceReport:
        with self._lock:
            budget = self._budget_for(budget_id)
            experiment_ids = sorted(
                item.experiment_id
                for item in self._experiments.values()
                if item.budget_id == budget_id
            )
            counts = Counter(self._state(item).value for item in experiment_ids)
            total_usage = self._budget_usage(budget_id)
            over_budget = tuple(
                item
                for item in experiment_ids
                if any(
                    event.payload.get("budget_overruns")
                    for event in self._events[item]
                )
            )
            return ResourceReport(
                budget_id=budget_id,
                registered_experiments=len(experiment_ids),
                max_experiments=budget["max_experiments"],
                running_experiments=counts[TrialState.RUNNING.value],
                status_counts=tuple(
                    (state.value, counts[state.value])
                    for state in TrialState
                ),
                elapsed_seconds=total_usage.elapsed_seconds,
                cpu_seconds=total_usage.cpu_seconds,
                peak_memory_bytes=total_usage.peak_memory_bytes,
                artifact_bytes=total_usage.artifact_bytes,
                spent_minor_units=total_usage.cost_minor_units,
                authorized_cost_minor_units=budget["authorized_cost_minor_units"],
                remaining_cost_minor_units=max(
                    0,
                    budget["authorized_cost_minor_units"]
                    - total_usage.cost_minor_units,
                ),
                currency=budget["currency"],
                over_budget_experiments=over_budget,
            )

    def resource_report(self, experiment_id: str) -> ResourceReport:
        with self._lock:
            experiment = self._require_experiment(experiment_id)
            budget = self._budget_for(experiment.budget_id)
            usage = self._experiment_usage(experiment_id)
            events = self._events[experiment_id]
            overruns = (
                (experiment_id,)
                if any(event.payload.get("budget_overruns") for event in events)
                else ()
            )
            return ResourceReport(
                budget_id=experiment.budget_id,
                registered_experiments=1,
                max_experiments=budget["max_experiments"],
                running_experiments=int(self._state(experiment_id) is TrialState.RUNNING),
                status_counts=tuple(
                    (
                        state.value,
                        int(self._state(experiment_id) is state),
                    )
                    for state in TrialState
                ),
                elapsed_seconds=usage.elapsed_seconds,
                cpu_seconds=usage.cpu_seconds,
                peak_memory_bytes=usage.peak_memory_bytes,
                artifact_bytes=usage.artifact_bytes,
                spent_minor_units=usage.cost_minor_units,
                authorized_cost_minor_units=budget["authorized_cost_minor_units"],
                remaining_cost_minor_units=max(
                    0,
                    budget["authorized_cost_minor_units"]
                    - self._budget_usage(experiment.budget_id).cost_minor_units,
                ),
                currency=budget["currency"],
                over_budget_experiments=overruns,
            )

    def _record_terminal(
        self,
        experiment_id: str,
        *,
        event_type: str,
        reason: str | None,
        reason_code: str | None,
        recorded_at: str,
        usage: ResourceUsage,
        allowed_states: tuple[TrialState, ...],
        extra: Mapping[str, Any] | None = None,
    ) -> TrialEvent:
        at = _timestamp(recorded_at, "recorded_at")
        if not isinstance(usage, ResourceUsage):
            raise ExperimentLedgerError("usage must be a ResourceUsage record")
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ExperimentLedgerError("failure and rejection reasons must be nonempty")
        if reason_code is not None and (
            not isinstance(reason_code, str) or not reason_code.strip()
        ):
            raise ExperimentLedgerError("reason codes must be nonempty")
        with self._lock:
            experiment = self._require_experiment(experiment_id)
            state = self._state(experiment_id)
            if state not in allowed_states:
                raise ExperimentLedgerError(f"cannot record {event_type} in {state.value} state")
            return self._append_trial_event(
                experiment,
                event_type=event_type,
                attempt_number=self._current_attempt(experiment_id),
                recorded_at=at,
                usage=usage,
                extra={
                    "reason": reason,
                    "reason_code": reason_code,
                    **dict(extra or {}),
                },
            )

    def _append_trial_event(
        self,
        experiment: RegisteredExperiment,
        *,
        event_type: str,
        attempt_number: int,
        recorded_at: str,
        usage: ResourceUsage,
        extra: Mapping[str, Any],
    ) -> TrialEvent:
        events = self._events[experiment.experiment_id]
        budget = self._budget_for(experiment.budget_id)
        overruns = self._resource_overruns(experiment, usage)
        previous_hash = events[-1].event_hash if events else None
        body: dict[str, Any] = {
            "id": new_uuidv7(),
            "experiment_ref": {
                "target_schema_name": EXPERIMENT_SCHEMA,
                "target_id": experiment.experiment_id,
                "content_hash": experiment.content_hash,
            },
            "sequence": len(events) + 1,
            "event_type": event_type,
            "attempt_number": attempt_number,
            "recorded_at": recorded_at,
            "previous_event_hash": previous_hash,
            "usage": {
                **usage.to_dict(),
                "currency": budget["currency"],
            },
            "budget_overruns": list(overruns),
            **dict(extra),
        }
        event_hash = domain_separated_sha256(
            _TRIAL_EVENT_DOMAIN, canonical_json_bytes(body)
        )
        payload = {**body, "event_hash": event_hash}
        event = TrialEvent(
            event_id=body["id"],
            experiment_id=experiment.experiment_id,
            sequence=body["sequence"],
            event_type=event_type,
            attempt_number=attempt_number,
            recorded_at=recorded_at,
            usage=usage,
            previous_event_hash=previous_hash,
            event_hash=event_hash,
            event_json=_canonical_json(payload),
        )
        events.append(event)
        return event

    def _resource_overruns(
        self, experiment: RegisteredExperiment, usage: ResourceUsage
    ) -> tuple[str, ...]:
        budget = self._budget_for(experiment.budget_id)
        prior = self._experiment_usage(experiment.experiment_id)
        total_budget = self._budget_usage(experiment.budget_id)
        checks = (
            (
                "MAX_ELAPSED_SECONDS",
                prior.elapsed_seconds + usage.elapsed_seconds
                > budget["max_elapsed_seconds"],
            ),
            (
                "MAX_CPU_SECONDS",
                prior.cpu_seconds + usage.cpu_seconds > budget["max_cpu_seconds"],
            ),
            (
                "MAX_MEMORY_BYTES",
                max(prior.peak_memory_bytes, usage.peak_memory_bytes)
                > budget["max_memory_bytes"],
            ),
            (
                "MAX_ARTIFACT_BYTES",
                prior.artifact_bytes + usage.artifact_bytes
                > budget["max_artifact_bytes"],
            ),
            (
                "AUTHORIZED_COST_MINOR_UNITS",
                total_budget.cost_minor_units + usage.cost_minor_units
                > budget["authorized_cost_minor_units"],
            ),
        )
        return tuple(name for name, exceeded in checks if exceeded)

    def _experiment_usage(self, experiment_id: str) -> ResourceUsage:
        events = self._events.get(experiment_id, ())
        return ResourceUsage(
            elapsed_seconds=sum(event.usage.elapsed_seconds for event in events),
            cpu_seconds=sum(event.usage.cpu_seconds for event in events),
            peak_memory_bytes=max(
                (event.usage.peak_memory_bytes for event in events), default=0
            ),
            artifact_bytes=sum(event.usage.artifact_bytes for event in events),
            cost_minor_units=sum(event.usage.cost_minor_units for event in events),
        )

    def _budget_usage(self, budget_id: str) -> ResourceUsage:
        usages = [
            self._experiment_usage(item.experiment_id)
            for item in self._experiments.values()
            if item.budget_id == budget_id
        ]
        return ResourceUsage(
            elapsed_seconds=sum(item.elapsed_seconds for item in usages),
            cpu_seconds=sum(item.cpu_seconds for item in usages),
            peak_memory_bytes=max(
                (item.peak_memory_bytes for item in usages), default=0
            ),
            artifact_bytes=sum(item.artifact_bytes for item in usages),
            cost_minor_units=sum(item.cost_minor_units for item in usages),
        )

    def _current_attempt(self, experiment_id: str) -> int:
        return sum(
            event.event_type in ("TRIAL_STARTED", "TRIAL_RESUMED")
            for event in self._events[experiment_id]
        )

    def _state(self, experiment_id: str) -> TrialState:
        state = TrialState.REGISTERED
        for event in self._events[experiment_id]:
            if event.event_type in _NONTERMINAL_EVENT_STATES:
                state = _NONTERMINAL_EVENT_STATES[event.event_type]
            elif event.event_type in _TERMINAL_EVENT_STATES:
                state = _TERMINAL_EVENT_STATES[event.event_type]
        return state

    def _require_experiment(self, experiment_id: str) -> RegisteredExperiment:
        try:
            return self._experiments[experiment_id]
        except KeyError as exc:
            raise ExperimentLedgerError("experiment is not registered") from exc

    def _budget_for(self, budget_id: str) -> dict[str, Any]:
        try:
            return self._budgets[budget_id].contract
        except KeyError as exc:
            raise ExperimentLedgerError("resource budget is not registered") from exc

    @staticmethod
    def _artifact_refs(refs: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
        result = [
            _validate_ref(
                ref,
                "qc2.integrity_build.ArtifactManifest.v1",
                content_hash_required=True,
            )
            for ref in refs
        ]
        identities = [item["target_id"] for item in result]
        if len(identities) != len(set(identities)):
            raise ExperimentLedgerError("artifact references must be unique within an event")
        return result
