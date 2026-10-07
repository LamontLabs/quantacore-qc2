export declare const QC2_ENVIRONMENTS: readonly [
  "development",
  "test",
  "research",
  "production",
];

export declare const DATABASE_AUTHORITIES: readonly [
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
];

export type Qc2Environment = (typeof QC2_ENVIRONMENTS)[number];
export type DatabaseAuthority = (typeof DATABASE_AUTHORITIES)[number];

export interface Qc2DatabaseConfig {
  environment: Qc2Environment;
  authority: DatabaseAuthority;
  expectedDatabase: string;
  connectionString: string;
}

export declare function resolveDatabaseConfig(
  environment?: NodeJS.ProcessEnv,
): Qc2DatabaseConfig;
