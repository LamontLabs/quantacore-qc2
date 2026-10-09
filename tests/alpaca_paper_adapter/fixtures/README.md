# Alpaca paper API fixtures

These are synthetic contract fixtures, not broker records or evidence of a
successful order. Field names and semantics are based on the current Alpaca
Trading API documentation checked on 2026-10-08:

- [Order lifecycle and documented statuses](https://docs.alpaca.markets/us/docs/orders-at-alpaca)
- [Account activity object and sample FILL](https://docs.alpaca.markets/us/docs/account-activities)
- [Retrieve account activities and pagination](https://docs.alpaca.markets/us/reference/getaccountactivities)
- [Replace order by ID](https://docs.alpaca.markets/us/reference/patchorderbyorderid-1)

The order fixtures include the documented `new`, `partially_filled`, and
`pending_cancel` states. Activity fixtures use Alpaca's `FILL` activity shape,
including the documented `fill` and `partial_fill` subtypes and the activity ID
cursor format. Identifiers, timestamps, symbols, quantities, and prices are
invented for tests.
