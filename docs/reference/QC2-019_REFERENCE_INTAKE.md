# QC2-019 — Runner Protocol Migration Wave 1 reference intake

## Inspection basis

- **Reason for inspection:** Resolve the canonical QC2-019 candidate queue from pinned source evidence before deciding which concepts fit the existing daily-feature Runner Protocol contract.
- Pinned source revision: `Lamont-Labs/QuantraCore-Apex@d65ad25b813977b1087b94db5f88a32963426477`.
- Relevant candidate entry point: `run(window, microtraits)` for each of the nine retrieved candidate source files.
- Each listed candidate file was retrieved read-only at that exact revision. Its Git blob SHA-1 was checked against the QC2-018 inventory entry; the match passed for every retrieved candidate.
- No legacy source or test was copied into the workspace, imported, executed, edited, or run.
- The pinned source snapshot does not establish historical original-project identity or protocol lineage.
- The QC2-018 inventory is the scope boundary. Unmapped candidates remain unresolved; no repository-wide absence claim is made.

## Candidate implementation intake

| Candidate | Pinned source path; Git blob SHA-1; raw SHA-256 | Source-supported behavior | Tests, conflicts, and disposition |
| --- | --- | --- | --- |
| T34 | `src/quantracore_apex/protocols/tier/T34.py`; `6bdd284ae92a233627a495cbde31f13055687125`; `51a2cfaee7de0c15d8cdf43af0ccd099b66a4fcc46891290fe36e23c0f103c32` | ROC 10/5/1, a 10-session ROC z-score, and ROC acceleration. The source branches at absolute z-scores 2.5 and 1.5; its acceleration branch compares absolute acceleration with twice the absolute mean. | The pinned implementation uses NumPy/binary floats. QC2-001 records the conflict with the tier document's “Strength zone mapping” label and leaves the historical trap-evader identity unresolved. The QC2-014 registry has no matching ROC-z-score feature. Excluded; `SOURCE_UNRESOLVED`. |
| T37 | `src/quantracore_apex/protocols/tier/T37.py`; `7a9321ef737f21273fa6b4619a5bf17ae6067537`; `386e4af59d104003d3718d9e9c628a83025a860cbe0b8573d55d2e933f4e28a5` | 14-bar Williams %R; source branches above -20, below -80, or at absolute trend change above 20. | NumPy/binary floats and legacy thresholds; no exact registered Williams %R feature. Excluded; `UNAVAILABLE_IN_F0`. |
| T38 | `src/quantracore_apex/protocols/tier/T38.py`; `06d07bc56dc24ec29543e99202fb300f4b0d3e8a`; `4ff7347f8a161a04a7d9e237dd93aee6143130163268067edf3228a42562053b` | 20-bar CCI over typical price and mean absolute deviation; source branches at CCI +200/+100/-200/-100 and absolute CCI-trend above 100. | NumPy/binary floats and legacy thresholds; no exact registered CCI feature. Excluded; `UNAVAILABLE_IN_F0`. |
| T41 | `src/quantracore_apex/protocols/tier/T41.py`; `c2447feb0073b113149861ec13a30f8494cfa4d6`; `f173bbe53c1e56e5135f57c089306287787b8aa0a9d0b03b28be669452a97a23` | Volume ratio, volume z-score, and spike/dry-up branches: ratio >3 with z-score >2.5, >2, >1.5, or <0.5. The source computes price change only for details. | Current bar is included in the source's 20-bar mean; QC2-014 `relative_volume` compares with the preceding 20 sessions. Legacy thresholds and float calculations are not reused. Research-only rewrite tests the exact prior-window ratio against its mathematical baseline of 1.0; not output-equivalent to T41. |
| T42 | `src/quantracore_apex/protocols/tier/T42.py`; `a2e78510ad6fec8412c873f76b383ef7044ff0cd`; `ace3cf5474137e52b066510f031efd6478e6c8e8145fdc38c9385bf705ffa197` | Cumulative OBV, 20-bar mean comparison at 1.2/0.8, 10-bar price/OBV divergence, and normalized slope branch above 0.5. | NumPy/binary floats; no registered OBV feature. The registered `accumulation` feature is not OBV and is not substituted. Excluded; `UNAVAILABLE_IN_F0`. |
| T44 | `src/quantracore_apex/protocols/tier/T44.py`; `9e539d69914eafdea477dbf1aa9900b9cc1ab07a`; `dd065a33f2d6f7c681f4ef4de30cc93a37e32d6cf5b84637f227c0bbca3f6ffb` | Cumulative A/D line from close-location multiplier times volume, with 10/20-bar moving-average comparisons at 1.1/0.9 and 10-bar price divergence. | The registered `accumulation` is a finite 20-session, volume-weighted close-location fraction, not the source's cumulative line. A research rewrite tests only the registered feature's positive sign; not output-equivalent to T44. |
| T57 | `src/quantracore_apex/protocols/tier/T57.py`; `582156eaf7194b2db5e20760e08a30a22569ba48`; `425153d69a09d20aebf5111b678fd77b0e7dbad8a810f253db30fca1f7ca0b0a` | 50-close cup-and-handle pattern; rim similarity <5%, cup depth 10–35%, handle pullback 5–15%. | NumPy/binary floats and source pattern thresholds; no exact registered daily shape feature. Excluded; `UNAVAILABLE_IN_F0`. |
| T77 | `src/quantracore_apex/protocols/tier/T77.py`; `e97d1b115ea5a2cf20ec087b2c2e8583531a4bbd`; `fab1f080bd16938adc01718e348a5f5e113080d86c941e6693527645e2a7ac05` | Mean-reversion score combines current deviation/volatility with a historical reversion rate; source high branch requires absolute z-score >2.5 and reversion rate >0.5, with lesser branches above 2 and 1.5. | The historical loop reads `closes[i+5]` to compute a future five-session return. This is future-memory/lookahead and is excluded. No matching registered mean-reversion z-score feature exists. |
| T78 | `src/quantracore_apex/protocols/tier/T78.py`; `0b7f2dc42404eb84ca45d09ae09c3788154dcf42`; `3b839ee6689c461b94ed842be282a992c0b4a774a31021ecee6f17a29a672b43` | 10/20-session trend sign alignment, recent/prior volume support, and pullback <3%; source score adds 0.3/0.25/0.25/0.2 and branches above 0.7/0.5. | Only sign alignment is rewritten from registered `return_10` and `return_20`. Volume, pullback, weighted score, confidence, and source thresholds are omitted; this is not output-equivalent to T78. |

