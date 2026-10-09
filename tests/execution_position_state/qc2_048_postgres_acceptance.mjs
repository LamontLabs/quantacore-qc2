import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { createRequire } from "node:module";

const require = createRequire(new URL("../../lib/db/package.json", import.meta.url));
const { Client } = require("pg");

const INTENT_HASH_DOMAIN =
  "qc2.contract-content.v1/qc2.execution.paperorderintent.v1/1.0";
const INTENT_HASH_ENVELOPE_FIELDS = new Set([
  "schema_name",
  "schema_version",
  "id",
  "created_at",
  "content_hash",
  "intent_state",
]);

function uuidV7() {
  const timeHex = Date.now().toString(16).padStart(12, "0").slice(-12);
  const entropy = randomBytes(10).toString("hex");
  const variant = (8 + (Number.parseInt(entropy[3], 16) & 3)).toString(16);
  return `${timeHex.slice(0, 8)}-${timeHex.slice(8, 12)}-7${entropy.slice(0, 3)}-${variant}${entropy.slice(4, 7)}-${entropy.slice(7, 19)}`;
}

function reference(targetSchemaName, targetId, contentHash) {
  const result = {
    target_schema_name: targetSchemaName,
    target_id: targetId,
  };
  if (contentHash !== undefined) result.content_hash = contentHash;
  return result;
}

function fixture(fixtures, name) {
  const found = fixtures.find((row) => row.contract === name);
  assert.ok(found, `missing ${name} fixture`);
  return structuredClone(found.payload);
}

async function hashJson(client, domain, payload) {
  const result = await client.query(
    "SELECT qc2_integrity_build.hash_json($1, $2::jsonb) AS value",
    [domain, JSON.stringify(payload)],
  );
  return result.rows[0].value;
}

async function sealIntent(adminClient, intent) {
  const immutableTerms = Object.fromEntries(
    Object.entries(intent).filter(
      ([key]) => !INTENT_HASH_ENVELOPE_FIELDS.has(key),
    ),
  );
  intent.content_hash = await hashJson(
    adminClient,
    INTENT_HASH_DOMAIN,
    immutableTerms,
  );
  return intent;
}

async function executionClient(connectionString) {
  const client = new Client({ connectionString });
  await client.connect();
  await client.query("SET SESSION AUTHORIZATION qc2_runtime_execution");
  return client;
}

async function buildEvent(
  adminClient,
  fixtures,
  orderId,
  eventType,
  sequence,
  providerId,
  at,
) {
  const event = fixture(fixtures, "BrokerOrderEvent");
  event.id = uuidV7();
  event.broker_order_ref = reference("qc2.execution.BrokerOrder.v1", orderId);
  event.event_type = eventType;
  event.event_sequence = sequence;
  event.provider_event_id = providerId;
  event.event_at = at;
  event.received_at = at;
  event.created_at = at;
  event.event_payload_hash = await hashJson(
    adminClient,
    "qc2.execution.provider-event-payload.v1",
    {
      order_id: orderId,
      provider_event_id: providerId,
      event_type: eventType,
      event_sequence: sequence,
      event_at: at,
    },
  );
  return event;
}

