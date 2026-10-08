# Temporal Firewall

This library provides cutoff-scoped query/export APIs for immutable artifact
snapshots. Every request requires explicit selectors, a cutoff, an operation,
artifact-kind permissions, and explicit permission for reconstructed evidence.
Exports include their resolved aliases, dependency closure, actual timestamps,
and historical assumptions.

`TemporalFirewall` is currently an in-memory authority. This workspace has no
verified QC2 persistence adapter or runtime database role, so this package does
not claim database-level `SELECT` denial or production storage enforcement.
Any future persisted adapter must enforce temporal filtering before data is
materialized and must prevent callers from bypassing the firewall with
unrestricted joins.

The package has no provider, database, execution, or credential dependencies.
