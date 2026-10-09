export const OWNER_READ_VIEWS = [
  "today",
  "predictions",
  "validation",
  "models",
  "system",
  "positions",
  "alerts",
  "reports",
  "evidence",
] as const;

export type OwnerReadView = (typeof OWNER_READ_VIEWS)[number];

export interface OwnerSessionBinding {
  sessionRecordId: string;
  environmentNamespace: string;
  scopeRefs: string[];
}

export interface ProjectionCursor {
  projectionSequence: number;
  sortKey: string;
  itemId: string;
}

export interface OwnerReadPage {
  projection_sequence: number;
  source_sequence: number;
  source_highwater_sequence: number;
  lag: number;
  stale: boolean;
  data_state: "CURRENT" | "STALE" | "EMPTY";
  built_at: string;
  freshness_deadline: string;
  source_refs: unknown[];
  items: Array<{
    item_id: string;
    sort_key: string;
    source_sequence: number;
    source_ref: unknown;
    payload: Record<string, unknown>;
    receipt_hash: string;
  }>;
  has_more: boolean;
}

export interface OwnerEvidenceDetail {
  projection_sequence: number;
  item: OwnerReadPage["items"][number];
}

interface QueryResult {
  rows: Array<{ result: unknown }>;
}

export interface OwnerReadQueryPort {
  query(statement: string, values?: unknown[]): Promise<QueryResult>;
}

export interface OwnerReadStore {
  resolveAccess(
    environmentNamespace: string,
    accessTokenHash: string,
    now: Date,
  ): Promise<OwnerSessionBinding | null>;
  readPage(input: {
    environmentNamespace: string;
    viewName: OwnerReadView;
    limit: number;
    cursor: ProjectionCursor | null;
  }): Promise<OwnerReadPage | null>;
  readEvidenceDetail(input: {
    environmentNamespace: string;
    itemId: string;
  }): Promise<OwnerEvidenceDetail | null>;
  diagnostics(environmentNamespace: string): Promise<unknown>;
  recordExport(input: {
    environmentNamespace: string;
    sessionRecordId: string;
    viewName: OwnerReadView;
    projectionSequence: number;
    itemCount: number;
    responseBytes: number;
  }): Promise<void>;
}

function parseJsonResult(value: unknown): Record<string, unknown> | null {
  let parsed = value;
  if (typeof parsed === "string") {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return null;
    }
  }
  return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
    ? (parsed as Record<string, unknown>)
    : null;
}

function requiredString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error("invalid_owner_read_database_result");
  }
  return value;
}

export class PostgresOwnerReadStore implements OwnerReadStore {
  constructor(private readonly database: OwnerReadQueryPort) {}

  async resolveAccess(
    environmentNamespace: string,
    accessTokenHash: string,
    now: Date,
  ): Promise<OwnerSessionBinding | null> {
    const { rows } = await this.database.query(
      `SELECT qc2_governance_owner.identity_resolve_access(
        $1::text, $2::text, $3::timestamptz
      ) AS result`,
      [environmentNamespace, accessTokenHash, now.toISOString()],
    );
    const result = parseJsonResult(rows[0]?.result);
    if (result?.status !== "VALID") return null;
    const session = parseJsonResult(result.session_record);
    if (!session || !Array.isArray(session.scope_refs)) return null;
    const scopeRefs = session.scope_refs.filter(
      (scope): scope is string => typeof scope === "string",
    );
    if (scopeRefs.length !== session.scope_refs.length) return null;
    return {
      sessionRecordId: requiredString(session, "id"),
      environmentNamespace: requiredString(session, "environment_namespace"),
      scopeRefs,
    };
  }

