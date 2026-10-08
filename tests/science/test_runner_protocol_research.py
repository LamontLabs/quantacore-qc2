from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from qc2_contracts.runtime import validate_contract, verify_content_hash
from qc2_science import (
    ContractRef,
    FeatureInputError,
    ProtocolEvidenceValue,
    ProtocolInputBundle,
    RunnerProtocolError,
    RunnerProtocolSpec,
    RunnerProtocolState,
    ProtocolActivationDenied,
    assert_runner_protocol_activation,
    build_feature_specs,
    evaluate_runner_protocol,
    materialize_runner_protocol_definition,
    materialize_runner_protocol_registry,
    research_wave1_protocols,
)

FIXED_CREATED = "2026-01-03T20:01:00Z"
FIXED_CUTOFF = "2026-01-03T20:00:00Z"
KNOWN_AT = "2026-01-03T19:59:00Z"
FUTURE_KNOWN_AT = "2026-01-03T20:00:01Z"
FEATURE_SNAPSHOT_SCHEMA = "qc2.scientific_definitions.FeatureSnapshot.v1"
INSTRUMENT_SCHEMA = "qc2.identity_market.Instrument.v1"
ROOT = Path(__file__).resolve().parents[2]
DECISION_LEDGER = ROOT / "docs/reference/QC2-019_MIGRATION_DECISIONS.json"
QUEUE = (
    "P55",
    "T34",
    "T37",
    "T38",
    "T41",
    "T42",
    "T44",
    "T57",
    "T77",
    "T78",
    "T92",
    "T102",
    "T103",
    "T104",
    "T108",
    "T109",
    "T110",
)


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


SNAPSHOT_REF = _ref(FEATURE_SNAPSHOT_SCHEMA, "qc2-019-research-feature-snapshot")
INSTRUMENT_REF = _ref(INSTRUMENT_SCHEMA, "qc2-019-research-instrument")


def _specs() -> tuple[RunnerProtocolSpec, ...]:
    return research_wave1_protocols(SNAPSHOT_REF)


def _definition(spec: RunnerProtocolSpec):
    return materialize_runner_protocol_definition(
        spec,
        record_id=_uuid7(f"definition:{spec.protocol_key}"),
        created_at=FIXED_CREATED,
    )


def _bundle(
    spec: RunnerProtocolSpec,
    values: dict[str, Decimal] | None = None,
    *,
    missingness: str = "PRESENT",
    known_at: str = KNOWN_AT,
) -> ProtocolInputBundle:
    values = values or {}
    evidence = tuple(
        ProtocolEvidenceValue(
            key=requirement.key,
            value=values.get(requirement.key) if missingness == "PRESENT" else None,
            unit=requirement.unit,
            uncertainty=Decimal("0"),
            missingness=missingness,
            source_ref=requirement.source_ref,
            known_at=known_at if missingness == "PRESENT" else None,
        )
        for requirement in spec.input_requirements
    )
    return ProtocolInputBundle(
        session_id=date(2026, 1, 3),
        instrument_ref=INSTRUMENT_REF,
        cutoff=FIXED_CUTOFF,
        values=evidence,
        uncertainty=Decimal("0"),
    )


def test_migration_ledger_covers_the_complete_requested_queue() -> None:
    ledger = json.loads(DECISION_LEDGER.read_text(encoding="utf-8"))
    assert ledger["candidate_ids"] == list(QUEUE)
    assert {item["candidate_id"] for item in ledger["decisions"]} == set(QUEUE)
    assert len(ledger["decisions"]) == len(QUEUE)
    assert all(item["disposition"] and item["regime_status"] for item in ledger["decisions"])


def test_research_registry_is_inactive_and_uses_only_registered_daily_features() -> None:
    specs = _specs()
    definitions = tuple(_definition(spec) for spec in specs)
    registry = materialize_runner_protocol_registry(
        specs,
        definitions,
        registry_version=1,
        active_protocol_keys=(),
        effective_from="2026-01-03",
        record_id=_uuid7("qc2-019-research-registry"),
        created_at=FIXED_CREATED,
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="research",
    )
    payload = registry.registry_record.to_payload()
    validate_contract("RunnerProtocolRegistry", payload)
    verify_content_hash("RunnerProtocolRegistry", payload)

    assert [spec.protocol_id for spec in specs] == [
        "t41-volume-expansion",
        "t44-positive-money-flow",
        "t78-return-sign-alignment",
    ]
    assert payload["active_protocol_ids"] == []
    assert payload["environment_namespace"] == "research"
    assert payload["evidence_class"] == "SYNTHETIC_FIXTURE"

    feature_units = {spec.stable_key: spec.output_unit for spec in build_feature_specs()}
    expected_units = {
        "relative_volume": "ratio",
        "accumulation": "signed_fraction",
        "return_10": "fraction",
        "return_20": "fraction",
    }
    assert {key: feature_units[key] for key in expected_units} == expected_units
    assert all(
        requirement.source_ref.target_schema_name == FEATURE_SNAPSHOT_SCHEMA
        for spec in specs
        for requirement in spec.input_requirements
    )
    assert all(spec.evidence_class == "SYNTHETIC_FIXTURE" for spec in specs)
    assert all(spec.environment_namespace == "research" for spec in specs)
    assert all(not spec.source_refs for spec in specs)


