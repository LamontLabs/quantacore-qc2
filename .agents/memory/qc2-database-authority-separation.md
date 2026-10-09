---
name: QC2 database authority separation
description: Preserve the authenticated runtime-role boundary when owner API routes span identity and owner data.
---

Keep identity operations and owner-projection operations on separate least-privilege database connections. An executable security-definer routine does not change the authenticated authority of its caller; grants cannot substitute for the runtime role required by an identity mutation. Do not bridge authorities by making runtime roles members of each other or by widening generic mutation grants.

**Why:** the authenticated PostgreSQL session role remains the basis for authority checks inside protected routines, so a cross-authority call can fail at commit time even after function execution is granted.

**How to apply:** split query ports by authority in routes that span identity and owner data, and verify each connection's expected database and runtime role.
