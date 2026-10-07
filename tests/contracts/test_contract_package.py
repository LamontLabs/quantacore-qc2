from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from qc2_contracts.catalog import (
    AUTHORITY_OVERRIDES,
    CONTENT_ADDRESSED,
    SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS,
    contract_rows,
)
from qc2_contracts.runtime import (
    CONTRACTS,
    ContractValidationError,
    assert_immutable_update,
    assert_transition,
    artifact_inventory_hash,
    canonical_content_hash,
    canonical_decimal_text,
    canonical_json_bytes,
    contract_metadata,
    domain_separated_sha256,
    new_uuidv7,
    parse_json_strict,
    scientific_payload_hash,
    validate_contract,
    validate_contract_collection,
    verify_content_hash,
)


FIXTURE_SECOND_ID = "018f0000-0000-7000-8000-000000000002"
FIXTURE_THIRD_ID = "018f0000-0000-7000-8000-000000000003"


def _invalid_fixtures(root: Path) -> list[dict[str, Any]]:
    path = root / "packages/contracts/fixtures/v1/invalid.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _serialization_vectors(root: Path) -> dict[str, str]:
    path = root / "packages/contracts/fixtures/v1/serialization-golden-vectors.properties"
    return {
        key: value
        for line in path.read_text(encoding="ascii").splitlines()
        if line and not line.startswith("#")
        for key, value in [line.split("=", 1)]
    }


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
    assert len(actual) == 124
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
        if name in CONTENT_ADDRESSED:
            included = set(schema["x-qc2"]["content_hash_fields"])
            excluded = set(schema["x-qc2"]["content_hash_excluded_fields"])
            assert included.isdisjoint(excluded)
            assert included | excluded == set(schema["properties"])
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
    with pytest.raises(ContractValidationError, match="representable across platforms"):
        canonical_json_bytes({"value": 9_007_199_254_740_992})
    assert canonical_json_bytes({"\ue000": 1, "\U00010000": 2}).hex() == (
        "7b22ee8080223a312c22f0908080223a327d"
    )


def test_qc2_serialization_golden_vectors(
    project_root: Path,
    valid_contract_fixtures: dict[str, dict[str, Any]],
) -> None:
    vectors = _serialization_vectors(project_root)
    decomposed = base64.b64decode(vectors["canonical.value_base64"]).decode("utf-8")
    canonical = canonical_json_bytes({"z": decomposed, "a": [True, None, 7]})
    assert canonical.hex() == vectors["canonical.expected_bytes_hex"]
    control_value = base64.b64decode(vectors["canonical.control_value_base64"]).decode(
        "utf-8"
    )
    assert canonical_json_bytes(control_value).hex() == vectors[
        "canonical.control_expected_hex"
    ]
    assert domain_separated_sha256(vectors["canonical.domain"], canonical) == vectors[
        "canonical.expected_hash"
    ]
    assert domain_separated_sha256("qc2.golden.other.v1", canonical) != vectors[
        "canonical.expected_hash"
    ]

    assert canonical_decimal_text(
        vectors["decimal.negative_zero"],
        precision=int(vectors["decimal.fixed_precision"]),
    ) == vectors["decimal.expected_zero"]
    assert canonical_decimal_text(
        vectors["decimal.trailing_zero_input"]
    ) == vectors["decimal.trailing_zero_expected"]
    with pytest.raises(ContractValidationError, match="exactly 12"):
        canonical_decimal_text("0.5", precision=12)
    with pytest.raises(ContractValidationError, match="without exponent"):
        canonical_decimal_text("1e2")

    files = [
        {
            "relative_path": vectors[f"artifact.{index}.relative_path"],
            "length_bytes": int(vectors[f"artifact.{index}.length_bytes"]),
            "media_type": vectors[f"artifact.{index}.media_type"],
            "schema_name": vectors[f"artifact.{index}.schema_name"],
            "schema_version": vectors[f"artifact.{index}.schema_version"],
            "sha256": vectors[f"artifact.{index}.sha256"],
        }
        for index in range(int(vectors["artifact.count"]))
    ]
    assert artifact_inventory_hash(files) == vectors["artifact.expected_hash"]
    assert artifact_inventory_hash(list(reversed(files))) == vectors["artifact.expected_hash"]
    with pytest.raises(ContractValidationError, match="relative paths"):
        artifact_inventory_hash([{**files[0], "relative_path": "C:/private/model.bin"}])
    with pytest.raises(ContractValidationError, match="unique after Unicode normalization"):
        artifact_inventory_hash(
            [
                {**files[0], "relative_path": "models/e\u0301.bin"},
                {**files[1], "relative_path": "models/é.bin"},
            ]
        )
    with pytest.raises(ContractValidationError, match="nonnegative safe integer"):
        artifact_inventory_hash([{**files[0], "length_bytes": -1}])
    manifest = deepcopy(valid_contract_fixtures["ArtifactManifest"])
    manifest.update(
        id=vectors["artifact.manifest_id"],
        created_at=vectors["artifact.manifest_created_at"],
        owning_authority=vectors["artifact.manifest_authority"],
        evidence_class=vectors["artifact.manifest_evidence_class"],
        environment_namespace=vectors["artifact.manifest_environment_namespace"],
        source_refs=[],
        content_hash="a" * 64,
        files=files,
        inventory_hash=artifact_inventory_hash(files),
        manifest_version=int(vectors["artifact.manifest_version"]),
        detached_signature=vectors["artifact.manifest_signature"],
        transport_hash=vectors["artifact.manifest_transport_hash"],
    )
    manifest_hash = canonical_content_hash("ArtifactManifest", manifest)
    assert manifest_hash == vectors["artifact.manifest_expected_hash"]
    manifest["content_hash"] = manifest_hash
    verify_content_hash("ArtifactManifest", manifest)
    changed_manifest_envelope = deepcopy(manifest)
    changed_manifest_envelope.update(
        id="018f0000-0000-7000-8000-000000000030",
        created_at="2026-10-07T12:00:00Z",
        content_hash="f" * 64,
        detached_signature="Ag",
        transport_hash="c" * 64,
    )
    assert (
        canonical_content_hash("ArtifactManifest", changed_manifest_envelope)
        == manifest_hash
    )

    payload = valid_contract_fixtures["ScientificPredictionPayload"]
    assert list(SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS) == [
        "session_id",
        "reference_kind",
        "reference_price",
        "instrument_ref",
        "horizon_label_refs",
        "head_output_refs",
        "dependency_refs",
        "score",
        "rank",
        "disposition",
        "model_hash",
        "epoch_ref",
        "regime",
    ]
    metadata = contract_metadata("ScientificPredictionPayload")
    assert metadata["scientific_payload_fields"] == list(
        SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS
    )
    assert set(metadata["scientific_payload_fields"]).isdisjoint(
        metadata["operational_envelope_fields"]
    )
    assert scientific_payload_hash(payload) == vectors["scientific.expected_hash"]
    changed_envelope = deepcopy(payload)
    changed_envelope.update(
        id=vectors["scientific.envelope_id"],
        created_at=vectors["scientific.envelope_created_at"],
        evidence_class="SYNTHETIC_FIXTURE",
        environment_namespace="development",
        source_refs=[
            {
                "target_schema_name": CONTRACTS["DailyBar"][1],
                "target_id": FIXTURE_SECOND_ID,
            }
        ],
        content_hash="f" * 64,
    )
    assert scientific_payload_hash(changed_envelope) == vectors["scientific.expected_hash"]
    changed_science = deepcopy(payload)
    changed_science["score"] = "50.000001"
    assert scientific_payload_hash(changed_science) != vectors["scientific.expected_hash"]


