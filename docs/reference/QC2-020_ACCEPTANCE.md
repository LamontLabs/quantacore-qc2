# QC2-020 — F0 Runner Protocol Migration Wave 2 acceptance assessment

## Acceptance assessment

- **Result:** PASS

Six independently specified daily research hypotheses use only QC2-014 registered features. Their transitive feature dependency graphs match the registered `FeatureDefinition` dependencies. The definitions remain in the `research` namespace with `SYNTHETIC_FIXTURE` evidence, use a typed `FeatureSnapshot` input, and are excluded from the active protocol set.

The read-only reference intake records the exact pinned Apex and Engine sources, hashes, observed meanings, test status, license evidence, and exclusion rationale. The inspected legacy source was not copied, imported, modified, executed, or tested. The Apex license restriction is preserved; no production/live use is inferred. The six daily hypotheses are not behavior-equivalent legacy ports.

Breakout and reversal fixtures exercise all declared legs and the decision cutoff. Duplicate protocol keys are rejected. Missing and unknown similarity ingredients remain `UNAVAILABLE` and `UNKNOWN`, respectively; present similarity values can only produce `OBSERVE`. The existing historical-similarity authority test rejects future-session, late-authorization, wrong-cutoff, availability-mismatch, and wrong-registry prototypes. The local typed access-evidence model does not independently authenticate an external authority signature, and no production decision depends on it. No synthetic intraday proxy, calibrated memory decision, live trading path, or runtime provider fallback was added.

## Verification

- Focused QC2-020 and historical-similarity gate tests: 7 passed, 0 failed, 0 skipped.
- Full suite: 222 passed, 0 failed, 0 skipped.
- Ruff: passed.
- Dependency-graph consistency check: documented graph exactly matches the code-generated registered-feature graph and each protocol's direct inputs.
- QC2-018 inventory validator: passed; 139 path-qualified source files and no unresolved, intraday-only, or float-only source marked `ACTIVE_F0`.
- Both QC2-020 JSON evidence files parse; task documentation check, QC2-020 preflight, task registry validation, and `git diff --check` passed.

## Acceptance checklist

- [x] DELIVERABLE: Research implementations for supported structural concepts with dependency graphs. | evidence: `runner_protocol_research_wave2.py`; `QC2-020_DEPENDENCY_GRAPH.json`; graph consistency check
- [x] DELIVERABLE: Failure-memory and similarity interface dependencies explicitly gated. | evidence: similarity protocol and temporal-gate record in `QC2-020_DEPENDENCY_GRAPH.json`; existing historical prototype validation and acceptance test
- [x] DELIVERABLE: Exclusion records for concepts impossible in F0. | evidence: `QC2-020_MIGRATION_DECISIONS.json`; `QC2-020_DECISION.md`; `QC2-020_REFERENCE_INTAKE.md`
- [x] TEST: Multi-leg and temporal-boundary fixtures; no future member in memory lookup. | evidence: `test_runner_protocol_research_wave2.py`; `test_similarity_uses_only_historical_registry_matched_receipted_prototypes`
- [x] TEST: No composite double-counting hidden behind duplicate protocol IDs. | evidence: duplicate protocol key rejection in `test_runner_protocol_research_wave2.py`; `double_counting_policy` in `QC2-020_MIGRATION_DECISIONS.json`
- [x] TEST: Unavailable ingredients produce UNAVAILABLE rather than invented evidence. | evidence: missing/unknown feature assertions in `test_runner_protocol_research_wave2.py`
