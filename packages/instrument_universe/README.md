# QC2 instrument-universe authority

This package owns stable instrument identity resolution, frozen candidate
censuses, point-in-time symbol/classification selection, and scientific
eligibility. It does not fetch provider data, persist records, choose feeds,
seal snapshots, or apply broker restrictions to scientific membership.

The caller supplies an explicit `SIP` or `IEX` feed. Initial scientific
eligibility requires verified `US_COMMON_EQUITY` classification, a USD symbol
assignment with confidence exactly `1.000000000000`, and a final or revised USD
bar for the target session that was observed and finalized by the census cutoff.
No price, liquidity, volume, or history-length cutoff is applied. Ambiguous or
unverified classifications are not admitted.

`Instrument.first_known_at`, symbol-assignment intervals, and observed bars are
not listing dates. The current contracts do not establish listing age or prove
that a candidate census covers all historical listings. Results report these
limits and never claim historical population completeness.

Each candidate receives exactly one `SCIENTIFIC_ELIGIBLE`, `UNSCORABLE`, or
`EXCLUDED` disposition and one stable reason code. Broker restrictions are
applied afterward by stable instrument ID to produce a separate execution set;
they do not change the `UniverseManifest` or its scientific reason counts.
`validate_snapshot_chain` checks the existing Market Data snapshot's references
without moving snapshot ownership into this package.
