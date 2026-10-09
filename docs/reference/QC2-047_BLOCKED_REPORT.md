# QC2-047 Blocked Report

## Status

**BLOCKED — do not record QC2-047 as PASS or activate broker writes.**

The adapter, synthetic API fixtures, and tests are implemented. Final account binding cannot be accepted because the exact fingerprint derivation pinned by QC2-010 is not recorded in its report or manifest, and the current proposed derivation does not match that pinned digest.

## Completed and checked

- Fixed paper API host and HTTPS transport; redirects to other hosts are rejected.
- Default transport allows GET only. POST, PATCH, and DELETE remain closed until QC2-086.
- Submit, client-order lookup, cancel, replace, order listing, and fill-activity read interfaces are implemented.
- The adapter consumes QC2's normalized mutation-request shape for submit and cancel.
- API normalization and synthetic fixtures cover partial fill, delayed visibility, duplicate keys, nonterminal cancellation, and malformed provider data.
- Current official Alpaca API documentation was reviewed and recorded in `QC2-047_REFERENCE_INTAKE.md`.
- `uv run --no-sync pytest -q tests/alpaca_paper_adapter`: 29 passed.
- `uv run --no-sync ruff check packages/execution/src/qc2_alpaca_paper tests/alpaca_paper_adapter`: passed.

## Unresolved acceptance condition

QC2-010 pins account fingerprint `4c426c01ca1732ea982aa644458b4577b88bec5c98800ade1920516b4134ec0c` and describes it only as a domain-separated SHA-256 of the account ID. The exact domain and payload encoding are absent from the report and manifest. The current adapter constant is explicitly unverified. A read-only probe returned HTTP 200, but the derived digest did not match the pinned digest. A bounded local check of 650 candidate domain labels across five plausible payload encodings also found no match; this search is not a substitute for source provenance.

The account ID and financial fields were not emitted or persisted. The probe performed no broker mutation requests. Connectivity is confirmed; the expected account identity is not.

**Needed to unblock:** provide the original QC2-010 probe/source revision or the exact fingerprint domain and payload canonicalization, and confirm that the currently configured paper credentials are intended to identify the same account. Do not provide credentials or the raw account ID. Do not change the pinned QC2-010 digest or assume a match without explicit authorization.

## Acceptance record

No QC2-047 acceptance receipt or task record was created. The task remains `IN_PROGRESS` with this blocker. QC2-048 remains downstream and must not start until QC2-047 is accepted.
