---
name: GitHub API vs Git authentication
description: Distinguishes GitHub REST connector access from Git remote authentication in Replit.
---

**Rule:** Treat GitHub REST integration access and Git remote authentication as separate capabilities. Verify remote access and a push explicitly before presenting a repository as populated or Actions-ready.

**Why:** Repository creation through the REST connector can succeed while workspace Git authentication remains unavailable or unbound.

**How to apply:** After creating a repository with the API, test the workspace Git connection before pushing. If Git authentication is unavailable, use Replit's Git pane connection flow; never ask the user to paste credentials into chat.
