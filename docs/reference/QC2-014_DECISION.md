# QC2-014 — Feature Authority decisions

## Contract and registry

- Strengthen the not-yet-deployed `FeatureDefinition` v1 shape before feature definitions are persisted: record the research family, output unit, split treatment, decimal precision, normalization, and parameter-profile key explicitly.
- Each definition carries its exact equation, typed input-unit statements, output unit and data type, warm-up, alignment, missingness, zero-denominator, dependency, implementation-hash, and invariance fields. The registry order is a stable topological sort with declaration order as the tie-breaker.
- Every snapshot contains exactly one type-conforming value or one explicit missing reason for every registered feature, in registry order; each row carries its unit and output data type. Its hash binds the ordered values, types, units, input hashes, registry, cutoff, implementation hash, environment fingerprint, and provenance references.

## Mathematics and edge behavior

- Price and volume inputs must be on one declared split-adjusted common share basis. Mixed adjustment manifests, share bases, canonical instruments, or ineffective symbol assignments fail closed.
- Decimal inputs reject binary floats and non-finite values. Outputs use declared precision with half-even rounding; integer event counts use precision zero.
- A zero denominator is not replaced with zero. It produces `DIVISION_BY_ZERO`; absent source fields produce `SOURCE_FIELD_MISSING`; insufficient listed history produces `WARMUP_REQUIRED`; missing historical comparison cohorts produce `NOT_APPLICABLE`.
- All normalizations are deterministic formula-level transforms. No global or dataset-fitted transform is introduced.
- Similarity is the maximum fixed-dimension mean absolute score `1 - mean(|b(x)-b(p)|)`, where `b(x)=x/(1+|x|)`. Only prior RunnerGenome/FailureGenome references with matching registry identity and caller-supplied temporal-access evidence can be compared. The engine checks event, source-availability, and access-receipt times against the cutoff; it does not read future outcomes.

## Calibration and activation

- Required 1/2/3/5/10/20-session return horizons are fixed by the master specification.
- Every other window is a named parameter in `fixture_daily_v1`. Its example values are synthetic fixtures, not calibration results, production defaults, or recommendations.
- Fixture evidence and fixture-only profiles are rejected for production. A non-fixture production registry requires a registry-bound calibration receipt, qualification receipt, and owner decision supplied by the relevant external authorities.
- No provider fallback, persistence, execution side effect, mutable global state, or live-trading behavior is part of the feature package.

## Scope limits

The local tests establish deterministic offline behavior for the supplied fixtures. They do not prove data-provider accuracy, exchange-calendar authority, production qualification, owner approval, or the identity of a Gen 1 source.
