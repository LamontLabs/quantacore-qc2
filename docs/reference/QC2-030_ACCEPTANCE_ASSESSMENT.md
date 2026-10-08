# QC2-030 — Matched Decoy Engine

## Acceptance assessment

- **Result:** PASS
- The engine freezes a date/regime risk set and a deterministic, scaled-L1
  matching policy before outcome membership is applied. It retains unmatched
  positives, never backfills controls rejected by later outcome evidence, and
  records feature-level lineage, reuse, class-prior weights, and the original
  population reference.

## Acceptance checklist

- [x] DELIVERABLE: Date/regime risk-set matcher, frozen caliper/distance policy and MatchedDecoySet. | evidence: `packages/apexlab/src/qc2_apexlab/decoy_engine.py`, `packages/apexlab/src/qc2_apexlab/decoy_models.py`, `packages/apexlab/src/qc2_apexlab/__init__.py`
- [x] DELIVERABLE: Reuse/unmatched accounting, training sample weights and original-population references. | evidence: `packages/apexlab/src/qc2_apexlab/decoy_engine.py`, `tests/apexlab/test_matched_decoys.py`
- [x] DELIVERABLE: Cutoff-safe matching feature extraction. | evidence: `packages/apexlab/src/qc2_apexlab/decoy_engine.py`, `tests/apexlab/test_matched_decoys.py`
- [x] TEST: No outcome variable enters distance or caliper selection. | evidence: `tests/apexlab/test_matched_decoys.py::test_outcome_variables_cannot_be_selected_and_extra_outcome_fields_do_not_change_distance`
- [x] TEST: Same-date candidates and repeated decoy reuse are recorded. | evidence: `tests/apexlab/test_matched_decoys.py::test_same_stratum_matches_record_reuse_weights_and_calibration_boundary`
- [x] TEST: Case-control sampling cannot be mistaken for natural-prevalence calibration. | evidence: `tests/apexlab/test_matched_decoys.py::test_same_stratum_matches_record_reuse_weights_and_calibration_boundary`

## Verification

- Focused regression tests: 5 passed.
- Full Python test suite: 334 passed.
- Ruff checks passed for the new engine, models, package exports, and tests.
- QC2-030 dependency and acceptance preflight passed.
