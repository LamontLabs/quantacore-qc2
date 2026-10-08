# QC2-015 — Label Authority decision

## Registry and target families

- The registry contains Expansion Runner and Session Monster definitions at 1-, 3-, 5-, and 10-session horizons.
- The primary label is `expansion_runner_5_session`. Its display alias is Runner Probability; the alias is not a separate target.
- Secondary Expansion Runner horizons are 1, 3, and 10 sessions. Session Monster targets are separately registered at each supported horizon and mean at least one qualifying per-session event.
- Continuation, Failure, and Time-to-Expansion definitions are explicit `UNAVAILABLE_LABEL` placeholders until their target semantics are frozen. Failure is not one minus Runner.
- The default registry is test-only with all Expansion Runner and Session Monster thresholds null. No empirical thresholds or persistence/drawdown filters are selected.

## Exact formulas and reference prices

All prices use one finalized, split-consistent share basis. `t` is the prediction session and `h` is the definition's exact horizon.

For an Expansion Runner definition, the reference is prediction-session close `C[t]`:

```text
endpoint_return_h = C[t+h] / C[t] - 1
max_high_return_h = max(H[t+1] ... H[t+h]) / C[t] - 1
min_low_return_h = min(L[t+1] ... L[t+h]) / C[t] - 1
mfe_h = max(0, max_high_return_h)
mae_h = min(0, min_low_return_h)
```

The event formula is `max_high_return_h >= frozen_fractional_return_threshold`. No persistence or drawdown condition is frozen. The label contract stores the exact formula and leaves `threshold` null until calibration evidence exists.

For each Session Monster horizon, each future session `i` has a separate event measurement:

```text
session_monster_return_i = H[t+i] / C[t+i-1] - 1
open_to_high_return_i = H[t+i] / O[t+i] - 1
opening_gap_return_i = O[t+i] / C[t+i-1] - 1
```

The horizon-level Session Monster target is true if any per-session return meets its frozen threshold. Opening gap and open-to-high remain separate values; this event is not interchangeable with multi-session Expansion Runner.

Outcome fractional returns are represented to exactly 12 decimal places with `ROUND_HALF_EVEN`; event comparisons use those same stored-precision values. Peak/trough selection uses the observed prices, with the earliest session winning ties. The raw high/low returns remain unclamped; only MFE and MAE are clamped, and MAE stays nonpositive.

The next-open proxy uses `O[t+1]` as its own denominator:

```text
next_open_proxy_endpoint_return_h = C[t+h] / O[t+1] - 1
next_open_proxy_max_high_return_h = max(H[t+1] ... H[t+h]) / O[t+1] - 1
next_open_proxy_min_low_return_h = min(L[t+1] ... L[t+h]) / O[t+1] - 1
next_open_proxy_mfe_h = max(0, next_open_proxy_max_high_return_h)
next_open_proxy_mae_h = min(0, next_open_proxy_min_low_return_h)
opening_gap_return = O[t+1] / C[t] - 1
```

These proxy values do not represent actual paper fills.

## Maturity, validity, and release

The resolver slices the frozen exchange calendar at exactly `t+1 ... t+h`; it never counts the next `h` bars that happen to exist. A halt or missing expected bar does not extend the horizon. A threshold hit before the final session does not release a full-horizon target.

| Outcome state | Condition | Target/release behavior |
| --- | --- | --- |
| `PENDING_MATURITY` | Horizon sessions have not elapsed, or bar/data finalization or the release transaction is incomplete. | No full-horizon target or learning timestamp. |
| `RESOLVED` | Every expected bar is present and finalized; corporate-action checks, data finalization, and release transaction are complete. | Continuous measurements may resolve. A binary target is available only for a defined event with a frozen threshold. |
| `PARTIALLY_RESOLVABLE` | The horizon elapsed but data is missing while some independent fields remain valid. | Valid fields such as the first-session opening gap may remain; no full-horizon event target or learning timestamp. |
| `UNRESOLVED_DATA` | The horizon elapsed but required data is missing and no usable partial result is available. | No target or learning timestamp. |
| `CORPORATE_ACTION_REVIEW` | The adjustment/corporate-action state is not final. | Affected measurements and target remain unavailable. |
| `CENSORED_TERMINAL_EVENT` | A terminal event occurs in the horizon without a supported verified-consideration resolution. | Fields are explicitly censored and no target is emitted. |

Field validity is carried independently with `VALID`, `MISSING`, `UNRESOLVED`, `NOT_APPLICABLE`, or `CENSORED` plus a reason code. `available_for_learning_at` is set only for a resolved, defined target after all required finalization and the release transaction. The current label input does not accept verified terminal cash consideration, so terminal outcomes are conservatively censored rather than inferred.

Production registration is denied while any registered Expansion Runner or Session Monster threshold is unresolved. Production also requires registry-bound calibration, qualification, and owner-decision evidence. The package does not activate a production registry.

The label resolver returns an in-memory calculation, not a persisted Outcome contract; Ground Truth remains the Outcome writer. No provider fallback, live trading, or upstream Apex execution is part of QC2-015.

## Verification evidence

Required synthetic tests cover fixed calendar membership with a missing fifth-session bar, no early release after an early threshold crossing, signed MAE and unclamped extrema, split-basis mismatch, earliest-session ties, zero-event measurements, next-open proxy separation, Session Monster equations, explicit maturity states, and rejection of undefined probability targets.
