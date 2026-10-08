# QC2-021 — Runtime Safety Protocol Framework decision

## Source disposition

The exact authorized Gen 1 QC-T01–T65 safety namespace was not identified in the pinned, accessible source records. Engine-T, Apex-T, and QuantraVision T-tier protocols are distinct namespaces and do not establish action-specific safety meanings. CIL describes a separate domain and its license decision prohibits copying code.

Record the requested legacy lineage as `IGNORE` + `SOURCE_UNRESOLVED`. Do not map by identifier, port legacy code, or claim legacy tests passed. QC2-021 will implement only the Gen 2 master specification and existing Gen 2 contracts. Any later-discovered source requires a separate read-only intake before reuse.

## Framework decisions

- Keep safety results separate from runner hypotheses, scores, model features, and prediction outputs. A safety `PASS` is permission evidence only; it never adds confidence or bullish points.
- Evaluate `PREDICT`, `NEW_ENTRY`, `CANCEL_ENTRY`, `EXIT_POSITION`, and `PROMOTE` independently. Do not create a global readiness flag.
- Required `UNKNOWN` or `UNAVAILABLE` evidence blocks only the action whose policy requires it. An optional `WARN` is accepted only under an explicit `ALLOW_WITH_EVIDENCE` policy and with reason evidence; otherwise it blocks.
- Use supplied immutable evaluation times and source freshness deadlines. Do not add an implicit clock, fallback, or guessed freshness TTL.
- Capability ports that have no configured implementation return explicit `UNAVAILABLE`; no live broker/provider integration is claimed.
- `EXIT_POSITION` has narrower requirements than `NEW_ENTRY`. Failure of model, prediction, or entry-only evidence cannot by itself suppress an exit whose own evidence passes.

## Current task state

All QC2-021 dependencies pass and its preflight passes. The former BLOCKED status and blocker text were stale. The corrected registry and reference intake are integrated, and QC2-021 is IN_PROGRESS through the canonical workflow. The action-scoped implementation, hostile fixtures, contract checks, and full test suite have passed. No live capability behavior is claimed; canonical acceptance is being recorded through the task workflow.
