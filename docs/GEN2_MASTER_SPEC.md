# QuantraCore Apex Gen 2

## Governing Architecture, Scientific Protocol, and Controlled Build Specification

**Version:** 2.0 — hardened replacement  
**Specification date:** October 6, 2026  
**Owner:** Jesse J. Lamont / Lamont Labs  
**Canonical repository path:** `docs/GEN2_MASTER_SPEC.md`  
**Status:** PRE-BUILD GOVERNING SPECIFICATION; implementation and operating evidence are not asserted  
**Initial regime:** F0, completed daily OHLCV, one explicitly selected Alpaca feed  
**Execution:** Alpaca Paper only  
**Owner interface:** Android, Kotlin and Jetpack Compose  
**Canonical task set:** QC2-000 through QC2-088, inclusive; 89 tasks

This document replaces the supplied pre-build specification. It preserves the private, single-owner runner-intelligence mission and original task identities, while resolving scientific, security, operational, and dependency gaps. An earlier document cannot override a requirement here. Legacy code is evidence to inspect, never an authority to inherit automatically.

This is a specification audit and redesign, not an audit of the three legacy repositories. Their protocol meanings, defects, test results, file paths, and implementation maturity remain unverified until reference intake. No passing implementation, available credential, sufficient dataset, profitable strategy, or predictive advantage is implied by this document.

The words **MUST**, **MUST NOT**, **SHALL**, and **FORBIDDEN** are mandatory. **MAY** identifies a bounded option. An illustrative value is not a production setting. An unresolved empirical decision is an explicit blocking record, never an implicit default.

## 0. Governing interpretation and changes

The following hierarchy applies: owner-approved constitutional amendment; this specification and its approved amendments; versioned contracts and frozen epoch manifests consistent with it; accepted task specifications; implementation. A later timestamp alone does not confer authority. An amendment must name the requirements changed, its reason, impact, migration, tests, and effective boundary.

The build agent may resolve ordinary implementation details within these constraints. It may not select scientific thresholds, widen permissions, invent legacy semantics, activate production, buy services, enable live trading, or silently relax a failed gate. Owner approval cannot turn an invalid model, incomplete proof, or unavailable capability into a passing machine gate.

Key corrections made in this revision:

| Gap in the supplied specification | Governing correction |
| --- | --- |
| Most canonical tasks lack complete dependencies or gates | Every task has an immediate predecessor, explicit technical prerequisites, deliverables, hostile checks, and an acceptance receipt. |
| QC2-011 requires prediction and outcome authorities that do not yet exist | It becomes a bounded real acquisition/evidence slice; complete live forward lineage is mandatory at QC2-086. No temporary production predictor. |
| Calendar, ingestion, universe, and snapshot definitions form a circular dependency | Split the candidate instrument census, acquired data bundle, eligibility manifest, and final snapshot into distinct objects. |
| Readiness is checked before inputs exist | Separate infrastructure preflight, snapshot readiness, prediction readiness, new-entry readiness, exit readiness, and research readiness. |
| Champion is pinned late in the daily sequence | Bind the complete scientific authority before feature/scoring work; later changes affect future runs only. |
| A session can be declared nonqualifying after research or outcomes are observed | Record all scheduled attempts; qualification is sealed by a fixed deadline using only prospective integrity facts. |
| `KNOWN_AT` could be backdated during historical reconstruction | Separate actual observation time, historical availability assumptions, and actual artifact creation time. |
| Model, preprocessing, calibration, and memory availability are underdefined | All learned dependencies have transitive training and learning cutoffs; retrospective artifacts never masquerade as forward artifacts. |
| Adjusted data, ticker reuse, and delistings can silently alter history | Stable instrument identities, point-in-time corporate actions, raw receipts, versioned adjustments, and explicit unresolved outcomes. |
| Daily bars are treated as an executable intraday path | Daily labels measure excursions; execution benchmarks are proxies; ambiguous stop/target paths cannot receive favorable assumed ordering. |
| Full-universe statistics can drop difficult or missing rows | Preserve candidate, eligible, scored, unscorable, and outcome denominators separately; publish missingness bounds. |
| Hash chaining is described as detecting all tampering | Define the attacker model, external checkpoint requirement, rollback detection, and limitations against privileged administrators. |
| Three broad database roles cannot enforce all declared authorities | Use narrow writer roles, restricted mutation procedures, separate privileged migration credentials, and runtime isolation. |
| Database state and evidence can diverge during a crash | Commit each authoritative mutation and its evidence record in one transaction; publish external work through durable outboxes. |
| A timed-out broker request can be submitted twice | Persist intent and attempt first; represent unknown submission state and reconcile by stable broker identifiers before retrying. |
| A general execution halt can block protective exits | Separate new exposure, cancellation, and risk-reducing actions with independently evaluated prerequisites. |
| Signature possession is treated as model trust | Verify provenance and safe artifact format independently; isolate deserialization; sign the final manifest, not a mutable package. |
| Promotion and owner identity tasks are ordered inconsistently | Earlier tasks implement ports and fixture proofs; real approval is disabled until enrollment, identity, and end-to-end security gates pass. |
| Ninety sessions is treated as sufficient statistical evidence | Ninety is a collection target; event counts, dependence, power, missingness, and elapsed-window limits determine closure. |
| Learning-policy value is inferred from whichever model won | Distinguish fixed-model performance, prospective adaptive-policy performance, and descriptive tenure comparisons. |
| Everything numerical is deferred as empirical | Separate architectural constants, owner risk policy, measured provider facts, engineering limits, and empirically selected parameters. |
| Nightly research and deployment have no resource contract | Require durable scheduling, storage, bounded jobs, budget ceilings, restart fencing, and a demonstrated hosting capability. |

## 1. Mission, scope, and success hierarchy

QuantraCore Apex Gen 2 is a private, single-owner, autonomous runner-intelligence and paper-trading system. Its central question is whether equities with exceptional future expansion can be identified before the measured expansion, with predictions preserved before outcomes and improvement demonstrated through controlled model competition.

Success is assessed in this order: scientific integrity; predictive discrimination and calibration; prospective learning effectiveness; frozen-strategy paper performance; eventual paid-data uplift. Positive P&L cannot cure leakage, missing provenance, denominator manipulation, or retrospective prediction creation.

Initial non-goals include multi-tenancy, billing, public APIs, investor dashboards, social feeds, news intelligence, discretionary mobile trading, a desktop terminal, live capital, options, futures, crypto, and intraday F0 features. No dependency on Project LEE, CIL, CerbaSeal, or another Lamont Labs system is required. Such integration would need a separately approved amendment and cannot become a hidden prerequisite.

The system must be useful when the broker is unavailable: trustworthy prediction collection may continue. Research must be useful when promotion is unavailable: candidates may accumulate. Android downtime must not erase state or create a second authority.

## 2. Non-negotiable invariants

Each invariant receives an automated enforcement test and a named owning module.

| ID | Invariant |
| --- | --- |
| INV-001 | No live broker endpoint, credential path, adapter, mode switch, or order route exists. |
| INV-002 | Only Execution Authority can cause a broker mutation, including orders, cancel, and replace. |
| INV-003 | There is one canonical operating ranking per epoch and scheduled prediction session. |
| INV-004 | Every canonical prediction refers to immutable, complete scientific dependencies. |
| INV-005 | A sealed scientific payload is never edited, resealed in place, or overwritten. |
| INV-006 | Every accepted input obeys its applicable availability cutoff, including learned dependencies. |
| INV-007 | Future labels cannot enter training, feature transforms, retrieval memories, or policy tuning prematurely. |
| INV-008 | Ground Truth does not import model, score, ranking, or strategy logic. |
| INV-009 | Safety state never raises a probability or QuantraScore. |
| INV-010 | Broker availability never changes scientific eligibility or ranking. |
| INV-011 | Research cannot mutate production authority, predictions, outcomes, or orders. |
| INV-012 | Owner requests pass machine gates; approval is necessary where specified and never sufficient by itself. |
| INV-013 | One operating Champion pointer exists per active epoch; the fixed Reference role is immutable. |
| INV-014 | Every scheduled prediction opportunity is accounted for, including a scheduler that failed to start. |
| INV-015 | Qualification never depends on realized future returns or a preferred model winning. |
| INV-016 | Unknown data or action state remains unknown; it is not converted into a negative label or successful action. |
| INV-017 | Replaying a sealed snapshot does not require a provider, broker, or current mutable database state. |
| INV-018 | Every authoritative mutation is atomic with its evidence record and recoverable after restart. |
| INV-019 | A stale worker cannot commit using an expired lease or generation. |
| INV-020 | No authority silently changes feed, universe, labels, feature definitions, score, strategy, or governed learned-memory dependencies within an epoch. |
| INV-021 | A restored installation cannot resume orders until reconciliation and identity checks pass. |
| INV-022 | A task cannot pass on mocked evidence when its gate requires real data or a real device. |
| INV-023 | Shared entity data cannot leak across development, test, research, and production credentials or storage. |
| INV-024 | No report claims a broader market, time, data feed, or execution validity than its evidence supports. |

## 3. Physical architecture and deployment boundary

Use one monorepo with a modular Python backend, PostgreSQL authority store, immutable artifact storage, and Android client. These are logical authorities, not a requirement to deploy dozens of microservices. A small number of separately permissioned processes is preferred:

- Core scientific worker: acquisition, snapshots, features, protocols, inference, predictions, ground truth, validation.
- Execution worker: paper broker credentials and order outbox, with no model-training capability.
- ApexLab worker: research data and candidate artifacts, no production mutation or broker credentials.
- Owner API: authenticated read projections and narrow command submission; no arbitrary SQL, code execution, or direct broker calls.
- Promotion verifier/committer: limited signing and transition functions, inaccessible to trainer credentials.

Runtime separation must be real. If the hosting environment cannot isolate credentials or enforce these boundaries, the corresponding security claim is not met. Separate deployments or an isolated worker environment are then required before activation. Shared source files are acceptable; shared all-powerful runtime credentials are not.

PostgreSQL is the canonical transaction system. Local deployment disks and process memory are caches. Long-lived objects, datasets, model artifacts, raw receipts, backups, and sealed reports must survive redeployment independently. Artifact writes use staging, full content verification, durable storage acknowledgment, then a database reference. Unreferenced staged artifacts may be collected after the retention policy permits; a committed reference to a missing artifact is an integrity failure.

Use PostgreSQL-backed job and outbox tables initially; do not add Redis, Kafka, Kubernetes, or another scheduler solely by preference. Select exact Python, PostgreSQL, package, Android SDK, JVM, and build-tool versions at bootstrap from supported versions the environment can run. Pin them and record hashes. No floating `latest` dependencies.

The deployment capability manifest must prove scheduling during idle periods, persistent database/storage access, outbound Alpaca access, secrets isolation, maximum job runtime, restart behavior, concurrency limits, storage quotas, and backup support. A development preview process is not a demonstrated unattended runtime. No hosting capability is assumed from the name Replit.

Required repository boundaries are `packages/contracts`, `packages/science`, `packages/core`, `packages/execution`, `packages/apexlab`, `packages/owner_api`, `packages/promotion`, `apps/android`, `migrations`, `tests`, `docs`, and `tools`. Equivalent packaging layouts require a recorded implementation decision preserving import and permission boundaries. Generated data, credentials, model binaries, and market history are not checked into source control.

## 4. Authorities and exclusive mutation ownership

| Authority | Sole canonical write responsibility | Forbidden responsibility |
| --- | --- | --- |
| Calendar | Session calendars, calendar revisions, operational phase | Inventing missing price data |
| Instrument/Universe | Stable security identity, symbol history, classification, candidate and eligibility manifests | Using future survival or broker buying power for eligibility |
| Market Data | Requests, raw receipts, normalized bundles, quarantines, market snapshots/revisions | Training, scoring, broker mutation |
| Feature | Feature definitions, dependency manifests, deterministic feature snapshots | Reading labels or future memories |
| Runner Protocol | Protocol lineage, versioned pure evaluations | Permission to execute or alter safety |
| Inference | Exact model loading and head outputs | Fit, retrain, promote, select a different model |
| QuantraScore | Versioned deterministic synthesis | Producing an undocumented probability |
| Prediction | Run bindings, row outcomes, complete ranks, prediction seals | Selecting a later successful retry |
| Label | Definitions and maturity rules | Choosing definitions after viewing qualification outcomes |
| Ground Truth | Independent outcome calculations and revisions | Asking the model whether it was correct |
| Validation | Epoch protocol, scheduled-attempt accounting, metrics, final decision | Training or silently repairing history |
| Safety | Action-specific readiness and blocking decisions | Bullish scoring or alpha generation |
| Strategy | Frozen interpretation of predictions into proposed exposure/actions | Modifying model evidence |
| Execution | Intent acceptance, submissions, cancellations, fills, positions, reconciliation | Discretionary ranking or live trading |
| Evidence | Append-only event and checkpoint integrity | Treating logging success as scientific success |
| Configuration | Versioned policy references and effective boundaries | Duplicated writable settings |
| Model Registry | Immutable artifacts and lifecycle facts | Training or self-certifying a candidate |
| Promotion | Eligibility, approvals, atomic authority transitions | Overriding a failed verifier |
| Identity | Single owner, devices, keys, sessions, enrollment/revocation | Discretionary orders |
| Alert | Severity, delivery attempts, acknowledgments | Treating acknowledgment as remediation |
| ApexLab | Datasets, experiments, genomes, decoys, research reports | Production authority or authoritative outcomes |

Ground Truth owns RunnerEvent detection; ApexLab consumes those events to build research memories. The label registry defines meaning, while Ground Truth applies the meaning. The Model Registry stores lifecycle facts, while Promotion owns the authoritative Champion pointer transition. Validation owns epoch activation after verifying an exact owner activation decision and the activation audit. These divisions eliminate overlapping writers.

Required database schemas are `calendar`, `instrument`, `market`, `features`, `runner_protocol`, `safety_protocol`, `prediction`, `label`, `outcome`, `validation`, `model`, `promotion`, `research`, `execution`, `evidence`, `owner`, `config`, `jobs`, and `alert`.

Each writer uses a separate non-owner, non-superuser role or a narrowly scoped equivalent. No runtime role has `BYPASSRLS`, schema ownership, DDL, arbitrary role switching, or unrestricted execution of security-definer procedures. Migration credentials are offline from application processes. SQL grants and typed stored operations, not naming conventions, enforce authority. RLS may supplement grants; it does not replace them. PostgreSQL explicitly permits privileged roles and ordinarily table owners to bypass RLS [S6].

Research receives read-only, cutoff-filtered scientific exports and its own writes. Owner API can enqueue approved command types and read projections; it cannot update Champion or execution tables. Identity administration uses a separate narrow endpoint and role. Artifact ACLs must match database grants; filesystem access must not defeat the database boundary.

## 5. Configuration, unknowns, budgets, and change classes

Configuration domains are secrets; immutable system policy; epoch scientific policy; frozen strategy policy; research search spaces/budgets; deployment engineering limits; owner identity. The same concept has exactly one writable authority. A manifest references a configuration hash instead of copying an editable value.

Classify unresolved decisions as follows:

| Class | Examples | Resolution |
| --- | --- | --- |
| ARCHITECTURAL_CONSTANT | Paper only, one owner, primary 5-session horizon, rank tie order | Defined here; change requires constitutional review |
| OWNER_POLICY_REQUIRED | Paper capital, maximum exposures, permitted costs, recovery method, default halt behavior | Owner chooses and signs; performance optimization cannot widen limits |
| CAPABILITY_MEASUREMENT_REQUIRED | Feed entitlement, history depth, calendar reach, API limits, hosting durability | Measure using the actual deployment/account |
| EMPIRICAL_CALIBRATION_REQUIRED | Label thresholds, feature subset, protocol parameters, score coefficients | Train/development-only experiments under a recorded plan |
| ENGINEERING_LIMIT_REQUIRED | Timeout, retry budget, clock tolerance, maximum artifact size | Justify from measured resource and deadline constraints; record and test |

A missing value is stored as a typed unresolved decision with reason, affected tasks, responsible authority, evidence needed, and activation consequence. It is never a blank string, magic zero, guessed number, or application fallback. Tests may use conspicuously named fixture policies; fixture identities are cryptographically and schematically forbidden in production manifests.

The empirical ledger must cover universe thresholds; Expansion/Monster thresholds; lookbacks and subset selection; Runner Protocol thresholds and active set; score parameters; optional-head inclusion; missingness eligibility; strategy values within owner caps; promotion minimum samples and effect sizes; Shadow duration; statistical event count, power, coverage, dependence settings, and maximum elapsed collection/maturation windows. Experimental thresholds cannot be selected by inspecting the locked holdout or F0 final outcome.

Engineering ceilings must bound requests per job, retry count and elapsed time, training CPU/memory/runtime, artifact size, experiment count, storage growth, report size, and maximum concurrent researchers. Zero authorized paid budget means no paid subscription, resource purchase, or upgrade. Exhaustion pauses research first, preserves evidence, and does not silently discard failed experiments. `RESEARCH_DISABLED` is a valid operating configuration; production cannot depend on nightly training completing.

Change classes: C0 presentation only; C1 operational implementation with proven scientific equivalence; C2 scientific identity change; C3 authority/security change; C4 emergency containment. C2 changes start a new epoch unless an exact model transition is permitted by an already frozen adaptive promotion policy. Bug fixes that alter scientific values are C2 even if called corrections. C4 may immediately reduce permissions; it cannot authorize new exposure or retrospectively repair an experiment. Every release records class, changed contracts, proofs, rollback path, and affected epochs.

## 6. Temporal truth and the leakage firewall

Use UTC for stored instants and America/New_York for exchange-session interpretation. Store `session_id` explicitly; never derive it by truncating an arbitrary UTC timestamp. Calendar versions record holidays, exceptional closures, early closes, and revisions. Clock evaluation uses an observed trusted-time comparison, measured uncertainty, wall clock, and monotonic elapsed time. A backward jump cannot create a fresh approval or prediction window.

Required temporal fields have different meanings:

| Field | Meaning |
| --- | --- |
| `event_time` / `event_interval` | When the underlying market event occurred |
| `provider_published_at` | Provider assertion if actually supplied; nullable, never invented |
| `observed_at` | When this deployment received the raw observation |
| `ingested_at` | When it durably committed the observation |
| `known_at` | Earliest evidenced usable time within this installation; never earlier than actual receipt for forward records |
| `available_for_learning_at` | Time all required outcomes, reviews, transformations, and embargo conditions permit learning |
| `decision_cutoff` | Latest allowed knowledge for a prediction run |
| `artifact_created_at` / `sealed_at` | Actual artifact creation and sealing instants |
| `historical_assumed_available_at` | Explicit retrospective assumption, allowed only for reconstructed evidence |

An input is eligible only if both its event boundary and its knowledge availability satisfy the run contract. A genome can describe an old pre-event date while remaining unavailable until its future label and curation mature. Its `available_for_learning_at` is the maximum of label maturity, source availability, review completion, derived-index creation, and applicable embargo release. Similarity indexes must bind their member set and a cutoff; filtering only after retrieval is insufficient because future membership can change neighbors and learned geometry.

Every learned artifact exposes a transitive dependency closure: training rows, labels, preprocessing, feature selection, encoders, calibrators, similarity embeddings/indexes, ensemble weights, score fits, and policy optimization. The latest learning-availability time of any dependency cannot exceed the declared training cutoff. A forward model must also have been actually produced, qualified, and made eligible before its bound prediction run. A model trained tonight cannot claim it predicted yesterday.

Historical replay is a different mode. It may build a model today with a simulated historical training cutoff, but must use only the reconstructed data permitted at that simulated time and label its results HISTORICAL_RECONSTRUCTED. Actual receipt and creation timestamps remain today. Provider symbol `asof` parameters are not proof of historical data availability or historical corporate-action knowledge.

Cross-sectional transforms at a cutoff may use only that session's already eligible, available peers and a frozen deterministic rule. Population scalers, imputers, PCA, feature selection, model calibration, and learned transforms are fitted within each training fold. A test fold may only receive transformation. This is an explicit application of established leakage controls [S7].

The temporal firewall is an API and a storage-permission boundary. Research cannot use unconstrained joins against future outcome tables when producing a simulated past feature view. Unit tests cover direct future fields; integration tests cover indirect access through cached datasets, revised bars, metadata, memory indexes, aliases, normalizers, and restored artifacts.

## 7. Evidence classes and permissible claims

Required classes are SYNTHETIC_FIXTURE, HISTORICAL_RECONSTRUCTED, FORWARD_OPERATIONAL, and FORWARD_SEALED. FORWARD_OPERATIONAL means genuine prospective collection without all formal epoch/anchoring requirements. Only FORWARD_SEALED observations meeting the epoch contract qualify as official F0 evidence.

Historical datasets separately declare universe fidelity: PIT_VERIFIED, SURVIVORSHIP_LIMITED, or UNKNOWN. These are not interchangeable. A current asset list joined to old bars is survivorship-limited even when each bar has a historical timestamp. Reconstructed qualification may be used to select a bootstrap model under a disclosed restricted claim; it cannot establish historical all-market capture. If unavailable delisted securities or historical classifications make the proposed qualification claim untestable, narrow the claim prospectively and record owner acceptance, or mark the task BLOCKED. Never fabricate missing universe membership.

Forward evidence establishes what this installation captured and sealed under its declared controls. It does not prove that a privileged administrator could never have interfered, nor that paper fills were executable live. Reports must state evidence class, feed, universe fidelity, anchoring assurance, missingness, model/epoch versions, and known limitations.

## 8. F0 provider and actual capability measurement

Alpaca is the initial canonical market-data provider and sole paper broker. Market-data access and paper-trading access are separate capabilities. Pin `provider`, `feed`, `adjustment`, symbol-mapping policy, currency, timeframe, calendar version, and bar-semantics version explicitly on every request. Provider defaults are forbidden in canonical requests.

Candidate F0 feeds are delayed historical SIP and IEX. The initial preference is delayed SIP if the actual account proves access and adequate coverage at the required cutoff; otherwise IEX may be selected explicitly before activation. This is initial regime selection, not runtime fallback. After selection, loss of access means a failed attempt or hold. Changing feeds requires a new regime and epoch. IEX volume must be described as IEX volume, not consolidated market volume.

Current Alpaca documentation distinguishes a single-exchange IEX feed from consolidated SIP and describes historical SIP access restrictions around recent data. These descriptions do not certify this account. The probe must measure entitlement, errors, coverage, and timing rather than hard-code free access, a start year, rate limit, or supported symbol count [S1, S2].

The DataCapabilityManifest records deployment/account fingerprint without secrets; requested capability; observed result; request/response evidence; earliest tested available session; pagination behavior; effective delay; feed identity; rate-limit headers; retry behavior; missing-symbol behavior; symbol rename handling; adjustment behavior; corporate-action availability; asset classification coverage; calendar availability; paper account identity; supported order/status operations; tested time; and expiration/revalidation rules.

The probe is read-only by default. Any real paper order test requires a separately named sandbox execution-test authorization and dedicated paper account. It must not probe live endpoints, upgrade data plans, or place exploratory orders in the epoch account. Credential absence produces BLOCKED, never PASS on fixtures.

## 9. Bar semantics, acquisition, and corporate actions

The canonical F0 features consume completed daily OHLCV only. Calendar, instrument identity, corporate actions, and provenance are required control metadata, not optional predictive features. Minute bars, quotes, news, sentiment, historical float estimates, and sector labels are excluded from F0 intelligence. An execution fill stream is operational evidence and cannot be fed back as a contemporaneous predictive feature.

Do not assume the provider's daily volume contains only regular-session trades or that its daily open is an official auction execution. Alpaca documents condition-dependent bar updates; extended-hours trade conditions can affect daily volume without affecting daily OHLC [S1]. The BarSemanticsManifest must record the tested interval, timezone, field meanings, revision behavior, and finalization rule. The scheduling cutoff must account for the last interval affecting any included field, not merely the exchange regular close. If the expected completed volume interval has not ended, the bar is not complete for this regime.

Raw API response bytes and sanitized request manifests are preserved before normalization. Pagination ends only when a verified terminal token is reached; a short page or first symbol is not completeness. Detect repeated tokens, duplicate pages, conflicting duplicate bars, missing requested instruments, inconsistent feeds, and truncated responses. Alpaca documents symbol-first sorting and a page limit across all requested symbols [S2]. Retry only within bounded request and session deadlines; retries use the same pinned feed and declared cutoff.

