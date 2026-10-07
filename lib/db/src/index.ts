import { drizzle } from "drizzle-orm/node-postgres";
import pg from "pg";
import * as schema from "./schema";
import { resolveDatabaseConfig } from "./environment.js";

const { Pool } = pg;
const databaseConfig = resolveDatabaseConfig();

export const pool = new Pool({
  connectionString: databaseConfig.connectionString,
});
export const db = drizzle(pool, { schema });

async function verifyDatabaseIdentity(): Promise<void> {
  const client = await pool.connect();
  try {
    const result = await client.query(`
      SELECT current_database() AS database_name,
             session_user AS session_role,
             current_user AS effective_role,
             pg_catalog.pg_is_in_recovery() AS is_replica,
             roles.rolcanlogin AS can_login,
             roles.rolsuper AS is_superuser,
             roles.rolcreatedb AS can_create_databases,
             roles.rolcreaterole AS can_create_roles,
             roles.rolreplication AS can_replicate,
             roles.rolbypassrls AS bypasses_rls,
             roles.rolinherit AS inherits_roles,
             EXISTS (
               SELECT 1
               FROM pg_catalog.pg_roles AS candidate
               WHERE candidate.oid <> roles.oid
                 AND pg_catalog.pg_has_role(
                   session_user, candidate.rolname, 'MEMBER'
                 )
             ) AS has_role_membership
      FROM pg_catalog.pg_roles AS roles
      WHERE roles.rolname = current_user
    `);
    const identity = result.rows[0];
    const expectedRole = `qc2_runtime_${databaseConfig.authority}`;
    if (
      !identity ||
      identity.database_name !== databaseConfig.expectedDatabase ||
      identity.session_role !== expectedRole ||
      identity.effective_role !== expectedRole ||
      identity.is_replica ||
      !identity.can_login ||
      identity.is_superuser ||
      identity.can_create_databases ||
      identity.can_create_roles ||
      identity.can_replicate ||
      identity.bypasses_rls ||
       identity.inherits_roles ||
       identity.has_role_membership
    ) {
      throw new Error(
        "Database identity guard failed: expected database or least-privilege runtime role did not match.",
      );
    }
  } catch {
    throw new Error(
      "Database identity guard failed: the configured database and runtime role could not be verified.",
    );
  } finally {
    client.release();
  }
}

try {
  await verifyDatabaseIdentity();
} catch (error) {
  await pool.end();
  throw error;
}

export * from "./schema";
