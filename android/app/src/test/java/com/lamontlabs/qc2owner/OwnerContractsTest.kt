package com.lamontlabs.qc2owner

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.json.JSONObject

class OwnerContractsTest {
    @Test
    fun commandBodiesMatchOwnerApiSchemas() {
        val pause = OwnerCommandBuilder.pauseEntries(7, "owner_request")
        assertEquals("PAUSE_NEW_ENTRIES", pause.getString("command_type"))
        assertEquals(7L, pause.getJSONObject("payload").getLong("expected_generation"))
        assertEquals("owner_request", pause.getJSONObject("payload").getString("reason_code"))

        val resume = OwnerCommandBuilder.requestResume(8)
        assertEquals("RESUME_REQUEST", resume.getString("command_type"))
        assertEquals(8L, resume.getJSONObject("payload").getLong("expected_pause_generation"))

        val alert = OwnerCommandBuilder.acknowledgeAlert(
            "018f0000-0000-7000-8000-000000000001",
            11,
        )
        val alertPayload = alert.getJSONObject("payload")
        assertEquals(
            "qc2.governance_owner.Alert.v1",
            alertPayload.getJSONObject("alert_ref").getString("target_schema_name"),
        )
        assertEquals(11L, alertPayload.getLong("expected_projection_sequence"))

        val promotion = OwnerCommandBuilder.approvePromotion(
            "018f0000-0000-7000-8000-000000000002",
            "a".repeat(64),
            "b".repeat(64),
        )
        assertEquals("APPROVE", promotion.getJSONObject("payload").getString("decision"))
        assertFalse(promotion.getJSONObject("payload").has("threshold"))
        assertFalse(promotion.getJSONObject("payload").has("model_install"))

        val revoke = OwnerCommandBuilder.revokeDevice("018f0000-0000-7000-8000-000000000003")
        assertEquals("DEVICE_ACTION", revoke.getString("command_type"))
        assertEquals("REVOKE_DEVICE", revoke.getJSONObject("payload").getString("action"))
    }

    @Test
    fun ownerApiRequiresHttpsAndPreservesApiPrefixAndQuery() {
        val url = ownerApiUrl(
            "https://owner.example.test/api/",
            "owner/v1?view=today&limit=100",
        )
        assertEquals(
            "https://owner.example.test/api/owner/v1?view=today&limit=100",
            url.toExternalForm(),
        )
        assertTrue(runCatching {
            ownerApiUrl("http://owner.example.test/api", "owner/v1")
        }.isFailure)
        assertTrue(runCatching {
            ownerApiUrl("https://user:secret@owner.example.test/api", "owner/v1")
        }.isFailure)
    }

    @Test
    fun ownerApiReadAddsBearerAndClientBuildHeaders() {
        lateinit var captured: StubConnection
        val client = OwnerApiClient(
            "https://owner.example.test/api",
            "0.1.0",
            "commit-abc",
        ) { url ->
            StubConnection(url, 200, """{"projection_sequence":4,"items":[]}""")
                .also { captured = it }
        }

        val response = client.readProjection("short-lived-session-token", "today")

        assertEquals(4, response.getInt("projection_sequence"))
        assertEquals("GET", captured.requestMethod)
        assertEquals(
            "https://owner.example.test/api/owner/v1?view=today&limit=100",
            captured.url.toExternalForm(),
        )
        assertEquals("Bearer short-lived-session-token", captured.getRequestProperty("Authorization"))
        assertEquals("0.1.0", captured.getRequestProperty("X-QC2-Client-Version"))
        assertEquals("commit-abc", captured.getRequestProperty("X-QC2-Client-Build"))
    }

    @Test
    fun pairingCodeFormatIsBoundedAndUsesOnlyUrlSafeCharacters() {
        val validCode = "A".repeat(43)
        assertTrue(validCode.matches(Regex("^[A-Za-z0-9_-]{43}$")))
        assertFalse("A".repeat(42).matches(Regex("^[A-Za-z0-9_-]{43}$")))
        assertFalse(("A".repeat(42) + "!").matches(Regex("^[A-Za-z0-9_-]{43}$")))
    }

    @Test
    fun apiErrorsDoNotExposeResponseBodiesAsExceptionText() {
        val client = OwnerApiClient(
            "https://owner.example.test/api",
            "0.1.0",
            "test",
        ) { url -> StubConnection(url, 403, """{"error":{"code":"forbidden"}}""") }

        val error = runCatching { client.readProjection("token", "system") }.exceptionOrNull()
        assertTrue(error is OwnerApiException)
        assertEquals(403, (error as OwnerApiException).httpStatus)
        assertEquals("forbidden", error.errorCode)
        assertFalse(error.message.orEmpty().contains("token"))
    }
}

private class StubConnection(
    url: java.net.URL,
    private val status: Int,
    private val responseText: String,
) : java.net.HttpURLConnection(url) {
    private val requestHeaders = mutableMapOf<String, String>()

    override fun connect() = Unit
    override fun disconnect() = Unit
    override fun usingProxy() = false
    override fun getResponseCode(): Int = status
    override fun getInputStream() =
        java.io.ByteArrayInputStream(responseText.toByteArray(Charsets.UTF_8))

    override fun getErrorStream() =
        java.io.ByteArrayInputStream(responseText.toByteArray(Charsets.UTF_8))

    override fun setRequestProperty(key: String, value: String) {
        requestHeaders[key] = value
    }

    override fun getRequestProperty(key: String): String? = requestHeaders[key]
}
