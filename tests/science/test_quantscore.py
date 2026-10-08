from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest
from qc2_contracts.runtime import (
    canonical_content_hash,
    new_uuidv7,
    validate_contract,
    verify_content_hash,
)
from qc2_science import (
    ContractRef,
    ScoreActivationDenied,
    ScoreDisposition,
    ScoreInputAvailability,
    ScoreInputError,
    ScoreInputRef,
    ScoreManifestError,
    evaluate_score_row,
    fixture_score_program,
    fixture_structural_protocols,
    load_score_program,
    materialize_runner_protocol_definition,
    materialize_score_definition,
    materialize_score_manifest,
    primary_probability_from_contracts,
    rank_score_evaluations,
    score_input_from_head_output,
    score_inputs_from_protocol_result,
)

ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = json.loads(
    (ROOT / "packages/contracts/fixtures/v1/valid.json").read_text(encoding="utf-8")
)
_CREATED = "2026-10-05T20:00:00Z"
_SESSION = "2026-10-05"
_MODEL_HEAD_SCHEMA = "qc2.models_prediction.ModelHeadDefinition.v1"
_PROTOCOL_RESULT_SCHEMA = "qc2.scientific_definitions.RunnerProtocolResult.v1"
_PRIMARY_HEAD_ID = "018f0000-0000-7000-8000-000000000101"
_PROTOCOL_RESULT_ID = "018f0000-0000-7000-8000-000000000102"
_DEFINITION_ID = "018f0000-0000-7000-8000-000000000103"
_MANIFEST_ID = "018f0000-0000-7000-8000-000000000104"
_LABEL_ID = "018f0000-0000-7000-8000-000000000105"
_INSTRUMENT_ID = "018f0000-0000-7000-8000-000000000106"
_FAILURE_HEAD_ID = "018f0000-0000-7000-8000-000000000110"


def _fixture_contract(name: str) -> dict:
    return copy.deepcopy(
        next(item["payload"] for item in _FIXTURES if item["contract"] == name)
    )


def _seal(name: str, payload: dict) -> dict:
    payload["content_hash"] = "0" * 64
    payload["content_hash"] = canonical_content_hash(name, payload)
    validate_contract(name, payload)
    verify_content_hash(name, payload)
    return payload


def _program(
    *,
    with_support: bool = True,
    missing_policy: str = "BLOCK_ROW",
    missing_penalty: str = "-0.100000000000",
    evidence_class: str = "SYNTHETIC_FIXTURE",
    environment_namespace: str = "test",
):
    primary_ref = ScoreInputRef(_MODEL_HEAD_SCHEMA, _PRIMARY_HEAD_ID)
    refs = [primary_ref]
    coefficients = ["1.000000000000"]
    transforms = ["HEAD_OUTPUT|IDENTITY"]
    if with_support:
        refs.append(ScoreInputRef(_PROTOCOL_RESULT_SCHEMA, _PROTOCOL_RESULT_ID))
        coefficients = ["0.500000000000", "0.500000000000"]
        support_transform = (
            "PROTOCOL_EVIDENCE:structure_value@fraction|DIRECTIONAL_RATIONAL_SQUASH"
        )
        if missing_policy == "EXPLICIT_PENALTY":
            support_transform += f"|MISSING_PENALTY={missing_penalty}"
        transforms.append(support_transform)
    definition = materialize_score_definition(
        definition_id=_DEFINITION_ID,
        created_at=_CREATED,
        stable_key="synthetic_quantscore_fixture",
        version=1,
        input_refs=refs,
        coefficients=coefficients,
        transforms=transforms,
        clipping_policy="CLIP_TO_0_100",
        missing_head_policy=missing_policy,
        tie_break_rule="SCORE_DESC_STABLE_INSTRUMENT_ID_ASC",
        evidence_class=evidence_class,
        environment_namespace=environment_namespace,
    )
    manifest = materialize_score_manifest(
        manifest_id=_MANIFEST_ID,
        created_at=_CREATED,
        frozen_at=_CREATED,
        definition=definition,
    )
    program = load_score_program(
        manifest,
        definition,
        target_environment_namespace=environment_namespace,
    )
    return program, manifest, definition


