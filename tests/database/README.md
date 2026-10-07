# PostgreSQL Acceptance

Run the QC2-005 and QC2-006 migrations and acceptance checks in an isolated,
rollback-only transaction with:

```sh
pnpm exec node lib/db/test/run-qc2-006-postgres-integration.mjs
```

Set `QC2_ENV=test`, `QC2_POSTGRES_TEST_URL`, and
`QC2_EXPECTED_DATABASE_TEST`. The runner accepts only a writable, isolated
`qc2_test_*` database that is not shared with a configured runtime identity.
It does not print connection strings and rolls back the transaction on both
success and failure.
