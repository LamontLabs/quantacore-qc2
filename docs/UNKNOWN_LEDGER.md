# Gen 2 Typed Unknown Ledger

**State at record date:** No row below is resolved for production. Each affected
capability remains blocked until the listed evidence and authority action are
recorded. This is not an inferred implementation backlog or a source of
fallback values.

## Open decisions and measurements

| ID | Required decision class | Unresolved scope | Sole canonical record owner | Resolution evidence | Current approved production value | Consequence while unresolved |
| --- | --- | --- | --- | --- | --- | --- |
| OP-001 | OWNER_POLICY_REQUIRED | Paper starting capital, per-position cost/fraction, gross exposure, cash reserve, concurrent-position cap, participation/liquidity cap, and treatment of external account activity | Configuration | Exact owner-signed CapitalPolicy and verified identity/receipt, then strategy and execution gate tests | NONE — unresolved; no fixture or inferred cap | NEW_ENTRY_READY and paper execution remain blocked; F0 activation is blocked |
| OP-002 | OWNER_POLICY_REQUIRED | Daily loss/drawdown thresholds and the owner-selected response within the specified halt model | Configuration | Exact owner-signed policy, versioned reference, Safety and Execution tests | NONE — unresolved; no guessed trigger or response | Affected paper-entry readiness and F0 activation remain blocked |
| OP-003 | OWNER_POLICY_REQUIRED | Recovery method and owner recovery-point/recovery-time objectives and retention policy | Configuration | Owner-signed recovery policy plus successful isolated restore/reconciliation evidence | NONE — unresolved; no assumed objective | Backup/restore acceptance and F0 activation remain blocked |
| CAP-001 | CAPABILITY_MEASUREMENT_REQUIRED | Actual Alpaca market-data entitlement, available history, API limits, pagination, data semantics, coverage, and supported finalization timing | Market Data | QC2-009/010 probes against the actual selected account and retained capability receipt | NONE — no feed or entitlement assumed | No feed-dependent snapshot or F0 activation |
| CAP-002 | CAPABILITY_MEASUREMENT_REQUIRED | Actual calendar reach, exceptional-session coverage, session/deadline semantics, and observed clock capability | Calendar | Versioned calendar evidence and measured trusted-time/deadline tests | NONE — no capability inferred from local time or library defaults | Affected scheduled attempt and F0 activation remain blocked |
| CAP-003 | CAPABILITY_MEASUREMENT_REQUIRED | Unattended scheduling, persistent database/artifact storage, isolation, outbound access, job duration, concurrency, quota, restart, and backup capability of the selected host | Configuration | Exact deployment capability manifest with measured probes and independent recovery evidence | NONE — development preview and inherited deployment settings are not production evidence | Unattended operation and F0 activation remain blocked |
| CAP-004 | CAPABILITY_MEASUREMENT_REQUIRED | Dedicated Alpaca Paper account identity, endpoint behavior, order precision, order semantics, consistency window, fill/reconciliation behavior | Execution | Actual-account capability and hostile integration receipts under explicit paper-only authorization | NONE — no account/order semantics assumed | Paper execution remains disabled; F0 activation is blocked |
| CAP-005 | CAPABILITY_MEASUREMENT_REQUIRED | Owner device, key enrollment, user-presence signing, revocation, and recovery capability on a real supported device | Identity | Real-device enrollment, signing, revocation, and recovery receipts | NONE — fixture identity is not production identity | Real owner actions and F0 activation remain blocked |
| EMP-001 | EMPIRICAL_CALIBRATION_REQUIRED | Candidate-universe and eligibility thresholds | Instrument/Universe | Preregistered development-only calibration, coverage/missingness report, and frozen manifest | NONE — no fixture threshold may enter a production manifest | Production universe and F0 activation remain blocked |
| EMP-002 | EMPIRICAL_CALIBRATION_REQUIRED | Expansion Runner and Monster label thresholds and related label calibration values | Label | Preregistered development-only analysis, mature outcome receipts, and frozen label registry | NONE — no outcome-informed or guessed threshold | Qualification and F0 activation remain blocked |
| EMP-003 | EMPIRICAL_CALIBRATION_REQUIRED | Feature lookbacks, subset selection, and other empirically selected feature definitions | Feature | Development-fold-only study, leakage checks, and frozen dependency manifest | NONE — no provisional feature profile promoted by implication | Production prediction readiness and F0 activation remain blocked |
| EMP-004 | EMPIRICAL_CALIBRATION_REQUIRED | Runner Protocol thresholds and active protocol set | Runner Protocol | Source-qualified lineage plus preregistered development calibration and frozen protocol registry | NONE — no uncalibrated active set | Production prediction readiness and F0 activation remain blocked |
| EMP-005 | EMPIRICAL_CALIBRATION_REQUIRED | QuantraScore coefficients, precision, and optional-head inclusion policy | QuantraScore | Development-only coefficient study, deterministic replay, and frozen score manifest | NONE — no guessed coefficient or implied optional-head availability | Production prediction readiness and F0 activation remain blocked |
| EMP-006 | EMPIRICAL_CALIBRATION_REQUIRED | Missingness eligibility, coverage/abstention limits, and associated qualification guardrails | Validation | Preregistered development-only missingness bounds, adverse-case tests, and frozen gate manifest | NONE — unknown rows remain unknown, never silently dropped or treated as negative | Qualification and F0 activation remain blocked |
| EMP-007 | EMPIRICAL_CALIBRATION_REQUIRED | Frozen strategy values, including rank selection, allocation, price cap, holding/exit/cooldown values, within separately signed owner caps | Strategy | Development-only calibration, immutable StrategyManifest, and proof of compliance with signed CapitalPolicy | NONE — no strategy value or cap is inferred | New-entry readiness and F0 activation remain blocked |
| EMP-008 | EMPIRICAL_CALIBRATION_REQUIRED | Promotion minimum samples/effects, prospective event requirements, Shadow duration, cooldown, and permitted transition envelope | Promotion | Preregistered development plan, independent evidence, and frozen PromotionPolicy | NONE — no candidate can self-select its gate | Promotion readiness and F0 activation remain blocked |
| EMP-009 | EMPIRICAL_CALIBRATION_REQUIRED | F0 event/sample requirements, power, minimum effect, uncertainty method, coverage, dependence settings, missingness rule, stopping rule, and maximum collection/maturation windows | Validation | Development-only calibration and simulation validation, owner approval where required, and frozen statistical plan before activation | NONE for unresolved plan fields; the specification's explicit 90-session collection target and default one-sided alpha 0.05 are not unset by this row | F0 qualification and activation remain blocked |
| EMP-010 | EMPIRICAL_CALIBRATION_REQUIRED | Candidate model/ensemble search space, model-specific training choices, and calibrated candidate selection | ApexLab | Logged development experiments under permitted folds, consumed-holdout controls, and independent candidate qualification | NONE — no research candidate is an operating Champion by default | Candidate qualification and F0 activation remain blocked |
| ENG-001 | ENGINEERING_LIMIT_REQUIRED | Request/retry counts and elapsed budgets, job/training CPU-memory-runtime limits, artifact/report size, experiment count, storage growth, and research concurrency | Configuration | Measured deployment/resource evidence, documented justification, versioned limits, and boundary/fault tests | NONE — no guessed ceiling or unbounded fallback | Bounded unattended work and F0 activation remain blocked |
| ENG-002 | ENGINEERING_LIMIT_REQUIRED | Clock uncertainty/tolerance and timing margins used for session deadlines and freshness | Configuration | Measured trusted-time comparison, explicit uncertainty policy, and boundary tests under clock jumps | NONE — no implicit tolerance | Deadline-dependent readiness and F0 activation remain blocked |
| ENG-003 | ENGINEERING_LIMIT_REQUIRED | Owner challenge lifetime and action freshness window | Identity | Measured online flow, frozen policy, expiry/replay/revocation tests, and exact challenge binding | NONE — no assumed lifetime or stale-approval grace period | Privileged owner mutations and F0 activation remain blocked |

