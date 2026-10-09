import { randomBytes } from "node:crypto";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runQc2045PaperOrderAcceptance } from "../../lib/db/test/qc2-045-paper-order-acceptance.mjs";
import { runQc2046ExecutionAuthorityAcceptance } from "../execution/qc2_046_postgres_acceptance.mjs";
import { runQc2048DurablePositionStateAcceptance } from "../execution_position_state/qc2_048_postgres_acceptance.mjs";
import { runQc2049BrokerReconciliationAcceptance } from "./qc2_049_postgres_acceptance.mjs";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(testDirectory, "../..");
const require = createRequire(
  new URL("../../lib/db/package.json", import.meta.url),
);
const { Client } = require("pg");
const migrationPaths = [
  "migrations/0001_postgresql_authority_foundation.sql",
  "migrations/0002_evidence_authority.sql",
  "migrations/0003_prediction_authority.sql",
  "migrations/0004_validation_authority.sql",
  "migrations/0005_apexlab_experiment_ledger.sql",
  "migrations/0006_model_registry.sql",
  "migrations/0007_atomic_champion_transition.sql",
  "migrations/0008_paper_order_intents.sql",
  "migrations/0009_execution_authority.sql",
  "migrations/0010_durable_position_state.sql",
  "migrations/0011_broker_reconciliation.sql",
].map((relativePath) => path.join(repositoryRoot, relativePath));
const rollbackScriptPaths = [
  "migrations/0001_postgresql_authority_foundation.sql",
  "tests/database/qc2_005_postgres_acceptance.sql",
  "migrations/0002_evidence_authority.sql",
  "tests/database/qc2_006_postgres_acceptance.sql",
  "migrations/0003_prediction_authority.sql",
  "tests/database/qc2_025_postgres_acceptance.sql",
  "migrations/0004_validation_authority.sql",
  "tests/database/qc2_026_postgres_acceptance.sql",
  "migrations/0005_apexlab_experiment_ledger.sql",
  "tests/database/qc2_034_postgres_acceptance.sql",
  "migrations/0006_model_registry.sql",
  "tests/database/qc2_037_postgres_acceptance.sql",
  "migrations/0007_atomic_champion_transition.sql",
  "tests/database/qc2_043_postgres_acceptance.sql",
  "migrations/0008_paper_order_intents.sql",
  "migrations/0009_execution_authority.sql",
  "migrations/0010_durable_position_state.sql",
].map((relativePath) => path.join(repositoryRoot, relativePath));
const connectionString = process.env.QC2_POSTGRES_TEST_URL;
const expectedDatabase = process.env.QC2_EXPECTED_DATABASE_TEST;

if (process.env.QC2_ENV !== "test") {
  throw new Error(
    "Set QC2_ENV=test before running PostgreSQL acceptance checks.",
  );
}
if (!connectionString) {
  throw new Error("QC2_POSTGRES_TEST_URL is required; no URL value is logged.");
}
if (!expectedDatabase) {
  throw new Error(
    "QC2_EXPECTED_DATABASE_TEST is required; no database URL is logged.",
  );
}