def test_uuidv7_ids_are_valid_and_distinct() -> None:
    generated = [new_uuidv7() for _ in range(32)]
    assert len(generated) == len(set(generated))
    before_ms = time.time_ns() // 1_000_000
    for value in generated:
        parsed = uuid.UUID(value)
        assert parsed.version == 7
        assert parsed.variant == uuid.RFC_4122
        timestamp_ms = int.from_bytes(parsed.bytes[:6], "big")
        assert 0 < timestamp_ms <= before_ms


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
    changed_identity = deepcopy(outcome)
    changed_identity.update(
        id=FIXTURE_SECOND_ID,
        created_at="2026-10-07T17:00:00Z",
        content_hash="f" * 64,
    )
    assert canonical_content_hash("Outcome", changed_identity) == positive_zero_hash
    verify_content_hash("Outcome", outcome)

    feature = copy_payload(valid_contract_fixtures["FeatureSnapshot"])
    feature_value = feature["feature_values"][0]
    feature_value["missing_reason"] = "WARMUP_REQUIRED"
    feature_hash = canonical_content_hash("FeatureSnapshot", feature)
    feature["content_hash"] = feature_hash
    verify_content_hash("FeatureSnapshot", feature)

    manifest = copy_payload(valid_contract_fixtures["ArtifactManifest"])
    manifest["inventory_hash"] = artifact_inventory_hash(manifest["files"])
    manifest_hash = canonical_content_hash("ArtifactManifest", manifest)
    manifest["content_hash"] = manifest_hash
    reordered = copy_payload(manifest)
    reordered["files"].reverse()
    assert artifact_inventory_hash(reordered["files"]) == manifest["inventory_hash"]
    assert canonical_content_hash("ArtifactManifest", reordered) == manifest_hash
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
            "--lib",
            "ES2022,DOM",
            "packages/contracts/src/qc2_contracts/generated.ts",
            "packages/contracts/src/qc2_contracts/serialization.ts",
        ],
        cwd=project_root,
        check=True,
        timeout=120,
    )


def test_cross_language_serialization_golden_vectors(
    project_root: Path, tmp_path: Path
) -> None:
    vectors = project_root / "packages/contracts/fixtures/v1/serialization-golden-vectors.properties"
    if shutil.which("pnpm") is not None and shutil.which("node") is not None:
        output_dir = tmp_path / "typescript"
        subprocess.run(
            [
                "pnpm",
                "exec",
                "tsc",
                "--strict",
                "--target",
                "ES2022",
                "--module",
                "commonjs",
                "--lib",
                "ES2022,DOM",
                "--outDir",
                str(output_dir),
                "packages/contracts/src/qc2_contracts/serialization.ts",
            ],
            cwd=project_root,
            check=True,
            timeout=120,
        )
        subprocess.run(
            [
                "node",
                "tests/contracts/serialization_smoke.cjs",
                str(output_dir / "serialization.js"),
                str(vectors),
            ],
            cwd=project_root,
            check=True,
            timeout=30,
        )

    compiler = shutil.which("kotlinc")
    java = shutil.which("java")
    if compiler is None or java is None:
        pytest.skip("Kotlin compiler and Java are unavailable in this environment")
    jar_path = tmp_path / "qc2-serialization-vectors.jar"
    subprocess.run(
        [
            compiler,
            "packages/contracts/android/Qc2Serialization.kt",
            "packages/contracts/android/Qc2SerializationSmoke.kt",
            "-include-runtime",
            "-d",
            str(jar_path),
        ],
        cwd=project_root,
        check=True,
        timeout=180,
    )
    subprocess.run(
        [java, "-jar", str(jar_path), str(vectors)],
        check=True,
        timeout=30,
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
