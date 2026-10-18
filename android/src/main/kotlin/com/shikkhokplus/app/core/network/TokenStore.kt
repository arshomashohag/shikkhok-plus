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
