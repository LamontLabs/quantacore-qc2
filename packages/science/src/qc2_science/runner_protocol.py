"""Pure, isolated Runner Protocol definitions, registries, and evaluations."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from qc2_contracts.runtime import (
    canonical_content_hash,
    validate_contract,
    verify_content_hash,
)

from .models import ContractRef, as_utc
from .runner_protocol_models import (
    RUNNER_PROTOCOL_DEFINITION_SCHEMA,
    RUNNER_PROTOCOL_REGISTRY_SCHEMA,
    RUNNER_PROTOCOL_RESULT_SCHEMA,
    ProtocolContractRecord,
    ProtocolEvidenceValue,
    ProtocolInputBundle,
    ProtocolActivationDenied,
    RunnerProtocolError,
    RunnerProtocolEvaluation,
    RunnerProtocolRegistryBundle,
    RunnerProtocolSpec,
    RunnerProtocolState,
    ProtocolInputRequirement,
    _canonical_json,
    _expression_document,
    _fixed_decimal,
    _reference_sort_key,
    utc_contract_text,
)

_WORKER_SCRIPT = Path(__file__).with_name("runner_protocol_worker.py")
_MAX_REQUEST_BYTES = 65_536
_RUNNER_INPUT_SCHEMAS = frozenset(
    {
        "qc2.scientific_definitions.FeatureSnapshot.v1",
        "qc2.identity_market.DailyBar.v1",
    }
)
_MISSINGNESS_PRIORITY = ("MISSING", "UNKNOWN", "NOT_APPLICABLE")


def _contract_record(contract_name: str, payload: dict[str, Any]) -> ProtocolContractRecord:
    if contract_name in {"RunnerProtocolDefinition", "RunnerProtocolRegistry"}:
        payload["content_hash"] = "0" * 64
        validate_contract(contract_name, payload)
        payload["content_hash"] = canonical_content_hash(contract_name, payload)
        verify_content_hash(contract_name, payload)
    else:
        validate_contract(contract_name, payload)
    text = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ProtocolContractRecord(payload["schema_name"], text)


def _ref_payloads(references: Sequence[ContractRef]) -> list[dict[str, str]]:
    return [item.to_payload() for item in sorted(references, key=_reference_sort_key)]


def _definition_matches_spec(
    payload: dict[str, Any], spec: RunnerProtocolSpec
) -> bool:
    return (
        payload["protocol_namespace"] == spec.protocol_namespace
        and payload["protocol_id"] == spec.protocol_id
        and payload["version"] == spec.version
        and payload["hypothesis"] == spec.hypothesis
        and payload["direction"] == spec.direction
        and payload["regime"] == spec.regime
        and payload["evidence_class"] == spec.evidence_class
        and payload["environment_namespace"] == spec.environment_namespace
        and payload["source_refs"] == _ref_payloads(spec.source_refs)
        and payload["input_refs"]
        == _ref_payloads(tuple(item.source_ref for item in spec.input_requirements))
        and payload["parameter_refs"] == _ref_payloads(spec.parameter_refs)
        and payload["implementation_hash"] == spec.implementation_hash
    )


def _new_base(
    *,
    schema_name: str,
    record_id: str,
    created_at: datetime | str,
    evidence_class: str,
    environment_namespace: str,
    source_refs: Sequence[ContractRef],
) -> dict[str, Any]:
    payload = {
        "schema_name": schema_name,
        "schema_version": "1.0",
        "id": record_id,
        "created_at": utc_contract_text(created_at),
        "owning_authority": "runner_protocol",
        "evidence_class": evidence_class,
        "environment_namespace": environment_namespace,
        "source_refs": _ref_payloads(source_refs),
    }
    if schema_name != RUNNER_PROTOCOL_RESULT_SCHEMA:
        payload["content_hash"] = "0" * 64
    return payload


def materialize_runner_protocol_definition(
    spec: RunnerProtocolSpec,
    *,
    record_id: str,
    created_at: datetime | str,
) -> ProtocolContractRecord:
    """Create a validated, content-addressed definition using caller-supplied identity and time."""
    payload = _new_base(
        schema_name=RUNNER_PROTOCOL_DEFINITION_SCHEMA,
        record_id=record_id,
        created_at=created_at,
        evidence_class=spec.evidence_class,
        environment_namespace=spec.environment_namespace,
        source_refs=spec.source_refs,
    )
    payload.update(
        {
            "protocol_namespace": spec.protocol_namespace,
            "protocol_id": spec.protocol_id,
            "version": spec.version,
            "hypothesis": spec.hypothesis,
            "direction": spec.direction,
            "input_refs": _ref_payloads(
                tuple(item.source_ref for item in spec.input_requirements)
            ),
            "parameter_refs": _ref_payloads(spec.parameter_refs),
            "implementation_hash": spec.implementation_hash,
            "regime": spec.regime,
        }
    )
    return _contract_record("RunnerProtocolDefinition", payload)


def assert_runner_protocol_activation(
    specs: Sequence[RunnerProtocolSpec],
    *,
    target_environment: str,
    registry_evidence_class: str,
) -> None:
    """Deny all production activation until a later authority supplies approval evidence."""
    if target_environment != "production":
        return
    if registry_evidence_class == "SYNTHETIC_FIXTURE" or any(
        spec.evidence_class == "SYNTHETIC_FIXTURE" for spec in specs
    ):
        raise ProtocolActivationDenied(
            "synthetic Runner Protocol fixtures cannot be activated in production"
        )
    raise ProtocolActivationDenied(
        "production activation requires calibration and owner evidence not provided by QC2-017"
    )


def materialize_runner_protocol_registry(
    specs: Sequence[RunnerProtocolSpec],
    definition_records: Sequence[ProtocolContractRecord],
    *,
    registry_version: int,
    active_protocol_keys: Sequence[str],
    effective_from: date | str,
    record_id: str,
    created_at: datetime | str,
    evidence_class: str,
    environment_namespace: str,
    source_refs: Sequence[ContractRef] = (),
) -> RunnerProtocolRegistryBundle:
    """Build a namespace-qualified registry with explicit active protocol keys."""
    specs = tuple(sorted(specs, key=lambda item: item.protocol_key))
    records = tuple(definition_records)
    if len(specs) != len(records):
        raise RunnerProtocolError("each registry protocol must have one definition record")
    if type(registry_version) is not int or registry_version < 1:
        raise RunnerProtocolError("registry_version must be a positive integer")
    if evidence_class not in {
        "SYNTHETIC_FIXTURE",
        "HISTORICAL_RECONSTRUCTED",
        "FORWARD_OPERATIONAL",
        "FORWARD_SEALED",
    }:
        raise RunnerProtocolError("registry evidence_class is not supported")
    if environment_namespace not in {"development", "test", "research", "production"}:
        raise RunnerProtocolError("registry environment_namespace is not supported")
    if any(item.schema_name != RUNNER_PROTOCOL_DEFINITION_SCHEMA for item in records):
        raise RunnerProtocolError("registry definition_refs must target RunnerProtocolDefinition")
    if any(spec.evidence_class != evidence_class for spec in specs):
        raise RunnerProtocolError("registry and protocol evidence classes must match")
    if any(spec.environment_namespace != environment_namespace for spec in specs):
        raise RunnerProtocolError("registry and protocol environments must match")

    specs_by_key = {spec.protocol_key: spec for spec in specs}
    if len(specs_by_key) != len(specs):
        raise RunnerProtocolError("protocol keys must be unique within a registry")
    records_by_key: dict[str, ProtocolContractRecord] = {}
    for record in records:
        payload = record.to_payload()
        key = (
            f"{payload.get('protocol_namespace')}:{payload.get('protocol_id')}:"
            f"v{payload.get('version')}"
        )
        if key in records_by_key:
            raise RunnerProtocolError("definition records contain duplicate protocol keys")
        records_by_key[key] = record
    if set(records_by_key) != set(specs_by_key):
        raise RunnerProtocolError("definition records do not match registry protocol specs")

    for spec in specs:
        record = records_by_key[spec.protocol_key]
        payload = record.to_payload()
        verify_content_hash("RunnerProtocolDefinition", payload)
        if not _definition_matches_spec(payload, spec):
            raise RunnerProtocolError("definition record does not match its protocol spec")

    active = tuple(sorted(active_protocol_keys))
    if len(set(active)) != len(active) or not set(active).issubset(specs_by_key):
        raise RunnerProtocolError("active_protocol_keys must uniquely identify registered protocols")
    assert_runner_protocol_activation(
        specs,
        target_environment=environment_namespace,
        registry_evidence_class=evidence_class,
    )

    payload = _new_base(
        schema_name=RUNNER_PROTOCOL_REGISTRY_SCHEMA,
        record_id=record_id,
        created_at=created_at,
        evidence_class=evidence_class,
        environment_namespace=environment_namespace,
        source_refs=source_refs,
    )
    payload.update(
        {
            "registry_version": registry_version,
            "definition_refs": [
                records_by_key[key].ref.to_payload() for key in sorted(records_by_key)
            ],
            "active_protocol_ids": list(active),
            "effective_from": date.fromisoformat(str(effective_from)).isoformat(),
        }
    )
    registry_record = _contract_record("RunnerProtocolRegistry", payload)
    ordered_records = tuple(records_by_key[key] for key in sorted(records_by_key))
    return RunnerProtocolRegistryBundle(registry_record, ordered_records)


def _worker_request(
    spec: RunnerProtocolSpec, values: Sequence[ProtocolEvidenceValue]
) -> dict[str, Any]:
    return {
        "expression": _expression_document(spec.expression),
        "inputs": {
            item.key: f"{item.value:.12f}"
            for item in values
            if item.missingness == "PRESENT" and item.value is not None
        },
        "parameters": {key: f"{value:.12f}" for key, value in spec.parameters},
        "max_steps": spec.max_steps,
    }


def _run_isolated_worker(
    request: dict[str, Any], *, timeout_seconds: float
) -> tuple[bool | None, int | None, str | None]:
    """Run only the trusted declarative interpreter, with imports and OS resources constrained."""
    if (
        type(timeout_seconds) not in (float, int)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > 10
    ):
        return None, None, "INVALID_TIMEOUT"
    try:
        raw = _canonical_json(request)
    except (TypeError, ValueError):
        return None, None, "INVALID_REQUEST"
    if len(raw) > _MAX_REQUEST_BYTES:
        return None, None, "RESOURCE_LIMIT_EXCEEDED"

    env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
    command = [sys.executable, "-I", "-S", str(_WORKER_SCRIPT)]
    try:
        completed = subprocess.run(
            command,
            input=raw.decode("utf-8"),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            close_fds=True,
            cwd="/",
            env=env,
            timeout=float(timeout_seconds),
        )
    except subprocess.TimeoutExpired:
        return None, None, "WORKER_TIMEOUT"
    except OSError:
        return None, None, "WORKER_LAUNCH_FAILED"
    if completed.returncode != 0:
        return None, None, "WORKER_RESOURCE_OR_EXIT_FAILURE"
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, None, "WORKER_INVALID_RESPONSE"
    if not isinstance(response, dict):
        return None, None, "WORKER_INVALID_RESPONSE"
    if response.get("ok") is True and type(response.get("matched")) is bool:
        steps = response.get("steps")
        if type(steps) is not int or steps < 0:
            return None, None, "WORKER_INVALID_RESPONSE"
        return response["matched"], steps, None
    code = response.get("code")
    if not isinstance(code, str) or not code:
        code = "WORKER_INVALID_RESPONSE"
    return None, None, code


def _validate_input_binding(
    spec: RunnerProtocolSpec, inputs: ProtocolInputBundle
) -> tuple[ProtocolEvidenceValue, ...]:
    by_key = {item.key: item for item in inputs.values}
    required = {item.key: item for item in spec.input_requirements}
    if set(by_key) != set(required):
        raise RunnerProtocolError("protocol inputs must exactly match the definition's required keys")

    for key, requirement in required.items():
        value = by_key[key]
        if value.unit != requirement.unit or value.source_ref != requirement.source_ref:
            raise RunnerProtocolError(f"input evidence binding does not match requirement {key!r}")
        if value.source_ref.target_schema_name not in _RUNNER_INPUT_SCHEMAS:
            raise RunnerProtocolError("protocol input reference schema is not permitted")
        if value.missingness == "PRESENT":
            known_at = as_utc(value.known_at, f"{key} known_at")
            if known_at > inputs.cutoff:
                raise RunnerProtocolError(f"input {key!r} was not known at the decision cutoff")
    return tuple(by_key[key] for key in sorted(by_key))


def _aggregate_missingness(values: Sequence[ProtocolEvidenceValue]) -> str:
    states = {item.missingness for item in values}
    for state in _MISSINGNESS_PRIORITY:
        if state in states:
            return state
    return "PRESENT"


def evaluate_runner_protocol(
    spec: RunnerProtocolSpec,
    definition_record: ProtocolContractRecord,
    inputs: ProtocolInputBundle,
    *,
    result_id: str,
    created_at: datetime | str,
    timeout_seconds: float = 2.0,
) -> RunnerProtocolEvaluation:
    """Evaluate a protocol with immutable evidence and convert all runtime failures to UNAVAILABLE."""
    assert_runner_protocol_activation(
        (spec,),
        target_environment=spec.environment_namespace,
        registry_evidence_class=spec.evidence_class,
    )
    if definition_record.schema_name != RUNNER_PROTOCOL_DEFINITION_SCHEMA:
        raise RunnerProtocolError("evaluation requires a RunnerProtocolDefinition record")
    definition_payload = definition_record.to_payload()
    verify_content_hash("RunnerProtocolDefinition", definition_payload)
    if not _definition_matches_spec(definition_payload, spec):
        raise RunnerProtocolError("definition record does not match the evaluation spec")

    bound_values = _validate_input_binding(spec, inputs)
    missingness = _aggregate_missingness(bound_values)
    reason_code: str | None = None
    worker_steps: int | None = None

    if missingness == "MISSING" or missingness == "NOT_APPLICABLE":
        state = RunnerProtocolState.UNAVAILABLE
        reason_code = "INPUT_UNAVAILABLE"
    elif missingness == "UNKNOWN":
        state = RunnerProtocolState.UNKNOWN
        reason_code = "INPUT_UNKNOWN"
    else:
        matched, worker_steps, failure = _run_isolated_worker(
            _worker_request(spec, bound_values),
            timeout_seconds=timeout_seconds,
        )
        if failure is not None:
            state = RunnerProtocolState.UNAVAILABLE
            reason_code = failure
        else:
            state = spec.on_match if matched else spec.on_non_match
            if matched is True:
                reason_code = f"HYPOTHESIS_MATCHED_{state.value}"
            else:
                reason_code = f"HYPOTHESIS_NOT_MATCHED_{state.value}"

    present_values = [item for item in bound_values if item.missingness == "PRESENT"]
    result_refs = sorted(
        {item.source_ref for item in bound_values},
        key=_reference_sort_key,
    )
    result_payload = _new_base(
        schema_name=RUNNER_PROTOCOL_RESULT_SCHEMA,
        record_id=result_id,
        created_at=created_at,
        evidence_class=spec.evidence_class,
        environment_namespace=spec.environment_namespace,
        source_refs=spec.source_refs,
    )
    result_payload.update(
        {
            "protocol_ref": definition_record.ref.to_payload(),
            "session_id": inputs.session_id.isoformat(),
            "instrument_ref": inputs.instrument_ref.to_payload(),
            "result": state.value,
            "hypothesis": spec.hypothesis,
            "direction": spec.direction,
            "evidence_values": [
                {
                    "key": item.key,
                    "value": f"{item.value:.12f}",
                    "unit": item.unit,
                    "uncertainty": _fixed_decimal(item.uncertainty),
                }
                for item in present_values
            ],
            "uncertainty": _fixed_decimal(inputs.uncertainty),
            "missingness": missingness,
            "parameter_hash": spec.parameter_hash,
            "implementation_hash": spec.implementation_hash,
            "cutoff": utc_contract_text(inputs.cutoff),
            "input_refs": [item.to_payload() for item in result_refs],
        }
    )
    record = _contract_record("RunnerProtocolResult", result_payload)
    return RunnerProtocolEvaluation(record, state, reason_code, worker_steps)


def fixture_structural_protocols(input_ref: ContractRef) -> tuple[RunnerProtocolSpec, ...]:
    """Return synthetic test-only examples; their thresholds are not calibrated or activatable."""
    from .runner_protocol_models import input_value, parameter_value, protocol_operation

    requirement = ProtocolInputRequirement("structure_value", "fraction", input_ref)
    positive = RunnerProtocolSpec(
        protocol_namespace="fixture",
        protocol_id="positive-structure-demo",
        version=1,
        hypothesis="A synthetic structure value exceeds its fixture threshold.",
        direction="POSITIVE",
        regime="fixture_daily",
        input_requirements=(requirement,),
        parameter_refs=(),
        parameters=(("fixture_threshold", Decimal("0.010000000000")),),
        expression=protocol_operation(
            "gt", input_value("structure_value"), parameter_value("fixture_threshold")
        ),
        on_match=RunnerProtocolState.PASS,
        on_non_match=RunnerProtocolState.OBSERVE,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
        max_steps=16,
    )
    adverse = RunnerProtocolSpec(
        protocol_namespace="fixture",
        protocol_id="adverse-structure-demo",
        version=1,
        hypothesis="A synthetic adverse structure value is below zero.",
        direction="NEGATIVE",
        regime="fixture_daily",
        input_requirements=(requirement,),
        parameter_refs=(),
        parameters=(("zero", Decimal("0")),),
        expression=protocol_operation(
            "lt", input_value("structure_value"), parameter_value("zero")
        ),
        on_match=RunnerProtocolState.BLOCK,
        on_non_match=RunnerProtocolState.OBSERVE,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
        max_steps=16,
    )
    return (positive, adverse)
