from __future__ import annotations

import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from qc2_contracts.catalog import AUTHORITY_OVERRIDES, CONTENT_ADDRESSED, contract_rows
from qc2_contracts.runtime import (
    CONTRACTS,
    ContractValidationError,
    assert_immutable_update,
    assert_transition,
    canonical_content_hash,
    canonical_json_bytes,
    parse_json_strict,
    validate_contract,
    validate_contract_collection,
    verify_content_hash,
)


FIXTURE_SECOND_ID = "018f0000-0000-7000-8000-000000000002"
FIXTURE_THIRD_ID = "018f0000-0000-7000-8000-000000000003"


def _invalid_fixtures(root: Path) -> list[dict[str, Any]]:
    path = root / "packages/contracts/fixtures/v1/invalid.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _complete_fixture_collection(
    valid: dict[str, dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    objects = [(name, deepcopy(payload)) for name, payload in valid.items()]
    second_manifest = deepcopy(valid["ArtifactManifest"])
    second_manifest["id"] = FIXTURE_SECOND_ID
    second_manifest["content_hash"] = "b" * 64
    objects.append(("ArtifactManifest", second_manifest))
    return objects


def test_contract_names_match_section_12(project_root: Path) -> None:
    spec = (project_root / "docs/GEN2_MASTER_SPEC.md").read_text(encoding="utf-8")
    section = spec.split("## 12. Canonical contracts and serialization", 1)[1]
    section = section.split("\n## ", 1)[0]
    expected: list[str] = []
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("| ---") or "Required objects" in line:
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) >= 2:
            expected.extend(item.strip() for item in columns[1].split(","))

    actual = [name for _, name, _ in contract_rows()]
    assert len(actual) == 121
    assert len(actual) == len(set(actual))
    assert set(actual) == set(expected)
    assert set(actual) == set(AUTHORITY_OVERRIDES)
    assert all(name in CONTRACTS for name in actual)


