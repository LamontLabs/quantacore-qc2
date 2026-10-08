# QC2-016 — Ground Truth Authority reference intake

## Inspection basis and disposition

- Native source revision: `2ca237f017ea30c9b5384c615511e829c4b0a4b9`.
- Inspected native files read-only; no native label or contract implementation was copied from a legacy repository.
- No project-level `LICENSE` file was found in the scoped repository search. No third-party or legacy source was used; this intake does not assert a separate license grant.
- The task authorizes Gen 1 ForwardValidator as a possible reference, but it was not inspected, imported, modified, or executed. No claims about its behavior are made.

## Inspected native files

| Repository path and SHA-256 at inspected revision | Source-supported meaning | Tests, conflict, and disposition |
| --- | --- | --- |
| `docs/GEN2_MASTER_SPEC.md` — `4c88d457f10bae4f94efe9689aab9c45372ded10b43f88ad6d40e25584a12aab` | Governing Gen2 domain authority and task scope. | Used as the requirements source; no legacy behavior overrides it. |
| `packages/science/src/qc2_science/label_models.py` — `6759ae5e012a1ec827d548c5b7a6f98fdb0623cb979f78c3d7e9915cc17fbc51` | Typed, immutable daily-bar and label inputs; stable Instrument references, share-basis consistency, and finalization evidence. | Ground Truth accepts this validated input boundary; it does not add a provider fallback. |
| `packages/science/src/qc2_science/label_outcomes.py` — `b18a82958d33cccd6248e2b74e52c096ed75516848b17bb92bfe52b36d7cec2d` | Fixed-calendar formulas, maturity states, field validity, target availability, and learning-time derivation. | Its pure `LabelOutcome` is not a persisted Outcome. QC2-016 serializes it and adds verified-terminal consideration handling without changing label formulas. |
| `packages/science/src/qc2_science/label_registry.py` — `b79e48f68b76f9a9bd3d85e059c4984ee861d6616f3446901b60f60019355c6b` | Registered stable label keys, horizons, target-event families, and threshold availability. | RunnerEvents are emitted only when the registered target is available and true. Null thresholds remain unavailable. |
| `docs/reference/QC2-015_DECISION.md` — `c859c14b024ab7aaff5ad80bf449d54f3630548732088988d2e814acd8cdcace` | Records the predecessor's frozen formulas, precision, target availability, and maturity/release states. | Reused only as the accepted QC2-015 science boundary; QC2-016 adds persistence, corrections, and terminal-cash evidence without changing those formulas. |
| `packages/contracts/src/qc2_contracts/catalog.py` — `7613f74810f6bcc6d549b46589bb27b161bb5f2690687fc6785d54ec1de15c65` | Wire schemas and field/reference constraints for Outcome, OutcomeRevision, and RunnerEvent. | Ground Truth records are validated against these contracts; their declared content-addressing differences are preserved. |
| `packages/contracts/src/qc2_contracts/runtime.py` — `5f93ceec304e02bf9898b75c57393cee083bc17c4258af6554d3d07887a8386c` | Contract validation, semantic invariants, and content-hash behavior. | Used to validate serialized records; non-content-addressed records are validated without inventing a content hash. |
| `tests/science/test_label_authority.py` — `5722dafc457ccb11e356c3eb43ee7b5af92cc74053569c05102980b294a7947e` | Existing synthetic tests for fixed sessions, split-basis inputs, return formulas, threshold precision, and unresolved maturity behavior. | Relevant predecessor coverage; QC2-016 adds separate eligible-row, terminal-event, RunnerEvent, review, correction, and release tests. |

## QC2-016 disposition

The implementation uses the native Gen2 label and contract boundaries, resolves all supplied eligible rows, and keeps corrections and learning-release references immutable. The predecessor label resolver does not model verified cash consideration; QC2-016 treats that case as endpoint-only partial resolution and keeps the remaining horizon censored. No Gen 1 ForwardValidator semantics or license-dependent source code were adopted.
