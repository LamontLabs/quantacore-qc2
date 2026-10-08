# QC2-019 — F0 Runner Protocol Migration Wave 1: dependency blocker cleared

## Previous blocker record

- **Checked at:** 2026-10-07T20:57:29Z (UTC).
- **Previous status:** BLOCKED because QC2-014, QC2-017, and QC2-018 were not PASS.
- **Previous preflight:** Failed because all three dependencies were not PASS.

## Current state

- **Checked at:** 2026-10-07.
- **Status:** TODO; the dependency blocker is cleared and the task is eligible to start.
- **Dependency evidence:** QC2-014, QC2-017, and QC2-018 have PASS receipts; `python3 tools/task_workflow.py preflight QC2-019` passes.
- **Scope boundary:** QC2-018's pinned inventory records verified source paths and hashes without asserting that every requested candidate is a verified original. Candidate-specific source meaning, tests, conflicts, licensing, and disposition must be established in QC2-019 before implementation or exclusion.
- No migration implementation, exclusion, RESEARCH entry, parameter contract, evidence field, or migration test has been created yet.

## Start conditions

1. Start QC2-019 only after confirming the integrated TODO registry and generated documents.
2. Inspect only source files whose repository, pinned revision, and path are authorized and accessible.
3. Record source hash, source-supported meaning, tests, conflicts, license, and disposition for every file actually inspected; keep missing lineage/meaning unresolved.
4. Complete tests for every migrated candidate or document an evidence-backed exclusion for each unavailable or incompatible item.

No candidate is active, and no legacy behavior or threshold has been carried into Gen 2.
