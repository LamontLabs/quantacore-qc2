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
pnpm exec tsc --noEmit --strict --target ES2022 packages/contracts/src/qc2_contracts/generated.ts
kotlinc packages/contracts/android/Qc2WireContracts.kt packages/contracts/android/Qc2WireFixtureSmoke.kt \
  -include-runtime -d /tmp/qc2-wire-fixtures.jar
java -jar /tmp/qc2-wire-fixtures.jar
```

`qc2_contracts.runtime` provides strict JSON parsing, per-object and
snapshot-level validation, transition and immutable-update guards, and
content-hash verification. Exact decimal values, UUIDv7 identifiers, timestamps,
and session dates remain strings at the wire boundary.

Prices and quantities preserve exact input precision. Probabilities and
registered continuous scientific outputs use exactly 12 decimal places with
round-half-even serialization; QuantraScore uses 6. Negative zero canonicalizes
to zero. The field catalog identifies which representation applies.

The shared Kotlin models and fixture smoke program verify Android-visible wire
shapes compile. They are not an Android application, serializer, or runtime JSON
decoder test; a future Android implementation must test decoding against the
schemas before shipping. Fixtures are synthetic test data, never activation
evidence.

See the generated `docs/reference/QC2-003_CONTRACT_CATALOG.md` for all field
definitions, authority and reader roles, reference targets, state transitions,
and contract invariants.
