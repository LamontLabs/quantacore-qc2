---
name: Private GitHub source access
description: Verify current connector access before relying on pinned private legacy source revisions.
---

Treat a private GitHub source as readable only after a current connector call retrieves its exact pinned revision. An installed App label or a previous source manifest is not proof of present access. If the connector exposes no usable connection and the public GitHub endpoint returns 404, keep the source unresolved and stop rather than inferring semantics; do not request credentials.

**Why:** A prior source record in this workspace described a private repository as readable, but the current GitHub reader exposed no usable connection and public lookup could not retrieve the pinned commit.

**How to apply:** Before any source-backed task, verify read-only access to each exact private revision, cite only source bytes actually retrieved, and keep inaccessible meanings excluded.
