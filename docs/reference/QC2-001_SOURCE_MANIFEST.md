# QC2-001 — Logical-role source manifest

- **Result:** PASS under the approved logical-role interpretation
- **Checked:** 2026-10-06
- **Remote handling:** GitHub API GET requests only. No clone, checkout, write, source import, or legacy test execution.
- **Workspace handling:** No local legacy source trees were present; `git status --short` was clean before these QC2-001 records were edited.

## Scope and disposition

The three authorized references are logical roles, not a requirement for three separately named Gen 1 repositories. A repository can support more than one role. Later snapshots are acceptable only when exact revision, observed version labels, license, and provenance limits are recorded. This PASS certifies that each functional role has an inspectable snapshot; it does **not** certify a historical Gen 1 source, the original protocol project's origin, a production deployment, or permission to use the candidate code in production.

## Role map

| Logical role | Exact mapped source | Source evidence | Limits |
|---|---|---|---|
| QuantraCore production/core implementation | `Lamont-Labs/QuantraCore-Apex`, `main` at `d65ad25b813977b1087b94db5f88a32963426477`; `src/quantracore_apex/core/` and `src/quantracore_apex/risk/` | `core/engine.py` identifies `ApexEngine` as the deterministic analysis entry point; `risk/engine.py` defines `ALLOW`, `DENY`, and `RESTRICTED` permissions. | This is a core implementation snapshot, not a verified production build. The separately named `QuantraCore_production` repository is empty. Apex version and license/compliance statements conflict; production authorization is not established. |
| ApexLab research/training | The same Apex commit; `src/quantracore_apex/apexlab/`, especially `apexlab_v2.py`; test `src/quantracore_apex/tests/test_apexlab_pipeline.py` | V2 code defines training rows with future outcomes, quality tiers, runner flags, and safety labels; the test checks feature shape, required labels, dataset construction/splitting, and NaN-free features. | It is a later ApexLab snapshot; no source establishes this as ApexLab Gen 1. Test source was inspected but not executed. |
| Original QuantraCore runner-protocol lineage | `Lamont-Labs/QuantraCore-Engine`, `main` at `67597a2a63fd3957e6ec50e270dba8e3df1d3757`, T01–T12 scaffold; and the expanded Apex `src/quantracore_apex/protocols/tier/` at the Apex commit, T01–T80. | Both trees contain concrete protocol modules; Apex `CORE_ENGINE.md` documents T01–T80 execution, and `T24.py`, `T25.py`, and `T34.py` expose protocol behavior. | The Engine README calls the repository a foundation scaffold. Neither repository proves the original protocol project's name or origin. Bare IDs collide and must stay repository/path-qualified. |

## Repository manifests

### `Lamont-Labs/QuantraCore-Engine`

- **URL / access:** <https://github.com/Lamont-Labs/QuantraCore-Engine>; private repository, readable through the installed GitHub connection.
- **Identity:** `main` at `67597a2a63fd3957e6ec50e270dba8e3df1d3757`, committed 2025-11-03T04:13:46Z. The accessible history contains 31 commits from 2025-11-03T03:59:21Z through the pinned head. One branch (`main`); no tags.
- **Tree:** Complete, non-truncated tree. README describes a “foundation scaffold.” The source has `src/quantracore/engine/`, `learning/`, utilities, and `src/quantracore/protocols/` with T01–T12. No test tree or root license file was found; GitHub reported no recognized license.
- **Mapped use:** Early core scaffold and runner-protocol snapshot only. It is not treated as an established production release or proven original protocol source.
- **Duplicate path:** T09 also exists at `src/quantracore/protocols/src/quantracore/protocols/T09_micro_pullback_timing.py`; this nested copy is byte-identical to the top-level T09 file (same Git blob SHA-1 and SHA-256 below).

### `Lamont-Labs/QuantraCore-Apex`

