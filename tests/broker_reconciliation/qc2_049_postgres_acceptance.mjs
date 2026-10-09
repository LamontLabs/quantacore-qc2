import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(
  new URL("../../lib/db/package.json", import.meta.url),
);
const { Client } = require("pg");

async function executionClient(connectionString) {
  const client = new Client({ connectionString });
  await client.connect();
  await client.query("SET SESSION AUTHORIZATION qc2_runtime_execution");
  return client;
}

async function hashJson(client, domain, value) {
  const result = await client.query(
    "SELECT qc2_integrity_build.hash_json($1, $2::jsonb) AS value",
    [domain, JSON.stringify(value)],
  );
  return result.rows[0].value;
}

async function makeInput(
  adminClient,
  episodeRef,
  expectedFingerprint,
  options,
) {
  const observedFingerprint =
    options.observedFingerprint ?? expectedFingerprint;
  const localSnapshotHash = await hashJson(
    adminClient,
    "qc2.execution.broker-reconciliation.local-inventory.v1",
    { fixture: "local", revision: options.revision },
  );
  const brokerSnapshotHash = await hashJson(
    adminClient,
    "qc2.execution.broker-reconciliation.broker-inventory.v1",
    { fixture: "broker", revision: options.revision },
  );
  const checkpointMaterial = {
    episode_ref: episodeRef,
    expected_account_fingerprint: expectedFingerprint,
    observed_account_fingerprint: observedFingerprint,
    local_snapshot_hash: localSnapshotHash,
    broker_snapshot_hash: brokerSnapshotHash,
  };
  const checkpointHash = await hashJson(
    adminClient,
    "qc2.execution.broker-reconciliation.checkpoint.v1",
    checkpointMaterial,
  );
  return {
    episode_ref: episodeRef,
    expected_account_fingerprint: expectedFingerprint,
    observed_account_fingerprint: observedFingerprint,
    local_snapshot_hash: localSnapshotHash,
    broker_snapshot_hash: brokerSnapshotHash,
    checkpoint_hash: checkpointHash,
    status: options.status,
    source_refs: [],
    broker_order_refs: [],
    position_refs: [],
    discrepancies: options.findings.map((finding) => finding.finding_key),
    findings: options.findings,
    checked_sources: ["fixture_order_inventory", "fixture_account_summary"],
    event_payload: {
      episode_ref: episodeRef,
      scenario: options.scenario,
      revision: options.revision,
    },
  };
}

async function record(execution, input) {
  const result = await execution.query(
    "SELECT qc2_control.record_broker_reconciliation($1::jsonb) AS result",
    [JSON.stringify(input)],
  );
  return result.rows[0].result;
}