def _primary_contracts(
    instrument_id: str,
    value: str = "0.750000000000",
) -> tuple[dict, dict, dict]:
    label = _fixture_contract("LabelDefinition")
    label.update(
        {
            "id": _LABEL_ID,
            "created_at": _CREATED,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "horizon_sessions": 1,
            "target_event": "EXPANSION_RUNNER",
        }
    )
    _seal("LabelDefinition", label)

    head = _fixture_contract("ModelHeadDefinition")
    head.update(
        {
            "id": _PRIMARY_HEAD_ID,
            "created_at": _CREATED,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "head_name": "fixture_expansion_runner_probability",
            "output_kind": "PROBABILITY",
            "label_ref": {
                "target_schema_name": label["schema_name"],
                "target_id": label["id"],
                "content_hash": label["content_hash"],
            },
            "horizon_sessions": 1,
            "availability": "AVAILABLE",
            "output_precision": 12,
        }
    )
    validate_contract("ModelHeadDefinition", head)

    output = _fixture_contract("ModelHeadOutput")
    output.update(
        {
            "id": new_uuidv7(),
            "created_at": _CREATED,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "head_ref": {
                "target_schema_name": _MODEL_HEAD_SCHEMA,
                "target_id": _PRIMARY_HEAD_ID,
            },
            "instrument_ref": {
                "target_schema_name": "qc2.identity_market.Instrument.v1",
                "target_id": instrument_id,
            },
            "session_id": _SESSION,
            "output_value": value,
            "output_unit": "probability",
            "availability": "AVAILABLE",
            "reason_code": None,
        }
    )
    validate_contract("ModelHeadOutput", output)
    return head, label, output


def _protocol_definition():
    source_ref = ContractRef(
        "qc2.scientific_definitions.FeatureSnapshot.v1",
        new_uuidv7(),
        "a" * 64,
    )
    positive_spec, _ = fixture_structural_protocols(source_ref)
    record = materialize_runner_protocol_definition(
        positive_spec,
        record_id=new_uuidv7(),
        created_at=_CREATED,
    )
    return record, source_ref


def _protocol_result(
    definition_record,
    source_ref: ContractRef,
    instrument_id: str,
    *,
    result: str = "PASS",
    direction: str = "POSITIVE",
    value: str = "0.500000000000",
) -> dict:
    payload = _fixture_contract("RunnerProtocolResult")
    payload.update(
        {
            "id": _PROTOCOL_RESULT_ID,
            "created_at": _CREATED,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "protocol_ref": definition_record.ref.to_payload(),
            "session_id": _SESSION,
            "instrument_ref": {
                "target_schema_name": "qc2.identity_market.Instrument.v1",
                "target_id": instrument_id,
            },
            "result": result,
            "direction": direction,
            "evidence_values": (
                [
                    {
                        "key": "structure_value",
                        "value": value,
                        "unit": "fraction",
                        "uncertainty": "0.000000000000",
                    }
                ]
                if result in {"PASS", "BLOCK", "OBSERVE"}
                else []
            ),
            "missingness": "PRESENT" if result in {"PASS", "BLOCK", "OBSERVE"} else "MISSING",
            "input_refs": [source_ref.to_payload()],
        }
    )
    validate_contract("RunnerProtocolResult", payload)
    return payload


def _evaluate(
    program,
    instrument_id: str,
    primary_value: str,
    *,
    protocol_result: dict | None = None,
    protocol_definition=None,
):
    head, label, output = _primary_contracts(instrument_id, primary_value)
    primary = primary_probability_from_contracts(head, label, output)
    supporting = ()
    if protocol_result is not None:
        supporting = score_inputs_from_protocol_result(
            program,
            protocol_result,
            protocol_definition=protocol_definition.to_payload(),
        )
    return evaluate_score_row(
        program,
        instrument_id=instrument_id,
        session_id=_SESSION,
        primary_probability=primary,
        supporting_inputs=supporting,
        target_environment_namespace="test",
    )


def test_fixture_score_is_manifest_bound_and_stays_fixture_only() -> None:
    program = fixture_score_program()

    assert program.parameter_set.fixture_only
    assert program.parameter_set.calibration_state.value == "FIXTURE_ONLY"
    assert program.parameters[0].input_ref.target_schema_name == _MODEL_HEAD_SCHEMA
    assert program.tie_break_rule == "SCORE_DESC_STABLE_INSTRUMENT_ID_ASC"

    with pytest.raises(ScoreActivationDenied, match="fixture-only"):
        _program(environment_namespace="production")


