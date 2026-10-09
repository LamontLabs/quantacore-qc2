# QC2-048 — Durable Position State

## Acceptance assessment

- **Result:** PASS
- Execution episodes, broker orders, broker events, fills, fill corrections, cash entries, corporate-action adjustments, and reservation settlements are preserved as append-only records. Runtime execution authority can read its ledger and mutate it only through scoped database functions.
- The deterministic projector deduplicates provider facts, orders partial fills by economic time, applies signed quantity/price/fee corrections, and computes cash, positions, and reservation state from the retained records. Conflicting identities, quantity overruns, and short sales hold the episode; projections never emit negative positions.
- Position and cash projections are persisted from the replay result. Cash balances derive from the episode opening baseline plus immutable ledger entries. Corporate-action terms are explicit; a cash distribution must name an order in the same episode and instrument as its intent anchor.
- Python fixture tests cover out-of-order partial fills, duplicate and conflicting provider identities, bust and other corrections, deterministic replay, corporate actions, reservation holds, and short-position blocking. A fresh UTF8 PostgreSQL cluster applies migrations through 0010, runs the QC2-045/046 setup, and verifies the QC2-048 persistence path, idempotency, cash distribution, reservation settlement, and append-only enforcement.
- No live broker calls, provider lookup, runtime feed fallback, fixture activation, or production mutation was performed.

## Acceptance checklist

- [x] DELIVERABLE: Immutable broker-event/fill ledger, correction events, positions and cash projections. | evidence: `migrations/0010_durable_position_state.sql` installs append-only facts and replay projections; `packages/execution/src/qc2_position_state` implements immutable domain models, adapters, ledger, and deterministic projector; PostgreSQL acceptance verifies ledger persistence and replayed balances.
- [x] DELIVERABLE: Cumulative-quantity checks, reservation settlement and execution-episode identity. | evidence: projector and database checks bind orders to sealed episodes, reject overfills, settle reservations from cumulative corrected quantities, and retain episode hashes; Python and PostgreSQL acceptance verify these paths.
- [x] DELIVERABLE: Corporate-action position adjustment interfaces. | evidence: the adapter requires explicit normalized share and cash terms; the database API persists adjustment terms and requires an explicit matching order anchor for cash distributions.
- [x] TEST: Duplicate/out-of-order/partial fills do not double count shares or cost. | evidence: `test_duplicate_and_out_of_order_partial_fills_rebuild_once` and the PostgreSQL acceptance verify ordered replay and duplicate-fill idempotency.
- [x] TEST: Trade correction/bust appends compensating state without deleting evidence. | evidence: `test_correction_bust_is_compensating_and_never_deletes_fill`, `test_quantity_price_and_fee_corrections_replay_deterministically`, and PostgreSQL correction persistence verify compensating entries while original fills remain immutable.
- [x] TEST: Projection rebuild equals persisted totals and disallows accidental short position. | evidence: deterministic Python replay is compared with PostgreSQL position/cash projections; short inputs are rejected and over-sales retain a nonnegative HOLD projection.
