---
name: QC2 task progression
description: The user's preference for autonomous task completion bookkeeping and sequential progression in the QC2 build.
---

In the QC2 build, resume at the earliest canonical task that is not PASS, even when the platform assignment points to a later task. Do not ask the owner to mark each task complete; handle completion bookkeeping and proceed sequentially.

**Why:** the user corrected the prior sequence to begin with the earliest unfinished canonical task and continue toward the assigned later task, without per-task completion prompts.

**How to apply:** Reconcile the platform assignment against the canonical registry before implementation. Complete the current task's acceptance bookkeeping, then advance only when its scope permits; stop at an explicit task boundary without starting downstream work. Keep dependency, evidence, and approval gates in force.
