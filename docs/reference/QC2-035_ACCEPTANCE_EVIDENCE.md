# QC2-035 — Model Factory acceptance evidence

## Acceptance assessment

- **Result:** PASS
- **Scope:** Research-only model training for the frozen linear, logistic, Random Forest, Gradient Boosting, and XGBoost families. The trainer receives only governed training and validation rows; qualification labels remain sealed.
- **Evidence class/environment:** SYNTHETIC_FIXTURE / test.
- **Reference intake:** No external or legacy repositories were inspected. The implementation uses the current ApexLab dataset, split, budget, model-manifest, and artifact-manifest contracts.
- **Safety boundary:** No broker or production credentials are passed to the trainer. Model exports are JSON-only; no model promotion, qualification, production write, or downstream evaluator work was performed.

## Acceptance checklist

- [x] DELIVERABLE: Linear/logistic, Random Forest, Gradient Boosting and XGBoost training adapters. | evidence: `packages/apexlab/src/qc2_apexlab/_model_worker.py` fits each supported family and returns a reason-coded incompatibility for unsupported family/task pairs; `tests/apexlab/test_model_factory.py::test_fixture_competition_trains_all_families_on_identical_governed_inputs` exercises eight family/task cases.
- [x] DELIVERABLE: Frozen seeds, parameter spaces, safe artifact export and environment manifests. | evidence: `packages/apexlab/src/qc2_apexlab/model_factory.py` freezes the parameter grids and seed, writes only strict JSON model/parameter/environment files, binds package versions and lockfile hash, and validates the generated QC2 manifests.
- [x] DELIVERABLE: Bounded CPU/memory/time jobs with calibration/preprocessing lineage. | evidence: the worker runs with OS CPU and address-space limits, one native thread, an allowlisted credential-free environment, and a bounded wall clock; model artifacts record transform/index hashes, fit rows, feature order, calibration-not-applied state, and resource provenance.
- [x] TEST: Equivalent fixture competition uses the same splits and permitted targets. | evidence: `tests/apexlab/test_model_factory.py::test_fixture_competition_trains_all_families_on_identical_governed_inputs` verifies identical dataset, split, and budget hashes, sealed qualification inputs, and provenance-complete candidates for all eight cases.
- [x] TEST: Budget exhaustion and interrupted export preserve honest failure state. | evidence: `tests/apexlab/test_model_factory.py::test_memory_budget_exhaustion_is_reason_coded_and_exports_nothing` and `tests/apexlab/test_model_factory.py::test_interrupted_export_cleans_staging_directory_and_returns_no_candidate`.
- [x] TEST: No production write, broker access or qualification-label read from trainer credentials. | evidence: `ModelTrainingRequest` contains only training-index and validation rows; `test_fixture_competition_trains_all_families_on_identical_governed_inputs` checks that only the explicit environment allowlist reaches the worker, including when broker, database, and session sentinels are present.

## Verification runs

- `uv run pytest tests/apexlab -q` — 49 passed, 0 failed.
- `uv run ruff check packages/apexlab/src/qc2_apexlab tests/apexlab` — all checks passed.
- `python3 tools/task_workflow.py validate` — task registry, acceptance records, and generated documentation valid before acceptance recording.
