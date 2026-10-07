# Canonical task acceptance workflow

**Workflow version:** 2.0

**Authority:** `registry/BUILD_TASKS.json` is the canonical task state. Native
task-board labels, merge state, and task titles are projections only; none can
create a canonical `PASS`.

## Sequential execution

1. Preserve the 89 canonical task IDs, names, dependencies, scientific
   requirements, and valid historical acceptance evidence. Follow their
   topological order; keep at most one canonical task `IN_PROGRESS`.
2. Before starting a task, run
   `python3 tools/task_workflow.py preflight QC2-NNN`. Preflight verifies every
   declared dependency's PASS records, content hashes, integrated source commit,
   and implementation bytes against both that commit and the receiving
   workspace.
3. Start an eligible task with
   `python3 tools/task_workflow.py start QC2-NNN`. It refuses a second active
   canonical task and regenerates the task documents.
4. When a task passes acceptance and its complete change set is integrated,
   report progress and automatically start the next eligible task. Routine
   acceptance-record creation, canonical bookkeeping, and advancement require
   no separate permission prompt.
5. If a predecessor needs repair, suspend the current task, repair and
   revalidate the predecessor and affected receipts, then return to the
   suspended task. Do not implement future tasks in parallel or in detached
   background work.

## Required completion evidence

1. Produce every task deliverable and run every required acceptance check
   against the exact implementation commit that will be integrated. Record
   actual commands, results, skips, limitations, and test counts; never
   backdate a check or imply independent review that did not occur.
2. Write `docs/reference/QC2-NNN_ACCEPTANCE_RECEIPT.md`. Include an
   `## Acceptance assessment` and an `## Acceptance checklist`. The checklist
   must contain one evidence-linked checked row for every exact required
   deliverable and test:

   - `- [x] DELIVERABLE: <exact registry text> | evidence: <path or result>`
   - `- [x] TEST: <exact registry text> | evidence: <path or result>`

3. Run `python3 tools/task_workflow.py finish QC2-NNN` with the actual tested
   source commit, evidence class/environment, executed commands, test counts,
   assessment path, and implementation artifact paths. The helper validates
   the checklist, ties artifact hashes to the tested commit, creates the
   content-addressed `BuildTask` and `TaskAcceptanceReceipt`, records the
   current UTC time, updates the registry and local task description, and
   regenerates `docs/BUILD_TASKS.md` and `docs/TASK_DEPENDENCIES.md`.
4. Commit the implementation, assessment, structured records, registry,
   generated task documents, and workflow tests as one integrated task change
   set. Then run `python3 tools/task_workflow.py validate`. Validation and
   dependent-task preflight require receipt records and exact implementation
   bytes to be present in the current integrated commit and workspace.
5. Do not report completion until the integrated workspace passes validation.
   A stale/missing artifact, mismatched source commit, missing receipt, failed
   required check, or stale generated task document keeps the task from
   passing.

## Authority and real gates

- The canonical registry and evidence-backed acceptance records determine task
  state. Native task-board status never promotes `TODO`, `IN_PROGRESS`, or
  `BLOCKED` to `PASS`.
- Update native task descriptions only through an available supported
  operation. If no such operation is exposed, update the canonical registry
  and generated task documentation; never use a board label as a substitute.
- Ordinary implementation decisions inside the accepted architecture are
  authorized. Unavailable credentials/repositories, physical-device
  participation, unresolved owner-risk/cost decisions, destructive/external
  actions, substantive architecture changes, and production authorization
  remain real gates.
- Build-task acceptance does not depend on the future Android model-approval
  system. Production model changes and official F0 activation retain their
  separate authorization requirements. QC2-088 may prepare activation
  evidence, but official F0 activation requires exact owner authorization for
  the specified epoch, manifest, and prospective start session.
