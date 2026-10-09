import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { Client } from "pg";

const CONTENT_HASH_DOMAIN =
  "qc2.contract-content.v1/qc2.execution.paperorderintent.v1/1.0";
const HASH_ENVELOPE_FIELDS = new Set([
  "schema_name",
  "schema_version",
  "id",
  "created_at",
  "content_hash",
  "intent_state",
]);
const ACCOUNT_MAIN = createHash("sha256")
  .update("qc2-045-main-account")
  .digest("hex");
const ACCOUNT_CONCURRENT = createHash("sha256")
  .update("qc2-045-concurrent-account")
  .digest("hex");
const ACCOUNT_REPLACEMENT = createHash("sha256")
  .update("qc2-045-replacement-account")
  .digest("hex");
const ACCOUNT_CANCEL = createHash("sha256")
  .update("qc2-045-cancel-account")
  .digest("hex");
const ACCOUNT_SHARES = createHash("sha256")
  .update("qc2-045-shares-account")
  .digest("hex");
const ACCOUNT_CLOSE = createHash("sha256")
  .update("qc2-045-close-account")
  .digest("hex");
const ACCOUNT_FRACTIONAL_CLOSE = createHash("sha256")
  .update("qc2-045-fractional-close-account")
  .digest("hex");
const ACCOUNT_WRONG = createHash("sha256")
  .update("qc2-045-wrong-account")
  .digest("hex");

function uuidV7() {
  const timeHex = Date.now().toString(16).padStart(12, "0").slice(-12);
  const entropy = randomBytes(10).toString("hex");
  const variant = (8 + (Number.parseInt(entropy[3], 16) & 3)).toString(16);
  return `${timeHex.slice(0, 8)}-${timeHex.slice(8, 12)}-7${entropy.slice(0, 3)}-${variant}${entropy.slice(4, 7)}-${entropy.slice(7, 19)}`;
}

function newKey(prefix = "intent") {
  return `${prefix}-${randomBytes(8).toString("hex")}`;
}

function isoAfter(milliseconds) {
  return new Date(Date.now() + milliseconds).toISOString();
}

function reference(targetSchemaName, targetId, contentHash) {
  const result = {
    target_schema_name: targetSchemaName,
    target_id: targetId,
  };
  if (contentHash !== undefined) {
    result.content_hash = contentHash;
  }
  return result;
}

function buildIntent(
  fixture,
  {
    id = uuidV7(),
    reservationId = uuidV7(),
    key = newKey(),
    account = ACCOUNT_MAIN,
    action = "OPEN_LONG",
    side = action === "OPEN_LONG" ? "BUY" : "SELL",
    quantity = 2,
    limitPrice = action === "OPEN_LONG" ? "10" : null,
    expiresAt = isoAfter(30 * 60 * 1000),
    sourceRef,
  } = {},
) {
  const payload = structuredClone(fixture);
  payload.id = id;
  payload.created_at = new Date().toISOString();
  payload.paper_account_fingerprint = account;
  payload.action_kind = action;
  payload.side = side;
  payload.quantity_whole_shares = quantity;
  payload.limit_price = limitPrice;
  payload.expires_at = expiresAt;
  payload.idempotency_key = key;
  payload.intent_state = "CREATED";
  payload.reservation_ref =
    action === "CANCEL_PENDING_ENTRY"
      ? null
      : reference("qc2.execution.Reservation.v1", reservationId);
  if (sourceRef) {
    payload.source_ref = sourceRef;
  } else if (action === "REDUCE_LONG" || action === "CLOSE_LONG") {
    payload.source_ref = reference("qc2.execution.Position.v1", uuidV7());
  }
  payload.content_hash = "0".repeat(64);
  return payload;
}

async function sealIntent(adminClient, payload) {
  const immutableTerms = Object.fromEntries(
    Object.entries(payload).filter(([key]) => !HASH_ENVELOPE_FIELDS.has(key)),
  );
  const result = await adminClient.query(
    "SELECT qc2_integrity_build.hash_json($1, $2::jsonb) AS content_hash",
    [CONTENT_HASH_DOMAIN, JSON.stringify(immutableTerms)],
  );
  return { ...payload, content_hash: result.rows[0].content_hash };
}

function buildReservation(fixture, intent, { cash, shares, kind }) {
  const contract = structuredClone(fixture);
  contract.id = intent.reservation_ref.target_id;
  contract.created_at = intent.created_at;
  contract.episode_ref = structuredClone(intent.episode_ref);
  contract.intent_ref = reference(
    "qc2.execution.PaperOrderIntent.v1",
    intent.id,
    intent.content_hash,
  );
  contract.instrument_ref = structuredClone(intent.instrument_ref);
  contract.reservation_kind = kind;
  contract.reserved_quantity = String(shares);
  contract.reserved_cash = String(cash);
  contract.state = "ACTIVE";
  contract.released_at = null;
  return contract;
}

