# QC2-047 Historical Blocker Record

This file preserves the earlier QC2-047 blocker assessment. It is superseded as
the current task report by `QC2-047_READ_ONLY_PROBE_REPORT.md`.

## Historical blocker

The earlier assessment correctly found that QC2-010 records account fingerprint
`4c426c01ca1732ea982aa644458b4577b88bec5c98800ade1920516b4134ec0c` without its
exact domain and payload encoding. Its candidate fingerprint did not match that
digest, and a bounded search of candidate formulas was not source provenance.

## Current boundary

QC2-047 now uses the separately authorized
`qc2.alpaca-paper-account-fingerprint.v1` scheme for a fresh identity
observation. This does not recover or validate QC2-010's historical formula and
does not establish continuity with the account identity behind the older
fingerprint. Historical continuity remains `UNVERIFIED`; the original QC2-010
manifest, receipt, and hashes remain unchanged.

The current GET-only evidence and QC2-047 acceptance result are recorded in
`QC2-047_READ_ONLY_PROBE_REPORT.md`. Broker writes remain gated by QC2-086.
