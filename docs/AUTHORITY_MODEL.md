# Authority Model and Requirement Traceability

**Status:** Normative ownership and test plan derived from
`docs/GEN2_MASTER_SPEC.md` §§2–5. A planned test is not evidence that its future
product test has already run.

## Canonical state ownership

Every state domain below has exactly one canonical mutation owner. The names and
write scopes match the governing authority table; the additional columns identify
implementation boundaries and planned acceptance coverage. A writer may not
delegate or duplicate its canonical write permission by sharing source code,
database credentials, or a writable settings copy.

| Canonical state domain | Sole owning authority | Sole canonical write responsibility | Explicit non-responsibility | Planned authority task coverage |
| --- | --- | --- | --- | --- |
| Calendar | Calendar | Session calendars, calendar revisions, operational phase | Inventing missing price data | QC2-008, QC2-021 |
| Instrument/Universe | Instrument/Universe | Stable security identity, symbol history, classification, candidate and eligibility manifests | Using future survival or broker buying power for eligibility | QC2-012, QC2-033 |
| Market Data | Market Data | Requests, raw receipts, normalized bundles, quarantines, market snapshots/revisions | Training, scoring, broker mutation | QC2-009, QC2-010, QC2-011 |
| Feature | Feature | Feature definitions, dependency manifests, deterministic feature snapshots | Reading labels or future memories | QC2-014 |
| Runner Protocol | Runner Protocol | Protocol lineage, versioned pure evaluations | Permission to execute or alter safety | QC2-017, QC2-018, QC2-019, QC2-020 |
| Inference | Inference | Exact model loading and head outputs | Fit, retrain, promote, select a different model | QC2-023 |
| QuantraScore | QuantraScore | Versioned deterministic synthesis | Producing an undocumented probability | QC2-024 |
| Prediction | Prediction | Run bindings, row outcomes, complete ranks, prediction seals | Selecting a later successful retry | QC2-025 |
| Label | Label | Definitions and maturity rules | Choosing definitions after viewing qualification outcomes | QC2-015 |
| Ground Truth | Ground Truth | Independent outcome calculations and revisions | Asking the model whether it was correct | QC2-016, QC2-027 |
| Validation | Validation | Epoch protocol, scheduled-attempt accounting, metrics, final decision | Training or silently repairing history | QC2-026 |
| Safety | Safety | Action-specific readiness and blocking decisions | Bullish scoring or alpha generation | QC2-021, QC2-050, QC2-051 |
| Strategy | Strategy | Frozen interpretation of predictions into proposed exposure/actions | Modifying model evidence | QC2-044 |
| Execution | Execution | Intent acceptance, submissions, cancellations, fills, positions, reconciliation | Discretionary ranking or live trading | QC2-045, QC2-046, QC2-047, QC2-048, QC2-049 |
| Evidence | Evidence | Append-only event and checkpoint integrity | Treating logging success as scientific success | QC2-006 |
| Configuration | Configuration | Versioned policy references and effective boundaries | Duplicated writable settings | QC2-007 |
| Model Registry | Model Registry | Immutable artifacts and lifecycle facts | Training or self-certifying a candidate | QC2-037 |
| Promotion | Promotion | Eligibility, approvals, atomic authority transitions | Overriding a failed verifier | QC2-040, QC2-041, QC2-042, QC2-043 |
| Identity | Identity | Single owner, devices, keys, sessions, enrollment/revocation | Discretionary orders | QC2-042, QC2-053 |
| Alert | Alert | Severity, delivery attempts, acknowledgments | Treating acknowledgment as remediation | QC2-056 |
| ApexLab | ApexLab | Datasets, experiments, genomes, decoys, research reports | Production authority or authoritative outcomes | QC2-027, QC2-028, QC2-029, QC2-030, QC2-031, QC2-032, QC2-033, QC2-034, QC2-035 |

### Boundary rules

- Ground Truth owns RunnerEvent detection; ApexLab may consume those events for
  research memories but cannot author outcomes.
- Label owns the meaning and maturity rule; Ground Truth applies it.
- Model Registry records artifact lifecycle facts; Promotion alone commits the
  canonical operating Champion pointer.
- Validation alone commits epoch activation, after independently verifying the
  exact owner decision and complete activation audit.
- Configuration owns a single versioned reference for each governed policy
  concept. Domain authorities own their domain objects; they must not create
  duplicate writable settings that can disagree with that reference.
