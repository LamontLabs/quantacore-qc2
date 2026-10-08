# QC2-017 — Runner Protocol Framework decision

## Boundary

Runner Protocols are deterministic structural-hypothesis evaluations, not action authorities. Their persisted owner is `runner_protocol`; their definitions, registry, result-state enum, runtime APIs, and active keys are distinct from Safety Protocols. Registry keys include namespace, ID, and version (`namespace:id:vN`), so matching bare IDs do not merge meanings.

## Evaluation language and worker

- A definition binds a hypothesis, direction, regime, typed input requirements, parameter references and values, a declarative expression, and explicit outcomes for both a match and a non-match. Its stored implementation hash covers the complete deterministic evaluation specification, including bound parameter values and references; the result also carries the separate parameter hash.
- Expressions use a closed JSON operator set over exact decimals and booleans. Python source, callables, imports, loops, arbitrary attributes, and arbitrary names are not accepted.
- Inputs are frozen typed records. Every required key must be present exactly once, bind the declared contract reference and unit, and be known at or before the supplied cutoff.
- Evaluation runs in a child interpreter started with `-I -S`, a minimal environment, and CPU, address-space, file-size, core-dump, and open-file limits. The child receives bounded JSON only, reads no arbitrary protocol files, has no application import path, and returns a boolean or a visible failure code.
- The worker caps request bytes, expression depth, nodes, input count, and evaluation steps. The parent also enforces a deadline. A timeout, resource limit, invalid response, or rejected expression becomes `UNAVAILABLE` with a `reason_code`; it never becomes `PASS`.

The process runs only the trusted declarative interpreter. Migrated legacy Python is not imported, evaluated, or executed in the worker. The operator allowlist and hostile-expression tests are the enforcement boundary for network, filesystem, clock, global-state, training, and broker attempts; those capabilities are not represented in the expression language.

## Result semantics

- A complete, supported input set evaluates the declared boolean hypothesis. The caller must explicitly configure `on_match` and `on_non_match` as `PASS`, `BLOCK`, or `OBSERVE`; there is no default positive outcome.
- `UNKNOWN` is retained when required evidence is indeterminate.
- `UNAVAILABLE` is used when data is missing or not applicable, or when evaluation cannot safely complete.
- `BLOCK` is only the configured outcome of a matched Runner Protocol hypothesis. It does not authorize a broker veto, order, cancellation, or other safety action.
- `reason_code` is returned by the in-process evaluation envelope for input and worker outcomes. The v1 `RunnerProtocolResult` contract has no reason-code field, so no unsupported contract field was added. The persisted result still carries state, hypothesis, direction, evidence values, uncertainty, missingness, hashes, cutoff, and input references.

## Contracts and fixtures

The implementation uses the existing strict v1 `RunnerProtocolDefinition`, `RunnerProtocolRegistry`, and `RunnerProtocolResult` contracts. Definitions and registries are content-addressed; results are not, matching the contract catalog. Active IDs are stored as namespace-qualified keys.

The built-in examples use only the `fixture` namespace, `SYNTHETIC_FIXTURE` evidence, and the `test` environment. Production registry materialization rejects synthetic evidence. QC2-017 grants no production activation at all: even a forward-labeled definition is rejected until a later calibration and owner-approval authority supplies evidence. The demonstration thresholds are not calibrated and do not activate any legacy protocol.

The runtime currently accepts concrete `FeatureSnapshot` and `DailyBar` references as definition inputs. It does not treat a `FeatureDefinition` reference as a runtime value and does not widen the contract's allowed input types.

## Legacy disposition

No original protocol source file was fetched, imported, modified, or executed for QC2-017. The prior QC2-001 manifest and decision record were reviewed for provenance and boundary constraints. They leave historical origin unresolved, record T24/T25/T34 documentation/source conflicts, and do not establish production permission. See `QC2-017_REFERENCE_INTAKE.md`.