Validate finite positive OHLC, nonnegative volume, high/low ordering, open and close within the bar's range, session membership, timestamp precision, unique instrument/session/feed keys, currency, and requested coverage. Zero or missing bars are not synthesized. Suspicious spikes are quarantined for an explicit rule-based reason, not removed because they would make a model look wrong. Extreme genuine runners must survive validation. Keep anomaly observations even when an instrument is ineligible.

Preserve unadjusted raw bars. The normalization layer produces a documented, versioned split-consistent view with point-in-time action availability for features. A forward split factor changes price and volume consistently; multiplying or dividing prices without matching volume is forbidden. Historical inputs may not use a future split to make a past minimum-price screen pass. Dividends are not silently converted into price-return labels.

For outcomes spanning splits, transform each future raw price onto the prediction reference share basis using only verified applicable action terms. A two-for-one split alone produces zero economic price expansion, not a collapse or runner. Test reverse splits, multiple splits, same-day actions, symbol changes, cash mergers, stock mergers, spin-offs, distributions, and delistings. Unsupported transformations produce CORPORATE_ACTION_REVIEW rather than guessed returns. Future action records may be used by Ground Truth to resolve the future, but never retroactively by that prediction's Feature Snapshot.

Alpaca warns that corporate-action availability can be delayed [S3]. Absence of an action in one response is not proof no action happened. Store observed versions, effective dates, processing dates where provided, and uncertainty. An action conflict may hold the affected instrument without changing an already sealed prediction. After resolution, append an OutcomeRevision and report both the originally available and corrected views under the frozen revision policy.

## 10. Instrument identity, universe, and denominators

An instrument has a stable internal identifier independent of ticker text. Symbol assignments carry exchange, currency, effective interval, known-at interval, source evidence, and mapping confidence. Ticker reuse must not join unrelated companies; uncertain lineage is blocked. Provider asset IDs are cross-references, not automatically a complete historical identity service.

Initial eligibility is verified US-listed common equity with USD price data under the chosen regime. ETFs, ETNs, closed-end funds, preferreds, warrants, rights, units, options, futures, crypto, OTC, and unknown classifications are excluded. ADRs, REIT common shares, and other edge classifications require explicit inclusion policy; the initial conservative rule is exclude ambiguous types until classification is verified. `us_equity` alone is not proof that an instrument is common stock. Name suffix heuristics can generate review candidates but cannot assert verified classification without supporting evidence.

Each session preserves five sets: CANDIDATE_CENSUS; SCIENTIFIC_ELIGIBLE; SCORED; UNSCORABLE; EXECUTION_ELIGIBLE. Prediction eligibility does not require the paper account to permit trading. Execution eligibility may be narrower and must never rewrite scientific ranks.

Construction order is fixed:

1. Calendar supplies the target session and acquisition/decision deadlines.
2. Universe Authority freezes the candidate census from metadata available by cutoff.
3. Market Data acquires an immutable DataBundle for that census and required history.
4. Universe Authority applies the frozen scientific rules to the census and DataBundle.
5. Market Data seals a MarketSnapshot referencing the census, bundle, and final UniverseManifest.
6. Prediction records one disposition for every scientifically eligible instrument.

All artifacts are acyclic: the DataBundle does not reference the final snapshot that references it. A snapshot retains the exact warm-up history needed for replay, not just one day's bars. Warm-up data acquired before F0 may remain HISTORICAL_RECONSTRUCTED input history even when a newly sealed prediction is prospective; this provenance must be visible.

Universe calibration determines price, dollar volume, volume, available history, listing-age rules, and missingness restrictions before activation. Actual listing age and observed bar-history length are different fields. Unknown listing date cannot be replaced by the earliest returned bar without labeling that approximation and excluding it from rules requiring verified listing age.

Publish counts and reason distributions at each boundary. Every exclusion is timestamped and reason-coded. A failed model evaluation leaves a visible UNSCORABLE row; it does not disappear from the universe. Report both conditional predictive metrics on scored rows and coverage over the declared eligible/candidate populations. Observatory recall is bounded by the observatory census and data coverage; it is not all-market recall unless that scope is verified.

## 11. Snapshot sealing and revision policy

A MarketSnapshot includes snapshot ID and content hash; evidence class; session/calendar; census and universe hashes; provider/feed; sanitized request manifest; raw receipt hashes; normalized history inventory; adjustment/action manifest; bar semantics; observation and decision cutoffs; row and instrument counts; coverage; exclusions; anomalies; creation/seal times; and registry/configuration references needed to interpret it.

Sealing checks every referenced artifact's bytes, size, content hash, schema, and durable availability. A database row containing a hash is not proof that the referenced object exists. The complete dependency inventory is stored in the snapshot manifest and later retained transitively.

A MarketSnapshotRevision is a new object referencing an earlier snapshot, changed observations, discovery time, reason, source evidence, and new content hash. It cannot change the earlier snapshot's scientific identity. Canonical forward predictions remain bound to their original snapshot. Corrected-data replays are a separately named sensitivity analysis, not replacements for the official predictions.

Prediction-input revisions received after the decision deadline do not rescue that session. Outcome corrections follow a preregistered resolution/freeze window. Corrections after a final report create an amendment with impact analysis; they do not silently rewrite the final result or release previously unavailable learning data with an earlier timestamp.

## 12. Canonical contracts and serialization

All external and persisted domain objects use versioned, strict schemas. Unknown fields, enum values, coercions, nonfinite numbers, duplicate JSON keys, implicit timezones, and incompatible versions fail validation. Readers support only explicitly tested versions. A schema migration never mutates the bytes of a sealed historical payload.

Common object fields are schema name/version, UUIDv7 operational ID, content hash where content-addressed, evidence class, creation time, owning authority, source/dependency references, and environment namespace. IDs are not hashes; UUID order is not proof of causal order. Explicit event sequence and timestamps carry ordering semantics.

Canonical scientific JSON uses UTF-8, normalized Unicode, deterministic lexicographic object keys, preserved array order, explicit nulls only where defined, and a single whitespace/escaping convention. Scientific decimals are decimal strings without locale formatting or exponent ambiguity. Canonicalization is a tested versioned format, not casually called RFC-compliant. Raw provider bytes have a separate raw hash.

Prices/quantities remain exact decimal values at ingestion and execution. Continuous derived scientific values use a registered fixed precision per field; the initial serialization convention is 12 decimal places for probabilities/continuous model outputs and 6 for QuantraScore, round-half-even. These are engineering representation choices, not evidence of statistical precision. Negative zero becomes zero. Nonfinite or out-of-range values are errors, never clipped silently. Feature intermediate precision and conversion rules are specified separately in each implementation contract.

Ranking uses canonical score values, then canonical primary probability, then stable instrument ID ascending as the final tie-break. No database row order, ticker ordering after a rename, or unseeded randomness can break a tie. Quantization is applied before ranking and hashing; it cannot be changed to conceal a failed replay.

Artifact identity is SHA-256 over domain-separated canonical content. An artifact manifest lists each allowed relative path, length, media type, schema/version, and SHA-256; absolute paths, `..`, symlinks, hardlinks, duplicate paths, decompression bombs, and executable surprises are rejected. The signed manifest excludes its own detached signature to avoid recursive hashing. A separate transport/archive hash may be recorded but does not replace the signed inventory.

Required contract families are exhaustive at the boundary level:

| Family | Required objects |
| --- | --- |
| Time and operation | CalendarManifest, CalendarRevision, MarketSession, ClockAssessment, JobDefinition, JobLease, JobAttempt, OutboxMessage, ReadinessAssessment, DeploymentCapabilityManifest |
| Identity and market | Instrument, SymbolAssignment, InstrumentClassification, CorporateActionRecord, AdjustmentManifest, CandidateCensus, DailyBar, RawReceipt, RequestManifest, DataCapabilityManifest, BarSemanticsManifest, DataBundle, UniverseManifest, MarketSnapshot, MarketSnapshotRevision, QuarantineCase |
| Scientific definitions | FeatureDefinition, FeatureRegistry, FeatureSnapshot, RunnerProtocolDefinition, RunnerProtocolRegistry, RunnerProtocolResult, SafetyProtocolDefinition, SafetyProtocolResult, LabelDefinition, LabelRegistry, ScoreDefinition, ScoreManifest, BaselineManifest |
| Models and prediction | ModelManifest, ModelHeadDefinition, ModelHeadOutput, InferenceReceipt, PredictionRun, Prediction, ScientificPredictionPayload, PredictionSeal, RunDisposition, ShadowPredictionSet, ReplayRequest, ReplayReceipt |
| Outcomes and research | Outcome, OutcomeRevision, RunnerEvent, RunnerGenome, FailureGenome, MemoryIndexManifest, MatchedDecoySet, ReviewCase, DatasetManifest, DatasetRowLineage, SplitManifest, HoldoutAccessReceipt, Experiment, CandidateEvaluation, ChallengerEvaluation, DriftAssessment |
| Validation | ValidationEpoch, EpochManifest, ScheduledAttempt, ValidationSession, QualificationReceipt, MetricDefinition, MetricResult, StatisticalAnalysisPlan, ValidationReport, ReportAmendment |
| Execution | StrategyManifest, CapitalPolicy, PaperOrderIntent, IntentDecision, SubmissionAttempt, BrokerOrder, BrokerOrderEvent, Fill, FillCorrection, Position, CashLedgerEntry, Reservation, ReconciliationReport, ExecutionEpisode |
| Governance and owner | PromotionPolicy, PromotionBundleManifest, PromotionRequest, PromotionChallenge, PromotionDecision, PromotionReceipt, ChampionPointer, EpochActivationChallenge, EpochActivationDecision, EpochActivationReceipt, OwnerDevice, OwnerSession, EnrollmentChallenge, RecoveryEvent, OwnerCommand, OwnerCommandReceipt, Alert |
| Integrity and build | EvidenceEvent, Checkpoint, AnchorReceipt, ArtifactManifest, ArtifactDependency, BackupManifest, RestoreReceipt, ConfigurationManifest, UnknownDecision, ChangeRequest, ReferenceIntake, BuildTask, TaskAcceptanceReceipt |

At QC2-003 each object must have field types, units, required/optional rules, identity fields, foreign-key behavior, state transitions, writer role, immutable/mutable designation, and at least one valid and several invalid fixtures. This table is not permission to defer actual contracts until their consumers are implemented.

## 13. Feature Authority

A FeatureDefinition includes stable ID/version; mathematical equation; exact inputs and units; lookback; warm-up; time alignment; split treatment; normalization; missingness behavior; zero-denominator behavior; supported regime; dependency graph; implementation hash; and expected invariance properties. If a lookback is empirical, implement a parameterized definition and fixture values without activating an uncalibrated production choice.

Required research families are 1/2/3/5/10/20-session returns; momentum slope and acceleration; directional persistence; true range and ATR; normalized range; volatility expansion/compression and volatility-of-volatility; relative volume, volume acceleration/slope and accumulation; price-volume divergence; gaps; close-location value; body and wick proportions; rolling-high distance; breakout proximity/attempts/failure count; trend slope; reversal; exhaustion; and temporally legal runner/failure similarity.

Each FeatureSnapshot records one value or explicit missing reason for every required feature/instrument. It binds ordered feature columns, units/dtypes, transform artifacts, input hashes, registry, cutoff, code version, and environment. Missingness is not interchangeable with zero. An approved model may use a missingness indicator and a training-fitted imputer; otherwise a missing required feature makes that row UNSCORABLE. The same rule applies to all comparators needing that input.

Tests cover flat prices, zero-range candles, absent volume, IPO warm-up, sparse history, splits, reversed order, duplicate sessions, very large volumes, decimal precision, future metadata, and symbol continuity. Metamorphic tests verify expected scale invariance where the mathematical feature promises it. Derived features cannot make network calls or query mutable global state.

## 14. Labels and independent Ground Truth

The primary horizon is the next five exchange sessions after prediction session t. Secondary horizons are 1, 3, and 10 sessions. Session membership comes from the frozen calendar, never from the next N bars that happen to exist. A halt or missing bar does not extend the horizon.

Store three price references separately: the canonical provider daily close for prediction session t; the next-session provider daily-open benchmark; and actual paper fills. The second is named `NEXT_SESSION_DAILY_OPEN_PROXY` unless a verified source proves official auction semantics. It is a standardized comparison, not a promise that a strategy could fill at that price. No prediction may call the unknown next open an input.

For split-consistent prices H, L, C on the reference share basis, the scientific outcome at horizon h is:

`endpoint_return_h = C[t+h] / C[t] - 1`

`max_high_return_h = max(H[t+1] ... H[t+h]) / C[t] - 1`

`min_low_return_h = min(L[t+1] ... L[t+h]) / C[t] - 1`

`mfe_h = max(0, max_high_return_h)`

`mae_h = min(0, min_low_return_h)`

Preserve both unclamped extrema returns and conventionally signed/clamped MFE/MAE so a gap that never revisits the reference is not misrepresented. MAE is nonpositive; a positive loss-magnitude view has a separately named field. Returns use fractions, not ambiguous percentage units. Peak/trough fields include the actual price, exchange session, session offset, and earliest-session tie-break. Daily bars do not identify intraday timestamps.

Also calculate next-open-proxy endpoint return/MFE/MAE over sessions t+1 through t+h using `O[t+1]` as denominator, plus the opening-gap return `O[t+1] / C[t] - 1`. Keep these separate from close-referenced outcomes and actual fills. For example, a move from a prior close of 100 to next open 200 and future high 205 has 105% close-referenced expansion but only 2.5% expansion above the next-open proxy. The system must not present 105% as an available next-session entry opportunity.

Because sealing can occur after the prediction-session close and daily bars do not reveal the full overnight path, F0 cannot prove the exact share of a move remaining at the seal instant. Report when the prediction was sealed, the prior-close reference, next-open opportunity, opening-gap contribution and already-elevated pre-prediction momentum. Claims of exact intraday early detection or capture before most of an overnight move require F1 evidence. A large close-referenced excursion alone does not establish that stronger mission claim.

Expansion Runner at horizon h is a versioned threshold event on `max_high_return_h` plus any explicitly frozen persistence/drawdown conditions. Thresholds and extra conditions are chosen before qualification; adding a favorable persistence rule after F0 is forbidden. Session Monster is separately defined from each future session's previous split-consistent close to that session's high; also store open-to-high expansion and opening gap as distinct measurements. A session-level extreme event and a multi-session expansion are allowed to overlap but are not interchangeable targets.

Each label has an exact horizon and price reference. `Runner Probability` is the display alias for the primary five-session Expansion Runner probability; it is not a third undefined duplicate head. `Session Monster Probability` means at least one qualifying Session Monster in the specified horizon. Continuation, Failure, and Time-to-Expansion are unavailable until their own label definitions are frozen. Failure is not assumed to be one minus runner probability.

Outcome states are PENDING_MATURITY, RESOLVED, PARTIALLY_RESOLVABLE, UNRESOLVED_DATA, CORPORATE_ACTION_REVIEW, and CENSORED_TERMINAL_EVENT. State carries field-level validity and reason codes. A terminal event may be economically resolvable if verified cash consideration is available; otherwise it remains explicitly censored/unresolved. No arbitrary `OTHER` state may hide an unclassified failure. New reason/state definitions require schema review.

Full-horizon training labels are released only after all required horizon sessions, data-finalization conditions, corporate-action checks, and the label release transaction complete. Even an early threshold hit does not make a full-horizon training row available early. This keeps all target heads on a consistent maturity policy and prevents asymmetric early release of winners. Separate early-event research would require a different label contract.

Ground Truth has no dependency on Champion, score, rank, or paper trade existence. It resolves all eligible/scored rows and independently observable census events. Data corrections create versions; neither the trainer nor review writer may override authoritative outcomes.

## 15. Runner Protocols, safety protocols, and legacy lineage

Runner Protocols express testable hypotheses about price/volume structure. Safety protocols govern whether an action is permissible. They use separate namespaces, registries, result schemas, imports, and tests. A protocol named T34 in one source cannot be assumed to equal a similarly numbered safety check in another source.

Runner results are PASS, BLOCK, OBSERVE, UNKNOWN, and UNAVAILABLE. These describe the protocol's stated hypothesis, not broker authority. For example, BLOCK can mean adverse/trap evidence under a declared hypothesis; it does not itself authorize a trade veto outside the frozen score/strategy interpretation. Every result includes hypothesis, direction, evidence values, uncertainty/missingness, rule parameters, implementation hash, cutoff, and input references. UNKNOWN is indeterminate; UNAVAILABLE means the data regime cannot support the test. Neither becomes PASS or neutral numeric zero automatically.

Safety results are PASS, WARN, BLOCK, and UNKNOWN, scoped to an action such as PREDICT, NEW_ENTRY, CANCEL_ENTRY, EXIT_POSITION, PROMOTE, RELEASE_TRAINING_DATA, or RESTORE. Unknown required safety evidence blocks that action. Warnings are allowed only when the action policy explicitly says so; all such allowances are frozen and visible. A healthy broker, database, or evidence chain cannot increase bullish confidence.

Protocol functions receive immutable typed inputs and return immutable typed outputs. They cannot access network, wall-clock time, secrets, broker clients, label tables, arbitrary files, process-global mutable dictionaries, model training, or production writes. Static import checks are useful but insufficient: run untrusted/migrated code in an isolated worker with no network and read-only allowed inputs; test attempted side effects. Resource limits prevent a pure but unbounded computation from stopping the nightly run.

Reference Intake records repository identity, exact revision, file path/hash, relevant symbol/test, reason for inspection, source-supported meaning, useful concepts, conflicting behavior, licensing/provenance, and disposition: REUSE, ADAPT, TESTS_ONLY, REWRITE, or IGNORE. Reuse copies reviewed code into Gen 2 with its own tests and lineage; production never imports from an external legacy checkout. The legacy projects are always read-only.

The requested migration candidates remain P55; T34; T37; T38; T41; T42; T44; T57; T77; T78; T92; T102; T103; T104; T108; T109; and T110. These IDs are an inspection queue, not verified semantics or a requirement to activate them. T24/T25 ambiguity and the proposed T34 trap-evader identity remain SOURCE_VERIFICATION_REQUIRED until exact source evidence resolves them. Missing or conflicting sources must produce an explicit exclusion decision; do not invent code to make a lineage table look complete.

Every discovered legacy protocol receives an inventory disposition and regime status: RESEARCH, ACTIVE_F0, UNAVAILABLE_IN_F0, RETIRED, or SOURCE_UNRESOLVED. F0 activation requires zero unresolved dependencies in the ACTIVE_F0 set, not every historical protocol implemented. Empirical contribution requires ablation against models without that protocol using the same splits and budget. Protocol count is not evidence of intelligence.

## 16. Models, heads, inference, and QuantraScore

Required initial model-family comparisons are regularized linear/logistic models, Random Forest, Gradient Boosting, and XGBoost. Compare equivalent targets, fold boundaries, eligibility, search budgets, and evaluation rules. Linear regressors can serve excursion heads; logistic classifiers serve binary heads. A complex model does not win a tie solely because it is complex. A frozen tie rule should prefer the simpler qualified artifact within the declared performance tolerance.

Required production capability is a valid primary Expansion Runner probability and a canonical rank score. The interface also supports Session Monster probability; expected 1/3/5/10-session MFE; horizon-specific MAE; Continuation and Failure probability; and optional Time-to-Expansion. Optional head status is AVAILABLE, UNAVAILABLE_LABEL, UNAVAILABLE_MODEL, or INVALID. Do not return zero, a fabricated probability, or an empty successful object when a head is unavailable. All primary-required heads failing for one instrument produce UNSCORABLE; a missing optional head follows the frozen score's explicit missing-head policy.

Expected MFE is not a price target or guaranteed achievable return. Probability is tied to the exact label, horizon, universe, and feed. Confidence, uncertainty, probability, evidence quality, and operational readiness are separate fields. Do not manufacture a confidence percentage from a score. Prediction intervals require a declared calibrated method and coverage assessment; otherwise display uncertainty descriptively.

ModelManifest binds every binary and preprocessing artifact; safe format; algorithm/version; target and label hashes; Feature Registry and column order; protocol compatibility; training/validation/qualification windows; transitive learning cutoff; dataset/split hashes; search budget; seeds; hyperparameters; calibration artifact; package lock; CPU/runtime fingerprint; source revision; training/inference resource constraints; reports; and allowed environment profiles. Its learned-dependency root includes every production similarity index, genome membership inventory, learned embedding, imputer and calibrator. These are part of the governed model release, not mutable background services.

Do not load arbitrary pickle/joblib/cloudpickle artifacts into production. Such formats can execute code when deserialized [S8]. Use an allowlisted, reviewed data-oriented representation appropriate to the model, and validate shape, operators, node count, resource cost, and feature compatibility. Conversion formats still require sandboxed validation; a signature does not make executable content safe. If a model cannot be represented and replayed safely, it is ineligible rather than an exception to isolation.

Inference has no training or artifact discovery path. It loads the exact content-addressed artifact selected by the pinned pointer, checks the package/environment contract, evaluates a fixed probe set, and exposes its loaded hash/generation. All required inference results are deterministic within the qualified environment and canonical precision. Bit-identical output across arbitrary CPUs, BLAS versions, and libraries is not promised. Environment changes require replay qualification before use. Training reproducibility is recorded separately from inference reproducibility.

QuantraScore is a versioned 0–100 deterministic ranking synthesis. It may use approved heads, protocol evidence, documented uncertainty penalties, failure evidence, and evidence quality. It is not a calibrated probability. The primary probability remains separately stored. All coefficients, nonlinear transforms, clipping rules, missing-head handling, and rank tie rules are frozen before the epoch. Safety checks are prohibited inputs. Evidence quality cannot be based on whether the realized trade was profitable.

Score calibration and protocol choice are model-selection operations and belong inside the development/nested validation process. A change in score or protocol parameters is a scientific release change, not an ordinary model-only promotion. A proposed model that needs different features, score, labels, or protocols starts a new epoch after qualification.

## 17. Prediction authority, sealing, and canonical identity

Create one ScheduledAttempt per exchange session expected by the active epoch, even if no worker starts. The schedule is generated in advance and reconciled against elapsed calendar sessions at every restart. An absent process creates a MISSED_START fact rather than an invisible missing denominator.

Once a finalized snapshot is available, atomically create and bind the PredictionRun to the epoch; snapshot; census/universe; feature and protocol registries; label registry; score manifest; operating Champion artifact/generation; fixed Reference artifact; pre-eligible Shadows; baseline manifests; calendar; memory indexes; scientific code; and decision/seal deadlines. These bindings precede features and inference. A concurrent promotion cannot alter them.

Run states are CREATED, INPUTS_BOUND, FEATURES_COMPLETE, SCORED, RANKED, SEALED, and terminal ABORTED or FAILED_BEFORE_SEAL. Post-seal outcome progress is a separate projection: AWAITING_OUTCOMES, PARTIAL_OUTCOMES, OUTCOMES_COMPLETE. A sealed Prediction never transitions back into an editable scoring state. Post-seal integrity findings are appended as invalidation findings; the original bytes remain.

All eligible rows have either a deterministic rank and complete scientific payload or a reason-coded UNSCORABLE disposition. A run may qualify only if its frozen coverage and primary comparison rules allow the observed missingness. Rank is unique within its scored set. Instrument membership, tie-breaks, and denominators are reproducible. Save the full ranking, not only Top 1/5/10.

ScientificPredictionPayload contains session, reference kind/price, stable instrument identity, horizon/label references, canonical model heads, feature/protocol/score dependencies, rank, row disposition, learned-memory references, model hash, and regime/epoch identity. It excludes operational request IDs, replay time, job host, and tracing IDs. Include scientific software/environment identity where needed to interpret values; do not hide a model change behind an operational envelope.

PredictionSeal binds a deterministic ordered inventory of all rows, disposition counts, aggregate payload hash, run bindings, deadline, actual sealing time, and evidence/checkpoint references. The database enforces uniqueness for the official operating seal at `(epoch_id, session_id, OPERATING)`. Reference, baseline, and Shadow seals are explicitly different roles and cannot become competing official rankings.

