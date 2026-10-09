import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { createRequire } from "node:module";

const require = createRequire(new URL("../../lib/db/package.json", import.meta.url));
const { Client } = require("pg");

const INTENT_HASH_DOMAIN =
  "qc2.contract-content.v1/qc2.execution.paperorderintent.v1/1.0";
const HASH_ENVELOPE_FIELDS = new Set([
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
  const result = { target_schema_name: targetSchemaName, target_id: targetId };
  if (contentHash !== undefined) result.content_hash = contentHash;
  return result;
}

async function sealIntent(adminClient, fixture, account) {
  const intent = structuredClone(fixture);
  intent.id = uuidV7();
  intent.created_at = new Date().toISOString();
  intent.paper_account_fingerprint = account;
  intent.account_mode = "PAPER";
  intent.action_kind = "OPEN_LONG";
  intent.side = "BUY";
  intent.quantity_whole_shares = 2;
  intent.limit_price = "10";
  intent.expires_at = new Date(Date.now() + 30 * 60 * 1000).toISOString();
  intent.idempotency_key = `qc2-051-${randomBytes(8).toString("hex")}`;
  intent.intent_state = "CREATED";
  intent.reservation_ref = reference(
    "qc2.execution.Reservation.v1",
    uuidV7(),
  );
  intent.content_hash = "0".repeat(64);
  const immutableTerms = Object.fromEntries(
    Object.entries(intent).filter(([key]) => !HASH_ENVELOPE_FIELDS.has(key)),
  );
  const result = await adminClient.query(
    "SELECT qc2_integrity_build.hash_json($1, $2::jsonb) AS content_hash",
    [INTENT_HASH_DOMAIN, JSON.stringify(immutableTerms)],
  );
  intent.content_hash = result.rows[0].content_hash;
  return intent;
}

function buildReservation(fixture, intent) {
  const reservation = structuredClone(fixture);
  reservation.id = intent.reservation_ref.target_id;
  reservation.created_at = intent.created_at;
  reservation.episode_ref = structuredClone(intent.episode_ref);
  reservation.intent_ref = reference(
    "qc2.execution.PaperOrderIntent.v1",
    intent.id,
    intent.content_hash,
  );
  reservation.instrument_ref = structuredClone(intent.instrument_ref);
  reservation.reservation_kind = "CASH";
  reservation.reserved_quantity = "0";
  reservation.reserved_cash = "20";
  reservation.state = "ACTIVE";
  reservation.released_at = null;
  return reservation;
}

async function executionClient(connectionString) {
  const client = new Client({ connectionString });
  await client.connect();
  await client.query("SET SESSION AUTHORIZATION qc2_runtime_execution");
  return client;
}

async function expectSqlState(client, code, operation) {
  let caught;
  await client.query("BEGIN");
  try {
    await operation();
  } catch (error) {
    caught = error;
  } finally {
    await client.query("ROLLBACK");
  }
  assert.ok(caught, `expected PostgreSQL error ${code}`);
  assert.equal(caught.code, code);
}

function resumeAssessment(pauseGeneration, { blockedPrerequisite = false } = {}) {
  const deadline = new Date(Date.now() + 5 * 60 * 1000).toISOString();
  const gates = [
    {
      gate_id: "entry_pause_authority",
      status: "BLOCK",
      reason_codes: ["ENTRY_PAUSED"],
    },
    {
      gate_id: "account_identity",
      status: blockedPrerequisite ? "BLOCK" : "PASS",
      reason_codes: blockedPrerequisite ? ["IDENTITY_UNVERIFIED"] : [],
    },
  ];
  return {
    assessment_id: uuidV7(),
    action: "NEW_ENTRY",
    status: "READY_TO_RESUME",
    pause_generation: pauseGeneration,
    input_generation: 7,
    evaluated_at: new Date(Date.now() - 1000).toISOString(),
    freshness_deadline: deadline,
    pending_entry_orders_clear: true,
    allowed_warning_gate_ids: [],
    gate_results: gates,
  };
}

function gateFor(intent, pauseGeneration) {
  const freshnessDeadline = new Date(Date.now() + 5 * 60 * 1000).toISOString();
  return {
    paper_account_fingerprint: intent.paper_account_fingerprint,
    account_mode: "PAPER",
    paper_endpoint_verified: true,
    account_identity_status: "VERIFIED",
    reconciliation_status: "FRESH",
    entry_paused: false,
    entry_pause_generation: pauseGeneration,
    input_generation: 7,
    current_session: intent.target_execution_session,
    session_open: true,
    reservation_active: true,
    symbol_assignment_id: intent.symbol_assignment_ref.target_id,
    broker_symbol: "XYZ",
    readiness: [
      {
        assessment_id: uuidV7(),
        action: "NEW_ENTRY",
        status: "READY",
        input_generation: 7,
        freshness_deadline: freshnessDeadline,
      },
    ],
    emergency_scopes: [],
    prior_intent_state: null,
    prior_reservation_active: null,
    prior_broker_order_id: null,
  };
}

function normalizedRequest(intent, gate) {
  return {
    schema_name: "qc2.execution.normalized_mutation_request.v1",
    action: "SUBMIT",
    intent_id: intent.id,
    account_fingerprint: intent.paper_account_fingerprint,
    client_order_key: intent.idempotency_key,
    instrument_id: intent.instrument_ref.target_id,
    symbol_assignment_id: gate.symbol_assignment_id,
    symbol: gate.broker_symbol,
    side: intent.side,
    quantity_whole_shares: intent.quantity_whole_shares,
    order_type: intent.order_type,
    time_in_force: intent.time_in_force,
    session_restriction: intent.session_restriction,
    limit_price: intent.limit_price,
    stop_price: intent.stop_price,
    extended_hours: false,
  };
}

async function prepareQueuedIntent(execution, adminClient, intent, reservation) {
  await execution.query(
    "SELECT qc2_control.persist_paper_order_intent($1::jsonb, $2::text)",
    [JSON.stringify(intent), intent.paper_account_fingerprint],
  );
  const verified = await execution.query(
    "SELECT qc2_control.transition_paper_order_intent($1::uuid, 'VERIFIED') AS changed",
    [intent.id],
  );
  assert.equal(verified.rows[0].changed, true);
  await execution.query(
    "SELECT qc2_control.set_reservation_capacity($1::text, $2::numeric)",
    [`paper_cash:${intent.paper_account_fingerprint}`, "100000"],
  );
  await execution.query(
    "SELECT qc2_control.reserve_paper_order_intent($1::uuid, $2::jsonb)",
    [intent.id, JSON.stringify(reservation)],
  );
  const queued = await execution.query(
    "SELECT qc2_control.transition_paper_order_intent($1::uuid, 'QUEUED_FOR_SUBMISSION') AS changed",
    [intent.id],
  );
  assert.equal(queued.rows[0].changed, true);
  const outbox = await execution.query(
    "SELECT qc2_control.enqueue_paper_order_submission($1::uuid) AS message_id",
    [intent.id],
  );
  const workerId = uuidV7();
  const delivery = await execution.query(
    "SELECT * FROM qc2_control.claim_paper_order_submission($1::uuid, 60)",
    [workerId],
  );
  assert.equal(delivery.rows[0].message_id, outbox.rows[0].message_id);

  const gate = gateFor(intent, 2);
  const request = normalizedRequest(intent, gate);
  const requestHashResult = await adminClient.query(
    "SELECT qc2_integrity_build.hash_json($1, $2::jsonb) AS request_hash",
    [
      "qc2.execution.normalized-request.v1",
      JSON.stringify(request),
    ],
  );
  const started = await execution.query(
    `
      SELECT * FROM qc2_control.begin_paper_order_attempt(
        $1::uuid, $2::uuid, $3::bigint, $4::jsonb, $5::text, $6::jsonb
      )
    `,
    [
      delivery.rows[0].message_id,
      delivery.rows[0].worker_id,
      delivery.rows[0].fencing_generation,
      JSON.stringify(request),
      requestHashResult.rows[0].request_hash,
      JSON.stringify(gate),
    ],
  );
  return {
    gate,
    delivery: delivery.rows[0],
    attemptId: started.rows[0].attempt_id,
    request,
    intent,
  };
}

async function authorize(execution, attempt, gate) {
  const result = await execution.query(
    `
      SELECT qc2_control.authorize_paper_order_attempt(
        $1::uuid, $2::uuid, $3::bigint, $4::uuid, $5::jsonb
      ) AS authorized
    `,
    [
      attempt.delivery.message_id,
      attempt.delivery.worker_id,
      attempt.delivery.fencing_generation,
      attempt.attemptId,
      JSON.stringify(gate),
    ],
  );
  return result.rows[0].authorized;
}

export async function runQc2051ExecutionReadinessAcceptance({
  connectionString,
  adminClient,
  intentFixture,
  reservationFixture,
}) {
  const execution = await executionClient(connectionString);
  const account = createHash("sha256")
    .update(`qc2-051-account-${randomBytes(12).toString("hex")}`)
    .digest("hex");
  try {
    const initial = await execution.query(
      "SELECT * FROM qc2_control.get_entry_pause_state()",
    );
    assert.equal(initial.rows[0].entry_paused, true);
    assert.equal(Number(initial.rows[0].generation), 1);

    const firstPauseRequestId = uuidV7();
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const paused = await execution.query(
        "SELECT * FROM qc2_control.pause_new_entries($1::uuid, 'acceptance_pause')",
        [firstPauseRequestId],
      );
      assert.equal(paused.rows[0].entry_paused, true);
      assert.equal(Number(paused.rows[0].generation), 1);
    }
    const duplicateCount = await adminClient.query(
      "SELECT count(*)::integer AS count FROM qc2_execution.entry_pause_request WHERE request_id = $1::uuid",
      [firstPauseRequestId],
    );
    assert.equal(duplicateCount.rows[0].count, 1);

    const resumed = await execution.query(
      "SELECT * FROM qc2_control.resume_new_entries($1::bigint, $2::jsonb)",
      [1, JSON.stringify(resumeAssessment(1))],
    );
    assert.equal(resumed.rows[0].entry_paused, false);
    assert.equal(Number(resumed.rows[0].generation), 2);

    const intent = await sealIntent(adminClient, intentFixture, account);
    const reservation = buildReservation(reservationFixture, intent);
    const attempt = await prepareQueuedIntent(
      execution,
      adminClient,
      intent,
      reservation,
    );

    assert.equal(
      await authorize(execution, attempt, {
        ...attempt.gate,
        input_generation: 8,
      }),
      false,
      "submit authorization must reject a stale readiness generation",
    );
    assert.equal(
      await authorize(execution, attempt, {
        ...attempt.gate,
        emergency_scopes: ["NEW_EXPOSURE_HALT"],
      }),
      false,
      "submit authorization must honor entry-scoped emergency holds",
    );
    assert.equal(await authorize(execution, attempt, attempt.gate), true);

    const secondPauseRequestId = uuidV7();
    const pauseAfterStart = await execution.query(
      "SELECT * FROM qc2_control.pause_new_entries($1::uuid, 'acceptance_race')",
      [secondPauseRequestId],
    );
    assert.equal(pauseAfterStart.rows[0].entry_paused, true);
    assert.equal(Number(pauseAfterStart.rows[0].generation), 3);

    const pending = await execution.query(
      "SELECT qc2_control.pending_entry_pause_cancellations() AS items",
    );
    assert.equal(pending.rows[0].items.length, 1);
    assert.equal(pending.rows[0].items[0].target_intent_id, intent.id);
    assert.equal(pending.rows[0].items[0].target_intent.intent_state, "SUBMISSION_STARTED");

    const proposedCancelId = uuidV7();
    const firstReservedId = await execution.query(
      `
        SELECT qc2_control.reserve_pause_cancel_intent_id(
          3, $1::uuid, $2::uuid
        ) AS cancel_intent_id
      `,
      [intent.id, proposedCancelId],
    );
    const retryReservedId = await execution.query(
      `
        SELECT qc2_control.reserve_pause_cancel_intent_id(
          3, $1::uuid, $2::uuid
        ) AS cancel_intent_id
      `,
      [intent.id, uuidV7()],
    );
    assert.equal(
      retryReservedId.rows[0].cancel_intent_id,
      firstReservedId.rows[0].cancel_intent_id,
      "pause cancellation identity must be stable across retries",
    );

    assert.equal(
      await authorize(execution, attempt, attempt.gate),
      false,
      "a pause generation change must block authorization before the broker mutation",
    );
    await expectSqlState(execution, "23514", async () => {
      await execution.query(
        "SELECT * FROM qc2_control.resume_new_entries($1::bigint, $2::jsonb)",
        [3, JSON.stringify(resumeAssessment(3, { blockedPrerequisite: true }))],
      );
    });
    await expectSqlState(execution, "23514", async () => {
      await execution.query(
        "SELECT * FROM qc2_control.resume_new_entries($1::bigint, $2::jsonb)",
        [3, JSON.stringify(resumeAssessment(3))],
      );
    });
    const finalState = await execution.query(
      "SELECT * FROM qc2_control.get_entry_pause_state()",
    );
    assert.equal(finalState.rows[0].entry_paused, true);
    assert.equal(Number(finalState.rows[0].generation), 3);
  } finally {
    await execution.end();
  }
}
