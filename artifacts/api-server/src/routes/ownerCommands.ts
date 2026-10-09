import {
  createHash,
  createPublicKey,
  randomBytes,
  verify,
} from "node:crypto";
import { Router, type IRouter, type Request, type Response } from "express";
import {
  CommitOwnerCommandBody,
  CommitOwnerCommandResponse,
  IssueOwnerCommandChallengeBody,
  IssueOwnerCommandChallengeResponse,
} from "@workspace/api-zod";
import {
  COMMAND_SCOPE_BY_TYPE,
  COMMAND_SIGNING_PREFIX,
  COMMAND_TYPE_BY_KIND,
  OWNER_COMMAND_KINDS,
  canonicalJsonBytes,
  isIdempotencyKey,
  isUuid7,
  ownerCommandBodyHash,
  ownerCommandContentHash,
  validateOwnerCommandRequest,
  type OwnerCommand,
  type OwnerCommandChallenge,
  type OwnerCommandKind,
  type OwnerCommandRequestBody,
} from "../lib/ownerCommandContracts";
import {
  PostgresOwnerCommandStore,
  type OwnerCommandStore,
  type ResolvedOwnerIdentity,
} from "../lib/ownerCommandStore";

const ACCESS_TOKEN_DOMAIN = "qc2.owner.access.v1";
const ENVIRONMENTS = new Set(["development", "test", "research", "production"]);
const MAX_BODY_BYTES = 8192;
const BASE64URL = /^[A-Za-z0-9_-]+$/;
const KIND_SET = new Set<string>(OWNER_COMMAND_KINDS);

interface OwnerCommandRequest extends Request {
  ownerIdentity?: ResolvedOwnerIdentity;
}

