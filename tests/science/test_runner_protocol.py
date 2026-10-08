from __future__ import annotations

import hashlib
import socket
from dataclasses import MISSING, fields, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from qc2_contracts.runtime import validate_contract, verify_content_hash
from qc2_science import (
    ContractRef,
    ProtocolEvidenceValue,
    ProtocolInputBundle,
    RunnerProtocolError,
    RunnerProtocolSpec,
    RunnerProtocolState,
    evaluate_runner_protocol,
    fixture_structural_protocols,
    materialize_runner_protocol_definition,
    materialize_runner_protocol_registry,
)
from qc2_science.runner_protocol import _run_isolated_worker

FIXED_CREATED = "2026-01-03T20:01:00Z"
FIXED_CUTOFF = "2026-01-03T20:00:00Z"
KNOWN_AT = "2026-01-03T19:59:00Z"
INPUT_REF = "qc2.scientific_definitions.FeatureSnapshot.v1"
INSTRUMENT_REF = "qc2.identity_market.Instrument.v1"


def _uuid7(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    random_bits = int.from_bytes(digest[:10], "big") & ((1 << 74) - 1)
    rand_a = random_bits >> 62
    rand_b = random_bits & ((1 << 62) - 1)
    timestamp_ms = 1_767_225_600_000
    value = (
        (timestamp_ms << 80)
        | (7 << 76)
        | (rand_a << 64)
        | (2 << 62)
        | rand_b
    )
    return str(UUID(int=value))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ref(schema_name: str, key: str) -> ContractRef:
    return ContractRef(schema_name, _uuid7(f"{schema_name}:{key}"), _hash(key))


def _inputs(
    source_ref: ContractRef,
    value: Decimal | None,
    *,
    missingness: str = "PRESENT",
    known_at: str | None = KNOWN_AT,
) -> ProtocolInputBundle:
    evidence = ProtocolEvidenceValue(
        key="structure_value",
        value=value,
        unit="fraction",
        uncertainty=Decimal("0.000000000000"),
        missingness=missingness,
        source_ref=source_ref,
        known_at=known_at,
    )
    return ProtocolInputBundle(
        session_id=date(2026, 1, 3),
        instrument_ref=_ref(INSTRUMENT_REF, "instrument"),
        cutoff=FIXED_CUTOFF,
        values=(evidence,),
    )


def _definition(spec, key: str = "definition"):
    return materialize_runner_protocol_definition(
        spec,
        record_id=_uuid7(key),
        created_at=FIXED_CREATED,
    )


def test_fixture_protocols_materialize_strict_contracts_and_preserve_block() -> None:
    source_ref = _ref(INPUT_REF, "snapshot")
    positive, adverse = fixture_structural_protocols(source_ref)
    positive_definition = _definition(positive, "positive-definition")
    adverse_definition = _definition(adverse, "adverse-definition")

    passing = evaluate_runner_protocol(
        positive,
        positive_definition,
        _inputs(source_ref, Decimal("0.02")),
        result_id=_uuid7("positive-result"),
        created_at=FIXED_CREATED,
    )
    blocking = evaluate_runner_protocol(
        adverse,
        adverse_definition,
        _inputs(source_ref, Decimal("-0.01")),
        result_id=_uuid7("adverse-result"),
        created_at=FIXED_CREATED,
    )

    pass_payload = passing.record.to_payload()
    block_payload = blocking.record.to_payload()
    validate_contract("RunnerProtocolDefinition", positive_definition.to_payload())
    validate_contract("RunnerProtocolResult", pass_payload)
    verify_content_hash("RunnerProtocolDefinition", positive_definition.to_payload())

    assert passing.state is RunnerProtocolState.PASS
    assert pass_payload["result"] == "PASS"
    assert pass_payload["owning_authority"] == "runner_protocol"
    assert pass_payload["protocol_ref"] == positive_definition.ref.to_payload()
    assert pass_payload["evidence_values"][0]["value"] == "0.020000000000"
    assert "content_hash" not in pass_payload
    assert blocking.state is RunnerProtocolState.BLOCK
    assert block_payload["result"] == "BLOCK"
    assert blocking.reason_code == "HYPOTHESIS_MATCHED_BLOCK"
    assert not hasattr(blocking, "safety_action")


def test_results_are_immutable_copies_and_namespaced_registry_keys_are_unambiguous() -> None:
    source_ref = _ref(INPUT_REF, "registry-snapshot")
    positive, adverse = fixture_structural_protocols(source_ref)
    positive_record = _definition(positive, "positive-registry-definition")
    adverse_record = _definition(adverse, "adverse-registry-definition")
    registry = materialize_runner_protocol_registry(
        (positive, adverse),
        (positive_record, adverse_record),
        registry_version=1,
        active_protocol_keys=(positive.protocol_key, adverse.protocol_key),
        effective_from="2026-01-03",
        record_id=_uuid7("runner-registry"),
        created_at=FIXED_CREATED,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )

    payload = registry.registry_record.to_payload()
    assert payload["active_protocol_ids"] == [
        "fixture:adverse-structure-demo:v1",
        "fixture:positive-structure-demo:v1",
    ]
    assert len(payload["definition_refs"]) == 2
    payload["active_protocol_ids"].clear()
    assert registry.registry_record.to_payload()["active_protocol_ids"]


def test_missing_and_unknown_evidence_never_default_to_pass() -> None:
    source_ref = _ref(INPUT_REF, "missingness-snapshot")
    positive, _ = fixture_structural_protocols(source_ref)
    definition = _definition(positive, "missingness-definition")

    unknown = evaluate_runner_protocol(
        positive,
        definition,
        _inputs(source_ref, None, missingness="UNKNOWN", known_at=None),
        result_id=_uuid7("unknown-result"),
        created_at=FIXED_CREATED,
    )
    unavailable = evaluate_runner_protocol(
        positive,
        definition,
        _inputs(source_ref, None, missingness="MISSING", known_at=None),
        result_id=_uuid7("missing-result"),
        created_at=FIXED_CREATED,
    )

    assert unknown.state is RunnerProtocolState.UNKNOWN
    assert unknown.reason_code == "INPUT_UNKNOWN"
    assert unknown.record.to_payload()["missingness"] == "UNKNOWN"
    assert unavailable.state is RunnerProtocolState.UNAVAILABLE
    assert unavailable.reason_code == "INPUT_UNAVAILABLE"
    assert unavailable.record.to_payload()["missingness"] == "MISSING"


def test_input_reference_and_point_in_time_binding_are_enforced() -> None:
    source_ref = _ref(INPUT_REF, "expected-snapshot")
    other_ref = _ref(INPUT_REF, "other-snapshot")
    positive, _ = fixture_structural_protocols(source_ref)
    definition = _definition(positive, "binding-definition")

    with pytest.raises(RunnerProtocolError, match="binding"):
        evaluate_runner_protocol(
            positive,
            definition,
            _inputs(other_ref, Decimal("0.02")),
            result_id=_uuid7("wrong-ref-result"),
            created_at=FIXED_CREATED,
        )

    mismatched_input_spec = replace(
        positive,
        input_requirements=(
            replace(positive.input_requirements[0], source_ref=other_ref),
        ),
    )
    mismatched_definition = _definition(mismatched_input_spec, "mismatched-definition")
    with pytest.raises(RunnerProtocolError, match="definition record"):
        evaluate_runner_protocol(
            positive,
            mismatched_definition,
            _inputs(source_ref, Decimal("0.02")),
            result_id=_uuid7("mismatched-definition-result"),
            created_at=FIXED_CREATED,
        )

    mismatched_parameters = replace(
        positive,
        parameters=(("fixture_threshold", Decimal("0.03")),),
    )
    mismatched_parameter_definition = _definition(
        mismatched_parameters, "mismatched-parameter-definition"
    )
    with pytest.raises(RunnerProtocolError, match="definition record"):
        evaluate_runner_protocol(
            positive,
            mismatched_parameter_definition,
            _inputs(source_ref, Decimal("0.02")),
            result_id=_uuid7("mismatched-parameter-result"),
            created_at=FIXED_CREATED,
        )

    future = _inputs(source_ref, Decimal("0.02"), known_at="2026-01-03T20:00:01Z")
    with pytest.raises(RunnerProtocolError, match="decision cutoff"):
        evaluate_runner_protocol(
            positive,
            definition,
            future,
            result_id=_uuid7("future-input-result"),
            created_at=FIXED_CREATED,
        )


@pytest.mark.parametrize(
    "hostile_expression",
    [
        {"op": "network_request", "url": "http://127.0.0.1"},
        {"op": "filesystem_write", "path": "filesystem-sentinel"},
        {"op": "clock_now"},
        {"op": "globals"},
        {"op": "model_train"},
        {"op": "broker_submit"},
    ],
)
def test_worker_rejects_network_filesystem_clock_global_training_and_broker_operations(
    hostile_expression: dict[str, object],
    tmp_path: Path,
) -> None:
    expression = dict(hostile_expression)
    sentinel = tmp_path / "forbidden-write"
    if expression["op"] == "filesystem_write":
        expression["path"] = str(sentinel)
    response = _run_isolated_worker(
        {
            "expression": expression,
            "inputs": {},
            "parameters": {},
            "max_steps": 32,
        },
        timeout_seconds=2.0,
    )
    assert response == (None, None, "UNSUPPORTED_EXPRESSION")
    assert not sentinel.exists()


def test_network_operator_cannot_connect_to_a_local_listener() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.05)
        host, port = listener.getsockname()
        response = _run_isolated_worker(
            {
                "expression": {"op": "socket_connect", "host": host, "port": port},
                "inputs": {},
                "parameters": {},
                "max_steps": 32,
            },
            timeout_seconds=2.0,
        )
        assert response == (None, None, "UNSUPPORTED_EXPRESSION")
        with pytest.raises(TimeoutError):
            listener.accept()


