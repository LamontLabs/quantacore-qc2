# QC2-013 — Temporal firewall package layout

## Decision

Keep the temporal firewall as a small standalone Python library under
`packages/temporal_firewall`. It is a reusable, side-effect-free query/export
boundary, not a runtime service or persistence owner. Its only public entry
points are the immutable artifact/query/permission types and
`TemporalFirewall.query()` / `TemporalFirewall.export()`.

The library does not import database clients, read environment credentials,
perform network I/O, or mutate domain state. A research adapter may construct
an immutable catalog snapshot and call this API; it must not expose unrestricted
outcome joins or silently substitute another provider.

## Evidence boundary

The workspace has no verified QC2 artifact-storage adapter to bind to this API.
A static review of the checked-in PostgreSQL migrations found schema `USAGE`
for the ApexLab runtime role on `qc2_outcomes_research`, but no `SELECT` grant
on that schema's tables; the second migration grants reads only on named
integrity-build evidence tables. The migrations do not create outcome/research
tables or a temporal SQL read function. Contract `reader_roles` metadata is not
itself a PostgreSQL grant.

The implementation and tests therefore establish the local in-memory
authorization and cutoff rules, while the current migration source does not
authorize direct outcome-table reads. No live QC2 database state was queried or
certified. A future persisted adapter must enforce the same temporal checks
before materializing data and prove its own role boundary before use by a
research runtime.

## Why this layout

The temporal firewall is a security boundary, not a scientific transform or
research dataset writer. Keeping its permission checks isolated makes callers
use the explicit capability object and makes the lack of persistence visible.
No new runtime service, storage system, or provider fallback is introduced.
