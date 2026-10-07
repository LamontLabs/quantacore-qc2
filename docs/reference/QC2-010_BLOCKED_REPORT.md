# QC2-010 — Real Account Capability Probe: initial blocker and authenticated recheck

> The initial blocker assessment and 21:17 reopen note below are historical. The authenticated measurements later in this report supersede their current-state conclusions. This report is not an acceptance receipt.

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
- The required secrets were submitted or confirmed through Replit's secure Secrets flow. Their values were passed only to authenticated request headers and were not displayed, logged, or persisted.
- QC2-010 has been reopened for a fresh authenticated capability probe against the updated secret pair. The prior HTTP 401 responses remain historical evidence; no capability is yet established by this update.

## Authenticated capability evidence — 2026-10-07

- **Probe window:** 2026-10-07T21:25:02Z–2026-10-07T21:32:11Z. The shell runtime reported `REPLIT_ENVIRONMENT=production`.
- **Fingerprinting:** Paper-account fingerprint `4c426c01ca1732ea982aa644458b4577b88bec5c98800ade1920516b4134ec0c`; deployment fingerprint `83f532be4b576a5958f4db8794ffa055d6d2d3179ed02db48c7e0fc2a7274216`. The account fingerprint is a domain-separated SHA-256 of the account ID; the account ID and financial fields were not recorded.
- **Safety:** 33 authenticated HTTP GET requests only. No 401 responses occurred after the secure secret update. Three SIP requests returned HTTP 403. Two exploratory malformed requests returned HTTP 400 and were excluded from capability conclusions; a valid, syntactically correct unknown symbol returned HTTP 200 with no bars. No retries, broker writes, order submissions, paid upgrades, or live brokerage-host requests occurred. Request bodies and secret values were not persisted.
- **Paper account:** `GET /v2/account` on the paper host returned HTTP 200; account status was `ACTIVE`, and the account/trading-block flags were false. `GET /v2/orders` with a read-only status/list query returned HTTP 200; order contents were not recorded. This establishes read access only, not order placement, amendment, cancellation, or fill support.
- **Asset classification:** `GET /v2/assets/SPY` returned HTTP 200 and classified the tested instrument as `us_equity`, exchange `ARCA`, status `active`. This is a one-instrument check, not a complete security-master coverage claim.
- **Calendar:** The paper calendar endpoint returned HTTP 200 and seven sessions for 2026-10-01 through 2026-10-09. For 2026-10-01 through 2026-10-07, the calendar and IEX daily bars matched on all five sessions with no missing SPY session and no next-page token.
- **IEX market data:** Recent daily bars returned HTTP 200 for SPY on all five tested sessions (2026-10-01, 10-02, 10-05, 10-06, 10-07). A 1-minute request returned 389 rows for the sampled 2026-10-07 interval; no broader intraday-coverage claim is made. An ascending history request from 1993 returned its first SPY IEX bar at 2018-11-01; a separate 1993 window returned no bars. This is the earliest row observed for SPY in this probe, not a guarantee for every symbol.
- **SIP market data:** Recent daily bars, an earliest-history query, and a latest-trade query each returned HTTP 403. A 1993 history-window request returned HTTP 200 with no bars. SIP access is therefore unavailable for this account under the tested requests; no subscription change was attempted.
- **Pagination and missingness:** A deliberately small two-symbol IEX request was paged through four one-row responses to a terminal response with no continuation token. The valid unknown symbol `QZXQV` returned HTTP 200 with no bars. A malformed long symbol and an initial bars request missing required query parameters returned HTTP 400; neither is counted as a feed entitlement failure.
- **Adjustments and symbol history:** AAPL daily queries around the August 2020 split returned three rows each for explicit `raw` and `split` adjustment modes, with different close values. An `FB` historical query with `asof=2021-06-30` returned three rows under the historical `FB` symbol. These checks do not establish adjustment or rename behavior for every instrument.
- **Corporate actions:** The AAPL split query for 2020-01-01 through 2025-01-01 returned HTTP 200 and one action. Action terms and raw response content were not recorded.
- **Rate limits and retry behavior:** Successful data and paper API responses exposed `x-ratelimit-limit=200`; remaining values observed for the data API ranged from 193 to 199. Calendar responses exposed limit 1000 and remaining 999. No 429 response or retry was observed. These are measured response headers, not a guaranteed quota.
- **Timing:** The completed 2026-10-07 SPY daily bar was successfully retrieved at 2026-10-07T21:25:02Z; the paper calendar reports that session closed at 16:00 ET (20:00Z). This proves the bar was available to this runtime by 5,102,000 ms after close, but does not identify when it first became available. Latest-trade timestamps were over 5.1 million ms old when queried after the session; that is post-market event age, not feed latency. Consequently, `effective_delay_ms` is `null` in the manifests rather than a guessed latency.
- **Manifest validity:** The six forward-operational manifests expire 24 hours after creation, at 2026-10-08T21:30:41Z. Revalidate after any credential or deployment change and before F0 activation. The expiration is a conservative evidence-freshness boundary, not an authorization to trade.
- **Manifest feed field:** The schema requires a feed value even for account, calendar, classification, and corporate-action records. Those records use `IEX` to identify the proposed diagnostic context; it does not claim those endpoints are sourced from IEX.
- **Feed proposal:** Propose IEX for an explicitly pinned, completed-daily diagnostic acquisition because the account returned complete SPY daily coverage for the five tested sessions and historical IEX data. Do not silently fall back to SIP or another provider. IEX is a single-exchange feed; its volume must not be described as consolidated market volume. SIP remains unavailable, broad-universe coverage and exact provider-side delay remain unresolved, and the proposal does not activate F0 or authorize a paper order.
- **Gate verdict:** PASS for the actual capability measurement and the limited IEX-only daily diagnostic proposal. The unresolved limitations above remain explicit; this is not an F0 activation or trading-authorization receipt. The acceptance record binds these manifest and report artifacts by hash; no independent digital signature is claimed.
