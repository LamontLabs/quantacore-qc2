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
  const result = {
    target_schema_name: targetSchemaName,
    target_id: targetId,
  };
  if (contentHash !== undefined) {
    result.content_hash = contentHash;
  }
  return result;
}

function buildIntent(fixture, { account, action, sourceRef, reservationId }) {
  const payload = structuredClone(fixture);
  payload.id = uuidV7();
  payload.created_at = new Date().toISOString();
  payload.paper_account_fingerprint = account;
  payload.account_mode = "PAPER";
  payload.action_kind = action;
  payload.side = action === "OPEN_LONG" ? "BUY" : "BUY";
  payload.quantity_whole_shares = 2;
  payload.limit_price = "10";
  payload.expires_at = new Date(Date.now() + 30 * 60 * 1000).toISOString();
  payload.idempotency_key = `qc2-046-${randomBytes(8).toString("hex")}`;
  payload.intent_state = "CREATED";
  payload.reservation_ref =
    action === "CANCEL_PENDING_ENTRY"
      ? null
      : reference("qc2.execution.Reservation.v1", reservationId);
  if (sourceRef) {
    payload.source_ref = sourceRef;
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
    [INTENT_HASH_DOMAIN, JSON.stringify(immutableTerms)],
  );
  return { ...payload, content_hash: result.rows[0].content_hash };
}

function buildReservation(fixture, intent, reservationId) {
  const contract = structuredClone(fixture);
  contract.id = reservationId;
  contract.created_at = intent.created_at;
  contract.episode_ref = structuredClone(intent.episode_ref);
  contract.intent_ref = reference(
    "qc2.execution.PaperOrderIntent.v1",
    intent.id,
    intent.content_hash,
  );
  contract.instrument_ref = structuredClone(intent.instrument_ref);
  contract.reservation_kind = "CASH";
  contract.reserved_quantity = "0";
  contract.reserved_cash = "20";
  contract.state = "ACTIVE";
  contract.released_at = null;
  return contract;
}

async function executionClient(connectionString) {
  const client = new Client({ connectionString });
  await client.connect();
  await client.query("SET SESSION AUTHORIZATION qc2_runtime_execution");
  return client;
}

async function prepareIntent(
  client,
  intent,
  reservation,
  { cashCapacity = "100000" } = {},
) {
  await client.query(
    "SELECT qc2_control.persist_paper_order_intent($1::jsonb, $2)",
    [JSON.stringify(intent), intent.paper_account_fingerprint],
  );
  const verified = await client.query(
    "SELECT qc2_control.transition_paper_order_intent($1::uuid, 'VERIFIED') AS changed",
    [intent.id],
  );
  assert.equal(verified.rows[0].changed, true);
  if (reservation !== null) {
    await client.query(
      "SELECT qc2_control.set_reservation_capacity($1, $2::numeric)",
      [`paper_cash:${intent.paper_account_fingerprint}`, cashCapacity],
    );
  }
  await client.query(
    "SELECT qc2_control.reserve_paper_order_intent($1::uuid, $2::jsonb)",
    [intent.id, reservation === null ? null : JSON.stringify(reservation)],
  );
}

async function enqueue(client, intentId) {
  const result = await client.query(
    "SELECT qc2_control.enqueue_paper_order_submission($1::uuid) AS message_id",
    [intentId],
  );
  return result.rows[0].message_id;
}

async function claim(client, workerId, leaseSeconds = 60) {
  const result = await client.query(
    "SELECT * FROM qc2_control.claim_paper_order_submission($1::uuid, $2::integer)",
    [workerId, leaseSeconds],
  );
  return result.rows[0] ?? null;
}

function gateFor(intent, action, options = {}) {
  return {
    paper_account_fingerprint: intent.paper_account_fingerprint,
    account_mode: "PAPER",
    paper_endpoint_verified: true,
    entry_paused: false,
    current_session: intent.target_execution_session,
    session_open: true,
    reservation_active: true,
    symbol_assignment_id: intent.symbol_assignment_ref.target_id,
    broker_symbol: "XYZ",
    readiness: [
      {
        assessment_id: uuidV7(),
        action,
        status: "READY",
        input_generation: 1,
        freshness_deadline: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
      },
    ],
    prior_intent_state: options.priorIntentState ?? null,
    prior_reservation_active: options.priorReservationActive ?? null,
    prior_broker_order_id: options.priorBrokerOrderId ?? null,
  };
}

