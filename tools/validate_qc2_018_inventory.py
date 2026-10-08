"""Validate the source-backed QC2-018 inventory and F0 exclusion rules."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

EXPECTED_NAMESPACE_COUNTS = {
    "Engine-T": 13,
    "Apex-T": 80,
    "Apex-LP": 25,
    "Apex-MR": 20,
    "Apex-Omega": 1,
}
VALID_DISPOSITIONS = {"REUSE", "ADAPT", "TESTS_ONLY", "REWRITE", "IGNORE"}
VALID_REGIME_STATUSES = {
    "RESEARCH",
    "ACTIVE_F0",
    "UNAVAILABLE_IN_F0",
    "RETIRED",
    "SOURCE_UNRESOLVED",
}
EXACT_NUMERIC_REPRESENTATIONS = {"EXACT_DECIMAL", "EXACT_INTEGER"}
GIT_BLOB_SHA1 = re.compile(r"^[0-9a-f]{40}$")


def validate_inventory(document: dict[str, Any]) -> list[str]:
    """Return contract violations; never infer protocol meaning from a bare ID."""
    errors: list[str] = []
    rows = document.get("protocols")
    if not isinstance(rows, list) or not rows:
        return ["protocols must be a non-empty list"]

    identities: set[str] = set()
    actual_counts: dict[str, int] = {}
    for index, row in enumerate(rows):
        prefix = f"protocols[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        identity = row.get("identity")
        if not isinstance(identity, str) or not identity:
            errors.append(f"{prefix} is missing a path-qualified identity")
        elif identity in identities:
            errors.append(f"duplicate path-qualified identity: {identity}")
        else:
            identities.add(identity)

        namespace = row.get("namespace")
        if not isinstance(namespace, str) or not namespace:
            errors.append(f"{prefix} is missing a namespace")
        else:
            actual_counts[namespace] = actual_counts.get(namespace, 0) + 1

        if not isinstance(row.get("path"), str) or not row["path"]:
            errors.append(f"{prefix} is missing a source path")
        if not GIT_BLOB_SHA1.fullmatch(str(row.get("git_blob_sha1", ""))):
            errors.append(f"{prefix} has an invalid Git blob SHA-1")
        if not isinstance(row.get("hypothesis"), str) or not row["hypothesis"].strip():
            errors.append(f"{prefix} is missing an explicit hypothesis or UNKNOWN")
        if not isinstance(row.get("data_need"), str) or not row["data_need"].strip():
            errors.append(f"{prefix} is missing an explicit data need or UNKNOWN")
        for field in (
            "source_test_status",
            "source_test_coverage",
            "license_and_provenance",
            "disposition_reason",
        ):
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append(f"{prefix} is missing {field}")
        if row.get("migration_disposition") not in VALID_DISPOSITIONS:
            errors.append(f"{prefix} has no valid migration disposition")
        if row.get("regime_status") not in VALID_REGIME_STATUSES:
            errors.append(f"{prefix} has no valid regime status")

        if row.get("regime_status") == "ACTIVE_F0":
            if row.get("f0_compatibility") != "VERIFIED":
                errors.append(f"{prefix} is ACTIVE_F0 without verified F0 compatibility")
            if row.get("intraday_dependency") is not False:
                errors.append(f"{prefix} is ACTIVE_F0 with an intraday or unknown dependency")
            if row.get("numeric_representation") not in EXACT_NUMERIC_REPRESENTATIONS:
                errors.append(f"{prefix} is ACTIVE_F0 without exact numeric semantics")
            if row.get("activation_blockers"):
                errors.append(f"{prefix} is ACTIVE_F0 with unresolved activation blockers")

    if actual_counts != EXPECTED_NAMESPACE_COUNTS:
        errors.append(
            f"namespace inventory mismatch: expected {EXPECTED_NAMESPACE_COUNTS}, "
            f"found {actual_counts}"
        )
    if document.get("counts", {}).get("total_protocol_source_files") != len(rows):
        errors.append("declared total_protocol_source_files does not match protocols")
    if document.get("counts", {}).get("by_repository_namespace") != actual_counts:
        errors.append("declared namespace counts do not match protocols")

    support_sources = document.get("support_sources")
    if not isinstance(support_sources, list) or len(support_sources) != 2:
        errors.append("both inspected Engine support files must have intake records")
    else:
        for index, row in enumerate(support_sources):
            prefix = f"support_sources[{index}]"
            for field in (
                "identity",
                "path",
                "git_blob_sha1",
                "source_supported_meaning",
                "tests",
                "license_and_provenance",
                "disposition",
            ):
                if not row.get(field):
                    errors.append(f"{prefix} is missing {field}")
            if not GIT_BLOB_SHA1.fullmatch(str(row.get("git_blob_sha1", ""))):
                errors.append(f"{prefix} has an invalid Git blob SHA-1")
            if row.get("disposition") not in VALID_DISPOSITIONS:
                errors.append(f"{prefix} has no valid disposition")
            if not isinstance(row.get("conflicts"), list):
                errors.append(f"{prefix} conflicts must be a list")

    engine_t09 = [
        row
        for row in rows
        if row.get("namespace") == "Engine-T" and row.get("protocol_id") == "T09"
    ]
    if len(engine_t09) != 2 or len({row.get("git_blob_sha1") for row in engine_t09}) != 1:
        errors.append("the two Engine T09 paths must be present and byte-identical by Git blob")

    for protocol_id in ("T01", "T09"):
        cross_repo = [
            row
            for row in rows
            if row.get("protocol_id") == protocol_id
            and row.get("repository")
            in {"Lamont-Labs/QuantraCore-Engine", "Lamont-Labs/QuantraCore-Apex"}
        ]
        if not any(row.get("repository") == "Lamont-Labs/QuantraCore-Engine" for row in cross_repo):
            errors.append(f"{protocol_id} is missing its Engine identity")
        if not any(row.get("repository") == "Lamont-Labs/QuantraCore-Apex" for row in cross_repo):
            errors.append(f"{protocol_id} is missing its Apex identity")
        if not all(row.get("conflicts") for row in cross_repo):
            errors.append(f"{protocol_id} collision must remain explicitly documented")

    for protocol_id in ("T24", "T25", "T34"):
        matches = [
            row
            for row in rows
            if row.get("repository") == "Lamont-Labs/QuantraCore-Apex"
            and row.get("namespace") == "Apex-T"
            and row.get("protocol_id") == protocol_id
        ]
        if len(matches) != 1:
            errors.append(f"Apex {protocol_id} must have one pinned inventory record")
            continue
        row = matches[0]
        if not row.get("conflicts"):
            errors.append(f"Apex {protocol_id} documentation conflict is not recorded")
        if row.get("regime_status") == "ACTIVE_F0":
            errors.append(f"Apex {protocol_id} cannot become ACTIVE_F0 from legacy evidence alone")

    completeness = document.get("tree_completeness", {})
    if completeness.get("engine_recursive_tree_truncated") is not False:
        errors.append("Engine inventory must be based on its complete, non-truncated tree")
    if completeness.get("apex_recursive_tree_is_not_used_as_complete_inventory") is not True:
        errors.append("Apex truncated recursive tree must not be represented as complete")

    policy = document.get("inventory_policy", {}).get("active_f0_gate", "")
    if "intraday-only or float-only" not in policy:
        errors.append("F0 policy must explicitly prohibit intraday-only and float-only dependencies")
    return errors


def main() -> int:
    inventory_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "reference"
        / "QC2-018_PROTOCOL_INVENTORY.json"
    )
    document = json.loads(inventory_path.read_text(encoding="utf-8"))
    errors = validate_inventory(document)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(
        "QC2-018 inventory valid: "
        f"{len(document['protocols'])} path-qualified protocol source files; "
        "no unresolved, intraday-only, or float-only source is ACTIVE_F0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
