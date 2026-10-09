import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { after, before, test } from "node:test";
import express from "express";
import type { Server } from "node:http";
import healthRouter from "../src/routes/health";
import {
  createOwnerReadRouter,
} from "../src/routes/ownerRead";
import type {
  OwnerEvidenceDetail,
  OwnerReadPage,
  OwnerReadQueryPort,
  OwnerReadStore,
  OwnerReadView,
  ProjectionCursor,
} from "../src/lib/ownerReadStore";
import { PostgresOwnerReadStore } from "../src/lib/ownerReadStore";

const TOKEN = "owner-read-test-token-0123456789-abcdefg";
const TOKEN_HASH = createHash("sha256")
  .update("QC2-HASH-V1\0qc2.owner.access.v1\0", "utf8")
  .update(TOKEN, "utf8")
  .digest("hex");

let server: Server;
let baseUrl: string;
let binding: {
  sessionRecordId: string;
  environmentNamespace: string;
  scopeRefs: string[];
} | null;
let page: OwnerReadPage;
let pageError: Error | null;
let detail: OwnerEvidenceDetail | null;
let accessCalls: Array<{ environment: string; tokenHash: string }> = [];
let pageCalls: Array<{
  environmentNamespace: string;
  viewName: OwnerReadView;
  limit: number;
  cursor: ProjectionCursor | null;
}> = [];
let evidenceCalls: string[] = [];
let exportCalls: Array<{ viewName: OwnerReadView; count: number }> = [];
let diagnosticsCalls = 0;

const store: OwnerReadStore = {
  async resolveAccess(environment, tokenHash) {
    accessCalls.push({ environment, tokenHash });
    return tokenHash === TOKEN_HASH ? binding : null;
  },
  async readPage(input) {
    pageCalls.push(input);
    if (pageError) throw pageError;
    return page;
  },
  async readEvidenceDetail(input) {
    evidenceCalls.push(input.itemId);
    return detail;
  },
  async diagnostics() {
    diagnosticsCalls += 1;
    return { schema_name: "qc2.owner_api.OwnerReadDiagnostics.v1", views: [] };
  },
  async recordExport(input) {
    exportCalls.push({ viewName: input.viewName, count: input.itemCount });
  },
};

function resetState(): void {
  binding = {
    sessionRecordId: "018f0000-0000-7000-8000-000000000001",
    environmentNamespace: "test",
    scopeRefs: ["OWNER_READ"],
  };
  page = {
    projection_sequence: 1,
    source_sequence: 1,
    source_highwater_sequence: 1,
    lag: 0,
    stale: false,
    data_state: "CURRENT",
    built_at: "2026-10-09T16:00:00Z",
    freshness_deadline: "2026-10-09T16:05:00Z",
    source_refs: [],
    items: [],
    has_more: false,
  };
  pageError = null;
  detail = null;
  accessCalls = [];
  pageCalls = [];
  evidenceCalls = [];
  exportCalls = [];
  diagnosticsCalls = 0;
}

before(async () => {
  resetState();
  const app = express();
  app.use("/api", healthRouter);
  app.use(
    "/api",
    createOwnerReadRouter({
      getStore: async () => store,
      getEnvironment: () => "test",
      now: () => new Date("2026-10-09T16:00:00Z"),
    }),
  );
  server = app.listen(0);
  await new Promise<void>((resolve, reject) => {
    server.once("listening", resolve);
    server.once("error", reject);
  });
  const address = server.address();
  assert(address && typeof address !== "string");
  baseUrl = `http://127.0.0.1:${address.port}`;
});

after(async () => {
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
});

async function request(path: string, token: string | null = TOKEN): Promise<Response> {
  const headers = token ? { authorization: `Bearer ${token}` } : undefined;
  return fetch(`${baseUrl}${path}`, { headers });
}

test("public liveness stays minimal and independent of owner access", async () => {
  const response = await request("/api/healthz", null);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
  assert.equal(accessCalls.length, 0);
  assert.equal(pageCalls.length, 0);
});

test("every owner view requires an authenticated OWNER_READ session", async () => {
  const unauthorized = await request("/api/owner/v1?view=predictions", null);
  assert.equal(unauthorized.status, 401);
  assert.equal(pageCalls.length, 0);

  binding = { ...binding!, scopeRefs: ["DEVICE_ADMIN"] };
  const forbidden = await request("/api/owner/v1?view=predictions");
  assert.equal(forbidden.status, 403);
  assert.equal(pageCalls.length, 0);

  binding = { ...binding!, environmentNamespace: "production" };
  const wrongEnvironment = await request("/api/owner/v1?view=predictions");
  assert.equal(wrongEnvironment.status, 403);
  assert.equal(pageCalls.length, 0);
  resetState();
});

