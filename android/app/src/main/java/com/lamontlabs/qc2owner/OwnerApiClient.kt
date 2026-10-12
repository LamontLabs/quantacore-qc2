package com.lamontlabs.qc2owner

import org.json.JSONObject
import java.io.BufferedInputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID
import java.util.Base64

internal class OwnerApiException(
    val httpStatus: Int,
    val errorCode: String?,
) : Exception(errorCode ?: "owner_api_http_$httpStatus")

internal class OwnerApiClient(
    private val baseUrl: String,
    private val version: String,
    private val buildIdentity: String,
    private val openConnection: (URL) -> HttpURLConnection = {
        it.openConnection() as HttpURLConnection
    },
) {
    fun enrollWithPairingCode(pairingCode: String): Pair<OwnerSession, String?> {
        require(pairingCode.matches(Regex("^[A-Za-z0-9_-]{43}$"))) {
            "invalid_pairing_code"
        }
        OwnerSigningKey.ensureCreated()
        val challengeResponse = request(
            path = "owner/v1/enrollment/challenges",
            method = "POST",
            body = JSONObject()
                .put("owner_key_id", OWNER_KEY_ID)
                .put("public_key_der_base64url", encodeBase64Url(OwnerSigningKey.publicKeyEncoded()))
                .put("app_version", version),
            headers = mapOf("x-owner-pairing-code" to pairingCode),
        )
        val challenge = challengeResponse.getJSONObject("challenge")
        val signingBytes = decodeBase64Url(
            challengeResponse.getString("signing_bytes_base64url"),
        )
        val completed = request(
            path = "owner/v1/enrollment/complete",
            method = "POST",
            body = JSONObject()
                .put("challenge_id", challenge.getString("challenge_id"))
                .put(
                    "signature_base64url",
                    encodeBase64Url(OwnerSigningKey.sign(signingBytes)),
                ),
            headers = mapOf("x-owner-pairing-code" to pairingCode),
        )
        return parseSession(completed) to optionalRecoveryMaterial(completed)
    }

    fun refreshSession(refreshToken: String): Pair<OwnerSession, String?> {
        val response = request(
            path = "owner/v1/session/refresh",
            method = "POST",
            body = JSONObject().put("refresh_token", refreshToken),
        )
        return parseSession(response) to optionalRecoveryMaterial(response)
    }

    fun readProjection(accessToken: String, view: String): JSONObject {
        require(view in OWNER_VIEWS)
        val encodedView = URLEncoder.encode(view, Charsets.UTF_8.name())
        return request(
            path = "owner/v1?view=$encodedView&limit=100",
            method = "GET",
            accessToken = accessToken,
        )
    }

    fun readIdentityStatus(accessToken: String): JSONObject =
        request(
            path = "owner/v1/identity/status",
            method = "GET",
            accessToken = accessToken,
        )

    fun createAdditionalDeviceChallenge(
        accessToken: String,
        ownerKeyId: String,
        candidatePublicKeyDerBase64Url: String,
    ): JSONObject = request(
        path = "owner/v1/devices/enrollment/challenges",
        method = "POST",
        accessToken = accessToken,
        body = JSONObject()
            .put("owner_key_id", ownerKeyId)
            .put("public_key_der_base64url", candidatePublicKeyDerBase64Url)
            .put("app_version", version),
    )

    fun completeAdditionalDeviceEnrollment(
        accessToken: String,
        challengeId: String,
        ownerSignatureBase64Url: String,
        candidateSignatureBase64Url: String,
    ): JSONObject = request(
        path = "owner/v1/devices/enrollment/complete",
        method = "POST",
        accessToken = accessToken,
        body = JSONObject()
            .put("challenge_id", challengeId)
            .put("owner_signature_base64url", ownerSignatureBase64Url)
            .put("candidate_signature_base64url", candidateSignatureBase64Url),
    )

    fun submitSignedCommand(
        accessToken: String,
        kind: String,
        requestBody: JSONObject,
    ): JSONObject {
        require(kind in OWNER_COMMAND_KINDS)
        val idempotencyKey = "owner-${UUID.randomUUID().toString().replace("-", "")}"
        val challengeResponse = request(
            path = "owner/commands/$kind/challenges",
            method = "POST",
            accessToken = accessToken,
            body = JSONObject()
                .put("idempotency_key", idempotencyKey)
                .put("request_body", requestBody),
        )
        val challenge = challengeResponse.getJSONObject("challenge")
        val commandId = challenge.getString("command_id")
        val signature = encodeBase64Url(
            OwnerSigningKey.sign(
                decodeBase64Url(challengeResponse.getString("signing_bytes_base64url")),
            ),
        )
        val committed = request(
            path = "owner/commands/$kind/commit",
            method = "POST",
            accessToken = accessToken,
            body = JSONObject()
                .put("challenge_id", challenge.getString("id"))
                .put("request_body", requestBody)
                .put("signature", signature),
        )
        val execution = committed.optJSONObject("execution")
        if (execution?.optString("status") in setOf("PENDING", "PROCESSING", "RETRYABLE")) {
            val status = readCommandStatus(accessToken, commandId)
            committed.put("execution", status.optJSONObject("execution") ?: execution)
        }
        return committed
    }

    fun readCommandStatus(accessToken: String, commandId: String): JSONObject =
        run {
            require(commandId.matches(Regex("^cmd-[0-9a-f]{32}$")))
            request(
                path = "owner/commands/$commandId",
                method = "GET",
                accessToken = accessToken,
            )
        }

    private fun request(
        path: String,
        method: String,
        accessToken: String? = null,
        body: JSONObject? = null,
        headers: Map<String, String> = emptyMap(),
    ): JSONObject {
        val url = ownerApiUrl(baseUrl, path)
        val connection = openConnection(url).apply {
            requestMethod = method
            connectTimeout = TIMEOUT_MILLIS
            readTimeout = TIMEOUT_MILLIS
            useCaches = false
            instanceFollowRedirects = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-store")
            setRequestProperty("X-QC2-Client-Version", version.take(64))
            setRequestProperty("X-QC2-Client-Build", buildIdentity.take(128))
            if (accessToken != null) {
                setRequestProperty("Authorization", "Bearer $accessToken")
            }
            headers.forEach { (name, value) -> setRequestProperty(name, value) }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (body != null) {
                connection.outputStream.use { stream ->
                    stream.write(body.toString().toByteArray(Charsets.UTF_8))
                }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val responseText = stream?.let { source ->
                BufferedInputStream(source).use { it.readBytes().toString(Charsets.UTF_8) }
            }.orEmpty()
            val response = runCatching { JSONObject(responseText) }
                .getOrElse { JSONObject() }
            if (status !in 200..299) {
                val code = response.optJSONObject("error")?.optString("code")
                    ?.takeIf(String::isNotBlank)
                throw OwnerApiException(status, code)
            }
            return response
        } finally {
            connection.disconnect()
        }
    }

    private fun parseSession(json: JSONObject): OwnerSession {
        val access = json.getString("access_token")
        val refresh = json.getString("refresh_token")
        val now = System.currentTimeMillis()
        val accessExpires = now + json.getLong("expires_in") * 1000L
        val refreshExpires = now + json.getLong("refresh_expires_in") * 1000L
        val session = json.optJSONObject("session")
        val deviceId = session
            ?.optJSONObject("device_ref")
            ?.optString("target_id")
            ?.ifBlank { null }
        return OwnerSession(access, refresh, accessExpires, refreshExpires, deviceId)
    }

    private fun optionalRecoveryMaterial(json: JSONObject): String? =
        if (json.isNull("recovery_material")) null
        else json.optString("recovery_material").takeIf(String::isNotBlank)

    private fun encodeBase64Url(bytes: ByteArray): String =
        Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)

    private fun decodeBase64Url(value: String): ByteArray =
        Base64.getUrlDecoder().decode(value)

    private companion object {
        const val OWNER_KEY_ID = "qc2-android-owner"
        const val TIMEOUT_MILLIS = 12_000
        val OWNER_VIEWS = setOf(
            "today", "predictions", "validation", "models", "system",
            "positions", "alerts", "reports", "evidence",
        )
        val OWNER_COMMAND_KINDS = setOf(
            "promotion-decision", "entry-pause", "resume-request",
            "alert-acknowledgment", "device-management",
        )
    }
}

internal fun ownerApiUrl(baseUrl: String, path: String): URL {
    require(path.isNotBlank() && !path.startsWith("/") && !path.contains("..")) {
        "invalid_owner_api_path"
    }
    val base = java.net.URI(baseUrl.trimEnd('/'))
    require(
        base.scheme.equals("https", ignoreCase = true) &&
            !base.host.isNullOrBlank() &&
            base.userInfo == null &&
            base.query == null &&
            base.fragment == null,
    ) { "owner_api_https_origin_required" }
    val queryIndex = path.indexOf('?')
    val routePath = if (queryIndex >= 0) path.substring(0, queryIndex) else path
    val query = if (queryIndex >= 0) path.substring(queryIndex + 1) else null
    val fullPath = listOf(base.path.trim('/'), routePath.trim('/'))
        .filter(String::isNotBlank)
        .joinToString("/", prefix = "/")
    return java.net.URI(
        base.scheme,
        null,
        base.host,
        base.port,
        fullPath,
        query,
        null,
    ).toURL()
}
