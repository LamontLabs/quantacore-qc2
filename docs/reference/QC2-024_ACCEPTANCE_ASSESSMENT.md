# QC2-024 — QuantraScore Framework Acceptance

## Acceptance assessment

- **Result:** PASS
- The content-addressed ScoreManifest pins the exact ScoreDefinition hash. Ordered references, 12-place coefficients, selectors, transforms, missing-head policy, clipping policy, and tie rule are validated before evaluation.
- The score is `100 × Σ(coefficient × transformed input)`, rounded half-even to six decimal places. Ranking occurs after quantization; equal scores sort by stable instrument ID.
- The primary Expansion Runner probability remains a separate 12-place value and must bind the exact Expansion Runner label, horizon, model head, instrument, and session. No confidence or readiness value is derived from the score.
- Missing required inputs produce reason-coded UNSCORABLE rows. Optional missing inputs follow the frozen block, omission-with-status, or explicit non-rewarding penalty policy.
- Safety protocol result references are rejected as score inputs. Protocol evidence must bind its content-addressed RunnerProtocolDefinition; each selector freezes the expected evidence unit and direction. Failure probabilities cannot raise the score under any accepted transform.
- Synthetic fixture parameter sets remain fixture-only. All other parameter sets remain uncalibrated; no production activation path exists. The fixture coefficients demonstrate mechanics only and are not empirical weights.
- No Gen 1 QuantraScore or ZDE source was inspected; no legacy reference intake was required.
- **Verification:** complete repository tests passed (277); science suite passed (110); focused QuantraScore tests passed (17); targeted Ruff and Python compilation checks passed; QC2-024 dependency preflight passed.

## Acceptance checklist

- [x] DELIVERABLE: ScoreManifest with inputs, transformations, missingness/penalty and tie rules. | evidence: exact manifest-to-definition hash binding, unit-pinned protocol selectors, transform, missingness, clipping, and stable tie tests in `tests/science/test_quantscore.py`
- [x] DELIVERABLE: Primary probability distinct from score/confidence/readiness. | evidence: primary label/head binding, separate 12-place value, and score output checks in `tests/science/test_quantscore.py`
- [x] DELIVERABLE: Calibratable parameter schema with fixture-only examples. | evidence: typed `ScoreParameterSet` and synthetic fixture builder in `packages/science/src/qc2_science/quantscore.py`
- [x] TEST: No safety input changes score; missing required head cannot silently score. | evidence: safety reference rejection, reason-coded UNSCORABLE required-input case, and failure-probability direction tests in `tests/science/test_quantscore.py`
- [x] TEST: Canonical quantization and ranking tie cases reproduce exactly. | evidence: 6-place half-even score and stable-ID tie test in `tests/science/test_quantscore.py`
- [x] TEST: Uncalibrated/fixture score cannot enter production epoch. | evidence: separate fixture-only and uncalibrated production-denial cases in `tests/science/test_quantscore.py`
