---
name: QC2 label precision
description: Canonical fractional-return precision and event-threshold comparison behavior for QC2 labels.
---

QC2 label fractional-return fields must be rounded to exactly 12 decimal places with `ROUND_HALF_EVEN`, and event comparisons must use those same rounded values. Select peak/trough sessions from raw observed prices so return rounding cannot create or hide an extrema tie.

**Why:** the Outcome wire contract requires twelve fractional places and the feature authority already uses `ROUND_HALF_EVEN`; using one precision rule keeps stored outcomes and threshold labels consistent.

**How to apply:** when implementing or changing Ground Truth outcome serialization and label event comparisons, preserve exact prices, round derived returns at the contract boundary, and retain the earliest-session tie-break.
