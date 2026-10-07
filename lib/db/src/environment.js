export const QC2_ENVIRONMENTS = Object.freeze([
  "development",
  "test",
  "research",
  "production",
]);

export const DATABASE_AUTHORITIES = Object.freeze([
  "alert",
  "apexlab",
  "build_governance",
  "calendar",
  "configuration",
  "core",
  "durable_job_service",
  "evidence",
  "execution",
  "feature",
  "governance",
  "ground_truth",
  "identity",
  "inference",
  "instrument_universe",
  "label",
  "market_data",
  "model_registry",
  "owner_api",
  "prediction",
  "promotion",
  "quantscore",
  "runner_protocol",
  "safety",
  "strategy",
  "universe",
  "validation",
]);

const authoritySet = new Set(DATABASE_AUTHORITIES);
const environmentSet = new Set(QC2_ENVIRONMENTS);

export function resolveDatabaseConfig(environment = process.env) {
  const qc2Environment = environment.QC2_ENV;
  if (!environmentSet.has(qc2Environment)) {
    throw new Error(
      "QC2_ENV must be one of development, test, research, or production.",
    );
  }

  const authority = environment.QC2_AUTHORITY;
  if (!authoritySet.has(authority)) {
    throw new Error(
      "QC2_AUTHORITY must name a registered QC2 database authority.",
    );
  }

  const expectedDatabaseKey = `QC2_EXPECTED_DATABASE_${qc2Environment.toUpperCase()}`;
  const expectedDatabase = environment[expectedDatabaseKey];
  if (
    typeof expectedDatabase !== "string" ||
    !/^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,62}$/.test(expectedDatabase)
  ) {
    throw new Error(
      `${expectedDatabaseKey} must name the expected PostgreSQL database.`,
    );
  }

  for (const otherEnvironment of QC2_ENVIRONMENTS) {
    if (otherEnvironment === qc2Environment) continue;
    const otherKey = `QC2_EXPECTED_DATABASE_${otherEnvironment.toUpperCase()}`;
    if (environment[otherKey] === expectedDatabase) {
      throw new Error(
        `Expected database names for ${qc2Environment} and ${otherEnvironment} must be distinct.`,
      );
    }
  }

  const suffix = `${qc2Environment.toUpperCase()}_${authority.toUpperCase()}`;
  const connectionKey = `QC2_DATABASE_URL_${suffix}`;
  const connectionString = environment[connectionKey];
  if (typeof connectionString !== "string" || connectionString.trim() === "") {
    if (environment.DATABASE_URL) {
      throw new Error(
        `${connectionKey} is required; generic DATABASE_URL is not an allowed fallback.`,
      );
    }
    throw new Error(
      `${connectionKey} is required; no database URL fallback is permitted.`,
    );
  }

  for (const otherEnvironment of QC2_ENVIRONMENTS) {
    if (otherEnvironment === qc2Environment) continue;
    const otherKey = `QC2_DATABASE_URL_${otherEnvironment.toUpperCase()}_${authority.toUpperCase()}`;
    if (environment[otherKey] === connectionString) {
      throw new Error(
        `Database credentials for ${qc2Environment} and ${otherEnvironment} must be distinct.`,
      );
    }
  }

  return Object.freeze({
    environment: qc2Environment,
    authority,
    expectedDatabase,
    connectionString,
  });
}