def test_every_schema_and_valid_fixture_pass(
    project_root: Path, valid_contract_fixtures: dict[str, dict[str, Any]]
) -> None:
    schema_dir = project_root / "packages/contracts/schemas/v1"
    assert set(valid_contract_fixtures) == set(CONTRACTS)
    for name, payload in valid_contract_fixtures.items():
        schema = json.loads((schema_dir / f"{name}.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
        assert schema["x-qc2"]["writer_role"] == AUTHORITY_OVERRIDES[name]
        assert "reader_roles" in schema["x-qc2"]
        assert "identity_fields" in schema["x-qc2"]
        assert "immutable_fields" in schema["x-qc2"]
        assert "mutable_fields" in schema["x-qc2"]
        validate_contract(name, payload)
    outcome_schema = json.loads(
        (schema_dir / "Outcome.schema.json").read_text(encoding="utf-8")
    )
    outcome_source_targets = {
        choice["properties"]["target_schema_name"]["const"]
        for choice in outcome_schema["properties"]["source_refs"]["items"]["oneOf"]
    }
    assert outcome_source_targets == {
        CONTRACTS[name][1]
        for name in ("DailyBar", "CorporateActionRecord", "MarketSnapshotRevision")
    }
    for name in CONTENT_ADDRESSED:
        assert "content_hash" in valid_contract_fixtures[name]


def test_all_invalid_fixtures_are_rejected(
    project_root: Path,
) -> None:
    invalid = _invalid_fixtures(project_root)
    assert len(invalid) >= 250
    for fixture in invalid:
        with pytest.raises(ContractValidationError):
            if fixture["kind"] == "transition":
                assert_transition(
                    fixture["contract"], fixture["from"], fixture["to"]
                )
            else:
                validate_contract(fixture["contract"], fixture["payload"])


@pytest.mark.parametrize(
    "text",
    [
        '{"x":1,"x":2}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":1.25}',
    ],
)
def test_strict_json_parser_rejects_ambiguous_or_inexact_values(text: str) -> None:
    with pytest.raises(ContractValidationError):
        parse_json_strict(text)


def test_canonical_json_normalizes_unicode_and_rejects_collisions() -> None:
    assert canonical_json_bytes({"é": "e\u0301"}) == canonical_json_bytes(
        {"é": "é"}
    )
    with pytest.raises(ContractValidationError, match="duplicate key"):
        canonical_json_bytes({"é": 1, "e\u0301": 2})
    with pytest.raises(ContractValidationError, match="binary floats"):
        canonical_json_bytes({"value": 1.25})


def test_content_hash_excludes_its_own_field_and_mutable_state(
    valid_contract_fixtures: dict[str, dict[str, Any]],
    copy_payload: Any,
) -> None:
    outcome = copy_payload(valid_contract_fixtures["Outcome"])
    endpoint_validity = next(
        item
        for item in outcome["field_validity"]
        if item["field_name"] == "endpoint_return"
    )
    endpoint_validity.update(status="VALID", reason_code=None)

    outcome["endpoint_return"] = "-0.000000000000"
    negative_zero_hash = canonical_content_hash("Outcome", outcome)
    outcome["endpoint_return"] = "0.000000000000"
    positive_zero_hash = canonical_content_hash("Outcome", outcome)
    assert negative_zero_hash == positive_zero_hash

    outcome["content_hash"] = positive_zero_hash
    verify_content_hash("Outcome", outcome)

    feature = copy_payload(valid_contract_fixtures["FeatureSnapshot"])
    feature_value = feature["feature_values"][0]
    feature_value["missing_reason"] = "WARMUP_REQUIRED"
    feature_hash = canonical_content_hash("FeatureSnapshot", feature)
    feature["content_hash"] = feature_hash
    verify_content_hash("FeatureSnapshot", feature)

    manifest = copy_payload(valid_contract_fixtures["ArtifactManifest"])
    manifest_hash = canonical_content_hash("ArtifactManifest", manifest)
    manifest["content_hash"] = manifest_hash
    manifest["detached_signature"] = "AQ"
    manifest["transport_hash"] = "b" * 64
    assert canonical_content_hash("ArtifactManifest", manifest) == manifest_hash
    verify_content_hash("ArtifactManifest", manifest)
    manifest["inventory_hash"] = "c" * 64
    assert canonical_content_hash("ArtifactManifest", manifest) != manifest_hash

    epoch = copy_payload(valid_contract_fixtures["ValidationEpoch"])
    original_hash = canonical_content_hash("ValidationEpoch", epoch)
    advanced_epoch = copy_payload(epoch)
    advanced_epoch["epoch_state"] = "READY"
    assert canonical_content_hash("ValidationEpoch", advanced_epoch) == original_hash
    with pytest.raises(ContractValidationError, match="not content-addressed"):
        canonical_content_hash("DailyBar", valid_contract_fixtures["DailyBar"])


def test_state_changes_are_guarded_and_other_fields_are_immutable(
    valid_contract_fixtures: dict[str, dict[str, Any]],
    copy_payload: Any,
) -> None:
    before = copy_payload(valid_contract_fixtures["ValidationEpoch"])
    after = copy_payload(before)
    after["epoch_state"] = "READY"
    assert_immutable_update("ValidationEpoch", before, after)

    altered = copy_payload(after)
    altered["start_session"] = "2026-10-06"
    with pytest.raises(ContractValidationError, match="immutable"):
        assert_immutable_update("ValidationEpoch", before, altered)

    with pytest.raises(ContractValidationError, match="Invalid ValidationEpoch transition"):
        assert_transition("ValidationEpoch", "CLOSED_PASS", "ACTIVE")


def test_foreign_references_resolve_and_dependency_graph_is_acyclic(
    valid_contract_fixtures: dict[str, dict[str, Any]],
    copy_payload: Any,
) -> None:
    objects = _complete_fixture_collection(valid_contract_fixtures)
    validate_contract_collection(objects)

    reverse = copy_payload(valid_contract_fixtures["ArtifactDependency"])
    reverse["id"] = FIXTURE_THIRD_ID
    reverse["parent_ref"] = {
        "target_schema_name": CONTRACTS["ArtifactManifest"][1],
        "target_id": FIXTURE_SECOND_ID,
        "content_hash": "b" * 64,
    }
    reverse["dependency_ref"] = {
        "target_schema_name": CONTRACTS["ArtifactManifest"][1],
        "target_id": valid_contract_fixtures["ArtifactManifest"]["id"],
        "content_hash": valid_contract_fixtures["ArtifactManifest"]["content_hash"],
    }
    with pytest.raises(ContractValidationError, match="cycle"):
        validate_contract_collection(objects + [("ArtifactDependency", reverse)])


def test_overlapping_symbol_assignments_are_rejected(
    valid_contract_fixtures: dict[str, dict[str, Any]],
    copy_payload: Any,
) -> None:
    objects = _complete_fixture_collection(valid_contract_fixtures)
    second_instrument = copy_payload(valid_contract_fixtures["Instrument"])
    second_instrument["id"] = FIXTURE_THIRD_ID
    second_instrument["stable_instrument_key"] = "fixture_other"
    objects.append(("Instrument", second_instrument))

    second_assignment = copy_payload(valid_contract_fixtures["SymbolAssignment"])
    second_assignment["id"] = FIXTURE_SECOND_ID
    second_assignment["instrument_ref"]["target_id"] = FIXTURE_THIRD_ID
    objects.append(("SymbolAssignment", second_assignment))
    with pytest.raises(ContractValidationError, match="multiple instruments"):
        validate_contract_collection(objects)


def test_model_head_output_uses_registered_decimal_precision(
    valid_contract_fixtures: dict[str, dict[str, Any]],
    copy_payload: Any,
) -> None:
    objects = _complete_fixture_collection(valid_contract_fixtures)
    validate_contract_collection(objects)

    mismatched = [
        (name, copy_payload(payload))
        for name, payload in objects
    ]
    output = next(payload for name, payload in mismatched if name == "ModelHeadOutput")
    output["output_value"] = "0.500000"
    with pytest.raises(ContractValidationError, match="registered head precision"):
        validate_contract_collection(mismatched)

    unavailable = [
        (name, copy_payload(payload))
        for name, payload in objects
    ]
    unavailable_output = next(
        payload for name, payload in unavailable if name == "ModelHeadOutput"
    )
    unavailable_output.update(
        availability="UNAVAILABLE_MODEL",
        output_value=None,
        reason_code="model_unavailable",
    )
    validate_contract_collection(unavailable)


def test_generated_artifacts_are_current_and_python_types_import(
    project_root: Path,
) -> None:
    subprocess.run(
        [sys.executable, "tools/generate_contract_package.py", "--check"],
        cwd=project_root,
        check=True,
        timeout=60,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "packages/contracts/src/qc2_contracts/generated.py",
        ],
        cwd=project_root,
        check=True,
        timeout=30,
    )
    from qc2_contracts.generated import Outcome, Prediction

    assert Outcome is not None
    assert Prediction is not None


def test_typescript_projection_compiles(project_root: Path) -> None:
    if shutil.which("pnpm") is None:
        pytest.skip("pnpm is unavailable in this environment")
    subprocess.run(
        [
            "pnpm",
            "exec",
            "tsc",
            "--noEmit",
            "--strict",
            "--target",
            "ES2022",
            "packages/contracts/src/qc2_contracts/generated.ts",
        ],
        cwd=project_root,
        check=True,
        timeout=120,
    )


def test_kotlin_projection_and_shared_fixtures_compile_and_run(
    project_root: Path, tmp_path: Path
) -> None:
    compiler = shutil.which("kotlinc")
    java = shutil.which("java")
    if compiler is None or java is None:
        pytest.skip("Kotlin compiler and Java are unavailable in this environment")
    jar_path = tmp_path / "qc2-wire-fixtures.jar"
    subprocess.run(
        [
            compiler,
            "packages/contracts/android/Qc2WireContracts.kt",
            "packages/contracts/android/Qc2WireFixtureSmoke.kt",
            "-include-runtime",
            "-d",
            str(jar_path),
        ],
        cwd=project_root,
        check=True,
        timeout=180,
    )
    subprocess.run([java, "-jar", str(jar_path)], check=True, timeout=30)
