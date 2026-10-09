import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const require = createRequire(
  new URL("../../lib/db/package.json", import.meta.url),
);
const { Client } = require("pg");
const connectionString = process.env.QC2_POSTGRES_TEST_URL;
const expectedDatabase = process.env.QC2_EXPECTED_DATABASE_TEST;

if (process.env.QC2_ENV !== "test") {
  throw new Error("Set QC2_ENV=test before running owner-command acceptance.");
}
if (!connectionString || !expectedDatabase) {
  throw new Error(
    "QC2_POSTGRES_TEST_URL and QC2_EXPECTED_DATABASE_TEST are required; values are not logged.",
  );
}

const baseUrl = new URL(connectionString);
const configuredDatabase = decodeURIComponent(
  baseUrl.pathname.replace(/^\//, ""),
);
if (
  !/^qc2_test_[a-z0-9_]+$/.test(configuredDatabase) ||
  configuredDatabase !== expectedDatabase
) {
  throw new Error(
    "Owner-command acceptance requires a dedicated qc2_test_* database.",
  );
}
if (
  ["DEVELOPMENT", "RESEARCH", "PRODUCTION"].some(
    (environment) =>
      process.env[`QC2_EXPECTED_DATABASE_${environment}`] ===
      configuredDatabase,
  ) ||
  Object.entries(process.env).some(
    ([key, value]) =>
      key.startsWith("QC2_DATABASE_URL_") && value === connectionString,
  )
) {
  throw new Error(
    "Owner-command acceptance cannot reuse a configured runtime database.",
  );
}

const migrationNames = [
  "0001_postgresql_authority_foundation.sql",
  "0002_evidence_authority.sql",
  "0003_prediction_authority.sql",
  "0004_validation_authority.sql",
  "0005_apexlab_experiment_ledger.sql",
  "0006_model_registry.sql",
  "0007_atomic_champion_transition.sql",
  "0008_paper_order_intents.sql",
  "0009_execution_authority.sql",
  "0010_durable_position_state.sql",
  "0011_broker_reconciliation.sql",
  "0012_execution_readiness.sql",
  "0013_owner_identity_device_enrollment.sql",
  "0014_owner_read_models.sql",
  "0015_owner_api_command_receipts.sql",
];
const scratchDatabase =
  `qc2_test_owner_commands_${process.pid}_${randomBytes(4).toString("hex")}`;
const scratchUrl = new URL(connectionString);
scratchUrl.pathname = `/${scratchDatabase}`;
const baseClient = new Client({ connectionString });
const scratchClient = new Client({ connectionString: scratchUrl.toString() });
let scratchCreated = false;

const NOW = Date.parse("2026-10-09T17:00:00.000Z");
const DEVICE_ID = uuid7(2);
const SESSION_RECORD_ID = uuid7(3);
const SESSION_ID = `session-${"c".repeat(32)}`;
const DEVICE_FINGERPRINT = createHash("sha256")
  .update("owner-command-integration-device")
  .digest("hex");
const OWNER_KEY_ID = "primary_key";
const SCOPES = [
  "OWNER_READ",
  "PROMOTION",
  "EPOCH_ACTIVATION",
  "PAUSE",
  "RESUME",
  "ALERT",
  "DEVICE_ADMIN",
];

function uuid7(sequence) {
  return `10000000-0000-7000-8000-${String(sequence).padStart(12, "0")}`;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function instant(seconds = 0) {
  return new Date(NOW + seconds * 1000)
    .toISOString()
    .replace(".000Z", "Z");
}

async function withSessionAuthorization(role, callback) {
  await scratchClient.query(`SET SESSION AUTHORIZATION "${role}"`);
  try {
    return await callback();
  } finally {
    await scratchClient.query("RESET SESSION AUTHORIZATION");
  }
}

async function expectSqlState(promise, code) {
  await assert.rejects(promise, (error) => error?.code === code);
}

async function hashJson(domain, value) {
  const result = await scratchClient.query(
    "SELECT qc2_integrity_build.hash_json($1::text, $2::jsonb) AS hash",
    [domain, JSON.stringify(value)],
  );
  return result.rows[0].hash;
}

async function makeChallenge({
  id,
  commandId,
  idempotencyKey,
  requestBody,
  issuedAt = instant(),
  expiresAt = instant(90),
}) {
  const requestBodyHash = await hashJson(
    "qc2.owner.command-body.v1",
    requestBody,
  );
  return {
    schema_name: "qc2.owner_api.OwnerSignedCommandChallenge.v1",
    schema_version: "1.0",
    environment_namespace: "test",
    id,
    command_id: commandId,
    command_type: "PAUSE_NEW_ENTRIES",
    idempotency_key: idempotencyKey,
    request_body_hash: requestBodyHash,
    device_ref: {
      target_schema_name: "qc2.governance_owner.OwnerDevice.v1",
      target_id: DEVICE_ID,
    },
    session_ref: {
      target_schema_name: "qc2.governance_owner.OwnerSession.v1",
      target_id: SESSION_RECORD_ID,
    },
    owner_key_id: OWNER_KEY_ID,
    public_key_fingerprint: DEVICE_FINGERPRINT,
    scope: "PAUSE",
    nonce: `n${"d".repeat(64)}`,
    issued_at: issuedAt,
    expires_at: expiresAt,
  };
}

function challengeBinding(challenge) {
  return {
    device_id: DEVICE_ID,
    session_record_id: SESSION_RECORD_ID,
    session_id: SESSION_ID,
    request_body_hash: challenge.request_body_hash,
  };
}

async function storeChallenge(challenge) {
  return withSessionAuthorization("qc2_runtime_identity", async () => {
    const { rows } = await scratchClient.query(
      `SELECT qc2_governance_owner.identity_store_command_challenge(
        $1::text, $2::jsonb, $3::jsonb
      ) AS result`,
      [
        "test",
        JSON.stringify(challenge),
        JSON.stringify(challengeBinding(challenge)),
      ],
    );
    return rows[0].result;
  });
}

async function makeOwnerCommand(challenge, sequence) {
  const command = {
    schema_name: "qc2.governance_owner.OwnerCommand.v1",
    schema_version: "1.0",
    id: uuid7(sequence),
    created_at: challenge.issued_at,
    owning_authority: "owner_api",
    evidence_class: "SYNTHETIC_FIXTURE",
    environment_namespace: "test",
    source_refs: [],
    command_id: challenge.command_id,
    command_type: challenge.command_type,
    idempotency_key: challenge.idempotency_key,
    request_body_hash: challenge.request_body_hash,
    issued_at: challenge.issued_at,
    device_ref: challenge.device_ref,
    signature: "AQID",
    scope: challenge.scope,
    content_hash: "0".repeat(64),
  };
  const content = {
    owning_authority: command.owning_authority,
    evidence_class: command.evidence_class,
    environment_namespace: command.environment_namespace,
    source_refs: command.source_refs,
    command_id: command.command_id,
    command_type: command.command_type,
    idempotency_key: command.idempotency_key,
    request_body_hash: command.request_body_hash,
    issued_at: command.issued_at,
    device_ref: command.device_ref,
    signature: command.signature,
    scope: command.scope,
  };
  command.content_hash = await hashJson(
    "qc2.contract-content.v1/qc2.governance_owner.ownercommand.v1/1.0",
    content,
  );
  return command;
}

async function commit(challenge, requestBody, sequence, now = instant()) {
  const ownerCommand = await makeOwnerCommand(challenge, sequence);
  return withSessionAuthorization("qc2_runtime_identity", async () => {
    const { rows } = await scratchClient.query(
      `SELECT qc2_governance_owner.owner_api_commit_signed_command(
        $1::text, $2::uuid, $3::jsonb, $4::jsonb, NULL, $5::uuid,
        $6::timestamptz
      ) AS result`,
      [
        "test",
        challenge.id,
        JSON.stringify(ownerCommand),
        JSON.stringify(requestBody),
        uuid7(sequence + 1),
        now,
      ],
    );
    return rows[0].result;
  });
}

async function seedOwnerIdentity() {
  const deviceRecord = {
    schema_name: "qc2.governance_owner.OwnerDevice.v1",
    schema_version: "1.0",
    id: DEVICE_ID,
    created_at: instant(),
    owning_authority: "identity",
    evidence_class: "SYNTHETIC_FIXTURE",
    environment_namespace: "test",
    source_refs: [],
    owner_key_id: OWNER_KEY_ID,
    public_key: "AQIDBA",
    public_key_fingerprint: DEVICE_FINGERPRINT,
    signing_algorithm: "ECDSA_P256_SHA256",
    security_level: "UNKNOWN",
    enrollment_proof_hash: sha256("enrollment-proof"),
    owner_binding: "primary_owner",
    app_version: "owner-command-integration-1",
    revocation_state: "ENROLLED",
    enrolled_at: instant(),
    revoked_at: null,
  };
  const sessionRecord = {
    schema_name: "qc2.governance_owner.OwnerSession.v1",
    schema_version: "1.0",
    id: SESSION_RECORD_ID,
    created_at: instant(),
    owning_authority: "identity",
    evidence_class: "SYNTHETIC_FIXTURE",
    environment_namespace: "test",
    source_refs: [],
    device_ref: {
      target_schema_name: "qc2.governance_owner.OwnerDevice.v1",
      target_id: DEVICE_ID,
    },
    session_id: SESSION_ID,
    issued_at: instant(),
    expires_at: instant(900),
    revoked_at: null,
    scope_refs: SCOPES,
    refresh_generation: 1,
  };

  await withSessionAuthorization("qc2_migrator", async () => {
    await scratchClient.query(
      `INSERT INTO qc2_governance_owner.identity_owner(
        environment_namespace, owner_binding, bootstrap_verifier_hash,
        bootstrap_consumed_at, recovery_verifier_hash
      ) VALUES ('test', 'primary_owner', $1, $2::timestamptz, $3)`,
      [sha256("bootstrap-verifier"), instant(), sha256("recovery-verifier")],
    );
    await scratchClient.query(
      `INSERT INTO qc2_governance_owner.identity_device(
        environment_namespace, id, owner_binding, public_key_fingerprint, record
      ) VALUES ('test', $1::uuid, 'primary_owner', $2, $3::jsonb)`,
      [DEVICE_ID, DEVICE_FINGERPRINT, JSON.stringify(deviceRecord)],
    );
    await scratchClient.query(
      `INSERT INTO qc2_governance_owner.identity_session(
        environment_namespace, id, session_id, device_id, generation, record
      ) VALUES ('test', $1::uuid, $2, $3::uuid, 1, $4::jsonb)`,
      [
        SESSION_RECORD_ID,
        SESSION_ID,
        DEVICE_ID,
        JSON.stringify(sessionRecord),
      ],
    );
  });
}

try {
  await baseClient.connect();
  await baseClient.query(`CREATE DATABASE "${scratchDatabase}"`);
  scratchCreated = true;
  await scratchClient.connect();

  const serverEncoding = await scratchClient.query(
    "SELECT current_setting('server_encoding') AS encoding",
  );
  assert.equal(serverEncoding.rows[0].encoding, "UTF8");

  for (const migrationName of migrationNames) {
    const migration = await readFile(
      path.join(repositoryRoot, "migrations", migrationName),
      "utf8",
    );
    await scratchClient.query(migration);
  }

  await seedOwnerIdentity();
  const requestBody = {
    schema_name: "qc2.owner_api.OwnerCommandRequest.v1",
    schema_version: "1.0",
    command_type: "PAUSE_NEW_ENTRIES",
    payload: {
      expected_generation: 0,
      reason_code: "integration-test",
    },
  };
  const firstChallenge = await makeChallenge({
    id: uuid7(10),
    commandId: "cmd-owner-pause-001",
    idempotencyKey: "owner-pause-integration",
    requestBody,
  });
  assert.equal((await storeChallenge(firstChallenge)).status, "STORED");

  const committed = await commit(firstChallenge, requestBody, 20);
  assert.equal(committed.status, "COMMITTED");
  assert.equal(committed.receipt.state, "ACCEPTED");
  assert.equal(committed.receipt.resulting_evidence_ref, null);
  assert.ok(committed.receipt.source_sequence > 0);
  assert.ok(committed.receipt.projection_lag_ms >= 0);

  const duplicate = await commit(firstChallenge, requestBody, 22);
  assert.equal(duplicate.status, "DUPLICATE");
  assert.deepEqual(duplicate.receipt, committed.receipt);
  assert.deepEqual(duplicate.owner_command, committed.owner_command);

  const changedBody = structuredClone(requestBody);
  changedBody.payload.reason_code = "changed-content";
  const changedChallenge = await makeChallenge({
    id: uuid7(30),
    commandId: "cmd-owner-pause-002",
    idempotencyKey: firstChallenge.idempotency_key,
    requestBody: changedBody,
  });
  assert.equal((await storeChallenge(changedChallenge)).status, "STORED");
  await expectSqlState(
    commit(changedChallenge, changedBody, 32),
    "23505",
  );

  const expiredChallenge = await makeChallenge({
    id: uuid7(40),
    commandId: "cmd-owner-pause-expired",
    idempotencyKey: "owner-pause-expired",
    requestBody,
    expiresAt: instant(1),
  });
  assert.equal((await storeChallenge(expiredChallenge)).status, "STORED");
  await expectSqlState(
    commit(expiredChallenge, requestBody, 42, instant(2)),
    "55000",
  );

  const revokedChallenge = await makeChallenge({
    id: uuid7(50),
    commandId: "cmd-owner-pause-revoked",
    idempotencyKey: "owner-pause-revoked",
    requestBody,
  });
  assert.equal((await storeChallenge(revokedChallenge)).status, "STORED");
  await withSessionAuthorization("qc2_migrator", () =>
    scratchClient.query(
      `UPDATE qc2_governance_owner.identity_device
       SET revoked_at = $1::timestamptz
       WHERE environment_namespace = 'test' AND id = $2::uuid`,
      [instant(3), DEVICE_ID],
    ),
  );
  await expectSqlState(
    commit(revokedChallenge, requestBody, 52, instant(4)),
    "42501",
  );

  const projected = await withSessionAuthorization(
    "qc2_runtime_promotion",
    async () => {
      const { rows } = await scratchClient.query(
        `SELECT qc2_governance_owner.owner_command_payload_by_command(
          'test', $1::text
        ) AS result`,
        [committed.owner_command.command_id],
      );
      return rows[0].result;
    },
  );
  assert.equal(projected.status, "FOUND");
  assert.equal(projected.source_sequence, committed.receipt.source_sequence);
  assert.deepEqual(projected.request_body, requestBody);
  assert.deepEqual(projected.receipt, committed.receipt);

  await expectSqlState(
    withSessionAuthorization("qc2_runtime_owner_api", () =>
      scratchClient.query(
        `SELECT * FROM qc2_governance_owner.owner_command_receipt_projection
         LIMIT 1`,
      ),
    ),
    "42501",
  );
  await expectSqlState(
    withSessionAuthorization("qc2_runtime_identity", () =>
      scratchClient.query(
        `SELECT * FROM qc2_governance_owner.owner_command_receipt_projection
         LIMIT 1`,
      ),
    ),
    "42501",
  );

  console.log("QC2-055 PostgreSQL acceptance passed.");
} finally {
  await scratchClient.end().catch(() => {});
  if (scratchCreated) {
    await baseClient
      .query(`DROP DATABASE IF EXISTS "${scratchDatabase}" WITH (FORCE)`)
      .catch(() => {});
  }
  await baseClient.end().catch(() => {});
}
