---
name: Contract validation JSON types
description: Thaw immutable containers before JSON Schema validation or canonical JSON encoding.
---

Convert immutable or generic collection wrappers to built-in `dict` and `list` values at JSON boundaries, including before QC2 contract validation and canonical hashing. Freeze records only after validation.

**Why:** The project's JSON Schema runtime and canonical JSON encoder require built-in JSON object/array containers; `MappingProxyType` and tuples can fail validation or hashing despite implementing mapping or sequence interfaces. Snapshot hashing also fails if immutable tuple collections are passed through unchanged.

**How to apply:** When an authority stores immutable snapshots, thaw all nested values before validation or canonical serialization, then freeze validated copies for internal use.

Content-addressed fixture contracts used as adapter inputs must carry hashes computed from their final canonical payloads, not schema-valid placeholder digests.

**Why:** Structural schema validity does not establish content integrity; reference-closure validation verifies the exact target content hash.

**How to apply:** Finish a dependency contract first, compute and verify its canonical content hash, then construct any references to it.

`TemporalArtifact.content_hash` and a content-addressed contract's `content_hash` are separate digests. The former hashes the canonical serialized full contract; the latter follows the contract-specific canonical payload rules.

**Why:** Comparing these digest fields directly rejects valid references because they cover different bytes and use different hash domains.

**How to apply:** Verify a typed reference against the payload's contract `content_hash`, then validate `TemporalArtifact.content_hash` independently against the canonical serialized payload.
