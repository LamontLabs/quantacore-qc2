package com.quantracore.contracts.v1

import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.text.Normalizer

private const val MAX_SAFE_INTEGER = 9_007_199_254_740_991L
private val DECIMAL_PATTERN = Regex("""-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?""")
private val DOMAIN_PATTERN = Regex("""[a-z0-9][a-z0-9._/-]{0,127}""")

val SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS = listOf(
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
)

private fun normalizedString(value: String): String {
    val normalized = Normalizer.normalize(value, Normalizer.Form.NFC)
    var index = 0
    while (index < normalized.length) {
        val current = normalized[index]
        if (Character.isHighSurrogate(current)) {
            if (index + 1 >= normalized.length || !Character.isLowSurrogate(normalized[index + 1])) {
                throw IllegalArgumentException("Canonical strings must contain valid Unicode scalar values")
            }
            index += 2
        } else {
            if (Character.isLowSurrogate(current)) {
                throw IllegalArgumentException("Canonical strings must contain valid Unicode scalar values")
            }
            index += 1
        }
    }
    return normalized
}

private fun compareUtf8(left: String, right: String): Int {
    val leftBytes = left.toByteArray(StandardCharsets.UTF_8)
    val rightBytes = right.toByteArray(StandardCharsets.UTF_8)
    val commonLength = minOf(leftBytes.size, rightBytes.size)
    for (index in 0 until commonLength) {
        val leftByte = leftBytes[index].toInt() and 0xff
        val rightByte = rightBytes[index].toInt() and 0xff
        if (leftByte != rightByte) return leftByte - rightByte
    }
    return leftBytes.size - rightBytes.size
}

private fun quoteCanonicalString(value: String): String {
    val result = StringBuilder("\"")
    val normalized = normalizedString(value)
    var index = 0
    while (index < normalized.length) {
        val codePoint = normalized.codePointAt(index)
        when (codePoint) {
            0x08 -> result.append("\\b")
            0x09 -> result.append("\\t")
            0x0a -> result.append("\\n")
            0x0c -> result.append("\\f")
            0x0d -> result.append("\\r")
            0x22 -> result.append("\\\"")
            0x5c -> result.append("\\\\")
            else -> if (codePoint < 0x20) {
                result.append("\\u")
                    .append(codePoint.toString(16).padStart(4, '0'))
            } else {
                result.appendCodePoint(codePoint)
            }
        }
        index += Character.charCount(codePoint)
    }
    return result.append('"').toString()
}

private fun canonicalText(value: Any?): String = when (value) {
    null -> "null"
    is Boolean -> if (value) "true" else "false"
    is Byte -> value.toString()
    is Short -> value.toString()
    is Int -> {
        require(value.toLong() in -MAX_SAFE_INTEGER..MAX_SAFE_INTEGER) {
            "Canonical JSON numbers must be exactly representable safe integers"
        }
        value.toString()
    }
    is Long -> {
        require(value in -MAX_SAFE_INTEGER..MAX_SAFE_INTEGER) {
            "Canonical JSON numbers must be exactly representable safe integers"
        }
        value.toString()
    }
    is Float, is Double -> throw IllegalArgumentException("Canonical JSON does not permit binary floats")
    is String -> quoteCanonicalString(value)
    is List<*> -> value.joinToString(separator = ",", prefix = "[", postfix = "]") {
        canonicalText(it)
    }
    is Map<*, *> -> {
        val normalizedEntries = mutableMapOf<String, Any?>()
        for ((rawKey, item) in value) {
            require(rawKey is String) { "Canonical JSON object keys must be strings" }
            val key = normalizedString(rawKey)
            require(!normalizedEntries.containsKey(key)) {
                "Unicode normalization creates duplicate object keys"
            }
            normalizedEntries[key] = item
        }
        normalizedEntries.keys.sortedWith(::compareUtf8).joinToString(
            separator = ",",
            prefix = "{",
            postfix = "}",
        ) { key ->
            "${quoteCanonicalString(key)}:${canonicalText(normalizedEntries[key])}"
        }
    }
    else -> throw IllegalArgumentException("Unsupported canonical JSON value: ${value::class.simpleName}")
}

fun canonicalJsonText(value: Any?): String = canonicalText(value)

fun canonicalJsonBytes(value: Any?): ByteArray =
    canonicalJsonText(value).toByteArray(StandardCharsets.UTF_8)

fun canonicalDecimalText(value: String, precision: Int? = null): String {
    require(DECIMAL_PATTERN.matches(value)) {
        "Canonical decimals must use plain base-10 notation without exponent or locale formatting"
    }
    require(precision == null || precision >= 0) {
        "Decimal precision must be a nonnegative integer"
    }
    val places = value.substringAfter('.', "").length
    if (precision != null) {
        require(places == precision) {
            "Decimal value must have exactly $precision fractional places"
        }
    }
    return if (value.startsWith("-") && !value.removePrefix("-").any { it in '1'..'9' }) {
        value.removePrefix("-")
    } else {
        value
    }
}

fun domainSeparatedSha256(domain: String, payload: ByteArray): String {
    require(DOMAIN_PATTERN.matches(domain)) {
        "Hash domain must be a lowercase ASCII identifier"
    }
    val preimage = "QC2-HASH-V1\u0000$domain\u0000".toByteArray(StandardCharsets.US_ASCII) + payload
    return MessageDigest.getInstance("SHA-256")
        .digest(preimage)
        .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
}

