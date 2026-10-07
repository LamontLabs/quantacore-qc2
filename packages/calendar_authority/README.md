# QC2 market calendar authority

This package is the single in-process source for the declared New York exchange
session inventory, UTC open/close instants, operational phases, and deadline
checks. Inputs and outputs use the existing `CalendarManifest`,
`CalendarRevision`, `MarketSession`, and `ClockAssessment` contracts.

`AlpacaCalendarAdapter` only normalizes an explicitly supplied provider-shaped
payload. It performs no network access, provider selection, fallback, retry, or
live-capability claim. QC2-010 owns measurement of actual provider support and
response coverage. Pinned fixtures are synthetic and are not operating
calendars.

Calendar queries fail closed outside `valid_from` / `valid_through`; an omitted
date inside a declared complete inventory is closed, while an omitted
`MarketSession` for a date listed in the manifest makes the inventory
unavailable. Next-session queries walk the pinned session inventory rather
than adding a bar count or weekday.

Constructing `CalendarAuthority` validates the manifest hash and the complete
typed-reference closure. Callers must supply every referenced supporting object,
including the source `EvidenceEvent` and its own dependencies; dangling or
hash-mismatched references block calendar use.

Clock uncertainty is never assigned a production default. A trusted limit must
be supplied; otherwise the outcome is unavailable. A detected backward jump
is latched for the monitor lifetime. The monitor is process-local, so a
production caller must restore previous samples and latched faults from durable
authority before enabling deadline-sensitive actions. No F0 activation is
enabled by this package.
