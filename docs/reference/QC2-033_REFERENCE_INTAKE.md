# QC2-033 Reference Intake

## Authorized scope

Only the current ApexLab dataset/split/evaluation implementation was authorized. No external or legacy repository was inspected.

## Sources inspected

### Current ApexLab evaluation consumer

- **Repository revision:** `4958de31ba57fd7ddc37e6fe7b94dc8646e63618`
- **Path:** `packages/apexlab/src/qc2_apexlab/decoy_engine.py`
- **SHA-256:** `952327737fe4bbdd78887001c414685442ff895459638d6d7a25773f9ae1872b`
- **Source-supported meaning:** The matched-decoy evaluator consumes a `DatasetManifest`, requires `PIT_VERIFIED` fidelity, rejects case-control/matched/decoy/balanced sampling policies, checks that its time range covers the risk-set session, and requires the exact `UniverseManifest` reference in `source_refs`.
- **Tests:** The current ApexLab suite, including the dataset-builder integration tests, passed: 34 passed, 0 failed, 0 skipped. The evaluation consumer itself was not modified.
- **Conflicts and constraints:** QC2-033 cannot manufacture a universe reference or claim PIT fidelity beyond its source rows. Callers must supply the exact universe reference in the build plan; the dataset builder retains it in `DatasetManifest.source_refs`. Its training-only sample-weight policy is distinct from population balancing.
- **License and access limits:** Read-only access to the checked-in workspace source at the revision above. No repository `LICENSE`, `COPYING`, or `NOTICE` file or ApexLab `license=` metadata was found. No external source was accessed or copied.
- **Disposition:** Use this implementation only as a downstream consumer contract. No evaluator code was copied or changed. Downstream use remains conditional on callers providing the correct point-in-time universe evidence.
