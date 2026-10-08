---
name: Python worker package isolation
description: Preserve Replit-managed Python packages in credential-free subprocesses without forwarding ambient environment.
---

In Replit's managed Python setup, `pytest` may expose `.pythonlibs/.../site-packages` on `sys.path` even when `sys.prefix` identifies the Nix base interpreter. Building a worker's `PYTHONPATH` only from directories under `sys.prefix` can therefore omit installed dependencies.

**Why:** The isolated model worker could not import NumPy until its package roots were resolved from the actual pinned modules rather than the interpreter prefix.

**How to apply:** For sanitized Python subprocesses, derive allowed `site-packages` roots from the installed origins of the specific required libraries. Pass those roots explicitly, keep user-site imports disabled, and do not forward the parent's ambient `PYTHONPATH`.
