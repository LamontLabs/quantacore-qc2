const assert = require("node:assert/strict");
const fs = require("node:fs");
const { TextDecoder } = require("node:util");

const [modulePath, vectorPath] = process.argv.slice(2);
const {
  artifactInventoryHash,
  artifactManifestContentHash,
  canonicalDecimalText,
  canonicalJsonBytes,
  domainSeparatedSha256,
  scientificPredictionPayloadHash,
} = require(modulePath);

function properties(path) {
  const result = {};
  for (const line of fs.readFileSync(path, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const separator = trimmed.indexOf("=");
    result[trimmed.slice(0, separator)] = trimmed.slice(separator + 1);
  }
  return result;
}

function artifactFiles(values) {
  return Array.from({ length: Number(values["artifact.count"]) }, (_, index) => {
    const key = `artifact.${index}.`;
    return {
      relative_path: values[`${key}relative_path`],
      length_bytes: Number(values[`${key}length_bytes`]),
      media_type: values[`${key}media_type`],
      schema_name: values[`${key}schema_name`],
      schema_version: values[`${key}schema_version`],
      sha256: values[`${key}sha256`],
    };
  });
}

function artifactManifest(values, files) {
  return {
    schema_name: "qc2.integrity_build.ArtifactManifest.v1",
    schema_version: "1.0",
    id: values["artifact.manifest_id"],
    created_at: values["artifact.manifest_created_at"],
    owning_authority: values["artifact.manifest_authority"],
    evidence_class: values["artifact.manifest_evidence_class"],
    environment_namespace: values["artifact.manifest_environment_namespace"],
    source_refs: [],
    content_hash: "a".repeat(64),
    files,
    inventory_hash: values["artifact.expected_hash"],
    manifest_version: Number(values["artifact.manifest_version"]),
    detached_signature: values["artifact.manifest_signature"],
    transport_hash: values["artifact.manifest_transport_hash"],
  };
}

function reference(values, prefix, includeHash = false) {
  const result = {
    target_schema_name: values[`${prefix}_schema`],
    target_id: values[`${prefix}_id`],
  };
  if (includeHash) result.content_hash = values[`${prefix}_hash`];
  return result;
}

function scientificPayload(values) {
  return {
    schema_name: "qc2.models_prediction.ScientificPredictionPayload.v1",
    schema_version: "1.0",
    id: values["scientific.envelope_id"],
    created_at: values["scientific.envelope_created_at"],
    owning_authority: "prediction",
    evidence_class: "SYNTHETIC_FIXTURE",
    environment_namespace: "test",
    source_refs: [],
    content_hash: "a".repeat(64),
    session_id: values["scientific.session_id"],
    reference_kind: values["scientific.reference_kind"],
    reference_price: values["scientific.reference_price"],
    instrument_ref: reference(values, "scientific.instrument"),
    horizon_label_refs: [reference(values, "scientific.horizon", true)],
    head_output_refs: [reference(values, "scientific.head")],
    dependency_refs: [reference(values, "scientific.dependency", true)],
    score: values["scientific.score"],
    rank: Number(values["scientific.rank"]),
    disposition: values["scientific.disposition"],
    model_hash: values["scientific.model_hash"],
    epoch_ref: reference(values, "scientific.epoch", true),
    regime: values["scientific.regime"],
  };
}

async function main() {
  const values = properties(vectorPath);
  const nfd = new TextDecoder().decode(
    Uint8Array.from(Buffer.from(values["canonical.value_base64"], "base64")),
  );
  const canonical = canonicalJsonBytes({ z: nfd, a: [true, null, 7] });
  const canonicalHex = Buffer.from(canonical).toString("hex");
  assert.equal(canonicalHex, values["canonical.expected_bytes_hex"]);
  assert.equal(
    await domainSeparatedSha256(values["canonical.domain"], canonical),
    values["canonical.expected_hash"],
  );
  assert.equal(
    Buffer.from(canonicalJsonBytes({ "\ue000": 1, "\u{10000}": 2 })).toString("hex"),
    "7b22ee8080223a312c22f0908080223a327d",
  );
  const controlValue = new TextDecoder().decode(
    Uint8Array.from(Buffer.from(values["canonical.control_value_base64"], "base64")),
  );
  assert.equal(
    Buffer.from(canonicalJsonBytes(controlValue)).toString("hex"),
    values["canonical.control_expected_hex"],
  );
  assert.throws(() => canonicalJsonBytes({ "é": 1, "e\u0301": 2 }));
  assert.throws(() => canonicalJsonBytes({ value: Number.NaN }));
  assert.throws(() => canonicalJsonBytes({ value: 1.5 }));
  assert.throws(() => canonicalJsonBytes({ value: Number.MAX_SAFE_INTEGER + 1 }));
  assert.notEqual(
    await domainSeparatedSha256("qc2.golden.other.v1", canonical),
    values["canonical.expected_hash"],
  );

  assert.equal(
    canonicalDecimalText(
      values["decimal.negative_zero"],
      Number(values["decimal.fixed_precision"]),
    ),
    values["decimal.expected_zero"],
  );
  assert.equal(
    canonicalDecimalText(values["decimal.trailing_zero_input"]),
    values["decimal.trailing_zero_expected"],
  );

  const files = artifactFiles(values);
  assert.equal(await artifactInventoryHash(files), values["artifact.expected_hash"]);
  assert.equal(
    await artifactInventoryHash([...files].reverse()),
    values["artifact.expected_hash"],
  );
  await assert.rejects(() =>
    artifactInventoryHash([{ ...files[0], relative_path: "C:/private/model.bin" }]),
  );
  await assert.rejects(() =>
    artifactInventoryHash([
      { ...files[0], relative_path: "models/e\u0301.bin" },
      { ...files[1], relative_path: "models/é.bin" },
    ]),
  );
  const manifest = artifactManifest(values, files);
  assert.equal(
    await artifactManifestContentHash(manifest),
    values["artifact.manifest_expected_hash"],
  );
  const changedManifestEnvelope = {
    ...manifest,
    id: "018f0000-0000-7000-8000-000000000030",
    created_at: "2026-10-07T12:00:00Z",
    content_hash: "f".repeat(64),
    detached_signature: "Ag",
    transport_hash: "c".repeat(64),
  };
  assert.equal(
    await artifactManifestContentHash(changedManifestEnvelope),
    values["artifact.manifest_expected_hash"],
  );

  const scientific = scientificPayload(values);
  const scientificHash = await scientificPredictionPayloadHash(scientific);
  assert.equal(scientificHash, values["scientific.expected_hash"]);
  scientific.id = "018f0000-0000-7000-8000-000000000010";
  scientific.created_at = "2026-10-07T11:00:00Z";
  scientific.source_refs = [{ trace_id: "replay-2" }];
  assert.equal(
    await scientificPredictionPayloadHash(scientific),
    values["scientific.expected_hash"],
  );
  scientific.score = "50.000001";
  assert.notEqual(
    await scientificPredictionPayloadHash(scientific),
    values["scientific.expected_hash"],
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
