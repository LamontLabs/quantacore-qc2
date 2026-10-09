---
name: PL/pgSQL name resolution
description: Prevent PL/pgSQL name ambiguity and SQL special-form qualification errors.
---

Use distinct prefixes for PL/pgSQL locals and qualify SQL columns with table aliases, including `ON CONFLICT` targets where a local has the same name as a column. Do not rely on block-label qualification when a row alias makes the SQL explicit.

**Why:** PL/pgSQL statements can defer name resolution until a branch executes, so an ambiguous identifier may survive migration creation and fail only in integration use.

**How to apply:** In new functions, prefer `v_`/`p_` local names and explicit row aliases; run each write path against PostgreSQL, not only migration parsing.

Do not schema-qualify SQL special forms such as `GREATEST` and `LEAST`; invoke them without a schema prefix.

**Why:** PostgreSQL does not expose these constructs as ordinary `pg_catalog` functions, so a qualified call can pass editing review but fail when the stored function executes.

**How to apply:** Schema-qualify ordinary function calls, but keep `GREATEST(...)` and `LEAST(...)` unqualified and verify the affected branch against PostgreSQL.
