# QC2-022 — Baseline Engines eligibility reconciliation

## Eligibility

- **Checked at:** 2026-10-08 (UTC).
- **Canonical status:** `TODO`; no acceptance receipt is recorded.
- Dependencies QC2-012, QC2-013, QC2-014, QC2-015, and QC2-021 are PASS with receipts.
- `python3 tools/task_workflow.py preflight QC2-022` passes.
- The previous BLOCKED status and HTTP-401 dependency statement were stale. QC2-010 through QC2-015 and QC2-021 now have PASS receipts; no Alpaca credential values were accessed or exposed during this reconciliation.

## Scope boundary before implementation

- No random seed-set, momentum, relative-volume, breakout, or equal-weight percentile-composite engine has been implemented yet.
- Baseline equations, manifests, full-row disposition accounting, Top-K/percentile conventions, tie conventions, and pinned fixture parameters remain to be implemented and verified.
- No fixture parameters or benchmark values have been activated, and no competing official scanner has been introduced.

## Next gate

Start QC2-022 through `task_workflow.py start` after the registry correction is integrated. Implement only the required local comparator framework and synthetic-fixture checks; do not add live trading, provider fallback, or outcome-based tuning.
