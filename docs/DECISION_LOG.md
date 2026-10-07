# Gen 2 Decision Log

**Record date:** 2026-10-06

**Scope:** Decisions grounded in the governing specification and the accepted
QC2-001 correction. This log does not claim owner signatures unless an exact
signed receipt is separately recorded.

## Recorded decisions

### DEC-001 — Governing precedence

- **State:** `LOCKED_BY_GOVERNING_SPEC`
- **Decision:** An owner-approved constitutional amendment may change only the
  requirements and effective boundary it names. Otherwise the governing
  specification outranks versioned contracts/manifests, accepted task
  specifications, and implementation. Timestamp alone does not grant authority.
- **Basis:** `docs/GEN2_MASTER_SPEC.md` §0.
- **Effect:** Apply `docs/CHANGE_CLASSIFICATION.md`; do not treat this log as a
  higher-level amendment or as owner approval.

### DEC-002 — Private, single-owner product and F0 boundary

- **State:** `LOCKED_BY_GOVERNING_SPEC`
- **Decision:** Gen 2 is private and single-owner. F0 is a daily-OHLCV scientific
  collection and paper-only scope. Live trading, commercialization, multi-
  tenancy, billing, and dependencies on other Lamont Labs systems are outside
  scope unless separately amended.
- **Basis:** `docs/GEN2_MASTER_SPEC.md` §§1, 8, 28, 36.
- **Effect:** No public, multi-user, live-trading, or external-project dependency
  is a production default.

### DEC-003 — No implicit provider or feed fallback

- **State:** `REGIME_RULE_LOCKED; CAPABILITY_AND_FEED_SELECTION_UNRESOLVED`
- **Decision:** Feed choice must be supported by measured account capability and
  explicitly selected before activation. The specification's delayed SIP
  preference and IEX alternative are pre-activation choices, not runtime
  fallback. After selection, lost access causes a failed attempt or hold.
- **Basis:** `docs/GEN2_MASTER_SPEC.md` §§5, 8, 40.
- **Effect:** No feed entitlement, adequacy, or selected feed is claimed here.
  See the capability entries in `docs/UNKNOWN_LEDGER.md`.

### DEC-004 — Frozen Champion is the F0 default

- **State:** `DEFAULT_LOCKED_BY_GOVERNING_SPEC; MODE_NOT_ACTIVATED`
- **Decision:** The default mode is `FROZEN_CHAMPION`. An owner may explicitly
  choose `PRE_REGISTERED_ADAPTIVE` only before activation, with the complete
  learning/promotion policy frozen. Switching modes mid-epoch is forbidden.
- **Basis:** `docs/GEN2_MASTER_SPEC.md` §22 and §40.
- **Effect:** This does not select, qualify, register, or name a Champion.

### DEC-005 — Evidence and scientific integrity outrank paper performance

- **State:** `LOCKED_BY_GOVERNING_SPEC`
- **Decision:** Scientific integrity is evaluated before predictive performance,
  learning effectiveness, paper performance, and paid-data uplift. Positive P&L
  cannot repair invalid evidence or leakage.
- **Basis:** `docs/GEN2_MASTER_SPEC.md` §§1, 21, 39.
- **Effect:** Owner acknowledgment cannot change a machine-computed integrity or
  epoch verdict.

### DEC-006 — Authority owners do not overlap

- **State:** `LOCKED_BY_GOVERNING_SPEC`
- **Decision:** Each canonical state domain has one writer. Label defines
  meaning; Ground Truth computes outcomes. Model Registry owns lifecycle facts;
  Promotion owns the Champion pointer. Validation owns epoch activation.
  Owner API and Android submit narrow requests and are not state authorities.
- **Basis:** `docs/GEN2_MASTER_SPEC.md` §§4, 31; `docs/AUTHORITY_MODEL.md`.
- **Effect:** Runtime grants and procedures must enforce the map; source-code
  naming or interface shape alone is not proof.

### DEC-007 — Execution and exit readiness remain separate

- **State:** `LOCKED_BY_GOVERNING_SPEC`
- **Decision:** A new-exposure pause blocks new exposure and follows the frozen
  pending-entry cancellation policy; it does not imply liquidation. Risk-
  reducing exits may proceed under their narrower prerequisites without a
  healthy Champion or new market snapshot. An unsafe/unrecordable broker
  mutation is not promised.
- **Basis:** `docs/GEN2_MASTER_SPEC.md` §§0, 29–30.
- **Effect:** See contradiction review `CR-EXEC-EXIT` in
  `docs/AUTHORITY_MODEL.md`.

### DEC-008 — Bootstrap and activation are separate transitions

- **State:** `LOCKED_BY_GOVERNING_SPEC`
- **Decision:** Registry existence does not imply a Champion. Bootstrap requires
  an explicit `NO_CHAMPION` expected state and a valid Promotion transition.
  Framework acceptance and task completion never activate F0. Activation is a
  later, prospective, exact-hash owner request independently verified and
  committed by Validation after the complete pre-activation checklist passes.
- **Basis:** `docs/GEN2_MASTER_SPEC.md` §§27, 31, 36, 39–40.
- **Effect:** See contradiction reviews `CR-BOOTSTRAP` and `CR-ACTIVATION` in
  `docs/AUTHORITY_MODEL.md`.

### DEC-009 — Unknowns are typed, not defaulted

- **State:** `LOCKED_BY_GOVERNING_SPEC`
- **Decision:** An unresolved item records its class, reason, affected scope,
  sole responsible authority, evidence needed, and gate consequence. It is not
  represented as a blank, magic zero, guessed value, fixture, fallback, or
  application default.
- **Basis:** `docs/GEN2_MASTER_SPEC.md` §5 and §40.
- **Effect:** No entry in `docs/UNKNOWN_LEDGER.md` authorizes production use.

### DEC-010 — QC2-001 source roles do not establish lineage or reuse rights

- **State:** `SCOPED_QC2-001_CORRECTION`
- **Decision:** QC2-001 mapped three logical source roles to inspectable,
  revision-pinned snapshots. Roles need not correspond to three distinct
  repositories; later snapshots remain role references only when their exact
  identity and provenance limits are recorded. Gen 1 identity, original
  protocol lineage, production deployment, and production authorization remain
  unverified where the evidence did not prove them.
- **Basis:** `docs/reference/QC2-001_DECISION.md` and
  `docs/reference/QC2-001_SOURCE_MANIFEST.md`.
- **Effect:** QC2-002 authorizes no legacy references. This correction neither
  authorizes legacy-code inspection/reuse nor imports a legacy design into the
  runtime.

## Explicitly not decided here

This log does not choose capital limits, a measured feed, hosting capability,
scientific thresholds, feature/protocol/score parameters, promotion criteria,
statistical closure values, engineering budgets, an adaptive F0 mode, a
Champion, or an activation date. Those are typed in
`docs/UNKNOWN_LEDGER.md`; the governing specification's explicit architectural
constants and stated defaults are not relabeled as unresolved. This decision log
does not activate F0.
