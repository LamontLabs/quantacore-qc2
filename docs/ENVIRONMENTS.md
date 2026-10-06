# Environment namespaces

`QC2_ENV` is the required namespace identifier for future runtime configuration.
Allowed values are `development`, `test`, `research`, and `production`. A missing
or unknown value must fail closed; no environment may silently fall back to
another namespace.

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

No production database or provider credential is configured by this bootstrap.
Environment-specific connection contracts are deferred to their owning tasks.
