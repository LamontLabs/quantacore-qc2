# QC2-017 — Reference intake

## Inspection basis

- Workspace revision at inspection: `b2455b29e911284d121b365e3436d7ec0dcc74a5`.
- Hashes below are SHA-256 of the exact files at that revision.
- QC2-017 implemented the local contract and specification boundary. No remote legacy source file was fetched or opened for this task; no legacy code was imported, copied, changed, or executed.
- The prior QC2-001 source manifest and decision were read as provenance records. Their descriptions of remote sources are attributed to that earlier read-only work and are not claimed as new QC2-017 source verification.

## Local sources consulted

| Revision | Path and SHA-256 | Source-supported meaning and relevant tests | Conflicts / license / disposition |
|---|---|---|---|
| `b2455b29e911284d121b365e3436d7ec0dcc74a5` | `docs/GEN2_MASTER_SPEC.md` — `4c88d457f10bae4f94efe9689aab9c45372ded10b43f88ad6d40e25584a12aab` | Section 15 separates Runner Protocols from safety, states PASS/BLOCK/OBSERVE/UNKNOWN/UNAVAILABLE meanings, forbids implicit numeric-zero or positivity defaults, requires immutable inputs, bounded isolation, and explicit reference intake. | Governing local specification; no third-party code or license issue. **ADAPT** as the runtime boundary. |
| Same | `packages/contracts/src/qc2_contracts/catalog.py` — `7613f74810f6bcc6d549b46589bb27b161bb5f2690687fc6785d54ec1de15c65` | Defines the persisted protocol definition, registry, result fields, and separate Runner/Safety state enums. Existing contract-package acceptance tests cover schema and reference validation; QC2-017 also validates generated records directly. | Definition/registry are content-addressed; result is not. **REUSE** unchanged v1 contracts. |
| Same | `packages/contracts/schemas/v1/RunnerProtocolDefinition.schema.json` — `ee5b6a19eb58b5a51b31fd2b711566bb0485817cb1d8ec8857244fc42c06a1d2` | Strict v1 definition schema: separate namespace, version, hypothesis, direction, feature/snapshot/bar input references, configuration references, implementation hash, and regime. | Input schema is narrower than result-input schema; runtime only accepts concrete feature snapshots and daily bars. **REUSE** unchanged. |
| Same | `packages/contracts/schemas/v1/RunnerProtocolRegistry.schema.json` — `6fa4b00e33a5b7840705d8c85d16020110d21aebbd0cbb9a43efb31e828b3436` | Strict v1 registry schema with definition references, active protocol IDs, and effective session. | Active IDs are strings, so QC2-017 stores namespace-qualified keys to avoid bare-ID collisions. **REUSE** unchanged. |
| Same | `packages/contracts/schemas/v1/RunnerProtocolResult.schema.json` — `2fe22d913b0c10da1f9dcb421e80759fde5889f3bc13dc0e98328f5c871f2c75` | Strict v1 result schema carries state, hypothesis, direction, evidence values, uncertainty, missingness, parameter/implementation hashes, cutoff, and input references. | It has no reason-code field and is not content-addressed. The runtime returns a separate diagnostic reason code; no unapproved field was added. **REUSE** unchanged. |
| Same | `packages/science/src/qc2_science/models.py` — `1bc1c07eb310198c90e38e21f1744d5c63f567f4f7e74d754e450da8948f7318` | Existing typed `ContractRef`, exact-decimal, date, and UTC validators informed immutable protocol bindings. | Gen2-local helpers only. **ADAPT** existing validators; no legacy dependency. |
| Same | `packages/science/src/qc2_science/registry.py` — `43939ce5a99090ab314c44a467a395e0d4e4e8f42f6d6fc5409ed268e918e284` | Existing feature registry materializes and verifies content-addressed v1 contracts. | Gen2-local implementation pattern. **ADAPT** hash/validation conventions, not feature authority behavior. |
| Same | `packages/science/src/qc2_science/__init__.py` — `12ef7769fe5cf3d831a01b79cb54e172831a7b9674520fd9ce5a1bb2756ce45b` | Existing package export surface. | Gen2-local API convention. **ADAPT** for the new public API. |
| Same | `tests/science/test_feature_authority.py` — `18ca1c435e05026c7c48fa2e9c680cf6fb031a1381bbaef5dd81757d59e20c0b` | Existing deterministic fixture, UUIDv7, and contract-validation test patterns. | Not a legacy test suite and does not establish Runner Protocol behavior. **TESTS_ONLY** as a local style reference. |
| Same | `docs/reference/QC2-001_SOURCE_MANIFEST.md` — `ed53904e10f5f8e49f864f9fd7fbb654dbd84452e92e7e3152a6c94339fc71b9` | Prior read-only manifest maps logical source roles to pinned repository snapshots and records namespaces, sampled hashes, tests, license limits, conflicts, and unresolved provenance. | Evidence is inherited from QC2-001, not refreshed here. **TESTS_ONLY** for provenance and boundaries; no protocol implementation reused. |
| Same | `docs/reference/QC2-001_DECISION.md` — `1417f75ed0e2782e594e3d79739d93be71ecdaa3596597297b3f2f99fe10e807` | Prior decision explicitly says later snapshots do not prove original/Gen1 origin, production deployment, or production authorization, and IDs are repository/path qualified. | No legacy source or license claims expanded. **TESTS_ONLY** for provenance constraints. |

## Screened context

| Revision | Path and SHA-256 | Result |
|---|---|---|
| `b2455b29e911284d121b365e3436d7ec0dcc74a5` | `attached_assets/QuantraCore_Apex_Gen2_SINGLE_FILE_REPLIT_HANDOFF_1791322523085.md` — `a9e294b7a336169a3d9669c7c90f7d387169e3c3049d976962415414092e093f` | Search-only check confirmed the handoff repeats the namespace, migration, and unverified-ID requirements; it contains no inspected legacy protocol implementation. Not used as protocol source. |
| Same | `docs/HARDENING_REVIEW.md` — `02a6491dd273decd471d46ef55e000a05f4deb71c7915568e7a649f3839f323f` | Search-only check found no Runner Protocol implementation or additional protocol rule. Not used in the implementation. |

## Authorized legacy references and disposition

The authorized “Original protocol framework” was not directly re-inspected for QC2-017. The prior QC2-001 manifest identifies:

- `Lamont-Labs/QuantraCore-Engine` at `67597a2a63fd3957e6ec50e270dba8e3df1d3757`, protocol paths under `src/quantracore/protocols/` (T01–T12). The manifest describes this as a foundation scaffold, reports no tests and no recognized license, and does not establish original historical origin.
- `Lamont-Labs/QuantraCore-Apex` at `d65ad25b813977b1087b94db5f88a32963426477`, tier paths under `src/quantracore_apex/protocols/tier/` (T01–T80). The manifest records version-label conflicts and a demo/evaluation-only license that reserves production/live use absent written consent. Its existing tier test does not verify the documented T24/T25/T34 source behaviors; those source-derived cases were not executed by QC2-001.
- The manifest records that Apex source behavior for T24/T25/T34 conflicts with the tier-document descriptions and that bare IDs collide across repositories and paths. QC2-017 does not identify, migrate, or activate any of those protocols.

**Disposition for QC2-017:** `IGNORE` the legacy implementations. The declarative evaluator is based on the local Gen2 contract and Section 15 boundary. No external license grant, production right, or historical-origin claim is inferred. No legacy tests were run.