@pytest.mark.parametrize(
    ("protocol_id", "fixtures"),
    [
        (
            "t41-volume-expansion",
            (
                ({"relative_volume": Decimal("1.25")}, "PRESENT", RunnerProtocolState.PASS),
                ({"relative_volume": Decimal("0.90")}, "PRESENT", RunnerProtocolState.OBSERVE),
                ({}, "UNKNOWN", RunnerProtocolState.UNKNOWN),
            ),
        ),
        (
            "t44-positive-money-flow",
            (
                ({"accumulation": Decimal("0.20")}, "PRESENT", RunnerProtocolState.PASS),
                ({"accumulation": Decimal("-0.20")}, "PRESENT", RunnerProtocolState.OBSERVE),
                ({}, "UNKNOWN", RunnerProtocolState.UNKNOWN),
            ),
        ),
        (
            "t78-return-sign-alignment",
            (
                (
                    {"return_10": Decimal("0.05"), "return_20": Decimal("0.08")},
                    "PRESENT",
                    RunnerProtocolState.PASS,
                ),
                (
                    {"return_10": Decimal("-0.05"), "return_20": Decimal("-0.08")},
                    "PRESENT",
                    RunnerProtocolState.PASS,
                ),
                (
                    {"return_10": Decimal("0.05"), "return_20": Decimal("-0.08")},
                    "PRESENT",
                    RunnerProtocolState.OBSERVE,
                ),
                ({}, "UNKNOWN", RunnerProtocolState.UNKNOWN),
            ),
        ),
    ],
)
def test_each_research_hypothesis_has_exact_replay_and_typed_evidence(
    protocol_id: str,
    fixtures: tuple[tuple[dict[str, Decimal], str, RunnerProtocolState], ...],
) -> None:
    spec = next(spec for spec in _specs() if spec.protocol_id == protocol_id)
    definition = _definition(spec)
    validate_contract("RunnerProtocolDefinition", definition.to_payload())
    verify_content_hash("RunnerProtocolDefinition", definition.to_payload())

    for index, (values, missingness, expected_state) in enumerate(fixtures):
        inputs = _bundle(spec, values, missingness=missingness)
        result_id = _uuid7(f"{spec.protocol_key}:fixture:{index}")
        first = evaluate_runner_protocol(
            spec,
            definition,
            inputs,
            result_id=result_id,
            created_at=FIXED_CREATED,
        )
        replay = evaluate_runner_protocol(
            spec,
            definition,
            inputs,
            result_id=result_id,
            created_at=FIXED_CREATED,
        )

        assert first.state is expected_state
        assert first.record.canonical_payload == replay.record.canonical_payload
        assert first.worker_steps == replay.worker_steps
        if missingness == "PRESENT":
            assert first.worker_steps is not None
            assert first.worker_steps <= spec.max_steps

        result = first.record.to_payload()
        validate_contract("RunnerProtocolResult", result)
        assert result["hypothesis"] == spec.hypothesis
        assert result["direction"] == spec.direction
        assert result["missingness"] == missingness
        assert result["cutoff"] == "2026-01-03T20:00:00.000000Z"
        assert result["parameter_hash"] == spec.parameter_hash
        assert result["implementation_hash"] == spec.implementation_hash
        assert {item["key"] for item in result["evidence_values"]} == (
            {item.key for item in spec.input_requirements} if missingness == "PRESENT" else set()
        )
        assert len(result["input_refs"]) == len(
            {item.source_ref for item in spec.input_requirements}
        )


@pytest.mark.parametrize("spec", _specs(), ids=lambda spec: spec.protocol_id)
def test_each_research_hypothesis_rejects_future_values_and_binary_floats(
    spec: RunnerProtocolSpec,
) -> None:
    present_values = {
        item.key: Decimal("0.25")
        for item in spec.input_requirements
    }
    future_inputs = _bundle(spec, present_values, known_at=FUTURE_KNOWN_AT)
    with pytest.raises(RunnerProtocolError, match="decision cutoff"):
        evaluate_runner_protocol(
            spec,
            _definition(spec),
            future_inputs,
            result_id=_uuid7(f"{spec.protocol_key}:future"),
            created_at=FIXED_CREATED,
        )

    requirement = spec.input_requirements[0]
    with pytest.raises(FeatureInputError, match="binary float"):
        ProtocolEvidenceValue(
            key=requirement.key,
            value=0.25,
            unit=requirement.unit,
            uncertainty=Decimal("0"),
            missingness="PRESENT",
            source_ref=requirement.source_ref,
            known_at=KNOWN_AT,
        )


def test_research_factory_rejects_non_snapshot_input_references() -> None:
    with pytest.raises(RunnerProtocolError, match="FeatureSnapshot"):
        research_wave1_protocols(_ref("qc2.identity_market.DailyBar.v1", "not-a-snapshot"))


@pytest.mark.parametrize("spec", _specs(), ids=lambda spec: spec.protocol_id)
def test_research_hypotheses_cannot_be_activated_in_production(
    spec: RunnerProtocolSpec,
) -> None:
    with pytest.raises(ProtocolActivationDenied):
        assert_runner_protocol_activation(
            (spec,),
            target_environment="production",
            registry_evidence_class=spec.evidence_class,
        )


def test_research_parameters_are_explicit_fixture_contract_values() -> None:
    specs = {spec.protocol_id: spec for spec in _specs()}
    assert specs["t41-volume-expansion"].parameters == (
        ("expansion_boundary", Decimal("1.000000000000")),
    )
    assert specs["t44-positive-money-flow"].parameters == (
        ("zero_boundary", Decimal("0E-12")),
    )
    assert specs["t78-return-sign-alignment"].parameters == (
        ("zero_boundary", Decimal("0E-12")),
    )
    assert all(not spec.parameter_refs for spec in specs.values())


def test_only_supported_declarative_operations_back_the_research_entries() -> None:
    permitted = {
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

    def visit(node) -> None:
        assert node.op in permitted
        for child in node.args:
            if hasattr(child, "op"):
                visit(child)

    for spec in _specs():
        visit(spec.expression)
