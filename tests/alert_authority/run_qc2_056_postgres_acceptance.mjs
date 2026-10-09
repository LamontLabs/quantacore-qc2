import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
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
  throw new Error("Set QC2_ENV=test before running alert acceptance.");
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
  throw new Error("Alert acceptance requires a dedicated qc2_test_* database.");
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
    "Alert acceptance cannot reuse a configured runtime database.",
  );
}

const migrationNames = Array.from(
  { length: 16 },
  (_, index) =>
    `${String(index + 1).padStart(4, "0")}_${
      [
        "postgresql_authority_foundation",
        "evidence_authority",
        "prediction_authority",
        "validation_authority",
        "apexlab_experiment_ledger",
        "model_registry",
        "atomic_champion_transition",
        "paper_order_intents",
        "execution_authority",
        "durable_position_state",
        "broker_reconciliation",
        "execution_readiness",
        "owner_identity_device_enrollment",
        "owner_read_models",
        "owner_api_command_receipts",
        "alert_authority",
      ][index]
    }.sql`,
);
const scratchDatabase = `qc2_test_alerts_${process.pid}_${randomBytes(4).toString("hex")}`;
const scratchUrl = new URL(connectionString);
scratchUrl.pathname = `/${scratchDatabase}`;
const baseClient = new Client({ connectionString });
const scratchClient = new Client({ connectionString: scratchUrl.toString() });
let scratchCreated = false;