- Owner API may enqueue only approved command types. Android is a read client and
  narrow command signer. Neither can write Champion, execution, or epoch state.
- Runtime database grants and isolated identities—not naming conventions—must
  enforce these boundaries. Migration credentials remain offline from application
  processes.
- A canonical record may reference another authority's immutable object by ID
  and hash; referencing it does not grant permission to rewrite it.

## Requirement-to-authority and planned enforcement map

Each invariant has one named primary enforcement owner and at least one explicit
planned test family. Cross-module checks remain part of those tests; the named
owner is accountable for ensuring the invariant is enforced at its boundary.
`PLANNED` describes future task coverage, not a passing implementation test.

| Invariant ID | Requirement summary | Primary enforcement owner | Planned enforcement test | Planned task coverage |
| --- | --- | --- | --- | --- |
| INV-001 | No live endpoint, credential path, adapter, mode switch, or order route | Execution | Static and hostile adapter/config scan rejects live endpoint, credential, and routing paths | QC2-046, QC2-047, QC2-068, QC2-070 |
| INV-002 | Only Execution can cause broker mutations | Execution | Database-role and adapter tests deny broker mutations from every non-Execution identity | QC2-046, QC2-068, QC2-070 |
| INV-003 | One canonical operating ranking per epoch and scheduled session | Prediction | Concurrent run/retry test proves one official seal and rank binding | QC2-025, QC2-069, QC2-071 |
| INV-004 | Every prediction binds complete immutable scientific dependencies | Prediction | Binding and replay tests reject missing, changed, or mixed-generation dependency roots | QC2-023, QC2-025, QC2-039, QC2-069 |
| INV-005 | Sealed scientific payloads cannot be edited, resealed, or overwritten | Prediction | Attempt update, reseal, delete, and favorable-retry replacement; original seal remains authoritative or operation is denied | QC2-006, QC2-025, QC2-068, QC2-069 |
| INV-006 | Every input and learned dependency obeys its availability cutoff | Feature | Direct and indirect future-input tests reject bars, metadata, transforms, memories, and indexes beyond cutoff | QC2-013, QC2-028, QC2-029, QC2-069 |
| INV-007 | Future labels cannot enter learning, transforms, memories, or tuning early | ApexLab | Cutoff-filtered dataset and learned-dependency tests deny immature labels and future-derived artifacts | QC2-013, QC2-028, QC2-029, QC2-033, QC2-069 |
| INV-008 | Ground Truth has no model, score, rank, or strategy dependency | Ground Truth | Import/credential boundary and independent outcome fixture tests prove outcome computation without model logic | QC2-016, QC2-027, QC2-069 |
| INV-009 | Safety state cannot raise probability or score | Safety | Safety PASS/FAIL permutation leaves scientific score bytes unchanged; architecture regression scan forbids score write | QC2-021, QC2-024, QC2-072 |
| INV-010 | Broker availability cannot change scientific eligibility or ranking | Prediction | Same sealed input under broker-up and broker-down conditions yields identical eligibility, ranks, and seals | QC2-025, QC2-026, QC2-069 |
| INV-011 | Research cannot mutate production authority, predictions, outcomes, or orders | ApexLab | Research credentials and artifact sandbox are denied production tables, broker secrets, and canonical mutation procedures | QC2-033, QC2-034, QC2-035, QC2-068 |
| INV-012 | Owner requests pass machine gates; approval is necessary but never sufficient | Promotion | Signed approval paired with a failed, stale, revoked, or incompatible gate is denied atomically | QC2-041, QC2-042, QC2-043, QC2-055, QC2-068 |
| INV-013 | One operating Champion pointer per active epoch; Reference is immutable | Promotion | Concurrent transition, duplicate pointer, and Reference rewrite tests fail without changing the prior authoritative pointer | QC2-037, QC2-043, QC2-071, QC2-084 |
| INV-014 | Every scheduled prediction opportunity is accounted for, including missed starts | Validation | Scheduler omission, delayed start, and duplicate attempt tests produce one durable attempt disposition each | QC2-008, QC2-025, QC2-026, QC2-071 |
| INV-015 | Qualification cannot depend on future returns or a preferred model winning | Validation | Locked outcome mutation and candidate-order permutation do not change eligibility or the frozen qualification rule | QC2-026, QC2-069, QC2-081 |
| INV-016 | Unknown data/action state is not converted to a negative label or success | Ground Truth | Missing bars, ambiguous action outcomes, and unknown broker responses retain explicit unresolved states | QC2-016, QC2-049, QC2-069, QC2-070 |
| INV-017 | Sealed snapshot replay requires no provider, broker, or current mutable state | Prediction | Network-disabled replay from retained immutable dependencies reproduces payload hashes and dispositions | QC2-039, QC2-069, QC2-071 |
| INV-018 | Authoritative mutation is atomic with evidence and recoverable after restart | Evidence | Inject evidence/outbox failure during domain mutation; transaction rolls back and restart recovers committed state only | QC2-005, QC2-006, QC2-071 |
| INV-019 | Expired lease/generation cannot commit from a stale worker | Durable Job Service | Pause worker past lease expiry, fence its generation, then prove its commit is rejected | QC2-025, QC2-046, QC2-071 |
| INV-020 | Feed, universe, labels, features, score, strategy, and learned dependencies do not silently change within an epoch | Configuration | Mutate each bound policy reference during an active epoch; reject write or confine it to a future permitted boundary | QC2-007, QC2-025, QC2-072 |
| INV-021 | Restored installation cannot resume orders before reconciliation and identity checks | Execution | Restore with pending outbox, stale identity, or unknown account state; no submit until fresh reconciliation and identity pass | QC2-049, QC2-051, QC2-053, QC2-066, QC2-070, QC2-071 |
| INV-022 | A gate requiring real evidence cannot pass on mocks or fixtures | Build Governance / Task Registry | Receipt validator rejects fixture evidence for real-data/device gates and records the evidence class actually run | QC2-000, QC2-072 |
| INV-023 | Development, test, research, and production data/credentials are isolated | Configuration | Cross-environment credential, storage, and row-access probes deny unauthorized reads and writes | QC2-005, QC2-034, QC2-068 |
| INV-024 | Reports do not claim broader market, time, feed, or execution validity than evidence supports | Validation | Report claim-scope tests compare claim metadata to feed, period, universe fidelity, and execution evidence | QC2-026, QC2-063, QC2-072 |

