---
name: ApexLab temporal memory indexes
description: Temporal rules for RunnerGenome indexes, replay proofs, and reconstructed availability.
---

ApexLab replay-proof revisions must cover the returned artifact and its validated dependency closure, not unrelated artifacts in the catalog. Filter index members before lookup. Empty indexes need an explicit proof of the index's own availability; if an embedding exists, validate its dependency closure separately.

**Why:** A full-catalog revision lets later, unrelated artifacts change a past decision's proof. The generic temporal firewall also fails closed on an index without an explicit member set, so an intentionally empty index needs a narrow, explicit proof rather than a fabricated member.

**How to apply:** Bind the exact cutoff, builder version, and member refs into the index inventory hash. Compute lookup proof revisions from the index/genome plus only its selected temporal dependencies. Never expose future members through similarity or catalog state.

Keep actual creation, known, and learning times separate from historical reconstructed availability and learning assumptions.

**Why:** Reconstructed history is an explicit research assumption, not evidence that the artifact actually existed or was learnable then.

**How to apply:** Use actual timestamps for forward eligibility and creation ordering. Use historical assumptions only in reconstructed-mode cutoff checks, and require each genome/index assumption to be no earlier than its relevant event, sources, and members.
