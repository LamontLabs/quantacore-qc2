# QC2-021 — Runtime Safety Protocol Framework status and implementation report

## Eligibility and source disposition

- **Checked at:** 2026-10-08 (UTC).
- **Canonical status during verification:** `IN_PROGRESS`; the subsequent task workflow accepted QC2-021 as PASS.
- **Dependencies:** QC2-006, QC2-007, QC2-008, QC2-013, QC2-017, and QC2-020 are PASS with receipts; canonical preflight passes.
- The prior blocker text described QC2-013, QC2-017, and QC2-020 as not PASS. The registry correction and source intake were integrated before the canonical start; no workflow guard was bypassed.
- The requested Gen 1 QC-T01–T65 safety namespace was not found in the inspected pinned sources. Engine-T, Apex-T, and QuantraVision T-tier identifiers have different meanings and contracts. CIL is from a different domain and its license decision prohibits copying code.
- `docs/reference/QC2-021_REFERENCE_INTAKE.md` records exact revisions, paths, hashes, test coverage/status, conflicts, licensing, and exclusions. `docs/reference/QC2-021_DECISION.md` records the `IGNORE` + `SOURCE_UNRESOLVED` disposition. No legacy code or tests were imported or run.

## Implemented framework

- `packages/core/src/qc2_core/safety/models.py` defines immutable action, gate, evidence, freshness, and readiness types.
- `policies.py` defines separate frozen policies for PREDICT, NEW_ENTRY, EXIT_POSITION, CANCEL_ENTRY, and PROMOTE. Default warnings are not allowed; the public evaluator does not accept runtime policy overrides.
- `evaluator.py` evaluates only the requested action, rejects unexpected or duplicate same-action gates, and marks missing, stale, future, or mixed-generation evidence UNKNOWN. WARN is actionable only under an explicit `ALLOW_WITH_EVIDENCE` rule with reason and evidence references.
- `ports.py` supplies an explicit `UNAVAILABLE` stub only. No network, provider, broker, or live mutation integration is implemented or claimed.
- ReadinessAssessment, SafetyProtocolDefinition, and SafetyProtocolResult payloads are validated against the existing strict contracts and content hashes. Safety output is not a score or model feature input.
- EXIT_POSITION has its own narrower gates. NEW_ENTRY failures are not inherited by an otherwise passing EXIT_POSITION evaluation.

## Verification

- `python3 -m pytest -q tests/core`: 16 passed.
- `python3 -m pytest -q`: 238 passed.
- `ruff check packages/core/src/qc2_core/safety tests/core`: passed.
- `python3 -m compileall -q packages/core/src/qc2_core/safety tests/core`: passed.
- `python3 tools/task_workflow.py validate`: registry, prior acceptance records, and generated task documents validate.
- No safety package imports were found in `packages/science/src`.

No live capability or broker behavior was tested. The canonical acceptance receipt is recorded in `docs/reference/QC2-021_ACCEPTANCE_RECORD.json`, with the task record in `docs/reference/QC2-021_TASK_RECORD.json`.
