# QC2-021 — Runtime Safety Protocol Framework reference intake

## Scope and handling

- Checked at 2026-10-08T06:35:29Z. GitHub calls were read-only. No external source was cloned, changed, imported, executed, or tested.
- QC2-013, QC2-017, and QC2-020 have PASS receipts. `python3 tools/task_workflow.py preflight QC2-021` passes.
- The task authorizes inspection of a “Gen 1 QC-T01–T65 safety lineage,” but the exact repository, revision, and namespace are not identified by the existing source records or the searches below. The candidate T-numbered namespaces are distinct runner or weighted-analysis protocols, not action-specific safety protocols.
- **Disposition:** `IGNORE` + `SOURCE_UNRESOLVED` for the requested legacy lineage. No equivalence or safety meaning is inferred from matching T numbers. Implement QC2-021 only from the independent Gen 2 specification; do not import legacy code or tests.
- Legacy test sources were read only where listed. No legacy test suite was run.

## Candidate namespace cross-checks

### QuantraCore-Engine

**Identity:** `Lamont-Labs/QuantraCore-Engine@67597a2a63fd3957e6ec50e270dba8e3df1d3757` (private; existing QC2-001 and QC2-018 source records).

The pinned complete tree has the `src/quantracore/protocols/` T01–T12 runner scaffold, not a QC-T01–T65 safety namespace. T01 and T09 already conflict with same-numbered Apex-T sources. The current tree listing exposed protocol paths only; the meanings below come from earlier pinned, read-only intakes:

| Path | Git blob SHA-1 | Raw SHA-256 | Source-supported meaning and evidence |
|---|---|---|---|
| `src/quantracore/protocols/T01_zde_detector.py` | `d6b050553c1b859adbfb2d62b6f00aaa8c1cd700` | `9a0e4b2b0d11b42e9c31f3cd8e895024adf31dcecefd1dc08004215ccb1ab305` | QC2-001 records a “Zero-Drawdown Entry detector” source description. It is an Engine-T runner identifier, not proof of a QC-T safety gate. |
| `src/quantracore/protocols/T07_exhaustion_blocker.py` | `71ce099629b7f278ed84b59022b6213930aa1c16` | `a676551b1c57b8d90ffcbb287f7e0f68da6035d27f6f99f798a499b5750a140f` | QC2-020 records an untyped exhaustion input and score deduction; no action permission is enforced. |
| `src/quantracore/protocols/T08_breaker_trap_detector.py` | `33d790e490ed91780e36564c91aa7131751c8ea6` | `544419ca19f6b30cb2471cb96a5637787da13feeebf90c93cf9e255a00559368` | QC2-020 records an untyped value compared to `0.6` and a score deduction; calibration and cutoff are unspecified. |
| `src/quantracore/protocols/T12_failed_breakdown_reversal.py` | `d2adebaf2e83863439956bb9fc48e866d8e02e60` | `600a37f879d7e72ca2239742a58f063f0cc1a17f2330ffffa0ee7addd563dc68` | QC2-020 records a truthy flag that increments score; it does not establish a safety permission. |

The complete Engine tree has no test tree and GitHub reports no recognized root license. The existing intakes document these limits. **Disposition:** ignore as a source for QC-T safety semantics.

### QuantraCore-Apex

**Identity:** `Lamont-Labs/QuantraCore-Apex@d65ad25b813977b1087b94db5f88a32963426477` (existing QC2-001 and QC2-018 source records).

The inventory classifies `protocols/tier/` as Apex-T T01–T80 market-analysis modules. Apex T01 is described in the existing inventory as a Trend Direction Protocol and conflicts with Engine T01. Apex T65 is present at `src/quantracore_apex/protocols/tier/T65.py` (Git blob `9ad2758ddb7153fb0d3a43a4c543291d33aadc5c`), but its body was not reviewed in the source inventory; no meaning is inferred from its filename.

Existing test evidence covers general tier loading/smoke behavior, not action-specific permission semantics for T01 or T65. Tests were not run. The pinned Apex `LICENSE` (`165291c0a65176ed5794d605b7a6102d2c37f25e`, raw SHA-256 `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9`) is demo/evaluation-only and reserves production/live use absent written consent. **Disposition:** ignore as a QC-T safety source; do not port or activate.

### QuantraVision candidate namespace

**Identity:** `Lamont-Labs/QuantraVision@80cf295421cccd62c25ff8dbd459cd9bfb7ffcd6`. This was checked as a possible T01–T65 collision, not established as the authorized Gen 1 safety source.

