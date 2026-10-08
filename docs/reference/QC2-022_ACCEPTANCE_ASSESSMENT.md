# QC2-022 — Baseline Engines acceptance assessment

## Acceptance assessment

- **Result:** PASS
- **Evidence class:** SYNTHETIC_FIXTURE
- **Environment:** test
- **Scope:** deterministic, offline comparator rankers over a validated eligible universe and point-in-time feature snapshots. No outcomes, labels, live providers, network access, or model artifacts are inputs.
- **Random baseline:** hashes canonical QC2 JSON for each preregistered seed, epoch, session, and stable instrument UUIDv7. The manifest freezes the normalized seed-set hash, and evaluation returns every seed ranking.
- **Momentum baselines:** use the registered simple close-to-close `return_1`, `return_5`, and `return_20` feature values; larger returns rank higher.
- **Relative volume:** uses the registered `relative_volume` feature, with its positive session lookback recorded in the baseline algorithm and bound to a configuration-manifest reference; larger values rank higher.
- **Breakout proximity:** uses `(max(prior highs) - H_t) / max(prior highs)`, with current-session high excluded and the positive lookback recorded in the manifest; smaller values rank higher.
- **Transparent composite:** averages the five oriented cross-sectional midrank percentiles with fixed weight `1/5` each. Component ranks use the composite's complete scoreable intersection; missing rows remain explicitly unscorable rather than changing other baselines' input sets.
- **Ranking conventions:** average-rank percentile is `(number of better rows + 0.5 × number of tied rows) / scoreable row count`; higher percentile is always better. Final score ties sort by stable instrument UUIDv7. Top-K is exact and fails when fewer than K rows are scoreable. Top 10 is primary; Top 1 and Top 5 are secondary.
- **Identity and missingness:** ticker/display-symbol labels are output-only; UUIDv7 instrument identity determines membership and ties. A missing feature snapshot or feature value retains its row with a reason code, including `DIVISION_BY_ZERO`.
- **Activation boundary:** synthetic values are test-only. Baseline manifests reject the production environment; no calibrated production lookbacks or scanner are introduced.
- **Reference Champion boundary:** the master specification separately requires a frozen F0 Reference Champion. QC2-022 does not train, select, or load that model; the later model registration and competition tasks own that artifact. This acceptance covers the comparator engines and shared ranking rules only, and does not claim the full F0 comparison set is registered.
- **Verification:** `uv run pytest -q` passed 246 tests; `uv run ruff check`, `uv run python -m compileall -q packages tests`, `git diff --check`, and `python3 tools/task_workflow.py preflight QC2-022` passed. Full registry validation will be repeated after the acceptance workflow regenerates the task documents.

## Acceptance checklist

- [x] DELIVERABLE: Random seed-set, momentum, relative-volume, breakout and equal-weight percentile composite engines. | evidence: `packages/science/src/qc2_science/baselines.py`; `tests/science/test_baseline_engines.py`
- [x] DELIVERABLE: Baseline manifests and full-row disposition accounting. | evidence: `materialize_baseline_manifest`, `evaluate_baseline_manifest`, and complete eligible-row results in `packages/science/src/qc2_science/baselines.py`
- [x] DELIVERABLE: Top-K/percentile and tie conventions shared by later evaluation. | evidence: shared `PRIMARY_REPORTING_K`, `SECONDARY_REPORTING_K`, `select_top_k`, `select_top_percentile`, and `scoreable_intersection` APIs
- [x] TEST: Identical universe/cutoff input gives deterministic ranks. | evidence: `test_identical_universe_and_cutoff_produce_deterministic_ranks`
- [x] TEST: Zero denominators, missing rows, all ties and renamed instruments handled explicitly. | evidence: `test_zero_denominator_and_missing_snapshot_keep_reason_coded_rows`; `test_all_ties_use_average_percentiles_and_stable_id_top_k`
- [x] TEST: Random seeds and composite weights cannot be optimized against outcomes. | evidence: `test_random_seed_set_is_preregistered_deterministic_and_never_selects_one_seed`; fixed `1/5` equation has no outcome or weight input
