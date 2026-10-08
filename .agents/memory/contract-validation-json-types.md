---
name: Contract validation JSON types
description: Preserve JSON Schema compatibility when validating immutable contract records.
---

Convert immutable or generic collection wrappers to built-in `dict` and `list` values before calling the QC2 contract validators. Freeze records only after validation.

**Why:** The project's JSON Schema runtime recognizes built-in JSON object/array containers; `MappingProxyType` and tuples can fail `object`/`array` checks despite implementing mapping or sequence interfaces.

**How to apply:** When an authority stores immutable snapshots, thaw all nested values before `validate_contract` or `validate_contract_collection`, then freeze validated copies for internal use.

Content-addressed fixture contracts used as adapter inputs must carry hashes computed from their final canonical payloads, not schema-valid placeholder digests.

**Why:** Structural schema validity does not establish content integrity; reference-closure validation verifies the exact target content hash.

**How to apply:** Finish a dependency contract first, compute and verify its canonical content hash, then construct any references to it.

`TemporalArtifact.content_hash` and a content-addressed contract's `content_hash` are separate digests. The former hashes the canonical serialized full contract; the latter follows the contract-specific canonical payload rules.

**Why:** Comparing these digest fields directly rejects valid references because they cover different bytes and use different hash domains.

**How to apply:** Verify a typed reference against the payload's contract `content_hash`, then validate `TemporalArtifact.content_hash` independently against the canonical serialized payload.