- **URL / access:** <https://github.com/Lamont-Labs/QuantraCore-Apex>; public repository.
- **Identity:** `main` at `d65ad25b813977b1087b94db5f88a32963426477`, committed 2026-02-06T23:15:32Z. The API reports 1,352 commits, from 2025-10-07T22:16:14Z through the pinned head. One branch (`main`); no tags.
- **Tree:** The `src/quantracore_apex/` subtree was retrieved without truncation (603 entries); the root test subtree was retrieved without truncation (147 entries). Relevant packages include `core/`, `apexlab/`, `protocols/tier/`, `protocols/learning/`, `protocols/monster_runner/`, `protocols/omega/`, `risk/`, and tests.
- **Observed version labels conflict:** README says v9.1; `docs/PROTOCOLS_TIER.md` says version 8.0; ApexLab overview and `config/protocol_manifest.yaml` say 9.0-A; `config/version_manifest.json` labels its system 2.1.0 with a 2025-12-12 release date. Use the immutable commit as the source identity; no single repository-wide release version is established.
- **License/compliance conflict:** `LICENSE` is demo/evaluation-only and reserves production/live use absent written consent. `docs/COMPLIANCE_AND_SAFETY.md` describes research/education use and simulation-only order handling. The version manifest, by contrast, says “Initial production release.” Do not infer a production release or production permission from that version manifest.
- **Relevant history:** T24, T25, and T34 file histories show an initial commit on 2025-11-27 and a later protocol-set commit on 2025-11-28. `apexlab_v2.py` history begins 2025-11-29, with later changes through 2025-12-23. Core engine history begins 2025-11-27 and continues through 2025-12-23.
- **Mapped use:** Core implementation, ApexLab research/training, later tier-protocol snapshot, and separately namespaced risk/Omega material. These are functional mappings only; Gen 1, original-lineage, and production status remain unverified.

### `LamontLabs/QuantraCore_production`

- **URL / access:** <https://github.com/LamontLabs/QuantraCore_production>; public repository metadata was readable.
- **Identity/access result:** Metadata reports size 0 and default branch `main`; the branches endpoint returned no branches, there are no tags, root contents returned HTTP 404, and commit lookup returned HTTP 409. No source file or license was available to hash.
- **Disposition:** Not a source mapping. It does not establish a production implementation; that limitation remains attached to the core role.

## Protocol namespace inventory and boundaries

| Repository / namespace | Observed inventory | Classification and limits |
|---|---|---|
| QuantraCore-Engine `src/quantracore/protocols/` | T01–T12; T09 has two paths with byte-identical contents. | Early scaffold protocol namespace. Its identifiers collide with the later Apex tier namespace; paths/repositories are part of every identity. No tests were present in the complete tree. |
| Apex `protocols/tier/` | T01–T80 (80 modules). | Tier/market-analysis intelligence modules. The inspected T24/T25/T34 implementations calculate breakout, channel-position, and rate-of-change measures; they are not runtime permission gates. |
| Apex `protocols/learning/` | LP01–LP25 (25 modules). | Learning-protocol namespace, separate from T IDs. |
| Apex `protocols/monster_runner/` | MR01–MR20 (20 modules). | Runner-detection namespace, separate from T IDs. |
| Apex `protocols/omega/omega.py` | Source header declares Ω1–Ω20. | Separate directive/override namespace. Some are safety locks and overrides; others are alerts/warnings. Constructor flags can disable individual directives, which conflicts with the documentation claim that the directives cannot be bypassed. Enforcement is not certified here. |
| Apex `risk/engine.py` | `RiskPermission` values `ALLOW`, `DENY`, `RESTRICTED`; risk assessment returns a permission and denial reasons. | A separate runtime risk gate, not a T-numbered intelligence protocol. Its actual enforcement in a complete runtime was not exercised. |

### Manifest discrepancy

