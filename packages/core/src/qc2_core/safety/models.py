"""Immutable inputs and outputs for action-scoped safety evaluation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Any

_UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)$"
)
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
_REASON_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SafetyViolation(ValueError):
    """Raised when safety input or policy is malformed or ambiguous."""


class SafetyAction(StrEnum):
    PREDICT = "PREDICT"
    NEW_ENTRY = "NEW_ENTRY"
    EXIT_POSITION = "EXIT_POSITION"
    CANCEL_ENTRY = "CANCEL_ENTRY"
    PROMOTE = "PROMOTE"


class GateStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class ReadinessStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class WarningPolicy(StrEnum):
    BLOCK = "BLOCK"
    ALLOW_WITH_EVIDENCE = "ALLOW_WITH_EVIDENCE"
    NOT_ALLOWED = "NOT_ALLOWED"


class CapabilityDomain(StrEnum):
    TIME = "TIME"
    DATA = "DATA"
    MODEL = "MODEL"
    REGISTRY = "REGISTRY"
    CONFIGURATION = "CONFIGURATION"
    EVIDENCE = "EVIDENCE"
    BROKER = "BROKER"
    RECONCILIATION = "RECONCILIATION"
    IDEMPOTENCY = "IDEMPOTENCY"
    IDENTITY = "IDENTITY"
    OWNER_AUTHORITY = "OWNER_AUTHORITY"
    STRATEGY = "STRATEGY"
    RESERVATION = "RESERVATION"
    PREDICTION_SEAL = "PREDICTION_SEAL"
    EPOCH = "EPOCH"


def parse_utc_instant(value: str, field_name: str) -> datetime:
    """Parse an explicit UTC timestamp; never infer a local timezone."""
    if not isinstance(value, str) or not _UTC_PATTERN.fullmatch(value):
        raise SafetyViolation(f"{field_name} must be an explicit UTC instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SafetyViolation(f"{field_name} must be a valid UTC instant") from exc
    if parsed.utcoffset() != timedelta(0):
        raise SafetyViolation(f"{field_name} must use UTC")
    return parsed.astimezone(timezone.utc)


def _freeze_source_refs(
    values: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise SafetyViolation("source_refs must be a sequence of reference objects")
    frozen: list[Mapping[str, Any]] = []
    for value in values:
        if not isinstance(value, Mapping) or any(
            not isinstance(key, str) for key in value
        ):
            raise SafetyViolation("source_refs must contain string-keyed objects")
        frozen.append(_freeze_json_object(value))
    return tuple(frozen)


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise SafetyViolation("source_refs must contain string-keyed objects")
        return _freeze_json_object(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    raise SafetyViolation("source_refs must contain finite JSON values")


def _freeze_json_object(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {key: _freeze_json_value(item) for key, item in value.items()}
    )


def _string_tuple(
    values: Sequence[str], field_name: str, pattern: re.Pattern[str] | None = None
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise SafetyViolation(f"{field_name} must be a sequence of strings")
    result = tuple(values)
    if any(not isinstance(item, str) or not item for item in result):
        raise SafetyViolation(f"{field_name} must contain non-empty strings")
    if pattern and any(not pattern.fullmatch(item) for item in result):
        raise SafetyViolation(f"{field_name} contains an invalid value")
    if len(result) != len(set(result)):
        raise SafetyViolation(f"{field_name} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class SafetyGatePolicy:
    """One immutable, versioned rule with explicit evidence and warning policy."""

    gate_id: str
    action: SafetyAction
    domain: CapabilityDomain
    rule: str
    required_evidence: tuple[str, ...]
    warning_policy: WarningPolicy = WarningPolicy.NOT_ALLOWED
    version: int = 1

    @property
    def protocol_key(self) -> str:
        return f"{self.action.value.lower()}_{self.gate_id}"

    def __post_init__(self) -> None:
        try:
            action = SafetyAction(self.action)
            domain = CapabilityDomain(self.domain)
            warning_policy = WarningPolicy(self.warning_policy)
        except ValueError as exc:
            raise SafetyViolation("gate policy contains an unsupported enum value") from exc
        if not _IDENTIFIER_PATTERN.fullmatch(self.gate_id):
            raise SafetyViolation("gate_id must be a lowercase stable identifier")
        if not isinstance(self.rule, str) or not self.rule.strip():
            raise SafetyViolation("gate policy rule is required")
        evidence = _string_tuple(
            self.required_evidence, "required_evidence", _IDENTIFIER_PATTERN
        )
        if not evidence:
            raise SafetyViolation("gate policy must name its required evidence")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise SafetyViolation("gate policy version must be a positive integer")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "warning_policy", warning_policy)
        object.__setattr__(self, "required_evidence", evidence)


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    """The complete set of gates for one action, with no cross-action inheritance."""

    action: SafetyAction
    gates: tuple[SafetyGatePolicy, ...]

    def __post_init__(self) -> None:
        try:
            action = SafetyAction(self.action)
        except ValueError as exc:
            raise SafetyViolation("action policy names an unsupported action") from exc
        gates = tuple(self.gates)
        if not gates or any(not isinstance(gate, SafetyGatePolicy) for gate in gates):
            raise SafetyViolation("action policy must contain safety gate policies")
        if any(gate.action is not action for gate in gates):
            raise SafetyViolation("action policy contains a gate for another action")
        gate_ids = tuple(gate.gate_id for gate in gates)
        if len(gate_ids) != len(set(gate_ids)):
            raise SafetyViolation("action policy contains duplicate gate IDs")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "gates", gates)


@dataclass(frozen=True, slots=True)
class GateObservation:
    """A capability observation bound to an action, generation, and freshness window."""

    gate_id: str
    action: SafetyAction
    domain: CapabilityDomain
    status: GateStatus
    evaluated_at: str
    freshness_deadline: str
    input_generation: int
    evidence_keys: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    source_refs: tuple[Mapping[str, Any], ...] = ()
    observed_versions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            action = SafetyAction(self.action)
            domain = CapabilityDomain(self.domain)
            status = GateStatus(self.status)
        except ValueError as exc:
            raise SafetyViolation("gate observation contains an unsupported enum value") from exc
        if not _IDENTIFIER_PATTERN.fullmatch(self.gate_id):
            raise SafetyViolation("gate observation ID must be a lowercase identifier")
        observed_at = parse_utc_instant(self.evaluated_at, "evaluated_at")
        deadline = parse_utc_instant(self.freshness_deadline, "freshness_deadline")
        if deadline < observed_at:
            raise SafetyViolation("freshness_deadline cannot precede evaluated_at")
        if (
            isinstance(self.input_generation, bool)
            or not isinstance(self.input_generation, int)
            or self.input_generation < 0
        ):
            raise SafetyViolation("input_generation must be a nonnegative integer")
        evidence_keys = _string_tuple(
            self.evidence_keys, "evidence_keys", _IDENTIFIER_PATTERN
        )
        reason_codes = _string_tuple(
            self.reason_codes, "reason_codes", _REASON_PATTERN
        )
        observed_versions = _string_tuple(
            self.observed_versions, "observed_versions"
        )
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "evidence_keys", evidence_keys)
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "source_refs", _freeze_source_refs(self.source_refs))
        object.__setattr__(self, "observed_versions", observed_versions)


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    """Action-specific normalized result used by both readiness and protocol receipts."""

    gate_id: str
    action: SafetyAction
    status: GateStatus
    reason_codes: tuple[str, ...]
    evaluated_at: str
    freshness_deadline: str
    source_refs: tuple[Mapping[str, Any], ...]
    observed_versions: tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            action = SafetyAction(self.action)
            status = GateStatus(self.status)
        except ValueError as exc:
            raise SafetyViolation("gate evaluation contains an unsupported enum value") from exc
        if not _IDENTIFIER_PATTERN.fullmatch(self.gate_id):
            raise SafetyViolation("gate evaluation ID must be a lowercase identifier")
        observed_at = parse_utc_instant(self.evaluated_at, "evaluated_at")
        deadline = parse_utc_instant(self.freshness_deadline, "freshness_deadline")
        if deadline < observed_at:
            raise SafetyViolation("freshness_deadline cannot precede evaluated_at")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "reason_codes",
            _string_tuple(self.reason_codes, "reason_codes", _REASON_PATTERN),
        )
        object.__setattr__(
            self, "source_refs", _freeze_source_refs(self.source_refs)
        )
        object.__setattr__(
            self,
            "observed_versions",
            _string_tuple(self.observed_versions, "observed_versions"),
        )


@dataclass(frozen=True, slots=True)
class ActionReadiness:
    """Immutable result for exactly one action and one coherent input generation."""

    action: SafetyAction
    status: ReadinessStatus
    gate_results: tuple[GateEvaluation, ...]
    input_generation: int
    evaluated_at: str
    freshness_deadline: str
    allowed_warning_gate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            action = SafetyAction(self.action)
            status = ReadinessStatus(self.status)
        except ValueError as exc:
            raise SafetyViolation("readiness result contains an unsupported enum value") from exc
        results = tuple(self.gate_results)
        if not results or any(not isinstance(item, GateEvaluation) for item in results):
            raise SafetyViolation("readiness result must include gate evaluations")
        if any(item.action is not action for item in results):
            raise SafetyViolation("readiness result contains another action's gate")
        gate_ids = tuple(item.gate_id for item in results)
        if len(gate_ids) != len(set(gate_ids)):
            raise SafetyViolation("readiness result contains duplicate gate IDs")
        allowed_warnings = _string_tuple(
            self.allowed_warning_gate_ids,
            "allowed_warning_gate_ids",
            _IDENTIFIER_PATTERN,
        )
        if not set(allowed_warnings) <= set(gate_ids):
            raise SafetyViolation("warning policy names a gate outside this readiness result")
        if (
            isinstance(self.input_generation, bool)
            or not isinstance(self.input_generation, int)
            or self.input_generation < 0
        ):
            raise SafetyViolation("input_generation must be a nonnegative integer")
        parse_utc_instant(self.evaluated_at, "evaluated_at")
        freshness_deadline = parse_utc_instant(
            self.freshness_deadline, "freshness_deadline"
        )
        expected_deadline = min(
            parse_utc_instant(item.freshness_deadline, "gate freshness_deadline")
            for item in results
        )
        if freshness_deadline != expected_deadline:
            raise SafetyViolation(
                "readiness freshness deadline does not match its gate results"
            )
        if any(item.status is GateStatus.BLOCK for item in results):
            expected_status = ReadinessStatus.BLOCKED
        elif any(
            item.status in {GateStatus.UNKNOWN, GateStatus.UNAVAILABLE}
            for item in results
        ):
            expected_status = ReadinessStatus.UNKNOWN
        elif any(item.status is GateStatus.WARN for item in results):
            expected_status = (
                ReadinessStatus.DEGRADED
                if all(
                    item.status is not GateStatus.WARN
                    or item.gate_id in allowed_warnings
                    for item in results
                )
                else ReadinessStatus.BLOCKED
            )
        else:
            expected_status = ReadinessStatus.READY
        if status is not expected_status:
            raise SafetyViolation(
                "readiness status does not match its action-scoped gate results"
            )
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "gate_results", results)
        object.__setattr__(self, "allowed_warning_gate_ids", allowed_warnings)

    @property
    def permits_action(self) -> bool:
        """Only fully ready or explicitly policy-degraded actions may proceed."""
        return self.status in {ReadinessStatus.READY, ReadinessStatus.DEGRADED}


def is_sha256(value: str) -> bool:
    """Return whether a caller-supplied implementation digest is lowercase SHA-256."""
    return isinstance(value, str) and bool(_SHA256_PATTERN.fullmatch(value))
