import { createServer, type Server } from "node:http";
import { generateKeyPairSync, sign, type KeyObject } from "node:crypto";
import express from "express";
import { after, test } from "node:test";
import assert from "node:assert/strict";
import {
  COMMAND_SIGNING_PREFIX,
  canonicalJsonBytes,
  ownerCommandBodyHash,
  type OwnerCommand,
  type OwnerCommandChallenge,
  type OwnerCommandRequestBody,
} from "../src/lib/ownerCommandContracts";
import {
  type OwnerCommandStore,
  type ResolvedOwnerIdentity,
} from "../src/lib/ownerCommandStore";
import { createOwnerCommandsRouter } from "../src/routes/ownerCommands";

const TOKEN = "A".repeat(43);
const NOW = new Date("2026-10-09T18:30:00.000Z");
const DEVICE_ID = "00000000-0000-7000-8000-000000000001";
const SESSION_RECORD_ID = "00000000-0000-7000-8000-000000000002";
const TARGET_DEVICE_ID = "00000000-0000-7000-8000-000000000003";
const REF_ID = "00000000-0000-7000-8000-000000000004";
const HASH = "a".repeat(64);

interface StoredChallenge {
  challenge: OwnerCommandChallenge;
  binding: {
    device_id: string;
    session_record_id: string;
    session_id: string;
    request_body_hash: string;
  };
  consumed: boolean;
}

class FakeOwnerCommandStore implements OwnerCommandStore {
  readonly challenges = new Map<string, StoredChallenge>();
  readonly receipts = new Map<
    string,
    { requestHash: string; commandType: string; receipt: Record<string, unknown>; command: OwnerCommand }
  >();
  readonly identity: ResolvedOwnerIdentity;
  revoked = false;
  sourceSequence = 0;

  constructor(publicKey: string) {
    this.identity = {
      deviceRecord: {
        id: DEVICE_ID,
        environment_namespace: "test",
        owner_key_id: "owner_key",
        public_key: publicKey,
        signing_algorithm: "ECDSA_P256_SHA256",
        revocation_state: "ENROLLED",
        revoked_at: null,
      },
      sessionRecord: {
        id: SESSION_RECORD_ID,
        environment_namespace: "test",
        device_ref: {
          target_schema_name: "qc2.governance_owner.OwnerDevice.v1",
          target_id: DEVICE_ID,
        },
        session_id: `session-${"b".repeat(32)}`,
        issued_at: "2026-10-09T18:00:00.000Z",
        expires_at: "2026-10-09T19:00:00.000Z",
        revoked_at: null,
        scope_refs: [
          "PROMOTION",
          "EPOCH_ACTIVATION",
          "PAUSE",
          "RESUME",
          "ALERT",
          "DEVICE_ADMIN",
        ],
        evidence_class: "SYNTHETIC_FIXTURE",
      },
    };
  }

  async resolveAccess(): Promise<ResolvedOwnerIdentity | null> {
    if (!this.revoked) return this.identity;
    return {
      deviceRecord: {
        ...this.identity.deviceRecord,
        revocation_state: "REVOKED",
        revoked_at: NOW.toISOString(),
      },
      sessionRecord: this.identity.sessionRecord,
    };
  }

  async storeChallenge(
    _environmentNamespace: string,
    challenge: OwnerCommandChallenge,
    binding: StoredChallenge["binding"],
  ): Promise<void> {
    this.challenges.set(challenge.id, {
      challenge,
      binding,
      consumed: false,
    });
  }

  async getChallenge(
    _environmentNamespace: string,
    challengeId: string,
  ): Promise<StoredChallenge | null> {
    return this.challenges.get(challengeId) ?? null;
  }

