# QC2-018 — Historical protocol reference intake

## Inspection basis and scope

- **Checked:** 2026-10-07.
- **Engine:** `Lamont-Labs/QuantraCore-Engine@67597a2a63fd3957e6ec50e270dba8e3df1d3757`.
- **Apex:** `Lamont-Labs/QuantraCore-Apex@d65ad25b813977b1087b94db5f88a32963426477`.
- Reads used the existing GitHub App connection and HTTP GET only. No new connection, credential, clone, local legacy tree, import, execution, edit, or test run against legacy code was used.
- Engine recursive tree was complete (`truncated: false`, 41 tree entries). Apex's recursive tree was truncated and is **not** used as a complete repository inventory. The Apex `protocols/` parent and each of its four child directories were read separately at the pinned commit.
- `QC2-018_PROTOCOL_INVENTORY.json` is the path-qualified inventory: 139 protocol source files, each with repository, pinned revision, exact path, Git blob SHA-1, hypothesis, data need, migration disposition, and regime status. It covers the discovered Engine T namespace and Apex `tier`, `learning`, `monster_runner`, and `omega` namespaces. It does not claim that every protocol-like file anywhere in the truncated Apex repository has been discovered.
- GitHub's Git blob SHA-1 values are the inventory hashes. Selected raw SHA-256 checks are inherited from `QC2-001_SOURCE_MANIFEST.md`; the inventory does not imply every blob was independently downloaded and re-hashed.
- Each module record includes source-test coverage/status, license/provenance, conflicts, and a migration disposition. The two Engine support files whose bodies were read are listed separately in `support_sources` with the same intake evidence.

## Source inventory and interpretation

| Repository / namespace | Discovered modules | Source-supported interpretation | Test, conflict, license, and disposition |
|---|---:|---|---|
| Engine `src/quantracore/protocols/` | T01–T12, plus a nested duplicate T09 path (13 files) | Read-only source bodies show a mutable dictionary scoring scaffold over untyped state keys. Missing fields often default to numeric zero; several modules mutate `score`. T01 is documented as Zero-Drawdown Entry detector; T09 as Micro Pullback Timing. The inventory records each file's observed key/hypothesis; no data time horizon, units, lineage, or daily-bar binding is established. | The complete Engine tree contains no test tree and no recognized root license. T01 and T09 bare IDs conflict with Apex meanings. Nested T09 and top-level T09 share the same Git blob. All Engine files: `IGNORE` / `SOURCE_UNRESOLVED`; no legacy code or defaults adopted. |
| Apex `protocols/tier/` | T01–T80 (80 files) | The reviewed T01 and T09 meanings are Trend Direction and Range Compression, respectively. T24 source calculates ATR breakout; T25 calculates Keltner position around a 20-close arithmetic mean named `ema20`; T34 calculates rate-of-change momentum and a z-score. For other tier files, no source meaning is inferred from an ID or filename. | `docs/PROTOCOLS_TIER.md` conflicts with source behavior for T24 (“Volume alignment with trend”), T25 (“Volume rejection under high entropy”), and T34 (“Strength zone mapping”). Existing tier tests do not execute/assert the recorded T24/T25/T34 cases. Apex's demo/evaluation-only license reserves production/live use absent written consent. All files: `IGNORE` / `SOURCE_UNRESOLVED`. |
| Apex `protocols/learning/` | LP01–LP25 (25 files) | Separate LP namespace. Module source bodies were not reviewed for this inventory; their hypothesis and data needs remain explicitly unknown. | No bare-ID equivalence to T modules is inferred. All files: `IGNORE` / `SOURCE_UNRESOLVED`; no test or daily compatibility claim. |
| Apex `protocols/monster_runner/` | MR01–MR20 (20 files) | Separate MR namespace. Module source bodies were not reviewed for this inventory; their hypothesis and data needs remain explicitly unknown. | The source directory exceeds the five MR entries in the protocol manifest. All files: `IGNORE` / `SOURCE_UNRESOLVED`; no test or daily compatibility claim. |
| Apex `protocols/omega/omega.py` | One source file; header declares Ω1–Ω20 | The prior pinned-source review recorded a mixture of safety locks/overrides and alerts/warnings. Constructor flags can disable directives. | This is not a T/Runner namespace or a certified safety authority. Disable flags conflict with documentation that directives cannot be bypassed; enforcement is uncertified. Apex license limits apply. `IGNORE` / `SOURCE_UNRESOLVED`. |

