# QC2-001 — Legacy source identity blocker

**Status:** BLOCKED — do not accept or mark complete  
**Checked:** 2026-10-06  
**Authorized references:** QuantraCore Gen 1; ApexLab Gen 1; Original QuantraCore Protocol project

## Finding

The GitHub connection is usable for read-only repository discovery, but the accessible repositories do not establish exact identities for all three authorized references. In particular, no confirmed ApexLab Gen 1 or Original QuantraCore Protocol repository was identified. Two QuantraCore-named repositories are plausible candidates but do not prove which historical sources the task authorizes.

No protocol meanings, T24/T25/T34 verification cases, or cross-project duplicate-ID conclusions are asserted here. Current/v9-era material and protocol numbers are not substitutes for identified historical sources.

## Discovery and handling

- Queried the connected GitHub API using GET requests only. No GitHub writes, clones, checkouts, or legacy-source edits were performed.
- The accessible repository listings included 14 repositories in `Lamont-Labs` and 11 under `LamontLabs`. No exact repository identity for the three authorized labels was established.
- The workspace had no local legacy source trees. Its `git status --short` was clean before this blocker note was added.
- No legacy tests were run. Running tests or importing code from an unconfirmed/current candidate would not verify the authorized historical references.

## Candidate repositories examined

These are discovery candidates, **not accepted legacy references**.

| Candidate | Exact repository revision | Observed evidence | Disposition |
|---|---|---|---|
| [Lamont-Labs/QuantraCore-Engine](https://github.com/Lamont-Labs/QuantraCore-Engine) (private) | `main` at `67597a2a63fd3957e6ec50e270dba8e3df1d3757` (2025-11-03) | Its README says “foundation scaffold”; the complete tree lists protocol files T01–T12, but does not identify the repository as Gen 1 or contain T24/T25/T34 paths. GitHub reports no recognized license, and the tree showed no root license file. | Candidate only. Neither the repository identity nor license establishes it as the authorized Gen 1 source. |
| [Lamont-Labs/QuantraCore-Apex](https://github.com/Lamont-Labs/QuantraCore-Apex) (public) | `main` at `d65ad25b813977b1087b94db5f88a32963426477` (2026-02-06) | README identifies v9.1. The ApexLab overview identifies version 9.0-A and “V1 + V2”; the protocol manifest identifies version 9.0-A and 115 protocols. Its README and files are current/v9-era material, not proof of a Gen 1 or original-protocol identity. The LICENSE is demo-only/evaluation and reserves production/live use absent written consent. | Not accepted as an authorized historical source. No code was reused. |
| [LamontLabs/QuantraCore_production](https://github.com/LamontLabs/QuantraCore_production) (public) | Default branch `main`; no resolvable commit | Repository metadata reports size 0; root contents returned HTTP 404 and commit lookup returned HTTP 409. No license was identified. | Unusable as a source at the time checked; identity remains unconfirmed. |

### Hash checks for files read during discovery

For each row below, the GitHub blob SHA-1 was recomputed from `blob <size>\\0<raw bytes>` and matched GitHub's blob ID. SHA-256 is over the raw file bytes returned by the API. These hashes identify only candidate files; they do not establish that a candidate is an authorized reference.

| Repository revision | Path | GitHub / recomputed Git blob SHA-1 | SHA-256 of raw file |
|---|---|---|---|
| Engine `67597a2a63fd3957e6ec50e270dba8e3df1d3757` | `README.md` | `af9cbdfbf6c16acaca7c754b1800b805903e6a07` | `d32ed8cf9618bc7decea8bb4599d92de4f54d847f8ab7036d188bca1bb72f0b1` |
| Apex `d65ad25b813977b1087b94db5f88a32963426477` | `README.md` | `ab7051c058b97550023e69e73200a4bf6f60adab` | `7cfba2db9715cba330be54ca7a3cd9ab5adde6519ee5d3252edc06a1a4944da5` |
| Apex `d65ad25b813977b1087b94db5f88a32963426477` | `LICENSE` | `165291c0a65176ed5794d605b7a6102d2c37f25e` | `9c6c3d40f38847fd60c7b354473e5320228bfcebe3fdebb1914b347317b204c9` |
| Apex `d65ad25b813977b1087b94db5f88a32963426477` | `docs/APEXLAB_OVERVIEW.md` | `e0c729b18cceb207b6f0da07b01f87df99440dc2` | `5ff079020c9d0be23ff8cab70ac902ee7fa88f6da4a702e9e4f1efc1da78fd77` |
| Apex `d65ad25b813977b1087b94db5f88a32963426477` | `docs/APEXLAB_V2.md` | `d46b6d9ca48376cf4cf0dea8960e05dc2efcc452` | `ebcc3543103e696ac33ddc9519e2fcf35b08cb52c5a5dade0171d2ef948645e6` |
| Apex `d65ad25b813977b1087b94db5f88a32963426477` | `config/protocol_manifest.yaml` | `3cf7246cbe1169e79e62a9313da68a90f1732303` | `410409e1cf98dbda4d2f4302b629a7ea9f9dadf2f1ec3584c6706328ee62bee3` |
| Apex `d65ad25b813977b1087b94db5f88a32963426477` | `docs/PROTOCOLS_TIER.md` | `83ac4c5c1234b960a5ca8a415ce22a196f1904d2` | `6aa104ceab9dcd94f4a0e777f952cdd7d06bc1740fa0b93053103ffeb8bdae16` |

## Acceptance gaps

- Exact immutable source identities and manifests for the three authorized references remain unresolved.
- Relevant historical tests and their outcomes are unknown.
- The historical protocol namespace and T24/T25/T34 verification cases cannot be established from authorized source evidence.
- Duplicate protocol IDs cannot yet be distinguished across the authorized projects.
- No evidence of legacy working-tree changes exists: no local legacy trees were present, and all remote requests made were GET-only.

## Required to unblock

Provide the exact repository URLs (and an immutable revision, if a specific historical snapshot is intended) for the three references, or explicitly approve which named reference(s) may be excluded. Until then, keep QC2-001 blocked and do not start downstream tasks.
