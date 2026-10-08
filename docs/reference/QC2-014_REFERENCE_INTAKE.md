# QC2-014 — Feature Authority reference intake

## Inspection basis and disposition

- Inspected revisions: Apex `Lamont-Labs/QuantraCore-Apex` at `d65ad25b813977b1087b94db5f88a32963426477`; Engine `Lamont-Labs/QuantraCore-Engine` at `67597a2a63fd3957e6ec50e270dba8e3df1d3757`.
- Inspection was read-only. No legacy file was copied, imported, modified, or executed.
- The Apex repository's `LICENSE` is demo/evaluation-only and bars production/live-trading use without written consent; its SHA-256 is `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9`. No recognized root license was found for the Engine snapshot.
- No upstream tests were run. The Engine mapped tree has no tests. Apex shape tests check feature/dataset shapes and split construction, not point-in-time safety.
- These snapshots are not evidence of Gen 1 identity, original-protocol lineage, production release, or production authorization. The source manifest's role mapping is functional only.

## Inspected files

| Repository path and SHA-256 | Source-supported meaning | Test coverage, conflict, and disposition |
| --- | --- | --- |
| Apex `apexlab/features.py` — `37ac87ebb0f82acaf026171bf8f38de85d89154cb593418bf805e354deca6796` | Research feature extraction over market inputs. The inspected implementation includes optional external enrichment/fallback behavior, zero-fills missing/NaN feature values, and keeps forward-return helpers in the same module. | No point-in-time proof was established. Runtime fallback and missing-as-zero conflict with QC2 requirements; forward-return helpers stay outside the feature authority. Audit reference only; none copied or run. |
| Apex `tests/lab/test_apexlab_v2_dataset_shapes.py` — `fb291eb7207129818d7718d3b69a8b631c7d94b4467e233db24f8ce45aac9af0` | Checks V2 feature/dataset shapes and split construction. | Does not establish temporal availability, cutoff-scoped reads, or separation of feature computation from future targets. Read only; not run. |
| Apex `apexlab/apexlab_v2.py` — `52f406bee3bdaaecb3632085a5d9b001c5d12902ee46ae9f5fe20bd8961a226a` | Later V2 research/dataset assembly snapshot; its training rows include feature inputs alongside future-derived labels and related research metadata. | Later ApexLab code is not verified Gen 1. Separation and availability must be explicit in this implementation; source is not reused. |
| Engine `feature_extractor.py` — `63a5880cbab997d7da6d9d8a2a4d1669c5264b9c61f8bf4e53facc8779584c41` | Feature-extraction component in the Engine foundation scaffold. | No mapped tests establish formulas, cutoff safety, or production status. Audit reference only; not copied or executed. |
| Engine protocol `T03_volatility_filter.py` — `24778162533ac99f3100044c468149778d6eef0403fcfd0670cb98ee6b7bc58a` | Volatility-filter concept in the repository's T01–T12 protocol scaffold. | The repository README describes a foundation scaffold; the snapshot does not verify an original protocol lineage. Its values are not adopted as defaults. |

## QC2-014 disposition

The implementation uses independently written formulas, explicit session calendars, source hashes, receipt-time cutoffs, adjustment-basis checks, reason-coded missingness, and fixture-only parameter profiles. Legacy formulas and empirical parameter choices are not enabled. No production/live-trading use is claimed.

The authorized label “Gen 1 feature logic” could not be tied to a verified Gen 1 repository or revision. This intake does not resolve that identity gap or grant rights beyond the source licenses.
