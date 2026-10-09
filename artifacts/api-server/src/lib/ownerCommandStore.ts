import {
  type OwnerCommand,
  type OwnerCommandChallenge,
  type OwnerDeviceRecord,
  type OwnerSessionRecord,
} from "./ownerCommandContracts";

export interface OwnerCommandDatabase {
  query(
    statement: string,
    values?: unknown[],
  ): Promise<{ rows: Array<{ result: unknown }> }>;
}

export interface ResolvedOwnerIdentity {
  deviceRecord: OwnerDeviceRecord;
  sessionRecord: OwnerSessionRecord;
}

export interface StoredOwnerCommandChallenge {
  challenge: OwnerCommandChallenge;
  binding: {
    device_id: string;
    session_record_id: string;
    session_id: string;
    request_body_hash: string;
  };
  consumed: boolean;
}

export interface OwnerCommandCommitResult {
  status: "COMMITTED" | "DUPLICATE";
  owner_command: OwnerCommand;
  receipt: Record<string, unknown>;
}

export interface OwnerCommandStore {
  resolveAccess(
    environmentNamespace: string,
    accessTokenHash: string,
    now: Date,
  ): Promise<ResolvedOwnerIdentity | null>;
  storeChallenge(
    environmentNamespace: string,
    challenge: OwnerCommandChallenge,
    binding: StoredOwnerCommandChallenge["binding"],
  ): Promise<void>;
  getChallenge(
    environmentNamespace: string,
    challengeId: string,
  ): Promise<StoredOwnerCommandChallenge | null>;
  commitSignedCommand(input: {
    environmentNamespace: string;
    challengeId: string;
    ownerCommand: OwnerCommand;
    requestBody: Record<string, unknown>;
    targetDeviceId: string | null;
    receiptId: string;
    now: Date;
  }): Promise<OwnerCommandCommitResult>;
}

function parseRecord(value: unknown): Record<string, unknown> | null {
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

function requiredString(
  record: Record<string, unknown>,
  key: string,
): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error("invalid_owner_command_database_result");
  }
  return value;
}

function parseIdentityRecord(
  value: unknown,
): Record<string, unknown> | null {
  return parseRecord(value);
}

function parseChallengeResult(
  value: unknown,
): StoredOwnerCommandChallenge | null {
  const result = parseRecord(value);
  if (result?.status !== "FOUND") return null;
  const challenge = parseRecord(result.challenge);
  const binding = parseRecord(result.binding);
  if (!challenge || !binding) {
    throw new Error("invalid_owner_command_database_result");
  }
  const challengeRecord = challenge as unknown as OwnerCommandChallenge;
  return {
    challenge: challengeRecord,
    binding: {
      device_id: requiredString(binding, "device_id"),
      session_record_id: requiredString(binding, "session_record_id"),
      session_id: requiredString(binding, "session_id"),
      request_body_hash: requiredString(binding, "request_body_hash"),
    },
    consumed: result.consumed === true,
  };
}

export class PostgresOwnerCommandStore implements OwnerCommandStore {
  constructor(private readonly database: OwnerCommandDatabase) {}

  async resolveAccess(
    environmentNamespace: string,
    accessTokenHash: string,
    now: Date,
  ): Promise<ResolvedOwnerIdentity | null> {
    const { rows } = await this.database.query(
      `SELECT qc2_governance_owner.identity_resolve_access(
        $1::text, $2::text, $3::timestamptz
      ) AS result`,
      [environmentNamespace, accessTokenHash, now.toISOString()],
    );
    const result = parseRecord(rows[0]?.result);
    if (result?.status !== "VALID") return null;
    const deviceRecord = parseIdentityRecord(result.device_record);
    const sessionRecord = parseIdentityRecord(result.session_record);
    if (
      !deviceRecord ||
      !sessionRecord ||
      !Array.isArray(sessionRecord.scope_refs) ||
      !isTypedReference(sessionRecord.device_ref)
    ) {
      throw new Error("invalid_owner_command_database_result");
    }
    return {
      deviceRecord: deviceRecord as unknown as OwnerDeviceRecord,
      sessionRecord: sessionRecord as unknown as OwnerSessionRecord,
    };
  }

  async storeChallenge(
    environmentNamespace: string,
    challenge: OwnerCommandChallenge,
    binding: StoredOwnerCommandChallenge["binding"],
  ): Promise<void> {
    const { rows } = await this.database.query(
      `SELECT qc2_governance_owner.identity_store_command_challenge(
        $1::text, $2::jsonb, $3::jsonb
      ) AS result`,
      [environmentNamespace, JSON.stringify(challenge), JSON.stringify(binding)],
    );
    if (parseRecord(rows[0]?.result)?.status !== "STORED") {
      throw new Error("owner_command_challenge_not_stored");
    }
  }

  async getChallenge(
    environmentNamespace: string,
    challengeId: string,
  ): Promise<StoredOwnerCommandChallenge | null> {
    const { rows } = await this.database.query(
      `SELECT qc2_governance_owner.identity_get_command_challenge(
        $1::text, $2::uuid
      ) AS result`,
      [environmentNamespace, challengeId],
    );
    return parseChallengeResult(rows[0]?.result);
  }

  async commitSignedCommand(input: {
    environmentNamespace: string;
    challengeId: string;
    ownerCommand: OwnerCommand;
    requestBody: Record<string, unknown>;
    targetDeviceId: string | null;
    receiptId: string;
    now: Date;
  }): Promise<OwnerCommandCommitResult> {
    const { rows } = await this.database.query(
      `SELECT qc2_governance_owner.owner_api_commit_signed_command(
        $1::text, $2::uuid, $3::jsonb, $4::jsonb, $5::uuid, $6::uuid,
        $7::timestamptz
      ) AS result`,
      [
        input.environmentNamespace,
        input.challengeId,
        JSON.stringify(input.ownerCommand),
        JSON.stringify(input.requestBody),
        input.targetDeviceId,
        input.receiptId,
        input.now.toISOString(),
      ],
    );
    const result = parseRecord(rows[0]?.result);
    if (
      !result ||
      (result.status !== "COMMITTED" && result.status !== "DUPLICATE")
    ) {
      throw new Error("owner_command_commit_failed");
    }
    const ownerCommand = parseRecord(result.owner_command);
    const receipt = parseRecord(result.receipt);
    if (!ownerCommand || !receipt) {
      throw new Error("invalid_owner_command_database_result");
    }
    return {
      status: result.status,
      owner_command: ownerCommand as unknown as OwnerCommand,
      receipt,
    };
  }
}

function isTypedReference(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
