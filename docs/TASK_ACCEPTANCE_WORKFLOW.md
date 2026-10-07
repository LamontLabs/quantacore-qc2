# Canonical task acceptance workflow

`registry/BUILD_TASKS.json` is the authoritative task state. Task-board labels and
merge status report workflow integration only; neither can create a canonical
`PASS`.

## Start and preflight

1. Before implementation, run
   `python tools/task_workflow.py preflight QC2-NNN`.
2. Preflight requires every declared dependency to be `PASS`, its acceptance
   receipt and task record to exist, their content hashes to validate, their
   source commit to be present in the current integration history, and their
   implementation artifact hashes to match this workspace.
3. Start work only with
   `python tools/task_workflow.py start QC2-NNN`. The command refuses a second
   active canonical task, sets only this task to `IN_PROGRESS`, and regenerates
   task documentation.

## Accept and integrate

1. Run the task's required checks against the implementation that will be
   integrated. Record the exact commands, actual results, skips, and limitations.
2. Write a task-specific acceptance assessment at
   `docs/reference/QC2-NNN_ACCEPTANCE_RECEIPT.md`. State the gate verdict,
   specification and registry versions, test results, source commit, and any
   historical discrepancy. Do not backdate checks or imply independent review
   that did not occur.
3. Run `python tools/task_workflow.py finish QC2-NNN` with the verified source
   commit, evidence class/environment, test counts, commands, and artifact paths.
   It validates the receipt schema, creates a content-addressed `BuildTask`
   record and `TaskAcceptanceReceipt`, captures the actual UTC time and artifact
   hashes, updates the registry and local task description, then regenerates
   `docs/BUILD_TASKS.md` and `docs/TASK_DEPENDENCIES.md`.
4. Run `python tools/task_workflow.py validate`. CI runs the same validation.
   A task cannot remain `PASS` if its receipt, task record, source commit, or
   implementation hashes are missing or stale.
5. Integrate the implementation, Markdown assessment, structured records,
   registry, generated task documents, and workflow tests together. Do not
   report task completion until that integrated workspace passes validation.
6. Before starting a dependent task, run its preflight again in the workspace
   that will receive the changes. A native board status or a merge label alone
   is never sufficient.
