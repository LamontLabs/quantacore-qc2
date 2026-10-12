package com.lamontlabs.qc2owner

import org.json.JSONObject

internal object OwnerCommandBuilder {
    private fun envelope(commandType: String, payload: JSONObject) =
        JSONObject()
            .put("schema_name", "qc2.owner_api.OwnerCommandRequest.v1")
            .put("schema_version", "1.0")
            .put("command_type", commandType)
            .put("payload", payload)

    fun pauseEntries(expectedGeneration: Long, reasonCode: String) = envelope(
        "PAUSE_NEW_ENTRIES",
        JSONObject()
            .put("expected_generation", expectedGeneration)
            .put("reason_code", reasonCode),
    )

    fun requestResume(expectedPauseGeneration: Long) = envelope(
        "RESUME_REQUEST",
        JSONObject().put("expected_pause_generation", expectedPauseGeneration),
    )

    fun acknowledgeAlert(
        alertId: String,
        expectedProjectionSequence: Long,
    ) = envelope(
        "ACKNOWLEDGE_ALERT",
        JSONObject()
            .put(
                "alert_ref",
                JSONObject()
                    .put("target_schema_name", "qc2.governance_owner.Alert.v1")
                    .put("target_id", alertId),
            )
            .put("expected_projection_sequence", expectedProjectionSequence),
    )

    fun approvePromotion(
        requestId: String,
        bundleHash: String,
        requestHash: String,
    ) = envelope(
        "PROMOTION",
        JSONObject()
            .put(
                "challenge_ref",
                JSONObject()
                    .put(
                        "target_schema_name",
                        "qc2.governance_owner.PromotionChallenge.v1",
                    )
                    .put("target_id", requestId)
                    .put("content_hash", bundleHash),
            )
            .put("decision", "APPROVE")
            .put("request_hash", requestHash),
    )

    fun revokeDevice(deviceId: String) = envelope(
        "DEVICE_ACTION",
        JSONObject()
            .put("action", "REVOKE_DEVICE")
            .put("device_id", deviceId),
    )
}
