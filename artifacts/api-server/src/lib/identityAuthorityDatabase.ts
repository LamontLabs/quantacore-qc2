import pg from "pg";

const ENVIRONMENTS = ["development", "test", "research", "production"] as const;
const { Pool } = pg;

type RuntimeEnvironment = (typeof ENVIRONMENTS)[number];
type QueryValue = string | number | boolean | null;

interface IdentityDatabaseConfig {
  environment: RuntimeEnvironment;
  expectedDatabase: string;
  connectionString: string;
}

interface IdentityPool {
  query(
    statement: string,
    values?: QueryValue[],
  ): Promise<{ rows: Array<Record<string, unknown>> }>;
  end(): Promise<void>;
}

function resolveIdentityDatabaseConfig(
  environment = process.env,
): IdentityDatabaseConfig {
  const qc2Environment = environment.QC2_ENV;
  if (!ENVIRONMENTS.includes(qc2Environment as RuntimeEnvironment)) {
    throw new Error("identity_database_unavailable");
  }
  if (environment.QC2_AUTHORITY !== "owner_api") {
    throw new Error("identity_database_unavailable");
  }

  const runtimeEnvironment = qc2Environment as RuntimeEnvironment;
  const environmentKey = runtimeEnvironment.toUpperCase();
  const expectedDatabaseKey = `QC2_EXPECTED_DATABASE_${environmentKey}`;
  const expectedDatabase = environment[expectedDatabaseKey];
  if (
    typeof expectedDatabase !== "string" ||
    !/^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,62}$/.test(expectedDatabase)
  ) {
    throw new Error("identity_database_unavailable");
  }
  for (const otherEnvironment of ENVIRONMENTS) {
    if (otherEnvironment === runtimeEnvironment) continue;
    if (
      environment[`QC2_EXPECTED_DATABASE_${otherEnvironment.toUpperCase()}`] ===
      expectedDatabase
    ) {
      throw new Error("identity_database_unavailable");
    }
  }

  const suffix = `${environmentKey}_IDENTITY`;
  const connectionKey = `QC2_DATABASE_URL_${suffix}`;
  const connectionString = environment[connectionKey];
  if (typeof connectionString !== "string" || connectionString.trim() === "") {
    throw new Error("identity_database_unavailable");
  }
  const ownerApiConnection =
    environment[`QC2_DATABASE_URL_${environmentKey}_OWNER_API`];
  if (connectionString === ownerApiConnection) {
    throw new Error("identity_database_unavailable");
  }
  for (const otherEnvironment of ENVIRONMENTS) {
    if (otherEnvironment === runtimeEnvironment) continue;
    if (
      environment[
        `QC2_DATABASE_URL_${otherEnvironment.toUpperCase()}_IDENTITY`
      ] === connectionString
    ) {
      throw new Error("identity_database_unavailable");
    }
  }
  try {
    const url = new URL(connectionString);
    if (url.protocol !== "postgres:" && url.protocol !== "postgresql:") {
      throw new Error("invalid protocol");
    }
  } catch {
    throw new Error("identity_database_unavailable");
  }

  return {
    environment: runtimeEnvironment,
    expectedDatabase,
    connectionString,
  };
}

async function createIdentityPool(): Promise<IdentityPool> {
  const config = resolveIdentityDatabaseConfig();
  const pool = new Pool({
    connectionString: config.connectionString,
  }) as IdentityPool;

  try {
    const { rows } = await pool.query(`
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
    const identity = rows[0];
    if (
      !identity ||
      identity.database_name !== config.expectedDatabase ||
      identity.session_role !== "qc2_runtime_identity" ||
      identity.effective_role !== "qc2_runtime_identity" ||
      identity.is_replica !== false ||
      identity.can_login !== true ||
      identity.is_superuser !== false ||
      identity.can_create_databases !== false ||
      identity.can_create_roles !== false ||
      identity.can_replicate !== false ||
      identity.bypasses_rls !== false ||
      identity.inherits_roles !== false ||
      identity.has_role_membership !== false
    ) {
      throw new Error("identity_database_unavailable");
    }
    return pool;
  } catch {
    await pool.end().catch(() => undefined);
    throw new Error("identity_database_unavailable");
  }
}

let identityPoolPromise: Promise<IdentityPool> | undefined;

export const identityAuthorityDatabase = Object.freeze({
  async query(statement: string, values?: unknown[]) {
    identityPoolPromise ??= createIdentityPool();
    const pool = await identityPoolPromise;
    const result = await pool.query(
      statement,
      values as QueryValue[] | undefined,
    );
    return {
      rows: result.rows.map((row) => ({ result: row.result })),
    };
  },
});