def test_worker_step_exhaustion_is_a_visible_unavailable_protocol_failure() -> None:
    source_ref = _ref(INPUT_REF, "resource-snapshot")
    positive, _ = fixture_structural_protocols(source_ref)
    limited = replace(positive, max_steps=1)
    definition = _definition(limited, "resource-definition")
    result = evaluate_runner_protocol(
        limited,
        definition,
        _inputs(source_ref, Decimal("0.02")),
        result_id=_uuid7("resource-result"),
        created_at=FIXED_CREATED,
    )

    assert result.state is RunnerProtocolState.UNAVAILABLE
    assert result.reason_code == "RESOURCE_LIMIT_EXCEEDED"
    assert result.record.to_payload()["result"] == "UNAVAILABLE"


def test_process_timeout_is_returned_as_a_visible_protocol_failure() -> None:
    response = _run_isolated_worker(
        {
            "expression": {"op": "decimal", "value": "1.000000000000"},
            "inputs": {},
            "parameters": {},
            "max_steps": 8,
        },
        timeout_seconds=0.000001,
    )
    assert response == (None, None, "WORKER_TIMEOUT")


def test_synthetic_protocols_cannot_enter_production_registry() -> None:
    source_ref = _ref(INPUT_REF, "production-snapshot")
    specs = fixture_structural_protocols(source_ref)
    production_specs = tuple(
        replace(spec, environment_namespace="production") for spec in specs
    )
    records = tuple(
        _definition(spec, f"production-def-{index}")
        for index, spec in enumerate(production_specs)
    )

    with pytest.raises(RunnerProtocolError, match="synthetic"):
        materialize_runner_protocol_registry(
            production_specs,
            records,
            registry_version=1,
            active_protocol_keys=(production_specs[0].protocol_key,),
            effective_from="2026-01-03",
            record_id=_uuid7("production-registry"),
            created_at=FIXED_CREATED,
            evidence_class="SYNTHETIC_FIXTURE",
            environment_namespace="production",
        )

    mislabeled_as_forward = replace(
        specs[0],
        evidence_class="FORWARD_OPERATIONAL",
        environment_namespace="production",
    )
    definition = _definition(mislabeled_as_forward, "unqualified-production-definition")
    with pytest.raises(RunnerProtocolError, match="calibration and owner evidence"):
        evaluate_runner_protocol(
            mislabeled_as_forward,
            definition,
            _inputs(source_ref, Decimal("0.02")),
            result_id=_uuid7("unqualified-production-result"),
            created_at=FIXED_CREATED,
        )