## Contradiction review

| Review ID | Apparent contradiction | Governing resolution | Planned verification |
| --- | --- | --- | --- |
| CR-EXEC-EXIT | A general execution halt could block protective exits, but an unrestricted exit could create unrecorded or duplicate risk | New exposure, cancellation, and risk-reducing actions have separate readiness. Entry pause blocks new exposure and follows the frozen pending-entry cancellation rule; it does not liquidate. Exit readiness does not depend on a healthy Champion or new snapshot. If evidence, identity, database, or broker capability prevents a safe recorded mutation, the system must disclose that limit and hold rather than promise an unavailable exit. | Verify new-entry pause, cancel race, and model-unavailable exit cases; verify that integrity/database failure does not claim a safe exit. |
| CR-BOOTSTRAP | Model Registry must exist before there is a real Champion, while Champion uniqueness rules apply once an epoch operates | Registry bootstrap may be `NO_CHAMPION`. The first real Champion requires the nominated artifact to pass independent qualification, then a Promotion transition with exact `NO_CHAMPION` expected state. It cannot overwrite an existing pointer; QC2-084 keeps the initial Reference bound to that complete artifact. Fixtures are never production identity. | Test no-Champion registry, valid bootstrap CAS, existing-pointer denial, and fixture-identity denial. |
| CR-ACTIVATION | Early tasks build contracts and fixture transitions, but the system's later activation requires measured capabilities and owner authorization | Framework/task PASS is not activation. All QC2-000–QC2-087 receipts must be current and passing; required unknowns and real capability/device/evidence/recovery gates must be resolved. Validation verifies the exact immutable epoch, prospective session, account and strategy identities, and audit; the owner signs the exact activation request; the server independently rechecks and commits prospectively. QC2-088 alone authorizes the start, not successful F0 or live trading. | Verify stale/incomplete activation audit, missing real evidence, duplicate request, changed manifest, and exact signed prospective activation cases. |

### Interpretation limits

The execution/exit resolution does not guarantee that an exit can be sent while
the server, evidence store, identity service, or broker is unavailable. Initial
bootstrap does not imply an initial model exists. Activation remains blocked by
any required unresolved policy, capability, empirical value, engineering limit,
or missing real gate evidence; acceptance of this document satisfies none of
those later gates.