export async function runQc2048DurablePositionStateAcceptance({
  connectionString,
  adminClient,
  fixtures,
}) {
  const episode = fixture(fixtures, "ExecutionEpisode");
  const openingPosition = fixture(fixtures, "Position");
  const intent = fixture(fixtures, "PaperOrderIntent");
  const reservation = fixture(fixtures, "Reservation");
  const brokerOrder = fixture(fixtures, "BrokerOrder");
  const fillTemplate = fixture(fixtures, "Fill");
  const correctionTemplate = fixture(fixtures, "FillCorrection");
  const action = fixture(fixtures, "CorporateActionRecord");

  const now = Date.now();
  const createdAt = new Date(now).toISOString();
  intent.id = uuidV7();
  intent.created_at = createdAt;
  intent.expires_at = new Date(now + 60 * 60 * 1000).toISOString();
  intent.paper_account_fingerprint = episode.paper_account_fingerprint;
  intent.account_mode = "PAPER";
  intent.action_kind = "OPEN_LONG";
  intent.side = "BUY";
  intent.quantity_whole_shares = 1;
  intent.limit_price = "11";
  intent.idempotency_key = `qc2-048-${randomBytes(10).toString("hex")}`;
  intent.intent_state = "CREATED";
  const reservationId = uuidV7();
  intent.reservation_ref = reference("qc2.execution.Reservation.v1", reservationId);
  intent.content_hash = "0".repeat(64);
  await sealIntent(adminClient, intent);

  reservation.id = reservationId;
  reservation.created_at = createdAt;
  reservation.episode_ref = structuredClone(intent.episode_ref);
  reservation.intent_ref = reference(
    "qc2.execution.PaperOrderIntent.v1",
    intent.id,
    intent.content_hash,
  );
  reservation.instrument_ref = structuredClone(intent.instrument_ref);
  reservation.reservation_kind = "CASH";
  reservation.reserved_quantity = "0";
  reservation.reserved_cash = "30";
  reservation.state = "ACTIVE";
  reservation.released_at = null;

  const orderId = uuidV7();
  brokerOrder.id = orderId;
  brokerOrder.created_at = createdAt;
  brokerOrder.updated_at = createdAt;
  brokerOrder.submitted_at = createdAt;
  brokerOrder.intent_ref = reference(
    "qc2.execution.PaperOrderIntent.v1",
    intent.id,
    intent.content_hash,
  );
  brokerOrder.paper_account_fingerprint = episode.paper_account_fingerprint;
  brokerOrder.broker_order_id = `fixture-${randomBytes(8).toString("hex")}`;
  brokerOrder.client_order_key = intent.idempotency_key;
  brokerOrder.filled_quantity = "0";
  brokerOrder.remaining_quantity = "1";
  brokerOrder.request_hash = createHash("sha256")
    .update(`${intent.id}:request`)
    .digest("hex");

  let firstFillId;
  const execution = await executionClient(connectionString);
  try {
    const registeredEpisode = await execution.query(
      "SELECT qc2_control.register_execution_episode($1::jsonb, $2::jsonb) AS id",
      [JSON.stringify(episode), JSON.stringify([openingPosition])],
    );
    assert.equal(registeredEpisode.rows[0].id, episode.id);

    await execution.query(
      "SELECT qc2_control.persist_paper_order_intent($1::jsonb, $2)",
      [JSON.stringify(intent), intent.paper_account_fingerprint],
    );
    const verified = await execution.query(
      "SELECT qc2_control.transition_paper_order_intent($1::uuid, 'VERIFIED') AS changed",
      [intent.id],
    );
    assert.equal(verified.rows[0].changed, true);
    await execution.query(
      "SELECT qc2_control.set_reservation_capacity($1, $2::numeric)",
      [`paper_cash:${intent.paper_account_fingerprint}`, "1000"],
    );
    await execution.query(
      "SELECT qc2_control.reserve_paper_order_intent($1::uuid, $2::jsonb)",
      [intent.id, JSON.stringify(reservation)],
    );
    await execution.query(
      "SELECT qc2_control.register_position_state_broker_order($1::jsonb)",
      [JSON.stringify(brokerOrder)],
    );

    const acceptedAt = new Date(now + 2 * 60_000).toISOString();
    const firstFillAt = new Date(now + 3 * 60_000).toISOString();
    const correctionAt = new Date(now + 4 * 60_000).toISOString();
    const secondFillAt = new Date(now + 5 * 60_000).toISOString();
    const acceptedEvent = await buildEvent(
      adminClient,
      fixtures,
      orderId,
      "ACCEPTED",
      0,
      `accepted-${randomBytes(4).toString("hex")}`,
      acceptedAt,
    );
    await execution.query(
      "SELECT qc2_control.append_position_state_broker_event($1::jsonb)",
      [JSON.stringify(acceptedEvent)],
    );

    const correctionEvent = await buildEvent(
      adminClient,
      fixtures,
      orderId,
      "CORRECTION",
      1,
      `correction-${randomBytes(4).toString("hex")}`,
      correctionAt,
    );
    await execution.query(
      "SELECT qc2_control.append_position_state_broker_event($1::jsonb)",
      [JSON.stringify(correctionEvent)],
    );

    const firstFill = structuredClone(fillTemplate);
    firstFillId = uuidV7();
    firstFill.id = firstFillId;
    firstFill.broker_order_ref = reference("qc2.execution.BrokerOrder.v1", orderId);
    firstFill.instrument_ref = structuredClone(intent.instrument_ref);
    firstFill.provider_fill_id = "provider-fill-a";
    firstFill.side = "BUY";
    firstFill.quantity = "0.4";
    firstFill.price = "10";
    firstFill.currency = episode.currency;
    firstFill.filled_at = firstFillAt;
    firstFill.received_at = firstFillAt;
    firstFill.created_at = firstFillAt;
    const firstResult = await execution.query(
      "SELECT qc2_control.append_position_state_fill($1::jsonb) AS id",
      [JSON.stringify(firstFill)],
    );
    assert.equal(firstResult.rows[0].id, firstFill.id);

    const correction = structuredClone(correctionTemplate);
    correction.id = uuidV7();
    correction.original_fill_ref = reference("qc2.execution.Fill.v1", firstFill.id);
    correction.source_event_ref = reference(
      "qc2.execution.BrokerOrderEvent.v1",
      correctionEvent.id,
    );
    correction.correction_kind = "PRICE_ADJUSTMENT";
    correction.quantity_delta = "0";
    correction.price_delta = "1";
    correction.reason_code = "broker_price_correction";
    correction.corrected_at = correctionAt;
    correction.created_at = correctionAt;
    await execution.query(
      "SELECT qc2_control.append_position_state_fill_correction($1::jsonb)",
      [JSON.stringify(correction)],
    );

    const secondFill = structuredClone(fillTemplate);
    secondFill.id = uuidV7();
    secondFill.broker_order_ref = reference("qc2.execution.BrokerOrder.v1", orderId);
    secondFill.instrument_ref = structuredClone(intent.instrument_ref);
    secondFill.provider_fill_id = "provider-fill-b";
    secondFill.side = "BUY";
    secondFill.quantity = "0.6";
    secondFill.price = "11";
    secondFill.currency = episode.currency;
    secondFill.filled_at = secondFillAt;
    secondFill.received_at = secondFillAt;
    secondFill.created_at = secondFillAt;
    const secondResult = await execution.query(
      "SELECT qc2_control.append_position_state_fill($1::jsonb) AS id",
      [JSON.stringify(secondFill)],
    );
    assert.equal(secondResult.rows[0].id, secondFill.id);
    const duplicateFill = await execution.query(
      "SELECT qc2_control.append_position_state_fill($1::jsonb) AS id",
      [JSON.stringify(secondFill)],
    );
    assert.equal(duplicateFill.rows[0].id, secondFill.id);

    const actionAdjustmentId = uuidV7();
    await execution.query(
      `SELECT qc2_control.append_position_state_corporate_action(
        $1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::text,
        $6::timestamptz, $7::numeric, $8::numeric, $9::text, $10::uuid
      )`,
      [
        episode.id,
        actionAdjustmentId,
        action.id,
        intent.instrument_ref.target_id,
        episode.currency,
        new Date(now + 60_000).toISOString(),
        "2",
        "0.25",
        action.terms_hash,
        orderId,
      ],
    );

    const outputPosition = structuredClone(openingPosition);
    outputPosition.id = uuidV7();
    outputPosition.quantity = "3.5";
    outputPosition.average_cost = "3.589285714286";
    outputPosition.as_of = secondFillAt;
    outputPosition.reconciliation_status = "RECONCILED";
    outputPosition.source_fill_refs = [
      ...outputPosition.source_fill_refs,
      reference("qc2.execution.Fill.v1", firstFill.id),
      reference("qc2.execution.Fill.v1", secondFill.id),
    ];
    const projectionHash = await hashJson(
      adminClient,
      "qc2.execution.position-state.replay.v1",
      {
        episode_id: episode.id,
        positions: [outputPosition],
        cash_balance: "-9.4375",
      },
    );
    await execution.query(
      `SELECT qc2_control.persist_execution_position_projection(
        $1::uuid, $2::jsonb, $3::text, $4::jsonb, $5::text, $6::timestamptz
      )`,
      [
        episode.id,
        JSON.stringify([outputPosition]),
        "RECONCILED",
        "[]",
        projectionHash,
        secondFillAt,
      ],
    );

    const state = await execution.query(
      `
        SELECT
          (SELECT pg_catalog.count(*)::integer
             FROM qc2_execution.position_state_fill WHERE order_id = $1::uuid)
            AS fill_count,
          (SELECT pg_catalog.count(*)::integer
             FROM qc2_execution.position_state_fill_correction
            WHERE fill_id = $2::uuid) AS correction_count,
          (SELECT pg_catalog.count(*)::integer
             FROM qc2_execution.position_state_cash_ledger
            WHERE episode_id = $3::uuid) AS cash_entry_count,
          (SELECT balance::text
             FROM qc2_execution.position_state_cash_projection
            WHERE episode_id = $3::uuid AND currency = 'USD') AS cash_balance,
          (SELECT quantity::text
             FROM qc2_execution.position_state_position_projection
            WHERE episode_id = $3::uuid
              AND instrument_id = $4::uuid AND currency = 'USD') AS position_quantity,
          (SELECT average_cost::text
             FROM qc2_execution.position_state_position_projection
            WHERE episode_id = $3::uuid
              AND instrument_id = $4::uuid AND currency = 'USD') AS average_cost,
          (SELECT state
             FROM qc2_execution.resource_reservation
            WHERE id = $5::uuid) AS reservation_state
      `,
      [
        orderId,
        firstFill.id,
        episode.id,
        intent.instrument_ref.target_id,
        reservationId,
      ],
    );
    assert.equal(state.rows[0].fill_count, 2);
    assert.equal(state.rows[0].correction_count, 1);
    assert.equal(state.rows[0].cash_entry_count, 4);
    assert.equal(Number(state.rows[0].cash_balance), -9.4375);
    assert.equal(Number(state.rows[0].position_quantity), 3.5);
    assert.equal(Number(state.rows[0].average_cost), 3.589285714286);
    assert.equal(state.rows[0].reservation_state, "RELEASED");

    const invalidShortPosition = {
      ...outputPosition,
      id: uuidV7(),
      quantity: "-0.25",
    };
    await assert.rejects(
      execution.query(
        `SELECT qc2_control.persist_execution_position_projection(
          $1::uuid, $2::jsonb, $3::text, $4::jsonb, $5::text, $6::timestamptz
        )`,
        [
          episode.id,
          JSON.stringify([invalidShortPosition]),
          "RECONCILED",
          "[]",
          projectionHash,
          secondFillAt,
        ],
      ),
      (error) => error.code === "23514",
    );
  } finally {
    await execution.end();
  }

  await assert.rejects(
    adminClient.query(
      `UPDATE qc2_execution.position_state_fill
          SET price = 999
        WHERE fill_id = $1::uuid`,
      [firstFillId],
    ),
    (error) => error.code === "55000",
  );
}