At the pinned Apex commit, `config/protocol_manifest.yaml` identifies version 9.0-A, snapshot `apex-v9.0A-20251129`, and `protocol_count: 115`. Its entries parse as T01–T80 (80), LP01–LP25 (25), MR01–MR05 (5), and Ω1–Ω5 (5). The checked-in source tree instead contains MR01–MR20, while `omega.py` declares Ω1–Ω20. The 115-entry manifest therefore does not enumerate all observed MR/Omega source components. It is not treated as a complete code inventory.

### Duplicate-ID handling

- The bare identifiers T01–T12 occur in both QuantraCore-Engine and Apex `protocols/tier/`. They are separate keys qualified by repository, commit, and path; no equivalence is inferred.
- T01 is an observed semantic conflict: Engine's source docstring calls it “Zero-Drawdown Entry detector (ZDE v1),” while Apex `tier/T01.py` calls it “Trend Direction Protocol.”
- T09 is another observed semantic conflict: Engine calls it “Micro Pullback Timing,” while Apex `tier/T09.py` calls it “Range Compression Protocol.” Engine's duplicated nested T09 path is byte-identical to its own top-level T09 path.
- The remaining shared T02–T08 and T10–T12 IDs remain repository-qualified; their meaning is not inferred from matching numbers or filenames.

## T24, T25, and T34 source interpretation and verification cases

Pinned source code, not the protocol number or the tier-document table, is the basis for these cases. `docs/PROTOCOLS_TIER.md` labels T24 “Volume alignment with trend,” T25 “Volume rejection under high entropy,” and T34 “Strength zone mapping.” The corresponding source files instead describe ATR breakout detection, Keltner-channel position, and rate-of-change momentum. Those conflicts are unresolved; the manifest records source behavior without declaring which historical wording was canonical.

| ID / pinned path | Source behavior | Source-derived verification case (expected by the code; not executed) |
|---|---|---|
| T24 `protocols/tier/T24.py` | Returns `insufficient_data` below 20 bars. Otherwise computes true-range ATR, last-close movement, and the last-five-bar range; strong breakout fires when `atr_multiple > 2.0` or `range_atr > 3.0`. | 20 bars with the first 19 closes at 100 and high/low 101/99; last bar open 100, high 107, low 99, close 106. Expected: `fired=True`, `signal_type="strong_breakout"`, `atr14=34/14`, `atr_multiple=6/(34/14)`, confidence `0.6 + 0.1*atr_multiple`. A 19-bar input should return `fired=False`, confidence 0, and `reason="insufficient_data"`. |
| T25 `protocols/tier/T25.py` | Returns `insufficient_data` below 20 bars. Otherwise checks current close against a channel around the last-20-close **arithmetic mean** and a true-range average. The source names the mean `ema20`, but it is not an exponential moving average. | Use the same 20 bars as above. Expected: mean 100.3, ATR 44/19, upper channel `100.3 + 2*(44/19)`, and `signal_type="above_upper_keltner"` with `fired=True`. With 20 flat bars at close 100, high/low 101/99, expected `within_keltner`, `fired=False`. |
| T34 `protocols/tier/T34.py` | Returns `insufficient_data` below 20 bars. Otherwise computes 10/5/1-period rate of change, a 10-period ROC z-score, and ROC acceleration. `abs(roc_zscore) > 2.5` yields `extreme_momentum`. | Use 19 closes at 100 and a final close of 120 in a 20-bar window. The source formulas yield ROC10=20, ROC5=20, ROC1=20, ROC mean=2, standard deviation=6, z-score=3. Expected: `fired=True`, `signal_type="extreme_momentum"`, confidence 0.9. Twenty flat closes at 100 should yield `normal_momentum`, `fired=False`. |

