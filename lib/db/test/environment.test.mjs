import assert from "node:assert/strict";
import test from "node:test";
import { resolveDatabaseConfig } from "../src/environment.js";

const baseEnvironment = {
  QC2_ENV: "development",
  QC2_AUTHORITY: "execution",
  QC2_EXPECTED_DATABASE_DEVELOPMENT: "qc2_dev",
  QC2_DATABASE_URL_DEVELOPMENT_EXECUTION: "postgresql://dev.example/qc2_dev",
};

test("selects only the explicitly named environment and authority", () => {
  assert.deepEqual(resolveDatabaseConfig(baseEnvironment), {
    environment: "development",
    authority: "execution",
    expectedDatabase: "qc2_dev",
    connectionString: "postgresql://dev.example/qc2_dev",
  });
});

test("fails closed for a missing or unknown environment", () => {
  assert.throws(
    () => resolveDatabaseConfig({ ...baseEnvironment, QC2_ENV: undefined }),
    /QC2_ENV must be one of/,
  );
  assert.throws(
    () => resolveDatabaseConfig({ ...baseEnvironment, QC2_ENV: "staging" }),
    /QC2_ENV must be one of/,
  );
});

test("requires a registered authority and its exact environment URL", () => {
  assert.throws(
    () =>
      resolveDatabaseConfig({ ...baseEnvironment, QC2_AUTHORITY: undefined }),
    /QC2_AUTHORITY must name/,
  );
  assert.throws(
    () =>
      resolveDatabaseConfig({
        QC2_ENV: "production",
        QC2_AUTHORITY: "execution",
        QC2_EXPECTED_DATABASE_PRODUCTION: "qc2_prod",
        QC2_DATABASE_URL_DEVELOPMENT_EXECUTION:
          "postgresql://dev.example/qc2_dev",
      }),
    /QC2_DATABASE_URL_PRODUCTION_EXECUTION is required/,
  );
});

test("requires the environment-specific expected database identity", () => {
  assert.throws(
    () =>
      resolveDatabaseConfig({
        ...baseEnvironment,
        QC2_EXPECTED_DATABASE_DEVELOPMENT: undefined,
      }),
    /QC2_EXPECTED_DATABASE_DEVELOPMENT must name/,
  );
  assert.throws(
    () =>
      resolveDatabaseConfig({
        ...baseEnvironment,
        QC2_EXPECTED_DATABASE_TEST: "qc2_dev",
      }),
    /database names for development and test must be distinct/,
  );
});

test("does not fall back to the inherited generic DATABASE_URL", () => {
  assert.throws(
    () =>
      resolveDatabaseConfig({
        QC2_ENV: "development",
        QC2_AUTHORITY: "execution",
        QC2_EXPECTED_DATABASE_DEVELOPMENT: "qc2_dev",
        DATABASE_URL: "postgresql://legacy.example/shared",
      }),
    /generic DATABASE_URL is not an allowed fallback/,
  );
});

test("rejects reuse of the same authority credentials across environments", () => {
  assert.throws(
    () =>
      resolveDatabaseConfig({
        ...baseEnvironment,
        QC2_DATABASE_URL_TEST_EXECUTION:
          baseEnvironment.QC2_DATABASE_URL_DEVELOPMENT_EXECUTION,
      }),
    /credentials for development and test must be distinct/,
  );
});

test("rejects unknown authority values instead of creating a broad connection", () => {
  assert.throws(
    () =>
      resolveDatabaseConfig({
        ...baseEnvironment,
        QC2_AUTHORITY: "core_and_execution",
      }),
    /QC2_AUTHORITY must name/,
  );
});
