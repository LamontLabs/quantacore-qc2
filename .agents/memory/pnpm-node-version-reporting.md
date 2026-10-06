---
name: pnpm Node version reporting
description: A Replit workspace may report different Node patches through pnpm and the shell binary.
---

Use the package engine range for major compatibility and enforce the exact Node
patch through the version file, CI setup, and a smoke check.

**Why:** In this workspace, `node --version` and `pnpm exec node` reported
24.13.0, but pnpm installation reported its current engine as 24.12.0.

**How to apply:** If pnpm emits an engine warning that conflicts with the actual
shell runtime, verify both commands, keep the exact runtime pin explicit, and
avoid relying on pnpm's patch-level engine report as the only check.