Retries before sealing are bounded and recorded. They use the declared deterministic repair policy and cannot select whichever score looks best. After a canonical seal, any recomputation is a replay or diagnostic revision, never a replacement. A run sealed after the prospective deadline remains diagnostic. The decision deadline must precede the next regular session's opening and leave enough time for the declared evidence anchor; exact timing is frozen from measured latency and bar semantics.

## 18. Baselines and fair comparisons

Mandatory baselines are deterministic random; 1-, 5-, and 20-session momentum; relative volume; breakout proximity; a transparent composite; and the frozen F0 Reference Champion. Use the same eligible universe, input snapshot, information cutoff, row accounting, rank convention, and outcome registry. If a baseline cannot score a row, retain its missing disposition and report the intersection as a secondary view; do not silently shrink every method to a favorable common subset.

The random baseline ranks by a cryptographic digest of a preregistered seed, epoch, session, and stable instrument ID. Freeze a seed set for random-baseline uncertainty; selecting the luckiest seed is prohibited. Historical seed selection must not use qualification results.

Define relative-volume and breakout baseline lookbacks in the calibration manifest, then freeze them. The transparent composite is the equal-weight mean of cross-sectional percentile ranks of 1/5/20-session return, relative volume, and breakout proximity, with explicitly oriented signs. Percentile ties use average ranks; final score ties use stable instrument ID. No fitted weights are permitted for this baseline. It is the primary comparator unless an owner-approved pre-activation analysis plan names another single comparator and explains why.

Top 10 is the primary reporting K. Top 1, Top 5, decile, percentile, and other horizons are secondary. These K choices define reporting and capacity; they are not tuned after seeing F0. A session with fewer than ten scoreable primary-method rows cannot satisfy the primary top-10 comparison and follows the preregistered qualification rule. Do not relabel Top 3 as Top 10.

## 19. ApexLab research and memory

Runner Observatory scans the declared observable census independently of model ranking. It identifies versioned Expansion Runners, Session Monsters, near-runners, continuation, collapse, and extreme outliers only where their labels are defined. It records coverage failures and cannot discover events solely from winners the model already selected.

A RunnerGenome and FailureGenome hold pre-event structural evidence, contemporaneous predictions if they existed, resolved outcomes, provenance, curation version, and all temporal availability fields. Preserve absent predictions as absent; retrospective scoring belongs to a separate analysis field. Outcome-derived cluster names and embeddings cannot leak through a pre-event feature view.

Matched decoys are chosen from the same eligible risk set using pre-outcome matching variables and a frozen matching procedure. The eventual outcome defines positive/negative membership but cannot define similarity distance, favorable exclusion, or hindsight-derived matching features. Match within date/regime strata, record calipers and unmatched cases, and account for repeated use of the same decoy. Decoy oversampling changes prevalence: training weights and probability recalibration must reflect the target population. Evaluate calibration on the original distribution, not a balanced synthetic case-control set.

Missed Monster Review consumes a frozen event definition and rank/coverage rule. It separates low rank, unscorable, scientifically excluded, unobserved, and no scheduled prediction. False Monster Review distinguishes high-probability non-events, downside, timing misses, and data errors. Reviews are explanatory research records; they cannot rewrite labels or scores. Every material case is queued by deterministic rules, including inconvenient failures.

The Experiment Ledger is append-only and records hypothesis, preregistered search space, code/environment, data and split manifests, feature/label/protocol/score candidates, algorithm, random seeds, search budget, compute cost, intermediate access to evaluation data, results, rejection reason, and artifacts. Failed and interrupted trials count toward the search history. Deleting bad trials or renaming them as unpublished work is forbidden.

No LLM is required for F0 core calculations. If later used to draft research explanations, its output is untrusted commentary with model/version/provenance. It cannot change contracts, thresholds, outcomes, code, or production authority automatically. Free-form explanations never constitute a gate receipt.

## 20. Datasets, splitting, and qualification holdouts

DatasetManifest binds evidence class; universe fidelity; all snapshot/raw/action references; feature/label/protocol registries; memory cutoff; actual and simulated availability policy; row IDs; row-lineage hash; membership; time range; symbol count; missingness; revisions; split assignment; normalization; sampling/weights; and artifact hash. Rows are unique by declared instrument, session, horizon/target, and registry version. Duplicate source data cannot inflate sample counts.

The split unit is exchange-session time, not global row position. Required stages are chronological training; development/validation with walk-forward folds; and a locked final historical qualification interval. Every symbol from the same session stays in the same outer time partition. No random symbol-day split or pooled 80/20 split is permitted.

For a training row, the label's complete dependency interval and learning-availability time must precede the fold's training cutoff. Purge rows whose target interval crosses the validation/qualification boundary. Embargo is an explicit session-based gap in the SplitManifest justified by the largest target horizon and residual dependence policy. TimeSeriesSplit by itself is not proof of correct purge or label maturity. Expanding walk-forward fits may use earlier validation rows only after their labels are actually available at the later simulated time.

Preprocessing, feature selection, protocol/score tuning, hyperparameter search, probability calibration, and ensemble selection occur within permitted training/development folds. An external memory index is rebuilt from eligible historical knowledge for each simulated cutoff. Do not use a globally trained embedding, final genome library, or final imputation state for every historical fold.

Separate evaluator credentials expose a narrow qualification service. Trainers cannot read qualification labels, per-row errors, or qualification metrics during development. Selection logs record all information released. A qualification report can certify or reject the already nominated candidate; if it influences another model-selection attempt, that holdout is consumed. A new untouched later interval or forward Shadow window is needed. Repeatedly changing a threshold until the same holdout passes is prohibited.

Bootstrap competition must select its contender using development evidence before opening qualification. Qualification refusal, insufficient data, or failure remains recorded; it cannot be repaired by making the holdout part of training and still calling it held out. Research may later train on a consumed historical interval if provenance permits, but it cannot count that interval again as independent qualification.

## 21. Statistical analysis and F0 decision rules

F0 collects a target of 90 qualifying prediction sessions, followed by the maturity window for all required 10-session secondary outcomes and data-resolution deadlines. Ninety sessions does not mean 90 independent observations and does not guarantee enough rare runners. Freeze a maximum scheduled-session collection window and maximum maturation extension before activation. No open-ended continuation until the result turns positive.

The default primary estimand is the mean paired session-level difference in five-session Expansion Runner Precision@10 between the operating prediction policy and the transparent composite. Each qualifying session contributes equally, regardless of the number of listed instruments. In frozen mode this measures one model; in adaptive mode it measures the preregistered sequence-producing policy. It is not an estimate of a retrospectively selected best model.

For complete labels, `d_s = precision_at_10_operating_s - precision_at_10_composite_s`. The primary effect is the mean of `d_s`. Publish the absolute precisions, paired difference, event counts, confidence interval, eligible/scored counts, and missingness. A ratio/lift with zero baseline events is undefined, not infinity.

Missing outcomes retain unknown status. Compute worst/best-case metric bounds over unresolved selected labels; for comparison, derive a conservative lower difference by assigning unresolved operating-only outcomes no success and unresolved comparator-only outcomes success, respecting shared-row identity. This is a bound, not a fabricated negative label. A PASS must survive the preregistered adverse missingness assessment. Complete-case results alone cannot establish PASS when missingness could reverse the conclusion.

Dependence analysis uses entire session cross-sections and contiguous blocks of exchange sessions. It must preserve overlapping horizons, market-wide moves, repeat symbols, and event clusters. Calibrate block length and sensitivity ranges on development data, not F0 outcomes, with a lower bound reflecting the longest overlapping target used in that analysis. At least 10,000 deterministic seeded resamples are the initial computation policy; more resamples do not create more independent information. Validate the chosen interval procedure on simulated dependent data with known nulls and alternatives. If coverage or effective-block requirements fail, report INSUFFICIENT_EVIDENCE.

The frozen statistical plan specifies the exact bootstrap/interval implementation, alpha, practical minimum effect, minimum independent event clusters, minimum effective time blocks, coverage gates, abstention limits, family of confirmatory tests, missingness treatment, and stopping rule. Default primary alpha is 0.05 with a one-sided superiority claim. The practical effect and evidence minimums require pre-F0 justification and owner approval. Secondary metrics are descriptive unless prospectively designated in a multiplicity-adjusted family. No p-value fishing across heads, Ks, labels, horizons, model tenures, or post-hoc subsets.

Report sensitivity to event-episode deduplication and concentration by instrument/market period. Define episodes before outcome analysis, grouping overlapping qualifying windows of the same instrument according to a frozen rule. Show both symbol-day metrics and distinct event capture. Do not treat repeatedly predicting the same runner as dozens of independent successes. Leave-one-period and leave-one-dominant-instrument analyses are robustness diagnostics, not alternate routes to PASS.

Required secondary metrics are Recall@K; top-decile/top-percentile lift; Session Monster and Expansion Runner capture; missed-event rate; false-monster rate; Brier score; reliability/calibration diagrams; PR-AUC with prevalence; MFE/MAE rank relationships; next-open-proxy opportunity and opening-gap contribution; temporal stability; and coverage/reliability. PR-AUC implementation and tie handling are pinned. Calibration bins and confidence methodology are prespecified. ROC-AUC alone is insufficient for rare events.

Operational reports also cover every scheduled opportunity, including nonqualifying attempts and missed starts. Primary conditional predictive quality must be presented beside the operational qualification rate and reasons. A system that selectively misses volatile days cannot claim reliable deployment by only reporting the surviving sessions. Preregistered reliability gates may prevent an epoch PASS even when conditional precision is high.

Closure is computed by immutable rules:

- PASS: integrity valid, evidence-volume and operational gates satisfied, primary lower confidence bound above the frozen practical effect, required guardrails satisfied, and missingness cannot reverse the result.
- FAIL: a verified disqualifying integrity violation, or adequate valid evidence establishes failure of a frozen guardrail or places the primary upper bound at/below the required practical effect. Report the exact failed rule; do not equate failure to prove this system with proof that prediction is impossible.
- INSUFFICIENT_EVIDENCE: too few events/blocks, incomplete collection, material unresolved data, unvalidated uncertainty estimation, or a confidence interval that still straddles the decision boundary at the fixed end.

Evaluate integrity first. If integrity is invalid, scientific performance is labeled NOT_INTERPRETABLE within a FAIL epoch report; do not attach a meaningful-looking accuracy conclusion to corrupted evidence. An owner can acknowledge a result, not edit its classification.

Multiple-model and strategy search is itself a source of optimistic selection; the experiment ledger and consumed-holdout policy address that risk. Backtest-overfitting research supports treating the search process, not only the winning result, as part of the evidence [S9]. No statistical method here guarantees that future market behavior will match the observed epoch.

## 22. F0 modes, frozen policy, and learning claims

The initial default is `FROZEN_CHAMPION`: the operating Champion, complete learned-dependency root, score, feature definitions, protocols, labels, universe rules, and strategy stay fixed through F0. Rolling calculations still receive each new lawful market snapshot; learned memories/indexes cannot change underneath them. ApexLab continues research and seals Shadows. Eligible promotions may be prepared but take effect only in the next epoch. The Reference role points to the complete initial model release under an immutable role binding; identical computation can be reused with proof of identical dependencies.

An owner may instead explicitly select `PRE_REGISTERED_ADAPTIVE` before activation. In that mode, the epoch freezes the complete learning and promotion policy, eligible search space, training-data-release rule, evaluation timing, Shadow requirements, owner-decision window, cooldown, and permitted model-only transition boundaries. Only a verified model release, including its explicitly bound learned dependencies, may change inside the already frozen compatibility envelope. Newly matured ApexLab genomes do not automatically update production indexes. The Reference always retains its initial complete learned-dependency root. There is no mid-epoch switch between frozen and adaptive modes.

In adaptive mode, learning from already matured earlier F0 outcomes is permitted for future predictions. Each future prediction must predate its own outcomes, and the adaptive policy must be defined before collection. Prior F0 observations reused for training cannot also be presented as unseen validation of the resulting candidate. Its post-training Shadow window supplies fresh evidence.

Owner discretion to approve or withhold an eligible promotion is recorded as part of the deployed operating policy. Reports identify deviations from the preregistered decision rule; repeated discretionary winner selection undermines a confirmatory automated-learning claim. Unsafe or incompatible changes close/hold the epoch rather than silently widening the policy.

Report separately: operating-policy performance; frozen Reference performance; prospective paired Shadow performance; each model tenure; promotion decisions; research throughput; and paper results. Tenure comparisons cover different dates and are descriptive. Operating-minus-Reference differences alone do not prove a causal learning benefit independent of regime changes, owner discretion, and model-selection multiplicity. Learning effectiveness requires new prospective evidence on common windows after candidate freeze.

## 23. Full scientific replay

Replay starts from the original sealed snapshot and its complete dependency graph, including warm-up history, metadata/action versions, universe rules, learned indexes, registries, exact model, score, and numerical environment. It reconstructs eligibility, features, protocol outputs, heads, score, ordering, and row dispositions without network access or current mutable state.

Scientific payload bytes and aggregate seal inventory must match exactly under the qualified environment. Operational replay ID, actual execution time, and trace IDs may differ. Compare intermediate checkpoints to localize mismatches; a final rounded score match alone is insufficient. Replay must include unscorable and excluded dispositions, not only successful rows.

A replay that uses a different environment is a compatibility experiment until it passes qualification. A corrected-data replay has a distinct input identity and cannot be called an exact replay. Store ReplayReceipt with expected/actual hashes, counts, environment, first mismatch, duration, and verdict. Any mismatch blocks new scientific release/promotion and creates an integrity alert; it does not rewrite the original artifact.

## 24. Evidence Authority, atomicity, and proof limits

Evidence is a canonical transaction record, separate from logs, traces, metrics, and mobile cache. Every event includes installation/environment identity; stream and sequence; event type/schema; actor/service identity; authorized command/correlation; canonical payload hash; dependency hashes; previous event hash; current hash; wall-clock instant; and relevant monotonic/generation information. Sensitive values and secrets do not enter evidence payloads.

The sequence is allocated transactionally from a locked stream-head row, with a unique `(stream_id, sequence)` constraint. Do not use an unconstrained `MAX(sequence)+1`, timestamp sorting, or a nontransactional database sequence while asserting gap-free committed events. Concurrent appends serialize on the head; aborted transactions do not advance the committed head. Genesis and stream rotation are explicit signed/checkpointed events. Stream sharding is allowed only with a documented cross-stream checkpoint and causal reference design.

An authoritative domain mutation, evidence event, and necessary outbox item commit in the same PostgreSQL transaction through a restricted mutation procedure. The procedure derives actor/authority from authenticated execution context and verifies the specific domain operation; callers cannot supply another role's actor name to impersonate it. The application cannot append only a plausible evidence event while bypassing the domain write, or write the domain row without evidence. External storage/broker/push effects occur after commit through the outbox and produce durable completion/unknown-state events. This provides exactly-once logical transitions where constraints permit, not exactly-once network delivery.

The evidence verifier checks genesis, complete inventory, count, sequence continuity, previous/current hashes, canonical payload bytes, schema, referenced artifact availability, signature validity, and checkpoint continuity. It distinguishes FULL_VERIFIED, PARTIAL_SCAN, FAILED, and UNAVAILABLE. A truncated or timed-out scan is never PASS. Incremental checks must identify the verified checkpoint and newly verified range; periodic full verification remains required.

A hash chain stored entirely in the same mutable database cannot detect a privileged attacker who rewrites the whole chain and its expected head, or restores a coordinated older backup. State the trust boundary explicitly. Stronger proof requires independent checkpoints containing the committed stream heads, prediction seal inventories, counts, and artifact roots, with externally retained receipts and observed times outside the backend's write authority.

F0 official proof level is `INDEPENDENT_PREOUTCOME_ANCHORED`: the prediction checkpoint must be accepted before the next outcome session begins by a preapproved independent append-only or timestamped receipt system. Define its trust assumptions, signing/verifying keys, accepted time source, retention, and failure behavior in the epoch. A local signature or self-reported creation date is insufficient. The root checkpoint must be recoverable independently from the backend's database and backup credentials.

If only local chaining is available, the system can operate in FORWARD_OPERATIONAL collection while displaying `BACKEND_LOCAL_TAMPER_EVIDENT`; those sessions do not count toward the stronger F0 claim. Anchor unavailability does not erase the local seal, but official qualification waits only until the preregistered pre-outcome deadline. A late anchor cannot retroactively qualify a session. No paid service is purchased automatically to meet this gate.

Threat model includes buggy services, compromised research artifacts, stolen mobile sessions, stale workers, accidental administrator actions, storage corruption, malicious package contents, and a compromised runtime role. The design does not claim resistance to an owner/admin controlling every independent trust root. Security reports state which compromise combinations remain outside the assurance claim.

## 25. Durable jobs, concurrency, and restart recovery

Each job has a deterministic logical key, dependency references, state, attempt count, lease owner, lease expiry, monotonically increasing fencing generation, deadlines, resource budget, and checkpoint. Claim and renew under database transaction/conditional update. Every committing side effect rechecks the generation; a worker that slept through lease expiry cannot write merely because it still holds a Python object.

Use state machines for each job type: QUEUED, CLAIMED, RUNNING, WAITING_EXTERNAL, RETRYABLE_FAILURE, COMPLETED, TERMINAL_FAILURE, and CANCELLED. Retryability is a reason-code decision, not `except Exception: retry`. Schema errors, feed mismatch, integrity failure, model incompatibility, and invalid signatures do not get silent retries with weaker checks.

A crash after artifact upload but before database commit leaves an unreferenced staged object; a crash after commit resumes from the committed dependency. A crash after a broker request but before acknowledgment produces SUBMISSION_UNKNOWN. A crash after a model transition commit never invites a second transition based on stale expected Champion state. Outbox consumers are duplicate-tolerant and idempotent by logical operation ID.

Startup enters RECOVERY. Verify installation/database/environment identity; schema and release compatibility; last independent checkpoint; evidence head; pending jobs and leases; artifact inventories; active epoch and Champion; unfinished transitions; owner revocations; broker account and outstanding orders/positions if execution is enabled. Do not trade while startup is merely healthy enough to serve HTTP.

Backpressure priority is evidence and recovery, outcome durability, prediction deadlines, required execution maintenance, then research/report decoration. A late research job cannot starve the scientific run. Research has bounded schedule windows and concurrency. Metrics expose lag and queued work; no unbounded retry or growing in-memory queue is permitted.

## 26. Model lifecycle and promotion eligibility

Lifecycle is RESEARCH → CANDIDATE → CHALLENGER → SHADOW → PROMOTION_ELIGIBLE → CHAMPION → RETIRED, with REJECTED reachable before Champion. An immutable artifact is never overwritten while advancing state. RESEARCH/CANDIDATE activity cannot claim promotion eligibility solely from training metrics.

RESEARCH means a logged experiment. CANDIDATE means a frozen artifact with complete provenance. CHALLENGER means independent historical/retrospective gates passed. SHADOW means prospective evaluation is scheduled and sealed under the production input contract. PROMOTION_ELIGIBLE means all policy-specific historical, integrity, forward-volume, calibration, robustness, and compatibility gates have current passing receipts. CHAMPION means the atomic pointer transition actually committed. RETIRED means no future run binds it; historical runs retain it.

Shadow registration fixes artifact hash, eligibility time, target labels, required forward comparison window, and baseline/Champion comparators before its first scored session. All registered Shadow sessions and failures are counted, even when the model later performs badly. A candidate trained through a date cannot call predictions before its registration date forward Shadow evidence. Dropping losers does not erase their trials from the selection history.

Shadows cannot influence official ranks, paper strategy, safety thresholds, or owner slate ordering. They may appear in clearly labeled model-comparison views. An optional Shadow failure need not invalidate the operating session, but it counts against that Shadow's coverage and eligibility.

PromotionPolicy sets minimum prospective sessions and distinct events, uncertainty/effect requirements, calibration/false-positive bounds, coverage and stability limits, regression gates, maximum attempts, cooldown, permitted artifact type, allowed compatibility envelope, and permitted epoch modes. Thresholds are calibrated before evaluation and frozen; the packager cannot write its own passing policy.

## 27. Immutable bundles, exact approval, and atomic transition

The Promotion Bundle includes signed inventory; candidate/previous Champion hashes; target epoch/mode; all registry hashes; dataset/split/holdout receipts; leakage and replay reports; independent evaluation; Shadow seal/outcome references; policy/gate results; environment qualification; expiry; and transition intent. The bundle binds complete immutable report artifacts, not mutable URLs to dashboards.

Use separate signing identities for artifact packaging, independent evaluation, and owner approval. Ed25519 is the backend manifest-signature convention; the Android device uses its registered Keystore-supported P-256 signing key with a precisely defined SHA-256 signing envelope. Cryptographic algorithms and encodings are versioned; no ad hoc cryptography. A packager's signature proves origin/integrity, not successful independent evaluation.

The verifier checks every file before any model deserialization, resolves every dependency, verifies signer role/key validity, confirms artifact safety and tested environment, recalculates gate evidence where required, and confirms that reports match the bundle hashes. Revoked/unknown keys, extra archive entries, expired requests, incompatible labels, missing Shadow evidence, and stale current-Champion expectations fail closed.

A PromotionChallenge binds domain and action; request/bundle hash; candidate hash; expected current Champion hash/generation; epoch; registries; policy; nonce; issued/expiry times; device ID/key ID; and server environment. A signature from another action or environment is invalid. The nonce is cryptographically random, single-use, durably consumed in the transition transaction. Short challenge lifetime is an engineering policy fixed before enrollment acceptance.

The owner sees the exact candidate, current Champion, epoch effect, evidence summary, missing/failed gates, and expiry. Approve, hold, and reject are distinct signed decisions. Hold does not satisfy approval and does not extend expiry. Offline approvals are not queued for later submission; the app must obtain current state and a fresh challenge online.

Prepare and verify model bytes before the transition. At a safe future-run boundary, the committer locks the authoritative pointer/request; rechecks eligibility, epoch mode, revocation, expiration, expected generation, and no conflicting transition; consumes approval; writes the transition/evidence/outbox; and updates the pointer with compare-and-swap in one transaction. Initial bootstrap has an explicit `NO_CHAMPION` expected-state variant and cannot overwrite an existing pointer.

If the transaction fails, the previous pointer remains. If it commits but a worker cannot load the artifact, the new generation is authoritative but PREDICTION_READY is blocked until recovery; the worker cannot silently continue as the old Champion for newly created runs. Already bound runs retain their earlier generation. Model-load confirmation and pointer transition are distinguishable receipts.

Rollback is another authorized forward transition to a retained artifact with a new generation and fresh compatibility checks; it never rewinds evidence. Emergency containment may hold new runs immediately. Neither a rollback nor a server restart resets the epoch history or reuses an old approval.

## 28. Paper strategy and capital policy

Paper trading is a secondary experiment consuming sealed predictions. The initial scope is long-only US common equities, no short selling, leverage, options, fractional-share assumptions, discretionary entries, or pyramiding. Paper borrowing power exposed by the broker does not authorize margin. Use a dedicated paper account and an ExecutionEpisode whose opening cash, positions, orders, and account fingerprint are sealed.

CapitalPolicy is owner policy, not an optimized return parameter. It must define paper starting capital; maximum per-position cost and fraction; maximum gross exposure; cash reserve; maximum concurrent positions; daily loss/drawdown response; participation/liquidity constraints; and treatment of manual/external account activity. Missing caps keep paper execution disabled. Research may optimize only within signed caps and may never widen them.

StrategyManifest freezes selection K/rank behavior; entry session/window; deterministic allocation order; price cap; quantity rounding; stop/target/trailing behavior if used; maximum holding sessions; re-entry/cooldown; capital-reservation method; cancellation; gap/no-fill handling; and resolution of competing actions. Feature/model updates cannot silently change the strategy. Every action identifies which rule generated it.

Initial new-entry order type is a price-capped regular-session DAY buy limit, submitted within the measured next-session execution window; extended-hours flag is false. The cap is computed from sealed information under a calibrated strategy rule, never from a future opening price. Reserve `quantity × limit_price` plus any explicit cost buffer before submission. Whole-share quantity rounding cannot exceed a cap. Unsupported provider order semantics block the strategy rather than selecting another order type automatically.

This conservative entry rule prevents an unbounded market-order gap from defeating a hard pre-entry notional limit. It does not guarantee a fill. Report selection-to-intent, intent-to-submission, submission-to-fill, and fill/no-fill rates. Unfilled runner predictions remain scientific successes/failures under their labels; they are not removed because trading missed them.

