# QC2-013 — ApexLab temporal reference intake

## Inspection record

- Repository: `Lamont-Labs/QuantraCore-Apex`
- Inspected revision: `d65ad25b813977b1087b94db5f88a32963426477`
- Access: read-only GitHub connector requests; no source checkout or edits.
- Repository license metadata: `NOASSERTION`.
- License file SHA-256: `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9`.
- License text: “Demo-only/Evaluation license. No production or live trading without written consent.” It also reserves all rights and disclaims warranty.
- Disposition: audit and anti-pattern reference only. No source code was copied, imported, or executed. No production or live-trading use is claimed.

## Inspected files

| Path and SHA-256 | Source-supported meaning | Tests, conflicts, and disposition |
| --- | --- | --- |
| `docs/investor/21_LABELING_METHODS_AND_LEAKAGE_GUARDS.md` — `71fb4c942df52d8f59713a9ff5b4c93c020e5a342bf0b9f9d08d0a8e36dd03ec` | Describes intended labeling, temporal splitting, and leakage guards. It records design intent, not proof that every training path enforces point-in-time availability. | Read only. Compared its stated safeguards with the training implementation and shape tests below; conflicts are documented as risks, not adopted implementation requirements. |
| `docs/APEXLAB_CONTINUOUS_DATA_ENGINE_SPEC.md` — `aff80de04e1fd50e66132d4e0783919ee125a9104ba3b81fd0cb838f40ca5690` | Describes continuous data collection, retrospective labels, and periodic training. | Read only. The document does not establish actual receipt-time preservation or cutoff-scoped storage reads. It is not evidence of a production data pipeline. |
| `src/quantracore_apex/apexlab/training.py` — `ba79b8b0539ca076a88ebcf09d7562243b80feb6085cc342862cdfb926f45e42` | Contains feature/target extraction, walk-forward split creation, and a training cycle. | Audit conflicts: the split path falls back to row order if event time is absent; the training flow mixes future-outcome-derived values with general feature extraction, so feature/target separation must be explicit. No code was copied. |
| `src/quantracore_apex/apexlab/data_augmentation.py` — `063e8dd7f418bff00935171df1636c4cc3cda1002774a76558acd132e6bcd692` | Contains augmentation helpers, including sampling from a shared returns pool. | A shared pool does not prove fold-, cutoff-, or universe-scoped membership. Treat as a leakage risk unless the caller proves a legal pool for each fold. No code was copied. |
| `tests/lab/test_apexlab_v2_dataset_shapes.py` — `fb291eb7207129818d7718d3b69a8b631c7d94b4467e233db24f8ce45aac9af0` | Tests feature/target shapes and walk-forward split shape/disjointness. | `test_split_no_time_column` accepts a split without timestamps. The inspected tests do not establish availability-time guards, transitive dependency closure, revision/cache isolation, or leakage-free feature/target separation. The upstream tests were read but not run. |
| `LICENSE` — `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9` | Reserves all rights; allows demo/evaluation only; forbids production or live trading without written consent. | Controls disposition of all inspected source. No source was copied, modified, or used in a production/live-trading system. |

## QC2-013 disposition

The new temporal firewall is an independent implementation. It requires actual `known_at`, keeps retrospective assumptions in separate fields, scopes cache identity to the catalog and cutoff, and blocks missing or late dependency evidence. The legacy material was used only to identify failure modes. The inspected upstream test suite is not treated as validation of this implementation.

This intake records source provenance and audit observations only. It does not grant rights beyond the license, establish production readiness, or certify upstream behavior.
