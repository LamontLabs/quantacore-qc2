# ApexLab

Research-only boundary for datasets, experiments, and candidate artifacts. It
must not mutate production authority or receive execution credentials.

`qc2_apexlab.RunnerGenomeStore` is an append-only in-memory reference
implementation. It validates RunnerGenome and MemoryIndexManifest contracts,
keeps actual creation and learning times distinct from explicit reconstructed
availability assumptions, and routes each lookup through the temporal firewall.
It is not a durable database adapter and does not enable production learning,
similarity ranking, or trading.

An empty `prediction_refs` list means no contemporaneous prediction is
represented; the store never fabricates or backfills one. The index binds its
cutoff, builder version, exact member refs, and optional embedding artifact into
content-addressed replay dependencies.

`qc2_apexlab.FailureGenomeStore` adds append-only failure memories using the
existing `FailureGenome` contract. Its explicit taxonomy maps `FALSE_MONSTER`
to non-event, `COLLAPSE` to downside, `DATA_ERROR` to data-error, and
`TIMING_MISS` to timing-miss; `MISSED_RUNNER` remains a separate positive-truth
miss category. A curated failure type is never inferred from realized returns
or runner probability. Creation requires an independent `EvidenceEvent`, a
resolved Outcome, and valid endpoint, extrema, MFE, and MAE fields. A data-error
memory also requires an `OutcomeRevision`, so unresolved records cannot become
negative training examples. Data-error memories are diagnostic-only,
missed-runner memories preserve positive ground truth, and the other three
categories are exposed as category-specific negative training examples only
after a cutoff-eligible lookup.

Corrections append a new FailureGenome with the next `curation_version` and a
source reference to its prior version. Outcome changes additionally require an
`OutcomeRevision` linking the prior and replacement outcomes. Existing records
and indexes remain unchanged; each failure index selects the latest version
available at its exact cutoff and binds `index_kind`, builder version, cutoff,
and member hashes into replay lineage. Historical reconstruction continues to
require separate explicit actual and assumed availability.
