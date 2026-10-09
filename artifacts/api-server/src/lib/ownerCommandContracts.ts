import { createHash } from "node:crypto";

export const OWNER_COMMAND_KINDS = [
  "promotion-decision",
  "epoch-activation-decision",
  "entry-pause",
  "resume-request",
  "alert-acknowledgment",
  "device-management",
] as const;

export type OwnerCommandKind = (typeof OWNER_COMMAND_KINDS)[number];

export const COMMAND_TYPE_BY_KIND: Record<OwnerCommandKind, string> = {
  "promotion-decision": "PROMOTION",
  "epoch-activation-decision": "EPOCH_ACTIVATION",
  "entry-pause": "PAUSE_NEW_ENTRIES",
  "resume-request": "RESUME_REQUEST",
  "alert-acknowledgment": "ACKNOWLEDGE_ALERT",
  "device-management": "DEVICE_ACTION",
};

export const COMMAND_SCOPE_BY_TYPE: Record<string, string> = {
  PROMOTION: "PROMOTION",
  EPOCH_ACTIVATION: "EPOCH_ACTIVATION",
  PAUSE_NEW_ENTRIES: "PAUSE",
  RESUME_REQUEST: "RESUME",
  ACKNOWLEDGE_ALERT: "ALERT",
  DEVICE_ACTION: "DEVICE_ADMIN",
};

export const COMMAND_SIGNING_PREFIX = Buffer.from(
  "QC2_OWNER_SIGNED_COMMAND_V1\0",
  "utf8",
);

export interface OwnerCommandRequestBody {
  schema_name: "qc2.owner_api.OwnerCommandRequest.v1";
  schema_version: "1.0";
  command_type: string;
  payload: Record<string, unknown>;
}

export interface TypedReference {
  target_schema_name: string;
  target_id: string;
  content_hash?: string;
}

export interface OwnerDeviceRecord {
  id: string;
  environment_namespace: string;
  owner_key_id: string;
  public_key: string;
  signing_algorithm: string;
  revocation_state: string;
  revoked_at: string | null;
}

export interface OwnerSessionRecord {
  id: string;
  environment_namespace: string;
  device_ref: TypedReference;
  session_id: string;
  issued_at: string;
  expires_at: string;
  revoked_at: string | null;
  scope_refs: string[];
  evidence_class: string;
}

export interface OwnerCommandChallenge {
  schema_name: "qc2.owner_api.OwnerSignedCommandChallenge.v1";
  schema_version: "1.0";
  environment_namespace: string;
  id: string;
  command_id: string;
  command_type: string;
  idempotency_key: string;
  request_body_hash: string;
  device_ref: TypedReference;
  session_ref: TypedReference;
  owner_key_id: string;
  public_key_fingerprint: string;
  scope: string;
  nonce: string;
  issued_at: string;
  expires_at: string;
}

export interface OwnerCommand {
  schema_name: "qc2.governance_owner.OwnerCommand.v1";
  schema_version: "1.0";
  id: string;
  created_at: string;
  owning_authority: "owner_api";
  evidence_class: string;
  environment_namespace: string;
  source_refs: unknown[];
  content_hash: string;
  command_id: string;
  command_type: string;
  idempotency_key: string;
  request_body_hash: string;
  issued_at: string;
  device_ref: TypedReference;
  signature: string;
  scope: string;
}

const UUID7 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const SLUG = /^[a-z][a-z0-9_-]{0,95}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const keys = Object.keys(value);
  return (
    keys.length === expected.length &&
    expected.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}

function validUuid7(value: unknown): value is string {
  return typeof value === "string" && UUID7.test(value);
}

function validHash(value: unknown): value is string {
  return typeof value === "string" && SHA256.test(value);
}

function validNonnegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0;
}

function validPositiveInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) > 0;
}

function validReference(
  value: unknown,
  schemaName: string,
  contentAddressed: boolean,
): value is TypedReference {
  if (!isRecord(value)) return false;
  const keys = contentAddressed
    ? ["target_schema_name", "target_id", "content_hash"]
    : ["target_schema_name", "target_id"];
  return (
    hasExactKeys(value, keys) &&
    value.target_schema_name === schemaName &&
    validUuid7(value.target_id) &&
    (!contentAddressed || validHash(value.content_hash))
  );
}

