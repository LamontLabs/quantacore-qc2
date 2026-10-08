# QC2-018 — Acceptance assessment

- **Result:** PASS
- **Checked:** 2026-10-07
- **Scope:** Historical Protocol Lineage Registry for the pinned Engine and Apex snapshots described in `QC2-018_REFERENCE_INTAKE.md`.

## Acceptance assessment

The Engine tree was retrieved completely at its pinned commit. The Apex recursive tree was truncated, so it was not represented as complete; instead, the Apex `protocols/` namespace and each child directory were retrieved separately at the pinned commit. The resulting 139 protocol source-file records are qualified by repository, commit, and exact path and include a Git blob hash, hypothesis, data need, test coverage/status, license/provenance, and one disposition.

The source-backed T24/T25/T34 findings and their conflicts with Apex tier documentation are explicit. Cross-repository T01/T09 collisions and Engine's byte-identical nested T09 duplicate remain path-qualified. Meanings or data needs not established from source are marked `UNKNOWN` and remain excluded. All entries are `IGNORE` / `SOURCE_UNRESOLVED`; none is `ACTIVE_F0`. The validator rejects activation with unresolved or intraday dependencies or non-exact numeric semantics.

No legacy source was copied, imported, edited, or executed. No legacy test suite was run. The observed upstream test limitations, Engine license gap, Apex demo/evaluation-only production restriction, and unverified historical origin are recorded. This task does not claim that the inspected snapshots are the original historical project or that any source is licensed for production use.

## Acceptance checklist

- [x] DELIVERABLE: Complete discovered protocol inventory with source hash, hypothesis, data need and disposition. | evidence: `docs/reference/QC2-018_PROTOCOL_INVENTORY.json`; `python3 tools/validate_qc2_018_inventory.py`
- [x] DELIVERABLE: Verified or unresolved T24/T25 and T34 records; compatibility map. | evidence: `docs/reference/QC2-018_REFERENCE_INTAKE.md`; `docs/reference/QC2-018_PROTOCOL_INVENTORY.json`
- [x] DELIVERABLE: Migration acceptance criteria and no-unresolved-active-dependency rule. | evidence: `docs/reference/QC2-018_REFERENCE_INTAKE.md`
- [x] TEST: Every discovered original file maps to one disposition. | evidence: `tests/reference/test_qc2_018_inventory.py`; 5 tests passed
- [x] TEST: ID collisions and unavailable source meanings remain explicit. | evidence: `tests/reference/test_qc2_018_inventory.py`; 5 tests passed
- [x] TEST: Intraday/float-only dependencies cannot become ACTIVE_F0. | evidence: `tests/reference/test_qc2_018_inventory.py`; hostile activation fixture rejected

## Executed verification

- `python3 tools/validate_qc2_018_inventory.py` — PASS; 139 path-qualified source files; no unresolved, intraday-only, or float-only source is `ACTIVE_F0`.
- `pytest -q tests/reference/test_qc2_018_inventory.py` — 5 passed.
- `ruff check tests/reference/test_qc2_018_inventory.py tools/validate_qc2_018_inventory.py` — PASS.
- `python3 tools/task_workflow.py preflight QC2-018` — PASS; declared dependencies and acceptance evidence are available.
