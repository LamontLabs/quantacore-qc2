package com.quantracore.contracts.v1

import java.io.FileInputStream
import java.util.Base64
import java.util.Properties

private fun reference(
    values: Properties,
    prefix: String,
    includeHash: Boolean = false,
): Map<String, Any?> {
    val result = mutableMapOf<String, Any?>(
        "target_schema_name" to values.getProperty("${prefix}_schema"),
        "target_id" to values.getProperty("${prefix}_id"),
    )
    if (includeHash) result["content_hash"] = values.getProperty("${prefix}_hash")
    return result
}

private fun artifactFiles(values: Properties): List<Map<String, Any?>> =
    (0 until values.getProperty("artifact.count").toInt()).map { index ->
        val prefix = "artifact.$index."
        mapOf(
            "relative_path" to values.getProperty("${prefix}relative_path"),
            "length_bytes" to values.getProperty("${prefix}length_bytes").toLong(),
            "media_type" to values.getProperty("${prefix}media_type"),
            "schema_name" to values.getProperty("${prefix}schema_name"),
            "schema_version" to values.getProperty("${prefix}schema_version"),
            "sha256" to values.getProperty("${prefix}sha256"),
        )
    }

private fun artifactManifest(
    values: Properties,
    files: List<Map<String, Any?>>,
): MutableMap<String, Any?> =
    mutableMapOf(
        "schema_name" to "qc2.integrity_build.ArtifactManifest.v1",
        "schema_version" to "1.0",
        "id" to values.getProperty("artifact.manifest_id"),
        "created_at" to values.getProperty("artifact.manifest_created_at"),
        "owning_authority" to values.getProperty("artifact.manifest_authority"),
        "evidence_class" to values.getProperty("artifact.manifest_evidence_class"),
        "environment_namespace" to values.getProperty("artifact.manifest_environment_namespace"),
        "source_refs" to emptyList<Any?>(),
        "content_hash" to "a".repeat(64),
        "files" to files,
        "inventory_hash" to values.getProperty("artifact.expected_hash"),
        "manifest_version" to values.getProperty("artifact.manifest_version").toInt(),
        "detached_signature" to values.getProperty("artifact.manifest_signature"),
        "transport_hash" to values.getProperty("artifact.manifest_transport_hash"),
    )

private fun scientificPayload(values: Properties): MutableMap<String, Any?> =
    mutableMapOf(
        "schema_name" to "qc2.models_prediction.ScientificPredictionPayload.v1",
        "schema_version" to "1.0",
        "id" to values.getProperty("scientific.envelope_id"),
        "created_at" to values.getProperty("scientific.envelope_created_at"),
        "owning_authority" to "prediction",
        "evidence_class" to "SYNTHETIC_FIXTURE",
        "environment_namespace" to "test",
        "source_refs" to emptyList<Any?>(),
        "content_hash" to "a".repeat(64),
        "session_id" to values.getProperty("scientific.session_id"),
        "reference_kind" to values.getProperty("scientific.reference_kind"),
        "reference_price" to values.getProperty("scientific.reference_price"),
        "instrument_ref" to reference(values, "scientific.instrument"),
        "horizon_label_refs" to listOf(reference(values, "scientific.horizon", true)),
        "head_output_refs" to listOf(reference(values, "scientific.head")),
        "dependency_refs" to listOf(reference(values, "scientific.dependency", true)),
        "score" to values.getProperty("scientific.score"),
        "rank" to values.getProperty("scientific.rank").toInt(),
        "disposition" to values.getProperty("scientific.disposition"),
        "model_hash" to values.getProperty("scientific.model_hash"),
        "epoch_ref" to reference(values, "scientific.epoch", true),
        "regime" to values.getProperty("scientific.regime"),
    )

private fun hex(bytes: ByteArray): String =
    bytes.joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }

fun main(args: Array<String>) {
    require(args.size == 1) { "Pass the shared serialization golden-vector properties file" }
    val values = Properties().apply {
        FileInputStream(args[0]).use(::load)
    }

    val decomposedAccent = String(
        Base64.getDecoder().decode(values.getProperty("canonical.value_base64")),
        Charsets.UTF_8,
    )
    val canonical = canonicalJsonBytes(mapOf("z" to decomposedAccent, "a" to listOf(true, null, 7)))
    check(hex(canonical) == values.getProperty("canonical.expected_bytes_hex"))
    check(
        domainSeparatedSha256(values.getProperty("canonical.domain"), canonical) ==
            values.getProperty("canonical.expected_hash"),
    )
    val supplementaryKey = String(Character.toChars(0x10000))
    val unicodeOrder = canonicalJsonBytes(mapOf("\ue000" to 1, supplementaryKey to 2))
    check(hex(unicodeOrder) == "7b22ee8080223a312c22f0908080223a327d")
    val controlValue = String(
        Base64.getDecoder().decode(values.getProperty("canonical.control_value_base64")),
        Charsets.UTF_8,
    )
    check(hex(canonicalJsonBytes(controlValue)) == values.getProperty("canonical.control_expected_hex"))
    check(runCatching {
        canonicalJsonBytes(mapOf("é" to 1, "e\u0301" to 2))
    }.isFailure)
    check(runCatching { canonicalJsonBytes(mapOf("value" to Double.NaN)) }.isFailure)
    check(runCatching { canonicalJsonBytes(mapOf("value" to 1.5)) }.isFailure)

    check(
        canonicalDecimalText(
            values.getProperty("decimal.negative_zero"),
            values.getProperty("decimal.fixed_precision").toInt(),
        ) == values.getProperty("decimal.expected_zero"),
    )
    check(
        canonicalDecimalText(values.getProperty("decimal.trailing_zero_input")) ==
            values.getProperty("decimal.trailing_zero_expected"),
    )

    val files = artifactFiles(values)
    check(artifactInventoryHash(files) == values.getProperty("artifact.expected_hash"))
    check(artifactInventoryHash(files.reversed()) == values.getProperty("artifact.expected_hash"))
    check(runCatching {
        artifactInventoryHash(listOf(files[0] + ("relative_path" to "C:/private/model.bin")))
    }.isFailure)
    check(runCatching {
        artifactInventoryHash(
            listOf(
                files[0] + ("relative_path" to "models/e\u0301.bin"),
                files[1] + ("relative_path" to "models/é.bin"),
            ),
        )
    }.isFailure)
    val manifest = artifactManifest(values, files)
    val manifestHash = values.getProperty("artifact.manifest_expected_hash")
    check(artifactManifestContentHash(manifest) == manifestHash)
    manifest["id"] = "018f0000-0000-7000-8000-000000000030"
    manifest["created_at"] = "2026-10-07T12:00:00Z"
    manifest["content_hash"] = "f".repeat(64)
    manifest["detached_signature"] = "Ag"
    manifest["transport_hash"] = "c".repeat(64)
    check(artifactManifestContentHash(manifest) == manifestHash)

    val scientific = scientificPayload(values)
    val scientificHash = scientificPredictionPayloadHash(scientific)
    check(scientificHash == values.getProperty("scientific.expected_hash"))
    scientific["id"] = "018f0000-0000-7000-8000-000000000010"
    scientific["created_at"] = "2026-10-07T11:00:00Z"
    scientific["source_refs"] = listOf(mapOf("trace_id" to "replay-2"))
    check(scientificPredictionPayloadHash(scientific) == values.getProperty("scientific.expected_hash"))
    scientific["score"] = "50.000001"
    check(scientificPredictionPayloadHash(scientific) != values.getProperty("scientific.expected_hash"))
}
