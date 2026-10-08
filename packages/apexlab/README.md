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
