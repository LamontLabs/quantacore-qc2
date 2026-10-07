import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MASTER_SPEC = ROOT / "docs/GEN2_MASTER_SPEC.md"
AUTHORITY_MODEL = ROOT / "docs/AUTHORITY_MODEL.md"
CONSTITUTION = ROOT / "docs/GEN2_CONSTITUTION.md"
DECISION_LOG = ROOT / "docs/DECISION_LOG.md"
UNKNOWN_LEDGER = ROOT / "docs/UNKNOWN_LEDGER.md"
CHANGE_CLASSIFICATION = ROOT / "docs/CHANGE_CLASSIFICATION.md"


def _table_rows(text: str, expected_header: tuple[str, ...]) -> list[list[str]]:
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue

        table: list[list[str]] = []
        for row_line in lines[start:]:
            if not row_line.strip().startswith("|"):
                break
            cells = [cell.strip() for cell in row_line.strip().strip("|").split("|")]
            if cells and all(set(cell) <= {"-", ":", " "} for cell in cells):
                continue
            table.append(cells)

        if table and tuple(table[0]) == expected_header:
            return table[1:]

    raise AssertionError(f"Markdown table not found with header: {expected_header}")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_each_canonical_state_domain_has_exactly_one_spec_owner() -> None:
    spec_rows = _table_rows(
        _text(MASTER_SPEC),
        ("Authority", "Sole canonical write responsibility", "Forbidden responsibility"),
    )
    model_rows = _table_rows(
        _text(AUTHORITY_MODEL),
        (
            "Canonical state domain",
            "Sole owning authority",
            "Sole canonical write responsibility",
            "Explicit non-responsibility",
            "Planned authority task coverage",
        ),
    )

    expected = [row[0] for row in spec_rows]
    actual = [row[0] for row in model_rows]
    owners = [row[1] for row in model_rows]

    assert len(expected) == len(set(expected))
    assert len(actual) == len(set(actual))
    assert actual == expected
    assert owners == actual
    assert all(row[2].strip() and row[3].strip() for row in model_rows)
    assert all(re.search(r"QC2-\d{3}", row[4]) for row in model_rows)


def test_all_24_invariants_have_one_owner_and_a_planned_test() -> None:
    spec_rows = _table_rows(_text(MASTER_SPEC), ("ID", "Invariant"))
    mapped_rows = _table_rows(
        _text(AUTHORITY_MODEL),
        (
            "Invariant ID",
            "Requirement summary",
            "Primary enforcement owner",
            "Planned enforcement test",
            "Planned task coverage",
        ),
    )

    expected = {row[0] for row in spec_rows}
    actual = [row[0] for row in mapped_rows]
    assert expected == {f"INV-{number:03d}" for number in range(1, 25)}
    assert len(actual) == len(set(actual))
    assert set(actual) == expected
    assert all(row[2].strip() and row[3].strip() for row in mapped_rows)
    assert all(re.search(r"QC2-\d{3}", row[4]) for row in mapped_rows)
    assert all("TBD" not in row[2].upper() + row[3].upper() for row in mapped_rows)


def test_required_contradictions_are_reviewed_and_have_verification_plans() -> None:
    rows = _table_rows(
        _text(AUTHORITY_MODEL),
        (
            "Review ID",
            "Apparent contradiction",
            "Governing resolution",
            "Planned verification",
        ),
    )
    by_id = {row[0]: row for row in rows}

    assert {"CR-EXEC-EXIT", "CR-BOOTSTRAP", "CR-ACTIVATION"} <= by_id.keys()
    exit_resolution = by_id["CR-EXEC-EXIT"][2].lower()
    assert "new exposure" in exit_resolution and "exit readiness" in exit_resolution
    assert "does not liquidate" in exit_resolution
    bootstrap_resolution = by_id["CR-BOOTSTRAP"][2]
    assert "`NO_CHAMPION`" in bootstrap_resolution
    assert "cannot overwrite" in bootstrap_resolution
    activation_resolution = by_id["CR-ACTIVATION"][2].lower()
    assert "owner" in activation_resolution and "prospective" in activation_resolution
    assert all(row[3].strip() for row in by_id.values())


def test_unresolved_ledger_rows_have_no_production_value_or_fallback() -> None:
    rows = _table_rows(
        _text(UNKNOWN_LEDGER),
        (
            "ID",
            "Required decision class",
            "Unresolved scope",
            "Sole canonical record owner",
            "Resolution evidence",
            "Current approved production value",
            "Consequence while unresolved",
        ),
    )

    assert len(rows) >= 15
    for row in rows:
        assert row[0].strip()
        assert row[1] in {
            "OWNER_POLICY_REQUIRED",
            "CAPABILITY_MEASUREMENT_REQUIRED",
            "EMPIRICAL_CALIBRATION_REQUIRED",
            "ENGINEERING_LIMIT_REQUIRED",
        }
        assert row[3].strip()
        assert row[4].strip()
        assert row[5].startswith("NONE")
        consequence = row[6].lower()
        assert any(term in consequence for term in ("block", "disabled", "no feed-dependent"))


def test_f0_scope_and_frozen_champion_default_are_explicit() -> None:
    constitution = _text(CONSTITUTION)
    assert "private" in constitution.lower()
    assert "single-owner" in constitution
    assert "daily OHLCV" in constitution
    assert "Alpaca Paper" in constitution
    assert "**`FROZEN_CHAMPION`**" in constitution
    assert "`PRE_REGISTERED_ADAPTIVE`" in constitution
    assert "before activation" in constitution


def test_change_classes_and_revalidation_procedure_are_complete() -> None:
    rows = _table_rows(
        _text(CHANGE_CLASSIFICATION),
        (
            "Class",
            "Meaning",
            "Minimum decision/proof",
            "Epoch and authority effect",
        ),
    )
    classes = {row[0].split(" ", maxsplit=1)[0] for row in rows}

    assert classes == {"C0", "C1", "C2", "C3", "C4"}
    content = re.sub(r"\s+", " ", _text(CHANGE_CLASSIFICATION)).lower()
    for required in (
        "owner-approved constitutional amendment",
        "`NEEDS_REVALIDATION`",
        "migration",
        "effective boundary",
        "new epoch",
        "exact, prospective activation request",
    ):
        assert required.lower() in content


def test_qc2_002_has_no_authorized_legacy_sources() -> None:
    registry = json.loads((ROOT / "registry/BUILD_TASKS.json").read_text(encoding="utf-8"))
    task = next(item for item in registry["tasks"] if item["task_id"] == "QC2-002")

    assert task["authorized_legacy_references"] == []
    assert task["required_reference_intake"].startswith("None.")


def test_decision_log_does_not_claim_unrecorded_owner_approval_or_activation() -> None:
    decisions = re.sub(r"\s+", " ", _text(DECISION_LOG))
    assert "does not claim owner signatures" in decisions
    assert "does not select, qualify, register, or name a Champion" in decisions
    assert "This decision log does not activate F0." in decisions
    assert "no legacy references" in decisions.lower()
