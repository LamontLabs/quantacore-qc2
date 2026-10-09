# Owner API

Reserved for authenticated read projections and narrow owner commands. Do not
expose arbitrary SQL, code execution, direct broker calls, or direct state
mutation that bypasses the owning authority.

## Promotion approval boundary

`schemas/v1/PromotionApprovalChallenge.schema.json` and
`schemas/v1/OwnerDecisionEnvelope.schema.json` add the owner-API scope around
the already accepted `PromotionChallenge` and `PromotionDecision` contracts.
They bind domain, action, environment, request, current-state hashes, device,
session, key fingerprint, and nonce as distinct signed fields. The P-256
signature message is the versioned `QC2_OWNER_DECISION_ENVELOPE_V1` prefix
followed by QC2 canonical JSON for the envelope without its signature.

The authority depends on three ports: an identity provider that resolves the
server-side OwnerSession and performs a fresh commit-time revocation check, a
read-only promotion-state reader, and an approval ledger that atomically
records idempotency and nonce reservation. `InMemoryApprovalLedger` is only a
fixture adapter. An approval reserves its nonce; hold/reject consume theirs
without creating approval authority. QC2-043 must consume an approval ticket
through `PromotionTransitionTransaction.consume_owner_approval` in the same
database transaction as the Champion compare-and-swap.

Production approval is hard-disabled. This implementation accepts only
synthetic fixture identities in test/development environments, has no real
identity-provider or durable-ledger adapter, and cannot authorize a transition.
No challenge or decision here calls a broker or changes the Champion pointer.
The challenge lifetime cap is supplied by the authority constructor; fixture
test values do not establish a production lifetime policy.

Run the focused hostile-fixture suite with:

```sh
uv run python -m pytest -q tests/owner_api/test_promotion_approval.py
```