**Existing test coverage:** `src/quantracore_apex/tests/test_all_tier_protocols.py` checks/imports T01–T80 with missing modules converted to skips. Its execution loop covers only T01–T20 and looks for `run_Txx`, while T24/T25/T34 expose `run(window, microtraits)`. It does not assert the behaviors in the cases above. The ApexLab pipeline test is `src/quantracore_apex/tests/test_apexlab_pipeline.py`. The Engine repository has no tests in its complete tree. No legacy tests were executed and no legacy runtime modules were imported.

## Hash verification

Git blob IDs below are GitHub's identifiers. For the sampled files with a raw SHA-256, the Git blob SHA-1 was independently recomputed as `SHA1("blob " + byte_length + NUL + raw_bytes)` and matched the GitHub blob ID. Hashes identify exact bytes, not the authorization or historical origin of a repository.

| Repository revision | Path | Git blob SHA-1 | Raw SHA-256 |
|---|---|---|---|
| Engine `67597a2a63fd3957e6ec50e270dba8e3df1d3757` | `README.md` | `af9cbdfbf6c16acaca7c754b1800b805903e6a07` | `d32ed8cf9618bc7decea8bb4599d92de4f54d847f8ab7036d188bca1bb72f0b1` |
| Engine same | `src/quantracore/protocols/T01_zde_detector.py` | `d6b050553c1b859adbfb2d62b6f00aaa8c1cd700` | `9a0e4b2b0d11b42e9c31f3cd8e895024adf31dcecefd1dc08004215ccb1ab305` |
| Engine same | `src/quantracore/protocols/T09_micro_pullback_timing.py` | `ce5eca1852ff0cae3e720b0f75596c2a80f388b4` | `00b1eb0fba9f17e4af27694f67b269b8f559ee46e816c33e8bbe1cf4d1216dff` |
| Engine same | `src/quantracore/protocols/src/quantracore/protocols/T09_micro_pullback_timing.py` | `ce5eca1852ff0cae3e720b0f75596c2a80f388b4` | `00b1eb0fba9f17e4af27694f67b269b8f559ee46e816c33e8bbe1cf4d1216dff` |
| Apex `d65ad25b813977b1087b94db5f88a32963426477` | `README.md` | `ab7051c058b97550023e69e73200a4bf6f60adab` | `7cfba2db9715cba330be54ca7a3cd9ab5adde6519ee5d3252edc06a1a4944da5` |
| Apex same | `LICENSE` | `165291c0a65176ed5794d605b7a6102d2c37f25e` | `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9` |
| Apex same | `docs/APEXLAB_OVERVIEW.md` | `e0c729b18cceb207b6f0da07b01f87df99440dc2` | `5ff079020c9d0be23ff8cab70ac902ee7fa88f6da4a702e9e4f1efc1da78fd77` |
| Apex same | `docs/APEXLAB_V2.md` | `d46b6d9ca48376cf4cf0dea8960e05dc2efcc452` | `ebcc3543103e696ac33ddc9519e2fcf35b08cb52c5a5dade0171d2ef948645e6` |
| Apex same | `docs/CORE_ENGINE.md` | `9163e6e95aff3a527317ea4cc097961100d8ce52` | — |
| Apex same | `docs/COMPLIANCE_AND_SAFETY.md` | `1ac81a3fe0e8186882e08f4342361c4790c94ce9` | — |
| Apex same | `docs/PROTOCOLS_TIER.md` | `83ac4c5c1234b960a5ca8a415ce22a196f1904d2` | `6aa104ceab9dcd94f4a0e777f952cdd7d06bc1740fa0b93053103ffeb8bdae16` |
| Apex same | `config/version_manifest.json` | `7394e168cda0c7329f5ff26717ad9a36c76946e4` | `375b21a85fd16bdabcbd4e68db211b63f312fb3c0b5916dada33a399d0780c9e` |
| Apex same | `config/protocol_manifest.yaml` | `3cf7246cbe1169e79e62a9313da68a90f1732303` | `410409e1cf98dbda4d2f4302b629a7ea9f9dadf2f1ec3584c6706328ee62bee3` |
| Apex same | `src/quantracore_apex/core/engine.py` | `e7cfdd2081a22ea99a8c2d6e56d310915a3a55df` | `824736919c96093a0c5caf95e5529a3acca7e05b1c4f1c8ad85931215e616dae` |
| Apex same | `src/quantracore_apex/risk/engine.py` | `26e52bcbb6e4aab4e135b4c323cb34ba6d86c14d` | `d226ea85b07b1a4ec5b719de3e6bcae8a92e57f97ecf4cb11cd109747da6912a` |
| Apex same | `src/quantracore_apex/apexlab/apexlab_v2.py` | `9dd2159b3565893fec745f0a4c1a818db59e27a6` | `52f406bee3bdaaecb3632085a5d9b001c5d12902ee46ae9f5fe20bd8961a226a` |
| Apex same | `src/quantracore_apex/tests/test_apexlab_pipeline.py` | `0f8b31b6b0e81b2bad9780b26a00c938b9903955` | `8ebca090299e33e4861bfbcf455213cf66c618f113c7a6b30c13a1c589f8af0b` |
| Apex same | `src/quantracore_apex/tests/test_all_tier_protocols.py` | `e1dc9fe6eb89da289fc240a25a6e08505b790983` | `d39b49f869617ddfc713ec3521957ce3aefa9147b2ab7cc988cdbb7c29124e58` |
| Apex same | `src/quantracore_apex/protocols/tier/T01.py` | `34270eb06a61b34b614baeef3cc99e35188555b6` | `c29c5b36ae5d615be625b9c9556056e9466c0d91601e8b1942896d2aa10f1963` |
| Apex same | `src/quantracore_apex/protocols/tier/T09.py` | `531cff5c5099a7aa206f348f3c084fd377ec7f5b` | `514c4b22ab57a64a63a529ec04cd90c46c30b9bdb2810d16f2027af14cd1912f` |
| Apex same | `src/quantracore_apex/protocols/tier/T24.py` | `5618550210510969adf2d52ced99c3845fe87147` | `64ed3ecff7dc161c2eed86535cc5533ce7fb7495a718e0b1b47c840f36a13ed5` |
| Apex same | `src/quantracore_apex/protocols/tier/T25.py` | `04b3fbb316afd3c22d78265557b5143f3a04a178` | `bc4a2d99ee4c35425d7966beda4c8e340ab69d02f8bf6321bc56dae1fc2e88f0` |
| Apex same | `src/quantracore_apex/protocols/tier/T34.py` | `6bdd284ae92a233627a495cbde31f13055687125` | `51a2cfaee7de0c15d8cdf43af0ccd099b66a4fcc46891290fe36e23c0f103c32` |
| Apex same | `src/quantracore_apex/protocols/omega/omega.py` | `c26a14360a20f32cb66edea7853c7145e0a855a5` | `44d777c493c6f8b1e6f0b94b75b1a095f64a5469269fc9f983d2b7cc626566e1` |
| Apex same | `tests/risk/test_risk_rejection.py` | `03ef52dabf4315b343380e14a7c6e248c0a01370` | `144638823a77b887fe7e73cf30816250a687e326e78ec3f5b0c58fdbe25c0112` |

## Acceptance record

- Sampled Git blob SHA-1 recomputations matched GitHub for the listed source and test samples; raw SHA-256 values are recorded above.
- Duplicate IDs are repository/path-qualified. Engine T09 duplicate paths were confirmed byte-identical; cross-repository T01 and T09 meanings demonstrably differ.
- Legacy working trees were not changed: no local source trees were used, all GitHub operations were GET-only, and no code was imported or executed.
- No full legacy test suite was run. The T24/T25/T34 cases above are source-derived checks, not claimed passing legacy tests.
- **Acceptance:** PASS for QC2-001's corrected logical-role gate. Exact Gen 1 identity, original protocol origin, and production deployment/authorization remain unverified and are not represented as found.
