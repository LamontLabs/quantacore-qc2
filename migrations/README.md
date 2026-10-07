# Migrations

Store schema changes here as ordered, immutable, forward-only migrations. Each
migration must state its purpose and compatibility expectations and receive
review before application. Do not edit an applied migration to repair history;
add a new corrective migration instead. Application startup must not apply
migrations automatically. Migration credentials remain offline from runtime
services, and destructive changes require a verified backup and explicit
approval.

`@workspace/db` has no push, force-push, startup, or post-merge schema-sync
command. `drizzle-kit` database mutation commands are disabled by the checked-in
configuration. Review each numbered SQL file before explicitly applying it with
the manual runner.

For a first development/test bootstrap, use the separate
`QC2_BOOTSTRAP_DATABASE_URL` with the isolated database-owner identity and the
runner's `--bootstrap --apply` flags. The bootstrap identity creates the
runtime roles, then the migration role is reduced to schema-owner privileges
without `CREATEROLE` or role memberships. For later development/test migrations,
use `QC2_MIGRATION_DATABASE_URL` authenticated as `qc2_migrator` and `--apply`.
Both paths require `QC2_MIGRATION_ENV` to match `QC2_ENV`, an exact
`QC2_EXPECTED_DATABASE_<ENV>`, and a writable non-replica target. The runner
refuses production and compares migration credentials against configured
runtime URLs without logging any URL. Bootstrap and migration credentials must
not be available to runtime services. The SQL creates login-capable role names
but deliberately assigns no passwords; credential provisioning is an explicit,
separate operation.

`pnpm test:postgres` runs the PostgreSQL acceptance script against a dedicated
`qc2_test_*` database inside one `SERIALIZABLE` transaction and rolls back the
migration and all fixtures. It requires `QC2_ENV=test`,
`QC2_EXPECTED_DATABASE_TEST`, and `QC2_POSTGRES_TEST_URL`; the test URL must use
an isolated superuser because it creates real roles before switching session
authorization to each runtime role. Never point it at development or production.