Initial F0 uses simple orders, not bracket/OCO groups. Maintain share reservations across every pending exit so concurrently live sells cannot exceed reconciled owned shares. A replacement or time-based close waits for definitive cancellation/reconciliation of the prior protective sell before reusing those shares. This may delay an exit during uncertainty; the system must report that limitation rather than risk a duplicate sell. Alpaca documents that linked exits can both fill during fast conditions [S5], so bracket/OCO support requires a later explicit order-policy amendment and dedicated race testing. Do not assume the broker guarantees reduce-only semantics for equity orders.

Order prices must meet measured current broker precision/tick rules. Buy-limit rounding cannot raise the signed strategy cap. Reject unrepresentable quantities/prices rather than silently widening risk. Corporate actions can create fractional or unexpected position quantities even when entries use whole shares; preserve those quantities exactly, hold unsupported actions, and reconcile rather than rounding them out of existence.

Strategy decisions based on daily OHLC cannot assume target-before-stop. Backtests encountering both in one bar report INTRADAY_PATH_AMBIGUOUS and use a frozen conservative bound for strategy assessment; favorable ordering is prohibited. Broker fills determine paper P&L for actual paper orders. A daily-bar backtest, a daily-open proxy, and broker paper execution are three separate evidence series.

Alpaca paper execution has documented simulation limits, including omitted market impact/latency effects and fills not constrained by displayed NBBO quantity [S4]. Apply a separately reported liquidity/cost stress analysis where data permits. Never claim that a paper fill proves real liquidity or that quote-based paper fill prices share the selected F0 bar feed. Provider/feed provenance for scientific bars and broker simulation must remain distinct.

## 29. Paper Order Intents and execution state machines

PaperOrderIntent is immutable and includes intent ID; execution episode; paper account identity; action kind; source prediction/position; stable instrument and broker symbol mapping; side; whole-share quantity; limit/stop parameters where applicable; order type/TIF/session restriction; strategy/capital-policy hashes; predicted session; target execution session/window; expiry; reason; required safety assessment references; reservation; and stable idempotency/client-order key.

Action kinds are OPEN_LONG, REDUCE_LONG, CLOSE_LONG, CANCEL_PENDING_ENTRY, and explicitly supported REPLACE_ORDER. A SELL must reference sufficient reconciled owned shares and cannot open a short. Replacement links old/new orders and preserves worst-case reservation while both might be live. Quantity or price changes create a new intent revision chain, never alter an already transmitted intent.

Intent lifecycle is CREATED → VERIFIED → RESERVED → QUEUED_FOR_SUBMISSION → SUBMISSION_STARTED. Broker outcomes then branch to ACKNOWLEDGED, SUBMISSION_UNKNOWN, or REJECTED. An accepted order proceeds through PARTIALLY_FILLED, FILLED, CANCEL_REQUESTED, CANCELLED, EXPIRED, or REPLACED according to documented broker facts. Terminal local states cannot be inferred solely from a request timeout.

Before a network submission, commit SubmissionAttempt with the stable client-order key and exact normalized request hash. If the process crashes or times out after sending, reconcile by that key and account, inspect open/recent/closed orders and activity as required, and respect the provider's consistency window. A single not-found response is insufficient to prove the order never existed. Never invent a new key to force a retry while the previous submission is uncertain.

Provider client-order identifiers assist deduplication and retrieval but are not assumed to provide transactional exactly-once semantics. Probe and test the actual API behavior [S5]. The adapter must reject reuse of one key for different request bytes. The application enforces unique intent/key/request bindings locally and reconciles all ambiguous remote states before further exposure.

Recheck account identity, paper endpoint, intent expiry, current session, pause state, exposure reservation, symbol mapping, and action-specific readiness immediately before submission. A readiness assessment has a bounded lifetime and input generation. Passing five minutes ago is not permission under changed state. Competing intents reserve exposure under a transaction/lock so they cannot both spend the same cash.

Fills are append-only, deduplicated by provider event/fill identity, and reconciled against cumulative quantities. Out-of-order/duplicate events do not double-count exposure. Fill corrections and trade busts are separate adjustments referencing originals. Positions derive from the fill/cash ledger and verified corporate actions, with periodic comparison to broker state. Unknown broker positions, unexplained cash changes, manual orders, and account resets create a hold and a discrepancy report.

## 30. Safety, pauses, and readiness

Readiness is an action-specific assessment containing status, all gate results, reason codes, observed versions, freshness deadline, and authority. No global `core_ready` boolean exists.

| Readiness | Required evidence |
| --- | --- |
| INGESTION_PREFLIGHT | Correct installation, clock/calendar, pinned data capability, storage/evidence writes, bounded resources |
| SNAPSHOT_READY | Complete declared acquisition, validated semantics/provenance, known universe coverage, durable snapshot dependencies |
| PREDICTION_READY | Snapshot ready; exact compatible Champion/registries; legal temporal dependencies; qualified numerical environment; seal deadline reachable |
| NEW_ENTRY_READY | Qualified sealed prediction; paper identity/connectivity; fresh reconciliation; valid strategy/caps/reservation; no entry pause or relevant safety failure |
| CANCEL_ENTRY_READY | Known account and order identity; durable action recording; broker availability; cancellation permission |
| EXIT_READY | Known long position/quantity; valid exit rule; fresh enough broker reconciliation; durable evidence; paper adapter; no prohibited sell quantity |
| PROMOTION_READY | Current exact bundle, all required gates, fresh exact owner decision, allowed epoch boundary |
| RESEARCH_READY | Mature permitted datasets; valid split/holdout policy; isolated environment; budget/storage available |

New-entry readiness inherits the scientific trust requirements of its source seal but does not require the next day's unbuilt prediction. Exit readiness does not require a healthy Champion, feature engine, or new Market Snapshot. This removes a dangerous dependency between risk reduction and fresh alpha generation.

Pause new entries atomically blocks new exposure and enqueues cancellation of pending entry orders under the frozen policy. It does not imply automatic liquidation. Existing strategy exits remain permitted if their narrower gates pass. Resume is a request: server rechecks all current gates and records the result. Android cannot unilaterally clear an emergency halt.

Emergency states are scope-specific: NEW_EXPOSURE_HALT, EXECUTION_UNCERTAIN, SCIENTIFIC_HOLD, INTEGRITY_HALT, and IDENTITY_HALT. An integrity or database failure may prevent any new broker mutation because it cannot be recorded safely. The system must disclose this limitation; existing broker-native protective orders may remain active, but the backend cannot promise new exits while offline. Recovery reconciles them before resuming.

Global presentation states are BOOTING, RECOVERY, READY, DEGRADED, HOLD, and OFFLINE. They summarize detailed readiness and last-seen freshness. An offline server cannot reliably report its own OFFLINE state; Android/monitoring derives it from stale authenticated contact. Show the last known state and timestamp rather than a reassuring cached green status.

## 31. Owner identity, enrollment, and Android

There is one Owner record and multiple explicitly enrolled devices. Each device generates its own nonexportable signing key inside Android Keystore; the backend stores public key, algorithm, key ID, verified security level, enrollment proof, owner binding, app version, revocation state, and timestamps. Hardware backing is measured, not assumed: Android documents that it depends on supported device/algorithm combinations [S10]. No broker, backend-signing, database, or provider secret is shipped in the APK.

Initial enrollment uses a high-entropy, single-use, short-lived bootstrap secret provided through an owner-controlled administration channel. It is stored only as a verifier, consumed transactionally, and disabled once the first owner device is enrolled. No public default password, first-user-wins enrollment, QR screenshot reuse, or unverified deep-link enrollment. Additional devices require a fresh enrolled-owner authorization or the documented recovery procedure.

Use TLS, secure token storage, short-lived access sessions, rotating refresh credentials, server-side revocation, rate limits, and explicit action scopes. Read endpoints require authentication except minimal non-sensitive liveness. Mutations require a fresh signed challenge, idempotent command ID, request-body hash, and server-side authorization. Revocation is checked again when a privileged command is committed, not only when a token was issued.

Promotion signing requires explicit user presence through supported device authentication. A compromised unlocked app may still be dangerous; record the threat and minimize reusable authorization. App integrity/attestation can inform risk but is not treated as infallible owner identity. A notification is merely an alert; tapping it cannot approve a transition without opening the verified review and signing a fresh challenge.

Loss/recovery is mandatory before F0: owner holds offline recovery material, tested without exposing it in logs. Recovery revokes prior devices/sessions, records an integrity event, holds promotions and new entries, requires reconciliation, and enrolls a replacement key. Recovery credentials cannot submit orders or bypass promotion gates. Root-key rotation preserves historical verification material and records compromise/effective revocation boundaries.

Tabs remain Today, Predictions, Validation, Models, and System. Today shows current session, last sealed run, Top 1/5/10, actionable alerts, paper status, and data freshness. Predictions shows full ranks, uncertainty, unscorable/excluded reasons, and evidence details. Validation shows collection and maturation counts, baseline comparisons, coverage, and final/provisional status. Models shows Reference, operating Champion, Shadows, lineage, and eligible promotion review. System shows detailed readiness, clock/data/evidence/reconciliation health, pause/resume request, devices, and recovery state.

Allowed writes are promotion approve/hold/reject; exact epoch-activation approve/reject; pause new entries; resume request; alert acknowledgment; and authorized device actions. Epoch activation is the one narrowly added owner action needed to make QC2-088's exact signed authorization implementable through the primary interface. It appears in Validation only after the server has a complete activation audit; it binds the immutable epoch hash, prospective start session, account/strategy identities, nonce and expiration under the same device-signature and revocation controls. Validation Authority independently checks all activation gates. It does not let the phone edit policy, choose arbitrary models, or override readiness. Bootstrap model registration uses the promotion review with an explicit NO_CHAMPION expected state.

No BUY/SELL, manual score edits, strategy slider, arbitrary symbol blacklist, override-gate button, or force-promote endpoint exists. Cache is explicitly read-only, encrypted where appropriate, and labeled with server time and stale status. Privileged offline actions are disabled. Mobile projections are rebuildable and never authoritative.

## 32. API, alerts, and observability

Owner API read models are Today, Predictions, Validation, Models, System, Positions, Alerts, Reports, and Evidence detail. Lists are bounded/paginated with stable ordering; export requests have size limits and audited scope. Do not leak raw stack traces, secrets, signed artifact access tokens, or database details through errors. Require content-type/schema validation and reject unknown mutation fields. Object IDs are never authorization.

An OwnerCommandReceipt records accepted, duplicate, denied, stale, expired, or executed state and the resulting evidence ID. `HTTP 200` alone does not mean the requested transition happened. Repeating the same command yields the original receipt; reusing its ID with changed body is rejected. Read projections carry source sequence and lag so Android can distinguish a stale projection from a failed command.

Alerts have exactly five severities: INFO, NOTICE, WARNING, CRITICAL, EMERGENCY. Each type declares triggering rule, dedupe key, escalation, action/owner, auto-resolution condition, and whether it affects readiness. Acknowledgment does not clear the underlying condition. Delivery failures and muted notifications are visible; unread notifications are never the sole safety control.

Public `/health` exposes only liveness and a minimal release identifier. Authenticated `/ready` returns detailed action assessments. Metrics and diagnostic endpoints are private, bounded, and exclude secrets. Logs use structured UTC events with correlation IDs and redaction; high-cardinality identifiers are not unbounded metric labels. Evidence identifiers link operations to authoritative records without copying sensitive payloads.

Required measurements include scheduled/missed attempts; ingestion/feed delay; page/coverage errors; seal/anchor timing; per-stage duration; lease losses; evidence verification ranges; artifact failures; prediction missingness; outcome maturity lag; Shadow coverage; budget usage; API/auth failure rates; broker unknown submissions; order/position discrepancies; and backup/restore recency.

## 33. Backup, restore, retention, and supply-chain controls

Backups include PostgreSQL at a coherent recovery point; artifact inventories and bytes; configuration/registry history; owner public keys and revocation records; encrypted operational secrets according to a separate recovery policy; signing-key recovery arrangements; evidence roots; and independently retained checkpoint receipts. A database dump without model/snapshot artifacts cannot meet restore acceptance.

Owner policy fixes recovery point/time objectives and retention before activation. Backup frequency and object replication are measured against them. Encrypt backups, keep independent credentials, verify inventories and hashes, monitor quota, and test retrieval. Successful upload is not a successful restore. A restore into a clean isolated environment must reconstruct a sealed scientific run and reconcile a representative interrupted execution case before QC2-066 passes.

Restores create a new recovery generation with the same declared installation lineage, not an unlogged replacement identity. Compare against independently retained latest checkpoints to detect rollback. Start with outbound order capability disabled. Production credentials are introduced only after isolated verification, correct environment identity, and broker reconciliation. An old backup must not replay stale order outboxes against the current paper account.

Artifact retention is graph-based. Retaining an epoch, prediction, report, dataset, experiment used for promotion, or Champion retains all its referenced dependencies. Deletion first marks candidates, checks reverse references and legal/project retention holds, then runs a bounded logged garbage collection. No retained scientific object may depend on deleted raw data, a vanished environment lock, or a discarded former Champion.

CI checks dependency locks, provenance/license records, secret scanning, artifact hashes, migration safety, and known vulnerable dependencies under a recorded policy. No fetched script, model artifact, or legacy README can redefine build instructions or gain shell authority. Treat external files as untrusted input. Production migrations are versioned, tested against a restore, and reviewed for lock duration and data loss. Destructive auto-sync is forbidden. Expand/contract migrations preserve old sealed schemas and compatibility until consumers move.

## 34. Operational daily sequence and failure boundaries

The nightly flow is a durable dependency graph, not a single fragile function whose final step decides whether the whole day existed.

1. Reconcile expected calendar attempts and record any missed scheduler starts.
2. Acquire the attempt lease; verify installation, clock, deadline, resources, and ingestion preflight.
3. Freeze candidate census; retrieve all required daily data pages and metadata under the pinned regime.
4. Validate, quarantine, build eligibility, and seal the complete MarketSnapshot.
5. Atomically bind the PredictionRun and all model/registry/memory/baseline roles.
6. Compute features and Runner Protocols; score operating model, Reference, required baselines, and registered optional Shadows with isolated failure accounting.
7. Compute canonical score/ranks and row dispositions; seal full prediction inventories.
8. Obtain the independent pre-outcome anchor and seal the QualificationReceipt before its deadline.
9. Publish mobile read projections and alerts from the outbox.
10. Evaluate frozen strategy and reserve eligible next-session paper intents.
11. Submit only during the designated next-session execution window after fresh NEW_ENTRY_READY; maintain exits/reconciliation on their own schedules.
12. Independently resolve previously matured outcomes; verify action adjustments; append outcome evidence.
13. Update provisional validation without altering already sealed qualification decisions.
14. Generate independent RunnerEvents; build newly mature genomes/decoys/review cases; release permitted learning examples.
15. Run bounded ApexLab jobs; freeze candidates; run independent evaluation and register future Shadows.
16. Prepare promotion requests only when frozen policy and epoch mode permit; no automatic owner approval.
17. Verify incremental evidence/checkpoints, run scheduled full integrity checks, and produce reports.

Steps 12–17 can progress independently of a failed current prediction day as long as their own readiness passes. Failure to train, deliver a notification, or contact the broker does not retroactively disqualify a valid prospective prediction. Discovery of a genuine integrity violation creates an appended disqualification finding and its effect on final closure; it never deletes the original qualification.

Qualification fields are prediction_integrity, denominator/coverage status, on-time seal, on-time anchor, required comparator availability, and protocol conformity. Paper performance, whether a runner later occurred, research success, report formatting, and optional Shadow success are forbidden inputs. The session count displayed on Android comes only from sealed qualification receipts plus visible later integrity findings.

## 35. F0 closure, F1 boundary, and claims

After the 90th qualifying session, stop adding predictions to that F0 cohort and enter OUTCOME_MATURATION. Continued operational predictions, if authorized, belong to a separately identified subsequent cohort and cannot extend the closed cohort's denominator. Wait for all required horizons and the frozen resolution window; unresolved outcomes are reported under the missingness policy, not delayed indefinitely until favorable data arrives.

Final reports include immutable epoch manifest and amendments; all scheduled attempts; qualifying/nonqualifying/missed counts; dataset and coverage; primary result and bounds; all baselines; Reference/operating/Shadow distinctions; tenure summaries; calibration; runner/monster capture; learning-policy evidence and limits; scientific reliability; paper strategy/episode results; integrity/anchor proof; unresolved issues; and exact PASS/FAIL/INSUFFICIENT_EVIDENCE computation.

F1 is a new data/feature/validation regime. Minute bars, quotes, spread, premarket behavior, halt/timing information, and other intraday features require measured entitlements, new semantics, a new label/feature/strategy plan, new leakage tests, cost approval, and a new epoch. F1 must demonstrate incremental value using comparable forward cohorts and realistic cost assumptions. F0 success does not authorize a paid plan, live trading, or automatic intraday expansion.

## 36. Build governance and complete dependency policy

The first Replit assignment is documentation/task registration only, called PREBUILD_REGISTRY. It is not QC2-000 and does not create domain code or execute any canonical task. This resolves the apparent conflict between creating task files before bootstrap and prohibiting bootstrap implementation initially.

Preserve exactly 89 canonical IDs and names. Execution order is QC2-000, QC2-001, continuing consecutively through QC2-088. Each task after QC2-000 explicitly depends on its immediate predecessor; selected additional technical dependencies identify important reuse points. Therefore all earlier tasks must be PASS, and the graph is acyclic by construction. An agent may not infer that an omitted direct edge allows skipping an earlier task.

Exactly one canonical task may be IN_PROGRESS. Subtasks may exist only inside it. Do not parallelize canonical tasks or let background work mutate later-task artifacts. A later task may read an already accepted contract, but may not be partially implemented under an earlier task to make a demo appear complete.

States are TODO → IN_PROGRESS → PASS or BLOCKED. A BLOCKED task may return to IN_PROGRESS only after a recorded blocker resolution and explicit instruction to resume. Reopening a PASS task requires an amendment/change request; dependent gates become NEEDS_REVALIDATION in acceptance metadata and cannot be used to advance until revalidated. NEEDS_REVALIDATION is gate metadata, not a hidden fourth successful task state.

Each task records ID/name, objective, dependencies, authorized legacy sources, mandatory reference intake, deliverables, required tests, forbidden actions, acceptance gate, required evidence class/environment, calibration dependency, status, blockers, and TaskAcceptanceReceipt. All tasks start TODO. Missing credentials, unverified sources, insufficient real data, unavailable devices, or failed gates are BLOCKED with concrete evidence, not inferred PASS.

A TaskAcceptanceReceipt identifies task/spec versions; source commit; changed paths; exact executed commands; test/environment/data class; test counts and outcomes; artifact hashes; legacy-intake references; unresolved decisions; gate verdict; and reviewer/agent identity. Passing an empty test command, relying on a screenshot of a success message, or reporting intended tests as run is forbidden. Unit, integration, property, fault, and device tests are required only where they prove the task's actual invariants.

After each canonical task, Replit stops and reports the receipt, failures, blockers, decision requests, and next eligible task. It does not automatically begin the next task. Current authorization to rewrite this specification is not authorization to activate F0 or submit paper orders.

Framework work can pass before empirical calibration only if the parameterized contracts, fixtures, and fail-closed activation behavior work. Fixture constants cannot appear in production manifests. Calibration occurs in QC2-073–QC2-083; freeze/activation occurs in QC2-084–QC2-088. Earlier acceptance never means the whole system is operational.

QC2-011 is intentionally an acquisition/evidence vertical slice. It proves real data → normalized diagnostic DataBundle → immutable diagnostic snapshot → evidence verification. It may use an explicitly declared diagnostic census supplied for the test; it does not establish the eventual full Universe Authority. It must not implement a temporary feature, second baseline, substitute prediction authority, or premature outcome resolver. Full real forward prediction/outcome lineage is required later at QC2-086.

QC2-042 and QC2-043 implement approval/transition contracts with fixture identity providers. They cannot accept real owner approvals until QC2-053, QC2-055, and security/integration gates pass. Their fixture receipts are not production authority. QC2-037 implements the registry without requiring a live Champion; the real bootstrap artifact is qualified at QC2-083 and registered at QC2-084 under its explicit bootstrap transition.

QC2-086 must create a prospective non-F0 diagnostic prediction and await actual future maturity under the complete stack. A historical replay can supplement this, not replace it. This task may require more than ten exchange sessions because the complete 10-session secondary horizon and resolution buffer are tested. The task is honestly BLOCKED while waiting. The forward dry-run holdout and outcomes are subsequently treated as consumed development evidence, not counted in F0.

## 37. Required hostile and fault-injection matrix

| Scenario | Required observed result | Principal tasks |
| --- | --- | --- |
| Different JSON key order, Unicode form, decimal representation | Canonical equivalence or explicit rejection according to contract | 003–004 |
| NaN, infinity, duplicate keys, unrecognized enum | Rejected before persistence or inference | 003–004, 068 |
| Concurrent evidence writers and rolled-back append | Unique contiguous committed chain with no fork | 005–006, 071 |
| Delete/edit/reorder/truncate evidence | Verifier fails against full inventory and checkpoint | 006, 068 |
| Privileged rollback of DB and local hashes | Independent checkpoint mismatch; RECOVERY/HOLD | 006, 066, 071 |
| Domain write succeeds but evidence insert fails | Whole transaction rolls back | 005–006, 071 |
| Partial artifact upload, missing object after DB commit | No valid seal; actionable integrity failure | 006, 039, 065 |
| Feed omitted, subscription changed, provider 403 | Explicit failure; no alternate feed | 009–010 |
| Pagination stops on short page or repeats token | Completeness fails; snapshot cannot seal | 009, 069 |
| Early close, DST, unexpected closure, backwards clock | Correct session/deadline or safe hold | 008, 021 |
| Post-close daily volume still changing | Bar-finalization rule prevents premature completion | 009–011 |
| Current survivor list used as historical complete universe | Fidelity marked limited; broad claim blocked | 012, 033, 073 |
| Ticker reused, renamed, split, reverse split | Stable identity/adjustment verified or quarantined | 012, 015–016 |
| Future bar/genome/calibrator/imputer/index member | Temporal access rejected, including indirect dependency | 013, 028–029, 069 |
| Test-fold fit, target overlap, missing purge | Dataset/evaluator gate fails | 026, 033, 036 |
| Repeated qualification access during tuning | Consumption receipt; subsequent independence claim rejected | 034, 036, 083 |
| Early positive label released before full maturity | Learning release denied | 015–016, 033 |
| Missing fifth-session bar | Unresolved field; horizon does not become six sessions | 015–016 |
| Prior close 100, next open 200, future high 205 | Separate 105% close expansion from 2.5% next-open opportunity | 015–016, 026 |
| Stop and target both inside daily bar | Ambiguous path retained; no favorable fill sequence | 044, 079 |
| Runner Protocol attempts network/files/global mutation | Isolation failure blocks protocol acceptance | 017, 068 |
| Safety PASS numerically boosts score | Architecture/regression gate fails | 021, 024, 072 |
| Champion transition races run creation | Each run binds exactly one full generation | 025, 043, 071 |
| Model uses changed feature order or unsafe deserializer | Model rejected before production load | 023, 037, 041 |
| Shadow fails or sees future outcomes | Shadow evidence invalid; no effect on canonical score | 038, 069 |
| Prediction retry tries a better-ranked replacement | Unique canonical seal/selection rules reject it | 025, 069 |
| Late seal or late independent anchor | Diagnostic evidence retained; session nonqualifying | 025–026, 086 |
| Successful broker day changes qualification | Scientific test rejects forbidden dependency | 026, 069 |
| Signature replay, stale Champion, expired challenge | Transition denied atomically | 041–043, 055, 068 |
| Device revoked after challenge issuance | Commit-time revocation check denies action | 042, 053, 055 |
| Model pointer commits; new worker crashes loading | New-run readiness blocks; no silent old-model fallback | 043, 050, 071 |
| Broker accepts request then connection drops | SUBMISSION_UNKNOWN; reconciliation before any retry | 046–049, 070 |
| Duplicate/out-of-order/partial fills and trade correction | No double position or cash effect | 048–049, 070 |
| Two intents consume same available cash | Transactional reservation prevents overspend | 045–048, 070 |
| Pause arrives between verification and submission | Submit-time check blocks entry; cancel race reconciled | 046, 051, 055 |
| New model unavailable while exit is due | Exit evaluated by narrower exit gates | 050–051, 070 |
| Reconciliation finds unknown order/account reset | Hold with discrepancy; no position deletion shortcut | 049, 070 |
| Lease expires during inference or network wait | Stale worker cannot commit; remote uncertainty reconciled | 025, 046, 071 |
| Restore contains old pending order outbox | No automatic re-send; account reconciliation required | 066, 071 |
| Delete retained prior Champion or raw snapshot | Dependency graph prevents garbage collection | 067 |
| One runner repeated across many days | Distinct-event and dependence tests expose concentration | 026, 081 |
| Zero positive events, all ties, zero baseline hits | Defined undefined/insufficient states; no invalid ratios | 026, 081 |
| Experiment budget exhausted halfway through search | Trials preserved; no silent best-only ledger | 034–035, 052 |
| Android offline, stale projection, duplicate tap | Read-only stale view; idempotent receipt, fresh approval required | 055, 057–062 |

