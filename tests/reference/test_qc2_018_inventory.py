from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.validate_qc2_018_inventory import validate_inventory  # noqa: E402

INVENTORY_PATH = (
    REPO_ROOT
    / "docs"
    / "reference"
    / "QC2-018_PROTOCOL_INVENTORY.json"
)


def _inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def test_complete_scoped_inventory_has_hash_hypothesis_data_need_and_disposition() -> None:
    inventory = _inventory()
    assert len(inventory["protocols"]) == 139
    assert validate_inventory(inventory) == []

    for row in inventory["protocols"]:
        assert row["identity"].endswith(":" + row["path"])
        assert row["git_blob_sha1"]
        assert row["hypothesis"].strip()
        assert row["data_need"].strip()
        assert row["migration_disposition"] == "IGNORE"
        assert row["regime_status"] == "SOURCE_UNRESOLVED"
        assert row["source_test_status"] == "NOT_RUN"
        assert row["source_test_coverage"]
        assert row["license_and_provenance"]
        assert row["disposition_reason"]

    assert len(inventory["support_sources"]) == 2
    assert all(source["git_blob_sha1"] for source in inventory["support_sources"])


def test_id_collisions_and_duplicate_path_are_explicit() -> None:
    inventory = _inventory()
    rows = inventory["protocols"]
    engine_t09 = [
        row for row in rows
        if row["namespace"] == "Engine-T" and row["protocol_id"] == "T09"
    ]
    assert len(engine_t09) == 2
    assert engine_t09[0]["git_blob_sha1"] == engine_t09[1]["git_blob_sha1"]

    for protocol_id in ("T01", "T09"):
        collisions = [row for row in rows if row["protocol_id"] == protocol_id]
        assert {row["repository"] for row in collisions} == {
            "Lamont-Labs/QuantraCore-Engine",
            "Lamont-Labs/QuantraCore-Apex",
        }
        assert all(row["conflicts"] for row in collisions)


def test_unreviewed_learning_and_monster_namespaces_do_not_infer_meaning() -> None:
    rows = _inventory()["protocols"]
    unreviewed = [
        row for row in rows
        if row["namespace"] in {"Apex-LP", "Apex-MR"}
    ]
    assert len(unreviewed) == 45
    assert all(row["source_review"] == "TREE_METADATA_ONLY" for row in unreviewed)
    assert all(row["hypothesis"].startswith("UNKNOWN:") for row in unreviewed)
    assert all(row["data_need"].startswith("UNKNOWN;") for row in unreviewed)


def test_t24_t25_t34_source_conflicts_and_numeric_limits_remain_unresolved() -> None:
    rows = _inventory()["protocols"]
    apex_tier = {
        row["protocol_id"]: row
        for row in rows
        if row["namespace"] == "Apex-T"
        and row["protocol_id"] in {"T24", "T25", "T34"}
    }
    assert set(apex_tier) == {"T24", "T25", "T34"}
    assert "ATR breakout" in apex_tier["T24"]["hypothesis"]
    assert "arithmetic mean" in apex_tier["T25"]["hypothesis"]
    assert "Rate-of-change momentum" in apex_tier["T34"]["hypothesis"]
    assert all(row["conflicts"] for row in apex_tier.values())
    assert all(row["numeric_representation"] == "FLOAT_ARITHMETIC" for row in apex_tier.values())
    assert all(row["f0_compatibility"] == "UNVERIFIED" for row in apex_tier.values())
    assert all(row["regime_status"] != "ACTIVE_F0" for row in apex_tier.values())


def test_intraday_float_only_and_unresolved_dependencies_fail_active_f0_gate() -> None:
    inventory = copy.deepcopy(_inventory())
    row = next(row for row in inventory["protocols"] if row["protocol_id"] == "T24")
    row.update(
        regime_status="ACTIVE_F0",
        f0_compatibility="VERIFIED",
        intraday_dependency=True,
        numeric_representation="FLOAT_ARITHMETIC",
        activation_blockers=[],
    )

    errors = validate_inventory(inventory)
    assert any("intraday or unknown dependency" in error for error in errors)
    assert any("exact numeric semantics" in error for error in errors)