  async commitSignedCommand(input: {
    environmentNamespace: string;
    challengeId: string;
    ownerCommand: OwnerCommand;
    requestBody: Record<string, unknown>;
    targetDeviceId: string | null;
    receiptId: string;
    now: Date;
  }): Promise<{
    status: "COMMITTED" | "DUPLICATE";
    owner_command: OwnerCommand;
    receipt: Record<string, unknown>;
  }> {
    const stored = this.challenges.get(input.challengeId);
    assert.ok(stored);
    const requestHash = ownerCommandBodyHash(
      input.requestBody as unknown as OwnerCommandRequestBody,
    );
    assert.equal(requestHash, stored.challenge.request_body_hash);
    const idempotencyKey = input.ownerCommand.idempotency_key;
    const prior = this.receipts.get(idempotencyKey);
    if (prior) {
      if (
        prior.requestHash !== requestHash ||
        prior.commandType !== input.ownerCommand.command_type
      ) {
        throw Object.assign(new Error("idempotency conflict"), { code: "23505" });
      }
      stored.consumed = true;
      return {
        status: "DUPLICATE",
        owner_command: prior.command,
        receipt: prior.receipt,
      };
    }
    stored.consumed = true;
    if (
      input.ownerCommand.command_type === "DEVICE_ACTION" &&
      input.targetDeviceId === DEVICE_ID
    ) {
      this.revoked = true;
    }
    this.sourceSequence += 1;
    const receipt: Record<string, unknown> = {
      schema_name: "qc2.governance_owner.OwnerCommandReceipt.v1",
      schema_version: "1.0",
      id: input.receiptId,
      created_at: input.now.toISOString(),
      owning_authority: "owner_api",
      evidence_class: "SYNTHETIC_FIXTURE",
      environment_namespace: input.environmentNamespace,
      source_refs: [],
      command_ref: {
        target_schema_name: "qc2.governance_owner.OwnerCommand.v1",
        target_id: input.ownerCommand.id,
        content_hash: input.ownerCommand.content_hash,
      },
      state: "ACCEPTED",
      resulting_evidence_ref: null,
      source_sequence: this.sourceSequence,
      projection_lag_ms: 0,
      received_at: input.now.toISOString(),
    };
    this.receipts.set(idempotencyKey, {
      requestHash,
      commandType: input.ownerCommand.command_type,
      receipt,
      command: input.ownerCommand,
    });
    return {
      status: "COMMITTED",
      owner_command: input.ownerCommand,
      receipt,
    };
  }
}

interface TestServer {
  server: Server;
  baseUrl: string;
}

async function startServer(
  store: FakeOwnerCommandStore,
  now: () => Date,
): Promise<TestServer> {
  const app = express();
  app.use(express.json());
  app.use(
    createOwnerCommandsRouter({
      getStore: async () => store,
      getEnvironment: () => "test",
      getChallengeTtlSeconds: () => 90,
      now,
    }),
  );
  const server = createServer(app);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  return { server, baseUrl: `http://127.0.0.1:${address.port}` };
}

