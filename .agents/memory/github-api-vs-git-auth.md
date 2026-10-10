---
name: GitHub API vs Git authentication
description: Distinguishes GitHub REST connector access from Git remote authentication in Replit.
---

**Rule:** Treat GitHub REST integration access and Git remote authentication as separate capabilities. Verify remote access and a push explicitly before presenting a repository as populated or Actions-ready.

**Why:** Repository creation through the REST connector can succeed while workspace Git authentication remains unavailable or unbound. The special Git source-control connection may report active/healthy while `git ls-remote` still returns “Invalid username or token”; its OAuth reauthorization may also be rejected by the generic reconnect flow.

**How to apply:** After creating a repository with the API, test the workspace Git connection before pushing. An active status is not proof; verify a real remote read and push. If Replit's Git-provider OAuth keeps failing, a user-authorized `GH_TOKEN` in Replit Secrets can be used by GitHub CLI (`gh auth setup-git`) without embedding the token in the remote URL or printing it. Verify a real push. Force-push only with explicit informed consent.

**Why:** Replit's Git-provider credential was repeatedly rejected while a user-authorized PAT in `GH_TOKEN`, consumed through GitHub CLI's credential helper, successfully authenticated the push.
