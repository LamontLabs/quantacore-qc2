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
  throw new Error("Set QC2_ENV=test before running identity integration.");
}
if (!connectionString || !expectedDatabase) {
  throw new Error(
    "QC2_POSTGRES_TEST_URL and QC2_EXPECTED_DATABASE_TEST are required; values are not logged.",
  );
}

const parsedUrl = new URL(connectionString);
const configuredDatabase = decodeURIComponent(
  parsedUrl.pathname.replace(/^\//, ""),
);
if (
  !/^qc2_test_[a-z0-9_]+$/.test(configuredDatabase) ||
  configuredDatabase !== expectedDatabase
) {
  throw new Error(
    "Identity acceptance requires a dedicated qc2_test_* database.",
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
    "Identity acceptance cannot reuse a configured runtime database.",
  );
}

const migrations = [
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
].map((name) => path.join(repositoryRoot, "migrations", name));
const scratchDatabase = `qc2_test_identity_${process.pid}_${randomBytes(4).toString("hex")}`;
const scratchUrl = new URL(connectionString);
scratchUrl.pathname = `/${scratchDatabase}`;
const baseClient = new Client({ connectionString });
let scratchClient;
let raceClient;
let scratchCreated = false;
let removeQc2RolesCreatedByTest = false;

function hash(label) {
  return createHash("sha256").update(label).digest("hex");
}

function uuid7(sequence) {
  return `10000000-0000-7000-8000-${String(sequence).padStart(12, "0")}`;
}

function instant(seconds = 0) {
  return new Date(Date.parse("2026-10-09T17:00:00.000Z") + seconds * 1000)
    .toISOString()
    .replace(".000Z", "Z");
}

async function withSessionAuthorization(client, role, callback) {
  await client.query(`SET SESSION AUTHORIZATION "${role}"`);
  try {
    return await callback();
  } finally {
    await client.query("RESET SESSION AUTHORIZATION");
  }
}

async function identityQuery(client, text, values = []) {
  return withSessionAuthorization(client, "qc2_runtime_identity", async () => {
    const result = await client.query(text, values);
    return result.rows[0]?.result;
  });
}

async function expectSqlState(promise, expectedCode) {
  let caught;
  try {
    await promise;
  } catch (error) {
    caught = error;
  }
  assert.ok(caught, `expected PostgreSQL SQLSTATE ${expectedCode}`);
  assert.equal(caught.code, expectedCode);
}

function ownerDevice({
  id,
  ownerKeyId,
  ownerBinding,
  publicKey,
  fingerprint,
  now,
  appVersion = "identity-test-1",
}) {
  return {
    schema_name: "qc2.governance_owner.OwnerDevice.v1",
    schema_version: "1.0",
    id,
    created_at: now,
    owning_authority: "identity",
    evidence_class: "SYNTHETIC_FIXTURE",
    environment_namespace: "test",
    source_refs: [],
    owner_key_id: ownerKeyId,
    public_key: publicKey,
    signing_algorithm: "ECDSA_P256_SHA256",
    security_level: "UNKNOWN",
    enrollment_proof_hash: hash(`proof:${id}`),
    owner_binding: ownerBinding,
    app_version: appVersion,
    revocation_state: "ENROLLED",
    enrolled_at: now,
    revoked_at: null,
  };
}

function ownerSession({
  id,
  deviceId,
  sessionId,
  generation,
  now,
  scopes,
  lifetimeSeconds = 900,
}) {
  return {
    schema_name: "qc2.governance_owner.OwnerSession.v1",
    schema_version: "1.0",
    id,
    created_at: now,
    owning_authority: "identity",
    evidence_class: "SYNTHETIC_FIXTURE",
    environment_namespace: "test",
    source_refs: [],
    device_ref: {
      target_schema_name: "qc2.governance_owner.OwnerDevice.v1",
      target_id: deviceId,
    },
    session_id: sessionId,
    issued_at: now,
    expires_at: instant(
      Math.round((Date.parse(now) - Date.parse(instant())) / 1000) +
        lifetimeSeconds,
    ),
    revoked_at: null,
    scope_refs: scopes,
    refresh_generation: generation,
  };
}

async function runIdentityAcceptance(client, raceClient) {
  const ownerBinding = "primary_owner";
  const bootstrapVerifierHash = hash("bootstrap-verifier");
  const recoveryVerifierHash = hash("offline-recovery-verifier");
  const initialScopes = [
    "OWNER_READ",
    "PROMOTION",
    "EPOCH_ACTIVATION",
    "PAUSE",
    "RESUME",
    "ALERT",
    "DEVICE_ADMIN",
  ];
  const deviceId = uuid7(2);
  const familyId = `session-${"1".padStart(32, "0")}`;
  const initialSessionId = uuid7(3);
  const bootstrapChallengeId = uuid7(1);
  const initialAccessHash = hash("initial-access-verifier");
  const initialRefreshHash = hash("initial-refresh-verifier");
  const recoveryMaterialHash = recoveryVerifierHash;
  const publicKey = "AQIDBA";
  const fingerprint = hash("initial-public-key");
  const bootstrapAt = instant();
  const bootstrapExpiresAt = instant(300);
  const bootstrapContract = {
    schema_name: "qc2.governance_owner.EnrollmentChallenge.v1",
    schema_version: "1.0",
    id: bootstrapChallengeId,
    created_at: bootstrapAt,
    owning_authority: "identity",
    evidence_class: "SYNTHETIC_FIXTURE",
    environment_namespace: "test",
    source_refs: [],
    owner_binding: ownerBinding,
    bootstrap_verifier_hash: bootstrapVerifierHash,
    nonce: `n${"a".repeat(64)}`,
    issued_at: bootstrapAt,
    expires_at: bootstrapExpiresAt,
    single_use: true,
    consumed_at: null,
  };
  const bootstrapPending = {
    schema_name: "qc2.owner_api.OwnerEnrollmentChallenge.v1",
    schema_version: "1.0",
    environment_namespace: "test",
    challenge_id: bootstrapChallengeId,
    owner_binding: ownerBinding,
    owner_key_id: "primary_key",
    public_key_fingerprint: fingerprint,
    signing_algorithm: "ECDSA_P256_SHA256",
    security_level: "UNKNOWN",
    app_version: "identity-test-1",
    nonce: bootstrapContract.nonce,
    issued_at: bootstrapAt,
    expires_at: bootstrapExpiresAt,
    bootstrap_verifier_hash: bootstrapVerifierHash,
    public_key_der: publicKey,
  };
  const device = ownerDevice({
    id: deviceId,
    ownerKeyId: "primary_key",
    ownerBinding,
    publicKey,
    fingerprint,
    now: bootstrapAt,
  });
  const session = ownerSession({
    id: initialSessionId,
    deviceId,
    sessionId: familyId,
    generation: 1,
    now: bootstrapAt,
    scopes: initialScopes,
  });

  await withSessionAuthorization(client, "qc2_migrator", async () => {
    await client.query(
      "SELECT qc2_governance_owner.identity_provision_owner($1, $2, $3)",
      ["test", ownerBinding, bootstrapVerifierHash],
    );
    await expectSqlState(
      client.query(
        "SELECT qc2_governance_owner.identity_provision_owner($1, $2, $3)",
        ["test", "second_owner", hash("second-bootstrap")],
      ),
      "23505",
    );
  });

  const unprovisioned = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_bootstrap_state($1) AS result",
    ["development"],
  );
  assert.equal(unprovisioned.status, "NOT_PROVISIONED");
  const provisioning = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_bootstrap_state($1) AS result",
    ["test"],
  );
  assert.equal(provisioning.owner_binding, ownerBinding);
  assert.equal(provisioning.bootstrap_verifier_hash, bootstrapVerifierHash);

  await withSessionAuthorization(client, "qc2_runtime_identity", async () => {
    await expectSqlState(
      client.query("SELECT * FROM qc2_governance_owner.identity_owner"),
      "42501",
    );
  });

  let result = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_store_bootstrap_challenge($1, $2::jsonb, $3::jsonb) AS result",
    [
      "test",
      JSON.stringify(bootstrapContract),
      JSON.stringify(bootstrapPending),
    ],
  );
  assert.equal(result.status, "STORED");
  const completeBootstrapStatement =
    "SELECT qc2_governance_owner.identity_complete_bootstrap($1, $2::uuid, $3, $4::jsonb, $5::jsonb, $6, $7, $8::timestamptz, $9, $10::timestamptz) AS result";
  const completeBootstrapParameters = [
    "test",
    bootstrapChallengeId,
    bootstrapVerifierHash,
    JSON.stringify(device),
    JSON.stringify(session),
    initialAccessHash,
    initialRefreshHash,
    instant(86_400),
    recoveryMaterialHash,
    instant(1),
  ];
  const bootstrapRace = await Promise.allSettled([
    identityQuery(
      client,
      completeBootstrapStatement,
      completeBootstrapParameters,
    ),
    identityQuery(
      raceClient,
      completeBootstrapStatement,
      completeBootstrapParameters,
    ),
  ]);
  const bootstrapWinners = bootstrapRace.filter(
    (outcome) => outcome.status === "fulfilled",
  );
  const bootstrapLosers = bootstrapRace.filter(
    (outcome) => outcome.status === "rejected",
  );
  assert.equal(bootstrapWinners.length, 1);
  assert.equal(bootstrapWinners[0].value.status, "COMPLETED");
  assert.equal(bootstrapLosers.length, 1);
  assert.equal(bootstrapLosers[0].reason.code, "55000");

  const access = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_resolve_access($1, $2, $3::timestamptz) AS result",
    ["test", initialAccessHash, instant(2)],
  );
  assert.equal(access.status, "VALID");
  assert.equal(access.device_record.id, deviceId);
  const crossEnvironmentAccess = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_resolve_access($1, $2, $3::timestamptz) AS result",
    ["development", initialAccessHash, instant(2)],
  );
  assert.equal(crossEnvironmentAccess.status, "INVALID_IDENTITY");

  const additionalChallengeId = uuid7(14);
  const additionalDeviceId = uuid7(15);
  const additionalSessionId = uuid7(16);
  const additionalFamilyId = `session-${"3".padStart(32, "0")}`;
  const additionalPublicKey = "AQIDBg";
  const additionalFingerprint = hash("additional-public-key");
  const additionalScopes = ["OWNER_READ", "DEVICE_ADMIN"];
  const additionalAt = instant(2);
  const additionalChallenge = {
    schema_name: "qc2.owner_api.OwnerDeviceEnrollmentChallenge.v1",
    schema_version: "1.0",
    environment_namespace: "test",
    id: additionalChallengeId,
    owner_binding: ownerBinding,
    authorized_by_device_ref: {
      target_schema_name: "qc2.governance_owner.OwnerDevice.v1",
      target_id: deviceId,
    },
    authorized_by_session_ref: {
      target_schema_name: "qc2.governance_owner.OwnerSession.v1",
      target_id: initialSessionId,
    },
    owner_key_id: "travel_key",
    public_key_fingerprint: additionalFingerprint,
    signing_algorithm: "ECDSA_P256_SHA256",
    security_level: "UNKNOWN",
    app_version: "identity-test-1",
    scope_refs: additionalScopes,
    nonce: `n${"b".repeat(64)}`,
    issued_at: additionalAt,
    expires_at: instant(302),
  };
  const additionalPending = {
    ...additionalChallenge,
    authorized_session_record_id: initialSessionId,
    authorized_device_id: deviceId,
    public_key_der: additionalPublicKey,
    scope_refs: additionalScopes,
  };
  result = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_store_additional_enrollment_challenge($1, $2::jsonb, $3::jsonb) AS result",
    [
      "test",
      JSON.stringify(additionalChallenge),
      JSON.stringify(additionalPending),
    ],
  );
  assert.equal(result.status, "STORED");
  const additionalDevice = ownerDevice({
    id: additionalDeviceId,
    ownerKeyId: "travel_key",
    ownerBinding,
    publicKey: additionalPublicKey,
    fingerprint: additionalFingerprint,
    now: instant(3),
  });
  const additionalSession = ownerSession({
    id: additionalSessionId,
    deviceId: additionalDeviceId,
    sessionId: additionalFamilyId,
    generation: 1,
    now: instant(3),
    scopes: additionalScopes,
  });
  const additionalAccessHash = hash("additional-access-verifier");
  result = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_complete_additional_enrollment($1, $2::uuid, $3::uuid, $4::uuid, $5::jsonb, $6::jsonb, $7, $8, $9::timestamptz, $10::timestamptz) AS result",
    [
      "test",
      additionalChallengeId,
      initialSessionId,
      deviceId,
      JSON.stringify(additionalDevice),
      JSON.stringify(additionalSession),
      additionalAccessHash,
      hash("additional-refresh-verifier"),
      instant(86_403),
      instant(3),
    ],
  );
  assert.equal(result.status, "COMPLETED");
  const additionalAccess = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_resolve_access($1, $2, $3::timestamptz) AS result",
    ["test", additionalAccessHash, instant(4)],
  );
  assert.equal(additionalAccess.status, "VALID");
  assert.deepEqual(
    additionalAccess.session_record.scope_refs,
    additionalScopes,
  );

  const rotatedSessionId = uuid7(4);
  const rotatedAccessHash = hash("rotated-access-verifier");
  const rotatedRefreshHash = hash("rotated-refresh-verifier");
  const rotatedAt = instant(3);
  const rotatedSession = ownerSession({
    id: rotatedSessionId,
    deviceId,
    sessionId: familyId,
    generation: 2,
    now: rotatedAt,
    scopes: initialScopes,
  });
  result = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_rotate_refresh($1, $2, $3::jsonb, $4, $5, $6::timestamptz, $7::timestamptz) AS result",
    [
      "test",
      initialRefreshHash,
      JSON.stringify(rotatedSession),
      rotatedAccessHash,
      rotatedRefreshHash,
      instant(86_403),
      rotatedAt,
    ],
  );
  assert.equal(result.status, "ROTATED");
  const oldAccess = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_resolve_access($1, $2, $3::timestamptz) AS result",
    ["test", initialAccessHash, instant(4)],
  );
  assert.equal(oldAccess.status, "IDENTITY_REVOKED");
  const liveRotatedAccess = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_resolve_access($1, $2, $3::timestamptz) AS result",
    ["test", rotatedAccessHash, instant(4)],
  );
  assert.equal(liveRotatedAccess.status, "VALID");

  const commandAt = instant(5);
  const commandExpiry = instant(95);
  const makeCommandChallenge = ({
    id,
    type,
    key,
    scope,
    bodyHash,
    commandId,
  }) => ({
    schema_name: "qc2.owner_api.OwnerSignedCommandChallenge.v1",
    schema_version: "1.0",
    environment_namespace: "test",
    id,
    command_id: commandId,
    command_type: type,
    idempotency_key: key,
    request_body_hash: bodyHash,
    device_ref: {
      target_schema_name: "qc2.governance_owner.OwnerDevice.v1",
      target_id: deviceId,
    },
    session_ref: {
      target_schema_name: "qc2.governance_owner.OwnerSession.v1",
      target_id: rotatedSessionId,
    },
    owner_key_id: "primary_key",
    public_key_fingerprint: fingerprint,
    scope,
    nonce: `n${"c".repeat(64)}`,
    issued_at: commandAt,
    expires_at: commandExpiry,
  });
  const makeBinding = (challenge) => ({
    device_id: deviceId,
    session_record_id: rotatedSessionId,
    session_id: familyId,
    request_body_hash: challenge.request_body_hash,
  });
  const pauseChallenge = makeCommandChallenge({
    id: uuid7(5),
    type: "PAUSE_NEW_ENTRIES",
    key: "pause-before-revocation",
    scope: "PAUSE",
    bodyHash: hash("pause-body"),
    commandId: "cmd-pause-before-revocation",
  });
  const revokeChallenge = makeCommandChallenge({
    id: uuid7(6),
    type: "DEVICE_ACTION",
    key: "revoke-primary",
    scope: "DEVICE_ADMIN",
    bodyHash: hash("revoke-body"),
    commandId: "cmd-revoke-primary",
  });
  for (const challenge of [pauseChallenge, revokeChallenge]) {
    result = await identityQuery(
      client,
      "SELECT qc2_governance_owner.identity_store_command_challenge($1, $2::jsonb, $3::jsonb) AS result",
      [
        "test",
        JSON.stringify(challenge),
        JSON.stringify(makeBinding(challenge)),
      ],
    );
    assert.equal(result.status, "STORED");
  }
  const revokeCommand = {
    schema_name: "qc2.governance_owner.OwnerCommand.v1",
    schema_version: "1.0",
    id: uuid7(7),
    created_at: instant(6),
    owning_authority: "owner_api",
    evidence_class: "SYNTHETIC_FIXTURE",
    environment_namespace: "test",
    source_refs: [],
    command_id: revokeChallenge.command_id,
    command_type: revokeChallenge.command_type,
    idempotency_key: revokeChallenge.idempotency_key,
    request_body_hash: revokeChallenge.request_body_hash,
    issued_at: revokeChallenge.issued_at,
    device_ref: revokeChallenge.device_ref,
    signature: "AQID",
    scope: revokeChallenge.scope,
    content_hash: hash("owner-command"),
  };
  result = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_commit_owner_command($1, $2::uuid, $3::jsonb, $4, $5::uuid, $6::timestamptz) AS result",
    [
      "test",
      revokeChallenge.id,
      JSON.stringify(revokeCommand),
      revokeChallenge.idempotency_key,
      deviceId,
      instant(6),
    ],
  );
  assert.equal(result.status, "COMMITTED");

  const staleCommand = {
    ...revokeCommand,
    id: uuid7(8),
    command_id: pauseChallenge.command_id,
    command_type: pauseChallenge.command_type,
    idempotency_key: pauseChallenge.idempotency_key,
    request_body_hash: pauseChallenge.request_body_hash,
    issued_at: pauseChallenge.issued_at,
    device_ref: pauseChallenge.device_ref,
    scope: pauseChallenge.scope,
    content_hash: hash("stale-owner-command"),
  };
  await expectSqlState(
    identityQuery(
      client,
      "SELECT qc2_governance_owner.identity_commit_owner_command($1, $2::uuid, $3::jsonb, $4, NULL, $5::timestamptz) AS result",
      [
        "test",
        pauseChallenge.id,
        JSON.stringify(staleCommand),
        pauseChallenge.idempotency_key,
        instant(7),
      ],
    ),
    "42501",
  );
  const revokedAccess = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_resolve_access($1, $2, $3::timestamptz) AS result",
    ["test", rotatedAccessHash, instant(8)],
  );
  assert.equal(revokedAccess.status, "IDENTITY_REVOKED");

  const recoveryChallengeId = uuid7(9);
  const recoveryAt = instant(9);
  const recoveryExpiry = instant(609);
  const replacementDeviceId = uuid7(10);
  const replacementSessionId = uuid7(11);
  const replacementPublicKey = "AQIDBQ";
  const replacementFingerprint = hash("replacement-public-key");
  const nextRecoveryVerifierHash = hash("next-recovery-verifier");
  const recoveryChallenge = {
    schema_name: "qc2.owner_api.OwnerRecoveryChallenge.v1",
    schema_version: "1.0",
    environment_namespace: "test",
    id: recoveryChallengeId,
    owner_binding: ownerBinding,
    owner_key_id: "recovery_key",
    public_key_fingerprint: replacementFingerprint,
    signing_algorithm: "ECDSA_P256_SHA256",
    security_level: "UNKNOWN",
    app_version: "identity-test-2",
    nonce: `n${"d".repeat(64)}`,
    issued_at: recoveryAt,
    expires_at: recoveryExpiry,
  };
  const recoveryPending = {
    ...recoveryChallenge,
    recovery_verifier_hash: recoveryMaterialHash,
    public_key_der: replacementPublicKey,
  };
  result = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_store_recovery_challenge($1, $2::jsonb, $3::jsonb) AS result",
    [
      "test",
      JSON.stringify(recoveryChallenge),
      JSON.stringify(recoveryPending),
    ],
  );
  assert.equal(result.status, "STORED");

  const replacementDevice = ownerDevice({
    id: replacementDeviceId,
    ownerKeyId: "recovery_key",
    ownerBinding,
    publicKey: replacementPublicKey,
    fingerprint: replacementFingerprint,
    now: recoveryAt,
    appVersion: "identity-test-2",
  });
  const replacementSession = ownerSession({
    id: replacementSessionId,
    deviceId: replacementDeviceId,
    sessionId: `session-${"2".padStart(32, "0")}`,
    generation: 1,
    now: instant(10),
    scopes: ["OWNER_READ", "DEVICE_ADMIN"],
  });
  const replacementAccessHash = hash("replacement-access-verifier");
  const replacementRefreshHash = hash("replacement-refresh-verifier");
  const recoveryEventId = uuid7(12);
  const recoveryEvent = {
    schema_name: "qc2.governance_owner.RecoveryEvent.v1",
    schema_version: "1.0",
    id: recoveryEventId,
    created_at: instant(10),
    owning_authority: "identity",
    evidence_class: "SYNTHETIC_FIXTURE",
    environment_namespace: "test",
    source_refs: [],
    event_kind: "DEVICE_LOST",
    prior_device_refs: [],
    replacement_device_ref: null,
    effective_at: instant(10),
    promotion_hold: true,
    entry_hold: true,
    reconciliation_required: true,
    evidence_ref: {
      target_schema_name: "qc2.integrity_build.EvidenceEvent.v1",
      target_id: uuid7(13),
      content_hash: hash("pending-evidence"),
    },
  };
  const recoveryParameters = [
    "test",
    recoveryChallengeId,
    recoveryMaterialHash,
    JSON.stringify(replacementDevice),
    JSON.stringify(replacementSession),
    replacementAccessHash,
    replacementRefreshHash,
    instant(86_410),
    nextRecoveryVerifierHash,
    JSON.stringify(recoveryEvent),
    instant(10),
  ];
  const completeRecoverySql =
    "SELECT qc2_governance_owner.identity_complete_recovery($1, $2::uuid, $3, $4::jsonb, $5::jsonb, $6, $7, $8::timestamptz, $9, $10::jsonb, $11::timestamptz) AS result";
  await expectSqlState(
    identityQuery(client, completeRecoverySql, recoveryParameters),
    "23514",
  );
  const unchangedStatus = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_status($1) AS result",
    ["test"],
  );
  assert.equal(unchangedStatus.promotion_hold, false);
  assert.equal(unchangedStatus.entry_hold, false);
  assert.equal(unchangedStatus.reconciliation_required, false);
  assert.equal(unchangedStatus.enrolled_devices.length, 1);
  assert.equal(unchangedStatus.enrolled_devices[0].id, additionalDeviceId);
  const unchangedPause = await client.query(
    "SELECT entry_paused, generation, reason_code FROM qc2_execution.entry_pause_state WHERE singleton_id",
  );
  assert.equal(unchangedPause.rows[0].entry_paused, true);
  assert.equal(unchangedPause.rows[0].reason_code, "initial_fail_closed");

  await withSessionAuthorization(client, "qc2_runtime_evidence", async () => {
    await client.query(
      "SELECT qc2_integrity_build.create_evidence_stream($1, $2, $3, $4)",
      ["identity-test", "test", "identity-test-stream", "SYNTHETIC_FIXTURE"],
    );
  });
  result = await identityQuery(client, completeRecoverySql, recoveryParameters);
  assert.equal(result.status, "RECOVERED");
  assert.equal(result.recovery_event.evidence_ref.content_hash.length, 64);
  assert.equal(result.recovery_event.prior_device_refs.length, 2);
  assert.equal(
    result.recovery_event.replacement_device_ref.target_id,
    replacementDeviceId,
  );

  const recoveredStatus = await identityQuery(
    client,
    "SELECT qc2_governance_owner.identity_status($1) AS result",
    ["test"],
  );
  assert.equal(recoveredStatus.promotion_hold, true);
  assert.equal(recoveredStatus.entry_hold, true);
  assert.equal(recoveredStatus.reconciliation_required, true);
  assert.equal(recoveredStatus.enrolled_devices.length, 1);
  assert.equal(recoveredStatus.enrolled_devices[0].id, replacementDeviceId);
  assert.deepEqual(
    recoveredStatus.enrolled_devices[0].security_level,
    "UNKNOWN",
  );
  const pauseState = await client.query(
    "SELECT entry_paused, generation, reason_code FROM qc2_execution.entry_pause_state WHERE singleton_id",
  );
  assert.equal(pauseState.rows[0].entry_paused, true);
  assert.equal(pauseState.rows[0].reason_code, "owner_identity_recovery");
  const recoveryRows = await client.query(
    "SELECT count(*)::integer AS count FROM qc2_governance_owner.identity_recovery_event",
  );
  assert.equal(recoveryRows.rows[0].count, 1);
}