test("owner view query parameters are bounded and a valid read is no-store", async () => {
  const invalid = await request("/api/owner/v1?view=predictions&view=models");
  assert.equal(invalid.status, 400);
  assert.equal(pageCalls.length, 0);

  const hugeQuery = await request(
    `/api/owner/v1?view=predictions&unused=${"x".repeat(8200)}`,
  );
  assert.equal(hugeQuery.status, 400);
  assert.equal(pageCalls.length, 0);

  const response = await request("/api/owner/v1?view=predictions&limit=10");
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(pageCalls.length, 1);
  assert.deepEqual(pageCalls[0], {
    environmentNamespace: "test",
    viewName: "predictions",
    limit: 10,
    cursor: null,
  });
  assert.equal(accessCalls[0]?.tokenHash, TOKEN_HASH);
  assert.deepEqual(await response.json(), {
    schema_name: "qc2.owner_api.OwnerReadPage.v1",
    schema_version: "1.0",
    environment_namespace: "test",
    view_name: "predictions",
    projection_sequence: 1,
    source_sequence: 1,
    source_highwater_sequence: 1,
    lag: 0,
    stale: false,
    data_state: "CURRENT",
    built_at: "2026-10-09T16:00:00Z",
    freshness_deadline: "2026-10-09T16:05:00Z",
    source_refs: [],
    items: [],
    next_cursor: null,
  });

  page.items = [
    {
      item_id: "item-0001",
      sort_key: "0001",
      source_sequence: 1,
      source_ref: {},
      payload: {},
      receipt_hash: "a".repeat(64),
    },
    {
      item_id: "item-0002",
      sort_key: "0002",
      source_sequence: 1,
      source_ref: {},
      payload: {},
      receipt_hash: "b".repeat(64),
    },
  ];
  const unboundedStorePage = await request(
    "/api/owner/v1?view=predictions&limit=1",
  );
  assert.equal(unboundedStorePage.status, 503);
  resetState();
});

test("cursors stay bound to their view and projection sequence", async () => {
  page = {
    ...page,
    items: [
      {
        item_id: "item-0001",
        sort_key: "0001",
        source_sequence: 1,
        source_ref: {},
        payload: {},
        receipt_hash: "a".repeat(64),
      },
    ],
    has_more: true,
  };
  const first = await request("/api/owner/v1?view=predictions&limit=1");
  assert.equal(first.status, 200);
  const body = await first.json();
  const cursor = body.next_cursor as string;
  const cursorBody = JSON.parse(Buffer.from(cursor, "base64url").toString("utf8"));
  assert.equal(cursorBody.view_name, "predictions");
  assert.equal(cursorBody.projection_sequence, 1);

  const second = await request(
    `/api/owner/v1?view=predictions&limit=1&cursor=${encodeURIComponent(cursor)}`,
  );
  assert.equal(second.status, 200);
  assert.deepEqual(pageCalls[1]?.cursor, {
    projectionSequence: 1,
    sortKey: "0001",
    itemId: "item-0001",
  });
  resetState();
});

test("invalid and expired cursors are rejected without leaking database details", async () => {
  const invalid = await request("/api/owner/v1?view=predictions&cursor=%21%21%21");
  assert.equal(invalid.status, 400);
  assert.equal(pageCalls.length, 0);

  const expiredCursor = Buffer.from(
    JSON.stringify({
      item_id: "item-0001",
      projection_sequence: 1,
      sort_key: "0001",
      version: 1,
      view_name: "predictions",
    }),
    "utf8",
  ).toString("base64url");
  pageError = new Error("owner_read_cursor_expired");
  const expired = await request(
    `/api/owner/v1?view=predictions&cursor=${expiredCursor}`,
  );
  assert.equal(expired.status, 409);
  assert.match(await expired.text(), /cursor_expired/);
  resetState();

  pageError = new Error("postgres://private-user:private-password@host/db");
  const failed = await request("/api/owner/v1?view=predictions");
  assert.equal(failed.status, 503);
  const body = await failed.text();
  assert.equal(body.includes("private-password"), false);
  assert.match(body, /owner_read_unavailable/);
  resetState();
});

