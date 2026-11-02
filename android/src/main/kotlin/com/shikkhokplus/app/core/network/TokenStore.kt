package com.shikkhokplus.app.core.network

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

/**
 * Holds the tokens for the signed-in session.
 *
 * **An interface, because where tokens live is a security decision this
 * Bolt does not settle.** The in-memory implementation below loses the
 * session when the process dies, which is wrong for a product whose
 * refresh token lasts 30 days — but it is honestly wrong rather than
 * quietly wrong, and the alternative (writing a refresh token to
 * SharedPreferences because it was convenient) is a decision that
 * should be made deliberately with EncryptedSharedPreferences or the
 * Keystore, not arrived at here.
 */
interface TokenStore {
    /**
     * The access token to send, or null when signed out.
     *
     * @return The bearer token, or null
     */
    fun accessToken(): String?

    /**
     * The refresh token, or null when signed out.
     *
     * @return The refresh token, or null
     */
    fun refreshToken(): String?

    /**
     * Record a freshly issued pair.
     *
     * @param access The access token
     * @param refresh The refresh token
     */
    fun save(access: String, refresh: String)

    /**
     * Forget the session.
     *
     * Called on refresh-token reuse detection, where the server has
     * invalidated the whole family and holding the tokens would mean
     * retrying with credentials known to be dead.
     */
    fun clear()

    /**
     * The account the stored session belongs to, or null when signed out.
     *
     * Read from the access token's subject, which stays readable after
     * the token expires -- so it answers offline too, which is when the
     * device queue most needs to know whose writes it is holding.
     *
     * @return The account id, or null
     */
    fun accountId(): String? = accessToken()?.let(::accountIdOf)

    /**
     * The process-lifetime store.
     *
     * **Deliberately not persisted.** See the interface note: persisting
     * a 30-day refresh token is a decision about encrypted storage, and
     * making it implicitly by reaching for SharedPreferences is how a
     * long-lived credential ends up in plaintext on the device.
     */
    class InMemory : TokenStore {
        private var access: String? = null
        private var refresh: String? = null

        override fun accessToken(): String? = access

        override fun refreshToken(): String? = refresh

        override fun save(access: String, refresh: String) {
            this.access = access
            this.refresh = refresh
        }

        override fun clear() {
            access = null
            refresh = null
        }
    }
}

/**
 * The persistent store: the device is remembered across restarts.
 *
 * **Encrypted at rest via the Android Keystore**, not plain
 * SharedPreferences. The refresh token lasts 30 days, which is exactly
 * what makes persisting it worth doing and exactly what makes storing
 * it in plaintext a bad idea: a long-lived credential readable via adb
 * on a rooted phone, or lifted from a backup.
 *
 * `allowBackup` is already false in the manifest, so this is not the
 * only control — but a control that depends on another control nobody
 * re-reads is one control.
 *
 * **What this does NOT defend against**, stated so it is not
 * over-read: a rooted device with the app running, or one whose screen
 * lock has been removed. The Keystore binds the key to the device, not
 * to the user's presence.
 *
 * **Falls back to in-memory when the Keystore is unavailable.** That
 * happens on an emulator without secure hardware and after a factory
 * reset invalidates the master key. The fallback means the teacher
 * re-enters an OTP rather than the app refusing to start — a worse
 * experience, not a broken one, and the alternative is a crash on
 * launch with no explanation.
 */
class EncryptedTokenStore private constructor(
    private val preferences: android.content.SharedPreferences,
) : TokenStore {

    override fun accessToken(): String? = preferences.getString(KEY_ACCESS, null)

    override fun refreshToken(): String? = preferences.getString(KEY_REFRESH, null)

    override fun save(access: String, refresh: String) {
        // **commit, not apply**, for the same reason as `clear` and with
        // a sharper edge. The server has ALREADY rotated the old refresh
        // token out when this runs; `apply` returns before the new one is
        // on disk, so a process death in that window leaves the rotated-out
        // token as the only one stored, and the next start presents it --
        // which the server reads as reuse and answers by revoking the
        // whole family. The new pair must be durable before anything uses
        // it.
        preferences.edit().putString(KEY_ACCESS, access).putString(KEY_REFRESH, refresh).commit()
    }

    override fun clear() {
        // commit, not apply: this is called on refresh-token reuse
        // detection, where the server has invalidated the whole family.
        // An async write that loses the race with a process death would
        // leave a known-dead credential on disk.
        preferences.edit().clear().commit()
    }

    companion object {
        private const val FILE_NAME = "shikkhokplus.session"
        private const val KEY_ACCESS = "access_token"
        private const val KEY_REFRESH = "refresh_token"

        /**
         * Build the store, falling back to memory on any failure.
         *
         * @param context The application context
         * @return An encrypted store, or an in-memory one
         */
        fun create(context: android.content.Context): TokenStore =
            try {
                val masterKey =
                    androidx.security.crypto.MasterKey
                        .Builder(context)
                        .setKeyScheme(
                            androidx.security.crypto.MasterKey.KeyScheme.AES256_GCM,
                        )
                        .build()

                EncryptedTokenStore(
                    androidx.security.crypto.EncryptedSharedPreferences.create(
                        context,
                        FILE_NAME,
                        masterKey,
                        androidx.security.crypto.EncryptedSharedPreferences
                            .PrefKeyEncryptionScheme.AES256_SIV,
                        androidx.security.crypto.EncryptedSharedPreferences
                            .PrefValueEncryptionScheme.AES256_GCM,
                    ),
                )
            } catch (_: Exception) {
                // Keystore unavailable, or a master key invalidated by a
                // factory reset. The teacher re-enters an OTP; the app
                // does not refuse to start.
                TokenStore.InMemory()
            }
    }
}

/** Base64 decodes whole four-character groups. */
private const val BASE64_GROUP = 4

/**
 * Read the account id out of an access token's subject claim.
 *
 * **Labelling, not authorization.** The client still learns what it may
 * DO only from responses [TC-11, D-2]; nothing here is trusted to grant
 * anything, and the signature is not checked because nothing rides on
 * it. The one use is to say which account a piece of device-local data
 * -- a queued roster -- was written under, so it is never sent under a
 * different one. A forged token gains nothing: the server verifies the
 * token every write is actually sent with.
 *
 * The id is the server's opaque account UUID: no name, no phone number.
 *
 * @param accessToken A JWT, `header.payload.signature`
 * @return The `sub` claim, or null when the token cannot be read
 */
@OptIn(ExperimentalEncodingApi::class)
fun accountIdOf(accessToken: String): String? {
    val payload = accessToken.split('.').getOrNull(1) ?: return null
    // A JWT segment is unpadded base64url; restore the padding so the
    // decoder accepts it whatever its padding policy.
    val padded = payload.padEnd((payload.length + BASE64_GROUP - 1) / BASE64_GROUP * BASE64_GROUP, '=')
    return try {
        val claims = Json.parseToJsonElement(Base64.UrlSafe.decode(padded).decodeToString())
        claims.jsonObject["sub"]?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotBlank() }
    } catch (_: IllegalArgumentException) {
        // Not base64, not JSON, or not an object with a string subject.
        // SerializationException is an IllegalArgumentException.
        null
    }
}
