"""Immutable, typed inputs and expressions for the QC2 Runner Protocol authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import Enum
from typing import Any

from .models import ContractRef, FeatureInputError, as_date, as_decimal, as_utc, require_sha256

RUNNER_PROTOCOL_DEFINITION_SCHEMA = "qc2.scientific_definitions.RunnerProtocolDefinition.v1"
RUNNER_PROTOCOL_REGISTRY_SCHEMA = "qc2.scientific_definitions.RunnerProtocolRegistry.v1"
RUNNER_PROTOCOL_RESULT_SCHEMA = "qc2.scientific_definitions.RunnerProtocolResult.v1"

_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
_DECIMAL_QUANTUM = Decimal("0.000000000001")
_DIRECTIONS = frozenset({"POSITIVE", "NEGATIVE", "NEUTRAL", "UNKNOWN"})
_EVIDENCE_CLASSES = frozenset(
    {"SYNTHETIC_FIXTURE", "HISTORICAL_RECONSTRUCTED", "FORWARD_OPERATIONAL", "FORWARD_SEALED"}
)
_ENVIRONMENTS = frozenset({"development", "test", "research", "production"})
_MISSINGNESS = frozenset({"PRESENT", "MISSING", "UNKNOWN", "NOT_APPLICABLE"})
_RESULT_STATES = frozenset({"PASS", "BLOCK", "OBSERVE", "UNKNOWN", "UNAVAILABLE"})
_EXPRESSION_OPS = frozenset(
    {
        "input",
        "parameter",
        "decimal",
        "abs",
        "not",
        "add",
        "subtract",
        "multiply",
        "divide",
        "gt",
        "gte",
        "lt",
        "lte",
        "eq",
        "and",
        "or",
    }
)
_BINARY_OPS = frozenset(
    {"add", "subtract", "multiply", "divide", "gt", "gte", "lt", "lte", "eq"}
)


class RunnerProtocolError(FeatureInputError):
    """A Runner Protocol definition, input, or evaluation violates its contract."""


class ProtocolActivationDenied(RunnerProtocolError):
    """QC2-017 does not grant production activation without external calibration and owner evidence."""


class RunnerProtocolState(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    OBSERVE = "OBSERVE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


def normalize_protocol_decimal(value: Decimal | str | int) -> Decimal:
    """Normalize an exact decimal to the persisted twelve-place protocol precision."""
    parsed = as_decimal(value, "protocol decimal")
    if parsed.copy_abs() >= Decimal("1e36"):
        raise RunnerProtocolError("protocol decimal magnitude exceeds the supported range")
    try:
        with localcontext() as context:
            context.prec = 64
            result = parsed.quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:
        raise RunnerProtocolError("protocol decimal cannot be represented at twelve places") from exc
    return Decimal(0) if result == 0 else result


def protocol_decimal_text(value: Decimal | str | int) -> str:
    normalized = normalize_protocol_decimal(value)
    return f"{normalized:.12f}"


def utc_contract_text(value: datetime | str) -> str:
    parsed = as_utc(value, "protocol UTC instant")
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ProtocolExpression:
    """A small declarative expression node; it cannot hold Python callables or code."""

    op: str
    args: tuple[Any, ...]

    def __post_init__(self) -> None:
        if self.op not in _EXPRESSION_OPS:
            raise RunnerProtocolError(f"unsupported protocol expression operator: {self.op!r}")
        object.__setattr__(self, "args", tuple(self.args))

        if self.op in {"input", "parameter"}:
            if len(self.args) != 1 or not isinstance(self.args[0], str) or not _SLUG.fullmatch(
                self.args[0]
            ):
                raise RunnerProtocolError(f"{self.op} expression requires one lowercase key")
        elif self.op == "decimal":
            if len(self.args) != 1:
                raise RunnerProtocolError("decimal expression requires one value")
            object.__setattr__(self, "args", (normalize_protocol_decimal(self.args[0]),))
        elif self.op in {"abs", "not"}:
            if len(self.args) != 1 or not isinstance(self.args[0], ProtocolExpression):
                raise RunnerProtocolError(f"{self.op} expression requires one child expression")
        elif self.op in _BINARY_OPS:
            if len(self.args) != 2 or not all(
                isinstance(item, ProtocolExpression) for item in self.args
            ):
                raise RunnerProtocolError(f"{self.op} expression requires two child expressions")
        elif self.op in {"and", "or"}:
            if not self.args or not all(
                isinstance(item, ProtocolExpression) for item in self.args
            ):
                raise RunnerProtocolError(f"{self.op} expression requires child expressions")


def input_value(key: str) -> ProtocolExpression:
    return ProtocolExpression("input", (key,))


def parameter_value(key: str) -> ProtocolExpression:
    return ProtocolExpression("parameter", (key,))


def decimal_value(value: Decimal | str | int) -> ProtocolExpression:
    return ProtocolExpression("decimal", (value,))


def protocol_operation(op: str, *args: ProtocolExpression) -> ProtocolExpression:
    return ProtocolExpression(op, tuple(args))


def _expression_document(expression: ProtocolExpression, *, max_nodes: int = 128) -> dict[str, Any]:
    nodes = 0

    def visit(node: ProtocolExpression, depth: int) -> dict[str, Any]:
        nonlocal nodes
        nodes += 1
        if depth > 32 or nodes > max_nodes:
            raise RunnerProtocolError("protocol expression exceeds its depth or node budget")
        if node.op in {"input", "parameter"}:
            return {"op": node.op, "name": node.args[0]}
        if node.op == "decimal":
            return {"op": node.op, "value": protocol_decimal_text(node.args[0])}
        if node.op in {"abs", "not"}:
            return {"op": node.op, "value": visit(node.args[0], depth + 1)}
        if node.op in {"and", "or"}:
            return {"op": node.op, "items": [visit(item, depth + 1) for item in node.args]}
        return {
            "op": node.op,
            "left": visit(node.args[0], depth + 1),
            "right": visit(node.args[1], depth + 1),
        }

    return visit(expression, 1)


def _expression_result_type(
    expression: ProtocolExpression, input_keys: set[str], parameter_keys: set[str]
) -> str:
    op = expression.op
    if op == "input":
        if expression.args[0] not in input_keys:
            raise RunnerProtocolError(f"expression references undeclared input {expression.args[0]!r}")
        return "decimal"
    if op == "parameter":
        if expression.args[0] not in parameter_keys:
            raise RunnerProtocolError(
                f"expression references undeclared parameter {expression.args[0]!r}"
            )
        return "decimal"
    if op == "decimal":
        return "decimal"
    if op == "abs":
        if _expression_result_type(expression.args[0], input_keys, parameter_keys) != "decimal":
            raise RunnerProtocolError("abs requires a decimal expression")
        return "decimal"
    if op == "not":
        if _expression_result_type(expression.args[0], input_keys, parameter_keys) != "boolean":
            raise RunnerProtocolError("not requires a boolean expression")
        return "boolean"
    if op in {"and", "or"}:
        if any(
            _expression_result_type(item, input_keys, parameter_keys) != "boolean"
            for item in expression.args
        ):
            raise RunnerProtocolError(f"{op} requires boolean expressions")
        return "boolean"

    left = _expression_result_type(expression.args[0], input_keys, parameter_keys)
    right = _expression_result_type(expression.args[1], input_keys, parameter_keys)
    if op in {"add", "subtract", "multiply", "divide"}:
        if left != "decimal" or right != "decimal":
            raise RunnerProtocolError(f"{op} requires decimal expressions")
        return "decimal"
    if op in {"gt", "gte", "lt", "lte", "eq"}:
        if left != "decimal" or right != "decimal":
            raise RunnerProtocolError(f"{op} requires decimal expressions")
        return "boolean"
    raise RunnerProtocolError(f"unsupported protocol expression operator: {op!r}")


@dataclass(frozen=True, slots=True)
class ProtocolInputRequirement:
    key: str
    unit: str
    source_ref: ContractRef

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.key):
            raise RunnerProtocolError("protocol input key must be a lowercase slug")
        if not isinstance(self.unit, str) or not self.unit.strip() or len(self.unit) > 96:
            raise RunnerProtocolError("protocol input unit is required and must be concise")
        if self.source_ref.target_schema_name not in {
            "qc2.scientific_definitions.FeatureSnapshot.v1",
            "qc2.identity_market.DailyBar.v1",
        }:
            raise RunnerProtocolError("runtime protocol inputs must bind a FeatureSnapshot or DailyBar")


@dataclass(frozen=True, slots=True)
class ProtocolEvidenceValue:
    key: str
    value: Decimal | str | int | None
    unit: str
    uncertainty: Decimal | str | int | None
    missingness: str
    source_ref: ContractRef
    known_at: datetime | str | None

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.key):
            raise RunnerProtocolError("evidence key must be a lowercase slug")
        if not isinstance(self.unit, str) or not self.unit.strip() or len(self.unit) > 96:
            raise RunnerProtocolError("evidence unit is required and must be concise")
        if self.missingness not in _MISSINGNESS:
            raise RunnerProtocolError("evidence missingness is not a supported state")
        if self.missingness == "PRESENT":
            if self.value is None or self.known_at is None:
                raise RunnerProtocolError("present evidence requires a value and known_at instant")
            object.__setattr__(self, "value", normalize_protocol_decimal(self.value))
            object.__setattr__(self, "known_at", as_utc(self.known_at, "evidence known_at"))
        elif self.value is not None:
            raise RunnerProtocolError("non-present evidence cannot carry a numeric value")
        if self.uncertainty is not None:
            object.__setattr__(self, "uncertainty", normalize_protocol_decimal(self.uncertainty))


@dataclass(frozen=True, slots=True)
class ProtocolInputBundle:
    session_id: date | str
    instrument_ref: ContractRef
    cutoff: datetime | str
    values: tuple[ProtocolEvidenceValue, ...]
    uncertainty: Decimal | str | int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", as_date(self.session_id, "protocol session_id"))
        object.__setattr__(self, "cutoff", as_utc(self.cutoff, "protocol cutoff"))
        if self.instrument_ref.target_schema_name != "qc2.identity_market.Instrument.v1":
            raise RunnerProtocolError("protocol input instrument_ref must target Instrument")
        values = tuple(sorted(self.values, key=lambda item: item.key))
        if len({item.key for item in values}) != len(values):
            raise RunnerProtocolError("protocol evidence keys must be unique")
        object.__setattr__(self, "values", values)
        if self.uncertainty is not None:
            object.__setattr__(self, "uncertainty", normalize_protocol_decimal(self.uncertainty))


@dataclass(frozen=True, slots=True)
class RunnerProtocolSpec:
    protocol_namespace: str
    protocol_id: str
    version: int
    hypothesis: str
    direction: str
    regime: str
    input_requirements: tuple[ProtocolInputRequirement, ...]
    parameter_refs: tuple[ContractRef, ...]
    parameters: tuple[tuple[str, Decimal | str | int], ...]
    expression: ProtocolExpression
    on_match: RunnerProtocolState
    on_non_match: RunnerProtocolState
    evidence_class: str
    environment_namespace: str
    max_steps: int
    source_refs: tuple[ContractRef, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("protocol_namespace", "protocol_id", "regime"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not _SLUG.fullmatch(value):
                raise RunnerProtocolError(f"{field_name} must be a lowercase slug")
        if type(self.version) is not int or self.version < 1:
            raise RunnerProtocolError("protocol version must be a positive integer")
        if not isinstance(self.hypothesis, str) or not self.hypothesis.strip():
            raise RunnerProtocolError("protocol hypothesis is required")
        if self.direction not in _DIRECTIONS:
            raise RunnerProtocolError("protocol direction is not supported")
        if self.evidence_class not in _EVIDENCE_CLASSES:
            raise RunnerProtocolError("protocol evidence_class is not supported")
        if self.environment_namespace not in _ENVIRONMENTS:
            raise RunnerProtocolError("protocol environment_namespace is not supported")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 128:
            raise RunnerProtocolError("protocol max_steps must be between 1 and 128")
        if not isinstance(self.expression, ProtocolExpression):
            raise RunnerProtocolError("protocol expression must use the declarative expression API")

        requirements = tuple(sorted(self.input_requirements, key=lambda item: item.key))
        if not requirements or len({item.key for item in requirements}) != len(requirements):
            raise RunnerProtocolError("protocol inputs must be nonempty and uniquely named")
        object.__setattr__(self, "input_requirements", requirements)

        parameters = tuple(
            sorted((key, normalize_protocol_decimal(value)) for key, value in self.parameters)
        )
        if len({key for key, _ in parameters}) != len(parameters):
            raise RunnerProtocolError("protocol parameter keys must be unique")
        if any(not _SLUG.fullmatch(key) for key, _ in parameters):
            raise RunnerProtocolError("protocol parameter keys must be lowercase slugs")
        object.__setattr__(self, "parameters", parameters)

        parameter_refs = tuple(sorted(self.parameter_refs, key=_reference_sort_key))
        if any(
            item.target_schema_name != "qc2.integrity_build.ConfigurationManifest.v1"
            for item in parameter_refs
        ):
            raise RunnerProtocolError("protocol parameter_refs must target ConfigurationManifest")
        object.__setattr__(self, "parameter_refs", parameter_refs)

        source_refs = tuple(sorted(self.source_refs, key=_reference_sort_key))
        object.__setattr__(self, "source_refs", source_refs)

        for field_name in ("on_match", "on_non_match"):
            try:
                value = RunnerProtocolState(getattr(self, field_name))
            except ValueError as exc:
                raise RunnerProtocolError(f"{field_name} is not a Runner Protocol result") from exc
            if value not in {RunnerProtocolState.PASS, RunnerProtocolState.BLOCK, RunnerProtocolState.OBSERVE}:
                raise RunnerProtocolError(f"{field_name} must explicitly be PASS, BLOCK, or OBSERVE")
            object.__setattr__(self, field_name, value)

        input_keys = {item.key for item in requirements}
        parameter_keys = {key for key, _ in parameters}
        _expression_document(self.expression)
        if _expression_result_type(self.expression, input_keys, parameter_keys) != "boolean":
            raise RunnerProtocolError("protocol expression must return a boolean hypothesis result")

    @property
    def protocol_key(self) -> str:
        return f"{self.protocol_namespace}:{self.protocol_id}:v{self.version}"

    @property
    def implementation_hash(self) -> str:
        document = {
            "protocol_namespace": self.protocol_namespace,
            "protocol_id": self.protocol_id,
            "version": self.version,
            "hypothesis": self.hypothesis,
            "direction": self.direction,
            "regime": self.regime,
            "inputs": [{"key": item.key, "unit": item.unit} for item in self.input_requirements],
            "expression": _expression_document(self.expression),
            "on_match": self.on_match.value,
            "on_non_match": self.on_non_match.value,
            "parameters": [
                [key, protocol_decimal_text(value)] for key, value in self.parameters
            ],
            "parameter_refs": [
                item.to_payload() for item in sorted(self.parameter_refs, key=_reference_sort_key)
            ],
        }
        return hashlib.sha256(_canonical_json(document)).hexdigest()

    @property
    def parameter_hash(self) -> str:
        document = {
            "parameters": [[key, protocol_decimal_text(value)] for key, value in self.parameters],
            "parameter_refs": [
                item.to_payload() for item in sorted(self.parameter_refs, key=_reference_sort_key)
            ],
        }
        return hashlib.sha256(_canonical_json(document)).hexdigest()


@dataclass(frozen=True, slots=True)
class ProtocolContractRecord:
    """Immutable contract bytes; callers receive a fresh payload copy when needed."""

    schema_name: str
    canonical_payload: str

    def __post_init__(self) -> None:
        if self.schema_name not in {
            RUNNER_PROTOCOL_DEFINITION_SCHEMA,
            RUNNER_PROTOCOL_REGISTRY_SCHEMA,
            RUNNER_PROTOCOL_RESULT_SCHEMA,
        }:
            raise RunnerProtocolError("unsupported Runner Protocol contract schema")
        try:
            payload = json.loads(self.canonical_payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RunnerProtocolError("contract record bytes must contain JSON") from exc
        if not isinstance(payload, dict) or payload.get("schema_name") != self.schema_name:
            raise RunnerProtocolError("contract record schema does not match its payload")

    def to_payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_payload)

    @property
    def ref(self) -> ContractRef:
        if self.schema_name == RUNNER_PROTOCOL_RESULT_SCHEMA:
            raise RunnerProtocolError("RunnerProtocolResult is not content-addressed")
        payload = self.to_payload()
        return ContractRef(self.schema_name, payload["id"], payload["content_hash"])


@dataclass(frozen=True, slots=True)
class RunnerProtocolEvaluation:
    record: ProtocolContractRecord
    state: RunnerProtocolState
    reason_code: str | None
    worker_steps: int | None


@dataclass(frozen=True, slots=True)
class RunnerProtocolRegistryBundle:
    registry_record: ProtocolContractRecord
    definition_records: tuple[ProtocolContractRecord, ...]


def _reference_sort_key(reference: ContractRef) -> tuple[str, str, str]:
    return (reference.target_schema_name, reference.target_id, reference.content_hash)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fixed_decimal(value: Decimal | None) -> str | None:
    return None if value is None else protocol_decimal_text(value)


def _utc_datetime(value: datetime | str) -> datetime:
    return as_utc(value, "protocol UTC instant").astimezone(timezone.utc)


def _ensure_hash(value: str, field_name: str) -> str:
    return require_sha256(value, field_name)
