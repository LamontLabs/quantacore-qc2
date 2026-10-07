# Change Classification, Amendment, and Gate Revalidation

## Change classes

Classify a change by its highest-impact effect, not its label or file type. If
the class is ambiguous, use the more restrictive class until reviewed.

| Class | Meaning | Minimum decision/proof | Epoch and authority effect |
| --- | --- | --- | --- |
| C0 — Presentation only | Changes display or wording without changing meaning, eligibility, action, evidence, or claim scope | Verify accessible display and prove no contract, gate, report-claim, or command semantics changed | No scientific identity change. Reclassify if presentation can alter a decision or claim |
| C1 — Operational implementation | Operational change with proven scientific equivalence | Record equivalence proof, affected contracts, fault/replay/regression tests, rollback path, and effective boundary | Preserve scientific identity only while equivalence is demonstrated; revalidate affected gates before dependent use |
| C2 — Scientific identity | Changes data, universe, labels, features, protocols, score, model, strategy, statistical policy, or another scientific dependency | Exact amendment/decision, impact and migration, new versioned dependencies, tests, and frozen effective boundary | Starts a new epoch unless the exact model-only transition is already permitted by a frozen adaptive policy. A value-changing bug fix is C2 |
| C3 — Authority or security | Changes writer ownership, permissions, identity, trust roots, isolation, signing, authorization, or evidence security | Owner-approved constitutional amendment; threat/permission analysis; migration and rollback; hostile security and regression tests; full dependent-gate review | No implementation-only widening. Affected authority/security gates require revalidation before dependent use |
| C4 — Emergency containment | Immediate action that reduces permission or contains a safety/security incident | Record actor, reason, time, affected scope, evidence, and expiry/review condition; preserve prior evidence | May hold or reduce permission immediately. Cannot authorize exposure, weaken gates, repair history, or serve as permanent policy without normal approval |

## Amendment procedure

1. **Open a change record.** State the reason, exact governing requirements,
   contracts, state domains, epochs, tasks, receipts, and users affected. The
   record is a proposal until approved and implemented.
2. **Classify impact.** Choose C0–C4 using the table above. Record the
   classification rationale and the reason any lower class does not apply.
   Include the higher class for mixed changes.
3. **Name the authority.** Identify the sole canonical state owner for every
   affected domain. A requestor, reviewer, Owner API, Android client, research
   worker, or migration tool is not automatically that owner.
4. **For constitutional changes, obtain prior owner approval.** The amendment
   must identify the requirements changed, reason, impact, migration, tests,
   and effective boundary. Approval cannot make invalid evidence, an
   unavailable capability, or a failed machine gate pass.
5. **Specify migration and rollback.** Preserve immutable artifacts and history.
   Use a forward-only migration where storage changes. Rollback is a new
   authorized forward transition; it does not rewind evidence or reuse old
   approval.
6. **Determine the affected dependency closure.** Starting with changed
   requirements and artifacts, identify dependent contracts, manifests, tests,
   task receipts, runtime authorities, reports, epochs, and downstream gates.
   Record unaffected items with a reason rather than assuming no impact.
7. **Mark affected gates stale.** Mark each dependent acceptance gate
   `NEEDS_REVALIDATION` in acceptance metadata. Preserve its task state; this is
   not a fourth successful task state. A stale receipt cannot satisfy a
   dependency or advance the canonical sequence.
8. **Revalidate before use.** Run the exact tests/evidence appropriate to each
   affected gate against the changed versions and record a new receipt with
   commands, environment/evidence class, outcomes, artifact hashes, unresolved
   decisions, verdict, and reviewer/agent identity. Revalidate affected
   descendants in dependency order.
9. **Apply at the effective boundary.** A scientific change starts a new epoch
   except for the narrowly permitted transition already frozen in adaptive
   policy. Activation requires the separate exact, prospective activation
   request and server-side gate recheck.

## Non-negotiable controls

- A later timestamp does not outrank the authority hierarchy.
- No silent change to feed, universe, labels, features, score, strategy, or
  governed learned-memory dependencies within an epoch.
- C4 can reduce permissions or hold operations immediately; releasing the hold
  requires the normal current evidence and gates.
- Reopening a PASS task requires a recorded amendment/change request.
  Downstream gate metadata becomes `NEEDS_REVALIDATION`; task state is not
  silently rewritten to imply success.
- The single-task-at-a-time rule remains in force. Amendment review does not
  start or partially implement a later canonical task.
- A documentation, framework, fixture, task, or audit PASS is not production
  activation, permission to submit paper orders, or permission to trade live.

## Sources

`docs/GEN2_MASTER_SPEC.md` §§0, 5, 24, 27, 36, and 40 govern precedence,
change classes, atomicity, transition boundaries, task revalidation, and F0
activation. `docs/AUTHORITY_MODEL.md` identifies the state owners and planned
enforcement families.
