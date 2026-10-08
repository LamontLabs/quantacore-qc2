# QC2-019 — F0 Runner Protocol Migration Wave 1 decisions

## Outcome

The inspection queue is resolved in `QC2-019_MIGRATION_DECISIONS.json`. Three component-level, research-only rewrites are registered:

- `research:t41-volume-expansion:v1`
- `research:t44-positive-money-flow:v1`
- `research:t78-return-sign-alignment:v1`

They are materialized by the existing declarative Runner Protocol contract and bounded isolated worker. The research registry is namespace `research`, evidence class `SYNTHETIC_FIXTURE`, environment `research`, and has an empty `active_protocol_ids` list. No candidate is active in F0 or production.

## Research hypotheses and parameter contracts

| Registry entry | Daily feature inputs and units | Exact parameter contract | Hypothesis result |
| --- | --- | --- | --- |
| `research:t41-volume-expansion:v1` | `relative_volume:ratio` | `expansion_boundary = 1.000000000000 ratio`; strict `>` | `PASS` when current daily volume exceeds the preceding 20-session arithmetic mean; otherwise `OBSERVE`. The value 1.0 is the ratio's mathematical comparison boundary, not an empirical calibration or legacy threshold. |
| `research:t44-positive-money-flow:v1` | `accumulation:signed_fraction` | `zero_boundary = 0.000000000000 signed_fraction`; strict `>` | `PASS` when the registered 20-session volume-weighted close-location feature is positive; otherwise `OBSERVE`. |
| `research:t78-return-sign-alignment:v1` | `return_10:fraction`, `return_20:fraction` | `zero_boundary = 0.000000000000 fraction`; signs compare exactly | `PASS` when both registered returns are positive, both are negative, or both are exactly zero; otherwise `OBSERVE`. The protocol direction is `UNKNOWN` because the matching signs may be positive or negative. |

The parameters are immutable exact-decimal values embedded in each `RunnerProtocolSpec`; each protocol's parameter hash and implementation hash bind them. No `ConfigurationManifest` is claimed for these uncalibrated synthetic fixtures. The contracts are research/test-only. Any future calibration must be externally evidenced and owner-approved before activation; it is not implied here.

## Evidence and runtime boundaries

- Inputs are only the named QC2-014 daily `FeatureSnapshot` scalar values. Units and feature names are cross-checked against the registered feature definitions in isolated tests.
- Present values are exact `Decimal` values; binary floats are rejected. Each value carries its unit, known-at instant, uncertainty, and content-addressed input reference.
- Results retain the hypothesis, direction, evidence values, uncertainty, missingness, parameter hash, implementation hash, decision cutoff, protocol reference, and input references.
- Positive, negative/nonmatching, and unknown fixtures are evaluated through the existing isolated declarative worker. Repeated identical inputs and IDs produce byte-identical result records. Worker step counts remain bounded.
- Future-known input values are rejected. Missing/unknown evidence is never changed into a numeric zero or a passing result.
- Production activation checks explicitly reject each synthetic research definition.
- No protocol accesses a quote feed, network, clock, secret, arbitrary file, model, broker, or live data source. The runner architecture is not expanded.

## Explicit exclusions and semantic limits

The full behavior of T41, T44, and T78 is not migrated. Their named research entries test only the exact subhypotheses listed above. In particular:

- T41's self-inclusive mean, z-score, source thresholds, and confidence branches are omitted.
- T44's cumulative A/D level, source moving averages, and price-divergence branches are omitted; the finite normalized `accumulation` feature is not equivalent to the cumulative line.
- T78's volume support, pullback depth, weighted score, confidence, and source thresholds are omitted.

T34 remains `SOURCE_UNRESOLVED` because the pinned code and tier-document identity conflict, and its floating ROC z-score has no matching registered feature. T37, T38, T42, and T57 are `UNAVAILABLE_IN_F0`: their required oscillator, OBV, or staged pattern calculations do not exist as registered features, and implementing them inside the protocol runner would broaden its architecture. T77 is excluded because its historical reversion-rate loop uses future five-session closes. P55, T92, T102, T103, T104, T108, T109, and T110 remain `SOURCE_UNRESOLVED` because the scoped inventory contains no verified path-qualified source for them.

All nine inspected Apex files use the demo/evaluation-only source snapshot. Its license bars production/live use without written consent. No legacy code is copied, imported, modified, or executed; the local rewrites are independent declarative definitions. No license or meaning is inferred for unmapped candidates.

## Verification scope

QC2-019 tests validate the full 17-ID decision queue; materialize and hash-check the three research definitions and inactive registry; exercise positive, negative/nonmatching, and unknown inputs; verify exact replay, daily-feature units, cutoff enforcement, decimal-only evidence, and bounded worker execution. Existing hostile-worker tests cover attempts to request network, filesystem, wall-clock, global-state, training, and broker operations. The pinned upstream Apex tests were inspected but not run.