## Shared test and license sources

| Path | Revision-bound hash | Findings |
| --- | --- | --- |
| `src/quantracore_apex/tests/test_all_tier_protocols.py` | Git blob SHA-1 `e1dc9fe6eb89da289fc240a25a6e08505b790983`; SHA-256 `d39b49f869617ddfc713ec3521957ce3aefa9147b2ab7cc988cdbb7c29124e58` | The T01–T80 loop checks import presence and skips missing modules. Its execution loop only covers T01–T20 and searches for `run_Txx`; it does not test the reviewed candidate `run(window, microtraits)` behaviors. Read-only inspection; not run. |
| `LICENSE` | Git blob SHA-1 `165291c0a65176ed5794d605b7a6102d2c37f25e`; SHA-256 `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9` | Demo-only/evaluation license; no production or live trading without written consent. No production authorization is inferred. |

## Unmapped requested candidates

P55, T92, T102, T103, T104, T108, T109, and T110 have no path-qualified source entry in the inspected QC2-018 inventory. Their source meaning, candidate tests, repository license, and revision remain unknown. They are explicitly excluded as `SOURCE_UNRESOLVED`; this does not establish that they are absent from any repository outside the scoped inventory.

The machine-readable candidate-by-candidate disposition is in `QC2-019_MIGRATION_DECISIONS.json`.

## Useful concepts and boundaries

These are source concepts considered during the intake, not claims that the source behavior is equivalent to a registered feature:

- **T34:** no concept is adopted while its historical identity conflict remains unresolved and the feature registry lacks its ROC-z-score calculation.
- **T37/T38:** oscillator saturation, CCI extremes, and reversals could motivate later feature review, but the required rolling indicators are not registered.
- **T41:** current volume versus a prior-only baseline is representable through `relative_volume`; the research variant uses that feature's exact semantics, not the source's self-inclusive denominator, z-score, or thresholds.
- **T42:** volume direction alongside price is a possible concept, but no registered OBV feature supports this source behavior.
- **T44:** volume-weighted close location is relevant to the registered finite `accumulation` feature, which is not the cumulative source A/D line.
- **T57:** the source expresses a staged price-shape hypothesis, but no exact registered daily shape feature supports it.
- **T77:** no concept is adopted from the historical reversion-rate branch because it uses future closes; its current-window z-score is also unavailable as a registered feature.
- **T78:** 10/20-session return-sign alignment is independently testable from registered features; volume, pullback, and weighted-score components are omitted.
- **P55, T92, T102, T103, T104, T108, T109, and T110:** source meaning and useful concepts remain unknown in the inspected scope.