export function validateOwnerCommandRequest(
  commandType: string,
  value: unknown,
): OwnerCommandRequestBody | null {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["schema_name", "schema_version", "command_type", "payload"]) ||
    value.schema_name !== "qc2.owner_api.OwnerCommandRequest.v1" ||
    value.schema_version !== "1.0" ||
    value.command_type !== commandType ||
    !isRecord(value.payload)
  ) {
    return null;
  }

  const payload = value.payload;
  let valid = false;
  switch (commandType) {
    case "PROMOTION":
      valid =
        hasExactKeys(payload, ["challenge_ref", "decision", "request_hash"]) &&
        validReference(
          payload.challenge_ref,
          "qc2.governance_owner.PromotionChallenge.v1",
          true,
        ) &&
        typeof payload.decision === "string" &&
        ["APPROVE", "HOLD", "REJECT"].includes(payload.decision) &&
        validHash(payload.request_hash);
      break;
    case "EPOCH_ACTIVATION":
      valid =
        hasExactKeys(payload, [
          "challenge_ref",
          "epoch_manifest_hash",
          "decision",
        ]) &&
        validReference(
          payload.challenge_ref,
          "qc2.governance_owner.EpochActivationChallenge.v1",
          true,
        ) &&
        typeof payload.decision === "string" &&
        ["APPROVE", "REJECT"].includes(payload.decision) &&
        validHash(payload.epoch_manifest_hash);
      break;
    case "PAUSE_NEW_ENTRIES":
      valid =
        hasExactKeys(payload, ["expected_generation", "reason_code"]) &&
        validNonnegativeInteger(payload.expected_generation) &&
        typeof payload.reason_code === "string" &&
        SLUG.test(payload.reason_code);
      break;
    case "RESUME_REQUEST":
      valid =
        hasExactKeys(payload, ["expected_pause_generation"]) &&
        validPositiveInteger(payload.expected_pause_generation);
      break;
    case "ACKNOWLEDGE_ALERT":
      valid =
        hasExactKeys(payload, ["alert_ref", "expected_projection_sequence"]) &&
        validReference(
          payload.alert_ref,
          "qc2.governance_owner.Alert.v1",
          false,
        ) &&
        validPositiveInteger(payload.expected_projection_sequence);
      break;
    case "DEVICE_ACTION":
      valid =
        hasExactKeys(payload, ["action", "device_id"]) &&
        payload.action === "REVOKE_DEVICE" &&
        validUuid7(payload.device_id);
      break;
    default:
      return null;
  }

  return valid ? (value as unknown as OwnerCommandRequestBody) : null;
}

function assertUnicodeScalars(value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw new TypeError("Canonical strings must contain valid Unicode scalar values");
      }
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      throw new TypeError("Canonical strings must contain valid Unicode scalar values");
    }
  }
}

function normalizedString(value: string): string {
  const normalized = value.normalize("NFC");
  assertUnicodeScalars(normalized);
  return normalized;
}

function compareUtf8(left: string, right: string): number {
  return Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));
}

function canonicalText(value: unknown): string {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw new TypeError("Canonical JSON numbers must be safe integers");
    }
    return String(value);
  }
  if (typeof value === "string") {
    return JSON.stringify(normalizedString(value));
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalText).join(",")}]`;
  }
  if (isRecord(value)) {
    const normalized = new Map<string, unknown>();
    for (const [key, item] of Object.entries(value)) {
      const normalizedKey = normalizedString(key);
      if (normalized.has(normalizedKey)) {
        throw new TypeError("Unicode normalization creates duplicate object keys");
      }
      normalized.set(normalizedKey, item);
    }
    const keys = [...normalized.keys()].sort(compareUtf8);
    return `{${keys
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonicalText(normalized.get(key))}`,
      )
      .join(",")}}`;
  }
  throw new TypeError("Unsupported canonical JSON value");
}

export function canonicalJsonBytes(value: unknown): Buffer {
  return Buffer.from(canonicalText(value), "utf8");
}

export function domainSeparatedSha256(domain: string, payload: Buffer): string {
  if (!/^[a-z0-9][a-z0-9._/-]{0,127}$/.test(domain)) {
    throw new TypeError("Invalid QC2 hash domain");
  }
  return createHash("sha256")
    .update(`QC2-HASH-V1\0${domain}\0`, "utf8")
    .update(payload)
    .digest("hex");
}

export function ownerCommandBodyHash(body: OwnerCommandRequestBody): string {
  return domainSeparatedSha256(
    "qc2.owner.command-body.v1",
    canonicalJsonBytes(body),
  );
}

const OWNER_COMMAND_HASH_FIELDS = [
  "owning_authority",
  "evidence_class",
  "environment_namespace",
  "source_refs",
  "command_id",
  "command_type",
  "idempotency_key",
  "request_body_hash",
  "issued_at",
  "device_ref",
  "signature",
  "scope",
] as const;

export function ownerCommandContentHash(command: OwnerCommand): string {
  const content: Record<string, unknown> = {};
  for (const field of OWNER_COMMAND_HASH_FIELDS) {
    content[field] = command[field];
  }
  return domainSeparatedSha256(
    "qc2.contract-content.v1/qc2.governance_owner.ownercommand.v1/1.0",
    canonicalJsonBytes(content),
  );
}

export function isUuid7(value: unknown): value is string {
  return validUuid7(value);
}

export function isIdempotencyKey(value: unknown): value is string {
  return typeof value === "string" && SLUG.test(value);
}
