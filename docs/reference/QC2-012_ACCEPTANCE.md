# QC2-012 — Universe Authority

## Acceptance assessment

- **Result:** PASS
- **Evidence class:** `SYNTHETIC_FIXTURE` / `test`
- **Scope:** Stable instrument identity, candidate census, deterministic scientific eligibility, explicit candidate dispositions, separate execution restrictions, point-in-time limitations, and snapshot-chain validation.
- **Reference intake:** No Gen 1 source was inspected; no legacy source interpretation is claimed.
- **Limitations:** Historical candidate-population completeness and listing age remain unavailable. This implementation does not fetch provider data, seal snapshots, introduce price or liquidity cutoffs, or perform trading.

## Acceptance checklist

- [x] DELIVERABLE: Instrument/symbol/classification history; candidate, eligible, unscorable and execution sets. | evidence: `packages/instrument_universe/README.md`; `packages/instrument_universe/src/qc2_instrument_universe/authority.py`; deterministic candidate partitions and separate broker-restricted execution IDs.
- [x] DELIVERABLE: Acyclic census→bundle→universe→snapshot construction and reason taxonomy. | evidence: `packages/instrument_universe/src/qc2_instrument_universe/authority.py`; `tests/instrument_universe/test_authority.py::test_snapshot_must_follow_the_census_bundle_universe_chain`.
- [x] DELIVERABLE: Point-in-time fidelity assessments and unresolved classification handling. | evidence: `packages/instrument_universe/src/qc2_instrument_universe/authority.py`; explicit fidelity limitations, unscorable timing failures, and classification dispositions.
- [x] TEST: Ticker reuse, rename, IPO, delisting, ETF/common-share ambiguity, unavailable listing age. | evidence: `tests/instrument_universe/test_authority.py::test_ticker_reuse_and_rename_preserve_stable_instrument_identity`; `test_ipo_delisting_and_ambiguous_classes_get_explicit_dispositions`; `test_missing_listing_age_is_not_inferred_from_observed_bar_history`.
- [x] TEST: Broker restriction does not alter scientific universe. | evidence: `tests/instrument_universe/test_authority.py::test_candidate_partitions_and_broker_restrictions_are_separate_and_reproducible`.
- [x] TEST: Every candidate has one inclusion/exclusion disposition; current listings cannot claim historical completeness. | evidence: `tests/instrument_universe/test_authority.py::test_candidate_partitions_and_broker_restrictions_are_separate_and_reproducible`; `test_missing_listing_age_is_not_inferred_from_observed_bar_history`.
