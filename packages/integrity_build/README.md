# Integrity Build

`qc2_integrity_build` contains evidence verification and artifact-inventory
checks. Database mutation authority is implemented by reviewed PostgreSQL
functions and triggers in `migrations/`; this package does not write domain
tables or create evidence events.

The verifier consumes complete scan results from an evidence store, object
store, and (when configured) an independent anchor provider. Local hashes alone
are not proof against a privileged rewrite or coordinated database restore.
