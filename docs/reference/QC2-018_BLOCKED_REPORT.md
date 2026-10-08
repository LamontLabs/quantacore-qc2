# QC2-018 — Access blocker resolution

- **Previous state:** BLOCKED while an unauthenticated public GitHub lookup returned 404 and the earlier reader lookup appeared empty.
- **Resolution checked:** 2026-10-07.
- **Pinned Engine revision:** `Lamont-Labs/QuantraCore-Engine@67597a2a63fd3957e6ec50e270dba8e3df1d3757`.
- **Pinned Apex revision:** `Lamont-Labs/QuantraCore-Apex@d65ad25b813977b1087b94db5f88a32963426477`.

The 404 from the unauthenticated public endpoint did not establish that the pinned commit was absent. The existing GitHub App connection was confirmed as `added`; its documented connector slug was `github`. An authenticated read returned the exact requested Engine commit and a recursive tree with 41 entries and `truncated: false`. No new integration, credentials, or write operation was used.

The source-access blocker is cleared. QC2-018 is now IN_PROGRESS, not accepted. Its inventory, compatibility analysis, tests, and acceptance evidence still need to be completed before QC2-019 may start.
