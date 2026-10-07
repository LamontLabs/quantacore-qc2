import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "pg";

const packageDirectory = path.dirname(fileURLToPath(import.meta.url));
const migrationDirectory = path.resolve(packageDirectory, "../../migrations");
const migrationPattern = /^\d{4}_[a-z0-9_]+\.sql$/;
const isBootstrap = process.argv.includes("--bootstrap");

function fail(message) {
  console.error(message);
  process.exitCode = 1;
}

if (!process.argv.includes("--apply")) {
  fail(
    "No migration was applied. Review the SQL, then rerun this command with --apply.",
  );
} else {
  const migrationEnvironment = process.env.QC2_MIGRATION_ENV;
  if (!["development", "test"].includes(migrationEnvironment)) {
    fail(
      "QC2_MIGRATION_ENV must be development or test; production migration is disabled.",
    );
  } else if (process.env.QC2_ENV !== migrationEnvironment) {
    fail("QC2_ENV must match QC2_MIGRATION_ENV before a migration can run.");
  } else {
    const expectedDatabaseKey = `QC2_EXPECTED_DATABASE_${migrationEnvironment.toUpperCase()}`;
    const expectedDatabase = process.env[expectedDatabaseKey];
    const connectionKey = isBootstrap
      ? "QC2_BOOTSTRAP_DATABASE_URL"
      : "QC2_MIGRATION_DATABASE_URL";
    const connectionString = process.env[connectionKey];
    if (!expectedDatabase || !connectionString) {
      fail(
        `${connectionKey} and ${expectedDatabaseKey} are required; values are never logged.`,
      );
    } else {
      let parsedUrl;
      try {
        parsedUrl = new URL(connectionString);
      } catch {
        fail(`${connectionKey} is not a valid PostgreSQL URL.`);
      }

      if (parsedUrl) {
        const configuredUser = decodeURIComponent(parsedUrl.username);
        const otherMigrationUrlKey = isBootstrap
          ? "QC2_MIGRATION_DATABASE_URL"
          : "QC2_BOOTSTRAP_DATABASE_URL";
        if (isBootstrap && configuredUser.startsWith("qc2_runtime_")) {
          fail(
            "Bootstrap must use a separately managed database-owner identity.",
          );
        } else if (!isBootstrap && configuredUser !== "qc2_migrator") {
          fail("QC2_MIGRATION_DATABASE_URL must connect as qc2_migrator.");
        } else if (process.env[otherMigrationUrlKey] === connectionString) {
          fail("Bootstrap and migration credentials must be distinct.");
        } else if (
          Object.entries(process.env).some(
            ([key, value]) =>
              key.startsWith("QC2_DATABASE_URL_") && value === connectionString,
          )
        ) {
          fail("Migration and runtime database credentials must be separate.");
        } else {
          const client = new Client({ connectionString });
          try {
            await client.connect();
            const identity = await client.query(`
              SELECT current_database() AS database_name,
                     session_user AS session_role,
                     current_user AS effective_role,
                     pg_catalog.pg_is_in_recovery() AS is_replica,
                     roles.rolcanlogin AS can_login,
                     roles.rolsuper AS is_superuser,
                     EXISTS (
                       SELECT 1
                       FROM pg_catalog.pg_database AS db_entry
                       WHERE db_entry.datname = current_database()
                         AND db_entry.datdba = roles.oid
                     ) AS owns_database,
                     roles.rolcreatedb AS can_create_databases,
                     roles.rolcreaterole AS can_create_roles,
                     roles.rolreplication AS can_replicate,
                     roles.rolbypassrls AS bypasses_rls,
                     roles.rolinherit AS inherits_roles,
                     EXISTS (
                       SELECT 1
                       FROM pg_catalog.pg_auth_members AS membership
                       JOIN pg_catalog.pg_roles AS granted_role
                         ON granted_role.oid = membership.roleid
                       JOIN pg_catalog.pg_roles AS member_role
                         ON member_role.oid = membership.member
                       WHERE granted_role.rolname = 'qc2_migrator'
                          OR granted_role.rolname ~ '^qc2_runtime_'
                          OR member_role.rolname = 'qc2_migrator'
                          OR member_role.rolname ~ '^qc2_runtime_'
                     ) AS has_qc2_role_membership
              FROM pg_catalog.pg_roles AS roles
              WHERE roles.rolname = current_user
            `);
            const databaseIdentity = identity.rows[0];
            if (
              !databaseIdentity ||
              databaseIdentity.database_name !== expectedDatabase
            ) {
              throw new Error(
                "Connected database did not match QC2_EXPECTED_DATABASE.",
              );
            }
            if (databaseIdentity.is_replica) {
              throw new Error("Migrations cannot run against a read replica.");
            }
            if (isBootstrap) {
              if (!databaseIdentity.is_superuser) {
                throw new Error(
                  "One-time bootstrap requires the database-owner superuser.",
                );
              }
              if (!databaseIdentity.owns_database) {
                throw new Error(
                  "One-time bootstrap identity must own the expected database.",
                );
              }
            } else if (
              databaseIdentity.session_role !== "qc2_migrator" ||
              databaseIdentity.effective_role !== "qc2_migrator" ||
              !databaseIdentity.can_login ||
              databaseIdentity.is_superuser ||
              databaseIdentity.can_create_databases ||
              databaseIdentity.can_create_roles ||
              databaseIdentity.can_replicate ||
              databaseIdentity.inherits_roles ||
              databaseIdentity.bypasses_rls ||
              databaseIdentity.has_qc2_role_membership
            ) {
              throw new Error(
                "Migration connection is not the isolated qc2_migrator identity.",
              );
            }

            const migrationFiles = (await readdir(migrationDirectory))
              .filter((name) => migrationPattern.test(name))
              .sort();
            if (!migrationFiles.length) {
              throw new Error("No numbered SQL migrations were found.");
            }

            const ledgerExists = await client.query(
              "SELECT pg_catalog.to_regclass('qc2_control.schema_migrations') IS NOT NULL AS ledger_present",
            );
            let ledgerPresent = ledgerExists.rows[0].ledger_present;
            if (isBootstrap === ledgerPresent) {
              throw new Error(
                isBootstrap
                  ? "Bootstrap is one-time and the migration ledger already exists."
                  : "Migration ledger is missing; use the reviewed one-time bootstrap procedure.",
              );
            }

            for (const fileName of migrationFiles) {
              const sql = await readFile(
                path.join(migrationDirectory, fileName),
                "utf8",
              );
              const sha256 = createHash("sha256").update(sql).digest("hex");
              const alreadyApplied = ledgerPresent
                ? await client.query(
                    "SELECT sha256 FROM qc2_control.schema_migrations WHERE version = $1",
                    [fileName],
                  )
                : { rows: [] };

              if (alreadyApplied.rows.length) {
                if (alreadyApplied.rows[0].sha256.trim() !== sha256) {
                  throw new Error(`Applied migration was edited: ${fileName}`);
                }
                continue;
              }

              await client.query("BEGIN");
              try {
                await client.query(sql);
                const ledgerNowExists = await client.query(
                  "SELECT pg_catalog.to_regclass('qc2_control.schema_migrations') IS NOT NULL AS ledger_present",
                );
                if (!ledgerNowExists.rows[0].ledger_present) {
                  throw new Error(
                    "Migration did not create qc2_control.schema_migrations.",
                  );
                }
                await client.query(
                  `INSERT INTO qc2_control.schema_migrations(version, sha256)
                   VALUES ($1, $2)`,
                  [fileName, sha256],
                );
                await client.query("COMMIT");
                ledgerPresent = true;
                console.log(`Applied ${fileName}.`);
              } catch (error) {
                await client.query("ROLLBACK");
                throw error;
              }
            }
            console.log(
              "Migration set is current; no runtime startup migration is configured.",
            );
          } catch (error) {
            fail(error instanceof Error ? error.message : "Migration failed.");
          } finally {
            await client.end();
          }
        }
      }
    }
  }
}
