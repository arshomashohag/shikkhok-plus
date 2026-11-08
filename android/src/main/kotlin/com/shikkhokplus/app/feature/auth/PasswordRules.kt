package com.shikkhokplus.app.feature.auth

/**
 * The only password checks this client makes: length, and that the two
 * typed copies match.
 *
 * **Format only, never policy** [team: Layer boundaries]. The server
 * also refuses very common passwords, and any other rule it adopts stays
 * there; a client copy of a policy is the validation-divergence path the
 * layer rule names. Length is counted in Unicode code points, as the
 * server counts it, so a Bangla password is measured the same on both
 * sides.
 *
 * The refusals reuse the server's own keys for length, so the person
 * reads the same sentence whichever side caught it; the mismatch is the
 * client's alone, because the server never sees the second copy.
 */
object PasswordRules {
    /** The shortest password the server accepts. */
    const val MIN_LENGTH: Int = 8

    /** The longest password the server accepts. */
    const val MAX_LENGTH: Int = 128

    /** Shorter than [MIN_LENGTH]; the server's own key. */
    const val TOO_SHORT_KEY: String = "auth.password.too_short"

    /** Longer than [MAX_LENGTH]; the server's own key. */
    const val TOO_LONG_KEY: String = "auth.password.too_long"

    /** The two copies differ. Client-side only. */
    const val MISMATCH_KEY: String = "auth.password.mismatch"

    /**
     * Check a new password and its confirmation.
     *
     * @param password The password typed
     * @param confirm The second copy, or null where no second copy is asked
     * @return The key of the first problem, or null when it may be sent
     */
    fun check(password: String, confirm: String?): String? {
        val length = password.codePointCount(0, password.length)
        return when {
            length < MIN_LENGTH -> TOO_SHORT_KEY
            length > MAX_LENGTH -> TOO_LONG_KEY
            confirm != null && confirm != password -> MISMATCH_KEY
            else -> null
        }
    }
}
