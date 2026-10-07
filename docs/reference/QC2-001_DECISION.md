# QC2-001 — Scoped source-role decision

- **Date:** 2026-10-06
- **Result:** PASS under the approved logical-role interpretation.

## Decision

QC2-001's three references are logical source roles:

1. QuantraCore production/core implementation.
2. ApexLab research/training.
3. Original QuantraCore runner-protocol lineage.

They do not require three separate repositories or literal repositories labeled “Gen 1.” One repository may cover multiple roles, and a later snapshot may map to a role when its exact commit, actual version labels, content, license, and provenance limits are recorded. A role mapping is not proof of original lineage, Gen 1 identity, production deployment, or production authorization. Those claims stay unverified unless source evidence proves them.

## Evidence-based application

- The QuantraCore-Apex core and risk packages provide inspectable core implementation evidence. Its repository snapshot is pinned to `d65ad25b813977b1087b94db5f88a32963426477`.
- The same snapshot contains the ApexLab research/training package and a pipeline test.
- The runner-protocol role is mapped to the T01–T12 QuantraCore-Engine scaffold at `67597a2a63fd3957e6ec50e270dba8e3df1d3757` and the expanded T01–T80 tier namespace in the pinned Apex snapshot.
- `LamontLabs/QuantraCore_production` has no resolvable commit or source tree. The mapped core code is therefore not represented as a verified production deployment.
- No inspected source proves the historical origin of the “original” runner-protocol project. The later snapshots are role references only.

## Scope and handling

Protocol IDs are repository- and path-qualified; matching IDs are not presumed to share meaning. T24, T25, and T34 are interpreted from their pinned implementations, and conflicts with the tier documentation are retained in the source manifest. Existing test locations are recorded, but no legacy runtime modules were imported and no legacy test suite was run.

This decision changes only QC2-001's source-identification rule. It does not start QC2-002, create its broader decision log, alter any other task, or authorize modification or runtime import of legacy source.
