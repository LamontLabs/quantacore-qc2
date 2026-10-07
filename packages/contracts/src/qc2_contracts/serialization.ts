export type CanonicalJson =
  | null
  | boolean
  | number
  | string
  | CanonicalJson[]
  | { [key: string]: CanonicalJson };

export interface ArtifactFileRecord {
  relative_path: string;
  length_bytes: number;
  media_type: string;
  schema_name: string;
  schema_version: string;
  sha256: string;
}

export const SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS = [
  "session_id",
  "reference_kind",
  "reference_price",
  "instrument_ref",
  "horizon_label_refs",
  "head_output_refs",
  "dependency_refs",
  "score",
  "rank",
  "disposition",
  "model_hash",
  "epoch_ref",
  "regime",
] as const;

const encoder = new TextEncoder();
const HASH_PREFIX = encoder.encode("QC2-HASH-V1\0");
const DOMAIN_PATTERN = /^[a-z0-9][a-z0-9._/-]{0,127}$/;
const DECIMAL_PATTERN = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;
const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER;

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
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  const commonLength = Math.min(leftBytes.length, rightBytes.length);
  for (let index = 0; index < commonLength; index += 1) {
    if (leftBytes[index] !== rightBytes[index]) {
      return leftBytes[index] - rightBytes[index];
    }
  }
  return leftBytes.length - rightBytes.length;
}

function canonicalText(value: unknown): string {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw new TypeError("Canonical JSON numbers must be exactly representable safe integers");
    }
    return String(value);
  }
  if (typeof value === "string") {
    return JSON.stringify(normalizedString(value));
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalText(item)).join(",")}]`;
  }
  if (typeof value === "object" && value !== null) {
    const normalizedEntries = new Map<string, unknown>();
    for (const [key, item] of Object.entries(value)) {
      const normalizedKey = normalizedString(key);
      if (normalizedEntries.has(normalizedKey)) {
        throw new TypeError("Unicode normalization creates duplicate object keys");
      }
      normalizedEntries.set(normalizedKey, item);
    }
    const keys = [...normalizedEntries.keys()].sort(compareUtf8);
    return `{${keys
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonicalText(normalizedEntries.get(key))}`,
      )
      .join(",")}}`;
  }
  throw new TypeError("Unsupported canonical JSON value");
}

export function canonicalJsonText(value: CanonicalJson): string {
  return canonicalText(value);
}

export function canonicalJsonBytes(value: CanonicalJson): Uint8Array {
  return encoder.encode(canonicalJsonText(value));
}

export function canonicalDecimalText(value: string, precision?: number): string {
  if (typeof value !== "string" || !DECIMAL_PATTERN.test(value)) {
    throw new TypeError(
      "Canonical decimals must use plain base-10 notation without exponent or locale formatting",
    );
  }
  if (
    precision !== undefined &&
    (!Number.isInteger(precision) || precision < 0)
  ) {
    throw new TypeError("Decimal precision must be a nonnegative integer");
  }
  const places = value.includes(".") ? value.length - value.indexOf(".") - 1 : 0;
  if (precision !== undefined && places !== precision) {
    throw new TypeError(`Decimal value must have exactly ${precision} fractional places`);
  }
  if (value.startsWith("-") && !/[1-9]/.test(value)) return value.slice(1);
  return value;
}

export async function domainSeparatedSha256(
  domain: string,
  payload: Uint8Array,
): Promise<string> {
  if (!DOMAIN_PATTERN.test(domain)) {
    throw new TypeError("Hash domain must be a lowercase ASCII identifier");
  }
  if (!(payload instanceof Uint8Array)) {
    throw new TypeError("Hash payload must be bytes");
  }
  const domainBytes = encoder.encode(domain);
  const preimage = new Uint8Array(
    HASH_PREFIX.length + domainBytes.length + 1 + payload.length,
  );
  preimage.set(HASH_PREFIX);
  preimage.set(domainBytes, HASH_PREFIX.length);
  preimage[HASH_PREFIX.length + domainBytes.length] = 0;
  preimage.set(payload, HASH_PREFIX.length + domainBytes.length + 1);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", preimage);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function scientificPredictionPayload(
  value: Record<string, CanonicalJson>,
): Record<string, CanonicalJson> {
  const projected: Record<string, CanonicalJson> = {};
  for (const field of SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(value, field)) {
      throw new TypeError(`ScientificPredictionPayload is missing ${field}`);
    }
    projected[field] = value[field];
  }
  projected.reference_price = canonicalDecimalText(
    String(projected.reference_price),
  );
  projected.score = canonicalDecimalText(String(projected.score), 6);
  return projected;
}

