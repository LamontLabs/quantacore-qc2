---
name: QC2 task progression
description: The user's preference for autonomous task completion bookkeeping and sequential progression in the QC2 build.
---

In the QC2 build, resume at the earliest canonical task that is not PASS, even when the platform assignment points to a later task. Do not ask the owner to mark each task complete; handle completion bookkeeping and proceed sequentially.

**Why:** the user corrected the prior sequence to begin with the earliest unfinished canonical task and continue toward the assigned later task, without per-task completion prompts. Acceptance validation also checks artifact hashes on earlier PASS tasks, not only declared dependencies.

**How to apply:** Reconcile the platform assignment against the canonical registry before implementation. For any changed shared tree, inspect all earlier PASS receipts that hash it and record scoped downstream drift authorization for each before acceptance. Include exact changed-tree hashes in the new receipt and rerun integrated validation. Then advance only when the current task's scope permits; stop at an explicit boundary without starting downstream work.
