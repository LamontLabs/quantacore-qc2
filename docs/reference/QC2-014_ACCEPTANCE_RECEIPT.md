# QC2-014 — Feature Authority acceptance

## Acceptance assessment

- **Result:** PASS
- **Evidence class:** SYNTHETIC_FIXTURE; the test data and empirical windows are fixtures only.
- **Environment:** test; no provider access, persistence, execution, live trading, or production activation is part of this acceptance.
- **Scope:** deterministic offline FeatureDefinition and FeatureSnapshot generation, with reason-coded missingness and fixture-profile production denial.
- **Contract boundary:** FeatureDefinition v1 was extended before any persisted or deployed feature definitions are claimed. The authorized drift and regenerated contract projections are recorded in the task registry.

## Acceptance checklist

- [x] DELIVERABLE: Feature Registry framework, required research families, dependency DAG and column order. | evidence: `packages/science/src/qc2_science/registry.py`; `tests/science/test_feature_authority.py::test_registry_contracts_cover_required_families_and_topological_column_order`
- [x] DELIVERABLE: Units, equations, warm-up, split, precision, normalization and missingness contracts. | evidence: `packages/contracts/schemas/v1/FeatureDefinition.schema.json`; `docs/reference/QC2-014_DECISION.md`; `tests/science/test_feature_authority.py`
- [x] DELIVERABLE: Fixture parameter profiles with production activation guard. | evidence: `packages/science/src/qc2_science/registry.py`; `tests/science/test_feature_authority.py::test_fixture_profile_has_no_production_activation_path`
- [x] TEST: Flat/zero-range/zero-volume/sparse/IPO/split/large-number edge cases. | evidence: `tests/science/test_feature_authority.py::test_flat_zero_range_zero_volume_and_absent_volume_are_reason_coded`; `::test_ipo_warmup_and_sparse_calendar_history_are_distinguished`; `::test_split_basis_and_scale_metamorphisms`; `::test_large_volumes_and_decimal_output_precision`
- [x] TEST: Repeated and reordered-input runs yield the same canonical snapshot. | evidence: `tests/science/test_feature_authority.py::test_snapshot_is_canonical_and_reordered_inputs_produce_identical_payload`
- [x] TEST: Metamorphic invariances and no-outcome-access tests pass. | evidence: `tests/science/test_feature_authority.py::test_split_basis_and_scale_metamorphisms`; `::test_feature_engine_has_no_outcome_import_or_external_side_effect_path`

## Implementation summary

The feature registry defines all required research families and a deterministic topological feature order. Definitions bind equations, input and output units, output data types, lookback and warm-up, session alignment, split treatment, precision, normalization, fixture profile, missingness, zero-denominator behavior, dependencies, implementation hash, and invariances.

Snapshot generation validates frozen calendar sessions, bar and metadata cutoffs, one canonical instrument, symbol-assignment continuity, and a common split-adjusted share basis. Every feature row carries its registered unit and output type and has exactly one value or missing reason. Snapshot content hashes bind the ordered feature rows, input hashes, registry, cutoff, implementation code hash, environment fingerprint, and provenance references.

Historical similarity accepts only matching-registry RunnerGenome/FailureGenome feature vectors with strictly prior event and feature-snapshot sessions. Typed temporal-access evidence binds both source artifact hashes, their availability time, the exact decision cutoff, and a strict point-in-time operation. The feature engine does not import or read outcome contracts, perform network calls, access persistence, or read mutable global state.

## Reference-source disposition

`docs/reference/QC2-014_REFERENCE_INTAKE.md` records the inspected revisions, file hashes, source-supported meanings, test coverage, conflicts, licenses, and dispositions. Inspection was read-only; no legacy file was copied, imported, modified, or executed. The ApexLab demo/evaluation license does not grant production or live-trading use, and the inspected snapshots do not establish Gen 1 identity or original-protocol lineage.

## Verification

- `python3 tools/generate_contract_package.py --check` — 124 contracts and 132 generated artifacts checked.
- `pnpm test` — 158 Python tests and 7 database guard tests passed.
- `python3 -m ruff check packages/science/src/qc2_science tests/science packages/contracts/src/qc2_contracts/catalog.py tools/generate_contract_package.py` — passed.
- `python3 tools/task_workflow.py preflight QC2-014` — dependencies and acceptance evidence available.

No production qualification, production activation, live trading authorization, provider accuracy, or owner approval is claimed.