These are required properties, not a claim that every possible attack is covered. Add concrete tests when a new failure mode is found. Remove a test only through an approved requirement change, never to obtain a green report.

## 38. Canonical task definitions

The definitions below are binding. In every task, the common forbidden actions also apply: no live trading, runtime provider fallback, legacy-source mutation, fabricated test evidence, premature empirical defaults, unauthorized spending, architecture broadening, or automatic advancement. All references to task numbers in tests or tables mean the full QC2-prefixed ID.

Additional technical dependencies are listed beside the immediate predecessor. Runtime prerequisites appearing later in the order are activation gates, not hidden dependencies permitting premature activation. All canonical statuses are initially TODO and no canonical task has started merely because this registry exists.

### QC2-000 — Repository Bootstrap

**Objective:** Establish an isolated monorepo and reproducible toolchain without implementing scientific or trading behavior.

**Dependencies:** None.  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Pinned Python/package/test/lint configuration; Kotlin/Compose directory reserved without product behavior.
- Repository boundaries, environment namespaces, CI skeleton, secret/artifact ignores, migration conventions.
- Preliminary hosting/resource capability checklist and deployment-isolation decision; unresolved capabilities recorded.

**Required tests:**

- Clean install/import and meaningful smoke test on the selected runtime.
- Lint/type/test commands actually run; generated credentials and artifacts are ignored.
- No production credential or legacy import is present.

**Task-specific forbidden actions:**

- Do not implement domain authorities, request new paid resources, or claim unattended hosting is proven.

**Acceptance gate:** A clean checkout reproduces the toolchain; all environment limitations are explicit.

**Evidence/environment:** LOCAL_TOOLCHAIN  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-001 — Legacy Reference Manifest

**Objective:** Map each authorized historical source role to an inspectable, reproducibly identified snapshot without assuming one repository per role or requiring a literal Gen 1 repository name.

**Dependencies:** QC2-000  

**Authorized logical source roles:** QuantraCore production/core implementation; ApexLab research/training; original QuantraCore runner-protocol lineage.

**Reference mapping rule:** A repository may cover multiple roles and a role may use more than one repository/path. A later snapshot may map to a role only when its exact revision and version labels are recorded with provenance limits. A role label does not prove Gen 1, original-lineage, or production-release identity.

**Reference intake:** For each repository and file inspected, record revision, path/hash, source-supported meaning, relevant tests, conflicts, license, access limits, and disposition.

**Required deliverables:**

- Repository manifests for inspected candidates plus a map from the three logical roles to exact paths and revisions; do not require three distinct repositories.
- Protocol namespace inventory with repository-qualified IDs, duplicate-ID handling, and source-derived T24/T25/T34 verification cases.
- Read-only handling, hash checks, test coverage/limitations, licensing, conflicts, and provenance records.
- A scoped QC2-001 decision record; do not create the broader QC2-002 decision log or other QC2-002 deliverables here.

**Required tests:**

- Recompute sampled file hashes and distinguish duplicate IDs by repository and path; never merge meanings from a bare protocol ID.
- Show legacy working trees were not changed.
- Do not invent unavailable source content. If a later snapshot maps to a role, keep unproven historical origin or production status explicitly unverified; a role with no inspectable source remains a blocker.

**Task-specific forbidden actions:**

- Do not infer semantics from protocol numbers or earlier prose alone.

**Acceptance gate:** PASS when all three logical roles map to inspectable, immutable source paths and their version, hash, license, test, and provenance limits are recorded. Later snapshots are acceptable under the mapping rule; unverified original/Gen 1/production identity is not claimed. BLOCKED only if a role lacks an inspectable source or required access is unavailable.

**Evidence/environment:** LEGACY_READ_ACCESS  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial baseline:** TODO; no blockers had been assessed and no receipt existed when the task was defined.

**Current result:** PASS — all three roles are mapped to pinned snapshots with the unresolved historical and production provenance recorded.

**Acceptance receipt:** `docs/reference/QC2-001_SOURCE_MANIFEST.md`; scoped decision: `docs/reference/QC2-001_DECISION.md`.

### QC2-002 — Constitution and Authority Model

**Objective:** Translate the governing invariants and correction decisions into enforceable project policy.

**Dependencies:** QC2-001  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- GEN2_CONSTITUTION, AUTHORITY_MODEL, DECISION_LOG, UNKNOWN_LEDGER, CHANGE_CLASSIFICATION.
- Requirement-to-authority map, decision classes, amendment and gate-revalidation procedure.
- Explicit private F0 scope and default frozen-Champion mode.

**Required tests:**

- Check every canonical mutation has one owner and every invariant a planned enforcement test.
- Contradiction review covers execution/exit separation, initial bootstrap, and later activation gates.
- No unresolved decision is represented as a production default.

**Task-specific forbidden actions:**

- Do not reintroduce external Lamont Labs dependencies or commercialization scope.

**Acceptance gate:** Documents agree with this specification and identify a unique owner for each kind of authoritative state.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-003 — Canonical Contract Package

**Objective:** Implement strict schemas for every contract family in Section 12 before implementing its authority.

**Dependencies:** QC2-002  
**Authorized legacy references:** QuantraCore Gen 1 schemas, optional; ApexLab Gen 1 schemas, optional  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Versioned typed contracts, field units, enums, state guards, immutable-field rules, and JSON schemas.
- Writer/reader role map and foreign-reference rules for each object.
- Valid/invalid fixtures including temporal, identity, execution, and missingness examples.

**Required tests:**

- Reject unknown fields, invalid decimals, implicit timezones, invalid transitions, and ambiguous target references.
- Cross-language fixtures confirm Android-visible contract compatibility.
- Every named contract is present or explicitly aliased with identical documented meaning.

**Task-specific forbidden actions:**

- Do not defer omitted contracts as untyped dictionaries or accept permissive coercion.

**Acceptance gate:** The complete boundary contract inventory is machine-validatable and state/authority rules are explicit.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-004 — Canonical Serialization and Identity

**Objective:** Implement reproducible scientific bytes and distinct operational identities.

**Dependencies:** QC2-003  
**Authorized legacy references:** Gen 1 hashing utilities; ApexLab hashing utilities  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Canonical JSON/decimal format, domain-separated SHA-256 functions, UUIDv7 ID utility.
- Scientific versus operational-envelope field lists; fixed precision and ordering rules.
- Cross-platform golden vectors and artifact-manifest hashing.

**Required tests:**

- Equivalent permitted inputs hash identically; scientific mutation changes hash.
- Replay metadata changes do not alter scientific payload hash.
- Unicode, negative zero, duplicate keys, nonfinite values, and hash self-reference are tested.

**Task-specific forbidden actions:**

- Do not rely on Python repr, unsorted database rows, local time, or mutable archive metadata.

**Acceptance gate:** Golden vectors pass and each scientific hash has one unambiguous byte definition.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-005 — PostgreSQL Authority Foundation

**Objective:** Build durable transaction boundaries and least-privilege storage enforcement.

**Dependencies:** QC2-003, QC2-004  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- All required schemas/roles, non-runtime migration role, constrained mutation interfaces.
- Unique keys, referential integrity, immutable-record protections, job leases/outboxes.
- Development/test/production identity guards and migration policy.

**Required tests:**

- Attempt cross-authority writes using actual runtime roles; each unauthorized write fails.
- Test rollback, isolation, stale-generation writes, duplicate IDs, and conflicting reservations.
- Verify application roles cannot DDL, bypass RLS, alter immutable rows, or escalate.

**Task-specific forbidden actions:**

- Do not use an all-powerful Core login for every module or destructive schema auto-sync.

**Acceptance gate:** Permission and transaction tests run against PostgreSQL, not only mocks.

**Evidence/environment:** POSTGRESQL_INTEGRATION  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-006 — Evidence Authority

**Objective:** Make authoritative state changes atomic with restart-safe tamper-evident evidence.

**Dependencies:** QC2-004, QC2-005  
**Authorized legacy references:** Gen 1 audit hash chain and tests; ApexLab hashing defects/source  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Append/mutation API, transactional stream heads, verifier, checkpoint and independent-anchor interfaces.
- FULL/PARTIAL/FAILED verification results and complete artifact inventory checks.
- Threat model and explicit local-versus-independent proof levels.

**Required tests:**

- Concurrent append, transaction rollback, edit/delete/reorder/truncation and corrupt object tests.
- Fault between domain write/evidence/outbox cannot commit partial authority.
- Independent-checkpoint fixture detects coordinated local rollback; incomplete scan never passes.

**Task-specific forbidden actions:**

- Do not claim a local chain detects all privileged tampering or use a timestamp as sequence.

**Acceptance gate:** All defined attacker/fault cases yield the specified verdict; real anchoring remains an activation dependency.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-007 — Configuration Authority

**Objective:** Create one versioned source of truth for each setting and a fail-closed unknown ledger.

**Dependencies:** QC2-002, QC2-003, QC2-005, QC2-006  
**Authorized legacy references:** QuantraCore Gen 1 configuration; ApexLab Gen 1 configuration  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Secret references, system/epoch/strategy/research/deployment configuration contracts.
- Typed unresolved decisions, fixture-policy tagging, resource/budget gates.
- Change classification and effective-boundary validation.

**Required tests:**

- Reject duplicate authoritative definitions and unresolved production-required fields.
- Reject fixture hashes in production manifests.
- Research cannot widen owner capital/cost limits; secrets never appear in evidence/log output.

**Task-specific forbidden actions:**

- Do not guess empirical or owner-risk values to make startup green.

**Acceptance gate:** Invalid configuration blocks only the relevant capability and has an actionable reason.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-008 — Market Calendar Authority

**Objective:** Provide a single versioned exchange-session and deadline truth.

**Dependencies:** QC2-003, QC2-005, QC2-007  
**Authorized legacy references:** Gen 1 schedulers/calendar handling  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Calendar manifests/revisions, UTC and New York conversion, phase/deadline APIs.
- Clock uncertainty/rollback assessment and scheduled-session inventory.
- Provider calendar adapter plus deterministic pinned test calendars.

**Required tests:**

- Holidays, early closes, DST transitions, exceptional closure, missing calendar range.
- No next-N-bars horizon logic; next session follows the calendar.
- Backward clock and expired calendar prevent deadline-sensitive actions.

**Task-specific forbidden actions:**

- Do not scatter independent market-hours calculations across modules.

**Acceptance gate:** Calendar/clock behavior is deterministic with explicit unavailable states; measured live calendar support follows at QC2-010.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-009 — Market Data Adapter Contract and Canonical Alpaca Implementation

**Objective:** Implement the sole F0 acquisition path with explicit bar semantics and complete provenance.

**Dependencies:** QC2-003, QC2-006, QC2-007, QC2-008  
**Authorized legacy references:** Gen 1 Alpaca adapter and tests; ApexLab provider abstractions, optional  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Pinned request adapter, raw receipts, normalized DataBundle, pagination/rate-limit policy.
- BarSemanticsManifest, raw/split adjustment handling, anomaly/quarantine pipeline.
- Corporate-action retrieval/versioning and sanitized request evidence.

**Required tests:**

- Multi-symbol pagination, short pages, repeated tokens, 429/403, partial coverage, conflicting duplicates.
- No default feed/adjustment/asof; invalid OHLC and future revisions fail correctly.
- Volume finalization and split fixtures demonstrate declared semantics.

**Task-specific forbidden actions:**

- Do not switch provider/feed, fabricate missing bars, or treat daily open as guaranteed executable auction price.

**Acceptance gate:** Deterministic fixtures produce complete or explicitly failed DataBundles with no silent substitution.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-010 — Real Account Capability Probe

**Objective:** Measure the actual account and deployment capabilities needed for the intended F0 regime.

**Dependencies:** QC2-008, QC2-009  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Signed/evidenced DataCapabilityManifest with real feed access, delay, history, coverage and rate observations.
- Classification/action/calendar capability results and paper account fingerprint.
- Pre-activation feed selection proposal and unresolved access limitations.

**Required tests:**

- Real authenticated read-only requests test success and error cases without leaking credentials.
- Explicit SIP/IEX distinction, supported ranges, and pagination are demonstrated.
- No broker write, paid upgrade, or live-endpoint probe occurs.

**Task-specific forbidden actions:**

- Do not infer entitlement from documentation or pass this task without credentials.

**Acceptance gate:** Measured capabilities support a declared feasible regime or produce a concrete BLOCKED report.

**Evidence/environment:** ALPACA_CREDENTIALS, REAL_MARKET_DATA  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-011 — Early Real-Data Vertical Slice

**Objective:** Prove real acquisition, normalization, durable diagnostic sealing, and evidence lineage before deeper implementation.

**Dependencies:** QC2-006, QC2-008, QC2-009, QC2-010  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Real diagnostic census, raw receipts, normalized daily DataBundle, immutable diagnostic snapshot.
- Acquisition/coverage timing report and verified evidence chain.
- Explicit separation from official prediction, universe qualification, and future outcomes.

**Required tests:**

- Reconstruct normalized diagnostic bytes from saved raw receipts offline.
- Corrupt/missing receipt prevents the diagnostic seal.
- Real feed/semantics and actual receipt times agree with the capability manifest.

**Task-specific forbidden actions:**

- Do not build a temporary feature/scanner/model/outcome path or claim official F0 evidence.

**Acceptance gate:** A genuine complete acquisition-to-evidence lineage is verified; full forward outcome lineage is reserved for QC2-086.

**Evidence/environment:** ALPACA_CREDENTIALS, REAL_MARKET_DATA  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-012 — Universe Authority

**Objective:** Implement stable identity, candidate census, and deterministic scientific eligibility independent of trading.

**Dependencies:** QC2-003, QC2-008, QC2-009, QC2-010, QC2-011  
**Authorized legacy references:** Gen 1 scanner/universe code  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Instrument/symbol/classification history; candidate, eligible, unscorable and execution sets.
- Acyclic census→bundle→universe→snapshot construction and reason taxonomy.
- Point-in-time fidelity assessments and unresolved classification handling.

**Required tests:**

- Ticker reuse, rename, IPO, delisting, ETF/common-share ambiguity, unavailable listing age.
- Broker restriction does not alter scientific universe.
- Every candidate has one inclusion/exclusion disposition; current listings cannot claim historical completeness.

**Task-specific forbidden actions:**

- Do not choose empirical price/liquidity cutoffs or silently remove difficult instruments.

**Acceptance gate:** Parameterized fixture universes reproduce exactly and actual metadata limitations remain explicit.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-013 — Temporal Firewall

**Objective:** Enforce recursive information and learning availability for forward and reconstructed modes.

**Dependencies:** QC2-003, QC2-007, QC2-012  
**Authorized legacy references:** ApexLab temporal audit findings and supporting source  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Cutoff-scoped query/export APIs and permissions; transitive learned-dependency validator.
- Actual versus simulated availability fields and mode guards.
- Index/cache/revision-aware temporal access tests.

**Required tests:**

- Block future bars, labels, genomes, embeddings, normalizers, calibrators, and metadata aliases.
- Historical replay retains actual download/creation timestamps.
- Indirect caches and globally fitted state cannot bypass the cutoff.

**Task-specific forbidden actions:**

- Do not backdate known_at or treat provider asof as a historical knowledge timestamp.

**Acceptance gate:** Every dependency path either proves legal availability or blocks the consuming operation.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-014 — Feature Authority

**Objective:** Implement deterministic feature definitions and snapshots with explicit missingness.

**Dependencies:** QC2-004, QC2-012, QC2-013  
**Authorized legacy references:** Gen 1 feature logic; ApexLab feature logic; Original protocol concepts  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Feature Registry framework, required research families, dependency DAG and column order.
- Units, equations, warm-up, split, precision, normalization and missingness contracts.
- Fixture parameter profiles with production activation guard.

**Required tests:**

- Flat/zero-range/zero-volume/sparse/IPO/split/large-number edge cases.
- Repeated and reordered-input runs yield the same canonical snapshot.
- Metamorphic invariances and no-outcome-access tests pass.

**Task-specific forbidden actions:**

- Do not activate uncalibrated lookbacks or globally fit transforms.

**Acceptance gate:** Feature outputs are exact/reason-coded under registered definitions and are reproducible offline.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-015 — Label Authority

**Objective:** Define exact target semantics and enforce mature-only learning release.

**Dependencies:** QC2-003, QC2-008, QC2-013, QC2-014  
**Authorized legacy references:** ApexLab label implementation as a hypothesis/anti-pattern to verify  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Label Registry, primary/secondary horizons, reference-price definitions and formulas.
- Expansion/Monster family parameterization, failure/continuation unavailable states.
- Maturity and field-validity state machine.

**Required tests:**

- Missing fifth-session bar does not extend horizon; early winner cannot release full label.
- Signed MAE, unclamped extrema, split basis, tie peaks and zero-event cases.
- Undefined target semantics cannot produce a probability label.

**Task-specific forbidden actions:**

- Do not invent empirical runner thresholds or force unresolved outcomes to zero.

**Acceptance gate:** Labels have precise equations and release conditions; unresolved thresholds block production registration.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-016 — Ground Truth Authority

**Objective:** Resolve future outcomes independently from predictions, ranks, and model opinions.

**Dependencies:** QC2-006, QC2-009, QC2-012, QC2-013, QC2-015  
**Authorized legacy references:** Gen 1 ForwardValidator  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Outcome/revision resolver, action-review queue, terminal-event handling and evidence.
- Full eligible-row resolution and independent RunnerEvent primitives.
- Frozen correction and learning-release interfaces.

**Required tests:**

- Run without importing model/score/strategy packages.
- Resolve split/rename fixtures; retain unresolved halt/delisting/action cases.
- Rerun is idempotent; corrections append versions and cannot alter sealed predictions.

**Task-specific forbidden actions:**

- Do not let research reviews edit outcomes or hide data failures as non-runners.

**Acceptance gate:** Known synthetic outcomes are exact, unknown outcomes remain explicit, and dependencies are scientifically independent.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-017 — Runner Protocol Framework

**Objective:** Create a pure, isolated and resource-bounded structural-hypothesis API.

**Dependencies:** QC2-003, QC2-013, QC2-014, QC2-016  
**Authorized legacy references:** Original protocol framework  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Protocol definition/result schemas, evaluation engine and immutable inputs.
- Separate namespaces from safety, reason semantics, input evidence binding.
- Restricted worker/import boundary and deterministic fixture protocols.

**Required tests:**

- Attempt network, filesystem, clock, globals, training and broker access.
- UNKNOWN/UNAVAILABLE/BLOCK semantics are preserved without default positivity.
- Timeout/resource exhaustion returns a visible protocol failure.

**Task-specific forbidden actions:**

- Do not give Runner Protocol BLOCK a hidden broker-permission meaning.

**Acceptance gate:** All prohibited side effects are prevented or detected by actual enforcement tests.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-018 — Historical Protocol Lineage Registry

**Objective:** Account for original concepts without assuming all are valid or daily-compatible.

**Dependencies:** QC2-001, QC2-017  
**Authorized legacy references:** Original QuantraCore Protocol project  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Complete discovered protocol inventory with source hash, hypothesis, data need and disposition.
- Verified or unresolved T24/T25 and T34 records; compatibility map.
- Migration acceptance criteria and no-unresolved-active-dependency rule.

**Required tests:**

- Every discovered original file maps to one disposition.
- ID collisions and unavailable source meanings remain explicit.
- Intraday/float-only dependencies cannot become ACTIVE_F0.

**Task-specific forbidden actions:**

- Do not fabricate missing protocols, source paths, or semantic equivalence.

**Acceptance gate:** Inventory is complete for verified sources; unresolved items are excluded from activation or block a required dependency.

**Evidence/environment:** LEGACY_READ_ACCESS  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-019 — F0 Runner Protocol Migration Wave 1

**Objective:** Rewrite the verified daily-compatible inspection queue as research protocols.

**Dependencies:** QC2-014, QC2-017, QC2-018  
**Authorized legacy references:** Verified original P55/T34/T37/T38/T41/T42/T44/T57/T77/T78/T92/T102/T103/T104/T108/T109/T110 sources  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Source-backed implementation or explicit exclusion for each requested candidate.
- RESEARCH registry entries, parameter contracts, evidence fields and isolated tests.
- Semantics-difference notes where Gen 2 adapts legacy behavior.

**Required tests:**

- Positive/negative/unknown fixtures per implemented hypothesis.
- No hidden future-memory, quote, float, or live data requirement.
- Exact replay and side-effect tests for each migrated protocol.

**Task-specific forbidden actions:**

- Do not activate candidates or preserve a legacy threshold merely because it exists.

**Acceptance gate:** Every queue item is either independently tested research code or an evidence-backed exclusion.

**Evidence/environment:** LEGACY_READ_ACCESS  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-020 — F0 Runner Protocol Migration Wave 2

**Objective:** Support more complex daily hypotheses without creating a second intelligence authority.

**Dependencies:** QC2-013, QC2-014, QC2-017, QC2-018, QC2-019  
**Authorized legacy references:** Verified original breakout/divergence/stall/confluence/reversal/memory/trap/exhaustion sources  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Research implementations for supported structural concepts with dependency graphs.
- Failure-memory and similarity interface dependencies explicitly gated.
- Exclusion records for concepts impossible in F0.

**Required tests:**

- Multi-leg and temporal-boundary fixtures; no future member in memory lookup.
- No composite double-counting hidden behind duplicate protocol IDs.
- Unavailable ingredients produce UNAVAILABLE rather than invented evidence.

**Task-specific forbidden actions:**

- Do not build synthetic intraday proxies and claim original intraday semantics.

**Acceptance gate:** Complex protocols remain reproducible research assets; active-set choice is deferred to calibration.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-021 — Runtime Safety Protocol Framework

**Objective:** Implement non-predictive action-specific safety gates.

**Dependencies:** QC2-006, QC2-007, QC2-008, QC2-013, QC2-017, QC2-020  
**Authorized legacy references:** Gen 1 QC-T01–T65 safety lineage, verify exact namespace  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Time/data/model/registry/config/evidence/broker/reconciliation/idempotency safety contracts.
- PREDICT/NEW_ENTRY/EXIT/CANCEL/PROMOTE action policies and freshness rules.
- Stubbed capability ports with explicit unavailable results.

**Required tests:**

- Required UNKNOWN blocks the scoped action; optional warnings follow policy.
- Safety output cannot enter score/model feature APIs.
- New-entry failure does not automatically suppress otherwise authorized exit.

**Task-specific forbidden actions:**

- Do not convert safety PASS into bullish points or claim unavailable broker integration is tested.

**Acceptance gate:** Safety classification and authority separation hold under hostile fixtures.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-022 — Baseline Engines

**Objective:** Implement all mandatory reproducible comparator rankings.

**Dependencies:** QC2-012, QC2-013, QC2-014, QC2-015, QC2-021  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Random seed-set, momentum, relative-volume, breakout and equal-weight percentile composite engines.
- Baseline manifests and full-row disposition accounting.
- Top-K/percentile and tie conventions shared by later evaluation.

**Required tests:**

- Identical universe/cutoff input gives deterministic ranks.
- Zero denominators, missing rows, all ties and renamed instruments handled explicitly.
- Random seeds and composite weights cannot be optimized against outcomes.

**Task-specific forbidden actions:**

- Do not introduce a competing official scanner or tune the primary comparator after F0 starts.

**Acceptance gate:** Each baseline has inspectable equations, pinned fixture parameters, and no hidden model dependency.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-023 — Model Inference Contract

