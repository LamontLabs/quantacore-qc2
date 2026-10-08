# QC2-025 — Prediction Authority Acceptance Receipt

## Acceptance assessment

- **Result:** PASS
- **Scope:** One canonical run per validation epoch and session; all eligible symbols are accounted for; run, row, payload, and seal state is immutable after sealing.
- **Evidence class/environment:** `SYNTHETIC_FIXTURE` / `test`
- **Outcome:** Champion and registry bindings are captured before scoring. Retry behavior is bounded and deterministic; late completion remains diagnostic and cannot qualify the run. SQL acceptance ran against an isolated UTF8 PostgreSQL 16 test database in a serializable rollback-only transaction.
- **Boundaries:** No legacy source was inspected or modified. No production fixture was enabled, no provider/feed fallback was added, and no downstream task was started.

## Acceptance checklist

- [x] DELIVERABLE: ScheduledAttempt binding, run/row state machines, immutable scientific payload and seals. | evidence: `packages/prediction_authority/src/qc2_prediction_authority/authority.py`; `packages/prediction_authority/src/qc2_prediction_authority/models.py`; `migrations/0003_prediction_authority.sql`; `tests/prediction_authority/test_prediction_authority.py`
- [x] DELIVERABLE: Early Champion/registry pinning and unique official seal constraints. | evidence: `packages/prediction_authority/src/qc2_prediction_authority/authority.py`; `migrations/0003_prediction_authority.sql`; `tests/database/qc2_025_postgres_acceptance.sql`
- [x] DELIVERABLE: Bounded deterministic retries, late-run diagnostics and anchor integration port. | evidence: `packages/prediction_authority/src/qc2_prediction_authority/authority.py`; `packages/prediction_authority/src/qc2_prediction_authority/anchor.py`; `tests/prediction_authority/test_prediction_authority.py`
- [x] TEST: Concurrent run creation/Champion change cannot produce mixed generations. | evidence: `tests/prediction_authority/test_prediction_authority.py::test_concurrent_run_creation_and_champion_rotation_keep_one_generation`
- [x] TEST: All eligible symbols appear ranked or unscorable; tie order is deterministic. | evidence: `tests/prediction_authority/test_prediction_authority.py::test_complete_inventory_tie_order_and_scientific_payload_hashes`
- [x] TEST: Mutation after seal, favorable retry replacement, late qualification and fixture activation are rejected. | evidence: `tests/prediction_authority/test_prediction_authority.py::test_retry_repairs_only_retryable_unscorable_rows_within_budget`; `tests/prediction_authority/test_prediction_authority.py::test_seal_is_immutable_and_late_completion_is_diagnostic`; `tests/prediction_authority/test_prediction_authority.py::test_fixture_evidence_cannot_create_a_production_run`; `tests/prediction_authority/test_prediction_authority.py::test_anchor_port_verifies_checkpoint_and_rejects_late_qualification`

## Verification

- `pnpm test` — 284 Python tests passed; database environment guards passed (7 tests).
- `pnpm run lint` — Ruff and Prettier checks passed.
- `QC2_ENV=test QC2_POSTGRES_TEST_URL=postgresql://postgres@127.0.0.1:55439/qc2_test_qc225 QC2_EXPECTED_DATABASE_TEST=qc2_test_qc225 pnpm exec node lib/db/test/run-qc2-025-postgres-integration.mjs` — QC2-005, QC2-006, and QC2-025 PostgreSQL acceptance passed; all DDL and fixtures rolled back.
- `python3 tools/task_workflow.py preflight QC2-025` — passed.
