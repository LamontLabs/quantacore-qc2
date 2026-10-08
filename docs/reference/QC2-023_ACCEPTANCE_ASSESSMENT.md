# QC2-023 — Model Inference Contract acceptance assessment

## Acceptance assessment

- **Result:** PASS
- **Evidence class:** `SYNTHETIC_FIXTURE`
- **Environment:** `test`
- **Scope:** Loads one exact, hash-pinned model artifact and computes typed logical-head outputs from a validated feature snapshot. It does not train or discover models, select a Champion, access providers or networks, submit orders, or activate fixture outputs.
- **Safe format:** Only `qc2_safe_linear_json_v1` is allowlisted. The canonical one-file JSON format supports declarative linear and logistic heads; unsupported operators and executable serialization formats fail closed. Evaluation runs in a subprocess with bounded CPU, memory, file size, descriptor count, and wall time.
- **Bindings:** Model, artifact manifest, artifact bytes, feature registry and definitions, labels, feature order, environment fingerprint, and package lock are checked against their exact identities and hashes. A caller-supplied pinned pointer must select the loaded manifest; its generation is recorded in the receipt. The inference interface does not choose or promote a model.
- **Head behavior:** The primary Expansion Runner probability must be available. Optional unavailable-label and unavailable-model heads remain typed with null values and explicit reasons. Invalid outputs, including out-of-range probabilities, remain `INVALID` with null values rather than being coerced to zero.
- **Determinism:** Registered feature order and fixed probe expectations are checked. The isolated worker evaluates each request twice; mismatched results or probes fail closed. The receipt binds the artifact hash, pointer generation, environment, probe set, and output projection.
- **Boundary:** This is local synthetic-fixture evidence for the safe linear/logistic representation only. It makes no empirical performance, model calibration, production-readiness, or live-trading claim. No authorized legacy source was inspected; see `docs/reference/QC2-023_REFERENCE_INTAKE.md`.
- **Verification:** The 14 focused inference tests and 260-test project suite passed, as did lint, bytecode compilation, whitespace checking, and task preflight. The acceptance workflow performs registry validation after generating the acceptance records.

## Acceptance checklist

- [x] DELIVERABLE: Model/head compatibility interface, safe-format allowlist and isolated loader. | evidence: `packages/science/src/qc2_science/model_inference.py`; `packages/science/src/qc2_science/model_inference_worker.py`; `tests/science/test_model_inference.py`
- [x] DELIVERABLE: Primary/optional head states, feature order checks, inference receipt. | evidence: `infer_exact_artifact`; `test_exact_safe_artifact_emits_repeatable_typed_heads_and_receipt`; `test_unavailable_label_head_remains_null_and_typed`
- [x] DELIVERABLE: Environment fingerprint and deterministic probe framework. | evidence: `compute_environment_fingerprint`; repeated worker evaluation and probe verification in `infer_exact_artifact`; `test_probe_mismatch_fails_closed`
- [x] TEST: Reject unsafe serialization, wrong feature order, invalid probability, oversized model and unsupported operators. | evidence: `test_unsafe_serialization_format_is_rejected_before_worker`; `test_exact_artifact_rejects_wrong_feature_order`; `test_invalid_probability_is_typed_invalid_not_zero`; `test_oversized_artifact_is_rejected_before_worker`; `test_unsupported_operator_is_rejected`
- [x] TEST: No training/network access during load/inference. | evidence: `test_worker_has_no_training_or_network_imports_and_runs_isolated`
- [x] TEST: Unavailable optional heads stay typed and do not become zero. | evidence: `test_exact_safe_artifact_emits_repeatable_typed_heads_and_receipt`; `test_unavailable_label_head_remains_null_and_typed`

