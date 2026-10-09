---
name: QC2 owner approval binding
description: Contract-boundary decisions for owner-signed promotion approval and its future transition consumer.
---

Keep owner-approval-only domain, action, environment, device, session, and idempotency scope in versioned `packages/owner_api` envelopes. Do not add those fields to already accepted canonical promotion contracts without explicit drift authorization. `OwnerDevice` and `OwnerSession` are not content-addressed; bind their typed record IDs plus a public-key fingerprint and a canonical session-binding hash instead of inventing content hashes.

**Why:** the canonical promotion contracts are pinned by earlier acceptance evidence, and identity records have mutable revocation state without content hashes. The local envelope adds the required scope without changing either contract's accepted bytes.

**How to apply:** validate both the local scope envelope and the canonical promotion record. A future transition consumer must perform a fresh identity/state recheck and consume the approval nonce in the same transaction as the Champion compare-and-swap; fixture identities never authorize that transition.