function requestFor(intent, gate, priorIntent = null) {
  if (intent.action_kind === "CANCEL_PENDING_ENTRY") {
    return {
      schema_name: "qc2.execution.normalized_mutation_request.v1",
      action: "CANCEL",
      intent_id: intent.id,
      account_fingerprint: intent.paper_account_fingerprint,
      client_order_key: intent.idempotency_key,
      target_intent_id: intent.source_ref.target_id,
      target_client_order_key: priorIntent?.idempotency_key,
      broker_order_id: gate.prior_broker_order_id,
    };
  }
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

async function requestHash(client, request) {
  const result = await client.query(
    "SELECT qc2_integrity_build.hash_json($1, $2::jsonb) AS request_hash",
    [
      "qc2.execution.normalized-request.v1",
      JSON.stringify(request),
    ],
  );
  return result.rows[0].request_hash;
}

async function beginAttempt(
  client,
  adminClient,
  delivery,
  intent,
  gate,
  request,
) {
  const hash = await requestHash(adminClient, request);
  const result = await client.query(
    `
      SELECT * FROM qc2_control.begin_paper_order_attempt(
        $1::uuid, $2::uuid, $3::bigint, $4::jsonb, $5::text, $6::jsonb
      )
    `,
    [
      delivery.message_id,
      delivery.worker_id,
      delivery.fencing_generation,
      JSON.stringify(request),
      hash,
      JSON.stringify(gate),
    ],
  );
  return result.rows[0];
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

export async function runQc2046ExecutionAuthorityAcceptance({
  connectionString,
  adminClient,
  intentFixture,
  reservationFixture,
}) {
  const account = createHash("sha256")
    .update(`qc2-046-paper-${randomBytes(12).toString("hex")}`)
    .digest("hex");
  const execution = await executionClient(connectionString);
  try {
    const entry = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account,
        action: "OPEN_LONG",
        reservationId: uuidV7(),
      }),
    );
    const entryReservation = buildReservation(
      reservationFixture,
      entry,
      entry.reservation_ref.target_id,
    );
    await prepareIntent(execution, entry, entryReservation);
    const outboxId = await enqueue(execution, entry.id);
    assert.equal(await enqueue(execution, entry.id), outboxId);

    const firstWorker = uuidV7();
    const firstDelivery = await claim(execution, firstWorker, 1);
    assert.ok(firstDelivery);
    const entryGate = gateFor(entry, "NEW_ENTRY");
    const entryRequest = requestFor(entry, entryGate);
    const ambiguousGate = {
      ...entryGate,
      readiness: [
        ...entryGate.readiness,
        {
          ...entryGate.readiness[0],
          assessment_id: uuidV7(),
        },
      ],
    };
    const entryRequestHash = await requestHash(adminClient, entryRequest);
    await expectSqlState(execution, "42501", async () => {
      await execution.query(
        `
          SELECT * FROM qc2_control.begin_paper_order_attempt(
            $1::uuid, $2::uuid, $3::bigint, $4::jsonb, $5::text, $6::jsonb
          )
        `,
        [
          firstDelivery.message_id,
          firstDelivery.worker_id,
          firstDelivery.fencing_generation,
          JSON.stringify(entryRequest),
          entryRequestHash,
          JSON.stringify(ambiguousGate),
        ],
      );
    });
    const attempt = await beginAttempt(
      execution,
      adminClient,
      firstDelivery,
      entry,
      entryGate,
      entryRequest,
    );
    assert.equal(attempt.created, true);
    assert.equal(attempt.attempt_state, "SUBMISSION_STARTED");
    const authorized = await execution.query(
      `
        SELECT qc2_control.authorize_paper_order_attempt(
          $1::uuid, $2::uuid, $3::bigint, $4::uuid, $5::jsonb
        ) AS authorized
      `,
      [
        firstDelivery.message_id,
        firstDelivery.worker_id,
        firstDelivery.fencing_generation,
        attempt.attempt_id,
        JSON.stringify(entryGate),
      ],
    );
    assert.equal(authorized.rows[0].authorized, true);

    await adminClient.query("SELECT pg_catalog.pg_sleep(1.1)");
    const secondWorker = uuidV7();
    const recoveredDelivery = await claim(execution, secondWorker);
    assert.ok(recoveredDelivery);
    assert.ok(recoveredDelivery.fencing_generation > firstDelivery.fencing_generation);
    const recovered = await execution.query(
      `
        SELECT qc2_control.mark_paper_order_attempt_unknown(
          $1::uuid, $2::uuid, $3::bigint, $4::uuid
        ) AS marked_unknown
      `,
      [
        recoveredDelivery.message_id,
        recoveredDelivery.worker_id,
        recoveredDelivery.fencing_generation,
        attempt.attempt_id,
      ],
    );
    assert.equal(recovered.rows[0].marked_unknown, true);
    const singleSourceAbsence = {
      intent_id: entry.id,
      account_fingerprint: account,
      client_order_key: entry.idempotency_key,
      normalized_request_hash: attempt.normalized_request_hash,
      disposition: "ABSENCE_PROVEN",
      checked_sources: ["account_orders"],
      consistency_window_closed: true,
      broker_order_id: null,
    };
    await expectSqlState(execution, "23514", async () => {
      await execution.query(
        "SELECT qc2_control.resolve_paper_order_attempt_unknown($1::uuid, $2::jsonb)",
        [attempt.attempt_id, JSON.stringify(singleSourceAbsence)],
      );
    });
    const completed = await execution.query(
      `
        SELECT qc2_control.complete_paper_order_submission(
          $1::uuid, $2::uuid, $3::bigint
        ) AS completed
      `,
      [
        recoveredDelivery.message_id,
        recoveredDelivery.worker_id,
        recoveredDelivery.fencing_generation,
      ],
    );
    assert.equal(completed.rows[0].completed, true);

    const staleFinish = await execution.query(
      `
        SELECT qc2_control.finish_paper_order_attempt(
          $1::uuid, $2::uuid, $3::bigint, $4::uuid, 'ACKNOWLEDGED',
          'late-order-id', 'OPEN', NULL
        ) AS finished
      `,
      [
        firstDelivery.message_id,
        firstDelivery.worker_id,
        firstDelivery.fencing_generation,
        attempt.attempt_id,
      ],
    );
    assert.equal(staleFinish.rows[0].finished, false);
    const terminal = await adminClient.query(
      `
        SELECT attempt.attempt_state, intent.intent_state,
               submission.outcome, message.status,
               (SELECT pg_catalog.count(*)::integer
                FROM qc2_execution.paper_execution_attempt AS all_attempts
                WHERE all_attempts.intent_id = intent.id) AS attempt_count
        FROM qc2_execution.paper_execution_attempt AS attempt
        JOIN qc2_execution.paper_order_intent AS intent
          ON intent.id = attempt.intent_id
        JOIN qc2_execution.submission_attempt_contract AS submission
          ON submission.id = attempt.id
        JOIN qc2_control.outbox_message AS message
          ON message.id = attempt.outbox_message_id
        WHERE attempt.id = $1::uuid
      `,
      [attempt.attempt_id],
    );
    assert.deepEqual(terminal.rows[0], {
      attempt_state: "SUBMISSION_UNKNOWN",
      intent_state: "SUBMISSION_UNKNOWN",
      outcome: "SUBMISSION_UNKNOWN",
      status: "DELIVERED",
      attempt_count: 1,
    });
    assert.equal(await enqueue(execution, entry.id), outboxId);
    assert.equal(await claim(execution, uuidV7()), null);

    const cancel = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account,
        action: "CANCEL_PENDING_ENTRY",
        sourceRef: reference(
          "qc2.execution.PaperOrderIntent.v1",
          entry.id,
          entry.content_hash,
        ),
      }),
    );
    await prepareIntent(execution, cancel, null);
    const cancelOutboxId = await enqueue(execution, cancel.id);
    const cancelWorker = uuidV7();
    const cancelDelivery = await claim(execution, cancelWorker);
    assert.ok(cancelDelivery);
    const cancelGate = gateFor(cancel, "CANCEL_ENTRY", {
      priorIntentState: "SUBMISSION_UNKNOWN",
      priorReservationActive: true,
    });
    const cancelRequest = requestFor(cancel, cancelGate, entry);
    const cancelAttempt = await beginAttempt(
      execution,
      adminClient,
      cancelDelivery,
      cancel,
      cancelGate,
      cancelRequest,
    );
    const cancelAuthorization = await execution.query(
      `
        SELECT qc2_control.authorize_paper_order_attempt(
          $1::uuid, $2::uuid, $3::bigint, $4::uuid, $5::jsonb
        ) AS authorized
      `,
      [
        cancelDelivery.message_id,
        cancelDelivery.worker_id,
        cancelDelivery.fencing_generation,
        cancelAttempt.attempt_id,
        JSON.stringify(cancelGate),
      ],
    );
    assert.equal(cancelAuthorization.rows[0].authorized, true);
    const cancelUnknown = await execution.query(
      `
        SELECT qc2_control.finish_paper_order_attempt(
          $1::uuid, $2::uuid, $3::bigint, $4::uuid, 'SUBMISSION_UNKNOWN',
          NULL, NULL, 'SIMULATED_CANCEL_TIMEOUT'
        ) AS finished
      `,
      [
        cancelDelivery.message_id,
        cancelDelivery.worker_id,
        cancelDelivery.fencing_generation,
        cancelAttempt.attempt_id,
      ],
    );
    assert.equal(cancelUnknown.rows[0].finished, true);
    await execution.query(
      `
        SELECT qc2_control.complete_paper_order_submission(
          $1::uuid, $2::uuid, $3::bigint
        )
      `,
      [
        cancelDelivery.message_id,
        cancelDelivery.worker_id,
        cancelDelivery.fencing_generation,
      ],
    );
    const priorAfterCancelUnknown = await adminClient.query(
      `
        SELECT intent.intent_state, resource.state AS reservation_state
        FROM qc2_execution.paper_order_intent AS intent
        JOIN qc2_execution.paper_order_intent_reservation AS intent_reservation
          ON intent_reservation.intent_id = intent.id
        JOIN qc2_execution.resource_reservation AS resource
          ON resource.resource_key = intent_reservation.resource_key
         AND resource.reservation_key = intent.id::text
        WHERE intent.id = $1::uuid
      `,
      [entry.id],
    );
    assert.deepEqual(priorAfterCancelUnknown.rows[0], {
      intent_state: "CANCEL_REQUESTED",
      reservation_state: "ACTIVE",
    });

    const replacement = await sealIntent(
      adminClient,
      buildIntent(intentFixture, {
        account,
        action: "REPLACE_ORDER",
        reservationId: uuidV7(),
        sourceRef: reference(
          "qc2.execution.PaperOrderIntent.v1",
          entry.id,
          entry.content_hash,
        ),
      }),
    );
    const replacementReservation = buildReservation(
      reservationFixture,
      replacement,
      replacement.reservation_ref.target_id,
    );
    await prepareIntent(execution, replacement, replacementReservation);
    const replacementOutboxId = await enqueue(execution, replacement.id);
    const replacementWorker = uuidV7();
    const replacementDelivery = await claim(execution, replacementWorker);
    assert.ok(replacementDelivery);
    const replacementGate = gateFor(replacement, "NEW_ENTRY", {
      priorIntentState: "CANCEL_REQUESTED",
      priorReservationActive: true,
    });
    const replacementRequest = requestFor(replacement, replacementGate);
    const replacementHash = await requestHash(adminClient, replacementRequest);
    await expectSqlState(execution, "23514", async () => {
      await execution.query(
        `
          SELECT * FROM qc2_control.begin_paper_order_attempt(
            $1::uuid, $2::uuid, $3::bigint, $4::jsonb, $5::text, $6::jsonb
          )
        `,
        [
          replacementDelivery.message_id,
          replacementDelivery.worker_id,
          replacementDelivery.fencing_generation,
          JSON.stringify(replacementRequest),
          replacementHash,
          JSON.stringify(replacementGate),
        ],
      );
    });
    const noReplacementAttempt = await adminClient.query(
      "SELECT pg_catalog.count(*)::integer AS count FROM qc2_execution.paper_execution_attempt WHERE intent_id = $1::uuid",
      [replacement.id],
    );
    assert.equal(noReplacementAttempt.rows[0].count, 0);
    const deferred = await execution.query(
      `
        SELECT qc2_control.defer_paper_order_submission(
          $1::uuid, $2::uuid, $3::bigint, 'PRIOR_ORDER_NOT_DEFINITIVELY_TERMINAL'
        ) AS deferred
      `,
      [
        replacementDelivery.message_id,
        replacementDelivery.worker_id,
        replacementDelivery.fencing_generation,
      ],
    );
    assert.equal(deferred.rows[0].deferred, true);
    const replacementOutbox = await adminClient.query(
      `
        SELECT message.status, intent.intent_state
        FROM qc2_control.outbox_message AS message
        JOIN qc2_execution.paper_order_intent AS intent
          ON intent.id = message.logical_operation_id
        WHERE message.id = $1::uuid
      `,
      [replacementOutboxId],
    );
    assert.deepEqual(replacementOutbox.rows[0], {
      status: "PENDING",
      intent_state: "QUEUED_FOR_SUBMISSION",
    });
    const priorReservation = await adminClient.query(
      `
        SELECT resource.state
        FROM qc2_execution.paper_order_intent_reservation AS intent_reservation
        JOIN qc2_execution.resource_reservation AS resource
          ON resource.resource_key = intent_reservation.resource_key
         AND resource.reservation_key = intent_reservation.intent_id::text
        WHERE intent_reservation.intent_id = $1::uuid
      `,
      [entry.id],
    );
    assert.equal(priorReservation.rows[0].state, "ACTIVE");

    const cancellationAttemptCount = await adminClient.query(
      `
        SELECT pg_catalog.count(*)::integer AS count
        FROM qc2_execution.paper_execution_attempt
        WHERE intent_id = $1::uuid
      `,
      [cancel.id],
    );
    assert.equal(cancellationAttemptCount.rows[0].count, 1);
    assert.ok(cancelOutboxId);
    return {
      intentId: entry.id,
      attemptId: attempt.attempt_id,
      cancelIntentId: cancel.id,
      replacementIntentId: replacement.id,
    };
  } finally {
    await execution.end();
  }
}