async function requestJson(
  baseUrl: string,
  path: string,
  body?: unknown,
): Promise<{ status: number; body: Record<string, unknown> }> {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${TOKEN}`,
      ...(body === undefined ? {} : { "content-type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return {
    status: response.status,
    body: (await response.json()) as Record<string, unknown>,
  };
}

function requestBody(
  commandType: string,
  payload: Record<string, unknown>,
): OwnerCommandRequestBody {
  return {
    schema_name: "qc2.owner_api.OwnerCommandRequest.v1",
    schema_version: "1.0",
    command_type: commandType,
    payload,
  };
}

function bodyFor(commandType: string): OwnerCommandRequestBody {
  switch (commandType) {
    case "PROMOTION":
      return requestBody(commandType, {
        challenge_ref: {
          target_schema_name: "qc2.governance_owner.PromotionChallenge.v1",
          target_id: REF_ID,
          content_hash: HASH,
        },
        decision: "APPROVE",
        request_hash: "b".repeat(64),
      });
    case "EPOCH_ACTIVATION":
      return requestBody(commandType, {
        challenge_ref: {
          target_schema_name:
            "qc2.governance_owner.EpochActivationChallenge.v1",
          target_id: REF_ID,
          content_hash: HASH,
        },
        epoch_manifest_hash: "b".repeat(64),
        decision: "APPROVE",
      });
    case "PAUSE_NEW_ENTRIES":
      return requestBody(commandType, {
        expected_generation: 3,
        reason_code: "operator_request",
      });
    case "RESUME_REQUEST":
      return requestBody(commandType, { expected_pause_generation: 3 });
    case "ACKNOWLEDGE_ALERT":
      return requestBody(commandType, {
        alert_ref: {
          target_schema_name: "qc2.governance_owner.Alert.v1",
          target_id: REF_ID,
        },
        expected_projection_sequence: 8,
      });
    case "DEVICE_ACTION":
      return requestBody(commandType, {
        action: "REVOKE_DEVICE",
        device_id: TARGET_DEVICE_ID,
      });
    default:
      throw new Error(`No test request for ${commandType}`);
  }
}

async function issueChallenge(
  baseUrl: string,
  kind: string,
  idempotencyKey: string,
  request: OwnerCommandRequestBody,
): Promise<{
  challenge: OwnerCommandChallenge;
  signingBytes: Buffer;
}> {
  const response = await requestJson(baseUrl, `/owner/commands/${kind}/challenges`, {
    idempotency_key: idempotencyKey,
    request_body: request,
  });
  assert.equal(response.status, 201);
  const challenge = response.body.challenge as OwnerCommandChallenge;
  const signingBytes = Buffer.from(
    String(response.body.signing_bytes_base64url),
    "base64url",
  );
  assert.deepEqual(
    signingBytes,
    Buffer.concat([COMMAND_SIGNING_PREFIX, canonicalJsonBytes(challenge)]),
  );
  return { challenge, signingBytes };
}

async function commit(
  baseUrl: string,
  kind: string,
  challenge: OwnerCommandChallenge,
  request: OwnerCommandRequestBody,
  privateKey: KeyObject,
): Promise<{ status: number; body: Record<string, unknown> }> {
  const signature = sign(
    "sha256",
    Buffer.concat([COMMAND_SIGNING_PREFIX, canonicalJsonBytes(challenge)]),
    privateKey,
  ).toString("base64url");
  return requestJson(baseUrl, `/owner/commands/${kind}/commit`, {
    challenge_id: challenge.id,
    request_body: request,
    signature,
  });
}

const servers: Server[] = [];
after(async () => {
  await Promise.all(
    servers.map(
      (server) =>
        new Promise<void>((resolve, reject) =>
          server.close((error) => (error ? reject(error) : resolve())),
        ),
    ),
  );
});

test("exposes six scoped command families and returns accepted, non-executed receipts", async () => {
  const { publicKey, privateKey } = generateKeyPairSync("ec", {
    namedCurve: "prime256v1",
  });
  const store = new FakeOwnerCommandStore(
    publicKey.export({ type: "spki", format: "der" }).toString("base64url"),
  );
  const { server, baseUrl } = await startServer(store, () => new Date(NOW));
  servers.push(server);

  const cases = [
    ["promotion-decision", "PROMOTION"],
    ["epoch-activation-decision", "EPOCH_ACTIVATION"],
    ["entry-pause", "PAUSE_NEW_ENTRIES"],
    ["resume-request", "RESUME_REQUEST"],
    ["alert-acknowledgment", "ACKNOWLEDGE_ALERT"],
    ["device-management", "DEVICE_ACTION"],
  ] as const;
  for (const [kind, commandType] of cases) {
    const body = bodyFor(commandType);
    const { challenge } = await issueChallenge(
      baseUrl,
      kind,
      `test-${commandType.toLowerCase()}`,
      body,
    );
    const result = await commit(baseUrl, kind, challenge, body, privateKey);
    assert.equal(result.status, 202);
    assert.equal(result.body.status, "ACCEPTED");
    const receipt = result.body.receipt as Record<string, unknown>;
    assert.equal(receipt.state, "ACCEPTED");
    assert.equal(receipt.resulting_evidence_ref, null);
  }
});

test("duplicate taps return one stable receipt; a reused key with changed content is rejected", async () => {
  const { publicKey, privateKey } = generateKeyPairSync("ec", {
    namedCurve: "prime256v1",
  });
  const store = new FakeOwnerCommandStore(
    publicKey.export({ type: "spki", format: "der" }).toString("base64url"),
  );
  const { server, baseUrl } = await startServer(store, () => new Date(NOW));
  servers.push(server);
  const body = bodyFor("PAUSE_NEW_ENTRIES");

  const first = await issueChallenge(baseUrl, "entry-pause", "same-tap", body);
  const firstResponse = await commit(
    baseUrl,
    "entry-pause",
    first.challenge,
    body,
    privateKey,
  );
  const second = await issueChallenge(baseUrl, "entry-pause", "same-tap", body);
  const secondResponse = await commit(
    baseUrl,
    "entry-pause",
    second.challenge,
    body,
    privateKey,
  );
  assert.equal(firstResponse.status, 202);
  assert.equal(secondResponse.status, 202);
  assert.deepEqual(secondResponse.body, firstResponse.body);

  const changedBody = bodyFor("PAUSE_NEW_ENTRIES");
  changedBody.payload.expected_generation = 4;
  const changed = await issueChallenge(
    baseUrl,
    "entry-pause",
    "same-tap",
    changedBody,
  );
  const conflict = await commit(
    baseUrl,
    "entry-pause",
    changed.challenge,
    changedBody,
    privateKey,
  );
  assert.equal(conflict.status, 409);
  assert.equal(
    (conflict.body.error as Record<string, unknown>).code,
    "idempotency_conflict",
  );
});

test("expired, stale, revoked, and invalidly signed requests are denied", async () => {
  const { publicKey, privateKey } = generateKeyPairSync("ec", {
    namedCurve: "prime256v1",
  });
  let now = new Date(NOW);
  const store = new FakeOwnerCommandStore(
    publicKey.export({ type: "spki", format: "der" }).toString("base64url"),
  );
  const { server, baseUrl } = await startServer(store, () => new Date(now));
  servers.push(server);
  const body = bodyFor("PROMOTION");

  const expired = await issueChallenge(
    baseUrl,
    "promotion-decision",
    "expired-command",
    body,
  );
  now = new Date(now.getTime() + 91_000);
  const expiredResponse = await commit(
    baseUrl,
    "promotion-decision",
    expired.challenge,
    body,
    privateKey,
  );
  assert.equal(expiredResponse.status, 410);

  now = new Date(NOW);
  const stale = await issueChallenge(
    baseUrl,
    "promotion-decision",
    "stale-command",
    body,
  );
  const changedBody = bodyFor("PROMOTION");
  changedBody.payload.request_hash = "c".repeat(64);
  const staleResponse = await commit(
    baseUrl,
    "promotion-decision",
    stale.challenge,
    changedBody,
    privateKey,
  );
  assert.equal(staleResponse.status, 409);

  const badSignature = await requestJson(
    baseUrl,
    "/owner/commands/promotion-decision/commit",
    {
      challenge_id: stale.challenge.id,
      request_body: body,
      signature: Buffer.from("invalid-signature").toString("base64url"),
    },
  );
  assert.equal(badSignature.status, 403);

  const revoked = await issueChallenge(
    baseUrl,
    "promotion-decision",
    "revoked-command",
    body,
  );
  store.revoked = true;
  const revokedResponse = await commit(
    baseUrl,
    "promotion-decision",
    revoked.challenge,
    body,
    privateKey,
  );
  assert.equal(revokedResponse.status, 401);
});

test("unsupported routes and privileged payload variants are rejected", async () => {
  const { publicKey } = generateKeyPairSync("ec", {
    namedCurve: "prime256v1",
  });
  const store = new FakeOwnerCommandStore(
    publicKey.export({ type: "spki", format: "der" }).toString("base64url"),
  );
  const { server, baseUrl } = await startServer(store, () => new Date(NOW));
  servers.push(server);

  for (const hiddenKind of [
    "buy",
    "sell",
    "force-promote",
    "scientific-edit",
    "safety-override",
  ]) {
    const response = await requestJson(
      baseUrl,
      `/owner/commands/${hiddenKind}/challenges`,
      {},
    );
    assert.equal(response.status, 404);
  }

  const forcePromotion = bodyFor("PROMOTION");
  forcePromotion.payload.decision = "FORCE_PROMOTE";
  const forceResponse = await requestJson(
    baseUrl,
    "/owner/commands/promotion-decision/challenges",
    { idempotency_key: "force-promotion", request_body: forcePromotion },
  );
  assert.equal(forceResponse.status, 400);

  const safetyOverride = bodyFor("PAUSE_NEW_ENTRIES");
  safetyOverride.payload.safety_override = true;
  const overrideResponse = await requestJson(
    baseUrl,
    "/owner/commands/entry-pause/challenges",
    { idempotency_key: "override-attempt", request_body: safetyOverride },
  );
  assert.equal(overrideResponse.status, 400);
});

test("owner scopes are checked before challenge issuance", async () => {
  const { publicKey } = generateKeyPairSync("ec", {
    namedCurve: "prime256v1",
  });
  const store = new FakeOwnerCommandStore(
    publicKey.export({ type: "spki", format: "der" }).toString("base64url"),
  );
  store.identity.sessionRecord.scope_refs = ["OWNER_READ"];
  const { server, baseUrl } = await startServer(store, () => new Date(NOW));
  servers.push(server);

  const result = await requestJson(
    baseUrl,
    "/owner/commands/epoch-activation-decision/challenges",
    {
      idempotency_key: "unauthorized-epoch",
      request_body: bodyFor("EPOCH_ACTIVATION"),
    },
  );
  assert.equal(result.status, 403);
});
