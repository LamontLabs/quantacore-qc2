# Threat Model

## Project Overview

QuantraCore Apex Gen 2 is a private, single-owner runner-intelligence and
paper-trading system. The repository currently establishes its authority,
contract, database, and verification foundations; the inherited API artifact
exposes only a health check and is not a product authority. The stack uses
TypeScript/Node.js, Python, generated QC2 contracts, and PostgreSQL. QC2-006
adds append-only evidence streams, database mutation capture, checkpoints, and
local verification.

No live trading or independent anchor provider is enabled by this task.
`FORWARD_SEALED` stream creation and writes fail closed until an approved,
independently operated anchor is integrated and verified.

## Assets

- **Authoritative database state** — job definitions and leases, outbox
  operations, resource reservations, stream heads, evidence events, and
  checkpoints. Corruption can cause invalid work, duplicate effects, or false
  claims about what happened.
- **Evidence and artifact integrity** — canonical payloads, chain heads,
  checkpoint roots, and artifact manifests. These support audit and scientific
  provenance, but a local hash chain is not proof against a privileged rewrite.
- **Runtime and migration identities** — PostgreSQL role boundaries, migration
  credentials, session context, and application secrets. Compromise can permit
  unauthorized mutations or broad database access.
- **Operational metadata** — actor identities, job keys, lease owners,
  reservation states, and hashed resource identifiers. These can reveal
  internal behavior even when raw resource keys are omitted.
- **Independent checkpoint receipts** — not yet backed by a production
  provider. If later integrated, their signing keys, accepted times, retention,
  and recovery path become high-value assets.

## Trust Boundaries

- **Runtime service to PostgreSQL** — runtime roles may call only their
  authority-specific functions. Row-level security, role checks, transactional
  triggers, and least-privilege grants enforce the boundary.
- **Migration operator to PostgreSQL** — the offline migration identity owns
  schema changes and is separate from service credentials. Database
  superusers and infrastructure administrators remain outside the protection
  offered by application-level triggers.
- **Domain mutation to evidence/outbox** — protected database writes append
  evidence in the same transaction. A failed append aborts the domain mutation;
  external delivery happens after commit through the outbox.
- **Local database to independent anchor** — the Python anchor protocol is an
  integration seam only. No receipt provider or independent retention system
  is configured, so current evidence is local proof only.
- **Manifest to artifact storage** — the verifier compares manifests with
  caller-supplied object listings and bytes. No production object-store adapter
  is wired by QC2-006.
- **Development/test to production** — stream environment and evidence class
  are recorded separately. Test fixtures are not production evidence, and
  production qualification must not infer proof from test or local state.
- **Public API surface** — the inherited API currently exposes `/healthz`
  only. It does not provide evidence mutation or verification endpoints.

## Scan Anchors

- `migrations/0001_postgresql_authority_foundation.sql` — runtime roles,
  database authorities, and row policies.
- `migrations/0002_evidence_authority.sql` — stream, append, checkpoint,
  trigger, rotation, and atomic job/outbox boundaries.
- `lib/db/run-migrations.mjs` — explicit migration operation and environment
  guards.
- `packages/integrity_build/src/qc2_integrity_build/verification.py` — local
  event, checkpoint, artifact, and external-receipt verification.
- `tests/database/` and `tests/integrity_build/` — rollback-only PostgreSQL
  acceptance and verifier fault fixtures.
- `artifacts/api-server/src/routes/` — inherited health-only API surface;
  audit again before adding authenticated product routes.

## Threat Categories

### Spoofing

A compromised or misconfigured service could try to claim another authority.
Event actor identity is derived from the database runtime context rather than
accepted as a caller-supplied role. Runtime roles must remain non-superuser,
non-owner, and unable to assume another authority; migration and runtime
credentials must not be shared.

### Tampering

Buggy or compromised runtime code could alter protected rows, reorder events,
truncate a scan, or supply inconsistent artifact bytes. Restricted mutation
functions, row-locked stream heads, unique sequence constraints, append-only
triggers, canonical hashes, complete-scan checks, and artifact inventory
verification address these cases. The verifier must return partial or failed
when the scan or referenced-object inventory is incomplete.

A database administrator, superuser, or coordinated backup restore can rewrite
both the event chain and its expected head. Local hashing cannot detect that
case. Stronger claims require independently retained checkpoints and verified
receipts outside the backend's write and backup authority.

### Repudiation

An actor could deny a protected database operation if its event were missing or
ambiguous. Mutation triggers append actor, event type, time, and generation
details in the same transaction as the domain write. These records improve
local auditability but do not provide non-repudiation against an administrator
who controls the database and local backups. Do not label local-only results as
independently anchored proof.

### Information Disclosure

Evidence payloads must not contain secrets or personal data. Event rows still
contain operational identifiers and states; access must remain limited to
approved runtime authorities. Domain-separated hashes of resource identifiers
are integrity references, not anonymization: low-entropy keys may be guessed.
Logs and verification errors must not expose connection strings, credentials,
or full sensitive payloads.

### Denial of Service

Evidence append failure deliberately blocks the associated authoritative
mutation. This preserves atomicity but makes missing streams, database
unavailability, lock contention, and oversized event/ref inputs availability
risks. Preserve clear health/failure reporting, bound inputs, and monitor
evidence backlog before enabling higher-volume workloads. Never silently skip
evidence or fall back to a provider or feed.

### Elevation of Privilege

An attacker with a runtime credential could attempt cross-authority calls,
disable row security, or exploit a `SECURITY DEFINER` function. Keep runtime
roles least-privileged, derive authority from authenticated PostgreSQL context,
pin function search paths, review grants and row-level policies, and test
cross-role calls. Migration credentials must remain unavailable to runtime
processes. A database superuser remains an explicit trust-root compromise.