def test_definition_requires_explicit_match_and_non_match_states() -> None:
    source_ref = _ref(INPUT_REF, "explicit-outcome-snapshot")
    spec = fixture_structural_protocols(source_ref)[0]
    assert spec.on_match is RunnerProtocolState.PASS
    assert spec.on_non_match is RunnerProtocolState.OBSERVE
    assert spec.protocol_key.startswith("fixture:")
    spec_fields = {field.name: field for field in fields(RunnerProtocolSpec)}
    assert spec_fields["on_match"].default is MISSING
    assert spec_fields["on_non_match"].default is MISSING


def test_same_bare_protocol_id_is_distinct_across_runner_namespaces() -> None:
    source_ref = _ref(INPUT_REF, "namespace-snapshot")
    fixture_spec = fixture_structural_protocols(source_ref)[0]
    research_spec = replace(fixture_spec, protocol_namespace="research")
    fixture_record = _definition(fixture_spec, "fixture-namespace-definition")
    research_record = _definition(research_spec, "research-namespace-definition")

    registry = materialize_runner_protocol_registry(
        (fixture_spec, research_spec),
        (fixture_record, research_record),
        registry_version=1,
        active_protocol_keys=(fixture_spec.protocol_key, research_spec.protocol_key),
        effective_from="2026-01-03",
        record_id=_uuid7("namespaced-registry"),
        created_at=FIXED_CREATED,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )

    assert fixture_spec.protocol_id == research_spec.protocol_id
    assert fixture_spec.protocol_key != research_spec.protocol_key
    assert registry.registry_record.to_payload()["active_protocol_ids"] == [
        "fixture:positive-structure-demo:v1",
        "research:positive-structure-demo:v1",
    ]
