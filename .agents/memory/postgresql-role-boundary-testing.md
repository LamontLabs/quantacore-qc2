---
name: PostgreSQL role-boundary testing
description: Tests real runtime identities and avoids implicit role memberships when bootstrapping least-privilege PostgreSQL roles.
---

## Rule

Use `SET LOCAL SESSION AUTHORIZATION` to test PostgreSQL permissions as an actual runtime principal. A superuser-backed `SET ROLE` does not accurately test privilege escalation. On PostgreSQL 16, a non-superuser `CREATEROLE` principal that creates a role receives an administrative membership in that role; create runtime roles with the separately approved bootstrap owner, then remove `CREATEROLE` from the offline migration role when ongoing role creation is not required. Verify membership behavior on the target PostgreSQL version.

**Why:** A rollback-only authority-foundation test exposed the creator's implicit administrative membership, which a role-membership guard correctly rejected.

**How to apply:** Use these checks when designing database bootstrap, least-privilege role policies, and PostgreSQL authorization integration tests.
