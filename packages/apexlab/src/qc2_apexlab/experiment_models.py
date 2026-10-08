"""Immutable records and resource summaries for the ApexLab experiment ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ExperimentLedgerError(ValueError):
    """A ledger record is invalid, unauthorized, or outside its frozen budget."""


class TrialState(str, Enum):
    REGISTERED = "REGISTERED"
    RUNNING = "RUNNING"
    INTERRUPTED = "INTERRUPTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class HoldoutConsumptionState(str, Enum):
    NOT_CONSUMED = "NOT_CONSUMED"
    CONSUMED = "CONSUMED"
    REPEATED_ACCESS = "REPEATED_ACCESS"


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    """Nonnegative deltas; memory is the peak observed for this report."""

    elapsed_seconds: int = 0
    cpu_seconds: int = 0
    peak_memory_bytes: int = 0
    artifact_bytes: int = 0
    cost_minor_units: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "elapsed_seconds",
            "cpu_seconds",
            "peak_memory_bytes",
            "artifact_bytes",
            "cost_minor_units",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ExperimentLedgerError(f"{field_name} must be a nonnegative integer")

    def to_dict(self) -> dict[str, int]:
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "cpu_seconds": self.cpu_seconds,
            "peak_memory_bytes": self.peak_memory_bytes,
            "artifact_bytes": self.artifact_bytes,
            "cost_minor_units": self.cost_minor_units,
        }


@dataclass(frozen=True, slots=True)
class RegisteredBudget:
    budget_id: str
    content_hash: str
    contract_json: str

    @property
    def contract(self) -> dict[str, Any]:
        return json.loads(self.contract_json)


@dataclass(frozen=True, slots=True)
class RegisteredExperiment:
    experiment_id: str
    budget_id: str
    content_hash: str
    contract_json: str

    @property
    def contract(self) -> dict[str, Any]:
        return json.loads(self.contract_json)


@dataclass(frozen=True, slots=True)
class TrialEvent:
    event_id: str
    experiment_id: str
    sequence: int
    event_type: str
    attempt_number: int
    recorded_at: str
    usage: ResourceUsage
    previous_event_hash: str | None
    event_hash: str
    event_json: str

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.event_json)


@dataclass(frozen=True, slots=True)
class ComparisonRegistration:
    comparison_id: str
    experiment_ids: tuple[str, ...]
    registration_hash: str
    registration_json: str

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.registration_json)


@dataclass(frozen=True, slots=True)
class HoldoutAccessAttempt:
    dataset_id: str
    dataset_content_hash: str
    sequence: int
    experiment_id: str
    disposition: str
    receipt_id: str | None
    event_hash: str
    event_json: str

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.event_json)


@dataclass(frozen=True, slots=True)
class ResourceReport:
    budget_id: str
    registered_experiments: int
    max_experiments: int
    running_experiments: int
    status_counts: tuple[tuple[str, int], ...]
    elapsed_seconds: int
    cpu_seconds: int
    peak_memory_bytes: int
    artifact_bytes: int
    spent_minor_units: int
    authorized_cost_minor_units: int
    remaining_cost_minor_units: int
    currency: str
    over_budget_experiments: tuple[str, ...]

    def counts(self) -> dict[str, int]:
        return dict(self.status_counts)
