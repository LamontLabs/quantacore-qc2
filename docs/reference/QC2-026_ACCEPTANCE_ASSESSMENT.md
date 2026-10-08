# QC2-026 — Validation Authority Acceptance Assessment

## Acceptance assessment

- **Result:** PASS
- **Acceptance gate:** Known fixture metrics and decision boundaries match independently computed results; policy remains nonproduction.
- **Assessment:** The independent metric fixture matches its hand calculation: operating Precision@10 is `0.1`, comparator Precision@10 is `0`, and the paired difference is `0.1` with matching lower and upper bounds. The precision ratio is explicitly undefined for a zero comparator denominator. Unknown outcomes produce conservative bounds; zero events, missing outcomes, undeclared calibration gates, unregistered iid methods, and inadequate effective blocks cannot produce PASS.
- **Prospective controls:** Qualification binds sealed operating runs and checkpoints to scheduled sessions and deadlines. Holdout access is content-addressed, tied to one epoch, limited to the frozen field and metric set, and denied until the schedule closes and the latest deadline passes.
- **Production boundary:** This implements policy and framework only. Evidence is synthetic test data; no empirical threshold, production calibration, or live trading authority is claimed.
- **Legacy reference intake:** No legacy repository or file was inspected or modified, so no legacy intake record is applicable.

## Acceptance checklist

- [x] DELIVERABLE: Metric definitions, frozen qualification receipts, scheduled-opportunity ledger. | evidence: `packages/validation_authority/src/qc2_validation_authority/authority.py`, `migrations/0004_validation_authority.sql`, `tests/database/qc2_026_postgres_acceptance.sql`
- [x] DELIVERABLE: Coverage/unknown bounds, comparator pairing, dependence-method interfaces. | evidence: `packages/validation_authority/src/qc2_validation_authority/metrics.py`, `packages/validation_authority/src/qc2_validation_authority/statistics.py`, `tests/validation_authority/test_metrics.py`, `tests/validation_authority/test_splitting_statistics.py`
- [x] DELIVERABLE: PASS/FAIL/INSUFFICIENT_EVIDENCE state logic with unevaluated calibration gates. | evidence: `packages/validation_authority/src/qc2_validation_authority/statistics.py`, `tests/validation_authority/test_splitting_statistics.py`
- [x] TEST: Train/test overlap, fake all-row test metrics, feed mismatch, holdout reuse and missing denominator tests. | evidence: `tests/validation_authority/`, `python3 -m pytest -q tests/validation_authority`
- [x] TEST: Broker profit/failure and future labels cannot change qualification. | evidence: `tests/validation_authority/test_authority.py`, `python3 -m pytest -q tests/validation_authority`
- [x] TEST: Zero events, undefined ratios, missing labels and inadequate blocks return honest states. | evidence: `tests/validation_authority/test_metrics.py`, `tests/validation_authority/test_splitting_statistics.py`