async function withAuthority(role, callback) {
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

async function raise(ruleKey, dedupeKey, severity) {
  return withAuthority("qc2_runtime_alert", async () => {
    const { rows } = await scratchClient.query(
      `SELECT qc2_alerts.raise_alert(
        'test', $1::text, $2::text, $3::text, $4::jsonb, $5::jsonb
      ) AS result`,
      [
        ruleKey,
        dedupeKey,
        severity,
        JSON.stringify(sourceRefs),
        JSON.stringify(evidenceRefs),
      ],
    );
    return rows[0].result;
  });
}

let sourceRefs = [];
let evidenceRefs = [];
const pauseState = async () =>
  withAuthority("qc2_migrator", async () => {
    const { rows } = await scratchClient.query(
      `SELECT entry_paused, generation
       FROM qc2_execution.entry_pause_state WHERE singleton_id`,
    );
    return rows[0];
  });
const alertLifecycle = async (alertId) =>
  withAuthority("qc2_runtime_alert", async () => {
    const { rows } = await scratchClient.query(
      `SELECT alert, lifecycle_state, current_severity,
              acknowledged_at, resolved_at
       FROM qc2_alerts.list_alerts('test')
       WHERE alert->>'id' = $1`,
      [alertId],
    );
    return rows[0];
  });

try {
  await baseClient.connect();
  const identity = await baseClient.query(`
    SELECT current_database() AS database_name,
           pg_catalog.current_setting('server_encoding') AS server_encoding,
           roles.rolsuper AS is_superuser,
           pg_catalog.pg_is_in_recovery() AS is_replica
    FROM pg_catalog.pg_roles AS roles
    WHERE roles.rolname = current_user
  `);
  const databaseIdentity = identity.rows[0];
  if (
    !databaseIdentity ||
    databaseIdentity.database_name !== configuredDatabase ||
    databaseIdentity.server_encoding !== "UTF8" ||
    databaseIdentity.is_replica ||
    !databaseIdentity.is_superuser
  ) {
    throw new Error(
      "Alert acceptance requires a writable, UTF8, dedicated test database and superuser.",
    );
  }

  await baseClient.query(
    `CREATE DATABASE "${scratchDatabase}" WITH TEMPLATE template0 ENCODING 'UTF8'`,
  );
  scratchCreated = true;
  await scratchClient.connect();

  for (const migrationName of migrationNames) {
    const migration = await readFile(
      path.join(repositoryRoot, "migrations", migrationName),
      "utf8",
    );
    await scratchClient.query(migration);
  }

  const genesisEventId = await withAuthority(
    "qc2_runtime_evidence",
    async () => {
      const { rows } = await scratchClient.query(
        `SELECT qc2_integrity_build.create_evidence_stream(
          'qc2_test_alerts', 'test', 'qc2_alert_acceptance',
          'SYNTHETIC_FIXTURE'
        ) AS event_id`,
      );
      return rows[0].event_id;
    },
  );
  const genesisEvent = await withAuthority("qc2_runtime_evidence", async () => {
    const { rows } = await scratchClient.query(
      `SELECT content_hash FROM qc2_integrity_build.evidence_event
         WHERE id = $1::uuid`,
      [genesisEventId],
    );
    return rows[0];
  });
  assert.match(genesisEvent.content_hash, /^[0-9a-f]{64}$/);
  sourceRefs = [
    {
      target_schema_name: "qc2.integrity_build.EvidenceEvent.v1",
      target_id: genesisEventId,
      content_hash: genesisEvent.content_hash,
    },
  ];
  evidenceRefs = structuredClone(sourceRefs);

  const severities = await withAuthority("qc2_runtime_alert", async () => {
    const { rows } = await scratchClient.query(
      `SELECT DISTINCT base_severity
       FROM qc2_alerts.alert_rule ORDER BY base_severity`,
    );
    return rows.map((row) => row.base_severity);
  });
  assert.deepEqual(severities, [
    "CRITICAL",
    "EMERGENCY",
    "INFO",
    "NOTICE",
    "WARNING",
  ]);

  const firstReadinessAlert = await raise(
    "readiness_failed",
    "readiness-service",
    "CRITICAL",
  );
  assert.equal(firstReadinessAlert.status, "CREATED");
  const firstAlertId = firstReadinessAlert.alert_id;
  const firstDeliveryId = firstReadinessAlert.delivery_id;

  const notification = await withAuthority(
    "qc2_runtime_durable_job_service",
    async () => {
      const { rows } = await scratchClient.query(
        `SELECT qc2_alerts.get_notification_payload($1::uuid) AS payload`,
        [firstDeliveryId],
      );
      return rows[0].payload;
    },
  );
  assert.equal(notification.payload_type, "alert_notification");
  assert.equal(notification.alert_id, firstAlertId);
  assert.deepEqual(notification.source_refs, sourceRefs);
  const forbiddenPayloadKey = (value) => {
    if (Array.isArray(value)) return value.some(forbiddenPayloadKey);
    if (!value || typeof value !== "object") return false;
    return Object.entries(value).some(
      ([key, child]) =>
        /secret|credential|signature|token|password|approval/i.test(key) ||
        forbiddenPayloadKey(child),
    );
  };
  assert.equal(forbiddenPayloadKey(notification), false);

  const workerId = "10000000-0000-7000-8000-000000000099";
  const lease = await withAuthority(
    "qc2_runtime_durable_job_service",
    async () => {
      const { rows } = await scratchClient.query(
        `SELECT * FROM qc2_control.claim_outbox($1::uuid, 60)`,
        [workerId],
      );
      return rows[0];
    },
  );
  assert.equal(lease.message_id, firstDeliveryId);
  const failedDelivery = await withAuthority(
    "qc2_runtime_durable_job_service",
    async () => {
      const { rows } = await scratchClient.query(
        `SELECT qc2_control.complete_outbox(
          $1::uuid, $2::uuid, $3::bigint, false
        ) AS completed`,
        [lease.message_id, workerId, lease.fencing_generation],
      );
      return rows[0].completed;
    },
  );
  assert.equal(failedDelivery, true);

  await new Promise((resolve) => setTimeout(resolve, 1_100));
  const staleDelivery = await withAuthority("qc2_runtime_alert", async () => {
    const { rows } = await scratchClient.query(
      `SELECT * FROM qc2_alerts.delivery_status('test')
         WHERE outbox_message_id = $1::uuid`,
      [firstDeliveryId],
    );
    return rows[0];
  });
  assert.equal(staleDelivery.outbox_status, "UNKNOWN");
  assert.equal(staleDelivery.is_stale, true);
  assert.equal((await pauseState()).entry_paused, true);
  const afterDeliveryFailure = await alertLifecycle(firstAlertId);
  assert.equal(afterDeliveryFailure.lifecycle_state, "OPEN");
  assert.equal(afterDeliveryFailure.current_severity, "CRITICAL");
  assert.equal(afterDeliveryFailure.alert.readiness_effect, true);
  assert.equal(afterDeliveryFailure.acknowledged_at, null);
  assert.equal(afterDeliveryFailure.resolved_at, null);

  const acknowledged = await withAuthority("qc2_runtime_alert", async () => {
    const { rows } = await scratchClient.query(
      `SELECT qc2_alerts.acknowledge_alert($1::uuid) AS result`,
      [firstAlertId],
    );
    return rows[0].result;
  });
  assert.equal(acknowledged.status, "ACKNOWLEDGED");
  assert.ok(acknowledged.acknowledged_at);
  assert.equal(acknowledged.resolved_at, null);
  assert.deepEqual(await pauseState(), { entry_paused: true, generation: "1" });
  const afterAcknowledgment = await alertLifecycle(firstAlertId);
  assert.equal(afterAcknowledgment.lifecycle_state, "OPEN");
  assert.ok(afterAcknowledgment.acknowledged_at);
  assert.equal(afterAcknowledgment.resolved_at, null);
  assert.equal(afterAcknowledgment.alert.readiness_effect, true);

  const duplicateAck = await withAuthority("qc2_runtime_alert", async () => {
    const { rows } = await scratchClient.query(
      `SELECT qc2_alerts.acknowledge_alert($1::uuid) AS result`,
      [firstAlertId],
    );
    return rows[0].result;
  });
  assert.equal(duplicateAck.status, "ALREADY_ACKNOWLEDGED");

  await expectSqlState(
    withAuthority("qc2_runtime_alert", () =>
      scratchClient.query(
        `SELECT qc2_alerts.resolve_alert_auto(
          $1::uuid, 'source_condition_cleared', $2::jsonb, $3::jsonb
        )`,
        [
          firstAlertId,
          JSON.stringify(sourceRefs),
          JSON.stringify(evidenceRefs),
        ],
      ),
    ),
    "42501",
  );
  const resolved = await withAuthority("qc2_runtime_alert", async () => {
    const { rows } = await scratchClient.query(
      `SELECT qc2_alerts.resolve_alert_auto(
        $1::uuid, 'readiness_restored', $2::jsonb, $3::jsonb
      ) AS result`,
      [firstAlertId, JSON.stringify(sourceRefs), JSON.stringify(evidenceRefs)],
    );
    return rows[0].result;
  });
  assert.equal(resolved.status, "RESOLVED");
  assert.equal(resolved.resolution_kind, "AUTO");

  const recurrence = await raise(
    "readiness_failed",
    "readiness-service",
    "CRITICAL",
  );
  assert.equal(recurrence.status, "CREATED");
  assert.notEqual(recurrence.alert_id, firstAlertId);
  const duplicateTrigger = await raise(
    "readiness_failed",
    "readiness-service",
    "CRITICAL",
  );
  assert.equal(duplicateTrigger.status, "DEDUPLICATED");
  assert.equal(duplicateTrigger.alert_id, recurrence.alert_id);
  const escalated = await raise(
    "readiness_failed",
    "readiness-service",
    "EMERGENCY",
  );
  assert.equal(escalated.status, "ESCALATED");
  assert.equal(escalated.alert_id, recurrence.alert_id);
  assert.equal(escalated.severity, "EMERGENCY");
  const noDowngrade = await raise(
    "readiness_failed",
    "readiness-service",
    "CRITICAL",
  );
  assert.equal(noDowngrade.status, "DEDUPLICATED");
  assert.equal(noDowngrade.severity, "EMERGENCY");

  const emergencyAlert = await raise(
    "safety_emergency",
    "safety-stop",
    "EMERGENCY",
  );
  await expectSqlState(
    withAuthority("qc2_runtime_alert", () =>
      scratchClient.query(
        `SELECT qc2_alerts.resolve_alert_auto(
          $1::uuid, 'manual_resolution_required', $2::jsonb, $3::jsonb
        )`,
        [
          emergencyAlert.alert_id,
          JSON.stringify(sourceRefs),
          JSON.stringify(evidenceRefs),
        ],
      ),
    ),
    "42501",
  );
  const manualResolution = await withAuthority(
    "qc2_runtime_alert",
    async () => {
      const { rows } = await scratchClient.query(
        `SELECT qc2_alerts.resolve_alert_manual(
          $1::uuid, 'operator_confirmed', $2::jsonb, $3::jsonb
        ) AS result`,
        [
          emergencyAlert.alert_id,
          JSON.stringify(sourceRefs),
          JSON.stringify(evidenceRefs),
        ],
      );
      return rows[0].result;
    },
  );
  assert.equal(manualResolution.status, "RESOLVED");
  assert.equal(manualResolution.resolution_kind, "MANUAL");

  const listedAlerts = await withAuthority("qc2_runtime_alert", async () => {
    const { rows } = await scratchClient.query(
      `SELECT alert, lifecycle_state, current_severity,
                acknowledged_at, resolved_at, trigger_count
         FROM qc2_alerts.list_alerts('test')`,
    );
    return rows;
  });
  const listedFirst = listedAlerts.find((row) => row.alert.id === firstAlertId);
  const listedRecurrence = listedAlerts.find(
    (row) => row.alert.id === recurrence.alert_id,
  );
  assert.equal(listedFirst.lifecycle_state, "RESOLVED");
  assert.equal(listedFirst.current_severity, "CRITICAL");
  assert.equal(listedFirst.alert.acknowledged_at, null);
  assert.equal(listedFirst.alert.resolved_at, null);
  assert.ok(listedFirst.acknowledged_at);
  assert.ok(listedFirst.resolved_at);
  assert.equal(listedRecurrence.lifecycle_state, "OPEN");
  assert.equal(listedRecurrence.alert.severity, "CRITICAL");
  assert.equal(listedRecurrence.current_severity, "EMERGENCY");
  assert.equal(listedRecurrence.acknowledged_at, null);
  assert.equal(listedRecurrence.resolved_at, null);
  assert.equal(listedRecurrence.trigger_count, "4");
  assert.deepEqual(listedFirst.alert.source_refs, sourceRefs);

  await expectSqlState(
    withAuthority("qc2_runtime_identity", () =>
      scratchClient.query(
        `SELECT qc2_alerts.raise_alert(
          'test', 'operational_info', 'unauthorized', 'INFO',
          $1::jsonb, $2::jsonb
        )`,
        [JSON.stringify(sourceRefs), JSON.stringify(evidenceRefs)],
      ),
    ),
    "42501",
  );
  await expectSqlState(
    withAuthority("qc2_runtime_alert", () =>
      scratchClient.query(
        `UPDATE qc2_alerts.alert_instance
         SET state = 'RESOLVED' WHERE id = $1::uuid`,
        [recurrence.alert_id],
      ),
    ),
    "42501",
  );
  await expectSqlState(
    withAuthority("qc2_runtime_alert", () =>
      scratchClient.query(
        `SELECT qc2_alerts.raise_alert(
          'test', 'unknown_rule', 'bad-rule', 'INFO',
          $1::jsonb, $2::jsonb
        )`,
        [JSON.stringify(sourceRefs), JSON.stringify(evidenceRefs)],
      ),
    ),
    "42501",
  );

  console.log("QC2-056 PostgreSQL alert acceptance passed.");
} finally {
  await scratchClient.end().catch(() => {});
  if (scratchCreated) {
    await baseClient
      .query(`DROP DATABASE IF EXISTS "${scratchDatabase}" WITH (FORCE)`)
      .catch(() => {});
  }
  await baseClient.end().catch(() => {});
}
