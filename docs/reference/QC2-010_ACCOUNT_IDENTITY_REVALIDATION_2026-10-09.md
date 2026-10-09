# QC2-010 Account Identity Revalidation Addendum — 2026-10-09

This addendum records a new, forward-operational check. It does not modify or
replace `QC2-010_BLOCKED_REPORT.md`, any of the six original capability
manifests, `QC2-010_ACCEPTANCE_RECORD.json`, or `QC2-010_TASK_RECORD.json`.

## Current credential observation

At `2026-10-09T14:36:46.444364Z`, the current credentials completed these
authenticated GET requests against the exact Alpaca paper origin:

- `/v2/account` — HTTP 200; status `ACTIVE`; `trading_blocked=false`;
  `account_blocked=false`.
- `/v2/orders?status=all&limit=1` — HTTP 200; response contents were discarded.

The current identity was fingerprinted under
`qc2.alpaca-paper-account-fingerprint.v1` as
`5ad45910697fc1333985dc584b571d82bea0623abc2242874c3cbdd32d1575f6`.
The read-only observation is
`QC2-047_PAPER_ACCOUNT_IDENTITY_OBSERVATION_2026-10-09.json`; its
`record_hash` is
`84c3ee6145ae7d88d269ac3d58cdcee40a297dfd84f8003b777e8d7d64b5960d`.
The observation file's SHA-256 is
`3b6a83209a9b3d7b300183e7e33f8828e257f2b048aa3c8775c262636f61eb75`.
The tested source commit is `44cf6bab29819369e7188019561668f5b877d795`.

## Historical boundary and preservation check

QC2-010's original paper-account fingerprint remains
`4c426c01ca1732ea982aa644458b4577b88bec5c98800ade1920516b4134ec0c`. The
original report does not record its exact domain or payload encoding. The new
scheme is an independent current identity observation, not a reconstruction of
that formula. The two digests are not evidence of either a match or mismatch;
historical account continuity remains `UNVERIFIED`.

The current check revalidates authenticated account and order-list read access
and the current account status. It does not refresh the historical market-data,
calendar, classification, or corporate-action capabilities, and does not
extend the original manifests' 2026-10-08 expiry. Their original measurements
remain historical evidence.

The six manifest hashes and the original acceptance/task record hashes were
recomputed on 2026-10-09 and match the values in the accepted QC2-010 report.
No raw account ID, credentials, financial fields, or order contents were
recorded. No broker write was performed. This observation grants no execution
permission and does not change the QC2-086 write gate.

See `QC2-047_READ_ONLY_PROBE_REPORT.md` for the adapter acceptance result and
full safety boundary.