**Objective:** Build safe exact-artifact inference with logical head semantics.

**Dependencies:** QC2-003, QC2-013, QC2-014, QC2-015, QC2-017, QC2-022  
**Authorized legacy references:** Gen 1 ApexCore V2/V3; ApexLab model utilities  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Model/head compatibility interface, safe-format allowlist and isolated loader.
- Primary/optional head states, feature order checks, inference receipt.
- Environment fingerprint and deterministic probe framework.

**Required tests:**

- Reject unsafe serialization, wrong feature order, invalid probability, oversized model and unsupported operators.
- No training/network access during load/inference.
- Unavailable optional heads stay typed and do not become zero.

**Task-specific forbidden actions:**

- Do not choose a production Champion or load arbitrary pickle/joblib files.

**Acceptance gate:** Fixture artifacts load safely or fail explicitly and yield reproducible typed outputs.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-024 — QuantraScore Framework

**Objective:** Implement the versioned deterministic synthesis interface without choosing empirical weights.

**Dependencies:** QC2-014, QC2-017, QC2-021, QC2-023  
**Authorized legacy references:** Gen 1 QuantraScore; Gen 1 ZDE ranker  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- ScoreManifest with inputs, transformations, missingness/penalty and tie rules.
- Primary probability distinct from score/confidence/readiness.
- Calibratable parameter schema with fixture-only examples.

**Required tests:**

- No safety input changes score; missing required head cannot silently score.
- Canonical quantization and ranking tie cases reproduce exactly.
- Uncalibrated/fixture score cannot enter production epoch.

**Task-specific forbidden actions:**

- Do not equate a 0–100 score with a calibrated probability.

**Acceptance gate:** Score behavior is fully specified by one immutable manifest and cannot hide missing empirical decisions.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-025 — Prediction Authority

**Objective:** Implement the single canonical run, complete ranking, and irreversible seal.

**Dependencies:** QC2-006, QC2-008, QC2-012, QC2-013, QC2-014, QC2-017, QC2-022, QC2-023, QC2-024  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- ScheduledAttempt binding, run/row state machines, immutable scientific payload and seals.
- Early Champion/registry pinning and unique official seal constraints.
- Bounded deterministic retries, late-run diagnostics and anchor integration port.

**Required tests:**

- Concurrent run creation/Champion change cannot produce mixed generations.
- All eligible symbols appear ranked or unscorable; tie order is deterministic.
- Mutation after seal, favorable retry replacement, late qualification and fixture activation are rejected.

**Task-specific forbidden actions:**

- Do not let Shadows, reports, or endpoints create another canonical ranking.

**Acceptance gate:** One fixture session produces a complete immutable scientifically bound ranking with explicit failure dispositions.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-026 — Validation Authority

**Objective:** Implement independent metrics, prospective qualification, and three-state closure mechanics.

**Dependencies:** QC2-006, QC2-015, QC2-016, QC2-022, QC2-025  
**Authorized legacy references:** Gen 1 ForwardValidator; ApexLab evaluator  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Metric definitions, frozen qualification receipts, scheduled-opportunity ledger.
- Coverage/unknown bounds, comparator pairing, dependence-method interfaces.
- PASS/FAIL/INSUFFICIENT_EVIDENCE state logic with unevaluated calibration gates.

**Required tests:**

- Train/test overlap, fake all-row test metrics, feed mismatch, holdout reuse and missing denominator tests.
- Broker profit/failure and future labels cannot change qualification.
- Zero events, undefined ratios, missing labels and inadequate blocks return honest states.

**Task-specific forbidden actions:**

- Do not invent performance/sample thresholds or award PASS from ordinary iid accuracy.

**Acceptance gate:** Known fixture metrics and decision boundaries match independently computed results; policy remains nonproduction.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-027 — Runner Observatory

**Objective:** Detect real outcome events independently of model-selected symbols.

**Dependencies:** QC2-012, QC2-015, QC2-016, QC2-026  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Census-scoped event detector, coverage accounting and frozen episode primitives.
- Expansion/Monster and defined ancillary event records.
- Event discovery queue for research consumers.

**Required tests:**

- A low-ranked and an unpredicted eligible runner are still observed.
- Missing census data is visible; unverified market completeness is not claimed.
- Repeated overlapping events follow the declared episode identity.

**Task-specific forbidden actions:**

- Do not learn winner membership from the Champion or discard unscorable events.

**Acceptance gate:** Independent event detection exactly matches labeled fixture markets and its scope is explicit.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-028 — Runner Genome System

**Objective:** Create structural winner memories whose availability begins only after justified resolution.

**Dependencies:** QC2-013, QC2-014, QC2-015, QC2-016, QC2-025, QC2-027  
**Authorized legacy references:** Original DNA/memory protocol sources  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- RunnerGenome schema/store, pre-event snapshots, resolved facts and lineage.
- Versioned cutoff-filtered memory index and actual creation/learning times.
- Missing-contemporaneous-prediction representation.

**Required tests:**

- An April 15 success cannot be retrieved by an April 11 simulated decision.
- Changing an index member changes the index hash and replay dependency.
- Outcome-derived embeddings cannot enter an earlier feature view.

**Task-specific forbidden actions:**

- Do not backfill model foresight or expose future membership through similarity search.

**Acceptance gate:** Every genome/index lookup proves temporal eligibility for the consumer cutoff.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-029 — Failure Genome System

**Objective:** Preserve negative structural memories with the same temporal rigor as winners.

**Dependencies:** QC2-013, QC2-016, QC2-025, QC2-028  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- FailureGenome store, failure taxonomy and index lineage.
- Distinct non-event, downside, data-error and timing-miss categories.
- Maturity-gated release and versioned corrections.

**Required tests:**

- Unresolved data cannot create a negative training example.
- Future failed outcomes/index memberships are blocked.
- Corrections append rather than edit previously used memories.

**Task-specific forbidden actions:**

- Do not define failure simply as low realized P&L or one minus runner probability.

**Acceptance gate:** Negative memories are independently labeled, temporally eligible and replayable.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-030 — Matched Decoy Engine

**Objective:** Build difficult negatives without selecting similarities using future outcomes.

**Dependencies:** QC2-012, QC2-013, QC2-016, QC2-027, QC2-028, QC2-029  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Date/regime risk-set matcher, frozen caliper/distance policy and MatchedDecoySet.
- Reuse/unmatched accounting, training sample weights and original-population references.
- Cutoff-safe matching feature extraction.

**Required tests:**

- No outcome variable enters distance or caliper selection.
- Same-date candidates and repeated decoy reuse are recorded.
- Case-control sampling cannot be mistaken for natural-prevalence calibration.

**Task-specific forbidden actions:**

- Do not silently discard hard unmatched winners or evaluate probability calibration on balanced decoys.

**Acceptance gate:** Every match has explainable pre-outcome lineage and downstream sampling effects are explicit.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-031 — Missed Monster Review

**Objective:** Generate reproducible false-negative cases across rank, eligibility and availability failures.

**Dependencies:** QC2-025, QC2-026, QC2-027, QC2-028, QC2-030  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Deterministic review queue and case schema with frozen trigger parameters.
- Ranked-low/unscorable/excluded/unobserved/missed-session categories.
- Evidence-linked explanation template and research-only annotations.

**Required tests:**

- Major fixture runners appear even when no prediction or trade existed.
- Review cannot modify outcomes, ranks or official denominators.
- Repeated generation yields the same case identity.

**Task-specific forbidden actions:**

- Do not focus only on convenient examples or claim an exclusion was a prediction.

**Acceptance gate:** All trigger-matching cases are generated with the correct failure category.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-032 — False Monster Review

**Objective:** Generate reproducible false-positive cases without conflating prediction, execution and data errors.

**Dependencies:** QC2-025, QC2-026, QC2-027, QC2-029, QC2-030, QC2-031  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- High-confidence non-event/downside/timing/data-error case rules.
- Contemporaneous score/head evidence and resolved outcome links.
- Annotation audit trail for proposed research hypotheses.

**Required tests:**

- Unfilled scientific success is not relabeled a prediction failure.
- Unresolved label remains unresolved instead of a false-positive training row.
- Case annotations cannot rewrite authoritative evidence.

**Task-specific forbidden actions:**

- Do not change the high-confidence definition after seeing the failed cases.

**Acceptance gate:** Fixture failures and uncertainty cases are correctly separated with immutable source references.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-033 — ApexLab Dataset Builder

**Objective:** Replace unsafe data assembly with fully traceable chronological learning datasets.

**Dependencies:** QC2-013, QC2-014, QC2-015, QC2-016, QC2-028, QC2-029, QC2-030, QC2-032  
**Authorized legacy references:** Current ApexLab dataset/split/evaluation implementation  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- DatasetManifest/row lineage, SplitManifest, cutoff-scoped export and deduplication.
- Walk-forward train/development/qualification, purge and embargo implementation.
- Per-fold transforms/index construction and sample-weight handling.

**Required tests:**

- Label dependency intervals crossing folds are removed; all same-session rows stay together.
- Training-only fit and mature-only release tested through actual pipeline integration.
- Survivorship-limited inputs cannot claim PIT_VERIFIED.

**Task-specific forbidden actions:**

- Do not use global row-index splits, globally fitted preprocessors or a future final memory library.

**Acceptance gate:** Each dataset row and learned dependency can be traced to legal inputs and a verified fold assignment.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-034 — ApexLab Experiment Ledger

**Objective:** Account for the entire model-search process and qualification-data consumption.

**Dependencies:** QC2-006, QC2-007, QC2-033  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Append-only experiments/trials, budgets, failures, artifacts and comparison registration.
- Holdout access receipts and consumed-state policy.
- Cost/resource reports and resumable interrupted-trial records.

**Required tests:**

- Rejected/interrupted trials persist and count toward budgets.
- Repeated holdout access changes its consumption state.
- Trainer role cannot delete unfavorable trials or alter evaluation receipts.

**Task-specific forbidden actions:**

- Do not store only the winning run or call a previously examined holdout untouched.

**Acceptance gate:** A complete reconstructed search history is possible from immutable records.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-035 — Model Factory

**Objective:** Train required model families under identical governed data/split/budget contracts.

**Dependencies:** QC2-023, QC2-033, QC2-034  
**Authorized legacy references:** ApexLab deterministic training utilities  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Linear/logistic, Random Forest, Gradient Boosting and XGBoost training adapters.
- Frozen seeds, parameter spaces, safe artifact export and environment manifests.
- Bounded CPU/memory/time jobs with calibration/preprocessing lineage.

**Required tests:**

- Equivalent fixture competition uses the same splits and permitted targets.
- Budget exhaustion and interrupted export preserve honest failure state.
- No production write, broker access or qualification-label read from trainer credentials.

**Task-specific forbidden actions:**

- Do not select the Champion, self-certify qualification or save unsafe production serialization.

**Acceptance gate:** Every required family can produce a provenance-complete candidate or a reason-coded incompatibility; no silent omission.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-036 — Independent Candidate Evaluation

**Objective:** Separate training from qualification and ensure every reported test metric is genuinely held out.

**Dependencies:** QC2-023, QC2-026, QC2-033, QC2-034, QC2-035  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Isolated evaluator role/service, evaluation receipts and gate engine.
- Calibration, regression, leakage, resource and deterministic-inference checks.
- Candidate nomination and holdout consumption enforcement.

**Required tests:**

- Trainer cannot fetch held-out labels or change evaluator policy.
- All-row fake test metrics and reused holdout nomination are rejected.
- Independent fixture computations match metrics and gate results.

**Task-specific forbidden actions:**

- Do not let the candidate package supply executable gate logic or certify itself.

**Acceptance gate:** Evaluation is independently reproducible and information release is logged with correct holdout status.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-037 — Model Registry

**Objective:** Store immutable model artifacts and enforce lifecycle/pointer uniqueness.

**Dependencies:** QC2-005, QC2-006, QC2-023, QC2-034, QC2-036  
**Authorized legacy references:** Gen 1 active-model/source-lock mechanisms  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Content-addressed registry, lifecycle transitions and dependency retention links.
- Single operating-pointer schema and immutable Reference role.
- Safe staging/verification API; explicit no-Champion bootstrap state.

**Required tests:**

- Duplicate/conflicting Champion pointers and artifact overwrite fail.
- Retired models remain available for retained predictions.
- Unqualified/corrupt/unsafe artifact cannot become a loadable production candidate.

**Task-specific forbidden actions:**

- Do not create a real Champion before competition/qualification or let trainer update the pointer.

**Acceptance gate:** Registry/lifecycle invariants pass with fixtures; actual bootstrap remains gated by QC2-083–084.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-038 — Shadow Engine

**Objective:** Collect prospective candidate evidence without influencing production decisions.

**Dependencies:** QC2-025, QC2-026, QC2-033, QC2-036, QC2-037  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Pre-registration, same-input Shadow predictions, seals and coverage ledger.
- Post-training start boundaries, comparison windows and lifecycle results.
- Separate mobile/report projections and no-execution capability.

**Required tests:**

- Future-trained or late-registered model cannot produce retroactive forward evidence.
- Shadow error does not change official ranks or strategy.
- Dropped/failed Shadows remain in the trial and coverage ledger.

**Task-specific forbidden actions:**

- Do not choose the best Shadow per session or feed Shadow outputs into trading.

**Acceptance gate:** Every registered Shadow has accountable forward attempts and immutable candidate-specific evidence.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-039 — Full Scientific Replay

**Objective:** Reconstruct every scientific stage from sealed retained dependencies without network access.

**Dependencies:** QC2-004, QC2-006, QC2-012, QC2-013, QC2-014, QC2-017, QC2-023, QC2-024, QC2-025, QC2-037, QC2-038  
**Authorized legacy references:** Gen 1 replay mechanisms; ApexLab replay mechanisms  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Replay runner, dependency closure resolver and intermediate/final hash comparison.
- Qualified environment profile and mismatch-localization receipt.
- Corrected-data replay explicitly distinct from exact replay.

**Required tests:**

- Recreate universe, missing dispositions, features, protocols, heads, score and ranks exactly.
- Remove network/current DB mutable state and replay still works.
- Missing history/index/model/environment dependency fails instead of being fetched silently.

**Task-specific forbidden actions:**

- Do not compare only final scores or loosen numeric precision after a mismatch.

**Acceptance gate:** Complete fixture runs reproduce their ScientificPredictionPayload bytes and inventories exactly.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-040 — Promotion Bundle

**Objective:** Package final immutable candidate evidence with complete signed dependency inventory.

**Dependencies:** QC2-004, QC2-006, QC2-026, QC2-034, QC2-036, QC2-037, QC2-038, QC2-039  
**Authorized legacy references:** Gen 1 G2 promotion artifacts; ApexLab promotion packaging  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- PromotionBundleManifest, detached backend signature, archive restrictions and expiry.
- Dataset/holdout/Shadow/replay/policy/environment report references.
- Separate artifact, evaluator and owner identity bindings.

**Required tests:**

- Any file/content/path/size mutation after signing invalidates the package.
- Missing report, changed gate policy and archive traversal/bomb fixtures rejected.
- Manifest hashing has no self-referential signature field.

**Task-specific forbidden actions:**

- Do not patch bytes after hashing or treat packager signature as independent eligibility.

**Acceptance gate:** A bundle is fully verifiable from immutable dependencies and contains no unlisted executable payload.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-041 — Promotion Verification

**Objective:** Verify bundles independently before model loading or owner decision.

**Dependencies:** QC2-023, QC2-036, QC2-037, QC2-039, QC2-040  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Strict verifier, key-role/revocation registry and recomputed gate receipts.
- Compatibility and temporal-evidence checks with exact error taxonomy.
- Sandboxed candidate load/probe after byte and manifest verification.

**Required tests:**

- Wrong signer role, stale reports, label mismatch, future Shadow evidence and unsafe model fail.
- Revoked/unknown keys and extra archive entries rejected.
- Independent gate recomputation detects manipulated metrics.

**Task-specific forbidden actions:**

- Do not accept a signed PASS string without its supporting evidence or execute package scripts.

**Acceptance gate:** Every bundle field and required evidence item is validated by the verifier authority.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-042 — Owner Approval Authority

**Objective:** Define exact-state signed decisions using an identity-provider port before actual device enrollment exists.

**Dependencies:** QC2-003, QC2-006, QC2-007, QC2-040, QC2-041  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Challenge/envelope schemas, nonce lifecycle, approve/hold/reject records and idempotency.
- Domain/action/environment separation and commit-time identity recheck interface.
- Fixture-device tests and explicit production-disabled guard.

**Required tests:**

- Reject replay, expiration, changed candidate/current Champion/epoch/policy, and revoked identity.
- Hold/reject cannot be interpreted as approval.
- No real action possible using fixture enrollment/session.

**Task-specific forbidden actions:**

- Do not invent a temporary production password or bypass later device enrollment.

**Acceptance gate:** Approval logic passes hostile fixtures while real authority remains disabled until identity/API security gates.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-043 — Atomic Champion Transition

**Objective:** Commit one exact approved model transition without ambiguous or split authority.

**Dependencies:** QC2-005, QC2-006, QC2-025, QC2-037, QC2-041, QC2-042  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Prepare/verify/commit state machine, compare-and-swap pointer generation, receipt/outbox.
- Initial NO_CHAMPION bootstrap and forward rollback transition types.
- Worker load-confirmation and new-run readiness guard.

**Required tests:**

- Fault injection before/after every transaction step; exactly one committed pointer.
- Two approvals/promotions racing cannot consume one nonce twice or overwrite stale state.
- Commit-success/load-failure blocks new runs; old bound runs retain their generation.

**Task-specific forbidden actions:**

- Do not silently restore an old pointer, mutate an in-flight run, or enable real fixture approval.

**Acceptance gate:** Every injected failure leaves a determinate authoritative state and recoverable receipt.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-044 — Paper Strategy Framework

**Objective:** Define frozen long-only paper rules separately from intelligence and owner capital caps.

**Dependencies:** QC2-007, QC2-015, QC2-021, QC2-025, QC2-026, QC2-043  
**Authorized legacy references:** Gen 1 strategy tiers, concepts only  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- StrategyManifest/CapitalPolicy, capped DAY entry, exits/cooldown/hold/ambiguity rules.
- Prediction→proposed action interface and deterministic allocation/reservation plan.
- Fixture strategy profiles and unresolved owner/empirical parameter gates.

**Required tests:**

- Daily target/stop ambiguity preserved; no future open used to size today.
- No short, margin, pyramiding, fixture activation or cap widening.
- Missed fills do not alter scientific outcome labels.

**Task-specific forbidden actions:**

- Do not choose empirical sizing/stops/targets or claim a daily-bar path reveals fills.

**Acceptance gate:** Strategy framework produces explainable proposals and cannot activate without signed caps and calibration.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-045 — Paper Order Intent

**Objective:** Create immutable broker-independent intentions with exact exposure and expiry semantics.

**Dependencies:** QC2-003, QC2-005, QC2-006, QC2-021, QC2-025, QC2-044  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Intent schemas/state machine, stable request/client key, evidence links and reservations.
- Entry/reduce/close/cancel/replace distinctions with position references.
- Idempotent intent persistence and whole-share rounding.

**Required tests:**

- Same key/different bytes, expired intent, excessive sell quantity and wrong account rejected.
- Concurrent reservations cannot spend the same cash twice.
- Replacement preserves worst-case pending exposure.

**Task-specific forbidden actions:**

- Do not submit orders from this task or mutate already transmitted intent bytes.

**Acceptance gate:** Each valid fixture action has one immutable intention and a safe explicit reservation effect.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-046 — Execution Authority

**Objective:** Implement the only broker-mutation gateway with durable attempts and unknown-state recovery.

**Dependencies:** QC2-005, QC2-006, QC2-021, QC2-043, QC2-044, QC2-045  
**Authorized legacy references:** Gen 1 execution/idempotency logic  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Outbox consumer, just-in-time gate recheck and stable SubmissionAttempt records.
- SUBMISSION_UNKNOWN workflow, cancellation/replacement races and adapter interface.
- Fenced leases and action-scoped execution permissions.

**Required tests:**

- Timeout after remote acceptance cannot cause blind resubmission.
- Pause/expiry/account change between validation and send blocks unsafe action.
- Stale worker cannot commit; repeated delivery preserves one logical operation.

**Task-specific forbidden actions:**

- Do not interpret a network timeout or one not-found query as proof no order exists.

**Acceptance gate:** Faulted simulated broker interactions always produce known terminal or explicitly unresolved state.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-047 — Alpaca Paper Adapter

**Objective:** Implement only the pinned paper broker API surface and response normalization.

**Dependencies:** QC2-009, QC2-010, QC2-045, QC2-046  
**Authorized legacy references:** Gen 1 Alpaca adapter and tests  
**Reference intake:** Mandatory for each referenced repository/file actually inspected; record revision, path/hash, source-supported meaning, tests, conflicts, license, and disposition.

**Required deliverables:**

- Allowlisted paper host/account checks; submit/query/cancel/replace/read-activity interfaces.
- Client-order lookup, order-state mapping, bounded rate/retry and redaction.
- Contract fixtures derived from current official API semantics.

**Required tests:**

- Reject live host, redirects to unapproved hosts, wrong account, unsupported TIF/type and malformed events.
- Duplicate key, partial fill, delayed visibility and nonterminal cancel fixtures.
- Read-only actual account identity/connectivity check where credentials exist.

**Task-specific forbidden actions:**

- Do not add live mode, use paper=true as the only guard, or place a real test order without explicit sandbox authorization.

**Acceptance gate:** Only paper endpoints are reachable through the adapter; actual write behavior remains a QC2-086 gate.

**Evidence/environment:** ALPACA_CREDENTIALS, PAPER_READ_ONLY_INTEGRATION  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-048 — Durable Position State

**Objective:** Maintain auditable order/fill/cash/position state resilient to duplicate and corrected events.

**Dependencies:** QC2-005, QC2-006, QC2-045, QC2-046, QC2-047  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Immutable broker-event/fill ledger, correction events, positions and cash projections.
- Cumulative-quantity checks, reservation settlement and execution-episode identity.
- Corporate-action position adjustment interfaces.

**Required tests:**

- Duplicate/out-of-order/partial fills do not double count shares or cost.
- Trade correction/bust appends compensating state without deleting evidence.
- Projection rebuild equals persisted totals and disallows accidental short position.

**Task-specific forbidden actions:**

- Do not treat broker snapshots as permission to erase contradictory local history.

**Acceptance gate:** Position and cash projections rebuild deterministically from the preserved ledger.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-049 — Broker Reconciliation

**Objective:** Resolve local/remote differences before opening new exposure or recovering after restart.

**Dependencies:** QC2-006, QC2-046, QC2-047, QC2-048  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- ReconciliationReport, unknown-submission resolver, broker inventory comparison.
- Manual-order/unknown-position/cash-change/account-reset detection.
- Hold/resolution workflow with evidence and stable checkpoints.

**Required tests:**

- Remote accepted/local unknown, local missing fill and unknown remote order scenarios.
- Account reset cannot be interpreted as all positions safely closed.
- Repeated reconciliation is idempotent and cannot create an order.

**Task-specific forbidden actions:**

- Do not auto-delete discrepancies, invent fills, or resume merely because connectivity returned.

**Acceptance gate:** All fixture discrepancies converge through explicit evidence or retain a blocking unresolved state.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-050 — Prediction Readiness

**Objective:** Compose infrastructure, snapshot and prediction readiness without circular prerequisites.

**Dependencies:** QC2-007, QC2-008, QC2-010, QC2-013, QC2-021, QC2-025, QC2-037, QC2-039, QC2-043, QC2-049  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- INGESTION_PREFLIGHT, SNAPSHOT_READY and PREDICTION_READY engines.
- Version/freshness/deadline assessments and reason-coded mobile/API projections.
- Loaded-model/pointer consistency and seal-capability checks.

**Required tests:**

- Broker outage leaves scientific readiness unaffected.
- Unknown clock, illegal dependency, missing artifact or model load mismatch blocks prediction.
- Run readiness cannot require that the same run already has a completed prediction.

**Task-specific forbidden actions:**

- Do not implement one broad ready boolean or permit stale green assessments.

**Acceptance gate:** Each scientific stage exposes exact prerequisites and fails only for relevant unavailable evidence.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-051 — Execution Readiness

**Objective:** Separate entry, cancellation and exit trust requirements.

