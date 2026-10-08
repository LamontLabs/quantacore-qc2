# QC2-028 — Runner Genome System

## Acceptance assessment

- **Result:** PASS
- **Acceptance gate:** Every genome and index lookup proves temporal eligibility for the consumer cutoff.
- **Verification:** The append-only in-memory store validates source contracts and hashes, requires resolved positive outcomes before creating a RunnerGenome, records pre-event snapshots and lineage, and keeps actual creation/learning timestamps separate from explicit historical assumptions. Index membership is cutoff-filtered and bound to the builder version, exact member refs, and cutoff. Lookups validate the selected temporal dependency closure; later unrelated catalog entries do not change an earlier empty-index proof. Empty predictions remain explicitly absent.
- **Validation:** `pnpm run verify` passed, including lint, type checks, 318 Python tests, 7 database guards, 2 smoke tests, and task-registry validation. The focused ApexLab suite passed all 3 tests; Ruff and compile checks for the new package and tests passed.
- **Scope:** Synthetic fixture and code evidence only. This is an in-memory research reference, not durable persistence or production learning. No similarity ranking, trading behavior, runtime provider fallback, or legacy DNA/memory sources are included.

## Acceptance checklist

- [x] DELIVERABLE: RunnerGenome schema/store, pre-event snapshots, resolved facts and lineage. | evidence: `packages/apexlab/src/qc2_apexlab/store.py` validates resolved outcomes, pre-event snapshots, source lineage, and temporal availability; `tests/apexlab/test_runner_genome.py` covers genome creation and lookup.
- [x] DELIVERABLE: Versioned cutoff-filtered memory index and actual creation/learning times. | evidence: `packages/apexlab/src/qc2_apexlab/models.py` binds builder version, cutoff, and exact member refs; `packages/apexlab/src/qc2_apexlab/store.py` filters membership and retains actual and reconstructed times separately.
- [x] DELIVERABLE: Missing-contemporaneous-prediction representation. | evidence: `prediction_refs` remains empty when no prediction is supplied, and `RunnerGenomeRecord.prediction_capture_status` reports `ABSENT`; asserted in `tests/apexlab/test_runner_genome.py`.
- [x] TEST: An April 15 success cannot be retrieved by an April 11 simulated decision. | evidence: `test_april_15_success_is_not_visible_to_april_11_decision` verifies the April 11 index remains empty, its proof revision remains stable after the later genome is added, and the genome is eligible at the April 15 cutoff.
- [x] TEST: Changing an index member changes the index hash and replay dependency. | evidence: `test_changed_index_membership_changes_hash_and_replay_dependency` compares one-member and two-member indexes and verifies their inventory hashes, content hashes, replay refs, and lookup results differ.
- [x] TEST: Outcome-derived embeddings cannot enter an earlier feature view. | evidence: `test_outcome_derived_embedding_is_rejected_from_earlier_feature_view` verifies the temporal firewall rejects a feature snapshot whose transform manifest depends on an outcome unavailable at the feature cutoff, and rejects the same dependency in an index lookup.