  async readPage(input: {
    environmentNamespace: string;
    viewName: OwnerReadView;
    limit: number;
    cursor: ProjectionCursor | null;
  }): Promise<OwnerReadPage | null> {
    const { rows } = await this.database.query(
      `SELECT qc2_owner_api.owner_projection_page(
        $1::text, $2::text, $3::integer, $4::text, $5::text, $6::bigint
      ) AS result`,
      [
        input.environmentNamespace,
        input.viewName,
        input.limit,
        input.cursor?.sortKey ?? null,
        input.cursor?.itemId ?? null,
        input.cursor?.projectionSequence ?? null,
      ],
    );
    const result = parseJsonResult(rows[0]?.result);
    if (result?.status === "UNAVAILABLE") return null;
    if (result?.status !== "OK") {
      const code =
        result?.status === "CURSOR_EXPIRED"
          ? "owner_read_cursor_expired"
          : "owner_read_projection_unavailable";
      throw new Error(code);
    }
    const page = parseJsonResult(result.page);
    if (
      !page ||
      !Array.isArray(page.items) ||
      !Array.isArray(page.source_refs) ||
      typeof result.has_more !== "boolean"
    ) {
      throw new Error("invalid_owner_read_database_result");
    }
    const items = page.items.map((value) => {
      const item = parseJsonResult(value);
      if (
        !item ||
        typeof item.item_id !== "string" ||
        typeof item.sort_key !== "string" ||
        typeof item.source_sequence !== "number" ||
        typeof item.receipt_hash !== "string" ||
        item.payload === null ||
        typeof item.payload !== "object" ||
        Array.isArray(item.payload)
      ) {
        throw new Error("invalid_owner_read_database_result");
      }
      return {
        item_id: item.item_id,
        sort_key: item.sort_key,
        source_sequence: item.source_sequence,
        source_ref: item.source_ref,
        payload: item.payload as Record<string, unknown>,
        receipt_hash: item.receipt_hash,
      };
    });
    const integerField = (key: string): number => {
      const value = page[key];
      if (!Number.isSafeInteger(value) || (value as number) < 0) {
        throw new Error("invalid_owner_read_database_result");
      }
      return value as number;
    };
    if (
      typeof page.stale !== "boolean" ||
      !["CURRENT", "STALE", "EMPTY"].includes(String(page.data_state)) ||
      typeof page.built_at !== "string" ||
      typeof page.freshness_deadline !== "string"
    ) {
      throw new Error("invalid_owner_read_database_result");
    }
    return {
      projection_sequence: integerField("projection_sequence"),
      source_sequence: integerField("source_sequence"),
      source_highwater_sequence: integerField("source_highwater_sequence"),
      lag: integerField("lag"),
      stale: page.stale,
      data_state: page.data_state as OwnerReadPage["data_state"],
      built_at: page.built_at,
      freshness_deadline: page.freshness_deadline,
      source_refs: page.source_refs,
      items,
      has_more: result.has_more,
    };
  }

  async diagnostics(environmentNamespace: string): Promise<unknown> {
    const { rows } = await this.database.query(
      `SELECT qc2_owner_api.owner_projection_diagnostics($1::text) AS result`,
      [environmentNamespace],
    );
    const result = parseJsonResult(rows[0]?.result);
    if (result?.status !== "OK") {
      throw new Error("owner_read_diagnostics_unavailable");
    }
    return result.diagnostics;
  }

  async readEvidenceDetail(input: {
    environmentNamespace: string;
    itemId: string;
  }): Promise<OwnerEvidenceDetail | null> {
    const { rows } = await this.database.query(
      `SELECT qc2_owner_api.owner_projection_evidence_detail(
        $1::text, $2::text
      ) AS result`,
      [input.environmentNamespace, input.itemId],
    );
    const result = parseJsonResult(rows[0]?.result);
    if (result?.status === "NOT_FOUND") return null;
    if (result?.status !== "FOUND") {
      throw new Error("owner_evidence_projection_unavailable");
    }
    const item = parseJsonResult(result.item);
    const projectionSequence = result.projection_sequence;
    if (
      !item ||
      !Number.isSafeInteger(projectionSequence) ||
      (projectionSequence as number) < 1 ||
      typeof item.item_id !== "string" ||
      typeof item.sort_key !== "string" ||
      typeof item.source_sequence !== "number" ||
      typeof item.receipt_hash !== "string" ||
      item.payload === null ||
      typeof item.payload !== "object" ||
      Array.isArray(item.payload)
    ) {
      throw new Error("invalid_owner_read_database_result");
    }
    return {
      projection_sequence: projectionSequence as number,
      item: {
        item_id: item.item_id,
        sort_key: item.sort_key,
        source_sequence: item.source_sequence,
        source_ref: item.source_ref,
        payload: item.payload as Record<string, unknown>,
        receipt_hash: item.receipt_hash,
      },
    };
  }

  async recordExport(input: {
    environmentNamespace: string;
    sessionRecordId: string;
    viewName: OwnerReadView;
    projectionSequence: number;
    itemCount: number;
    responseBytes: number;
  }): Promise<void> {
    await this.database.query(
      `SELECT qc2_owner_api.owner_projection_record_export(
        $1::text, $2::uuid, $3::text, $4::bigint, $5::integer, $6::integer
      ) AS result`,
      [
        input.environmentNamespace,
        input.sessionRecordId,
        input.viewName,
        input.projectionSequence,
        input.itemCount,
        input.responseBytes,
      ],
    );
  }
}
