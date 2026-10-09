"""Fail-closed research launch checks and bounded, priority-aware scheduling."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from qc2_contracts.runtime import canonical_json_bytes, validate_contract, verify_content_hash
from qc2_temporal_firewall.models import parse_utc_instant

from .dataset_models import PreparedDatasetRow, fold_rows_hash
from .experiment_models import HoldoutConsumptionState

_DATASET_SCHEMA = "qc2.outcomes_research.DatasetManifest.v1"


class ResearchReadinessError(ValueError):
    """Research readiness or queue policy input is invalid."""


class ResearchMode(str, Enum):
    DISABLED = "DISABLED"
    ENABLED = "ENABLED"


class WorkloadClass(str, Enum):
    EVIDENCE = "EVIDENCE"
    PREDICTION = "PREDICTION"
    RESEARCH = "RESEARCH"


@dataclass(frozen=True, slots=True)
class ResearchRuntimeContext:
    """Fresh operational facts that are not part of immutable QC2 contracts.

    Missing facts block research. The default context therefore leaves research
    disabled and cannot authorize a launch.
    """

    mode: ResearchMode = ResearchMode.DISABLED
    environment_namespace: str | None = None
    assessed_at: str | None = None
    budget_expires_at: str | None = None
    holdout_consumption_state: HoldoutConsumptionState | None = None
    storage_available: bool = False
    running_jobs: int | None = None
    spent_minor_units: int | None = None
    requested_cost_minor_units: int = 0


@dataclass(frozen=True, slots=True)
class ResearchReadinessAssessment:
    status: str
    reason_codes: tuple[str, ...]
    dataset_id: str | None
    split_id: str | None
    budget_id: str | None
    assessed_at: str | None
    schedule_priority: str = "RESEARCH_BACKGROUND"

    @property
    def ready(self) -> bool:
        return self.status == "RESEARCH_READY"


@dataclass(frozen=True, slots=True)
class QueueJob:
    job_id: str
    workload_class: WorkloadClass
    priority: int
    enqueued_at: str


@dataclass(frozen=True, slots=True)
class QueueDeferral:
    job_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class QueueDecision:
    scheduled_job_ids: tuple[str, ...]
    deferred: tuple[QueueDeferral, ...]
    decision_hash: str


def _plain_json(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _plain_json(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("contract object keys must be strings")
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _contract(name: str, value: Mapping[str, Any]) -> dict[str, Any]:
    payload = _plain_json(value)
    validate_contract(name, payload)
    verify_content_hash(name, payload)
    return payload


def _parse_interval_rows(value: Any, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    intervals: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} entries must be JSON text")
        parsed = json.loads(item)
        if not isinstance(parsed, dict):
            raise ValueError(f"{field_name} entries must be JSON objects")
        intervals.append(parsed)
    return intervals


def _row_keys(rows: Sequence[PreparedDatasetRow]) -> tuple[str, ...]:
    keys = tuple(getattr(row, "row_key", None) for row in rows)
    if not all(isinstance(key, str) and key for key in keys):
        raise ValueError("row keys must be nonempty strings")
    if len(keys) != len(set(keys)):
        raise ValueError("row keys must be unique")
    return keys


def _labels_mature_before_cutoff(
    rows: Sequence[PreparedDatasetRow],
    cutoff_at: str,
    *,
    reason_prefix: str,
    reasons: set[str],
) -> None:
    try:
        cutoff = parse_utc_instant(cutoff_at, "fold cutoff")
    except (TypeError, ValueError):
        reasons.add(f"{reason_prefix}_CUTOFF_UNAVAILABLE")
        return
    for row in rows:
        available_at = getattr(row, "label_available_at", None)
        if not isinstance(available_at, str):
            reasons.add(f"{reason_prefix}_MATURITY_UNAVAILABLE")
            continue
        try:
            available = parse_utc_instant(available_at, "label availability")
        except (TypeError, ValueError):
            reasons.add(f"{reason_prefix}_MATURITY_UNAVAILABLE")
            continue
        if available >= cutoff:
            reasons.add(f"IMMATURE_{reason_prefix}_LABEL")


def assess_research_readiness(
    *,
    dataset_manifest: Mapping[str, Any],
    split_manifest: Mapping[str, Any],
    resource_budget: Mapping[str, Any],
    fold_id: str,
    training_index: Any,
    transform_hash: str,
    validation_rows: Sequence[PreparedDatasetRow],
    validation_index_hash: str,
    context: ResearchRuntimeContext,
    storage_available: bool | None = None,
) -> ResearchReadinessAssessment:
    """Assess one specific training fold; every missing safety fact blocks launch."""
    reasons: set[str] = set()
    if not isinstance(context, ResearchRuntimeContext):
        context = ResearchRuntimeContext()
        reasons.add("RUNTIME_CONTEXT_UNAVAILABLE")
    if context.mode is not ResearchMode.ENABLED:
        reasons.add("RESEARCH_DISABLED")

    assessed_at = context.assessed_at
    assessed_instant = None
    if not isinstance(assessed_at, str):
        reasons.add("ASSESSMENT_TIME_UNAVAILABLE")
    else:
        try:
            assessed_instant = parse_utc_instant(assessed_at, "assessment time")
        except (TypeError, ValueError):
            reasons.add("ASSESSMENT_TIME_INVALID")

    dataset: dict[str, Any] = {}
    split: dict[str, Any] = {}
    budget: dict[str, Any] = {}
    for contract_name, supplied, target, reason_code in (
        ("DatasetManifest", dataset_manifest, "dataset", "DATASET_CONTRACT_INVALID"),
        ("SplitManifest", split_manifest, "split", "SPLIT_CONTRACT_INVALID"),
        ("ResourceBudget", resource_budget, "budget", "RESOURCE_BUDGET_CONTRACT_INVALID"),
    ):
        try:
            payload = _contract(contract_name, supplied)
        except (TypeError, ValueError, KeyError):
            reasons.add(reason_code)
            continue
        if target == "dataset":
            dataset = payload
        elif target == "split":
            split = payload
        else:
            budget = payload

    if dataset and split:
        expected_dataset_ref = {
            "target_schema_name": _DATASET_SCHEMA,
            "target_id": dataset["id"],
            "content_hash": dataset["content_hash"],
        }
        if split.get("dataset_ref") != expected_dataset_ref or split.get(
            "split_hash"
        ) != dataset.get("split_assignment_hash"):
            reasons.add("DATASET_SPLIT_MISMATCH")
        if dataset.get("evidence_class") != split.get("evidence_class"):
            reasons.add("DATASET_EVIDENCE_CLASS_MISMATCH")

    runtime_environment = context.environment_namespace
    if runtime_environment not in {"test", "research"}:
        reasons.add("ENVIRONMENT_NOT_ISOLATED")
    for contract in (dataset, split, budget):
        if contract and contract.get("environment_namespace") != runtime_environment:
            reasons.add("ENVIRONMENT_MISMATCH")
    if budget and budget.get("configuration_domain") != "RESEARCH":
        reasons.add("RESOURCE_BUDGET_NOT_RESEARCH")

    try:
        if not isinstance(fold_id, str) or not fold_id:
            raise ValueError("fold id is missing")
        training_intervals = _parse_interval_rows(
            split.get("training_intervals"), "training_intervals"
        )
        validation_intervals = _parse_interval_rows(
            split.get("validation_intervals"), "validation_intervals"
        )
        matching_training = [item for item in training_intervals if item.get("fold_id") == fold_id]
        matching_validation = [
            item for item in validation_intervals if item.get("fold_id") == fold_id
        ]
        if len(matching_training) != 1 or len(matching_validation) != 1:
            raise ValueError("selected fold must have one training and validation interval")
        training_interval = matching_training[0]
        validation_interval = matching_validation[0]
        training_rows = tuple(training_index.rows)
        training_keys = _row_keys(training_rows)
        validation_keys = _row_keys(validation_rows)
        if set(training_keys) != set(training_interval.get("released_row_keys", ())):
            reasons.add("TRAINING_DATASET_MISMATCH")
        if set(validation_keys) != set(validation_interval.get("released_row_keys", ())):
            reasons.add("VALIDATION_DATASET_MISMATCH")

        try:
            calculated_training_hash = fold_rows_hash(
                fold_id,
                training_interval["cutoff_at"],
                transform_hash,
                training_rows,
            )
            if (
                training_index.fold_id != fold_id
                or training_index.cutoff_at != training_interval["cutoff_at"]
                or tuple(training_index.member_row_keys) != training_keys
                or training_index.index_hash != calculated_training_hash
            ):
                reasons.add("TRAINING_INDEX_INVALID")
        except (AttributeError, KeyError, TypeError, ValueError):
            reasons.add("TRAINING_INDEX_INVALID")

        try:
            calculated_validation_hash = fold_rows_hash(
                fold_id,
                validation_interval["cutoff_at"],
                transform_hash,
                validation_rows,
            )
            if validation_index_hash != calculated_validation_hash:
                reasons.add("VALIDATION_INDEX_INVALID")
        except (KeyError, TypeError, ValueError):
            reasons.add("VALIDATION_INDEX_INVALID")

        _labels_mature_before_cutoff(
            training_rows,
            training_interval.get("cutoff_at"),
            reason_prefix="TRAINING",
            reasons=reasons,
        )
        _labels_mature_before_cutoff(
            validation_rows,
            validation_interval.get("cutoff_at"),
            reason_prefix="VALIDATION",
            reasons=reasons,
        )

        qualification = json.loads(split.get("qualification_interval", "null"))
        if not isinstance(qualification, dict) or qualification.get("labels_released") is not False:
            reasons.add("QUALIFICATION_LABELS_RELEASED")
        else:
            qualification_keys = set(qualification.get("row_keys", ()))
            qualification_sessions = set(qualification.get("sessions", ()))
            if (
                qualification_keys.intersection(training_keys)
                or qualification_keys.intersection(validation_keys)
                or qualification_sessions.intersection(
                    {row.session_id for row in training_rows}
                    | {row.session_id for row in validation_rows}
                )
            ):
                reasons.add("QUALIFICATION_ROW_OVERLAP")
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        reasons.add("TRAINING_FOLD_INVALID")

    holdout_state = context.holdout_consumption_state
    if holdout_state is HoldoutConsumptionState.CONSUMED:
        reasons.add("QUALIFICATION_ALREADY_CONSUMED")
    elif holdout_state is HoldoutConsumptionState.REPEATED_ACCESS:
        reasons.add("QUALIFICATION_REPEAT_ACCESS")
    elif holdout_state is not HoldoutConsumptionState.NOT_CONSUMED:
        reasons.add("QUALIFICATION_STATE_UNKNOWN")

    if budget:
        try:
            effective_from = date.fromisoformat(budget["effective_from"])
            if assessed_instant is not None and effective_from > assessed_instant.date():
                reasons.add("BUDGET_NOT_YET_EFFECTIVE")
        except (KeyError, TypeError, ValueError):
            reasons.add("BUDGET_EFFECTIVE_DATE_INVALID")

        if context.budget_expires_at is None:
            reasons.add("BUDGET_EXPIRY_UNAVAILABLE")
        else:
            try:
                expiry = parse_utc_instant(context.budget_expires_at, "budget expiry")
                if assessed_instant is not None and expiry <= assessed_instant:
                    reasons.add("BUDGET_EXPIRED")
            except (TypeError, ValueError):
                reasons.add("BUDGET_EXPIRY_INVALID")

        if context.running_jobs is None or (
            type(context.running_jobs) is not int or context.running_jobs < 0
        ):
            reasons.add("RESOURCE_USAGE_UNAVAILABLE")
        elif context.running_jobs >= budget.get("max_concurrent_jobs", 0):
            reasons.add("CONCURRENCY_BUDGET_EXHAUSTED")

        if (
            context.spent_minor_units is None
            or type(context.spent_minor_units) is not int
            or context.spent_minor_units < 0
            or type(context.requested_cost_minor_units) is not int
            or context.requested_cost_minor_units < 0
        ):
            reasons.add("COST_USAGE_UNAVAILABLE")
        elif (
            budget.get("authorized_cost_minor_units", 0) > 0
            or context.requested_cost_minor_units > 0
        ):
            reasons.add("COST_NOT_AUTHORIZED")
        elif context.spent_minor_units + context.requested_cost_minor_units > budget.get(
            "authorized_cost_minor_units", 0
        ):
            reasons.add("COST_BUDGET_EXHAUSTED")

    available_storage = (
        context.storage_available if storage_available is None else storage_available
    )
    if available_storage is not True:
        reasons.add("STORAGE_UNAVAILABLE")

    return ResearchReadinessAssessment(
        status="RESEARCH_READY" if not reasons else "BLOCKED",
        reason_codes=tuple(sorted(reasons)),
        dataset_id=dataset.get("id"),
        split_id=split.get("id"),
        budget_id=budget.get("id"),
        assessed_at=assessed_at if isinstance(assessed_at, str) else None,
    )


def schedule_jobs(
    jobs: Sequence[QueueJob],
    *,
    capacity: int,
    active_jobs: int,
    active_research_jobs: int,
    research_concurrency_limit: int,
) -> QueueDecision:
    """Dispatch protected work FIFO before research, within hard slot limits."""
    counters = (capacity, active_jobs, active_research_jobs, research_concurrency_limit)
    if any(type(value) is not int or value < 0 for value in counters):
        raise ResearchReadinessError("queue capacities must be nonnegative integers")
    if active_research_jobs > active_jobs:
        raise ResearchReadinessError("active research jobs exceed all active jobs")
    if research_concurrency_limit < 1:
        raise ResearchReadinessError("research concurrency limit must be positive")
    if len({job.job_id for job in jobs}) != len(jobs):
        raise ResearchReadinessError("queue job IDs must be unique")

    def order_key(job: QueueJob) -> tuple[int, Any, int, str]:
        if not isinstance(job, QueueJob) or not isinstance(job.workload_class, WorkloadClass):
            raise ResearchReadinessError("queue entries require a known workload class")
        if not isinstance(job.job_id, str) or not job.job_id:
            raise ResearchReadinessError("queue job IDs must be nonempty strings")
        if type(job.priority) is not int or job.priority < 0:
            raise ResearchReadinessError("queue priority must be a nonnegative integer")
        try:
            enqueued = parse_utc_instant(job.enqueued_at, "queue enqueue time")
        except (TypeError, ValueError) as exc:
            raise ResearchReadinessError("queue enqueue time must be a UTC instant") from exc
        return (
            int(job.workload_class is WorkloadClass.RESEARCH),
            enqueued,
            -job.priority,
            job.job_id,
        )

    ordered = sorted(jobs, key=order_key)
    free_slots = max(0, capacity - active_jobs)
    scheduled: list[str] = []
    deferred: list[QueueDeferral] = []
    scheduled_research = 0
    unscheduled_protected = sum(job.workload_class is not WorkloadClass.RESEARCH for job in ordered)
    for job in ordered:
        if free_slots <= 0:
            reason = (
                "HIGHER_PRIORITY_WORK_PENDING"
                if job.workload_class is WorkloadClass.RESEARCH and unscheduled_protected
                else "NO_CAPACITY"
            )
            deferred.append(QueueDeferral(job_id=job.job_id, reason_code=reason))
            if job.workload_class is not WorkloadClass.RESEARCH:
                unscheduled_protected -= 1
            continue
        if job.workload_class is WorkloadClass.RESEARCH and (
            active_research_jobs + scheduled_research >= research_concurrency_limit
        ):
            deferred.append(
                QueueDeferral(
                    job_id=job.job_id,
                    reason_code="RESEARCH_CONCURRENCY_LIMIT",
                )
            )
            continue
        scheduled.append(job.job_id)
        free_slots -= 1
        if job.workload_class is WorkloadClass.RESEARCH:
            scheduled_research += 1
        else:
            unscheduled_protected -= 1

    body = {
        "scheduled_job_ids": scheduled,
        "deferred": [{"job_id": item.job_id, "reason_code": item.reason_code} for item in deferred],
    }
    decision_hash = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    return QueueDecision(
        scheduled_job_ids=tuple(scheduled),
        deferred=tuple(deferred),
        decision_hash=decision_hash,
    )
