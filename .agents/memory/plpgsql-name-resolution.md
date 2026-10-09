---
name: PL/pgSQL name resolution
description: Prevent local-variable and column-name ambiguity in stored procedures.
---

Use distinct prefixes for PL/pgSQL locals and qualify SQL columns with table aliases, including `ON CONFLICT` targets where a local has the same name as a column. Do not rely on block-label qualification when a row alias makes the SQL explicit.

**Why:** PL/pgSQL statements can defer name resolution until a branch executes, so an ambiguous identifier may survive migration creation and fail only in integration use.

**How to apply:** In new functions, prefer `v_`/`p_` local names and explicit row aliases; run each write path against PostgreSQL, not only migration parsing.