test("evidence detail is authenticated and accepts only one bounded item id", async () => {
  const unauthorized = await request(
    "/api/owner/v1/evidence/detail?item_id=evidence-1",
    null,
  );
  assert.equal(unauthorized.status, 401);
  assert.equal(evidenceCalls.length, 0);

  const duplicate = await request(
    "/api/owner/v1/evidence/detail?item_id=evidence-1&item_id=evidence-2",
  );
  assert.equal(duplicate.status, 400);
  assert.equal(evidenceCalls.length, 0);

  detail = {
    projection_sequence: 4,
    item: {
      item_id: "evidence-1",
      sort_key: "0001",
      source_sequence: 12,
      source_ref: { target_schema_name: "qc2.integrity_build.EvidenceEvent.v1" },
      payload: { evidence_type: "PREDICTION_SEAL" },
      receipt_hash: "a".repeat(64),
    },
  };
  const response = await request(
    "/api/owner/v1/evidence/detail?item_id=evidence-1",
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(evidenceCalls, ["evidence-1"]);
  assert.equal((await response.json()).projection_sequence, 4);

  const invalidId = await request(
    "/api/owner/v1/evidence/detail?item_id=%2Fetc%2Fpasswd",
  );
  assert.equal(invalidId.status, 400);
  resetState();
});

test("exports reject partial or oversized output and audit successful exports", async () => {
  page.has_more = true;
  const partial = await request("/api/owner/v1/export?view=reports&limit=10");
  assert.equal(partial.status, 413);
  assert.equal(exportCalls.length, 0);

  page.has_more = false;
  page.items = [
    {
      item_id: "large-1",
      sort_key: "0001",
      source_sequence: 1,
      source_ref: {},
      payload: {},
      receipt_hash: "a".repeat(64),
    },
    {
      item_id: "large-2",
      sort_key: "0002",
      source_sequence: 1,
      source_ref: {},
      payload: {},
      receipt_hash: "b".repeat(64),
    },
  ];
  const overCount = await request("/api/owner/v1/export?view=reports&limit=1");
  assert.equal(overCount.status, 413);
  assert.equal(exportCalls.length, 0);

  page.has_more = false;
  page.items = [
    {
      item_id: "large",
      sort_key: "0001",
      source_sequence: 1,
      source_ref: {},
      payload: { content: "x".repeat(1_048_576) },
      receipt_hash: "a".repeat(64),
    },
  ];
  const tooLarge = await request("/api/owner/v1/export?view=reports&limit=10");
  assert.equal(tooLarge.status, 413);
  assert.equal(exportCalls.length, 0);
  resetState();

  page.has_more = false;
  const complete = await request("/api/owner/v1/export?view=reports&limit=10");
  assert.equal(complete.status, 200);
  assert.equal(complete.headers.get("cache-control"), "no-store");
  assert.deepEqual(exportCalls, [{ viewName: "reports", count: 0 }]);
  assert.deepEqual(pageCalls[0], {
    environmentNamespace: "test",
    viewName: "reports",
    limit: 10,
    cursor: null,
  });
  resetState();
});

test("owner diagnostics stay private", async () => {
  const unauthorized = await request("/api/owner/v1/diagnostics", null);
  assert.equal(unauthorized.status, 401);
  assert.equal(diagnosticsCalls, 0);

  const authorized = await request("/api/owner/v1/diagnostics");
  assert.equal(authorized.status, 200);
  assert.equal(diagnosticsCalls, 1);
  resetState();
});

test("PostgreSQL pages read has_more from the function envelope", async () => {
  const database: OwnerReadQueryPort = {
    async query(statement, values) {
      assert.match(statement, /owner_projection_page/);
      assert.deepEqual(values, ["test", "predictions", 1, null, null, null]);
      return {
        rows: [
          {
            result: {
              status: "OK",
              page: {
                projection_sequence: 1,
                source_sequence: 1,
                source_highwater_sequence: 1,
                lag: 0,
                stale: false,
                data_state: "CURRENT",
                built_at: "2026-10-09T16:00:00Z",
                freshness_deadline: "2026-10-09T16:05:00Z",
                source_refs: [],
                items: [],
              },
              has_more: true,
            },
          },
        ],
      };
    },
  };
  const store = new PostgresOwnerReadStore(database);
  const result = await store.readPage({
    environmentNamespace: "test",
    viewName: "predictions",
    limit: 1,
    cursor: null,
  });
  assert.equal(result?.has_more, true);
});

test("owner access checks use the separate identity-authority database", async () => {
  const ownerApiDatabase: OwnerReadQueryPort = {
    async query() {
      assert.fail("owner projection database must not resolve identity");
      return { rows: [] };
    },
  };
  const identityDatabase: OwnerReadQueryPort = {
    async query(statement, values) {
      assert.match(statement, /identity_resolve_access/);
      assert.deepEqual(values, [
        "test",
        "a".repeat(64),
        "2026-10-09T17:00:00.000Z",
      ]);
      return {
        rows: [
          {
            result: {
              status: "VALID",
              session_record: {
                id: "018f0000-0000-7000-8000-000000000001",
                environment_namespace: "test",
                scope_refs: ["OWNER_READ"],
              },
            },
          },
        ],
      };
    },
  };

  const store = new PostgresOwnerReadStore(
    ownerApiDatabase,
    identityDatabase,
  );
  const result = await store.resolveAccess(
    "test",
    "a".repeat(64),
    new Date("2026-10-09T17:00:00.000Z"),
  );
  assert.deepEqual(result, {
    sessionRecordId: "018f0000-0000-7000-8000-000000000001",
    environmentNamespace: "test",
    scopeRefs: ["OWNER_READ"],
  });
});