async function asRuntime(connectionString, authority) {
  const client = new Client({ connectionString });
  await client.connect();
  await client.query(`SET SESSION AUTHORIZATION qc2_runtime_${authority}`);
  return client;
}

async function persistIntent(
  client,
  intent,
  expectedAccount = intent.paper_account_fingerprint,
) {
  const result = await client.query(
    "SELECT qc2_control.persist_paper_order_intent($1::jsonb, $2) AS id",
    [JSON.stringify(intent), expectedAccount],
  );
  return result.rows[0].id;
}

async function verifyIntent(client, id) {
  const result = await client.query(
    "SELECT qc2_control.transition_paper_order_intent($1::uuid, 'VERIFIED') AS changed",
    [id],
  );
  assert.equal(result.rows[0].changed, true);
}

async function reserveIntent(client, id, reservation) {
  const result = await client.query(
    "SELECT qc2_control.reserve_paper_order_intent($1::uuid, $2::jsonb) AS id",
    [id, reservation === null ? null : JSON.stringify(reservation)],
  );
  return result.rows[0].id;
}

async function setCapacity(client, resourceKey, capacity) {
  await client.query(
    "SELECT qc2_control.set_reservation_capacity($1, $2::numeric)",
    [resourceKey, String(capacity)],
  );
}

async function expectSqlState(client, code, label, operation) {
  let caught;
  await client.query("BEGIN");
  try {
    await operation();
  } catch (error) {
    caught = error;
  } finally {
    await client.query("ROLLBACK");
  }
  assert.ok(caught, `${label}: expected PostgreSQL error ${code}`);
  assert.equal(caught.code, code, `${label}: unexpected PostgreSQL error`);
}

async function openEvidenceStream(connectionString) {
  const evidenceClient = await asRuntime(connectionString, "evidence");
  try {
    await evidenceClient.query(
      "SELECT qc2_integrity_build.create_evidence_stream($1, $2, $3, $4)",
      [
        "qc2-test-installation",
        "test",
        "qc2-045-paper-intents",
        "SYNTHETIC_FIXTURE",
      ],
    );
  } finally {
    await evidenceClient.end();
  }
}