**Dependencies:** QC2-021, QC2-044, QC2-045, QC2-046, QC2-047, QC2-048, QC2-049, QC2-050  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- NEW_ENTRY_READY, CANCEL_ENTRY_READY, EXIT_READY and emergency scope logic.
- Pause-new-entries behavior and fresh server-side resume assessment.
- Generation-bound readiness lifetime and submit-time checks.

**Required tests:**

- Champion failure does not itself block valid exit; storage/evidence failure still blocks unrecordable mutation.
- Pause cancels pending entries according to policy and prevents race-through submission.
- Unknown reconciliation/account identity blocks exposure.

**Task-specific forbidden actions:**

- Do not interpret resume request as approval to bypass safety or pause as liquidation.

**Acceptance gate:** Action-specific tests demonstrate the intended reduction of exposure while preserving fail-closed identity/evidence.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-052 — Research Readiness

**Objective:** Gate research on legal mature data and bounded isolated resources.

**Dependencies:** QC2-007, QC2-013, QC2-033, QC2-034, QC2-035, QC2-036, QC2-051  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- RESEARCH_READY engine, disabled mode, job budgets and schedule priorities.
- Dataset/holdout/environment/cost readiness reasons.
- Research queue controls that cannot starve prediction/evidence.

**Required tests:**

- Immature labels, consumed qualification, expired budget and missing storage prevent launch.
- Research failure does not invalidate sealed production predictions.
- Worker lacks production/broker mutation credentials.

**Task-specific forbidden actions:**

- Do not expand paid capacity automatically or make nightly training mandatory for prediction.

**Acceptance gate:** Research can be paused or fail independently with complete job/trial accounting.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-053 — Owner Identity and Device Enrollment

**Objective:** Implement one-owner trust, secure device enrollment, revocation and recovery.

**Dependencies:** QC2-003, QC2-005, QC2-006, QC2-007, QC2-042, QC2-052  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Single-use bootstrap, device public-key registry, sessions and rotating refresh credentials.
- Device security-level metadata, signed command validation and revocation checks.
- Offline recovery procedure and hold/re-enrollment transitions.

**Required tests:**

- Enrollment replay/race, invalid key binding, lost-device recovery and post-challenge revocation.
- No first-user-wins takeover or default password.
- Fixture/device trust cannot cross environment namespace.

**Task-specific forbidden actions:**

- Do not store mobile private keys or broker credentials in the app/backend device records.

**Acceptance gate:** Identity lifecycle passes backend integration; real Keystore/device validation is required with Android work.

**Evidence/environment:** IDENTITY_INTEGRATION  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-054 — Owner API Read Models

**Objective:** Expose authenticated rebuildable owner views with evidence and freshness.

**Dependencies:** QC2-025, QC2-026, QC2-037, QC2-048, QC2-049, QC2-050, QC2-051, QC2-052, QC2-053  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Today/Predictions/Validation/Models/System/Positions/Alerts/Reports read schemas.
- Bounded pagination, stable sort, projection sequence/lag and redacted errors.
- Minimal public liveness and private detailed diagnostics.

**Required tests:**

- Unauthenticated/object-ID guessing cannot read sensitive state.
- Projection rebuild matches source receipts; stale data remains labeled.
- Large exports and invalid pagination are bounded.

**Task-specific forbidden actions:**

- Do not expose arbitrary SQL, mutable scientific rows or a second desktop product.

**Acceptance gate:** All owner views are permissioned projections with traceable canonical sources.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-055 — Owner API Mutations

**Objective:** Expose only authorized owner commands with exact-state signatures and idempotent receipts.

**Dependencies:** QC2-042, QC2-043, QC2-051, QC2-053, QC2-054  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Promotion decisions, exact epoch-activation decisions, entry pause, resume request, acknowledgment and device-management endpoints.
- Fresh challenges, body-hash/idempotency validation and commit-time identity checks.
- Command receipt and projection linkage; Validation alone commits a verified epoch activation.

**Required tests:**

- Duplicate tap returns same receipt; same ID/new body rejected.
- Stale/expired/revoked approvals and unauthorized endpoint/action rejected.
- No hidden buy/sell, force-promote, scientific-edit or safety-override route.

**Task-specific forbidden actions:**

- Do not enable offline queued approvals or treat HTTP success as completed transition.

**Acceptance gate:** Every permitted write maps to one scoped authority command; all other mutation classes are denied.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-056 — Alert Authority

**Objective:** Create deterministic operational alerts with five severities and separate acknowledgment/resolution.

**Dependencies:** QC2-006, QC2-050, QC2-051, QC2-052, QC2-053, QC2-054, QC2-055  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- INFO/NOTICE/WARNING/CRITICAL/EMERGENCY taxonomy and trigger/escalation catalog.
- Dedupe, delivery outbox, stale-delivery visibility and source-event references.
- Acknowledgment and automatic/manual resolution rules.

**Required tests:**

- Repeated trigger does not flood; recurrence after resolution is visible.
- Acknowledgment cannot clear failed readiness.
- Push-delivery failure cannot suppress server safety behavior.

**Task-specific forbidden actions:**

- Do not put secrets or actionable approval credentials into notification payloads.

**Acceptance gate:** Alerts reliably reflect source conditions and delivery state without becoming an authority shortcut.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-057 — Android Foundation

**Objective:** Build the authenticated Kotlin/Compose owner app with real device signing and safe cache behavior.

**Dependencies:** QC2-003, QC2-053, QC2-054, QC2-055, QC2-056  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Five-tab shell, enrollment/sign-in, Keystore P-256 signing and server contract client.
- Encrypted scoped cache, online freshness, environment identity and release signing policy.
- Device capability/security-level reporting and accessibility baseline.

**Required tests:**

- Build/install on a supported real Android device; enrollment and signed challenge round trip.
- Offline state is visibly stale and cannot submit privileged actions.
- APK/config/log scan finds no broker/backend secrets; key is nonexportable through app API.

**Task-specific forbidden actions:**

- Do not invent hardware-backed status, add manual trading or retain fixture identities.

**Acceptance gate:** A real device communicates with the test backend using its own registered key and all required user flows are reachable.

**Evidence/environment:** ANDROID_BUILD_ENVIRONMENT, REAL_ANDROID_DEVICE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-058 — Android Today

**Objective:** Present current operating state and owner attention without concealing stale or blocked data.

**Dependencies:** QC2-025, QC2-050, QC2-051, QC2-054, QC2-056, QC2-057  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Today session/Top1/5/10, last seal/anchor, paper state and actionable alert cards.
- Explicit provisional/stale/missing-run states and evidence drill-down.
- Loading/error/empty/accessibility layouts.

**Required tests:**

- Wrong session/stale cached green state cannot appear current.
- Prediction availability and broker outage display independently.
- Tap targets/text scaling and one-device acceptance walkthrough.

**Task-specific forbidden actions:**

- Do not display fabricated confidence percentages, live P&L claims or a buy button.

**Acceptance gate:** Today accurately represents fixture and connected backend states on the supported device.

**Evidence/environment:** ANDROID_BUILD_ENVIRONMENT, REAL_ANDROID_DEVICE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-059 — Android Predictions

**Objective:** Expose full ranked evidence and missingness, not only favorable top picks.

**Dependencies:** QC2-025, QC2-026, QC2-054, QC2-057, QC2-058  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Ranked pagination, primary probability/QuantraScore distinction, horizon views.
- Unscorable/excluded reasons, prediction provenance and Reference/Shadow labels.
- No-fill and scientific-outcome separation.

**Required tests:**

- Ordering/ties match sealed server ranks; pagination does not duplicate or omit rows.
- Unknown labels/heads remain unknown rather than zero.
- Connected/device checks verify stale and late-diagnostic distinctions.

**Task-specific forbidden actions:**

- Do not let the phone rerank canonically, hide bad outcomes or alter symbol eligibility.

**Acceptance gate:** The owner can inspect any eligible row and identify the exact scientific evidence it represents.

**Evidence/environment:** ANDROID_BUILD_ENVIRONMENT, REAL_ANDROID_DEVICE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-060 — Android Validation

**Objective:** Show experiment progress, uncertainty and honest denominators.

**Dependencies:** QC2-026, QC2-054, QC2-057, QC2-059  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Scheduled/qualifying/missed/maturing counts and fixed-end collection status.
- Baseline/Reference/operating comparisons, confidence and missingness bounds.
- Provisional/final integrity views and exact epoch-activation review after all audit gates pass.

**Required tests:**

- Ninety sessions without enough events does not display automatic PASS.
- Zero-event/undefined ratio/insufficient evidence and corrupted-epoch fixtures.
- Displayed denominator/model role match the report; stale or incomplete activation request cannot be signed into effect.

**Task-specific forbidden actions:**

- Do not present descriptive interim metrics as a final statistical win.

**Acceptance gate:** Validation UI communicates the actual frozen decision rules and uncertainty on a real device.

**Evidence/environment:** ANDROID_BUILD_ENVIRONMENT, REAL_ANDROID_DEVICE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-061 — Android Models and Promotion

**Objective:** Provide exact-candidate evidence review and user-presence-bound model decisions.

**Dependencies:** QC2-037, QC2-038, QC2-040, QC2-041, QC2-042, QC2-043, QC2-053, QC2-055, QC2-057, QC2-060  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Champion/Reference/Shadow lineage, eligibility and gate evidence pages.
- Approve/hold/reject review tied to current bundle/epoch/challenge.
- Expired/stale/revoked and post-transition-load-failure states.

**Required tests:**

- Biometric/device-auth signing round trip uses actual enrolled key.
- Candidate or current Champion change invalidates the open review.
- Duplicate decision, offline action and forbidden frozen-F0 promotion rejected.

**Task-specific forbidden actions:**

- Do not hide failed gates, automatically approve, or allow force promotion.

**Acceptance gate:** End-to-end device decisions produce the exact server receipt or a clear denial without stale-state transition.

**Evidence/environment:** REAL_ANDROID_DEVICE, IDENTITY_INTEGRATION  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-062 — Android System

**Objective:** Expose actionable operational trust, entry pause/resume request and device control.

**Dependencies:** QC2-049, QC2-050, QC2-051, QC2-052, QC2-053, QC2-055, QC2-056, QC2-057, QC2-061  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Detailed readiness, evidence/anchor/data/model/reconciliation/storage status.
- Pause/resume request, device list/revocation and recovery guidance.
- Offline/last-contact semantics and alert acknowledgment.

**Required tests:**

- Pause races and denial of unsafe resume are visible.
- Revoked device loses privileged access; cached state stays explicitly stale.
- No global green state hides a blocking subsystem.

**Task-specific forbidden actions:**

- Do not make alert acknowledgment or resume tap clear machine safety gates.

**Acceptance gate:** The owner can identify and act on allowed operational states without gaining discretionary trading power.

**Evidence/environment:** REAL_ANDROID_DEVICE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-063 — Generated Reports

**Objective:** Generate immutable evidence-linked daily, learning, promotion and validation reports.

**Dependencies:** QC2-026, QC2-027, QC2-031, QC2-032, QC2-034, QC2-038, QC2-039, QC2-041, QC2-048, QC2-056, QC2-060, QC2-062  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Daily Runner, Weekly Learning, Missed Monster, False Monster, Promotion, F0 Validation and Integrity reports.
- Machine-readable metric source manifests and human-readable versions.
- Report revisions/amendments, scope limitations and provisional status.

**Required tests:**

- Recompute report totals from source artifacts; denominators match.
- No report presents survivor-limited research or paper fills as broader proof.
- Changed source correction produces amendment, not overwritten final report.

**Task-specific forbidden actions:**

- Do not select only favorable time windows or use unlabeled generated prose as evidence.

**Acceptance gate:** Every material number and verdict resolves to immutable inputs and a registered metric definition.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-064 — Internal Observability

**Objective:** Make missing work, lag and failures visible without exposing sensitive internals.

**Dependencies:** QC2-006, QC2-025, QC2-049, QC2-050, QC2-051, QC2-052, QC2-054, QC2-056, QC2-063  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Private metrics/readiness, minimal public health and structured redacted logs.
- Scheduled-attempt watchdog, job/outbox lag, quota and reconciliation monitors.
- Operational runbooks for each critical reason code.

**Required tests:**

- Scheduler never starts: watchdog still records missed opportunity.
- Logs/API/metrics contain no secrets; cardinality and payload limits enforced.
- Monitoring outage does not disable authoritative safety.

**Task-specific forbidden actions:**

- Do not replace evidence with logs or expose diagnostic internals publicly.

**Acceptance gate:** Defined failure states are observable and recoverable using tested runbook steps.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-065 — Backup System

**Objective:** Create coherent encrypted recovery sets across database, artifacts and trust material.

**Dependencies:** QC2-005, QC2-006, QC2-007, QC2-037, QC2-053, QC2-063, QC2-064  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- BackupManifest, independent destination policy and recovery-point/time objectives.
- Database/artifact/checkpoint/key-recovery inventories with hashes and retention.
- Backup jobs, quota/error monitoring and restore instructions.

**Required tests:**

- Missing object or checkpoint invalidates backup completeness.
- Encrypted backup can be retrieved using intended recovery credentials.
- Backup account and application write scopes are separated.

**Task-specific forbidden actions:**

- Do not claim restore success from an upload response or put secrets in plain archives.

**Acceptance gate:** A real nonproduction recovery set is stored and verified against its complete inventory.

**Evidence/environment:** BACKUP_DESTINATION_ACCESS, REAL_BACKUP_ARTIFACTS  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-066 — Restore Drill

**Objective:** Prove a clean environment can recover scientific identity and interrupted operations safely.

**Dependencies:** QC2-039, QC2-043, QC2-049, QC2-053, QC2-065  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Isolated restored deployment, RestoreReceipt and measured RPO/RTO evidence.
- Replayed sealed run and independent-checkpoint comparison.
- Order-outbox/account reconciliation rehearsal with egress disabled.

**Required tests:**

- Restore with missing model/raw data fails; valid restore yields exact scientific bytes.
- Older coordinated backup is detected against independent head.
- Stale pending broker action cannot automatically resend after restore.

**Task-specific forbidden actions:**

- Do not run a drill against the active epoch account or bypass identity/reconciliation.

**Acceptance gate:** Actual clean restore meets signed recovery objectives or task remains BLOCKED.

**Evidence/environment:** CLEAN_ISOLATED_ENVIRONMENT, BACKUP_DESTINATION_ACCESS  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-067 — Artifact Dependency/Retention Graph

**Objective:** Protect all evidence required by retained scientific and governance artifacts.

**Dependencies:** QC2-006, QC2-025, QC2-033, QC2-037, QC2-039, QC2-040, QC2-063, QC2-065, QC2-066  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Typed dependency graph, reverse-reference query and retention roots.
- Two-stage bounded garbage collection with audit and dry-run output.
- Former-Champion/old-schema/environment retention rules.

**Required tests:**

- Attempt to delete dependencies of retained prediction/model/report/epoch is denied.
- Unreferenced staging object can expire without affecting retained closure.
- Graph cycles/missing nodes and stale GC plan are detected.

**Task-specific forbidden actions:**

- Do not delete raw inputs solely because a newer model or report exists.

**Acceptance gate:** Retention closure remains complete across backup, retirement, and proposed deletion.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-068 — Hostile Security Tests

**Objective:** Verify actual trust boundaries against concrete hostile requests and artifacts.

**Dependencies:** QC2-005, QC2-006, QC2-017, QC2-023, QC2-040, QC2-041, QC2-042, QC2-043, QC2-053, QC2-055, QC2-057, QC2-061, QC2-067  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Security test inventory mapped to invariants/threat model.
- Permission/API/auth/artifact/secret-isolation findings with severity and remediation.
- Accepted residual-risk statement limited to actual tested boundaries.

**Required tests:**

- Cross-role writes, replayed signatures, revoked devices, path traversal and deserialization attempts.
- Runtime network/filesystem escape attempts from research/protocol artifacts.
- Direct and alternate API paths cannot submit orders or promote without authority.

**Task-specific forbidden actions:**

- Do not claim penetration-test certification or close a finding without evidence.

**Acceptance gate:** All critical/high authority-boundary defects are fixed and retested; known limitations are explicit.

**Evidence/environment:** INTEGRATED_TEST_DEPLOYMENT  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-069 — Hostile Scientific Tests

**Objective:** Attempt to manufacture false predictive evidence and prove the system rejects it.

**Dependencies:** QC2-013, QC2-015, QC2-016, QC2-025, QC2-026, QC2-028, QC2-029, QC2-030, QC2-033, QC2-034, QC2-036, QC2-038, QC2-039, QC2-068  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Leakage/selection/denominator/revision/qualification adversarial suite.
- Known-null and known-signal synthetic populations with dependence.
- Findings tied to contracts and repaired gate receipts.

**Required tests:**

- Future index/normalizer, overlapping target, survivorship, early-label and repeated-holdout attacks.
- Late seal/anchor, favorable rerun, broker-dependent qualification and dropped losers.
- Missing labels, repeated runner episodes and feed mismatch cannot inflate official metrics.

**Task-specific forbidden actions:**

- Do not use high synthetic accuracy as real market predictive proof.

**Acceptance gate:** Every specified false-proof path is blocked or produces visibly nonqualifying evidence.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-070 — Hostile Execution Tests

**Objective:** Attack the paper-order lifecycle with uncertain, duplicate and racing remote outcomes.

**Dependencies:** QC2-044, QC2-045, QC2-046, QC2-047, QC2-048, QC2-049, QC2-051, QC2-055, QC2-069  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Deterministic adversarial broker simulator and executable scenario matrix.
- Reservation/fill/cancel/replace/account-reset discrepancy proofs.
- No-live-route and independent exit-readiness regression tests.

**Required tests:**

- Remote accept/timeout/not-found window, duplicate partial fills, cancel/fill race, paused send.
- Concurrent intents and quantity changes cannot overspend/oversell.
- Unknown submissions remain unresolved until positive reconciliation evidence.

**Task-specific forbidden actions:**

- Do not interpret this fixture suite as a real Alpaca write-integration test.

**Acceptance gate:** All adversarial executions preserve bounded exposure and honest state without duplicate logical orders.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-071 — Restart/Fault Injection Suite

**Objective:** Prove recovery across process, transaction, storage and lease failure boundaries.

**Dependencies:** QC2-006, QC2-025, QC2-039, QC2-043, QC2-046, QC2-048, QC2-049, QC2-065, QC2-066, QC2-068, QC2-069, QC2-070  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Crash-point inventory across seals, artifacts, outboxes, promotion and broker attempts.
- Worker fencing/restart harness, evidence comparison and recovery receipts.
- Resource exhaustion, partial transfer and connection-loss scenarios.

**Required tests:**

- Kill before/after each critical commit; recover to one determinate state.
- Stale lease worker cannot commit; external unknown state survives restart.
- Corrupt/missing artifact and old backup prevent unsafe readiness.

**Task-specific forbidden actions:**

- Do not reset a database or discard unresolved jobs to make recovery pass.

**Acceptance gate:** All declared crash points recover or hold explicitly with preserved evidence and no unauthorized effect.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-072 — Architecture Regression Audit

**Objective:** Check implemented import, credential, dataflow and mutation boundaries against the constitution.

**Dependencies:** QC2-002, QC2-003, QC2-005, QC2-013, QC2-021, QC2-025, QC2-036, QC2-043, QC2-055, QC2-067, QC2-068, QC2-069, QC2-070, QC2-071  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Architecture dependency graph and invariant-to-test traceability report.
- Scan for alternate scanners, feature leakage, duplicated config, legacy imports and live routes.
- Change/deviation log and revalidation of affected prior gates.

**Required tests:**

- Static import checks plus runtime permission checks verify each exclusive writer.
- All 24 invariants map to real passing or explicitly pending activation evidence.
- A deliberately introduced boundary violation is caught by regression controls.

**Task-specific forbidden actions:**

- Do not excuse scientific/authority drift as an implementation detail.

**Acceptance gate:** No unresolved critical/high architecture violation; framework status remains distinct from calibrated readiness.

**Evidence/environment:** LOCAL_FIXTURE_AND_CODE_EVIDENCE  
**Calibration state:** FRAMEWORK_OR_POLICY_ONLY  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-073 — Historical Calibration Dataset

**Objective:** Acquire a real calibration corpus with known limitations before freezing empirical choices.

**Dependencies:** QC2-010, QC2-012, QC2-013, QC2-015, QC2-016, QC2-033, QC2-034, QC2-036, QC2-072  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Historical raw/normalized corpus, metadata/actions and universe-fidelity report.
- Chronological development and untouched qualification boundaries; budget and search plan.
- Rebuildable dataset recipes; final target/feature views created by subsequent calibration tasks.

**Required tests:**

- Actual provider provenance, coverage, delisted/rename limitations and revision assumptions verified.
- Qualification access controls work; no overlap with parameter-selection windows.
- Corpus can be reconstructed from retained receipts without current mutable data.

**Task-specific forbidden actions:**

- Do not label this preliminary corpus as a finalized production feature/label dataset or PIT-complete without evidence.

**Acceptance gate:** Real data supports a precisely scoped calibration/qualification plan; inadequate scope or volume blocks progression.

**Evidence/environment:** ALPACA_CREDENTIALS, REAL_HISTORICAL_DATA  
**Calibration state:** CALIBRATION_INPUT_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-074 — Universe Calibration

**Objective:** Select coverage/liquidity/history rules from development evidence without future survival bias.

**Dependencies:** QC2-012, QC2-026, QC2-033, QC2-073  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Universe parameter study, missingness/classification analysis and rejected choices.
- Frozen eligibility proposal with verified meanings and estimated capacity.
- Owner acceptance of scope/cost limitations where needed.

**Required tests:**

- Apply thresholds using only each historical cutoff data.
- Quantify exclusions, rare-event coverage and sensitivity without using locked qualification.
- Unknown listing age cannot be silently substituted by history length.

**Task-specific forbidden actions:**

- Do not optimize universe on the unopened qualification set or later F0 winners.

**Acceptance gate:** One justified eligibility policy is selected and immutable for subsequent qualification.

**Evidence/environment:** REAL_HISTORICAL_DATA  
**Calibration state:** EMPIRICAL_CALIBRATION_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-075 — Runner Label Calibration

**Objective:** Freeze economically interpretable Expansion Runner and Session Monster definitions.

**Dependencies:** QC2-015, QC2-016, QC2-026, QC2-073, QC2-074  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Development-only event-rate/threshold/horizon studies and action/missingness effects.
- Label Registry with primary/secondary thresholds and any persistence conditions.
- Minimum-event feasibility and target-overlap analysis.

**Required tests:**

- Labels match independent formula calculations and split invariance.
- Definition choice does not maximize held-out model performance.
- Expected rare-event volume is reported honestly for the planned 90 sessions.

**Task-specific forbidden actions:**

- Do not rewrite thresholds after qualification or equate one-session gap and multiday expansion.

**Acceptance gate:** Targets are exact, viable enough to test or explicitly blocked, and frozen before model qualification.

**Evidence/environment:** REAL_HISTORICAL_DATA  
**Calibration state:** EMPIRICAL_CALIBRATION_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-076 — Feature Calibration

**Objective:** Select useful daily features and lookbacks through nested development evaluation.

**Dependencies:** QC2-014, QC2-033, QC2-034, QC2-035, QC2-036, QC2-073, QC2-074, QC2-075  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Feature search space/budget, missingness and redundancy analysis, ablations.
- Frozen production-compatible Feature Registry candidate set.
- Provisional training results using existing factory/evaluator without Champion registration.

**Required tests:**

- Every selection/transform fit stays inside its fold.
- Performance stability and resource cost compared with simple baselines.
- No qualification rows or future memory members affect selection.

**Task-specific forbidden actions:**

- Do not call provisional development models the operating Champion or amend earlier framework logic silently.

**Acceptance gate:** A reproducible feature selection procedure and bounded candidate set are locked for bootstrap competition.

**Evidence/environment:** REAL_HISTORICAL_DATA  
**Calibration state:** EMPIRICAL_CALIBRATION_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-077 — Runner Protocol Calibration

**Objective:** Choose the active daily protocol subset by contribution, compatibility and robustness.

**Dependencies:** QC2-017, QC2-018, QC2-019, QC2-020, QC2-033, QC2-034, QC2-035, QC2-036, QC2-075, QC2-076  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Development-only per-protocol and joint ablations with search accounting.
- Thresholds, missingness rules and ACTIVE_F0 proposal; rejected/unavailable statuses retained.
- Source lineage and environment/compute compatibility proofs.

