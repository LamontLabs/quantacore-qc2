# QC2-044 — Strategy parameters and activation gates

This is a framework-only implementation. No production StrategyManifest,
CapitalPolicy, empirical parameter set, owner approval, or calibration result was
created by this task.

## Rules represented by the framework

- Predictions enter through a contract-validated projection. A caller must verify
  prediction-seal membership and provide current, verified US-common-equity and
  USD symbol eligibility; failure rejects the projection.
- Selection uses the prediction authority's rank. Ties and allocation are
  ordered by stable instrument ID; the strategy does not recompute scores.
- New proposals are long-only, whole-share, regular-session DAY buy limits.
  The limit cap is computed from the sealed prediction-session close and a
  separately resolved buffer, then rounded down to the verified price tick.
  The plan reserves limit notional plus the explicitly configured cost buffer.
- Owner position, starting-capital fraction, gross-exposure, cash-reserve,
  concurrent-position, daily-loss, and participation limits intersect by
  minimum; strategy settings cannot widen them. Entries stop at the daily loss
  limit, on unreconciled external activity, while prior exits are unresolved,
  or when account, cooldown, market-session, price-tick, or DAY-order evidence
  is incomplete.
- Existing holdings and active reservations prevent pyramiding. Re-entry
  cooldowns count exchange sessions and require complete cooldown history.
  Unfilled DAY entries are not upgraded or chased.
- Stop, target, trailing, and maximum-hold behavior are explicit rules. A
  completed daily bar touching both stop and target returns
  `INTRADAY_PATH_AMBIGUOUS`; the conservative scenario is labeled as a
  stop-level scenario, not a broker fill. Fill feedback is separate from
  scientific labels.

## Values that remain unresolved

No numeric values in the fixture profiles are recommendations or empirical
estimates. Before production activation, the following must be resolved and
bound to immutable, verified records:

- **Owner policy:** starting capital, per-position cost and fraction, gross
  exposure, cash reserve, concurrent positions, daily-loss/drawdown response,
  participation limit, and external/manual activity treatment. The exact
  CapitalPolicy content hash must have a valid owner-command approval receipt.
- **Strategy calibration:** selection K; price-cap and cost buffers; per-entry
  ceiling; stop, target, and trailing thresholds if used; holding duration; and
  cooldown. The exact StrategyManifest, ConfigurationManifest, and resolved
  rules digest must pass the configured calibration verifier.
- **Execution readiness:** a sealed paper ExecutionEpisode, next exchange
  session, current reconciliation, broker price tick, regular-session DAY
  limit support, and measured execution window. Unsupported or missing evidence
  blocks proposals; no alternate order type or provider/feed fallback is used.

The only supported policy behavior in this framework halts new entries at the
daily-loss limit and blocks them while external account activity is
unreconciled. A different owner policy needs an explicit framework change.

## Activation and execution boundary

`assess_activation_readiness` is a pure readiness check, not an activation
operation. It fails closed unless both the owner-approval verifier and
calibration verifier approve the exact hashes. Synthetic, historical, test,
development, or research inputs are not eligible. The allocation output always
has `submission_authorized = false`; it creates neither PaperOrderIntent
records nor broker submissions. QC2-045 owns the subsequent intent boundary.

Fixture profiles are named `test_only_*`, use synthetic evidence and a test
namespace, and include non-resolving placeholder references only to exercise
strict schemas. Their activation gate rejects them even if test callbacks claim
approval or calibration.
