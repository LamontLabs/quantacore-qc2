---
name: PostgreSQL acceptance session state
description: Transaction-local settings can leak between sequential rollback-only PostgreSQL acceptance scripts.
---

When acceptance scripts run sequentially inside one `SERIALIZABLE` rollback
transaction, their `SET LOCAL` and transaction-local configuration changes
remain active across script boundaries. QC2-005's row-security assertion turns
`row_security` off; QC2-006 restores it before testing protected mutations.

**Why:** The suites share a connection and transaction, and changing the
previous task's hash-pinned test file would invalidate its recorded acceptance.

**How to apply:** Before relying on RLS or `SECURITY DEFINER` behavior in a
later script, explicitly restore test-only session settings at that script's
start. Keep the earlier accepted SQL artifact unchanged where possible.