export async function scientificPredictionPayloadHash(
  value: Record<string, CanonicalJson>,
): Promise<string> {
  const projected = scientificPredictionPayload(value);
  return domainSeparatedSha256(
    "qc2.contract-content.v1/qc2.models_prediction.scientificpredictionpayload.v1/1.0",
    canonicalJsonBytes(projected),
  );
}

export async function artifactInventoryHash(
  files: readonly ArtifactFileRecord[],
): Promise<string> {
  const seenPaths = new Set<string>();
  const normalizedFiles = files.map((file) => {
    const path = normalizedString(file.relative_path);
    const declaredFields = [
      "relative_path",
      "length_bytes",
      "media_type",
      "schema_name",
      "schema_version",
      "sha256",
    ];
    if (
      Object.keys(file).length !== declaredFields.length ||
      Object.keys(file).some((field) => !declaredFields.includes(field))
    ) {
      throw new TypeError("Artifact inventory entry has undeclared fields");
    }
    if (
      path.startsWith("/") ||
      /^[A-Za-z]:/.test(path) ||
      path.includes("\\") ||
      path.split("/").some((part) => part === "" || part === "." || part === "..")
    ) {
      throw new TypeError("Artifact paths must be normalized relative paths");
    }
    if (seenPaths.has(path)) {
      throw new TypeError("Artifact paths must be unique after Unicode normalization");
    }
    seenPaths.add(path);
    if (
      !Number.isSafeInteger(file.length_bytes) ||
      file.length_bytes < 0 ||
      typeof file.media_type !== "string" ||
      typeof file.schema_name !== "string" ||
      typeof file.schema_version !== "string" ||
      !/^[0-9a-f]{64}$/.test(file.sha256)
    ) {
      throw new TypeError("Artifact inventory entry is invalid");
    }
    return {
      relative_path: path,
      length_bytes: file.length_bytes,
      media_type: file.media_type,
      schema_name: file.schema_name,
      schema_version: file.schema_version,
      sha256: file.sha256,
    };
  });
  normalizedFiles.sort((left, right) =>
    compareUtf8(left.relative_path, right.relative_path),
  );
  return domainSeparatedSha256(
    "qc2.artifact-inventory.v1",
    canonicalJsonBytes(normalizedFiles as unknown as CanonicalJson),
  );
}

export async function artifactManifestContentHash(
  value: Record<string, CanonicalJson>,
): Promise<string> {
  const schemaName = "qc2.integrity_build.ArtifactManifest.v1";
  const schemaVersion = "1.0";
  if (value.schema_name !== schemaName || value.schema_version !== schemaVersion) {
    throw new TypeError("ArtifactManifest schema identity is invalid");
  }
  const requiredFields = [
    "owning_authority",
    "evidence_class",
    "environment_namespace",
    "source_refs",
    "manifest_version",
    "inventory_hash",
    "files",
  ];
  if (requiredFields.some((field) => !Object.prototype.hasOwnProperty.call(value, field))) {
    throw new TypeError("ArtifactManifest is missing a content field");
  }
  const rawFiles = value.files;
  if (!Array.isArray(rawFiles)) {
    throw new TypeError("ArtifactManifest files must be an array");
  }
  const files = rawFiles as unknown as ArtifactFileRecord[];
  const inventoryHash = value.inventory_hash;
  if (typeof inventoryHash !== "string") {
    throw new TypeError("ArtifactManifest inventory_hash must be a string");
  }
  if ((await artifactInventoryHash(files)) !== inventoryHash) {
    throw new TypeError("ArtifactManifest inventory_hash does not match its files");
  }
  const orderedFiles = [...files].sort((left, right) =>
    compareUtf8(
      normalizedString(left.relative_path),
      normalizedString(right.relative_path),
    ),
  );
  const content: CanonicalJson = {
    owning_authority: value.owning_authority,
    evidence_class: value.evidence_class,
    environment_namespace: value.environment_namespace,
    source_refs: value.source_refs,
    manifest_version: value.manifest_version,
    inventory_hash: inventoryHash,
    files: orderedFiles as unknown as CanonicalJson,
  };
  return domainSeparatedSha256(
    "qc2.contract-content.v1/qc2.integrity_build.artifactmanifest.v1/1.0",
    canonicalJsonBytes(content),
  );
}

