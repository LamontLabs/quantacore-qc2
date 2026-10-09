# QC2-054 — Owner API Read Models

## Acceptance assessment

- **Result:** PASS
- **Acceptance gate:** All owner views are permissioned projections with traceable canonical sources.
- **Dependency preflight:** `python3 tools/task_workflow.py preflight QC2-054` passed.
- **Source tested:** Integrated source at commit `65f45005a30fb829ff718db8fa4cf2e7f7c42d1e`.
- **Verification:** Re-ran the owner API acceptance checks because the merged implementation had no canonical acceptance receipt. Typecheck passed, all 9 HTTP tests passed, all 50 owner API Python tests passed, the fresh UTF-8 PostgreSQL migration and projection acceptance passed, and the API workflow returned the minimal health response `{"status":"ok"}`.
- **Environment limits:** Verification used local test fixtures and an isolated disposable PostgreSQL cluster. No production data, credentials, or activation authority were used.

## Acceptance checklist

- [x] DELIVERABLE: Today/Predictions/Validation/Models/System/Positions/Alerts/Reports read schemas. | evidence: `packages/owner_api/schemas/v1` defines the view payload schemas; `tests/owner_api/test_read_models.py` exercises their typed projection payloads.
- [x] DELIVERABLE: Bounded pagination, stable sort, projection sequence/lag and redacted errors. | evidence: `packages/owner_api/src/qc2_owner_api/read_models.py`, `artifacts/api-server/src/routes/ownerRead.ts`, and `artifacts/api-server/src/lib/ownerReadStore.ts`; HTTP and PostgreSQL tests cover cursor bounds, stable ordering, sequence/lag, stale labeling, and redacted failures.
- [x] DELIVERABLE: Minimal public liveness and private detailed diagnostics. | evidence: `artifacts/api-server/src/routes/health.ts` exposes the minimal liveness response; authenticated diagnostics are covered by `artifacts/api-server/test/ownerRead.test.ts`.
- [x] TEST: Unauthenticated/object-ID guessing cannot read sensitive state. | evidence: `artifacts/api-server/test/ownerRead.test.ts` rejects unauthenticated reads and invalid evidence IDs without calling the store; `tests/owner_api/run_qc2_054_postgres_integration.mjs` verifies runtime-role boundaries.
- [x] TEST: Projection rebuild matches source receipts; stale data remains labeled. | evidence: `tests/owner_api/run_qc2_054_postgres_integration.mjs` rebuilds from hashed source receipts, pages the snapshot, advances the source high-water mark, and verifies stale state and lag.
- [x] TEST: Large exports and invalid pagination are bounded. | evidence: `artifacts/api-server/test/ownerRead.test.ts` rejects partial, over-count, and oversized exports plus duplicate/oversized query parameters and invalid cursors.
