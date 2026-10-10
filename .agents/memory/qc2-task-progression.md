---
name: QC2 task progression
description: The user's preference for autonomous task completion bookkeeping and sequential progression in the QC2 build.
---

In the QC2 build, select work from the canonical dependency DAG, not numeric task-ID order. Keep one active task and proceed with eligible independent branches when another branch is deferred. Do not ask the owner to mark each task complete; handle completion bookkeeping autonomously. Canonical acceptance requires committing the tested source first; the finish workflow hashes artifact paths at that integrated commit, then generates acceptance receipts and task docs.

**Why:** the user later asked to audit and revise the plan because the fixed predecessor chain made Android a global gate despite independent backend work. Acceptance validation also checks artifact hashes on earlier PASS tasks, not only declared dependencies. The finish step must bind evidence to an unchanged, integrated source commit before it mutates registry and receipt files. The start guard requires registry changes to be integrated, and the workspace Git command guard blocks unprefixed Git operations.

**How to apply:** Reconcile platform assignment with the canonical registry and choose an eligible task whose declared dependencies are PASS. For shared-tree changes, enumerate every earlier PASS receipt that hashes it; preflight can pass while final validation catches missed historical receipts. Commit scoped drift authorization and generated task docs before starting; include status transitions with tested implementation commits, then finish and validate acceptance receipts. Prefix workspace Git commands with `DANGEROUSLY_ALLOW_GIT=1`. Keep branches independent only where their actual deliverables do not require each other.

For QC2-038, keep the Shadow implementation in its dedicated submodule and import it directly; the QC2-025 receipt pins the prediction-authority package initializer.

**Why:** Editing the shared initializer changed an earlier accepted artifact hash and QC2-038 preflight rejected it because no downstream drift authorization existed.

**How to apply:** Before changing shared package entry points, check every pinned artifact path. Prefer a new focused module over modifying an accepted initializer unless the task explicitly authorizes the drift.

When a master specification pins the canonical contract inventory, keep task-scoped evidence schemas supplemental unless an explicit specification migration is authorized.

**Why:** Expanding the generated catalog changed the accepted canonical count and failed the contract gate; the new observation did not need to become a master-spec object.

**How to apply:** Before adding a schema to the canonical catalog, verify the governing inventory and acceptance pins. Use a clearly scoped supplemental schema for evidence that must not alter the canonical contract set.
