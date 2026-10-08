# Promotion bundle packaging

`qc2_promotion` creates and verifies an immutable, content-addressed promotion
bundle. The backend uses Ed25519 with the versioned
`QC2-PROMOTION-BUNDLE-SIGNATURE-V1` profile. Its detached signature covers the
PromotionBundleManifest content hash, the complete inventory hash, the backend
artifact-packager key ID, and separate evaluator and owner identity bindings.

The archive contains exactly three reserved metadata files plus every declared
dependency file. Contract JSON must be canonical QC2 JSON; model data is
restricted to the safe JSON schemas accepted by model-artifact packaging.
Dependency references are resolved transitively, and any undeclared, missing,
mutated, unsafe, expired, oversized, or untrusted content is rejected.

Callers must provide explicit `BundleLimits`, including the maximum lifetime,
archive bytes, unpacked bytes, per-file bytes, entry count, and compression
ratio. There are no package defaults that could become production policy.

The returned `VerifiedPromotionBundle` proves package integrity only. The
artifact-packager signature is not independent eligibility evidence, an
evaluator signature, or owner approval. Promotion verification and owner
authorization remain separate boundaries.