interface RouterDependencies {
  getStore: () => Promise<OwnerCommandStore>;
  getEnvironment: () => string | undefined;
  getChallengeTtlSeconds: () => number | undefined;
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

function exactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const keys = Object.keys(value);
  return (
    keys.length === expected.length &&
    expected.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}

function fail(response: Response, status: number, code: string): void {
  response.setHeader("Cache-Control", "no-store");
  response.status(status).json({
    error: {
      code,
      message:
        status >= 500
          ? "The owner command service is temporarily unavailable."
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

function uuid7(now: Date): string {
  const bytes = randomBytes(16);
  const milliseconds = BigInt(now.getTime());
  bytes[0] = Number((milliseconds >> 40n) & 0xffn);
  bytes[1] = Number((milliseconds >> 32n) & 0xffn);
  bytes[2] = Number((milliseconds >> 24n) & 0xffn);
  bytes[3] = Number((milliseconds >> 16n) & 0xffn);
  bytes[4] = Number((milliseconds >> 8n) & 0xffn);
  bytes[5] = Number(milliseconds & 0xffn);
  bytes[6] = (bytes[6] & 0x0f) | 0x70;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function parseTime(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function identityIsCurrent(
  identity: ResolvedOwnerIdentity,
  environment: string,
  requiredScope: string,
  now: Date,
): boolean {
  const { deviceRecord: device, sessionRecord: session } = identity;
  const issuedAt = parseTime(session.issued_at);
  const expiresAt = parseTime(session.expires_at);
  return (
    device.environment_namespace === environment &&
    session.environment_namespace === environment &&
    device.revocation_state === "ENROLLED" &&
    device.revoked_at === null &&
    session.revoked_at === null &&
    session.device_ref.target_id === device.id &&
    issuedAt !== null &&
    expiresAt !== null &&
    issuedAt <= now.getTime() &&
    now.getTime() < expiresAt &&
    Array.isArray(session.scope_refs) &&
    session.scope_refs.includes(requiredScope) &&
    (environment === "test" || session.evidence_class !== "SYNTHETIC_FIXTURE")
  );
}

function publicKeyDer(identity: ResolvedOwnerIdentity): Buffer | null {
  const encoded = identity.deviceRecord.public_key;
  if (
    typeof encoded !== "string" ||
    encoded.length === 0 ||
    encoded.length > 2048 ||
    !BASE64URL.test(encoded)
  ) {
    return null;
  }
  const decoded = Buffer.from(encoded, "base64url");
  if (decoded.toString("base64url") !== encoded) return null;
  return decoded;
}

function makeChallenge(
  input: {
    environment: string;
    commandType: string;
    idempotencyKey: string;
    bodyHash: string;
    identity: ResolvedOwnerIdentity;
    now: Date;
    ttlSeconds: number;
  },
): OwnerCommandChallenge {
  const device = input.identity.deviceRecord;
  const session = input.identity.sessionRecord;
  const der = publicKeyDer(input.identity);
  if (!der) throw new Error("invalid_owner_device_key");
  return {
    schema_name: "qc2.owner_api.OwnerSignedCommandChallenge.v1",
    schema_version: "1.0",
    environment_namespace: input.environment,
    id: uuid7(input.now),
    command_id: `cmd-${uuid7(input.now).replaceAll("-", "")}`,
    command_type: input.commandType,
    idempotency_key: input.idempotencyKey,
    request_body_hash: input.bodyHash,
    device_ref: {
      target_schema_name: "qc2.governance_owner.OwnerDevice.v1",
      target_id: device.id,
    },
    session_ref: {
      target_schema_name: "qc2.governance_owner.OwnerSession.v1",
      target_id: session.id,
    },
    owner_key_id: device.owner_key_id,
    public_key_fingerprint: createHash("sha256").update(der).digest("hex"),
    scope: COMMAND_SCOPE_BY_TYPE[input.commandType],
    nonce: `n${randomBytes(32).toString("hex")}`,
    issued_at: input.now.toISOString(),
    expires_at: new Date(
      input.now.getTime() + input.ttlSeconds * 1000,
    ).toISOString(),
  };
}

function commandContentHash(command: OwnerCommand): string {
  return ownerCommandContentHash(command);
}

function evidenceClass(environment: string): string {
  return environment === "test" ? "SYNTHETIC_FIXTURE" : "FORWARD_OPERATIONAL";
}

function parseSignature(value: unknown): Buffer | null {
  if (
    typeof value !== "string" ||
    value.length > 256 ||
    !BASE64URL.test(value)
  ) {
    return null;
  }
  const decoded = Buffer.from(value, "base64url");
  if (
    decoded.toString("base64url") !== value ||
    decoded.length < 8 ||
    decoded.length > 128
  ) {
    return null;
  }
  return decoded;
}

function isValidReceipt(
  value: Record<string, unknown>,
  environment: string,
  commandId: string,
): boolean {
  const commandRef = value.command_ref;
  return (
    value.schema_name === "qc2.governance_owner.OwnerCommandReceipt.v1" &&
    value.schema_version === "1.0" &&
    isUuid7(value.id) &&
    value.owning_authority === "owner_api" &&
    value.environment_namespace === environment &&
    value.state === "ACCEPTED" &&
    value.resulting_evidence_ref === null &&
    Number.isSafeInteger(value.source_sequence) &&
    (value.source_sequence as number) > 0 &&
    Number.isSafeInteger(value.projection_lag_ms) &&
    (value.projection_lag_ms as number) >= 0 &&
    typeof value.created_at === "string" &&
    typeof value.received_at === "string" &&
    isRecord(commandRef) &&
    commandRef.target_schema_name === "qc2.governance_owner.OwnerCommand.v1" &&
    commandRef.target_id === commandId &&
    typeof commandRef.content_hash === "string" &&
    /^[0-9a-f]{64}$/.test(commandRef.content_hash)
  );
}

function mapDatabaseError(error: unknown): {
  status: number;
  code: string;
} {
  const code =
    error !== null && typeof error === "object" && "code" in error
      ? String((error as { code?: unknown }).code)
      : "";
  if (code === "23505") return { status: 409, code: "idempotency_conflict" };
  if (code === "55000") return { status: 410, code: "challenge_expired_or_consumed" };
  if (code === "42501") return { status: 403, code: "command_not_authorized" };
  if (code === "23514") return { status: 400, code: "invalid_command" };
  return { status: 503, code: "owner_command_unavailable" };
}

export function createOwnerCommandsRouter(
  dependencies: RouterDependencies,
): IRouter {
  const router: IRouter = Router();
  const now = dependencies.now ?? (() => new Date());

  const resolveOwner = async (
    request: OwnerCommandRequest,
    response: Response,
    requiredScope: string,
  ): Promise<{ store: OwnerCommandStore; environment: string } | null> => {
    const environment = dependencies.getEnvironment();
    if (!environment || !ENVIRONMENTS.has(environment)) {
      fail(response, 503, "owner_command_unavailable");
      return null;
    }
    const token = readBearerToken(request);
    if (!token || Buffer.byteLength(token, "utf8") < 32) {
      fail(response, 401, "unauthorized");
      return null;
    }
    try {
      const store = await dependencies.getStore();
      const identity = await store.resolveAccess(
        environment,
        tokenDigest(token),
        now(),
      );
      if (!identity) {
        fail(response, 401, "unauthorized");
        return null;
      }
      if (!identityIsCurrent(identity, environment, requiredScope, now())) {
        const hasScope = identity.sessionRecord.scope_refs.includes(requiredScope);
        fail(response, hasScope ? 401 : 403, hasScope ? "identity_revoked" : "forbidden");
        return null;
      }
      request.ownerIdentity = identity;
      return { store, environment };
    } catch {
      request.log?.warn({ requestId: request.id }, "owner command access verification failed");
      fail(response, 503, "owner_command_unavailable");
      return null;
    }
  };

  const routeKind = (value: string | string[] | undefined): OwnerCommandKind | null =>
    typeof value === "string" && KIND_SET.has(value)
      ? (value as OwnerCommandKind)
      : null;

  router.post(
    "/owner/commands/:kind/challenges",
    async (request: OwnerCommandRequest, response: Response) => {
      const kind = routeKind(request.params.kind);
      if (!kind) {
        fail(response, 404, "not_found");
        return;
      }
      const commandType = COMMAND_TYPE_BY_KIND[kind];
      const scope = COMMAND_SCOPE_BY_TYPE[commandType];
      const resolved = await resolveOwner(request, response, scope);
      if (!resolved) return;

      const ttlSeconds = dependencies.getChallengeTtlSeconds();
      if (
        !Number.isInteger(ttlSeconds) ||
        (ttlSeconds as number) < 1 ||
        (ttlSeconds as number) > 300
      ) {
        fail(response, 503, "owner_command_policy_unavailable");
        return;
      }
      if (
        !isRecord(request.body) ||
        !exactKeys(request.body, ["idempotency_key", "request_body"]) ||
        !isIdempotencyKey(request.body.idempotency_key)
      ) {
        fail(response, 400, "invalid_command_request");
        return;
      }
      const parsedInput = IssueOwnerCommandChallengeBody.safeParse(request.body);
      if (!parsedInput.success) {
        fail(response, 400, "invalid_command_request");
        return;
      }
      const requestBody = validateOwnerCommandRequest(
        commandType,
        request.body.request_body,
      );
      if (!requestBody) {
        fail(response, 400, "invalid_command_request");
        return;
      }
      let requestBytes: Buffer;
      try {
        requestBytes = canonicalJsonBytes(requestBody);
      } catch {
        fail(response, 400, "invalid_command_request");
        return;
      }
      if (requestBytes.length > MAX_BODY_BYTES) {
        fail(response, 413, "command_request_too_large");
        return;
      }

      const requestTime = now();
      if (!identityIsCurrent(request.ownerIdentity!, resolved.environment, scope, requestTime)) {
        fail(response, 401, "identity_revoked");
        return;
      }
      const bodyHash = ownerCommandBodyHash(requestBody);
      const challenge = makeChallenge({
        environment: resolved.environment,
        commandType,
        idempotencyKey: parsedInput.data.idempotency_key,
        bodyHash,
        identity: request.ownerIdentity!,
        now: requestTime,
        ttlSeconds: ttlSeconds as number,
      });
      const signingBytes = Buffer.concat([
        COMMAND_SIGNING_PREFIX,
        canonicalJsonBytes(challenge),
      ]);

      try {
        await resolved.store.storeChallenge(resolved.environment, challenge, {
          device_id: request.ownerIdentity!.deviceRecord.id,
          session_record_id: request.ownerIdentity!.sessionRecord.id,
          session_id: request.ownerIdentity!.sessionRecord.session_id,
          request_body_hash: bodyHash,
        });
      } catch {
        fail(response, 503, "owner_command_unavailable");
        return;
      }
      const challengeResponse = {
        challenge,
        signing_bytes_base64url: signingBytes.toString("base64url"),
      };
      if (!IssueOwnerCommandChallengeResponse.safeParse(challengeResponse).success) {
        fail(response, 503, "owner_command_unavailable");
        return;
      }
      response.setHeader("Cache-Control", "no-store");
      response.status(201).json(challengeResponse);
    },
  );

  router.post(
    "/owner/commands/:kind/commit",
    async (request: OwnerCommandRequest, response: Response) => {
      const kind = routeKind(request.params.kind);
      if (!kind) {
        fail(response, 404, "not_found");
        return;
      }
      const commandType = COMMAND_TYPE_BY_KIND[kind];
      const scope = COMMAND_SCOPE_BY_TYPE[commandType];
      const resolved = await resolveOwner(request, response, scope);
      if (!resolved) return;

      if (
        !isRecord(request.body) ||
        !exactKeys(request.body, ["challenge_id", "request_body", "signature"]) ||
        !isUuid7(request.body.challenge_id)
      ) {
        fail(response, 400, "invalid_command_request");
        return;
      }
      const parsedInput = CommitOwnerCommandBody.safeParse(request.body);
      if (!parsedInput.success) {
        fail(response, 400, "invalid_command_request");
        return;
      }
      const requestBody = validateOwnerCommandRequest(
        commandType,
        request.body.request_body,
      );
      const signature = parseSignature(parsedInput.data.signature);
      if (!requestBody || !signature) {
        fail(response, 400, "invalid_command_request");
        return;
      }
      const bodyHash = ownerCommandBodyHash(requestBody);
      let requestBytes: Buffer;
      try {
        requestBytes = canonicalJsonBytes(requestBody);
      } catch {
        fail(response, 400, "invalid_command_request");
        return;
      }
      if (requestBytes.length > MAX_BODY_BYTES) {
        fail(response, 413, "command_request_too_large");
        return;
      }

      let stored;
      try {
        stored = await resolved.store.getChallenge(
          resolved.environment,
          parsedInput.data.challenge_id,
        );
      } catch {
        fail(response, 503, "owner_command_unavailable");
        return;
      }
      if (!stored) {
        fail(response, 404, "challenge_not_found");
        return;
      }
      const challenge = stored.challenge;
      const requestTime = now();
      if (Date.parse(challenge.expires_at) <= requestTime.getTime()) {
        fail(response, 410, "challenge_expired");
        return;
      }
      if (
        challenge.command_type !== commandType ||
        challenge.scope !== scope ||
        challenge.environment_namespace !== resolved.environment ||
        challenge.request_body_hash !== bodyHash ||
        stored.binding.request_body_hash !== bodyHash ||
        stored.binding.device_id !== request.ownerIdentity!.deviceRecord.id ||
        stored.binding.session_record_id !== request.ownerIdentity!.sessionRecord.id ||
        challenge.device_ref.target_id !== request.ownerIdentity!.deviceRecord.id ||
        challenge.session_ref.target_id !== request.ownerIdentity!.sessionRecord.id ||
        challenge.public_key_fingerprint !==
          createHash("sha256")
            .update(publicKeyDer(request.ownerIdentity!) ?? Buffer.alloc(0))
            .digest("hex")
      ) {
        fail(response, 409, "challenge_binding_mismatch");
        return;
      }

      const der = publicKeyDer(request.ownerIdentity!);
      if (!der || request.ownerIdentity!.deviceRecord.signing_algorithm !== "ECDSA_P256_SHA256") {
        fail(response, 403, "invalid_signing_key");
        return;
      }
      const signingBytes = Buffer.concat([
        COMMAND_SIGNING_PREFIX,
        canonicalJsonBytes(challenge),
      ]);
      let signatureValid = false;
      try {
        const key = createPublicKey({
          key: der,
          format: "der",
          type: "spki",
        });
        signatureValid = verify("sha256", signingBytes, key, signature);
      } catch {
        signatureValid = false;
      }
      if (!signatureValid) {
        fail(response, 403, "invalid_signature");
        return;
      }

      const command: OwnerCommand = {
        schema_name: "qc2.governance_owner.OwnerCommand.v1",
        schema_version: "1.0",
        id: uuid7(requestTime),
        created_at: requestTime.toISOString(),
        owning_authority: "owner_api",
        evidence_class: evidenceClass(resolved.environment),
        environment_namespace: resolved.environment,
        source_refs: [],
        content_hash: "0".repeat(64),
        command_id: challenge.command_id,
        command_type: challenge.command_type,
        idempotency_key: challenge.idempotency_key,
        request_body_hash: challenge.request_body_hash,
        issued_at: challenge.issued_at,
        device_ref: challenge.device_ref,
        signature: signature.toString("base64url"),
        scope: challenge.scope,
      };
      command.content_hash = commandContentHash(command);
      const targetDeviceId =
        commandType === "DEVICE_ACTION"
          ? String(requestBody.payload.device_id)
          : null;

      try {
        const result = await resolved.store.commitSignedCommand({
          environmentNamespace: resolved.environment,
          challengeId: challenge.id,
          ownerCommand: command,
          requestBody: requestBody as unknown as Record<string, unknown>,
          targetDeviceId,
          receiptId: uuid7(requestTime),
          now: requestTime,
        });
        const commitResponse = {
          status: "ACCEPTED",
          receipt: result.receipt,
        };
        if (
          !isValidReceipt(
            result.receipt,
            resolved.environment,
            result.owner_command.id,
          ) ||
          !CommitOwnerCommandResponse.safeParse(commitResponse).success
        ) {
          throw new Error("invalid_owner_command_receipt");
        }
        response.setHeader("Cache-Control", "no-store");
        response.status(202).json(commitResponse);
      } catch (error) {
        const mapped = mapDatabaseError(error);
        if (mapped.status < 500) {
          fail(response, mapped.status, mapped.code);
        } else {
          request.log?.warn(
            { requestId: request.id },
            "owner command commit failed",
          );
          fail(response, mapped.status, mapped.code);
        }
      }
    },
  );

  return router;
}

let productionStore: Promise<OwnerCommandStore> | undefined;

async function getProductionStore(): Promise<OwnerCommandStore> {
  productionStore ??= import("../lib/identityAuthorityDatabase").then(
    ({ identityAuthorityDatabase }) =>
      new PostgresOwnerCommandStore(identityAuthorityDatabase),
  );
  return productionStore;
}

const ownerCommandsRouter = createOwnerCommandsRouter({
  getStore: getProductionStore,
  getEnvironment: () => process.env.QC2_ENV,
  getChallengeTtlSeconds: () => {
    const raw = process.env.QC2_OWNER_COMMAND_CHALLENGE_TTL_SECONDS;
    if (!raw || !/^[1-9][0-9]{0,2}$/.test(raw)) return undefined;
    return Number(raw);
  },
});

export default ownerCommandsRouter;
