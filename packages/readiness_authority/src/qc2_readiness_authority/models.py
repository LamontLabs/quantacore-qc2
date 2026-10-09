"""Immutable, reason-coded readiness assessments and their wire projections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from qc2_contracts.runtime import validate_contract

_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)$")
_UUID7_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REASON_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_GATE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")


class ReadinessInputError(ValueError):
    """Raised when a readiness assessment has malformed or ambiguous inputs."""


class ReadinessStage(StrEnum):
    INGESTION_PREFLIGHT = "INGESTION_PREFLIGHT"
    SNAPSHOT_READY = "SNAPSHOT_READY"
    PREDICTION_READY = "PREDICTION_READY"


class GateState(StrEnum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class ReadinessStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


_CONTRACT_ACTION = {
    ReadinessStage.INGESTION_PREFLIGHT: "INGESTION_PREFLIGHT",
    ReadinessStage.SNAPSHOT_READY: "SNAPSHOT_READY",
    # The canonical ReadinessAssessment contract names this action PREDICT.
    ReadinessStage.PREDICTION_READY: "PREDICT",
}


def parse_utc_instant(value: str, field_name: str) -> datetime:
    """Parse an explicit UTC timestamp without inferring a local timezone."""
    if not isinstance(value, str) or not _UTC_PATTERN.fullmatch(value):
        raise ReadinessInputError(f"{field_name} must be an explicit UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReadinessInputError(f"{field_name} must be a valid UTC instant") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ReadinessInputError(f"{field_name} must use UTC")
    return parsed.astimezone(timezone.utc)


def _unique_strings(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    result = tuple(values)
    if any(not isinstance(value, str) or not value for value in result):
        raise ReadinessInputError(f"{field_name} must contain non-empty strings")
    if len(result) != len(set(result)):
        raise ReadinessInputError(f"{field_name} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class ReadinessContext:
    evaluated_at: str
    input_generation: int

    def __post_init__(self) -> None:
        parse_utc_instant(self.evaluated_at, "evaluated_at")
        if (
            isinstance(self.input_generation, bool)
            or not isinstance(self.input_generation, int)
            or self.input_generation < 1
        ):
            raise ReadinessInputError("input_generation must be a positive integer")


@dataclass(frozen=True, slots=True)
class SourceReference:
    target_schema_name: str
    target_id: str
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_schema_name, str) or not self.target_schema_name:
            raise ReadinessInputError("target_schema_name is required")
        if not _UUID7_PATTERN.fullmatch(self.target_id):
            raise ReadinessInputError("source target_id must be UUIDv7")
        if self.content_hash is not None and not _SHA256_PATTERN.fullmatch(self.content_hash):
            raise ReadinessInputError("source content_hash must be lowercase SHA-256")

    def as_json(self) -> dict[str, str]:
        result = {
            "target_schema_name": self.target_schema_name,
            "target_id": self.target_id,
        }
        if self.content_hash is not None:
            result["content_hash"] = self.content_hash
        return result

    @property
    def identity(self) -> tuple[str, str, str]:
        return (
            self.target_schema_name,
            self.target_id,
            self.content_hash or "",
        )


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    """One authority observation bound to a version, generation and freshness window."""

    status: GateState
    observed_at: str | None = None
    freshness_deadline: str | None = None
    version: str | None = None
    source_refs: tuple[SourceReference, ...] = ()
    reason_codes: tuple[str, ...] = ()
    input_generation: int | None = None

    def __post_init__(self) -> None:
        try:
            status = GateState(self.status)
        except ValueError as exc:
            raise ReadinessInputError("unsupported evidence status") from exc
        if (self.observed_at is None) != (self.freshness_deadline is None):
            raise ReadinessInputError(
                "observed_at and freshness_deadline must be supplied together"
            )
        if self.observed_at is not None:
            observed = parse_utc_instant(self.observed_at, "observed_at")
            deadline = parse_utc_instant(self.freshness_deadline, "freshness_deadline")
            if deadline < observed:
                raise ReadinessInputError("freshness_deadline precedes observed_at")
        if self.version is not None and (
            not isinstance(self.version, str) or not self.version.strip()
        ):
            raise ReadinessInputError("version must be a non-empty string when supplied")
        refs = tuple(self.source_refs)
        if any(not isinstance(ref, SourceReference) for ref in refs):
            raise ReadinessInputError("source_refs must contain SourceReference values")
        if len(refs) != len(set(refs)):
            raise ReadinessInputError("source_refs must not contain duplicates")
        reasons = _unique_strings(self.reason_codes, "reason_codes")
        if any(not _REASON_PATTERN.fullmatch(reason) for reason in reasons):
            raise ReadinessInputError("reason_codes must be stable uppercase identifiers")
        if self.input_generation is not None and (
            isinstance(self.input_generation, bool)
            or not isinstance(self.input_generation, int)
            or self.input_generation < 1
        ):
            raise ReadinessInputError("input_generation must be positive when supplied")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "source_refs", refs)
        object.__setattr__(self, "reason_codes", reasons)


@dataclass(frozen=True, slots=True)
class DeadlineAssessment:
    deadline_id: str
    deadline_at: str | None
    estimated_at: str | None
    status: GateState
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _GATE_PATTERN.fullmatch(self.deadline_id):
            raise ReadinessInputError("deadline_id must be a stable lowercase identifier")
        try:
            status = GateState(self.status)
        except ValueError as exc:
            raise ReadinessInputError("unsupported deadline status") from exc
        if (self.deadline_at is None) != (self.estimated_at is None):
            raise ReadinessInputError("deadline and estimate must be supplied together")
        if self.deadline_at is not None:
            parse_utc_instant(self.deadline_at, "deadline_at")
            parse_utc_instant(self.estimated_at, "estimated_at")
        reasons = _unique_strings(self.reason_codes, "deadline reason_codes")
        if any(not _REASON_PATTERN.fullmatch(reason) for reason in reasons):
            raise ReadinessInputError("deadline reason_codes must be uppercase identifiers")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_codes", reasons)

    def as_projection(self) -> dict[str, Any]:
        return {
            "deadline_id": self.deadline_id,
            "deadline_at": self.deadline_at,
            "estimated_at": self.estimated_at,
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class GateAssessment:
    gate_id: str
    status: GateState
    reason_codes: tuple[str, ...]
    evaluated_at: str
    freshness_deadline: str
    source_refs: tuple[SourceReference, ...] = ()
    observed_versions: tuple[str, ...] = ()
    deadline_assessments: tuple[DeadlineAssessment, ...] = ()

    def __post_init__(self) -> None:
        if not _GATE_PATTERN.fullmatch(self.gate_id):
            raise ReadinessInputError("gate_id must be a stable lowercase identifier")
        try:
            status = GateState(self.status)
        except ValueError as exc:
            raise ReadinessInputError("unsupported gate status") from exc
        evaluated = parse_utc_instant(self.evaluated_at, "gate evaluated_at")
        deadline = parse_utc_instant(self.freshness_deadline, "gate freshness_deadline")
        if deadline < evaluated:
            raise ReadinessInputError("gate freshness_deadline precedes evaluated_at")
        reasons = _unique_strings(self.reason_codes, "gate reason_codes")
        if any(not _REASON_PATTERN.fullmatch(reason) for reason in reasons):
            raise ReadinessInputError("gate reason_codes must be uppercase identifiers")
        refs = tuple(self.source_refs)
        if any(not isinstance(ref, SourceReference) for ref in refs):
            raise ReadinessInputError("gate source_refs must be SourceReference values")
        if len(refs) != len(set(refs)):
            raise ReadinessInputError("gate source_refs must not contain duplicates")
        versions = _unique_strings(self.observed_versions, "observed_versions")
        deadline_assessments = tuple(self.deadline_assessments)
        if any(not isinstance(item, DeadlineAssessment) for item in deadline_assessments):
            raise ReadinessInputError("deadline_assessments must contain DeadlineAssessment values")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(self, "source_refs", refs)
        object.__setattr__(self, "observed_versions", versions)
        object.__setattr__(self, "deadline_assessments", deadline_assessments)

    def as_projection(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
            "evaluated_at": self.evaluated_at,
            "freshness_deadline": self.freshness_deadline,
            "observed_versions": list(self.observed_versions),
            "source_refs": [ref.as_json() for ref in self.source_refs],
            "deadline_assessments": [item.as_projection() for item in self.deadline_assessments],
        }


@dataclass(frozen=True, slots=True)
class StageAssessment:
    stage: ReadinessStage
    context: ReadinessContext
    gate_results: tuple[GateAssessment, ...]

    def __post_init__(self) -> None:
        try:
            stage = ReadinessStage(self.stage)
        except ValueError as exc:
            raise ReadinessInputError("unsupported readiness stage") from exc
        gates = tuple(self.gate_results)
        if not gates or any(not isinstance(gate, GateAssessment) for gate in gates):
            raise ReadinessInputError("a stage assessment must contain gate results")
        if len({gate.gate_id for gate in gates}) != len(gates):
            raise ReadinessInputError("stage assessment contains duplicate gates")
        object.__setattr__(self, "stage", stage)
        object.__setattr__(self, "gate_results", gates)

    @property
    def action(self) -> str:
        return _CONTRACT_ACTION[self.stage]

    @property
    def status(self) -> ReadinessStatus:
        if any(gate.status is GateState.BLOCK for gate in self.gate_results):
            return ReadinessStatus.BLOCKED
        if any(
            gate.status in {GateState.UNKNOWN, GateState.UNAVAILABLE} for gate in self.gate_results
        ):
            return ReadinessStatus.UNKNOWN
        return ReadinessStatus.READY

    @property
    def freshness_deadline(self) -> str:
        return min(
            (gate.freshness_deadline for gate in self.gate_results),
            key=lambda value: parse_utc_instant(value, "freshness_deadline"),
        )

    @property
    def reason_codes(self) -> tuple[str, ...]:
        ordered: list[str] = []
        for gate in self.gate_results:
            if gate.status is not GateState.PASS:
                for reason in gate.reason_codes:
                    if reason not in ordered:
                        ordered.append(reason)
        return tuple(ordered)

    def as_projection_payload(self) -> dict[str, Any]:
        """Build the richer reason/version/deadline projection used by API and mobile."""
        return {
            "stage": self.stage.value,
            "action": self.action,
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
            "input_generation": self.context.input_generation,
            "evaluated_at": self.context.evaluated_at,
            "freshness_deadline": self.freshness_deadline,
            "gate_results": [gate.as_projection() for gate in self.gate_results],
        }

    def as_contract_payload(
        self,
        *,
        record_id: str,
        evidence_class: str,
        environment_namespace: str,
    ) -> dict[str, Any]:
        """Materialize the pinned, Android-visible ReadinessAssessment contract."""
        refs = {ref.identity: ref for gate in self.gate_results for ref in gate.source_refs}
        payload = {
            "schema_name": "qc2.time_operation.ReadinessAssessment.v1",
            "schema_version": "1.0",
            "id": record_id,
            "created_at": self.context.evaluated_at,
            "owning_authority": "safety",
            "evidence_class": evidence_class,
            "environment_namespace": environment_namespace,
            "source_refs": [refs[key].as_json() for key in sorted(refs)],
            "action": self.action,
            "status": self.status.value,
            "gate_results": [
                {
                    "gate_id": gate.gate_id,
                    "status": gate.status.value,
                    "reason_codes": list(gate.reason_codes),
                    "evaluated_at": gate.evaluated_at,
                    "source_refs": [ref.as_json() for ref in gate.source_refs],
                }
                for gate in self.gate_results
            ],
            "input_generation": self.context.input_generation,
            "freshness_deadline": self.freshness_deadline,
        }
        validate_contract("ReadinessAssessment", payload)
        return payload
