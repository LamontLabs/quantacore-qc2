# QC2-010 — Real Account Capability Probe: BLOCKED

> The initial blocker assessment below records the state before credentials were provisioned on 2026-10-07. The required secret names were later confirmed present using existence-only checks, and QC2-010 was reopened. The current authenticated recheck is recorded below; this report is not an acceptance receipt.

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

## Authenticated recheck after secrets were provisioned

- **Checked at:** 2026-10-07T19:38:00Z (UTC)
- **Current result:** BLOCKED. Both expected secret names were present in the runtime, but all authenticated API requests returned HTTP 401. Secret values were not printed, logged, or persisted.
- **Environment:** The runtime reported `REPLIT_ENVIRONMENT=production`. The only brokerage host contacted was Alpaca's paper host; no live brokerage host was contacted.
- **Paper-account requests:** `GET https://paper-api.alpaca.markets/v2/account`, `/v2/assets/SPY`, and `/v2/calendar` for 2026-10-01 through 2026-10-09 each returned HTTP 401. The sanitized response-body SHA-256 was `9007f14739da08d0908ba9251c065befbf6b561f92f1cc2c69347f0e6ec7fc03`.
- **Market-data requests:** Ten authenticated GET requests to `https://data.alpaca.markets` returned HTTP 401 with sanitized response-body SHA-256 `9371176869a945e2958e43b349397210a1b72b83f11c67e02e0be1f950254ef2`. They covered recent daily bars and current one-minute bars for each explicit feed (`iex`, `sip`), a 1993 SPY history window for each feed, an IEX pagination first page, AAPL split corporate actions, an intentionally unknown symbol, and an FB historical/as-of symbol-mapping query.
- **Pagination and rate limits:** The pagination request failed before returning a page token, so no second-page request was made. No rate-limit headers were present in the observed error responses. No retries were issued.
- **Capability conclusion:** No account identity or account fingerprint was returned. Feed entitlement, effective delay, supported history, coverage, pagination behavior, rate limits, action/classification/calendar availability, and paper-account operations remain unknown. No DataCapabilityManifest or feed-selection proposal is issued from these errors.
- **Safety:** Every probe used authenticated GET requests only. No anonymous probe, broker write, order, paid upgrade, or live-brokerage request occurred. Error bodies were not stored or printed; only status codes and response hashes were recorded.
- **Unblock condition:** Verify that the two Replit Secrets contain a matching Alpaca paper-trading API key pair with account access, update them through Replit Secrets if needed, then rerun QC2-010. Do not send credential values in chat. Until successful authenticated responses are measured, QC2-010 remains BLOCKED and F0 must not be activated.

## Reopened after secure credential update

- **Checked at:** 2026-10-07T21:17:00Z (UTC)
- The required secret names were submitted or confirmed through Replit's secure Secrets flow. Secret values were not accessed, printed, or recorded.
- QC2-010 has been reopened for a fresh authenticated capability probe against the updated secret pair. The prior HTTP 401 responses remain historical evidence; no capability is yet established by this update.
