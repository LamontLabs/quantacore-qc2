import { defineConfig } from "drizzle-kit";
import path from "path";

if (
  process.argv.some((argument) =>
    ["push", "push-force", "migrate", "drop"].includes(argument),
  )
) {
  throw new Error(
    "Drizzle Kit database mutation commands are disabled; use the reviewed forward-only SQL migration runner.",
  );
}

const migrationDatabaseUrl = process.env.QC2_MIGRATION_DATABASE_URL;
if (!migrationDatabaseUrl) {
  throw new Error(
    "QC2_MIGRATION_DATABASE_URL is required; generic DATABASE_URL is not allowed.",
  );
}

export default defineConfig({
  schema: path.join(__dirname, "./src/schema/index.ts"),
  dialect: "postgresql",
  dbCredentials: {
    url: migrationDatabaseUrl,
  },
});
