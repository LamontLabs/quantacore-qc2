import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { randomBytes } from "node:crypto";
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
  throw new Error("Set QC2_ENV=test before running owner-read acceptance.");
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
    "Owner-read acceptance requires a dedicated qc2_test_* database.",
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
    "Owner-read acceptance cannot reuse a configured runtime database.",
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
];
const scratchDatabase =
  `qc2_test_owner_read_${process.pid}_${randomBytes(4).toString("hex")}`;
const scratchUrl = new URL(connectionString);
scratchUrl.pathname = `/${scratchDatabase}`;
const baseClient = new Client({ connectionString });
const scratchClient = new Client({ connectionString: scratchUrl.toString() });
let scratchCreated = false;

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

async function makeItem(sequence) {
  const padded = String(sequence).padStart(12, "0");
  const targetId = `10000000-0000-7000-8000-${padded}`;
  const sourceRef = {
    target_schema_name: "qc2.models_prediction.Prediction.v1",
    target_id: targetId,
    content_hash: "a".repeat(64),
  };
  const instrumentRef = {
    target_schema_name: "qc2.identity_market.Instrument.v1",
    target_id: targetId,
    content_hash: "b".repeat(64),
  };
  const item = {
    item_id: `prediction-${String(sequence).padStart(3, "0")}`,
    sort_key: "same-sort-key",
    source_sequence: sequence,
    source_ref: sourceRef,
    payload: {
      session_id: "2026-10-09",
      rank: sequence,
      instrument_ref: instrumentRef,
      symbol: `SYM${sequence}`,
      prediction_state: "SCORED",
      score: "0.812",
      uncertainty: "0.1",
      excluded_reason: null,
      evidence_refs: [],
    },
  };
  const receiptBody = {
    schema_name: "qc2.owner_api.OwnerReadSourceReceipt.v1",
    schema_version: "1.0",
    environment_namespace: "test",
    view_name: "predictions",
    source_sequence: item.source_sequence,
    item_id: item.item_id,
    sort_key: item.sort_key,
    source_ref: item.source_ref,
    payload: item.payload,
  };
  return {
    ...item,
    receipt_hash: await hashJson(
      "qc2.owner_api.read_source_receipt.v1",
      receiptBody,
    ),
  };
}

try {
  await baseClient.connect();
  await baseClient.query(`CREATE DATABASE "${scratchDatabase}"`);
  scratchCreated = true;
  await scratchClient.connect();

  for (const migrationName of migrationNames) {
    const migration = await readFile(
      path.join(repositoryRoot, "migrations", migrationName),
      "utf8",
    );
    await scratchClient.query(migration);
  }

  const items = [await makeItem(1), await makeItem(2)];
  const sourceRefs = items.map((item) => item.source_ref);
  const builtAt = "2026-10-09T16:00:00Z";
  const freshnessDeadline = "2026-10-09T16:05:00Z";
  const snapshotBody = {
    environment_namespace: "test",
    view_name: "predictions",
    projection_sequence: 1,
    source_sequence: 2,
    source_highwater_sequence: 2,
    built_at: builtAt,
    freshness_deadline: freshnessDeadline,
    source_refs: sourceRefs,
    items,
  };
  const snapshotHash = await hashJson(
    "qc2.owner_api.read_projection_snapshot.v1",
    snapshotBody,
  );

  await withSessionAuthorization("qc2_runtime_owner_api", async () => {
    await expectSqlState(
      scratchClient.query(
        "SELECT * FROM qc2_owner_api.owner_projection_item LIMIT 1",
      ),
      "42501",
    );
    await expectSqlState(
      scratchClient.query(
        "SELECT qc2_owner_api.owner_projection_source_allowed($1, $2)",
        ["predictions", "qc2.models_prediction.Prediction.v1"],
      ),
      "42501",
    );

    const empty = await scratchClient.query(
      `SELECT qc2_owner_api.owner_projection_page(
        'test', 'predictions', 1, NULL, NULL, NULL
      ) AS result`,
    );
    assert.equal(empty.rows[0].result.status, "UNAVAILABLE");

    const rebuilt = await scratchClient.query(
      `SELECT qc2_owner_api.owner_projection_rebuild(
        $1::text, $2::text, $3::bigint, $4::bigint, $5::bigint,
        $6::timestamptz, $7::timestamptz, $8::jsonb, $9::jsonb, $10::text
      ) AS result`,
      [
        "test",
        "predictions",
        1,
        2,
        2,
        builtAt,
        freshnessDeadline,
        JSON.stringify(sourceRefs),
        JSON.stringify(items),
        snapshotHash,
      ],
    );
    assert.equal(rebuilt.rows[0].result.status, "BUILT");

    const firstPage = await scratchClient.query(
      `SELECT qc2_owner_api.owner_projection_page(
        'test', 'predictions', 1, NULL, NULL, NULL
      ) AS result`,
    );
    assert.equal(firstPage.rows[0].result.status, "OK");
    assert.equal(firstPage.rows[0].result.has_more, true);
    assert.equal(firstPage.rows[0].result.page.source_refs.length, 1);
    assert.equal(
      firstPage.rows[0].result.page.items[0].item_id,
      "prediction-001",
    );

    const secondPage = await scratchClient.query(
      `SELECT qc2_owner_api.owner_projection_page(
        'test', 'predictions', 1, $1::text, $2::text, $3::bigint
      ) AS result`,
      ["same-sort-key", "prediction-001", 1],
    );
    assert.equal(secondPage.rows[0].result.has_more, false);
    assert.equal(secondPage.rows[0].result.page.source_refs.length, 1);
    assert.equal(
      secondPage.rows[0].result.page.items[0].item_id,
      "prediction-002",
    );

    await scratchClient.query(
      `SELECT qc2_owner_api.owner_projection_advance_source(
        'test', 'predictions', 3
      )`,
    );
    const stalePage = await scratchClient.query(
      `SELECT qc2_owner_api.owner_projection_page(
        'test', 'predictions', 1, NULL, NULL, NULL
      ) AS result`,
    );
    assert.equal(stalePage.rows[0].result.page.lag, 1);
    assert.equal(stalePage.rows[0].result.page.stale, true);

    const diagnostics = await scratchClient.query(
      "SELECT qc2_owner_api.owner_projection_diagnostics('test') AS result",
    );
    assert.equal(diagnostics.rows[0].result.status, "OK");
    assert.equal(diagnostics.rows[0].result.diagnostics.views.length, 9);
    assert.equal(
      diagnostics.rows[0].result.diagnostics.views.find(
        (view) => view.view_name === "predictions",
      ).lag,
      1,
    );
  });

  console.log("QC2-054 PostgreSQL acceptance passed.");
} finally {
  await scratchClient.end().catch(() => {});
  if (scratchCreated) {
    await baseClient
      .query(`DROP DATABASE IF EXISTS "${scratchDatabase}" WITH (FORCE)`)
      .catch(() => {});
  }
  await baseClient.end().catch(() => {});
}
