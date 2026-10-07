# QC2-022 — Baseline Engines: BLOCKED

## Blocker assessment

- **Checked at:** 2026-10-07T21:13:21Z (UTC)
- **Canonical status:** BLOCKED; no acceptance receipt is recorded.
- **Unmet dependencies:** QC2-012, QC2-013, QC2-014, QC2-015, and QC2-021 are canonically BLOCKED.
- **Preflight evidence:** `python3 tools/task_workflow.py preflight QC2-022` failed with `preflight failed: QC2-012 is not PASS; QC2-013 is not PASS; QC2-014 is not PASS; QC2-015 is not PASS; QC2-021 is not PASS`.

## Dependency state

- QC2-012 remains blocked by QC2-011. QC2-010 now has a PASS acceptance receipt supported by authenticated read-only capability measurements and six `DataCapabilityManifest` records. The evidence supports only a proposed, explicitly pinned IEX completed-daily diagnostic regime; SIP is unavailable, exact provider-side delay is unmeasured, and broad-universe coverage is unresolved. See `docs/reference/QC2-010_BLOCKED_REPORT.md` and `docs/reference/QC2-012_BLOCKED_REPORT.md`.
- QC2-013 and QC2-014 remain blocked by QC2-012; QC2-015 remains blocked by QC2-013 and QC2-014. See their linked blocker reports.
- QC2-021 remains blocked by QC2-013, QC2-017, and QC2-020; see `docs/reference/QC2-021_BLOCKED_REPORT.md`.

## Work status and scope boundary

- No random seed-set, momentum, relative-volume, breakout, or equal-weight percentile-composite engine was implemented.
- No baseline equations, manifests, full-row disposition accounting, Top-K/percentile conventions, or tie conventions were selected.
- No tests were run for deterministic rankings, zero denominators, missing rows, all ties, renamed instruments, random seed protection, or outcome-independent weights.
- No fixture parameters or benchmark values were activated, and no competing official scanner was introduced.

## Resume conditions

1. Complete QC2-011 and QC2-012 with their required evidence and PASS receipts; QC2-010 is now PASS.
2. Complete QC2-013, QC2-014, QC2-015, and QC2-021 with their required evidence and PASS receipts.
3. Re-run QC2-022 preflight before implementing the baseline engines.

Until these dependencies pass, no comparator ranking or baseline evidence is asserted.
