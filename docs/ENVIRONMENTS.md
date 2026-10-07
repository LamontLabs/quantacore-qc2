# Environment namespaces

`QC2_ENV` is the required namespace identifier for runtime database configuration.
Allowed values are `development`, `test`, `research`, and `production`. A missing
or unknown value must fail closed; no environment may silently fall back to
another namespace.

Each database process must also set one registered `QC2_AUTHORITY`. It connects
only with `QC2_DATABASE_URL_<ENV>_<AUTHORITY>` and must set
`QC2_EXPECTED_DATABASE_<ENV>` to the expected PostgreSQL database name. The
runtime verifies `current_database()`, the authenticated role
`qc2_runtime_<AUTHORITY>`, login status, non-privileged role attributes, and
absence of PostgreSQL role memberships before exporting the connection pool.
Generic `DATABASE_URL` is never a fallback. Configured environment URLs and
expected database names must not be reused across environments.

Each environment must use separate database identities, storage locations, and
credentials. Development and test must not read production data or credentials.
Research receives only explicitly approved, cutoff-filtered inputs and its own
write area; it must not receive production mutation or execution credentials.
Production secrets must not be copied into local files, CI variables, fixtures,
logs, or evidence payloads.

The tracked `.env.example` contains only the safe local selector
`QC2_ENV=development`. It deliberately supplies no database URL, provider
credential, signing key, or session secret. Real secrets belong in the workspace
secret manager or a separately approved production secret store.

No runtime database URL or production database/provider credential is configured
by this bootstrap. The explicit `QC2_MIGRATION_DATABASE_URL` is accepted only by
the manual migration tools, while one-time bootstrap uses a separate
`QC2_BOOTSTRAP_DATABASE_URL`. Migration tools require a matching
`QC2_MIGRATION_ENV` and `QC2_EXPECTED_DATABASE_<ENV>`, reject production, and
never run at application startup or post-merge. Production migration remains
outside this task and requires its own approved platform-compatible procedure.
The SQL creates login-capable role names without assigning passwords; credentials
must be provisioned separately for the exact environment and authority. No such
runtime or migration credentials are configured here.
