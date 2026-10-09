# QC2-043 — Atomic Champion Transition

## Acceptance assessment

- **Result:** PASS
- Prepare, verify, and commit are separated; commit rechecks approval and compares the locked operating slot's state, generation, and pointer hash before writing a new generation.
- The PostgreSQL transaction records the local approval nonce, evidence, lifecycle change, durable transition receipt, forward-rollback retention, pointer compare-and-swap, and load-request outbox message atomically. Fault injection confirms rollback leaves no partial authoritative state.
- Bootstrap requires an explicit `NO_CHAMPION` slot. A forward rollback creates a new transition to a retained retired model; it does not restore or mutate an old pointer.
- New runs require a successful load confirmation for the exact current pointer and generation. A failed or missing load blocks new runs, while existing runs retain their original binding.
- Production approval remains disabled. The Owner API ledger and the Champion PostgreSQL commit do not yet share a transaction, so the Owner API nonce is not consumed atomically with the database compare-and-swap. No fixture approval or production transition is enabled.

## Acceptance checklist

- [x] DELIVERABLE: Prepare/verify/commit state machine, compare-and-swap pointer generation, receipt/outbox. | evidence: `tests/promotion/test_transition.py` covers prepared snapshots, recheck, stale generation, durable receipt/outbox, idempotent replay, unknown commit outcome, and transaction fault points; the PostgreSQL acceptance applies migration 0007 and verifies atomic durable state.
- [x] DELIVERABLE: Initial NO_CHAMPION bootstrap and forward rollback transition types. | evidence: Python and PostgreSQL acceptance start from generation-zero `NO_CHAMPION`, then commit a forward rollback as generation 3 to the retained retired model.
- [x] DELIVERABLE: Worker load-confirmation and new-run readiness guard. | evidence: Worker load requests and confirmations bind the exact pointer, generation, and model; tests prove failed or missing loads block new runs and existing runs keep their prior binding.
- [x] TEST: Fault injection before/after every transaction step; exactly one committed pointer. | evidence: Python and PostgreSQL suites inject faults around approval, nonce, evidence, receipt, lifecycle, pointer, CAS, and outbox writes; every failed attempt preserves the baseline, and only one pointer commits.
- [x] TEST: Two approvals/promotions racing cannot consume one nonce twice or overwrite stale state. | evidence: The barrier-synchronized two-promotion race has exactly one winner; the other fails on stale generation, with one nonce consumed and one committed pointer.
- [x] TEST: Commit-success/load-failure blocks new runs; old bound runs retain their generation. | evidence: The transition/readiness test rejects new runs after failed or absent worker load confirmation, then confirms old runs remain bound to generation 1 after generation 2 commits.
