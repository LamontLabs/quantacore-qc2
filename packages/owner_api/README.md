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

## Owner read projections

The nine owner views are rebuildable projections. The projector and database
writer enforce the same per-view source-reference allowlists:

| View | Accepted canonical receipt schemas |
| --- | --- |
| Today | `PredictionSeal.v1`, `MarketSession.v1`, `ReadinessAssessment.v1` |
| Predictions | `Prediction.v1` |
| Validation | `QualificationReceipt.v1`, `ValidationReport.v1` |
| Models | `ModelManifest.v1`, `ChampionPointer.v1` |
| System | `ReadinessAssessment.v1` |
| Positions | `Position.v1` |
| Alerts | `Alert.v1`, `ReconciliationReport.v1` |
| Reports | `ValidationReport.v1`, `ReconciliationReport.v1` |
| Evidence | `EvidenceEvent.v1`, `Checkpoint.v1` |

The trusted source builder supplies receipts from the owning authorities and
the authoritative per-view event sequence/high-water; timestamps or generated
database IDs are not substitutes for those watermarks. This package exposes a
typed projector and constrained persistence functions, not arbitrary source
table queries. Owner read endpoints query the projection functions rather than
source tables; the migration grants no direct table access to its projection
tables and leaves pre-existing grants from other QC2 subsystems unchanged.
Source references in a page are limited to the distinct references used by
that page's items. Cursor pagination is bound to an immutable projection
sequence and does not grant access.
