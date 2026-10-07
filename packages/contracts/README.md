# QC2 canonical contracts

This package defines the versioned boundary contracts named in Section 12 of
`docs/GEN2_MASTER_SPEC.md`. The source of truth is
`packages/contracts/src/qc2_contracts/catalog.py`; generated schemas, language
projections, fixtures, and the full field/authority catalog must be changed by
running `tools/generate_contract_package.py`, not by editing generated files.

The contracts define data shape, units, ownership, state guards, immutability,
and typed references. They do not implement persistence, make decisions, enable
fixture values, or provide live provider/trading behavior.

## Validate

From the repository root:

```sh
uv run python tools/generate_contract_package.py --check
uv run pytest -q tests/contracts
pnpm exec tsc --noEmit --strict --target ES2022 --lib ES2022,DOM \
  packages/contracts/src/qc2_contracts/generated.ts \
  packages/contracts/src/qc2_contracts/serialization.ts
kotlinc packages/contracts/android/Qc2WireContracts.kt packages/contracts/android/Qc2WireFixtureSmoke.kt \
  -include-runtime -d /tmp/qc2-wire-fixtures.jar
java -jar /tmp/qc2-wire-fixtures.jar
kotlinc packages/contracts/android/Qc2Serialization.kt \
  packages/contracts/android/Qc2SerializationSmoke.kt \
  -include-runtime -d /tmp/qc2-serialization.jar
java -jar /tmp/qc2-serialization.jar \
  packages/contracts/fixtures/v1/serialization-golden-vectors.properties
```

`qc2_contracts.runtime` provides strict JSON parsing, per-object and
snapshot-level validation, transition and immutable-update guards, and
content-hash verification. Exact decimal values, UUIDv7 identifiers, timestamps,
and session dates remain strings at the wire boundary.

Prices and quantities preserve exact input precision. Probabilities and
registered continuous scientific outputs use 12 decimal places, quantized
round-half-even before hashing; QuantraScore uses 6. The canonical serializer
validates precision without rounding, normalizes negative zero, and applies the
shared QC2-HASH-V1 framing and artifact inventory order. ArtifactManifest
content hashes bind the validated inventory hash and exclude operational
identity, detached signatures, and transport hashes.

Python, TypeScript, and Kotlin canonical encoders run the same golden vectors
from `fixtures/v1/serialization-golden-vectors.properties`. Kotlin wire models
verify Android-visible contract shapes compile, but they are not a general
runtime JSON decoder; an Android app must still test decoding against the
schemas before shipping. Fixtures are synthetic test data, never activation
evidence.

See the generated `docs/reference/QC2-003_CONTRACT_CATALOG.md` for all field
definitions, authority and reader roles, reference targets, state transitions,
and contract invariants.
