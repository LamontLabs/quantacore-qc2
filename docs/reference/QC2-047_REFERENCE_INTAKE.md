# QC2-047 Reference Intake

**Reviewed:** 2026-10-08  
**Result:** Partial. The inspected Alpaca code is a candidate legacy source, but its files do not establish that it is the task's Gen 1 authority. The pinned account-fingerprint derivation is also absent from the inspected materials.

## Legacy-source candidates

The task authorizes the Gen 1 Alpaca adapter and its tests. The accessible public repository is `Lamont-Labs/QuantraCore-Apex`. Neither inspected source revision labels itself Gen 1, so these are recorded as candidates, not accepted as authoritative Gen 1 source.

| Revision | Path and SHA-256 | Source-supported meaning and tests | Conflict, license, access limit, and disposition |
|---|---|---|---|
| `79a62d333fa9121b2572bf2fe3111a0449b67f4d` | `src/quantracore_apex/broker/adapters/alpaca_adapter.py` — `d0d59bbb84f13b8e38052ef8b60cd3c73aa37b435ab5e162ce1ebe1b2887bf5a` | Earliest Alpaca adapter file revision found in the inspected path history (2025-11-29). It identifies itself as paper-only and defaults to Alpaca's paper URL. | The host is configurable through `base_url`; raw request/response data and provider error details are logged. These conflict with QC2's fixed-host and redaction requirements. The candidate is not copied or used as the implementation contract. |
| `79a62d333fa9121b2572bf2fe3111a0449b67f4d` | `tests/broker/test_broker_layer.py` — `3e1c60a45c8ae066250ad8f9eb25f8ff1543c09711bd38500be8df88ba0df7be` | The inspected tests cover the in-memory `PaperSimAdapter` and generic broker objects. They do not provide Alpaca adapter contract or transport tests. | No source-specific Alpaca test coverage was found in the listed `tests/broker` directory. Not used as evidence that the Alpaca adapter is tested. |
| `d65ad25b813977b1087b94db5f88a32963426477` | `src/quantracore_apex/broker/adapters/alpaca_adapter.py` — `29ef3aea806a4f35faf4b2cd3bfdf335eabc8fade86848d036502735530cd5be` | Later public snapshot of the same adapter path. It continues to identify as paper-only and defaults to the paper URL. | The host remains configurable; raw request/response payloads and provider response bodies are logged and may appear in exceptions. This is a later snapshot, not proof of Gen 1 authority. No code was copied. |
| `d65ad25b813977b1087b94db5f88a32963426477` | `tests/broker/test_broker_layer.py` — `0345eaafe9fbbef207e2261e2ee98507447ed833fbaf8c2711ca7f60bf9be4d2` | The test file contains `PaperSimAdapter` tests; it has no `AlpacaPaperAdapter` test references. | Does not satisfy QC2-047's Alpaca contract, hostile transport, or account-binding test requirements. Not used as acceptance evidence. |
| `d65ad25b813977b1087b94db5f88a32963426477` | `docs/BROKER_ADAPTERS.md` — `fda72203a9ef549f30a6efe08a17c65b4d6efe8df7b42c89f63bef4fa9cb1754` | Describes Alpaca paper trading as an available adapter and live trading as disabled. | The documentation's “Production” label does not override this task's no-write gate or the repository license. It is informational only, not the pinned QC2 interface. |
| Both inspected revisions | `LICENSE` — `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9` | States: “Demo-only/Evaluation license. No production or live trading without written consent.” | No legacy implementation or test code was copied. The adapter here was built against current API documentation and the QC2 interface. |

### Discovery-only repository check

`Lamont-Labs/QuantraCore-Engine` was checked only through GitHub repository metadata and directory listings on its `main` branch. The root and `src/quantracore` listings were viewed; no source-file bodies or pinned commit SHA were retrieved. The listing did not identify an Alpaca adapter at that directory level. This repository is not relied on as a reference, and no license or source claim is made for it.

## Current official Alpaca API sources

These documentation pages were fetched on 2026-10-08 and used to define synthetic response fixtures and the narrow supported surface:

- [Create an Order](https://docs.alpaca.markets/reference/postorder) — paper-host order request fields and response schema.
- [Get Order by Client Order ID](https://docs.alpaca.markets/reference/getorderbyclientorderid) — client-order lookup route.
- [Get All Orders](https://docs.alpaca.markets/us/reference/getallorders-1) — order listing and query semantics.
- [Replace Order by ID](https://docs.alpaca.markets/us/reference/patchorderbyorderid-1) — replacement route and nonreplaceable states, including `accepted`, `pending_new`, `pending_cancel`, and `pending_replace`.
- [Delete Order by ID](https://docs.alpaca.markets/us/reference/deleteorderbyorderid-1) — a successful cancellation request returns 204; this does not establish that the order is terminally canceled.
- [Get Account](https://docs.alpaca.markets/us/reference/getaccount-1) — read-only account endpoint.
- [Retrieve Account Activities](https://docs.alpaca.markets/us/reference/getaccountactivities-2) — paper-host `/v2/account/activities`, comma-separated `activity_types`, and `page_size`, `direction`, and `page_token` parameters.
- [Account Activities guide](https://docs.alpaca.markets/us/docs/account-activities.md) — fill activity fields and pagination behavior.
- [Working with Orders](https://docs.alpaca.markets/us/docs/working-with-orders.md) — order lifecycle and client-order-ID guidance.

The adapter fixes the only permitted host to `paper-api.alpaca.markets`, does not follow redirects, and uses a default transport that blocks every non-GET request until QC2-086. The synthetic order fixtures cover provider states and simple-order responses; the simple class fixture uses the documented empty-string representation. No live endpoint, runtime feed fallback, or broker write was used.

## QC2 execution-interface source

The local `qc2_execution.authority` builds `qc2.execution.normalized_mutation_request.v1` mappings and passes those mappings to `submit_order` and `cancel_order`. The adapter now consumes that exact normalized request shape. Tests use the authority's `build_normalized_request` function for submit and cancel cases; this resolves the former mismatch with raw `PaperOrderIntent` field names without editing the execution authority.

## Account fingerprint provenance gap

`docs/reference/QC2-010_BLOCKED_REPORT.md` and `docs/reference/QC2-010_CAPABILITY_MANIFESTS/paper_trading.json` record the pinned digest but not its domain string or payload canonicalization. Neither inspected candidate adapter/test nor the inspected later adapter documentation supplies that missing derivation. The candidate constant `qc2.identity_market.paper-account-fingerprint.v1` is unverified and synthetic tests using it prove only internal consistency.

QC2-047 uses the separately authorized, versioned scheme in
`QC2-047_ACCOUNT_FINGERPRINT_V1.md`; it is not presented as a recovery of the
QC2-010 formula. The fresh observation will record current identity and
read-only account/order-list results under that scheme, with continuity to the
historical QC2-010 fingerprint explicitly `UNVERIFIED`. The original QC2-010
manifest, acceptance receipt, and hashes remain unchanged. See the separate
`QC2-010_ACCOUNT_IDENTITY_REVALIDATION_2026-10-09.md` addendum and
`QC2-047_READ_ONLY_PROBE_REPORT.md` for the fresh evidence.