const parsedUrl = new URL(connectionString);
const configuredDatabase = decodeURIComponent(
  parsedUrl.pathname.replace(/^\//, ""),
);
if (
  !/^qc2_test_[a-z0-9_]+$/.test(configuredDatabase) ||
  expectedDatabase !== configuredDatabase
) {
  throw new Error(
    "PostgreSQL acceptance requires a dedicated qc2_test_* database.",
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
    "The isolated PostgreSQL test database must not reuse a configured runtime identity.",
  );
}

const scratchDatabase = `qc2_test_broker_reconciliation_${process.pid}_${randomBytes(4).toString("hex")}`;
const scratchUrl = new URL(connectionString);
scratchUrl.pathname = `/${scratchDatabase}`;
const baseClient = new Client({ connectionString });
let scratchClient;
let scratchCreated = false;
let removeQc2RolesCreatedByTest = false;

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
    databaseIdentity.database_name !== configuredDatabase
  ) {
    throw new Error(
      "Connected database did not match the test URL database name.",
    );
  }
  if (databaseIdentity.server_encoding !== "UTF8") {
    throw new Error(
      "PostgreSQL acceptance requires a UTF8-encoded test database.",
    );
  }
  if (databaseIdentity.is_replica || !databaseIdentity.is_superuser) {
    throw new Error(
      "PostgreSQL acceptance requires a writable isolated test superuser.",
    );
  }
  const preexistingQc2Roles = await baseClient.query(`
    SELECT rolname
    FROM pg_catalog.pg_roles
    WHERE rolname = 'qc2_migrator' OR rolname LIKE 'qc2_runtime_%'
  `);
  removeQc2RolesCreatedByTest = preexistingQc2Roles.rowCount === 0;

  const rollbackScripts = await Promise.all(
    rollbackScriptPaths.map(async (scriptPath) =>
      (await readFile(scriptPath, "utf8")).replace(
        /^\\set ON_ERROR_STOP on\s*$/gm,
        "",
      ),
    ),
  );
  await baseClient.query("BEGIN ISOLATION LEVEL SERIALIZABLE");
  try {
    for (const [index, script] of rollbackScripts.entries()) {
      try {
        await baseClient.query(script);
      } catch (error) {
        const relativePath = path.relative(
          repositoryRoot,
          rollbackScriptPaths[index],
        );
        throw new Error(
          `Rollback-only PostgreSQL acceptance failed in ${relativePath}: ${error.message}`,
          { cause: error },
        );
      }
    }
    await baseClient.query("ROLLBACK");
  } catch (error) {
    await baseClient.query("ROLLBACK");
    throw error;
  }

  await baseClient.query(
    `CREATE DATABASE "${scratchDatabase}" WITH TEMPLATE template0 ENCODING 'UTF8'`,
  );
  scratchCreated = true;
  scratchClient = new Client({ connectionString: scratchUrl.toString() });
  await scratchClient.connect();

  for (const migrationPath of migrationPaths) {
    const script = (await readFile(migrationPath, "utf8")).replace(
      /^\\set ON_ERROR_STOP on\s*$/gm,
      "",
    );
    const relativePath = path.relative(repositoryRoot, migrationPath);
    await scratchClient.query("BEGIN");
    try {
      await scratchClient.query(script);
      await scratchClient.query("COMMIT");
    } catch (error) {
      await scratchClient.query("ROLLBACK");
      throw new Error(
        `PostgreSQL migration failed in ${relativePath}: ${error.message}`,
        { cause: error },
      );
    }
  }

  const fixtures = JSON.parse(
    await readFile(
      path.join(repositoryRoot, "packages/contracts/fixtures/v1/valid.json"),
      "utf8",
    ),
  );
  const intentFixture = structuredClone(
    fixtures.find((row) => row.contract === "PaperOrderIntent").payload,
  );
  const reservationFixture = structuredClone(
    fixtures.find((row) => row.contract === "Reservation").payload,
  );
  await runQc2045PaperOrderAcceptance({
    connectionString: scratchUrl.toString(),
    adminClient: scratchClient,
    intentFixture,
    reservationFixture,
  });
  await runQc2046ExecutionAuthorityAcceptance({
    connectionString: scratchUrl.toString(),
    adminClient: scratchClient,
    intentFixture,
    reservationFixture,
  });
  await runQc2048DurablePositionStateAcceptance({
    connectionString: scratchUrl.toString(),
    adminClient: scratchClient,
    fixtures,
  });
  await runQc2049BrokerReconciliationAcceptance({
    connectionString: scratchUrl.toString(),
    adminClient: scratchClient,
    fixtures,
  });
  console.log(
    "QC2-049 PostgreSQL acceptance passed: stable evidence-backed checkpoints, idempotent repeats, explicit finding resolution, account-reset holds, and unchanged broker orders/submission attempts.",
  );
} finally {
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
      ORDER BY CASE WHEN rolname = 'qc2_migrator' THEN 1 ELSE 0 END,
               rolname
    `);
    for (const row of createdRoles.rows) {
      await baseClient.query(`DROP ROLE IF EXISTS "${row.rolname}"`);
    }
  }
  await baseClient.end();
}
