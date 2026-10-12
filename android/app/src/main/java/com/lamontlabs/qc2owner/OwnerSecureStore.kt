package com.lamontlabs.qc2owner

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal data class OwnerSession(
    val accessToken: String,
    val refreshToken: String,
    val accessExpiresAtMillis: Long,
    val refreshExpiresAtMillis: Long,
    val deviceId: String?,
)

internal data class CachedOwnerPage(
    val json: String,
    val cachedAtMillis: Long,
)

internal class OwnerSecureStore(context: Context) {
    private val preferences =
        context.getSharedPreferences("qc2-owner-secure-v1", Context.MODE_PRIVATE)

    fun saveSession(session: OwnerSession) {
        val json = JSONObject()
            .put("access_token", session.accessToken)
            .put("refresh_token", session.refreshToken)
            .put("access_expires_at", session.accessExpiresAtMillis)
            .put("refresh_expires_at", session.refreshExpiresAtMillis)
            .put("device_id", session.deviceId)
        putEncrypted("session", json.toString())
    }

    fun readSession(): OwnerSession? {
        val json = getEncrypted("session")?.let {
            runCatching { JSONObject(it) }.getOrNull()
        } ?: return null
        val access = json.optString("access_token").takeIf(String::isNotBlank) ?: return null
        val refresh = json.optString("refresh_token").takeIf(String::isNotBlank) ?: return null
        val accessExpires = json.optLong("access_expires_at", 0L)
        val refreshExpires = json.optLong("refresh_expires_at", 0L)
        if (accessExpires <= 0 || refreshExpires <= 0) return null
        return OwnerSession(
            access,
            refresh,
            accessExpires,
            refreshExpires,
            json.optString("device_id").ifBlank { null },
        )
    }

    fun clearSession() {
        check(preferences.edit().remove("session").commit()) { "owner_session_clear_failed" }
    }

    fun savePage(view: String, json: String, cachedAtMillis: Long) {
        require(view.matches(Regex("^[a-z]+$")))
        putEncrypted("page:$view", JSONObject()
            .put("json", json)
            .put("cached_at", cachedAtMillis)
            .toString())
    }

    fun readPage(view: String): CachedOwnerPage? {
        val json = getEncrypted("page:$view")?.let {
            runCatching { JSONObject(it) }.getOrNull()
        } ?: return null
        val body = json.optString("json").takeIf(String::isNotBlank) ?: return null
        val cachedAt = json.optLong("cached_at", 0L)
        if (cachedAt <= 0) return null
        return CachedOwnerPage(body, cachedAt)
    }

    private fun putEncrypted(name: String, plainText: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(plainText.toByteArray(Charsets.UTF_8))
        val packed = cipher.iv + encrypted
        check(
            preferences.edit()
                .putString(name, Base64.encodeToString(packed, Base64.NO_WRAP))
                .commit(),
        ) { "owner_secure_storage_failed" }
    }

    private fun getEncrypted(name: String): String? {
        val packed = preferences.getString(name, null) ?: return null
        return try {
            val bytes = Base64.decode(packed, Base64.NO_WRAP)
            if (bytes.size <= GCM_IV_BYTES) throw IllegalArgumentException("invalid ciphertext")
            val iv = bytes.copyOfRange(0, GCM_IV_BYTES)
            val ciphertext = bytes.copyOfRange(GCM_IV_BYTES, bytes.size)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(GCM_TAG_BITS, iv))
            String(cipher.doFinal(ciphertext), Charsets.UTF_8)
        } catch (_: Exception) {
            preferences.edit().remove(name).commit()
            null
        }
    }

    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(ENCRYPTION_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            "AndroidKeyStore",
        )
        generator.init(
            KeyGenParameterSpec.Builder(
                ENCRYPTION_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val ENCRYPTION_ALIAS = "qc2-owner-local-aes-v1"
        const val GCM_IV_BYTES = 12
        const val GCM_TAG_BITS = 128
    }
}
