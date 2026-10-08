# QC2-019 — F0 Runner Protocol Migration Wave 1 acceptance assessment

## Acceptance assessment

- **Result:** PASS

The inspected QC2-019 queue has 17 explicit, source-backed dispositions. Nine Apex candidate files were retrieved read-only at the exact revision and matched to the QC2-018 Git blob hashes. The Apex source test and LICENSE were also inspected at that revision. No legacy source or test was copied, imported, executed, edited, or run. The pinned Apex license does not authorize production/live use without written consent; none is inferred. Unmapped IDs remain unresolved only within the QC2-018 inspection scope.

Three deliberately partial, independently authored research hypotheses use only QC2-014 registered daily features: prior-window relative volume, finite normalized accumulation, and 10/20-session return-sign alignment. Their exact Decimal parameter contracts, input units, evidence, cutoff, implementation/parameter hashes, and semantic differences are documented. They are materialized in the `research` namespace with `SYNTHETIC_FIXTURE` evidence, research environment, and an empty active-ID list. Production activation checks reject each definition. No candidate or uncalibrated fixture value is activated.

The remaining queue items have explicit evidence-backed exclusions. T34 remains unresolved because its historical identity conflicts with the inspected source behavior. T37, T38, T42, and T57 require computations absent from the registered daily feature set. T77 reads future five-session closes. P55, T92, T102, T103, T104, T108, T109, and T110 lack path-qualified sources in the scoped inventory; no repository-wide absence is claimed.

Positive, negative/nonmatching, and unknown fixtures run through the existing bounded isolated declarative worker. Each research definition has exact replay checks, typed result/evidence validation, future-known-value and binary-float rejection, and a production-activation denial check. Shared worker tests reject network, filesystem, clock, process-global, model-training, and broker operations, including a local socket connection attempt. The candidate expressions use only supported declarative operations; there is no provider/feed fallback, hidden quote requirement, live-data path, or new runner architecture.

## Verification

- Focused QC2-019 tests: 14 passed, 0 failed, 0 skipped.
- Full suite: 216 passed, 0 failed, 0 skipped.
- Ruff: passed.
- QC2-018 inventory validator: passed; 139 path-qualified source files and no unresolved, intraday-only, or float-only source marked `ACTIVE_F0`.
- Task documentation generation check, decision-ledger JSON parse, and QC2-019 dependency preflight: passed.
- Pinned upstream Apex candidate tests: inspected but not run; they do not assert the reviewed T34/T37/T38/T41/T42/T44/T57/T77/T78 behavior.

## Acceptance checklist

- [x] DELIVERABLE: Source-backed implementation or explicit exclusion for each requested candidate. | evidence: `QC2-019_MIGRATION_DECISIONS.json`; `QC2-019_REFERENCE_INTAKE.md`; complete 17-ID queue test
- [x] DELIVERABLE: RESEARCH registry entries, parameter contracts, evidence fields and isolated tests. | evidence: `runner_protocol_research.py`; `test_runner_protocol_research.py`; `QC2-019_DECISION.md`
- [x] DELIVERABLE: Semantics-difference notes where Gen 2 adapts legacy behavior. | evidence: `QC2-019_DECISION.md`; `QC2-019_REFERENCE_INTAKE.md`; `QC2-019_MIGRATION_DECISIONS.json`
- [x] TEST: Positive/negative/unknown fixtures per implemented hypothesis. | evidence: 14 focused QC2-019 tests; positive, negative/nonmatching, and unknown cases for all three definitions
- [x] TEST: No hidden future-memory, quote, float, or live data requirement. | evidence: `test_runner_protocol_research.py`; exact daily FeatureSnapshot requirements; future cutoff and binary-float rejection; existing isolated-worker hostile-operation tests
- [x] TEST: Exact replay and side-effect tests for each migrated protocol. | evidence: per-definition canonical-result replay and bounded-step checks in `test_runner_protocol_research.py`; supported-operation allowlist; shared network/filesystem/clock/global/training/broker denial tests
