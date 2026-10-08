# QC2-016 — Ground Truth Authority decision

## Authority boundary

- Ground Truth consumes only a frozen label registry, eligible instrument/session rows, finalized bar inputs, corporate-action evidence, terminal-event evidence, and optional market-snapshot references.
- It does not read predictions, model opinions, scores, ranks, strategies, or paper-trade state. It persists validated `Outcome` and `RunnerEvent` contracts; the label resolver remains a pure calculation dependency.
- Every supplied eligible row produces exactly one `Outcome`, including pending, partial, censored, and otherwise unresolved rows. Missing data is never converted into a negative event.
- Stable `Instrument` identity is authoritative. Symbol assignments are checked as non-overlapping half-open intervals covering the prediction and observed horizon through any terminal event. A rename does not create a new instrument.

## Outcome and event decisions

- Full-horizon measurements are released only after the frozen calendar horizon, corporate-action finalization, data finalization, and label-release transaction are complete.
- Fractional returns use 12 decimal places with `ROUND_HALF_EVEN`. Event comparisons use the same rounded return; raw prices select extrema, with the earliest session winning ties. MFE and MAE retain their signed/clamped definitions.
- Verified terminal cash consideration per share, normalized to the label's frozen share basis and reference currency, may resolve only endpoint return after corporate-action finalization. Every unavailable full-horizon metric remains censored, and the Outcome is not released for learning. Unverified terminal consideration remains censored and opens an action-review case.
- Corporate-action review and terminal-event review produce separate immutable queue cases. Review decisions require evidence and do not modify or replace any Outcome.
- `EXPANSION_RUNNER` events use the first threshold-crossing session and the observed peak session. `SESSION_MONSTER` events are emitted independently for each threshold-crossing session. No event is emitted when its target is unavailable or false.

## Corrections and learning releases

- Corrections append a new Outcome and an `OutcomeRevision` linking the prior and replacement content-addressed references. The prior record, sealed prediction references, and already-created release batches remain unchanged.
- A correction cannot change logical instrument/session/label identity, evidence class, or environment. The replacement becomes the current version for subsequent learning releases.
- A learning-release batch binds only current, fully resolved Outcomes with a learning-availability timestamp and no unresolved or censored scientific fields. It cannot precede the latest member maturity or mix evidence classes/environments. Synthetic fixture Outcomes are rejected in production.
- These interfaces are immutable and append-only in the offline science package; they do not activate production values or implement live trading.

## Verification boundary

- Synthetic fixture inputs prove formulas, unresolved-state retention, terminal handling, independent event generation, idempotency, correction immutability, and learning-release gating.
- No empirical calibration or production activation is claimed.
- Gen 1 ForwardValidator source was not inspected, copied, imported, or executed; see the reference intake.
