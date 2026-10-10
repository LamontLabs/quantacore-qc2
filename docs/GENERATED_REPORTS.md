# QC2 Generated Reports

`qc2_reporting` builds Daily Runner, Weekly Learning, Missed Monster, False
Monster, Promotion, F0 Validation, and Integrity reports from source artifacts
provided by their owning authorities. Report kinds share a deterministic
renderer; each report still declares its own kind, period, sources, and metric
definitions.

## Evidence and metrics

Every metric must resolve through `MetricRegistry` to a schema-valid
`qc2.validation.MetricDefinition.v1` plus an explicit numerator field,
denominator field, and eligible source schemas. The engine recomputes totals
from validated source contracts; when a source result names a metric
definition, its reference must match the registered definition. The engine
does not accept caller-supplied totals.

The machine-readable report contains:

- Immutable source references, including the source artifact hash and a hash
  of the exact rows used.
- The registered metric-definition ID, version, unit, estimand, formula paths,
  contributing sources, recomputed numerator/denominator, and row count.
- Scope limitations, evidence classes, period, provisional/final status, and a
  report hash.

`ReportSource` validates each complete source object against its registered
contract schema and verifies content hashes when the source contract carries
one. The owning authority selects the scope label. The report binds the exact
contract rows with `row_snapshot_hash`; a consumer can resolve the source
reference and recompute totals rather than trusting a caller-provided value.
The report and amendment envelopes also have explicit runtime shape checks;
recomputing a hash over a malformed envelope does not make it publishable.

`render_markdown` renders those recorded values and limitations without
generating evidentiary prose. A report based on synthetic or reconstructed
evidence, survivor-limited research, paper execution, or a zero denominator is
provisional. Survivor-limited research and paper fills are explicitly not
operational proof.

## Corrections

`ReportLedger.publish` stores canonical report bytes append-only. Publishing a
later version under the same report key requires an amendment reason. The
earlier report remains available; the new revision records the superseded
report hash and an amendment identifies corrected source references and impact.
Callers persist the ledger's report and amendment records through their owning
authority rather than editing an already-published report.