export async function runQc2049BrokerReconciliationAcceptance({
  connectionString,
  adminClient,
  fixtures,
}) {
  const episode = structuredClone(
    fixtures.find((row) => row.contract === "ExecutionEpisode")?.payload,
  );
  assert.ok(episode?.id, "ExecutionEpisode fixture is required");
  assert.match(episode.content_hash, /^[0-9a-f]{64}$/);
  const episodeRef = {
    target_schema_name: "qc2.execution.ExecutionEpisode.v1",
    target_id: episode.id,
    content_hash: episode.content_hash,
  };
  const execution = await executionClient(connectionString);
  try {
    const episodeState = await execution.query(
      `SELECT episode.paper_account_fingerprint,
              episode.content_hash,
              (SELECT count(*)::integer
                 FROM qc2_execution.position_state_position_projection AS position
                WHERE position.episode_id = episode.episode_id) AS position_count,
              (SELECT count(*)::integer
                 FROM qc2_execution.position_state_cash_projection AS cash
                WHERE cash.episode_id = episode.episode_id) AS cash_count
         FROM qc2_execution.execution_episode_state AS episode
        WHERE episode.episode_id = $1::uuid`,
      [episode.id],
    );
    assert.equal(episodeState.rowCount, 1);
    assert.equal(episodeState.rows[0].content_hash, episode.content_hash);
    assert.ok(episodeState.rows[0].position_count > 0);
    assert.ok(episodeState.rows[0].cash_count > 0);
    const expectedFingerprint = episodeState.rows[0].paper_account_fingerprint;

    const beforeCounts = await adminClient.query(
      `SELECT
         (SELECT count(*)::integer
            FROM qc2_execution.position_state_broker_order) AS orders,
         (SELECT count(*)::integer
            FROM qc2_execution.paper_execution_attempt) AS attempts`,
    );
    const initial = await makeInput(
      adminClient,
      episodeRef,
      expectedFingerprint,
      {
        revision: 1,
        scenario: "unmapped-manual-order",
        status: "HOLD",
        findings: [
          {
            finding_key: "manual_order:fixture-order-1",
            reason_code: "UNMAPPED_REMOTE_ORDER",
            detail: "Fixture order has no matching local intent.",
          },
        ],
      },
    );
    const first = await record(execution, initial);
    assert.equal(first.already_recorded, false);
    assert.equal(first.report_contract.status, "HOLD");
    assert.deepEqual(first.active_finding_keys, [
      "manual_order:fixture-order-1",
    ]);
    assert.equal(
      first.report_contract.schema_name,
      "qc2.execution.ReconciliationReport.v1",
    );
    assert.equal(
      first.report_contract.evidence_ref.target_schema_name,
      "qc2.integrity_build.EvidenceEvent.v1",
    );

    const checkpointCountAfterFirst = await adminClient.query(
      `SELECT
         (SELECT count(*)::integer
            FROM qc2_execution.broker_reconciliation_checkpoint
           WHERE episode_id = $1::uuid) AS checkpoints,
         (SELECT count(*)::integer
            FROM qc2_integrity_build.evidence_event
           WHERE event_contract->>'event_type'
             = 'broker_reconciliation_checkpoint') AS checkpoint_events`,
      [episode.id],
    );
    const repeated = await record(execution, initial);
    assert.equal(repeated.already_recorded, true);
    assert.equal(repeated.checkpoint_id, first.checkpoint_id);
    assert.equal(repeated.generation, first.generation);
    const checkpointCountAfterRepeat = await adminClient.query(
      `SELECT
         (SELECT count(*)::integer
            FROM qc2_execution.broker_reconciliation_checkpoint
           WHERE episode_id = $1::uuid) AS checkpoints,
         (SELECT count(*)::integer
            FROM qc2_integrity_build.evidence_event
           WHERE event_contract->>'event_type'
             = 'broker_reconciliation_checkpoint') AS checkpoint_events`,
      [episode.id],
    );
    assert.deepEqual(
      checkpointCountAfterRepeat.rows[0],
      checkpointCountAfterFirst.rows[0],
    );

    const didResolve = await execution.query(
      `SELECT qc2_control.resolve_broker_reconciliation_finding(
        $1::uuid, $2::text, $3::text, $4::text, $5::jsonb
      ) AS resolved`,
      [
        episode.id,
        "manual_order:fixture-order-1",
        "reviewed_fixture",
        "Owner reviewed the fixture evidence and classified the order.",
        JSON.stringify(first.report_contract.evidence_ref),
      ],
    );
    assert.equal(didResolve.rows[0].resolved, true);

    const clean = await makeInput(
      adminClient,
      episodeRef,
      expectedFingerprint,
      {
        revision: 2,
        scenario: "clean-after-explicit-resolution",
        status: "RECONCILED",
        findings: [],
      },
    );
    const cleanResult = await record(execution, clean);
    assert.equal(cleanResult.already_recorded, false);
    assert.equal(cleanResult.report_contract.status, "RECONCILED");
    assert.deepEqual(cleanResult.active_finding_keys, []);
    const holdState = await adminClient.query(
      `SELECT reconciliation_status, hold_reasons
         FROM qc2_execution.position_state_projection_control
        WHERE episode_id = $1::uuid`,
      [episode.id],
    );
    assert.equal(holdState.rows[0].reconciliation_status, "RECONCILED");
    assert.deepEqual(holdState.rows[0].hold_reasons, []);

    const positionCountBeforeReset = episodeState.rows[0].position_count;
    const reset = await makeInput(
      adminClient,
      episodeRef,
      expectedFingerprint,
      {
        revision: 3,
        scenario: "account-reset-with-empty-remote-inventory",
        status: "HOLD",
        observedFingerprint: "e".repeat(64),
        findings: [],
      },
    );
    const resetResult = await record(execution, reset);
    assert.equal(resetResult.report_contract.status, "HOLD");
    assert.deepEqual(resetResult.active_finding_keys, ["account_reset"]);
    assert.deepEqual(resetResult.report_contract.discrepancies, [
      "account_reset",
    ]);
    const projectedPositions = await execution.query(
      `SELECT count(*)::integer AS count
         FROM qc2_execution.position_state_position_projection
        WHERE episode_id = $1::uuid`,
      [episode.id],
    );
    assert.equal(projectedPositions.rows[0].count, positionCountBeforeReset);

    const afterCounts = await adminClient.query(
      `SELECT
         (SELECT count(*)::integer
            FROM qc2_execution.position_state_broker_order) AS orders,
         (SELECT count(*)::integer
            FROM qc2_execution.paper_execution_attempt) AS attempts`,
    );
    assert.deepEqual(afterCounts.rows[0], beforeCounts.rows[0]);
  } finally {
    await execution.end();
  }
}