export async function runQc2045PaperOrderAcceptance({
  connectionString,
  adminClient,
  intentFixture,
  reservationFixture,
}) {
  await openEvidenceStream(connectionString);
  const executionClient = await asRuntime(connectionString, "execution");
  const concurrentClient = await asRuntime(connectionString, "execution");
  try {
    const sameKeyId = uuidV7();
    const sameKeyReservationId = uuidV7();
    const original = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        id: sameKeyId,
        reservationId: sameKeyReservationId,
        key: "same-key-contract",
        quantity: 2,
      }),
    );
    assert.equal(await persistIntent(executionClient, original), sameKeyId);
    assert.equal(await persistIntent(executionClient, original), sameKeyId);

    const changedBytes = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        id: sameKeyId,
        reservationId: sameKeyReservationId,
        key: "same-key-contract",
        quantity: 3,
      }),
    );
    await expectSqlState(
      executionClient,
      "23505",
      "same key, changed terms",
      () => persistIntent(executionClient, changedBytes),
    );

    const concurrentDuplicate = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        key: newKey("concurrent-idempotency"),
      }),
    );
    const duplicateResults = await Promise.all([
      persistIntent(executionClient, concurrentDuplicate),
      persistIntent(concurrentClient, concurrentDuplicate),
    ]);
    assert.deepEqual(duplicateResults, [
      concurrentDuplicate.id,
      concurrentDuplicate.id,
    ]);

    const expired = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        key: newKey("expired"),
        expiresAt: isoAfter(-60_000),
      }),
    );
    await expectSqlState(executionClient, "23514", "expired intent", () =>
      persistIntent(executionClient, expired),
    );

    const wrongAccount = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account: ACCOUNT_WRONG,
        key: newKey("wrong-account"),
      }),
    );
    await expectSqlState(executionClient, "42501", "wrong paper account", () =>
      persistIntent(executionClient, wrongAccount, ACCOUNT_MAIN),
    );

    await expectSqlState(executionClient, "42501", "direct table write", () =>
      executionClient.query(
        `INSERT INTO qc2_execution.paper_order_intent(
           id, idempotency_key, paper_account_fingerprint, content_hash,
           intent_state, intent_contract, created_at
         ) VALUES ($1::uuid, 'direct-write', $2, $3, 'CREATED', '{}'::jsonb, now())`,
        [uuidV7(), ACCOUNT_MAIN, "0".repeat(64)],
      ),
    );

    const replacementKey = `paper_cash:${ACCOUNT_REPLACEMENT}`;
    await setCapacity(executionClient, replacementKey, 100);
    const prior = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account: ACCOUNT_REPLACEMENT,
        key: newKey("old-entry"),
        quantity: 2,
        limitPrice: "10",
      }),
    );
    const priorId = await persistIntent(executionClient, prior);
    await verifyIntent(executionClient, priorId);
    const priorReservation = buildReservation(reservationFixture, prior, {
      cash: 20,
      shares: 0,
      kind: "CASH",
    });
    assert.equal(
      await reserveIntent(executionClient, priorId, priorReservation),
      priorReservation.id,
    );

    const replacement = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account: ACCOUNT_REPLACEMENT,
        key: newKey("replacement-entry"),
        action: "REPLACE_ORDER",
        side: "BUY",
        quantity: 3,
        limitPrice: "11",
        sourceRef: reference(
          "qc2.execution.PaperOrderIntent.v1",
          prior.id,
          prior.content_hash,
        ),
      }),
    );
    const replacementId = await persistIntent(executionClient, replacement);
    await verifyIntent(executionClient, replacementId);
    const replacementReservation = buildReservation(
      reservationFixture,
      replacement,
      { cash: 33, shares: 0, kind: "CASH" },
    );
    await reserveIntent(executionClient, replacementId, replacementReservation);

    const replacementTotals = await adminClient.query(
      `SELECT resource.reserved::text AS reserved,
              pg_catalog.count(*) FILTER (WHERE active.state = 'ACTIVE')::text AS active_count
       FROM qc2_execution.reservation_resource AS resource
       LEFT JOIN qc2_execution.resource_reservation AS active
         ON active.resource_key = resource.resource_key
       WHERE resource.resource_key = $1
       GROUP BY resource.reserved`,
      [replacementKey],
    );
    assert.equal(replacementTotals.rows[0]?.reserved, "53.000000000000");
    assert.equal(replacementTotals.rows[0]?.active_count, "2");

    const cancelAccountKey = `paper_cash:${ACCOUNT_CANCEL}`;
    await setCapacity(executionClient, cancelAccountKey, 40);
    const cancelPrior = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account: ACCOUNT_CANCEL,
        key: newKey("cancel-prior"),
        quantity: 2,
        limitPrice: "10",
      }),
    );
    const cancelPriorId = await persistIntent(executionClient, cancelPrior);
    await verifyIntent(executionClient, cancelPriorId);
    const cancelPriorReservation = buildReservation(
      reservationFixture,
      cancelPrior,
      { cash: 20, shares: 0, kind: "CASH" },
    );
    await reserveIntent(executionClient, cancelPriorId, cancelPriorReservation);
    const cancel = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account: ACCOUNT_CANCEL,
        key: newKey("cancel-entry"),
        action: "CANCEL_PENDING_ENTRY",
        side: "BUY",
        quantity: 2,
        limitPrice: "10",
        reservationId: undefined,
        sourceRef: reference(
          "qc2.execution.PaperOrderIntent.v1",
          cancelPrior.id,
          cancelPrior.content_hash,
        ),
      }),
    );
    const cancelId = await persistIntent(executionClient, cancel);
    await verifyIntent(executionClient, cancelId);
    assert.equal(await reserveIntent(executionClient, cancelId, null), null);
    assert.equal(await reserveIntent(executionClient, cancelId, null), null);
    const cancelReserved = await adminClient.query(
      "SELECT reserved::text FROM qc2_execution.reservation_resource WHERE resource_key = $1",
      [cancelAccountKey],
    );
    assert.equal(cancelReserved.rows[0]?.reserved, "20.000000000000");

    const wholeCloseKey = `paper_shares:${ACCOUNT_CLOSE}:${intentFixture.instrument_ref.target_id}`;
    await setCapacity(executionClient, wholeCloseKey, 3);
    const wholeClose = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account: ACCOUNT_CLOSE,
        action: "CLOSE_LONG",
        side: "SELL",
        key: newKey("whole-close"),
        quantity: 3,
      }),
    );
    const wholeCloseId = await persistIntent(executionClient, wholeClose);
    await verifyIntent(executionClient, wholeCloseId);
    await reserveIntent(
      executionClient,
      wholeCloseId,
      buildReservation(reservationFixture, wholeClose, {
        cash: 0,
        shares: 3,
        kind: "SHARES",
      }),
    );

    const fractionalCloseKey = `paper_shares:${ACCOUNT_FRACTIONAL_CLOSE}:${intentFixture.instrument_ref.target_id}`;
    await setCapacity(executionClient, fractionalCloseKey, "3.5");
    const fractionalClose = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account: ACCOUNT_FRACTIONAL_CLOSE,
        action: "CLOSE_LONG",
        side: "SELL",
        key: newKey("fractional-close"),
        quantity: 3,
      }),
    );
    const fractionalCloseId = await persistIntent(
      executionClient,
      fractionalClose,
    );
    await verifyIntent(executionClient, fractionalCloseId);
    await expectSqlState(executionClient, "23514", "fractional close", () =>
      reserveIntent(
        executionClient,
        fractionalCloseId,
        buildReservation(reservationFixture, fractionalClose, {
          cash: 0,
          shares: 3,
          kind: "SHARES",
        }),
      ),
    );

    const shareResourceKey = `paper_shares:${ACCOUNT_SHARES}:${intentFixture.instrument_ref.target_id}`;
    await setCapacity(executionClient, shareResourceKey, 3);
    const excessiveSell = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account: ACCOUNT_SHARES,
        action: "REDUCE_LONG",
        side: "SELL",
        key: newKey("excessive-sell"),
        quantity: 4,
      }),
    );
    const excessiveSellId = await persistIntent(executionClient, excessiveSell);
    await verifyIntent(executionClient, excessiveSellId);
    const excessiveSellReservation = buildReservation(
      reservationFixture,
      excessiveSell,
      { cash: 0, shares: 4, kind: "SHARES" },
    );
    await expectSqlState(
      executionClient,
      "23514",
      "excessive sell reservation",
      () =>
        reserveIntent(
          executionClient,
          excessiveSellId,
          excessiveSellReservation,
        ),
    );

    const concurrentResource = `paper_cash:${ACCOUNT_CONCURRENT}`;
    await setCapacity(executionClient, concurrentResource, 100);
    const concurrentIntents = [];
    for (let index = 0; index < 2; index += 1) {
      const intent = await sealIntent(
        adminClient,
        buildIntent(intentFixture, {
          account: ACCOUNT_CONCURRENT,
          key: newKey(`concurrent-${index}`),
          quantity: 6,
          limitPrice: "10",
        }),
      );
      const id = await persistIntent(executionClient, intent);
      await verifyIntent(executionClient, id);
      concurrentIntents.push({
        intent,
        id,
        reservation: buildReservation(reservationFixture, intent, {
          cash: 60,
          shares: 0,
          kind: "CASH",
        }),
      });
    }
    const outcomes = await Promise.allSettled([
      reserveIntent(
        executionClient,
        concurrentIntents[0].id,
        concurrentIntents[0].reservation,
      ),
      reserveIntent(
        concurrentClient,
        concurrentIntents[1].id,
        concurrentIntents[1].reservation,
      ),
    ]);
    assert.equal(
      outcomes.filter((result) => result.status === "fulfilled").length,
      1,
    );
    const rejected = outcomes.find((result) => result.status === "rejected");
    assert.equal(rejected?.reason?.code, "23514");
    const concurrentTotals = await adminClient.query(
      `SELECT resource.reserved::text AS reserved,
              pg_catalog.count(active.id)::text AS active_count
       FROM qc2_execution.reservation_resource AS resource
       LEFT JOIN qc2_execution.resource_reservation AS active
         ON active.resource_key = resource.resource_key
        AND active.state = 'ACTIVE'
       WHERE resource.resource_key = $1
       GROUP BY resource.reserved`,
      [concurrentResource],
    );
    assert.equal(concurrentTotals.rows[0]?.reserved, "60.000000000000");
    assert.equal(concurrentTotals.rows[0]?.active_count, "1");

    const winnerIndex = outcomes[0].status === "fulfilled" ? 0 : 1;
    const winner = concurrentIntents[winnerIndex];
    assert.equal(
      await reserveIntent(executionClient, winner.id, winner.reservation),
      winner.reservation.id,
    );
    const afterRetry = await adminClient.query(
      "SELECT reserved::text FROM qc2_execution.reservation_resource WHERE resource_key = $1",
      [concurrentResource],
    );
    assert.equal(afterRetry.rows[0]?.reserved, "60.000000000000");

    await expectSqlState(adminClient, "42501", "immutable intent terms", () =>
      adminClient.query(
        `UPDATE qc2_execution.paper_order_intent
         SET intent_contract = pg_catalog.jsonb_set(
           intent_contract, '{quantity_whole_shares}', '999'::jsonb
         )
         WHERE id = $1::uuid`,
        [sameKeyId],
      ),
    );

    console.log(
      "QC2-045 persistence acceptance passed: sequential/concurrent idempotency, expiry/account guards, append-only writes, exact close/reduce/cancel/replace exposure, excess-share rejection, and concurrent cash serialization.",
    );
  } finally {
    await concurrentClient.end();
    await executionClient.end();
  }
}