**Required tests:**

- No active unresolved source or intraday dependency.
- Protocol benefit is compared on identical splits without winner-only case selection.
- Correlated redundant protocols do not receive undocumented duplicate influence.

**Task-specific forbidden actions:**

- Do not activate every legacy protocol to increase protocol count.

**Acceptance gate:** One documented active-set selection procedure and parameter manifest are ready for bootstrap qualification.

**Evidence/environment:** REAL_HISTORICAL_DATA  
**Calibration state:** EMPIRICAL_CALIBRATION_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-078 — QuantraScore Calibration

**Objective:** Fit/choose deterministic synthesis rules without leaking qualification outcomes.

**Dependencies:** QC2-024, QC2-026, QC2-033, QC2-034, QC2-035, QC2-036, QC2-075, QC2-076, QC2-077  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Nested out-of-fold score calibration with uncertainty/missingness and trap penalties.
- Frozen score candidates tied to compatible model-family/head contracts.
- Predeclared joint model/score selection rule for QC2-082.

**Required tests:**

- In-sample head predictions cannot masquerade as score-calibration holdout.
- Probability versus score remains distinct; safety input prohibited.
- Each candidate replays exactly and has all coefficients/precision frozen.

**Task-specific forbidden actions:**

- Do not select a score by viewing final qualification or pretend a later model can use incompatible fitted score weights.

**Acceptance gate:** Score candidates and the selection procedure are fixed; QC2-082 selects the final pair using development only.

**Evidence/environment:** REAL_HISTORICAL_DATA  
**Calibration state:** EMPIRICAL_CALIBRATION_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-079 — Paper Strategy Calibration

**Objective:** Choose a frozen paper strategy within signed owner limits and daily-data capability.

**Dependencies:** QC2-026, QC2-044, QC2-045, QC2-047, QC2-048, QC2-073, QC2-074, QC2-075, QC2-078  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Owner CapitalPolicy, development-only strategy study and search ledger.
- Entry cap/allocation/exit/hold/re-entry values; gap/no-fill/ambiguous-path rules.
- Liquidity/cost sensitivity and operational order-capability assessment.

**Required tests:**

- No future opening price in decisions; caps cannot be widened by optimizer.
- Ambiguous target/stop ordering receives conservative bounds.
- Scientific labels and no-fill accounting remain independent from strategy selection.

**Task-specific forbidden actions:**

- Do not claim daily backtests establish live fills or activate trading during calibration.

**Acceptance gate:** One strategy/capital manifest is frozen with honest data limitations and all required owner choices resolved.

**Evidence/environment:** REAL_HISTORICAL_DATA, OWNER_CAPITAL_POLICY  
**Calibration state:** EMPIRICAL_AND_OWNER_POLICY_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-080 — Promotion Policy Calibration

**Objective:** Define prospective eligibility and search/decision limits before any official adaptive use.

**Dependencies:** QC2-026, QC2-034, QC2-036, QC2-038, QC2-040, QC2-041, QC2-043, QC2-073, QC2-075, QC2-078, QC2-079  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Historical/Shadow sample and distinct-event minima, effect/calibration/regression gates.
- Frozen comparison method, cooldown, attempt budget, owner-decision timing and compatibility envelope.
- Default frozen-mode behavior and optional pre-registered adaptive policy.

**Required tests:**

- Simulated candidates with leakage, few events, missing sessions or policy drift are rejected.
- False-promotion behavior tested on development/null scenarios.
- A model cannot certify itself by packaging easier gate values.

**Task-specific forbidden actions:**

- Do not pick Shadow duration after seeing a candidate win or permit incompatible scientific changes within F0.

**Acceptance gate:** Promotion policy is fully numeric, justified and executable before prospective model evaluation.

**Evidence/environment:** REAL_HISTORICAL_DATA, OWNER_MODE_POLICY  
**Calibration state:** EMPIRICAL_CALIBRATION_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-081 — F0 Statistical Closure Calibration

**Objective:** Freeze the full primary analysis, sample sufficiency and stopping rules before F0.

**Dependencies:** QC2-026, QC2-034, QC2-073, QC2-074, QC2-075, QC2-078, QC2-080  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- StatisticalAnalysisPlan with primary paired Precision@10 effect/comparator and 0.05 one-sided alpha.
- Practical effect, event/block minima, block method/length, coverage/reliability/missingness rules.
- Power/coverage study, multiplicity plan, maximum scheduled and maturation windows, exact closure algorithm.

**Required tests:**

- Known dependent null/alternative simulations assess interval coverage and power.
- Ninety sparse sessions and straddling intervals yield INSUFFICIENT_EVIDENCE.
- No positive-result-driven extension, outcome-dependent exclusion or undefined ratio.

**Task-specific forbidden actions:**

- Do not treat symbol-days as independent or select analysis settings using F0/locked qualification outcomes.

**Acceptance gate:** All decision parameters are resolved and justified; infeasible evidence requirements block activation rather than get weakened.

**Evidence/environment:** REAL_HISTORICAL_DATA, STATISTICAL_SIMULATION_EVIDENCE  
**Calibration state:** EMPIRICAL_CALIBRATION_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-082 — Bootstrap Champion Competition

**Objective:** Select one bootstrap contender fairly using only development evidence.

**Dependencies:** QC2-022, QC2-033, QC2-034, QC2-035, QC2-036, QC2-073, QC2-074, QC2-075, QC2-076, QC2-077, QC2-078, QC2-081  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Equal-budget required-family comparison and complete trial ledger.
- Nominated immutable model/score pair under the frozen selection/tie rule.
- Full provenance, calibration and resource/replay qualification package.

**Required tests:**

- Same folds/targets/universe and head semantics for compared families.
- Simpler model tie preference follows predeclared tolerance.
- Locked historical qualification remains unopened before nomination.

**Task-specific forbidden actions:**

- Do not compare families on different favorable windows or select from qualification results.

**Acceptance gate:** Exactly one nominated artifact/pipeline exists with a development-only selection receipt.

**Evidence/environment:** REAL_HISTORICAL_DATA  
**Calibration state:** CALIBRATION_SELECTION_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-083 — Bootstrap Champion Qualification

**Objective:** Evaluate the already nominated contender once on the locked historical qualification period.

**Dependencies:** QC2-036, QC2-039, QC2-041, QC2-073, QC2-081, QC2-082  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Independent qualification report, holdout-access/consumption receipts.
- Leakage/replay/calibration/coverage/resource gates and dataset-fidelity limits.
- Final immutable bootstrap artifact package or explicit rejection.

**Required tests:**

- Recompute every required gate independently and verify training excludes qualification.
- Failed qualification cannot be repaired by tuning on the same report and reusing it as untouched.
- Any limited historical scope is displayed and consistent with approved claims.

**Task-specific forbidden actions:**

- Do not hide failures, choose another model using the same holdout as if untouched, or automatically retrain through the holdout.

**Acceptance gate:** Nominated candidate passes all frozen gates, or task is BLOCKED pending a valid new evidence plan.

**Evidence/environment:** REAL_HISTORICAL_DATA, INDEPENDENT_EVALUATOR  
**Calibration state:** LOCKED_QUALIFICATION_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-084 — Register F0 Reference Champion

**Objective:** Register the qualified initial model and an immutable Reference role without starting F0.

**Dependencies:** QC2-037, QC2-039, QC2-041, QC2-042, QC2-043, QC2-053, QC2-055, QC2-061, QC2-083  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Verified bootstrap transition from NO_CHAMPION with exact owner authorization.
- Operating pointer, immutable F0 Reference binding, worker-load receipt and retained artifacts.
- Model/score/registry compatibility proof and recovery path.

**Required tests:**

- Bootstrap cannot overwrite existing Champion or use fixture identity.
- Reference role cannot change after freeze; repeated registration is idempotent.
- Correct artifact is loaded and replayed before readiness.

**Task-specific forbidden actions:**

- Do not count predictions, start the official epoch or enable paper orders here.

**Acceptance gate:** The exact qualified artifact is registered, independently verifiable and ready for epoch binding.

**Evidence/environment:** OWNER_SIGNED_BOOTSTRAP, REAL_ANDROID_DEVICE  
**Calibration state:** QUALIFIED_ARTIFACT_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-085 — F0 Epoch Manifest

**Objective:** Freeze the complete experiment and all activation-relevant policy references.

**Dependencies:** QC2-010, QC2-050, QC2-051, QC2-052, QC2-065, QC2-066, QC2-067, QC2-074, QC2-075, QC2-076, QC2-077, QC2-078, QC2-079, QC2-080, QC2-081, QC2-084  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- EpochManifest binding regime, calendar, universe, registries, model/Reference, strategy and mode.
- Scientific/operational deadlines, anchor policy, budgets, RPO/RTO, stats and stopping rules.
- Scheduled-attempt plan, owner acknowledgment and zero-unresolved-required-decision report.

**Required tests:**

- Manifest rejects fixture policies, unresolved values, incompatible hashes or absent trust roots.
- Frozen/adaptive mode behavior and comparator identity are unambiguous.
- Changing any scientific authority requires a new manifest/epoch.

**Task-specific forbidden actions:**

- Do not start collecting official sessions or edit the manifest after freeze.

**Acceptance gate:** Every required empirical, owner, capability and engineering value is resolved and content-addressed.

**Evidence/environment:** OWNER_EPOCH_ACKNOWLEDGMENT, CALIBRATED_REAL_MANIFESTS  
**Calibration state:** ALL_ACTIVATION_PARAMETERS_RESOLVED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-086 — Complete F0 Dry Run

**Objective:** Exercise the entire deployed path prospectively with real future outcomes before formal F0.

**Dependencies:** QC2-039, QC2-043, QC2-047, QC2-049, QC2-050, QC2-051, QC2-052, QC2-057, QC2-061, QC2-065, QC2-066, QC2-068, QC2-069, QC2-070, QC2-071, QC2-085  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Measured unattended deployment manifest; real snapshot→prediction→on-time independent anchor→mature outcome lineage.
- Real device approval/pause/recovery, backup/restore, and dedicated-account paper execution/reconciliation evidence.
- Dry-run incident report and proof that its sessions remain outside the official F0 cohort.

**Required tests:**

- Observe actual required 1/3/5/10-session maturity; historical replay cannot substitute.
- Authorized dedicated paper-account order/cancel/fill/no-fill behavior and timeout/restart recovery.
- Complete numerical replay, report totals, alerting, deadlines and resource ceilings under actual hosting.

**Task-specific forbidden actions:**

- Do not fabricate elapsed sessions, trade without explicit sandbox authorization or count dry-run outcomes toward F0.

**Acceptance gate:** All real integration gates pass; missing credentials/device/anchor authorization or waiting for maturity remains BLOCKED.

**Evidence/environment:** REAL_MARKET_DATA, ALPACA_CREDENTIALS, INDEPENDENT_ANCHOR_ACCESS, REAL_ANDROID_DEVICE, OWNER_SANDBOX_PAPER_TEST_AUTHORIZATION  
**Calibration state:** FROZEN_MANIFEST_REQUIRED  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-087 — F0 Architecture Audit

**Objective:** Audit the actual calibrated deployed system against this specification before activation.

**Dependencies:** QC2-002, QC2-003, QC2-072, QC2-083, QC2-084, QC2-085, QC2-086  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Invariant/requirement/task-evidence traceability and complete configuration/artifact inventory.
- No-critical-drift report covering science, permissions, real capabilities and restore.
- Activation checklist with unresolved risks and source-verified readiness.

**Required tests:**

- Independent review of the deployed commit versus accepted receipts and frozen hashes.
- No alternate ranker, live path, stale credentials, future leakage or unresolved required value.
- Re-run only gates affected by calibration/integration changes; do not substitute document existence for behavior.

**Task-specific forbidden actions:**

- Do not waive scientific or authority blockers to meet a date.

**Acceptance gate:** No unresolved critical/high scientific, security or execution defect; every activation requirement has actual evidence.

**Evidence/environment:** INTEGRATED_DEPLOYMENT_EVIDENCE  
**Calibration state:** ALL_PRIOR_GATES_VALID  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.

### QC2-088 — F0 Activation

**Objective:** Begin the official forward cohort only under explicit exact-manifest owner authorization.

**Dependencies:** QC2-006, QC2-025, QC2-026, QC2-043, QC2-049, QC2-053, QC2-055, QC2-065, QC2-084, QC2-085, QC2-086, QC2-087  
**Authorized legacy references:** None.  
**Reference intake:** None. Do not inspect or copy legacy code for this task without a scoped amendment.

**Required deliverables:**

- Signed activation request/receipt, prospective start session and active immutable epoch pointer.
- Fresh readiness/account/reconciliation/checkpoint checks and scheduled jobs.
- First-attempt monitoring and owner-visible active mode/strategy status.

**Required tests:**

- Activation cannot backdate its cohort or reuse a stale manifest approval.
- Duplicate activation is idempotent; changed hash/state requires a fresh authorization.
- Any failed gate keeps the epoch inactive and paper exposure disabled.

**Task-specific forbidden actions:**

- Do not treat task registry creation, spec approval or a successful dry run as activation authorization.

**Acceptance gate:** Exact authorized epoch becomes active prospectively with complete evidence; F0 success is not yet claimed.

**Evidence/environment:** EXPLICIT_OWNER_F0_ACTIVATION_AUTHORIZATION, PRODUCTION_READINESS  
**Calibration state:** ALL_PRIOR_GATES_VALID  
**Initial status:** TODO. **Blockers:** none assessed; required inputs must be verified when the task begins. **Acceptance receipt:** absent; no work is certified complete.


## 39. Phase acceptance boundaries

| Boundary | Required result | What it does not authorize |
| --- | --- | --- |
| PREBUILD_REGISTRY | 89 verified task records, dependency graph and contradiction report | Starting QC2-000 |
| QC2-000–011 | Reproducible foundation and genuine acquisition/evidence slice | Predictions, training claims, official F0 sessions or paper orders |
| QC2-012–026 | Parameterized scientific pipeline, independent labels and validation mechanics | Use of uncalibrated settings as production policy |
| QC2-027–039 | Temporally safe research, independent evaluation, Shadow and exact replay | Self-promotion or retrospective claims of forward foresight |
| QC2-040–056 | Controlled promotion/execution/identity/API frameworks | Passing real integration on fixture evidence |
| QC2-057–072 | Real owner interface, recoverability and hostile/regression suites | Assuming empirical predictive advantage |
| QC2-073–083 | Real calibration, locked selection and bootstrap qualification | Reusing consumed qualification as untouched evidence |
| QC2-084–087 | Exact model/epoch freeze, real prospective dry run and activation audit | Official collection or paper execution without the specified authorizations |
| QC2-088 | Authorized prospective F0 start | A claim of successful F0, paid-data purchase or live trading |

Within a phase, the same one-task-at-a-time rule applies. A phase summary cannot replace individual task receipts. Passing a structural test does not satisfy a scientific, device, provider, or restore gate requiring different evidence.

## 40. Mandatory pre-activation checklist

F0 activation is forbidden unless all of the following are true and evidenced in the immutable activation request:

- All 89 task records exist; QC2-000 through QC2-087 have current passing acceptance receipts and no dependent gate is awaiting revalidation.
- The exact deployment/source/environment is identified and the actual host has demonstrated unattended scheduling, storage durability, isolation, and bounded resources.
- Every required unknown decision is resolved under the correct decision class. No fixture manifest or unresolved parameter appears in production dependency closure.
- Actual selected Alpaca feed, history, data semantics, finalization, calendar, corporate-action and classification capabilities support the stated scope. Provider defaults and runtime fallback are absent.
- The instrument census and eligibility/coverage rules are frozen. Historical limitations remain disclosed; no current survivor list is represented as complete past membership.
- Feature, label, protocol, score, model, memory, baseline, strategy, promotion and statistical manifests are compatible, retained, and immutable.
- Required model heads are available and calibrated under their exact labels. Optional heads clearly indicate unavailable state.
- The initial Champion was nominated before locked qualification, qualified independently, safely loaded, registered by exact authority transition, and retained as the frozen Reference.
- The F0 mode is explicitly selected. Adaptive mode, if chosen, has an exact predeclared learning/promotion/search/owner-decision policy; frozen mode prevents within-epoch promotion.
- Scientific seals, qualification deadlines, and independent pre-outcome checkpoints were demonstrated in a real prospective dry run.
- All required 1/3/5/10-session dry-run outcomes actually matured, missingness/action handling behaved correctly, and full scientific replay matched.
- Owner enrollment, challenge signing, revocation, recovery, stale-state denial, pause/resume request, and exact-model review worked on a real Android device.
- Paper account identity, authorized capital, reservations, order-type semantics, partial fills, uncertainty recovery, and reconciliation were tested under explicitly authorized dedicated-account conditions.
- New-entry versus exit/cancel gates are separately verified. Unknown state cannot create duplicate exposure, false fills, or an implicit short.
- Backup and isolated restore met owner recovery objectives, detected rollback against independent evidence, and did not replay stale broker actions.
- Retention closure is complete; quotas and cost budgets support the frozen window; research cannot starve production deadlines.
- No unresolved critical/high integrity, leakage, authorization, execution, or recovery defect remains. Lesser limitations have explicit nonconflicting disposition and are visible in the activation report.
- The owner signs the exact epoch/manifest/starting-session activation request. The server independently rechecks readiness and commits prospectively.

If a required evidence source is unavailable, activation is BLOCKED. A smaller valid declared experiment may be proposed through an amendment, but the agent must not quietly relabel a weaker experiment as satisfying this one.

## 41. First Replit instruction — exact handoff

Use the following assignment after placing this document at `docs/GEN2_MASTER_SPEC.md`:

```text
Read docs/GEN2_MASTER_SPEC.md completely, including all 89 canonical task definitions and the final activation/interpretation sections. If the tool truncates the file, continue reading until every section is read.

Do not implement QuantraCore yet. Do not begin QC2-000.

Your assignment is PREBUILD_REGISTRY only. Create or validate the project's official task-management records and docs/BUILD_TASKS.md plus registry/BUILD_TASKS.json for QC2-000 through QC2-088 inclusive.

If the supplied package already contains these files, reconcile them against the master specification; do not mark them implemented or create duplicate tasks.

Preserve exactly 89 canonical task IDs, names, scopes, consecutive execution order and explicit dependencies. Every task after QC2-000 depends on its immediate predecessor in addition to its listed technical prerequisites. All earlier tasks must be PASS before a later task starts. Do not merge, delete, rename, reorder or broaden canonical tasks.

For every task record objective, dependencies, authorized legacy sources, required Reference Intake, deliverables, tests, forbidden actions, acceptance gate, required evidence/environment, calibration dependency, initial TODO status, blockers and absent acceptance receipt.

Exactly one canonical task may be IN_PROGRESS once implementation is later authorized. Subtasks are allowed only beneath that task. Do not run or implement future canonical tasks in the background.

The QC2-001 logical reference roles—QuantraCore production/core, ApexLab research/training, and original QuantraCore runner-protocol lineage—are read-only. A role can map to overlapping repositories, paths, or later revisions only when exact identity and provenance limits are recorded; the role names do not prove Gen 1, original-lineage, or production-release identity. Never modify reference sources or import their runtime modules. Do not infer meanings from protocol numbers. Missing or unproven lineage stays explicitly unverified.

Do not invent empirical, owner-risk, provider-capability or engineering-limit values. Record each unresolved decision with its correct class and activation consequence. Fixture policies are test-only and cannot enter production manifests.

Do not implement live trading, provider/feed fallback, a second official ranking, manual mobile trading, an external Lamont Labs dependency, paid services or deployment activation.

Respect the corrected sequencing: QC2-011 is real acquisition/evidence only; complete prospective prediction/outcome integration is QC2-086. Earlier owner-approval tasks are fixture frameworks until real enrollment/security gates pass. Calibration selects a contender before locked qualification. F0 starts only with exact explicit owner activation authorization at QC2-088.

Validate the task registry mechanically and report:
1. Exact canonical count and every ID in topological execution order.
2. Dependency table and any cycle, missing ID, duplicate, forward prerequisite or omitted immediate predecessor.
3. Tasks using Gen 1 QuantraCore, ApexLab, and original protocols.
4. Tasks requiring real data, credentials/external access, Android devices, owner policy or explicit authorization.
5. Framework tasks that can pass on fixtures, and later gates requiring real evidence.
6. Tasks dependent on empirical calibration and unresolved decision classes.
7. Any actual contradiction or missing prerequisite found, citing both affected requirements.
8. Confirmation that no canonical task is IN_PROGRESS or PASS and no domain implementation or external activation occurred.

If an actual contradiction remains, record it and stop; do not silently weaken or reinterpret a requirement. Proposed corrections must be concrete and reviewable.

Stop after the registry and validation report. Do not begin QC2-000 until explicitly instructed.
```

## 42. Source register and external facts

External documentation was checked on October 6, 2026. It supports the narrow facts listed below, not a claim that the user's account has those capabilities. The system must still probe actual behavior. This specification's architecture, thresholds-to-be-calibrated, state machines, and task requirements are design decisions, not representations that a provider endorses them.

| Ref | Primary source | Fact used and engineering consequence |
| --- | --- | --- |
| S1 | [Alpaca Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) | IEX/SIP distinction, historical access behavior, symbol mapping and condition-dependent daily aggregation; explicit feed/semantics and actual entitlement probe. |
| S2 | [Alpaca Historical Bars](https://docs.alpaca.markets/us/reference/stockbars) | Symbol-first ordering, pagination, explicit adjustment and symbol-as-of fields; full request provenance and pagination verification. |
| S3 | [Alpaca Corporate Actions](https://docs.alpaca.markets/us/reference/corporateactions-1) | Action availability may lag; absent records cannot prove no action and corrections need temporal provenance. |
| S4 | [Alpaca Paper Trading](https://docs.alpaca.markets/us/docs/paper-trading) | Separate paper endpoint/credentials and simulation limitations; retain distinct scientific/proxy/paper execution evidence. |
| S5 | [Alpaca Placing Orders](https://docs.alpaca.markets/us/docs/orders-at-alpaca) and [Alpaca official Python client](https://github.com/alpacahq/alpaca-py/blob/master/alpaca/trading/client.py) | Order lifecycle/client operations are provider-specific; test current semantics, never assume transactional exactly-once delivery. |
| S6 | [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | Privileged and owner bypass behavior; runtime roles need grants, ownership separation and negative permission tests. |
| S7 | [scikit-learn Common Pitfalls](https://scikit-learn.org/stable/common_pitfalls.html) | Test data must not train preprocessing/selection; fold-scoped learned transforms. |
| S8 | [scikit-learn Model Persistence](https://scikit-learn.org/stable/model_persistence.html) | Pickle-based deserialization can execute arbitrary code; no arbitrary production unpickling. |
| S9 | [Bailey, Borwein, López de Prado and Zhu: The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) | Selection across many backtests is part of overfitting risk; complete search history and protected qualification. |
| S10 | [Android Keystore System](https://developer.android.com/privacy-and-security/keystore) | Nonexportable key facilities and device-dependent hardware support; measure key security level and use explicit user authentication. |
| S11 | [Alpaca Calendar SDK reference](https://alpaca.markets/sdks/python/api_reference/trading/calendar.html) | Calendar responses include actual market open/close times and early closures; pin calendar observations rather than assume fixed hours. |

Documentation links are informational input. Changes in documentation, an API default, SDK behavior, or subscription do not automatically amend the frozen experiment. The relevant capability is remeasured and any required scientific change follows the amendment/epoch rules.

## 43. Implementation honesty and final governing rule

This document intentionally leaves unresolved empirical and owner-policy decisions as typed blockers until the designated tasks produce evidence. Filling those records with arbitrary numbers would weaken the specification, not complete it. Architectural omissions have been filled here; unknowable account facts and unmeasured strategy advantages have not been fabricated.

No requirement to preserve auditability authorizes unnecessary infrastructure expansion. Build the smallest implementation that actually enforces the defined boundaries. Conversely, a low budget is not permission to mislabel local hash chaining as independent timestamp proof, paper fills as live liquidity, historical survivors as a complete historical universe, or successful code execution as predictive intelligence.

The final governing rule is: **preserve what happened, preserve what was knowable, preserve who had authority, and make every claim no stronger than the evidence that can be independently reconstructed.**
