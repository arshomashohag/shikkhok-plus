package com.shikkhokplus.app.core.network

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
        preferences.edit().putString(KEY_ACCESS, access).putString(KEY_REFRESH, refresh).apply()
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
