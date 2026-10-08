# Science

Reserved for deterministic scientific transformations over explicit,
versioned inputs. Keep this boundary side-effect free and independent of
network, persistence, and execution.

QC2's feature authority lives in `src/qc2_science/`. It consumes frozen,
content-addressed bars, calendar sessions, instrument/assignment references,
and adjustment manifests. It does not fetch data or read labels. Historical
similarity prototypes require caller-supplied temporal-access evidence and
must be known by the decision cutoff. Every ordered snapshot row carries its
unit and output data type, followed by exactly one type-conforming value or
explicit missing reason.

`fixture_daily_v1` is synthetic-only. Its empirical windows cannot be
activated in production; only windows explicitly fixed by the master
specification are non-parameterized. See
`docs/reference/QC2-014_DECISION.md` for formulas and constraints and
`docs/reference/QC2-014_REFERENCE_INTAKE.md` for legacy-source limits.

Deterministic comparator rankings live in `src/qc2_science/baselines.py`.
They consume validated `UniverseManifest` and `FeatureSnapshot` records without
reading labels or outcomes. Calibration windows are explicit in each baseline
manifest and require a `ConfigurationManifest` reference; synthetic parameters
are limited to the test environment, and these rankers have no production
activation path. Midrank percentiles, stable-instrument-ID score ties, and
reporting K conventions are shared through the science package API. See
`docs/reference/QC2-022_ACCEPTANCE_ASSESSMENT.md` for the equations and limits.

QuantraScore synthesis lives in `src/qc2_science/quantscore.py`. A content-
addressed `ScoreManifest` pins the immutable `ScoreDefinition`; its ordered
coefficients, selectors, transforms, missing-value policy, clipping rule, and
stable instrument-ID tie break fully determine the output. The score is
`100 × Σ(coefficient × transformed input)`, quantized to six decimal places
with round-half-even. The Expansion Runner probability is validated against
its exact label and kept separately at twelve decimal places. Protocol evidence
selectors pin their expected unit and direction. Uncertainty is a nonpositive
penalty; safety protocol records cannot bind as inputs. Missing required data is
reason-coded and cannot silently score. Fixture parameters are synthetic-only; all other parameter
sets are uncalibrated, and neither class can enter a production epoch. These
examples specify mechanics only and do not set empirical weights.
