# QC2-020 — Runner Protocol Migration Wave 2 reference intake

## Scope and handling

- QC2-020 dependencies passed and the task preflight passed before this intake was written.
- Private GitHub source files below were read at their exact pinned commits. No legacy source was copied, imported, modified, executed, or tested.
- Source test files were read only; none of the legacy test suites were run.
- This intake records the files actually inspected. It makes no repository-wide semantic claims beyond the tree and directory listings noted below.

## QuantraCore-Apex

**Pinned revision:** `Lamont-Labs/QuantraCore-Apex@d65ad25b813977b1087b94db5f88a32963426477`

| Path | Git blob SHA-1 | Raw SHA-256 | Read-only findings and disposition |
|---|---|---|---|
| `src/quantracore_apex/protocols/tier/T24.py` | `5618550210510969adf2d52ced99c3845fe87147` | `64ed3ecff7dc161c2eed86535cc5533ce7fb7495a718e0b1b47c840f36a13ed5` | OHLC-based ATR breakout: after a 20-bar minimum, the source fires `strong_breakout` if `atr_multiple > 2.0` or five-bar range / ATR exceeds `3.0`. Uses floating-point arithmetic. Conflicts with the documentation label “Volume alignment with trend.” Daily F0 equivalence, exact deterministic decimal behavior, calibration, and original lineage are unverified. **Disposition: ignore as a port; do not activate.** |
| `src/quantracore_apex/protocols/tier/T25.py` | `04b3fbb316afd3c22d78265557b5143f3a04a178` | `bc4a2d99ee4c35425d7966beda4c8e340ab69d02f8bf6321bc56dae1fc2e88f0` | Keltner-channel position using a 20-close arithmetic mean named `ema20` and average true range; the mean is not an EMA. Uses floating-point arithmetic. Conflicts with the documentation label “Volume rejection under high entropy.” Daily F0 equivalence, deterministic decimal behavior, calibration, and original lineage are unverified. **Disposition: ignore as a port; do not activate.** |
| `LICENSE` | `165291c0a65176ed5794d605b7a6102d2c37f25e` | `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9` | Demo/evaluation-only terms reserve production and live-trading use absent written consent. Original protocol origin is unverified. **Disposition: no production or live use; no legacy implementation import.** |

### Apex test evidence

The pinned `tests/protocols` listing contained these relevant test files:

| Path | Git blob SHA-1 | Raw SHA-256 | Coverage observed; status |
|---|---|---|---|
| `tests/protocols/test_protocol_execution.py` | `da532e1d9105133d7b575a2e6540292d4f102c1a` | `4e071742a043b0cdb40bb8254ed3017a7ef54e5a133eae6d4b4ccec3c421ce8e` | Runs the general Apex engine against synthetic 100-bar windows and checks result shape, score range, symbols, and determinism. No T24/T25-specific semantic assertions. Read only; not run. |
| `tests/protocols/test_protocol_smoke.py` | `f42ead6ed7d3b0ed9622e005d8828f06fa0538e2` | `49688e637a9aa869774f8c8947397815bd47e16254bfb0f029b10de2d2dbce07` | Checks tier loader breadth, callable protocols, general result fields/ranges, a first-listed protocol, and determinism on synthetic data. No T24/T25-specific semantic assertions. Read only; not run. |

The full recursive Apex tree response was truncated; targeted contents listings verified the tier directory and `tests/protocols` directory used above. No absence claim is made for other test locations. The QC2-018 inventory records the T24/T25 source-test status as `NOT_RUN` and likewise records that the listed pinned tier tests do not assert those source cases.

## QuantraCore-Engine

**Pinned revision:** `Lamont-Labs/QuantraCore-Engine@67597a2a63fd3957e6ec50e270dba8e3df1d3757`

| Path | Git blob SHA-1 | Raw SHA-256 | Read-only findings and disposition |
|---|---|---|---|
| `src/quantracore/protocols/T07_exhaustion_blocker.py` | `71ce099629b7f278ed84b59022b6213930aa1c16` | `a676551b1c57b8d90ffcbb287f7e0f68da6035d27f6f99f798a499b5750a140f` | Reads a mutable, untyped `exhaustion` value; subtracts two points and emits a flag. It does not enforce a block. Scale, horizon, provenance, and cutoff are unspecified. **Disposition: ignore; no port or activation.** |
| `src/quantracore/protocols/T08_breaker_trap_detector.py` | `33d790e490ed91780e36564c91aa7131751c8ea6` | `544419ca19f6b30cb2471cb96a5637787da13feeebf90c93cf9e255a00559368` | Reads mutable, untyped `breaker_trap_prob`, compares it with `0.6`, and subtracts two points. Calibration, source, horizon, and cutoff are unspecified. **Disposition: ignore; do not adopt the threshold or treat it as a probability contract.** |
| `src/quantracore/protocols/T12_failed_breakdown_reversal.py` | `d2adebaf2e83863439956bb9fc48e866d8e02e60` | `600a37f879d7e72ca2239742a58f063f0cc1a17f2330ffffa0ee7addd563dc68` | A truthy mutable, untyped `failed_breakdown_flag` increments score by two and is echoed. No price-path or reversal definition establishes how that flag is derived; a missing flag defaults to zero. **Disposition: ignore; no port or activation.** |

The complete pinned Engine tree contained 41 files, no test tree, and no recognized root license. Repository provenance and original protocol lineage remain unverified. The three source files' tests were not run; no test evidence establishes their semantics, cutoff safety, or calibration.

## Implementation boundary

The legacy records above are exclusion evidence, not implementation inputs. Any QC2-020 research hypotheses are independently specified over the existing QC2-014 registered daily features, preserve that registry's units and warm-up rules, remain in the `research` namespace with `SYNTHETIC_FIXTURE` evidence, and are not activated in an active protocol set. No legacy module ID is treated as proof of meaning.

Similarity is an existing, separately gated daily feature interface. A usable historical prototype must have a strictly earlier event session, matching feature registry, and point-in-time access evidence available by the decision cutoff. Missing or not-applicable similarity inputs remain unavailable; this task does not create a memory-based decision policy.

Concepts requiring unverified intraday path/tick semantics, or a calibrated memory/trap/exhaustion policy, remain excluded or unavailable. No synthetic intraday proxy is introduced.
