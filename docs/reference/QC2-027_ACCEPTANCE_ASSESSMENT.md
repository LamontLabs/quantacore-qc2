# QC2-027 — Runner Observatory Acceptance Assessment

## Acceptance assessment

- **Result:** PASS
- **Acceptance gate:** Independent event detection exactly matches labeled fixture markets and its scope is explicit.
- **Verification:** The Observatory detected the expected Expansion Runner and Session Monster records on eligible census members without model or ranking inputs. Exact event count, type, and target sessions are asserted. Census omissions, missing label inputs, unscorable labels, and resolved negatives remain visible in the queue. Coverage is explicitly limited to each declared CandidateCensus; all-market completeness is never claimed.
- **Validation:** `pnpm run verify` passed, including repository lint, TypeScript checks, 315 Python tests, 7 database guard tests, smoke checks, and task-registry validation. The focused science and instrument-universe suites also passed 125 tests.
- **Scope:** Synthetic fixture evidence only. No claim of historical market completeness, production readiness, prediction quality, or trading behavior.

## Acceptance checklist

- [x] DELIVERABLE: Census-scoped event detector, coverage accounting and frozen episode primitives. | evidence: `packages/science/src/qc2_science/ground_truth_observatory.py`; census membership verification, per-census coverage, and overlap-rule tests in `tests/science/test_ground_truth_observatory.py`.
- [x] DELIVERABLE: Expansion/Monster and defined ancillary event records. | evidence: `test_low_ranked_and_unpredicted_eligible_runners_are_discovered` asserts the exact Expansion Runner and Session Monster fixture records, including event types and sessions; undefined labels remain unscorable.
- [x] DELIVERABLE: Event discovery queue for research consumers. | evidence: `EventDiscoveryQueue` records discovered, negative, missing, excluded, unverified, unobserved, and unscorable census scans with deterministic IDs and a content hash.
- [x] TEST: A low-ranked and an unpredicted eligible runner are still observed. | evidence: `test_low_ranked_and_unpredicted_eligible_runners_are_discovered`; the scanner accepts census and label inputs, not ranking or prediction inputs.
- [x] TEST: Missing census data is visible; unverified market completeness is not claimed. | evidence: `test_missing_census_data_is_visible_and_market_completeness_is_not_claimed`; it asserts missing-member and label-input counts plus census-only scope.
- [x] TEST: Repeated overlapping events follow the declared episode identity. | evidence: `test_overlapping_target_windows_share_a_frozen_episode_identity`; two census sessions resolve to one episode under the frozen inclusive transitive-overlap rule.
