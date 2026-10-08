---
name: QC2 task progression
description: The user's preference for autonomous task completion bookkeeping and sequential progression in the QC2 build.
---

In the QC2 build, resume at the earliest canonical task that is not PASS, even when the platform assignment points to a later task. Do not ask the owner to mark each task complete; handle completion bookkeeping and proceed sequentially. Canonical acceptance requires committing the tested source first; the finish workflow hashes artifact paths at that integrated commit, then generates acceptance receipts and task docs.

**Why:** the user corrected the prior sequence to begin with the earliest unfinished canonical task and continue toward the assigned later task, without per-task completion prompts. Acceptance validation also checks artifact hashes on earlier PASS tasks, not only declared dependencies. The finish step must bind evidence to an unchanged, integrated source commit before it mutates registry and receipt files.

**How to apply:** Reconcile the platform assignment against the canonical registry before implementation. For each changed shared tree, enumerate every earlier PASS receipt that hashes it, not only direct dependencies; preflight can pass while final registry validation catches missed historical receipts. Add scoped downstream drift authorization for each before acceptance, commit tested implementation paths, run the finish workflow against that source commit, then validate and commit generated receipts. Advance only when the current task's scope permits; stop at an explicit boundary without starting downstream work.