The Apex protocol manifest identifies 115 entries (T01–T80, LP01–LP25, MR01–MR05, Ω1–Ω5), while the pinned source directories contain MR01–MR20 and `omega.py` declares Ω1–Ω20. The manifest is not a complete source inventory. The separate Apex `risk/engine.py` permission enum (`ALLOW`, `DENY`, `RESTRICTED`) is not a T-numbered protocol and its whole-runtime enforcement was not exercised.

## Support-file intake

| Revision and path/hash | Source-supported meaning | Tests, conflicts, license, and disposition |
|---|---|---|
| Engine `67597a2a63fd3957e6ec50e270dba8e3df1d3757`, `src/quantracore/engine/core_engine.py`, blob `951b4c26ebbc74310cb8bc940d2d8c75d186038f` | Initializes learning state, enriches an input snapshot, runs feature extraction, and forwards it to a routing bus. | No tests in the complete Engine tree; no recognized root license; scaffold identity does not prove historical origin. No typed data/cutoff contract. `IGNORE`. |
| Engine same revision, `src/quantracore/protocols/protocol_base.py`, blob `336b0f513c554d02fcb0132423ace6281346c48a` | Logs `state.price` and calls `run(state)` on a mutable dictionary. | No tests in the complete Engine tree; no recognized root license; the determinism docstring is not an enforced immutability/type/cutoff contract. `IGNORE`. |

## T24, T25, and T34 compatibility records

The exact paths, blob hashes, source-derived hypotheses, required data notes, documentation conflicts, and prior expected-output cases are recorded in the inventory and `QC2-001_SOURCE_MANIFEST.md`. The source-derived vectors are expectations read from code, **not executed test results**.

| Path-qualified identity | Finding | F0 compatibility and disposition |
|---|---|---|
| Apex `protocols/tier/T24.py` | A 20-bar-minimum ATR/range breakout calculation; not the tier-document's stated volume/trend alignment. | Uses floating-point arithmetic and a rolling OHLC window. Daily completed-bar equivalence, exact numeric behavior, cutoff semantics, independent tests, and calibration are unverified. `IGNORE` / `SOURCE_UNRESOLVED`. |
| Apex `protocols/tier/T25.py` | Keltner-channel position around an arithmetic mean, not an EMA; not the tier-document's stated high-entropy volume rejection. | Uses floating-point arithmetic and a rolling OHLC/close window. Daily equivalence, exact numeric behavior, cutoff semantics, independent tests, and calibration are unverified. `IGNORE` / `SOURCE_UNRESOLVED`. |
| Apex `protocols/tier/T34.py` | Rate-of-change momentum/z-score, not the tier-document's stated strength-zone mapping. | Uses floating-point arithmetic and a rolling close window. Daily equivalence, exact numeric behavior, cutoff semantics, independent tests, and calibration are unverified. `IGNORE` / `SOURCE_UNRESOLVED`. |

No equivalence is inferred from duplicate numbers. Engine and Apex T01/T09 remain distinct repository- and path-qualified identities. LP, MR, Ω, and T namespaces remain separate.

## Migration acceptance criteria and F0 boundary

All 139 inventoried protocol files are currently `IGNORE` / `SOURCE_UNRESOLVED`; none is `ACTIVE_F0`. An inventory entry can be considered for future migration only after all of the following are satisfied in the owning future task:

1. Exact source meaning, lineage, license/permission, relevant tests, and all ID/document conflicts are resolved or explicitly accepted as a rewrite-only hypothesis.
2. A new Gen 2 implementation uses typed immutable inputs, explicit data provenance and cutoffs, explicit missingness, bounded deterministic evaluation, and no side effects. Legacy Python is not imported or executed.
3. Every transitive input is demonstrated to be completed daily OHLCV or an approved deterministic daily feature. Intraday-only or float-only inputs cannot be `ACTIVE_F0`.
4. Numeric representation, parameters, and missing-data semantics are exact, versioned, independently tested, and bound into the implementation manifest. Legacy zero defaults and uncalibrated thresholds are not adopted.
5. Empirical contribution is established by predeclared ablation on permitted splits and budgets; protocol count or source presence is not evidence of predictive value.
6. The active-set validator reports zero unresolved dependencies. Owner-risk, security, license, and activation approvals remain separate gates; a source inventory does not grant any of them.

Unresolved or unavailable concepts remain excluded from activation (or block a required dependency); they are not filled in from a filename, bare ID, fixture, or documentation claim.
