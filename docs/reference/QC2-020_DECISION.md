# QC2-020 — F0 Runner Protocol Migration Wave 2 decisions

## Status and boundary

QC2-020 adds six independent, inactive research hypotheses. Every definition uses the existing `research` namespace, `SYNTHETIC_FIXTURE` evidence, and registered daily `FeatureSnapshot` inputs. The research registry has an empty active set. A `PASS` is only a research hypothesis match; it is not an order, execution permission, safety decision, or production signal.

The legacy Apex and Engine files documented in [the reference intake](QC2-020_REFERENCE_INTAKE.md) are exclusion evidence, not implementation inputs. No legacy source is copied, imported, modified, executed, or tested. The research formulas below use the existing QC2-014 feature definitions and do not claim equivalence to any legacy protocol.

## Research definitions

| Protocol | Registered input legs | Research meaning and result |
|---|---|---|
| `daily-breakout-confluence` | `breakout_proximity`, `relative_volume`, `return_1` | Matches when the daily high reaches/exceeds the preceding registered high window (`breakout_proximity <= 0`), current volume exceeds the preceding-window mean (`relative_volume > 1`), and the close-to-close return is positive. Match is `PASS`; non-match is `OBSERVE`. This is not T24 or T25 behavior. |
| `daily-reversal-location` | `reversal_score`, `return_1`, `close_location_value` | Matches an opposing latest return when close-location value agrees with that return: prior-direction score `< 0`, return `> 0`, CLV `> 0`, or the inverse. Match is `PASS`; non-match is `OBSERVE`. |
| `daily-failed-breakout-observation` | `breakout_attempt_count`, `breakout_failure_count` | Observes when both registered daily counts are nonzero. Both match and non-match are `OBSERVE`; counts do not establish a trap probability or a blocker. |
| `daily-price-volume-divergence-observation` | `price_volume_divergence` | Observes whether the registered daily divergence value is nonzero. It does not infer an action or new direction. |
| `daily-exhaustion-pressure-observation` | `exhaustion_pressure` | Observes whether the registered daily exhaustion-pressure value is nonzero. It does not block signals or change a score. |
| `historical-similarity-interface-observation` | `runner_similarity`, `failure_similarity` | Requires both registered values to be present and in the signed-unit range `[-1, 1]`; a present pair yields `OBSERVE` only. It is an interface-readiness check, not a memory-based decision. |

The transitive feature dependency adjacency lists are in [QC2-020_DEPENDENCY_GRAPH.json](QC2-020_DEPENDENCY_GRAPH.json). The graph includes all feature ancestors declared by the existing registry; raw market inputs and their units remain governed by the corresponding `FeatureDefinition` contracts.

## Similarity and memory gate

The existing feature engine accepts a historical similarity prototype only when:

- the prototype event session is strictly earlier than the target session;
- its feature snapshot belongs to that same event session;
- the artifact and access receipt are available by the decision cutoff and bound to that cutoff;
- the feature registry hash and complete registered vector match; and
- the prototype reference is not duplicated.

QC2-020 does not broaden that interface or create a failure-memory decision policy. The protocol requires both similarity feature values. `NOT_APPLICABLE` or missing ingredients produce `UNAVAILABLE`; `UNKNOWN` remains `UNKNOWN`. No threshold is used to promote or suppress an operational signal.

The local typed evidence model requires hash-shaped references, binds exactly the source and feature-snapshot artifacts, and constrains the operation, access mode, cutoff, availability, and authorization time. It does not independently authenticate an external authority signature. The protocol remains an inactive readiness observation; no production decision depends on this interface.

## Exclusions

- **Legacy T24/T25 breakout and channel semantics:** excluded as ports. The pinned source meaning conflicts with its documentation labels; daily F0 equivalence, deterministic numeric behavior, calibration, and original lineage are unverified. The Apex license also reserves production/live use absent written consent.
- **Legacy Engine T07/T08/T12 outputs:** excluded as ports. Their mutable untyped flags/probabilities do not define daily evidence, point-in-time cutoffs, calibrated probability, or a permission boundary. Engine provenance and applicable license are unverified, and its pinned tree has no test tree.
- **Intraday stall or path-dependent microstructure semantics:** unavailable in F0. No verified original stall source was inspected for this wave, and the registered daily feature set contains no validated stall definition. No intraday proxy is invented.
- **Memory-driven action, trap probability, and exhaustion blocking:** excluded pending verified semantics and calibration. Daily count/feature observations above are separate research records, not substitutes for those policies.
- **Production activation, live trading, and runtime feed/provider fallback:** not implemented. No synthetic or uncalibrated definition is activated.

## Double-counting and verification evidence

Each research protocol has a unique namespace-qualified ID. Protocol results remain separate records; the wave does not sum scores or count duplicate IDs as independent evidence. The registry rejects duplicate protocol keys.

QC2-020 tests cover multi-leg breakout and reversal matches, exact-cutoff acceptance, late evidence rejection, unavailable and unknown ingredients, the similarity interface's observation-only behavior, transitive dependency closure, inactive registry membership, and duplicate-ID rejection. The existing `tests/science/test_feature_authority.py::test_similarity_uses_only_historical_registry_matched_receipted_prototypes` covers future-event, late-availability, wrong-cutoff, registry-mismatch, and access-receipt rejection. No downstream canonical task was started.
