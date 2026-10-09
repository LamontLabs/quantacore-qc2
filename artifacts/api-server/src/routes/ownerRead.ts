import { createHash } from "node:crypto";
import { Router, type IRouter, type Request, type Response } from "express";
import {
  OWNER_READ_VIEWS,
  PostgresOwnerReadStore,
  type OwnerReadPage,
  type OwnerReadStore,
  type OwnerReadView,
  type OwnerSessionBinding,
  type ProjectionCursor,
} from "../lib/ownerReadStore";

const ACCESS_TOKEN_DOMAIN = "qc2.owner.access.v1";
const MAX_PAGE_SIZE = 100;
const MAX_EXPORT_SIZE = 1000;
const MAX_EXPORT_BYTES = 1_048_576;
const MAX_QUERY_BYTES = 8192;
const BASE64URL = /^[A-Za-z0-9_-]+$/;
const ENVIRONMENTS = new Set(["development", "test", "research", "production"]);

interface OwnerReadRequest extends Request {
  ownerSession?: OwnerSessionBinding;
}

interface RouterDependencies {
  getStore: () => Promise<OwnerReadStore>;
  getEnvironment: () => string | undefined;
  now?: () => Date;
}

function tokenDigest(token: string): string {
  return createHash("sha256")
    .update(`QC2-HASH-V1\0${ACCESS_TOKEN_DOMAIN}\0`, "utf8")
    .update(token, "utf8")
    .digest("hex");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function fail(res: Response, status: number, code: string): void {
  res.setHeader("Cache-Control", "no-store");
  res.status(status).json({
    error: {
      code,
      message:
        status >= 500
          ? "The owner read service is temporarily unavailable."
          : "The request could not be authorized or validated.",
    },
  });
}

function readBearerToken(request: Request): string | null {
  const header = request.header("authorization");
  if (!header || header.length > 512) return null;
  const match = /^Bearer ([A-Za-z0-9_-]{40,256})$/.exec(header);
  return match?.[1] ?? null;
}

function parseQueryString(request: Request): URLSearchParams | null {
  if (Buffer.byteLength(request.originalUrl, "utf8") > MAX_QUERY_BYTES) return null;
  return new URL(request.originalUrl, "http://owner-api.invalid").searchParams;
}

function parseLimit(
  params: URLSearchParams,
  maximum: number,
  defaultValue: number,
): number | null {
  const values = params.getAll("limit");
  if (values.length > 1) return null;
  if (values.length === 0) return defaultValue;
  if (!/^[1-9][0-9]{0,4}$/.test(values[0])) return null;
  const parsed = Number(values[0]);
  return parsed <= maximum ? parsed : null;
}

function parseCursor(
  value: string | null,
  viewName: OwnerReadView,
): ProjectionCursor | null | false {
  if (value === null) return null;
  if (value.length > 2048 || !BASE64URL.test(value)) return false;
  try {
    const bytes = Buffer.from(value, "base64url");
    if (bytes.toString("base64url") !== value) return false;
    const parsed: unknown = JSON.parse(bytes.toString("utf8"));
    if (
      !isRecord(parsed) ||
      Object.keys(parsed).sort().join(",") !==
        "item_id,projection_sequence,sort_key,version,view_name" ||
      parsed.version !== 1 ||
      parsed.view_name !== viewName ||
      !Number.isSafeInteger(parsed.projection_sequence) ||
      (parsed.projection_sequence as number) < 1 ||
      typeof parsed.sort_key !== "string" ||
      parsed.sort_key.length > 256 ||
      !/^[ -~]*$/.test(parsed.sort_key) ||
      typeof parsed.item_id !== "string" ||
      parsed.item_id.length < 1 ||
      parsed.item_id.length > 128 ||
      !/^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(parsed.item_id)
    ) {
      return false;
    }
    if (
      JSON.stringify({
        item_id: parsed.item_id,
        projection_sequence: parsed.projection_sequence,
        sort_key: parsed.sort_key,
        version: parsed.version,
        view_name: parsed.view_name,
      }) !== bytes.toString("utf8")
    ) {
      return false;
    }
    return {
      projectionSequence: parsed.projection_sequence as number,
      sortKey: parsed.sort_key,
      itemId: parsed.item_id,
    };
  } catch {
    return false;
  }
}

function encodeCursor(viewName: OwnerReadView, page: OwnerReadPage): string | null {
  if (!page.has_more || page.items.length === 0) return null;
  const last = page.items[page.items.length - 1];
  return Buffer.from(
    JSON.stringify({
      item_id: last.item_id,
      projection_sequence: page.projection_sequence,
      sort_key: last.sort_key,
      version: 1,
      view_name: viewName,
    }),
    "utf8",
  ).toString("base64url");
}

function isView(value: string): value is OwnerReadView {
  return (OWNER_READ_VIEWS as readonly string[]).includes(value);
}

function publicPage(
  environmentNamespace: string,
  viewName: OwnerReadView,
  page: OwnerReadPage,
): Record<string, unknown> {
  return {
    schema_name: "qc2.owner_api.OwnerReadPage.v1",
    schema_version: "1.0",
    environment_namespace: environmentNamespace,
    view_name: viewName,
    projection_sequence: page.projection_sequence,
    source_sequence: page.source_sequence,
    source_highwater_sequence: page.source_highwater_sequence,
    lag: page.lag,
    stale: page.stale,
    data_state: page.data_state,
    built_at: page.built_at,
    freshness_deadline: page.freshness_deadline,
    source_refs: page.source_refs,
    items: page.items,
    next_cursor: encodeCursor(viewName, page),
  };
}

function responseBytes(value: unknown): number {
  return Buffer.byteLength(JSON.stringify(value), "utf8");
}

export function createOwnerReadRouter(
  dependencies: RouterDependencies,
): IRouter {
  const router: IRouter = Router();
  const now = dependencies.now ?? (() => new Date());

  const requireOwnerRead = async (
    request: OwnerReadRequest,
    response: Response,
  ): Promise<{ store: OwnerReadStore; environment: string } | null> => {
    const environment = dependencies.getEnvironment();
    if (!environment || !ENVIRONMENTS.has(environment)) {
      fail(response, 503, "owner_read_unavailable");
      return null;
    }
    const token = readBearerToken(request);
    if (!token || Buffer.byteLength(token, "utf8") < 32) {
      fail(response, 401, "unauthorized");
      return null;
    }
    try {
      const store = await dependencies.getStore();
      const binding = await store.resolveAccess(environment, tokenDigest(token), now());
      if (!binding) {
        fail(response, 401, "unauthorized");
        return null;
      }
      if (
        binding.environmentNamespace !== environment ||
        !binding.scopeRefs.includes("OWNER_READ")
      ) {
        fail(response, 403, "forbidden");
        return null;
      }
      request.ownerSession = binding;
      return { store, environment };
    } catch {
      request.log?.warn(
        { requestId: request.id },
        "owner access verification failed",
      );
      fail(response, 503, "owner_read_unavailable");
      return null;
    }
  };

  router.get("/owner/v1/diagnostics", async (request, response): Promise<void> => {
    const authorized = await requireOwnerRead(
      request as OwnerReadRequest,
      response,
    );
    if (!authorized) return;
    try {
      const diagnostics = await authorized.store.diagnostics(
        authorized.environment,
      );
      response.setHeader("Cache-Control", "no-store");
      response.json(diagnostics);
    } catch {
      request.log?.warn(
        { requestId: request.id },
        "owner diagnostics query failed",
      );
      fail(response, 503, "owner_read_unavailable");
    }
  });

  router.get(
    "/owner/v1/export",
    async (request, response): Promise<void> => {
      const authorized = await requireOwnerRead(
        request as OwnerReadRequest,
        response,
      );
      if (!authorized) return;
      const params = parseQueryString(request);
      if (!params) {
        fail(response, 400, "invalid_pagination");
        return;
      }
      const rawViewName = params.get("view");
      if (typeof rawViewName !== "string" || !isView(rawViewName)) {
        fail(response, 404, "owner_view_not_found");
        return;
      }
      const viewName = rawViewName;
      if ([...params.keys()].some((key) => key !== "view" && key !== "limit")) {
        fail(response, 400, "invalid_pagination");
        return;
      }
      const limit = parseLimit(params, MAX_EXPORT_SIZE, 100);
      if (
        limit === null ||
        params.getAll("view").length !== 1 ||
        params.getAll("limit").length > 1
      ) {
        fail(response, 400, "invalid_pagination");
        return;
      }
      try {
        const page = await authorized.store.readPage({
          environmentNamespace: authorized.environment,
          viewName,
          limit,
          cursor: null,
        });
        if (!page) {
          fail(response, 503, "projection_unavailable");
          return;
        }
        if (page.has_more || page.items.length > limit) {
          fail(response, 413, "export_too_large");
          return;
        }
        const body = publicPage(authorized.environment, viewName, page);
        const bytes = responseBytes(body);
        if (bytes > MAX_EXPORT_BYTES) {
          fail(response, 413, "export_too_large");
          return;
        }
        await authorized.store.recordExport({
          environmentNamespace: authorized.environment,
          sessionRecordId: (request as OwnerReadRequest).ownerSession!
            .sessionRecordId,
          viewName,
          projectionSequence: page.projection_sequence,
          itemCount: page.items.length,
          responseBytes: bytes,
        });
        response.setHeader("Cache-Control", "no-store");
        response.json(body);
      } catch {
        request.log?.warn({ requestId: request.id }, "owner export failed");
        fail(response, 503, "owner_read_unavailable");
      }
    },
  );

  router.get(
    "/owner/v1/evidence/detail",
    async (request, response): Promise<void> => {
      const authorized = await requireOwnerRead(
        request as OwnerReadRequest,
        response,
      );
      if (!authorized) return;
      const params = parseQueryString(request);
      if (
        !params ||
        [...params.keys()].some((key) => key !== "item_id") ||
        params.getAll("item_id").length !== 1
      ) {
        fail(response, 400, "invalid_query");
        return;
      }
      const rawItemId = params.get("item_id");
      if (
        typeof rawItemId !== "string" ||
        !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(rawItemId)
      ) {
        fail(response, 400, "invalid_evidence_id");
        return;
      }
      try {
        const detail = await authorized.store.readEvidenceDetail({
          environmentNamespace: authorized.environment,
          itemId: rawItemId,
        });
        if (!detail) {
          fail(response, 404, "evidence_not_found");
          return;
        }
        response.setHeader("Cache-Control", "no-store");
        response.json({
          schema_name: "qc2.owner_api.OwnerEvidenceDetail.v1",
          schema_version: "1.0",
          environment_namespace: authorized.environment,
          projection_sequence: detail.projection_sequence,
          item: detail.item,
        });
      } catch {
        request.log?.warn(
          { requestId: request.id },
          "owner evidence detail query failed",
        );
        fail(response, 503, "owner_read_unavailable");
      }
    },
  );

  router.get("/owner/v1", async (request, response): Promise<void> => {
    const authorized = await requireOwnerRead(
      request as OwnerReadRequest,
      response,
    );
    if (!authorized) return;
    const params = parseQueryString(request);
    if (!params) {
      fail(response, 400, "invalid_pagination");
      return;
    }
    const rawViewName = params.get("view");
    if (typeof rawViewName !== "string" || !isView(rawViewName)) {
      fail(response, 404, "owner_view_not_found");
      return;
    }
    const viewName = rawViewName;
    if (
      [...params.keys()].some(
        (key) => key !== "view" && key !== "limit" && key !== "cursor",
      )
    ) {
      fail(response, 400, "invalid_pagination");
      return;
    }
    const limit = parseLimit(params, MAX_PAGE_SIZE, 50);
    const cursor = parseCursor(params.get("cursor"), viewName);
    if (
      limit === null ||
      cursor === false ||
      params.getAll("view").length !== 1 ||
      params.getAll("limit").length > 1 ||
      params.getAll("cursor").length > 1
    ) {
      fail(response, 400, "invalid_pagination");
      return;
    }
    try {
      const page = await authorized.store.readPage({
        environmentNamespace: authorized.environment,
        viewName,
        limit,
        cursor,
      });
      if (!page) {
        fail(response, 503, "projection_unavailable");
        return;
      }
      if (page.items.length > limit) {
        fail(response, 503, "owner_read_unavailable");
        return;
      }
      response.setHeader("Cache-Control", "no-store");
      response.json(publicPage(authorized.environment, viewName, page));
    } catch (error) {
      if (
        error instanceof Error &&
        error.message === "owner_read_cursor_expired"
      ) {
        fail(response, 409, "cursor_expired");
        return;
      }
      request.log?.warn({ requestId: request.id }, "owner view query failed");
      fail(response, 503, "owner_read_unavailable");
    }
  });

  return router;
}

let productionStore: Promise<OwnerReadStore> | undefined;

async function getProductionStore(): Promise<OwnerReadStore> {
  productionStore ??= Promise.all([
    import("@workspace/db"),
    import("../lib/identityAuthorityDatabase"),
  ]).then(([{ pool }, { identityAuthorityDatabase }]) =>
    new PostgresOwnerReadStore(
      {
        query: async (statement, values) => {
          const result = await pool.query(
            statement,
            values as unknown as (string | number | boolean | null)[],
          );
          return {
            rows: result.rows.map((row) => ({ result: row.result })),
          };
        },
      },
      identityAuthorityDatabase,
    ),
  );
  return productionStore;
}

const ownerReadRouter = createOwnerReadRouter({
  getStore: getProductionStore,
  getEnvironment: () => process.env.QC2_ENV,
});

export default ownerReadRouter;
