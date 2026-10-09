---
name: Reconciliation checkpoint hashes
description: Keep repeated broker/local inventory checks stable when reconciliation itself advances control generations.
---

Inventory checkpoint hashes must cover canonical inventory facts and observation identity, not a control-generation counter that reconciliation itself can advance when setting or clearing a hold.

**Why:** Including hold-side-effect generations makes unchanged local and broker inventories appear to be new checkpoints, defeating idempotency and producing unnecessary evidence events.

**How to apply:** Keep storage/control generations available for diagnostics, but exclude them from local inventory content hashes. Include actual order, fill, position, cash, account, and broker-observation facts.
