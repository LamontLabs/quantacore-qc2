---
name: Execution PostgreSQL acceptance fixtures
description: Fixture ordering for evidence-producing pause operations and paper-order outbox transitions.
---

For PostgreSQL acceptance around entry pause/resume, test both transactional evidence failure and success: call the evidence-producing operation without an active stream, require a constraint failure and unchanged pause state/generation, then create an explicit synthetic evidence stream before successful state changes. For paper-order submission, let `enqueue_paper_order_submission` perform the transition from `RESERVED` to queued; do not transition the intent manually first.

**Why:** Pause appends its audit event within the same transaction, and enqueue only accepts the reserved state. Mis-seeded fixtures can test an unintended failure path instead of the real runtime sequence.

**How to apply:** In a disposable acceptance database, build preconditions through the actual stored APIs and assert state remains unchanged around expected failures.
