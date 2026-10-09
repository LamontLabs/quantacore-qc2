# QC2-042 — Owner Approval Authority

## Acceptance assessment

- **Result:** PASS
- Approval decisions bind the promotion request and exact candidate, bundle, Champion hash/generation, epoch, registries, policy, device, session, action, domain, environment, and nonce.
- P-256 signatures are verified over the versioned canonical owner-decision envelope. Idempotent retries return the recorded decision; conflicting keys and nonce replay fail closed.
- Approve reserves the nonce for the downstream atomic transition. Hold/reject consume it without approval authority. Expired challenges become terminal.
- The commit-time interface revalidates the signed record, current promotion snapshot, session/device identity, and signature. QC2-043 must consume the resulting ticket in the same transaction as the Champion compare-and-swap.
- This implementation accepts only synthetic fixture identities in test/development. Production approval is hard-disabled; no identity-provider, durable-ledger, Champion-writer, or broker adapter is added.

## Acceptance checklist

- [x] DELIVERABLE: Challenge/envelope schemas, nonce lifecycle, approve/hold/reject records and idempotency. | evidence: Owner API schemas and the P-256 fixture suite exercise canonical records, retries, nonce reservation, terminal hold/reject, replay, and expiry.
- [x] DELIVERABLE: Domain/action/environment separation and commit-time identity recheck interface. | evidence: The signed envelope keeps all three scope fields distinct; commit recheck verifies stored signature, current snapshot, and live identity-provider port result.
- [x] DELIVERABLE: Fixture-device tests and explicit production-disabled guard. | evidence: Tests use a synthetic P-256 fixture key and assert fixture/non-production restrictions; `PRODUCTION_APPROVAL_ENABLED` is false.
- [x] TEST: Reject replay, expiration, changed candidate/current Champion/epoch/policy, and revoked identity. | evidence: Hostile fixtures cover replay, expired submission/commit, changed candidate, Champion hash/generation, bundle, epoch, policy, and revoked device/session.
- [x] TEST: Hold/reject cannot be interpreted as approval. | evidence: Both decisions create terminal non-approval records and fail the commit recheck.
- [x] TEST: No real action possible using fixture enrollment/session. | evidence: Fixture approval passes evidence checks but returns `action_authorized = false` and no transition ticket.
