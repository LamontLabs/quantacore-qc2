# QC2-010 — Real Account Capability Probe: BLOCKED

## Blocker assessment

- **Result:** BLOCKED
- **Checked on:** 2026-10-07
- **Canonical status:** BLOCKED; this is not a PASS and does not establish Alpaca entitlement.
- **Blocker:** No Alpaca integration or Alpaca API credentials are available in this Replit environment.

## Evidence collected

- The complete Replit integration listing contained no Alpaca connection or connector.
- A secret-existence-only check returned `false` for each of `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `APCA_API_KEY_ID`, and `APCA_API_SECRET_KEY`. Secret values were not read or exposed.
- QC2-009 is canonically PASS and integrated. `python3 tools/task_workflow.py preflight QC2-010` passed before this blocker was recorded.
- No request was sent to an Alpaca account, trading, or market-data endpoint. No credentials, account identity, or authenticated response were available.

## Capability evidence not available

Because authenticated access is absent, this report cannot establish:

- SIP or IEX entitlement, feed delay, supported history, coverage, pagination, timing, or rate-limit behavior.
- Asset classification, corporate-action, calendar, or paper-account identity capabilities.
- A feed selection suitable for the pre-activation F0 regime.

These facts remain unknown, not failed and not inferred from documentation or fixtures. No `DataCapabilityManifest` claiming measured account capabilities is issued.

## Safety and unblock conditions

- No broker write, live-endpoint probe, paid upgrade, order submission, or runtime feed fallback was performed.
- QC2-010 remains BLOCKED until the intended paper account's Alpaca credentials are made available through Replit Secrets. Do not send credentials in chat.
- After credentials are provisioned, resume with authenticated read-only requests only, record the observed responses and limitations, and repeat the task preflight. Do not select a feed or activate F0 from this report.
- F0 activation remains subject to exact owner authorization for the specified epoch, manifest, and prospective start session.
