# QuantraCore Apex Gen 2 — Hardening Review

**Date:** October 6, 2026. **Scope:** the supplied governing specification. **Implementation status:** not started or certified by this review. Legacy repositories and account credentials were not inspected.

The replacement specification is complete enough to govern implementation, while leaving empirical choices and account facts as explicit gated decisions. The design has been materially strengthened; it has not been proven secure or profitable merely by being written.

| Priority | Gap | Correction | Governing sections |
| --- | --- | --- | --- |
| Critical | Future knowledge through models, preprocessing or learned memories | Recursive learning cutoffs; actual versus assumed historical availability; immutable model dependency closure | 6–7, 16, 19–22 |
| Critical | Frozen model changes through growing similarity index | Freeze complete learned-dependency root; update only through permitted governed model release | 16, 22 |
| Critical | Local hash chain overclaims historical proof | Independent pre-outcome checkpoints; defined trust boundary and local-only downgrade | 24 |
| Critical | State changes commit without matching evidence | Atomic domain/evidence/outbox mutation procedures with authenticated actor identity | 4, 24–25 |
| Critical | Broker timeout causes a duplicate order | Durable attempt before send; explicit SUBMISSION_UNKNOWN; reconciliation before retry | 29 |
| Critical | Safety halt blocks exits or accidental concurrent sells create shorts | Action-specific readiness; simple orders and share reservations; definitive cancel reconciliation | 28–30 |
| Critical | Approval can be replayed against changed state | Device/action/epoch/bundle/generation/nonce/expiry binding and commit-time revocation | 27, 31–32 |
| Critical | Broad roles defeat claimed authority boundaries | Narrow writers, restricted stored operations, nonprivileged runtime identities and artifact ACLs | 3–4 |
| High | Day qualification can cherry-pick favorable outcomes | Advance schedule inventory and sealed pre-outcome qualification; report all missed attempts | 17, 21, 34 |
| High | Missing data and survivorship disappear from metrics | Explicit census/eligible/scored/unscorable denominators, fidelity limits and adverse bounds | 7, 10, 14, 21 |
| High | Daily bars assumed to represent exact executable prices | Provider bar-semantics manifest; next-open proxy, excursion outcomes and paper fills kept separate | 8–9, 14, 28 |
| High | Splits, delistings and ticker reuse contaminate returns | Stable security identities, raw receipts, split-consistent reference basis and unresolved states | 9–11, 14 |
| High | Holdout repeatedly reused during model tuning | Development nomination before independent locked qualification; access/consumption receipts | 20 |
| High | Ninety sessions treated as proof regardless of rare-event count | Dependence-aware primary estimand, power/coverage checks and three-state closure | 21–22 |
| High | Adaptive promotions change the experiment without defining the policy | Default frozen F0; explicitly preregistered adaptive alternative, separate claims | 22, 26–27 |
| High | Signed model assumed safe to deserialize | Allowlisted artifact formats, inventory validation and isolated loader | 12, 16, 27 |
| High | Restores silently replay old orders or erase latest evidence | Independent checkpoint comparison, fenced recovery generation, order-disabled restore and reconciliation | 25, 33 |
| High | Research jobs exhaust resources or depend on sleeping development host | Real deployment capability proof, bounded budgets, durable jobs and production priorities | 3, 5, 25 |
| High | Most tasks lack dependencies or acceptance details | All 89 tasks have complete contracts and predecessor chain; structure checked mechanically | 36–39 |
| High | Early vertical slice depends on later authorities | Narrow QC2-011 to acquisition/evidence; real forward maturation required at QC2-086 | 36, task contracts |
| High | Approval framework precedes device identity | Fixture-only early interfaces, real identity/security gates before activation | 27, 31, 36 |
| High | Activation requires a signature but provides no owner flow | Narrow epoch-activation decision through Validation with the same exact-signature controls | 31, 40 |

## Explicit design choices introduced

- Initial F0 defaults to a frozen Champion with a frozen complete learned dependency root. Adaptive operation remains available only through a pre-activation registered policy.
- Initial paper entries are long-only, whole-share, capped regular-session DAY buy limits. Initial order class is simple; bracket/OCO behavior requires a later reviewed amendment.
- The primary reporting comparison is paired session-level five-session Expansion Runner Precision@10 against a transparent equal-weight baseline. Parameters requiring empirical justification remain gated at calibration.
- Strong official forward proof requires independent checkpoint receipt before outcome sessions begin. Local-only collection is useful but carries a weaker evidence class and does not count toward that claim.
- Android gains only one narrow additional owner decision category: exact epoch activation, needed to make activation authorization concrete. It adds no discretionary trading authority.
- Owner risk ceilings, engineering limits, capability measurements and empirical thresholds are distinct decision classes. The agent cannot optimize or invent owner authority.

## Residual limits that cannot be erased by specification

Actual free-data entitlement, historical delisted-security completeness, instrument classifications, host isolation, independent anchoring, real Android behavior, available budget and model edge require evidence during the build. If those facts cannot support the intended claim, the appropriate gate blocks or the owner approves a narrower new experiment. No account capability or predictive advantage has been fabricated here.

The included validation report checks document structure, task identities and dependencies. It is not a security audit of code, an Alpaca account probe, an Android test, a restore drill, or market validation.