def test_score_manifest_and_definition_hashes_are_enforced() -> None:
    _, manifest, definition = _program()
    changed_manifest = copy.deepcopy(manifest)
    changed_manifest["score_unit"] = "probability"
    with pytest.raises(ScoreManifestError, match="invalid ScoreManifest"):
        load_score_program(
            changed_manifest,
            definition,
            target_environment_namespace="test",
        )

    changed_definition = copy.deepcopy(definition)
    changed_definition["coefficients"][0] = "0.600000000000"
    with pytest.raises(ScoreManifestError, match="invalid ScoreDefinition"):
        load_score_program(
            manifest,
            changed_definition,
            target_environment_namespace="test",
        )


def test_primary_probability_is_bound_to_exact_label_and_stays_separate() -> None:
    program, _, _ = _program()
    instrument_id = _INSTRUMENT_ID
    definition_record, source_ref = _protocol_definition()
    result = _protocol_result(definition_record, source_ref, instrument_id)

    evaluated = _evaluate(
        program,
        instrument_id,
        "0.750000000000",
        protocol_result=result,
        protocol_definition=definition_record,
    )

    assert evaluated.disposition is ScoreDisposition.SCORED
    assert evaluated.primary_probability == Decimal("0.750000000000")
    assert evaluated.score == Decimal("54.166667")
    assert evaluated.score != evaluated.primary_probability
    assert not hasattr(evaluated, "confidence")
    assert not hasattr(evaluated, "readiness")


def test_primary_probability_missingness_cannot_produce_a_successful_score() -> None:
    program, _, _ = _program(with_support=False)
    head, label, output = _primary_contracts(_INSTRUMENT_ID)
    output["availability"] = "UNAVAILABLE_MODEL"
    output["output_value"] = None
    output["reason_code"] = "MODEL_NOT_AVAILABLE"
    validate_contract("ModelHeadOutput", output)
    primary = primary_probability_from_contracts(head, label, output)

    evaluated = evaluate_score_row(
        program,
        instrument_id=_INSTRUMENT_ID,
        session_id=_SESSION,
        primary_probability=primary,
        supporting_inputs=(),
        target_environment_namespace="test",
    )

    assert evaluated.disposition is ScoreDisposition.UNSCORABLE
    assert evaluated.score is None
    assert evaluated.primary_probability is None
    assert evaluated.reason_codes == ("PRIMARY_PROBABILITY_UNAVAILABLE_MODEL",)


def test_protocol_result_must_bind_its_runner_definition() -> None:
    program, _, _ = _program()
    instrument_id = _INSTRUMENT_ID
    definition_record, source_ref = _protocol_definition()
    result = _protocol_result(definition_record, source_ref, instrument_id)
    result["protocol_ref"]["content_hash"] = "b" * 64

    with pytest.raises(ScoreInputError, match="does not bind"):
        score_inputs_from_protocol_result(
            program,
            result,
            protocol_definition=definition_record.to_payload(),
        )


def test_protocol_evidence_unit_is_frozen_in_the_score_transform() -> None:
    program, _, _ = _program()
    definition_record, source_ref = _protocol_definition()
    result = _protocol_result(definition_record, source_ref, _INSTRUMENT_ID)
    result["evidence_values"][0]["unit"] = "USD/share"
    validate_contract("RunnerProtocolResult", result)

    with pytest.raises(ScoreInputError, match="unit differs"):
        score_inputs_from_protocol_result(
            program,
            result,
            protocol_definition=definition_record.to_payload(),
        )


