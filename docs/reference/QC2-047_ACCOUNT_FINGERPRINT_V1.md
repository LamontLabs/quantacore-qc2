# Working specification: QC2 Alpaca paper-account fingerprint v1

**Status:** Scoped, versioned identity contract for QC2-047. This does not
recover, redefine, or validate the historical fingerprint formula used by
QC2-010.

## Identity input and fingerprint

The scheme identifier and hash domain are
`qc2.alpaca-paper-account-fingerprint.v1`. The identity object contains exactly
these four fields:

```json
{"account_id":"<normalized-account-uuid>","broker":"alpaca","environment":"paper","origin":"https://paper-api.alpaca.markets"}
```

Encode the object as compact UTF-8 JSON with sorted keys using the shared QC2
canonical JSON serializer. The exact preimage is:

```text
UTF8("qc2.alpaca-paper-account-fingerprint.v1") || 0x00 || canonical_json_bytes(identity)
```

The fingerprint is the lowercase hexadecimal SHA-256 digest of that preimage.
This account fingerprint deliberately does **not** call
`domain_separated_sha256`: that general-purpose function adds the separate
`QC2-HASH-V1` prefix. The generic QC2 hash implementation remains unchanged.
The supplemental observation's `record_hash` is separate from the account
fingerprint and uses the QC2 generic domain-separated hash helper over its
canonical JSON payload, excluding `record_hash` itself. It is not a canonical
contract `content_hash`.

`account_id` must be a strict hyphenated UUID with hexadecimal digits. Uppercase
hexadecimal is accepted and normalized to lowercase. Whitespace, braces,
unhyphenated values, malformed IDs, and the nil UUID are rejected with a
sanitized error. No raw account ID is stored in the observation, logs, fixtures,
or report.

Golden vector:

- Input account ID: `01234567-89ab-4cde-8f01-23456789abcd`
- Preimage length: `177` bytes
- SHA-256: `ce862c5092d42d0ca7db43d55549f83bc1f66385680ec81d6e324cf76a7e24cf`

Credentials, balances, account status and flags, order data, timestamps, and
other mutable account fields are excluded from the identity object. Credential
rotation for the same account therefore leaves this fingerprint unchanged.

## Origin and observation boundary

The adapter and the probe use the same fingerprint implementation and require
the actual transport origin to be exactly
`https://paper-api.alpaca.markets` over HTTPS. They reject other origins and
redirect responses. Identity observation is limited to authenticated GET
requests; the QC2-047 transport rejects every non-GET method.

The scoped QC2-047 supplemental schema is
`qc2.identity_market.AlpacaPaperIdentityObservation.v1`. It records the
fingerprint scheme, broker, paper environment, exact origin, observation time,
tested source identity, endpoint statuses, non-financial account status flags,
evidence references, and the historical-continuity determination. It has no
account-ID or credential field. The schema is kept outside the canonical
Section 12 object list so the accepted master specification remains unchanged.

`execution_authorized` is fixed to `false`. This observation is not an
execution-account binding or authorization, does not alter any existing owner
approval, and does not bypass QC2-086. The historical QC2-010 manifest, receipt,
and fingerprint remain unchanged. The historical formula and continuity between
that fingerprint and this v1 fingerprint remain **unverified** unless separate
historical evidence establishes them.