try {
  await baseClient.connect();
  const identity = await baseClient.query(`
    SELECT current_database() AS database_name,
           pg_catalog.current_setting('server_encoding') AS server_encoding,
           role.rolsuper AS is_superuser,
           pg_catalog.pg_is_in_recovery() AS is_replica
      FROM pg_catalog.pg_roles AS role
     WHERE role.rolname = current_user
  `);
  const baseIdentity = identity.rows[0];
  if (
    !baseIdentity ||
    baseIdentity.database_name !== configuredDatabase ||
    baseIdentity.server_encoding !== "UTF8" ||
    baseIdentity.is_replica ||
    !baseIdentity.is_superuser
  ) {
    throw new Error(
      "Identity acceptance requires a writable UTF8 dedicated test database and test superuser.",
    );
  }
  const existingRoles = await baseClient.query(`
    SELECT rolname
      FROM pg_catalog.pg_roles
     WHERE rolname = 'qc2_migrator' OR rolname LIKE 'qc2_runtime_%'
  `);
  removeQc2RolesCreatedByTest = existingRoles.rowCount === 0;

  await baseClient.query(
    `CREATE DATABASE "${scratchDatabase}" WITH TEMPLATE template0 ENCODING 'UTF8'`,
  );
  scratchCreated = true;
  scratchClient = new Client({ connectionString: scratchUrl.toString() });
  await scratchClient.connect();
  raceClient = new Client({ connectionString: scratchUrl.toString() });
  await raceClient.connect();
  for (const migrationPath of migrations) {
    const migration = (await readFile(migrationPath, "utf8")).replace(
      /^\\set ON_ERROR_STOP on\s*$/gm,
      "",
    );
    await scratchClient.query("BEGIN");
    try {
      await scratchClient.query(migration);
      await scratchClient.query("COMMIT");
    } catch (error) {
      await scratchClient.query("ROLLBACK");
      throw new Error(
        `PostgreSQL migration failed in ${path.relative(repositoryRoot, migrationPath)}: ${error.message}`,
        { cause: error },
      );
    }
  }
  await runIdentityAcceptance(scratchClient, raceClient);
  console.log(
    "QC2-053 PostgreSQL identity integration passed: least-privilege runtime access, single-owner bootstrap, key-bound sessions, refresh rotation, commit-time revocation, and atomic recovery holds/evidence.",
  );
} finally {
  if (raceClient) await raceClient.end();
  if (scratchClient) await scratchClient.end();
  if (scratchCreated) {
    await baseClient.query(
      `SELECT pg_catalog.pg_terminate_backend(pid)
         FROM pg_catalog.pg_stat_activity
        WHERE datname = $1 AND pid <> pg_catalog.pg_backend_pid()`,
      [scratchDatabase],
    );
    await baseClient.query(`DROP DATABASE IF EXISTS "${scratchDatabase}"`);
  }
  if (removeQc2RolesCreatedByTest) {
    const createdRoles = await baseClient.query(`
      SELECT rolname
        FROM pg_catalog.pg_roles
       WHERE rolname = 'qc2_migrator' OR rolname LIKE 'qc2_runtime_%'
       ORDER BY CASE WHEN rolname = 'qc2_migrator' THEN 1 ELSE 0 END, rolname
    `);
    for (const row of createdRoles.rows) {
      await baseClient.query(`DROP ROLE IF EXISTS "${row.rolname}"`);
    }
  }
  await baseClient.end();
}