def test_safety_protocol_results_cannot_be_score_inputs() -> None:
    safety_ref = {
        "target_schema_name": "qc2.scientific_definitions.SafetyProtocolResult.v1",
        "target_id": "018f0000-0000-7000-8000-000000000107",
    }
    with pytest.raises(ScoreManifestError, match="safety"):
        ScoreInputRef.from_payload(safety_ref)

    with pytest.raises(ScoreManifestError, match="safety"):
        materialize_score_definition(
            definition_id=_DEFINITION_ID,
            created_at=_CREATED,
            stable_key="unsafe_fixture",
            version=1,
            input_refs=(
                ScoreInputRef(_MODEL_HEAD_SCHEMA, _PRIMARY_HEAD_ID),
                safety_ref,
            ),
            coefficients=("0.500000000000", "0.500000000000"),
            transforms=("HEAD_OUTPUT|IDENTITY", "HEAD_OUTPUT|IDENTITY"),
            clipping_policy="CLIP_TO_0_100",
            missing_head_policy="BLOCK_ROW",
            tie_break_rule="SCORE_DESC_STABLE_INSTRUMENT_ID_ASC",
            evidence_class="SYNTHETIC_FIXTURE",
            environment_namespace="test",
        )


def test_missing_required_protocol_head_is_unscorable_with_typed_reason() -> None:
    program, _, _ = _program()
    instrument_id = _INSTRUMENT_ID
    definition_record, source_ref = _protocol_definition()
    result = _protocol_result(
        definition_record,
        source_ref,
        instrument_id,
        result="UNAVAILABLE",
        direction="UNKNOWN",
    )

    evaluated = _evaluate(
        program,
        instrument_id,
        "0.750000000000",
        protocol_result=result,
        protocol_definition=definition_record,
    )

    assert evaluated.disposition is ScoreDisposition.UNSCORABLE
    assert evaluated.score is None
    assert evaluated.primary_probability == Decimal("0.750000000000")
    assert evaluated.reason_codes == (
        "REQUIRED_SCORE_INPUT_UNAVAILABLE:PROTOCOL_EVIDENCE:structure_value@fraction",
    )
    assert evaluated.missing_components[0].availability is ScoreInputAvailability.MISSING
    assert evaluated.missing_components[0].reason_code == "PROTOCOL_UNAVAILABLE"
    assert evaluated.missing_components[0].handling == "BLOCKED_ROW"


@pytest.mark.parametrize(
    ("missing_policy", "expected_score", "expected_handling"),
    [
        ("EXPLICIT_PENALTY", Decimal("20.000000"), "EXPLICIT_PENALTY"),
        ("OMIT_WITH_SEPARATE_STATUS", Decimal("25.000000"), "OMITTED_ZERO_CONTRIBUTION"),
    ],
)
def test_optional_missingness_uses_frozen_policy_and_is_reported(
    missing_policy: str,
    expected_score: Decimal,
    expected_handling: str,
) -> None:
    program, _, _ = _program(missing_policy=missing_policy)
    instrument_id = _INSTRUMENT_ID
    definition_record, source_ref = _protocol_definition()
    result = _protocol_result(
        definition_record,
        source_ref,
        instrument_id,
        result="UNAVAILABLE",
        direction="UNKNOWN",
    )

    evaluated = _evaluate(
        program,
        instrument_id,
        "0.500000000000",
        protocol_result=result,
        protocol_definition=definition_record,
    )

    assert evaluated.disposition is ScoreDisposition.SCORED
    assert evaluated.score == expected_score
    assert evaluated.missing_components[0].handling == expected_handling


def test_quantized_score_ties_use_stable_instrument_id() -> None:
    program, _, _ = _program(with_support=False)
    higher_raw = "018f0000-0000-7000-8000-000000000109"
    lower_raw = "018f0000-0000-7000-8000-000000000108"
    evaluations = (
        _evaluate(program, higher_raw, "0.500000000001"),
        _evaluate(program, lower_raw, "0.500000000000"),
    )
    assert evaluations[0].score == evaluations[1].score == Decimal("50.000000")

    ranking = rank_score_evaluations(
        program,
        evaluations,
        target_environment_namespace="test",
    )
    assert [row.instrument_id for row in ranking.rows] == [lower_raw, higher_raw]
    assert [row.rank for row in ranking.rows] == [1, 2]