## Rules for resolution

1. Resolve the item only in its stated class and by its sole canonical record
   owner. Owner selection/signature and authority persistence are distinct:
   identity verifies the signer; the designated authority stores the canonical
   versioned decision.
2. Preserve the evidence, version/hash, observed time, affected tasks, gate
   consequences, and effective boundary. A capability must be measured in the
   actual account/deployment/device when the specification requires real
   evidence.
3. Empirical values are chosen using the permitted development evidence and
   frozen before qualification/F0. Locked holdout or F0 outcomes cannot be used
   to tune a threshold and then still count as untouched confirmation.
4. Engineering limits require measured-resource justification and tests.
   Defaults are not created by a missing configuration key.
5. A fixture value must be visibly fixture-scoped and rejected from a production
   dependency closure. No resolution in this ledger activates F0 by itself.

## Explicit non-unknowns

The governing specification already defines architectural constants and
explicit defaults, including paper-only scope, one owner, the primary five-
session horizon, the rank tie order, the F0 target of 90 qualifying sessions,
the initial 10-session secondary outcome horizon, default one-sided alpha 0.05,
and `FROZEN_CHAMPION` as the initial mode. They are not reclassified here as
unknown. Any field the specification expressly leaves to owner policy,
capability measurement, empirical calibration, or engineering measurement
remains unresolved until its own evidence is recorded.
