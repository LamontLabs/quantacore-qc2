import { defineConfig, InputTransformerFn } from "orval";
import path from "path";

const root = path.resolve(__dirname, "..", "..");
const apiClientReactSrc = path.resolve(root, "lib", "api-client-react", "src");
const apiZodSrc = path.resolve(root, "lib", "api-zod", "src");
const ownerPayloadSchemas = [
  "../../packages/owner_api/schemas/v1/OwnerTodayPayload.schema.json",
  "../../packages/owner_api/schemas/v1/OwnerPredictionsPayload.schema.json",
  "../../packages/owner_api/schemas/v1/OwnerValidationPayload.schema.json",
  "../../packages/owner_api/schemas/v1/OwnerModelsPayload.schema.json",
  "../../packages/owner_api/schemas/v1/OwnerSystemPayload.schema.json",
  "../../packages/owner_api/schemas/v1/OwnerPositionsPayload.schema.json",
  "../../packages/owner_api/schemas/v1/OwnerAlertsPayload.schema.json",
  "../../packages/owner_api/schemas/v1/OwnerReportsPayload.schema.json",
  "../../packages/owner_api/schemas/v1/OwnerEvidencePayload.schema.json",
];

// Our exports make assumptions about the title of the API being "Api" (i.e. generated output is `api.ts`).
const titleTransformer: InputTransformerFn = (config) => {
  config.info ??= {};
  config.info.title = "Api";

  return config;
};

export default defineConfig({
  "api-client-react": {
    input: {
      target: "./openapi.yaml",
      parserOptions: {
        externalRefs: { allow: ownerPayloadSchemas },
      },
      override: {
        transformer: titleTransformer,
      },
    },
    output: {
      workspace: apiClientReactSrc,
      target: "generated",
      client: "react-query",
      mode: "split",
      baseUrl: "/api",
      clean: true,
      prettier: true,
      override: {
        fetch: {
          includeHttpResponseReturnType: false,
        },
        mutator: {
          path: path.resolve(apiClientReactSrc, "custom-fetch.ts"),
          name: "customFetch",
        },
      },
    },
  },
  zod: {
    input: {
      target: "./openapi.yaml",
      parserOptions: {
        externalRefs: { allow: ownerPayloadSchemas },
      },
      override: {
        transformer: titleTransformer,
      },
    },
    output: {
      workspace: apiZodSrc,
      client: "zod",
      target: "generated",
      schemas: { path: "generated/types", type: "typescript" },
      mode: "split",
      clean: true,
      prettier: true,
      override: {
        zod: {
          // Orval resolves `auto` from lib/api-spec/package.json, which has no
          // zod dependency, so orval >= 8.23 falls back to Zod 4 syntax while
          // the catalog installs zod 3. Pin to match the catalog.
          version: 3,
          coerce: {
            query: ['boolean', 'number', 'string'],
            param: ['boolean', 'number', 'string'],
            body: ['bigint', 'date'],
            response: ['bigint', 'date'],
          },
        },
        useDates: true,
        useBigInt: true,
      },
    },
  },
});