@pytest.mark.parametrize(
    (
        "failure_coefficient",
        "failure_transform",
        "expected_disposition",
        "expected_score",
    ),
    [
        (
            "-0.500000000000",
            "IDENTITY",
            ScoreDisposition.SCORED,
            Decimal("32.500000"),
        ),
        ("0.500000000000", "IDENTITY", ScoreDisposition.UNSCORABLE, None),
        ("-0.500000000000", "COMPLEMENT", ScoreDisposition.UNSCORABLE, None),
    ],
)
def test_failure_probability_cannot_raise_the_score(
    failure_coefficient: str,
    failure_transform: str,
    expected_disposition: ScoreDisposition,
    expected_score: Decimal | None,
) -> None:
    primary_ref = ScoreInputRef(_MODEL_HEAD_SCHEMA, _PRIMARY_HEAD_ID)
    failure_ref = ScoreInputRef(_MODEL_HEAD_SCHEMA, _FAILURE_HEAD_ID)
    definition = materialize_score_definition(
        definition_id=_DEFINITION_ID,
        created_at=_CREATED,
        stable_key="fixture_failure_head",
        version=1,
        input_refs=(primary_ref, failure_ref),
        coefficients=("0.500000000000", failure_coefficient),
        transforms=("HEAD_OUTPUT|IDENTITY", f"HEAD_OUTPUT|{failure_transform}"),
        clipping_policy="CLIP_TO_0_100",
        missing_head_policy="BLOCK_ROW",
        tie_break_rule="SCORE_DESC_STABLE_INSTRUMENT_ID_ASC",
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="test",
    )
    manifest = materialize_score_manifest(
        manifest_id=_MANIFEST_ID,
        created_at=_CREATED,
        frozen_at=_CREATED,
        definition=definition,
    )
    program = load_score_program(manifest, definition, target_environment_namespace="test")

    primary_head, label, primary_output = _primary_contracts(
        _INSTRUMENT_ID, "0.750000000000"
    )
    primary = primary_probability_from_contracts(primary_head, label, primary_output)
    failure_head = _fixture_contract("ModelHeadDefinition")
    failure_head.update(
        {
            "id": _FAILURE_HEAD_ID,
            "created_at": _CREATED,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "head_name": "fixture_failure_probability",
            "output_kind": "FAILURE",
            "label_ref": primary_head["label_ref"],
            "horizon_sessions": 1,
            "availability": "AVAILABLE",
            "output_precision": 12,
        }
    )
    validate_contract("ModelHeadDefinition", failure_head)
    failure_output = _fixture_contract("ModelHeadOutput")
    failure_output.update(
        {
            "id": new_uuidv7(),
            "created_at": _CREATED,
            "evidence_class": "SYNTHETIC_FIXTURE",
            "environment_namespace": "test",
            "head_ref": {
                "target_schema_name": _MODEL_HEAD_SCHEMA,
                "target_id": _FAILURE_HEAD_ID,
            },
            "instrument_ref": {
                "target_schema_name": "qc2.identity_market.Instrument.v1",
                "target_id": _INSTRUMENT_ID,
            },
            "session_id": _SESSION,
            "output_value": "0.100000000000",
            "output_unit": "probability",
            "availability": "AVAILABLE",
            "reason_code": None,
        }
    )
    validate_contract("ModelHeadOutput", failure_output)
    supporting = score_input_from_head_output(failure_head, failure_output)

    evaluated = evaluate_score_row(
        program,
        instrument_id=_INSTRUMENT_ID,
        session_id=_SESSION,
        primary_probability=primary,
        supporting_inputs=(supporting,),
        target_environment_namespace="test",
    )

    assert evaluated.disposition is expected_disposition
    assert evaluated.score == expected_score
    if expected_disposition is ScoreDisposition.UNSCORABLE:
        assert evaluated.reason_codes == ("FAILURE_PROBABILITY_CANNOT_RAISE_SCORE",)


@pytest.mark.parametrize(
    ("evidence_class", "message"),
    [
        ("SYNTHETIC_FIXTURE", "fixture-only"),
        ("FORWARD_SEALED", "no calibration-attested"),
    ],
)
def test_fixture_and_uncalibrated_scores_are_denied_in_production(
    evidence_class: str,
    message: str,
) -> None:
    with pytest.raises(ScoreActivationDenied, match=message):
        _program(
            evidence_class=evidence_class,
            environment_namespace="production",
        )


def test_explicit_missing_penalty_cannot_reward_a_missing_head() -> None:
    with pytest.raises(ScoreManifestError, match="cannot increase"):
        _program(
            missing_policy="EXPLICIT_PENALTY",
            missing_penalty="0.100000000000",
        )
