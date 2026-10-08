# QC2-018 — Historical Protocol Lineage Registry access blocker

- **Current status:** BLOCKED; no QC2-018 acceptance receipt.
- **Checked:** 2026-10-07.
- **Pinned Engine revision:** `Lamont-Labs/QuantraCore-Engine@67597a2a63fd3957e6ec50e270dba8e3df1d3757`.
- **Pinned Apex revision:** `Lamont-Labs/QuantraCore-Apex@d65ad25b813977b1087b94db5f88a32963426477`.

## Access finding

- The unauthenticated GitHub API lookup for the exact Engine commit returned HTTP 404. The prior QC2-001 source manifest identifies this repository as private.
- The configured GitHub reader exposed no usable connection in this context. A prior connector lookup returned no connection; no new connection or credentials were requested.
- The public Apex revision is readable. Direct raw-file SHA-256 checks for T24, T25, T34, and `LICENSE` match the values recorded in the QC2-001 source manifest.

## Verified partial findings

- Apex T24 source describes ATR breakout detection; T25 describes Keltner-channel position using an arithmetic mean named `ema20`; T34 describes rate-of-change momentum.
- Those source meanings conflict with the labels in Apex `docs/PROTOCOLS_TIER.md`. They remain source/documentation conflicts, not resolved historical semantics.
- Apex `LICENSE` is demo/evaluation-only and reserves production/live use absent written consent. No legacy source was imported or executed, and no live behavior was enabled.
- Additional public Apex protocol namespaces were inspected read-only, but no complete inventory artifact was produced or accepted.

## Stop condition

QC2-018 requires a complete source-backed inventory for the discovered references. The exact pinned Engine source cannot currently be read, so its file paths, hashes, and protocol meanings must remain unresolved. The earlier QC2-001 manifest is prior evidence, not a substitute for current access to the source bytes. Do not infer missing Engine semantics or mark the inventory complete from Apex alone.

QC2-019 and later tasks must not start until QC2-018 is unblocked and accepted. Resume this task only when the existing GitHub reader can retrieve the exact pinned Engine revision read-only.