fun scientificPredictionPayload(value: Map<String, Any?>): Map<String, Any?> {
    val projected = linkedMapOf<String, Any?>()
    for (field in SCIENTIFIC_PREDICTION_PAYLOAD_FIELDS) {
        require(value.containsKey(field)) { "ScientificPredictionPayload is missing $field" }
        projected[field] = value[field]
    }
    val referencePrice = projected["reference_price"]
    val score = projected["score"]
    require(referencePrice is String && score is String) {
        "Scientific prediction decimals must be strings"
    }
    projected["reference_price"] = canonicalDecimalText(referencePrice)
    projected["score"] = canonicalDecimalText(score, 6)
    return projected
}

fun scientificPredictionPayloadHash(value: Map<String, Any?>): String =
    domainSeparatedSha256(
        "qc2.contract-content.v1/qc2.models_prediction.scientificpredictionpayload.v1/1.0",
        canonicalJsonBytes(scientificPredictionPayload(value)),
    )

fun artifactInventoryHash(files: List<Map<String, Any?>>): String {
    val seenPaths = mutableSetOf<String>()
    val normalizedFiles = files.map { file ->
        val declaredFields = setOf(
            "relative_path",
            "length_bytes",
            "media_type",
            "schema_name",
            "schema_version",
            "sha256",
        )
        require(file.keys == declaredFields) { "Artifact inventory entry has undeclared fields" }
        val pathValue = file["relative_path"]
        require(pathValue is String) { "Artifact inventory paths must be strings" }
        val path = normalizedString(pathValue)
        require(
            !path.startsWith("/") &&
                !Regex("^[A-Za-z]:").containsMatchIn(path) &&
                '\\' !in path &&
                path.split('/').none { it.isEmpty() || it == "." || it == ".." },
        ) { "Artifact paths must be normalized relative paths" }
        require(seenPaths.add(path)) {
            "Artifact paths must be unique after Unicode normalization"
        }
        val length = when (val rawLength = file["length_bytes"]) {
            is Byte -> rawLength.toLong()
            is Short -> rawLength.toLong()
            is Int -> rawLength.toLong()
            is Long -> rawLength
            else -> throw IllegalArgumentException(
                "Artifact inventory length_bytes must be a nonnegative safe integer",
            )
        }
        require(length in 0..MAX_SAFE_INTEGER) {
            "Artifact inventory length_bytes must be a nonnegative safe integer"
        }
        val mediaType = file["media_type"]
        val schemaName = file["schema_name"]
        val schemaVersion = file["schema_version"]
        val hash = file["sha256"]
        require(mediaType is String && schemaName is String && schemaVersion is String) {
            "Artifact inventory string fields are invalid"
        }
        require(hash is String && Regex("^[0-9a-f]{64}$").matches(hash)) {
            "Artifact inventory SHA-256 is invalid"
        }
        mapOf(
            "relative_path" to path,
            "length_bytes" to length,
            "media_type" to mediaType,
            "schema_name" to schemaName,
            "schema_version" to schemaVersion,
            "sha256" to hash,
        )
    }.sortedWith { left, right ->
        compareUtf8(left.getValue("relative_path") as String, right.getValue("relative_path") as String)
    }
    return domainSeparatedSha256(
        "qc2.artifact-inventory.v1",
        canonicalJsonBytes(normalizedFiles),
    )
}

fun artifactManifestContentHash(value: Map<String, Any?>): String {
    require(value["schema_name"] == "qc2.integrity_build.ArtifactManifest.v1") {
        "ArtifactManifest schema identity is invalid"
    }
    require(value["schema_version"] == "1.0") {
        "ArtifactManifest schema identity is invalid"
    }
    val requiredFields = setOf(
        "owning_authority",
        "evidence_class",
        "environment_namespace",
        "source_refs",
        "manifest_version",
        "inventory_hash",
        "files",
    )
    require(requiredFields.all(value::containsKey)) {
        "ArtifactManifest is missing a content field"
    }
    @Suppress("UNCHECKED_CAST")
    val files = value["files"] as? List<Map<String, Any?>>
        ?: throw IllegalArgumentException("ArtifactManifest files must be an array")
    val inventoryHash = value["inventory_hash"] as? String
        ?: throw IllegalArgumentException("ArtifactManifest inventory_hash must be a string")
    require(artifactInventoryHash(files) == inventoryHash) {
        "ArtifactManifest inventory_hash does not match its files"
    }
    val orderedFiles = files.sortedWith { left, right ->
        compareUtf8(
            normalizedString(left["relative_path"] as String),
            normalizedString(right["relative_path"] as String),
        )
    }
    val content = mapOf(
        "owning_authority" to value["owning_authority"],
        "evidence_class" to value["evidence_class"],
        "environment_namespace" to value["environment_namespace"],
        "source_refs" to value["source_refs"],
        "manifest_version" to value["manifest_version"],
        "inventory_hash" to inventoryHash,
        "files" to orderedFiles,
    )
    return domainSeparatedSha256(
        "qc2.contract-content.v1/qc2.integrity_build.artifactmanifest.v1/1.0",
        canonicalJsonBytes(content),
    )
}