| Path | Git blob SHA-1 | Raw SHA-256 | Findings |
|---|---|---|---|
| `README.md` | `5e457e0dd98efeba5602e89a451d70a52ec31b83` | `729ddc243b0f07aed69d6bdde047c5816e2b78b15de85cd4ec0a96fa7d7e2418` | Describes QuantraVision’s Apex pattern-validation suite; it does not identify a Gen 1 QC-T safety lineage. |
| `app/src/main/java/com/lamontlabs/quantravision/apex/ProtocolRegistryMobile.kt` | `59378498528b57b3e8f4736cfc06394619f7649f` | `cdde8561533e1034fb3dec960fca8ec6163257dd6f530ecb17ab3d933dbd03ae` | Registers T01–T80 as weighted `ApexProtocol` tier protocols returning `ProtocolVerdict`; the registry names Omega01–04 separately as safety checks. This is a different namespace and contract. |
| `app/src/main/java/com/lamontlabs/quantravision/apex/protocols/tier/T01InputSanitization.kt` | `ba39b16b02a2e93e6b574a1c5ba319f8fe7e01b2` | `2712afdf2db3b14f63b88e929b47d5c06a372a7747884e8dd4d269126466016e` | T01 tier implementation returns an Apex protocol verdict; it does not return an action-scoped permission result. |
| `app/src/main/java/com/lamontlabs/quantravision/apex/protocols/tier/T65CoherenceValidator.kt` | `f01efd40b2f21e2e02fbaff9460e032ddc944fd6` | `a5fecb0bdcdc815c9a64a2b547ec25e2372e6de880f7e986459f0ca49eec2c65` | T65 tier implementation returns an Apex protocol verdict; it is not an action-specific safety result. |
| `app/src/main/java/com/lamontlabs/quantravision/apex/protocols/tier/mobile/T01.kt` | `dd03b26ca717bed7ff34a144fb61113492e841d1` | `1c177ff8e16b15b2c5dfa17cb71263a118dc9af1ba2758e4984230f98a699b94` | Type alias to the tier T01 implementation above; it does not create a separate safety protocol. |
| `app/src/main/java/com/lamontlabs/quantravision/apex/protocols/tier/mobile/T65.kt` | `d91c268ab9898a1c0a5a86f93c09c49cb09a11b2` | `eff2d1dde87c41d6157d7c24df8902d9b48e4eb5840bc1dc0dfaf58ddf55cc9f` | Type alias to the tier T65 implementation above; it does not create a separate safety protocol. |
| `app/src/test/java/com/lamontlabs/quantravision/apex/protocols/tier/TierProtocolsT01Test.kt` | `1bf14c16be7e9392cf420dcfcb945b9ce89a85fe` | `3acb33dc60c56a552bc24e081108ebe4258add51e74304fc37d75eff3a499fe1` | Tests verdict behavior, confidence, mutable state, determinism, and input edge cases. It does not test action authority. Read only; not run. |
| `app/src/test/java/com/lamontlabs/quantravision/tiers/TierRegistryTest.kt` | `63fc60eea3b375e5694426ffd4f9936b20d003b7` | `d495fb21f69616f57c3320736e89c80d26d866095476869526fedca852d48209` | Tests subscription quota tiers; unrelated to Apex protocol tiers or safety gates. Read only; not run. |
| `LICENSE` | `dc9be951d061f9d4a14abb313c0cc1d53c68f57a` | `12d360e6fcd7a6bfa478cb85885f891801f1ee56e312e6581ce04feec9422896` | Apache 2.0. The license does not establish historical identity with the requested Gen 1 lineage. No source is copied. |

The inspected tier-test listing contains T01 and selected other T tests, but no T65-named test file. No T65-specific test coverage was established and no tests were run. **Disposition:** ignore as a mapping source; keep the T01–T80 weighted tier namespace separate from safety.

### Cognitive Infrastructure Layer (CIL)

**Identity:** `Lamont-Labs/Cognitive-Infrastructure-Layer@672f35eabb1b519f14654a0b7adc731abe31a8b5`.

| Path | Git blob SHA-1 | Raw SHA-256 | Findings |
|---|---|---|---|
| `README.md` | `f047c03334a25e75425dd16f3cbe39d3787c50f6` | `5936cbd1d5eb97e56903d0c8674f85216d6d70fcdd775d766f2083e92ff2b441` | Describes an experimental support-domain cognitive runtime and its own safety constraints, not trading-action permissions or QC-T numbering. |
| `docs/safety-primitives.md` | `1480ca05e32cb9bc7838116c2d21fbddffa33a01` | `8b45a8c99927b58c99a8b3a5f30b82029fd2232ae1ea81d34fa6d2ffde2663da` | Describes scope drift, contradiction arbitration, governance, poisoning, replay, and circuit-breaker concepts for cognitive-asset reuse. These do not define the requested action gates. |
| `LICENSE_DECISION.md` | `b4adb3ce55968eddfa605e3c86710cee755ee5e2` | `8ed7cade373d119eaa31724f3417c3d51efb6f05d6802bb798610d11a3da5396` | States “source-available preview only” and no open-source license; reading and attributed discussion are allowed, but copying or incorporating source code is prohibited absent written permission. |

No CIL code or tests were imported or run. **Disposition:** ignore; its different domain and source-available restrictions make it unsuitable as an implementation source.

## Exact QC-T namespace search and disposition

- Read-only GitHub code searches for the literal identifiers `QC-T01` and `QC-T65` in the Lamont-Labs organization returned no matches. This search does not establish that no source exists outside that organization or its indexed code.
- Existing source records identify Engine-T as a T01–T12 runner scaffold and Apex-T as T01–T80 analysis protocols. QuantraVision uses another T01–T80 weighted tier namespace and separately names Omega safety checks. None is verified as the requested QC-T01–T65 safety lineage.
- The exact authorized source identity remains **SOURCE_UNRESOLVED**. No old T number is mapped to a Gen 2 safety policy. The independent Gen 2 implementation may proceed without this lineage because the task does not require importing it; this exclusion is explicit and does not claim source verification.
