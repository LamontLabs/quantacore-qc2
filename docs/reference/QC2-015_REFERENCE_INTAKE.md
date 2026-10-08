# QC2-015 — Label Authority reference intake

## Inspection basis and disposition

- Inspected Apex `Lamont-Labs/QuantraCore-Apex` at revision `d65ad25b813977b1087b94db5f88a32963426477`.
- Inspection was read-only. No Apex source was copied, imported, modified, or executed. The upstream label tests were read but not run.
- Apex `LICENSE` is demo/evaluation-only and prohibits production or live-trading use without written consent. Its SHA-256 is `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9`.
- The label wrapper delegates values to dynamically loaded `LP01`–`LP25` modules. Those individual protocol modules were not inspected, so this intake does not claim their detailed target semantics.

## Inspected files

| Repository path and SHA-256 | Source-supported meaning | Test coverage, conflict, and disposition |
| --- | --- | --- |
| Apex `src/quantracore_apex/apexlab/labels.py` — `0438f2bc3a7d068ad198bc99475c1ac7ecf095d7dfa4c6d02d2765c832ca2b74` | Creates a deterministic Apex engine result using seed 42 and compliance mode, asks `LearningProtocolRunner` for teacher labels, flattens their values, then adds regime/risk/score and other engine-derived classes. The module-level helper returns `quantrascore_numeric` and substitutes `50.0` if that key is absent; its `ohlcv_bars` argument is unused. | The inspected implementation is a teacher-label wrapper, not a forward-outcome authority: it does not expose a frozen future-session horizon, split basis, data/corporate-action finalization, or mature-only label release. The absent-value fallback conflicts with explicit unavailable states. Audit-only; not reused or run. |
| Apex `src/quantracore_apex/protocols/learning/__init__.py` — `e178abd6fa1126606c830ea8c4af7a59a8fa3d891e02d83a65f731aa5a7284ce` | Re-exports `LearningProtocolRunner` from the loader. | Does not define label formulas. Read only; no behavior adopted. |
| Apex `src/quantracore_apex/protocols/learning/learning_loader.py` — `0ad5faced1eb52d5fee0e547b57b2a1461f04a90fbd4e8961de1dfe3e7f628f2` | Tries to import LP01 through LP25, calls each available `generate_label`, and returns a flat label-name-to-value dictionary. Import errors and per-protocol exceptions are caught and skipped. | Silent omissions make this unsuitable as an authoritative target registry. Its `confidence` and `metadata` are not used by the flattening step. Read only; not reused or run. |
| Apex `tests/lab/test_apexlab_labelgen.py` — `674c97663937cb1da3a590653fd9c7545118dd4ca24395f4224b458a63969962` | Tests importability, label dictionary shape, selected score/regime/risk fields, numeric range, batch length, and deterministic scores on synthetic bars. | Does not assert forward-return equations, session calendars, split consistency, mature-only release, field validity, or missing-horizon behavior. Read only; not run. |
| Apex `LICENSE` — `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9` | “Demo-only/Evaluation license. No production or live trading without written consent.” | No production/live-trading use absent written permission. This reference intake does not expand the license. |

## QC2-015 disposition

The QC2 implementation defines its labels from the governing Gen2 master specification, uses explicit frozen-calendar sessions and split-basis checks, and records unresolved target definitions without substituting zero or a synthetic negative. No Apex label formula or empirical threshold was adopted. Nothing in this intake is evidence of empirical calibration, production permission, or live-data capability.
