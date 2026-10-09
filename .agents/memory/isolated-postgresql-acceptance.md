---
name: Isolated PostgreSQL acceptance
description: Local database acceptance behavior in Replit's shell environment.
---

Run local PostgreSQL acceptance against a fresh UTF-8 cluster, applying migrations and running the acceptance SQL in the same shell invocation. The shell runtime may stop detached PostgreSQL processes when an invocation ends, and strict QC2 role bootstrap rejects reusing a cluster whose roles were already initialized by the migration. Initialize with `-U postgres`: `initdb` otherwise names the superuser after the current OS account, while QC2 acceptance fixtures expect a `postgres` role.

**Why:** Separate shell invocations did not preserve the local server; rerunning role-creating migrations against a reused cluster failed the migration's safety checks. A default-role cluster also failed fixtures that explicitly assign objects to `postgres`. This container also lacks PostgreSQL's default `/run/postgresql` socket directory, so `pg_ctl` otherwise fails before the test connects.

**How to apply:** Keep `initdb -U postgres`, `pg_ctl start`, database creation, migration application, acceptance execution, and `pg_ctl stop` in one shell command. Use a disposable `PGDATA` directory, create a temporary socket directory, and pass it to `pg_ctl` with `-k`.
