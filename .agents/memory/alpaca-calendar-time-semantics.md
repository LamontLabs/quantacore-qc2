---
name: Alpaca calendar time semantics
description: Parse session-local Alpaca calendar hours before applying UTC finalization cutoffs.
---

Alpaca calendar `open` and `close` values may be wall-clock strings such as `16:00`, not full ISO timestamps. Bind time-only values to the returned session date in the exchange timezone; preserve explicit offsets on full timestamps and reject date mismatches.

**Why:** A real capture first failed because the calendar parser expected a full timestamp. Converting with the session date and New York timezone made the completed-session cutoff check accurate.

**How to apply:** When deriving daily-session completeness from Alpaca calendar responses, parse each row against its own date and `America/New_York`, then convert to UTC before comparing with receipt, finalization, or sealing times.
