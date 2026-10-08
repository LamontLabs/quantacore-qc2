import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "pg";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(testDirectory, "../../..");
const scriptPaths = [
  "migrations/0001_postgresql_authority_foundation.sql",
  "tests/database/qc2_005_postgres_acceptance.sql",
  "migrations/0002_evidence_authority.sql",
  "tests/database/qc2_006_postgres_acceptance.sql",
  "migrations/0003_prediction_authority.sql",
  "tests/database/qc2_025_postgres_acceptance.sql",
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

const client = new Client({ connectionString });
await client.connect();
try {
  const identity = await client.query(`
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

  const scripts = await Promise.all(
    scriptPaths.map((scriptPath) => readFile(scriptPath, "utf8")),
  );
  await client.query("BEGIN ISOLATION LEVEL SERIALIZABLE");
  try {
    for (const script of scripts) {
      await client.query(script);
    }
    await client.query("ROLLBACK");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  }
  console.log(
    "QC2-005, QC2-006, and QC2-025 PostgreSQL acceptance checks passed; all DDL and fixtures were rolled back.",
  );
} finally {
  await client.end();
}
