# QC2 configuration authority

This package provides pure cross-contract checks for versioned configuration,
scoped capability gates, research/resource limits, change boundaries, and
secret-safe audit output. Callers must validate each object and its typed
references with `qc2_contracts` first.

Configuration settings carry a value hash, authority, provenance class, and
effective session; they never carry a setting value or credential. A
`SecretReference` is a versioned symbolic handle, not a secret. Production
manifests reject synthetic/fixture policy even when a caller reuses a valid
64-character hash.

Capability assessments are independent: a missing or unresolved requirement
blocks only the manifest's narrow `capability_scope`. Resource use is checked
against explicit budgets; no default budget or provider fallback is supplied.
This package has no persistence, network access, secret resolution, or trading
behavior.
