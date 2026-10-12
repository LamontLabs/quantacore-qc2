package com.lamontlabs.qc2owner

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Signature

internal object OwnerSigningKey {
    private const val ALIAS = "qc2-owner-p256-v1"

    fun ensureCreated() {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (store.containsAlias(ALIAS)) return
        val generator = KeyPairGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_EC,
            "AndroidKeyStore",
        )
        generator.initialize(
            KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY,
            )
                .setAlgorithmParameterSpec(java.security.spec.ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setUserAuthenticationRequired(false)
                .build(),
        )
        generator.generateKeyPair()
    }

    fun publicKeyEncoded(): ByteArray {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val certificate = store.getCertificate(ALIAS)
            ?: error("owner_signing_key_not_initialized")
        return certificate.publicKey.encoded
    }

    fun sign(message: ByteArray): ByteArray {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val privateKey = store.getKey(ALIAS, null)
            ?: error("owner_signing_key_not_initialized")
        return Signature.getInstance("SHA256withECDSA").run {
            initSign(privateKey as java.security.PrivateKey)
            update(message)
            sign()
        }
    }

    fun delete() {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (store.containsAlias(ALIAS)) store.deleteEntry(ALIAS)
    }
}
