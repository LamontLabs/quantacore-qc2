# QC2-033 — ApexLab Dataset Builder

## Acceptance assessment

- **Result:** PASS
- The builder creates content-addressed DatasetManifest, SplitManifest, and row-lineage contracts. Stable logical row keys deduplicate identical inputs and reject conflicting duplicates. Source artifacts are exported through TemporalFirewall at each fold cutoff; labels are released only when their learning-availability time is strictly before that cutoff. Label intervals crossing fold boundaries are excluded while all rows for a session remain in one stage. Embargo length is enforced against the largest declared horizon. Each fold fits its transform and training index from mature, non-purged training rows only, and explicit sample-weight sources are re-exported only for released training rows. Qualification exports request features only; qualification rows and their lineage omit Outcome and weight-source references.

## Acceptance checklist

- [x] DELIVERABLE: DatasetManifest/row lineage, SplitManifest, cutoff-scoped export and deduplication. | evidence: `packages/apexlab/src/qc2_apexlab/dataset_builder.py`; `packages/apexlab/src/qc2_apexlab/dataset_models.py`; `tests/apexlab/test_dataset_builder.py`
- [x] DELIVERABLE: Walk-forward train/development/qualification, purge and embargo implementation. | evidence: `packages/apexlab/src/qc2_apexlab/dataset_builder.py`; `tests/apexlab/test_dataset_builder.py::test_crossing_label_intervals_are_purged_and_sessions_stay_whole`
- [x] DELIVERABLE: Per-fold transforms/index construction and sample-weight handling. | evidence: `packages/apexlab/src/qc2_apexlab/dataset_builder.py`; `packages/apexlab/src/qc2_apexlab/dataset_models.py`; `tests/apexlab/test_dataset_builder.py::test_fold_local_fit_maturity_and_weight_export_use_real_firewall_pipeline`
- [x] TEST: Label dependency intervals crossing folds are removed; all same-session rows stay together. | evidence: `tests/apexlab/test_dataset_builder.py::test_crossing_label_intervals_are_purged_and_sessions_stay_whole`
- [x] TEST: Training-only fit and mature-only release tested through actual pipeline integration. | evidence: `tests/apexlab/test_dataset_builder.py::test_fold_local_fit_maturity_and_weight_export_use_real_firewall_pipeline`
- [x] TEST: Survivorship-limited inputs cannot claim PIT_VERIFIED. | evidence: `tests/apexlab/test_dataset_builder.py::test_survivorship_limited_rows_cannot_claim_point_in_time_fidelity`

## Verification

- Dataset-builder integration tests: 3 passed, 0 failed, 0 skipped.
- Full ApexLab suite: 34 passed, 0 failed, 0 skipped.
- Full Python suite: 349 passed, 0 failed, 0 skipped.
- Ruff checks and Python compile check passed.
- Reference intake is recorded in `docs/reference/QC2-033_REFERENCE_INTAKE.md`.
