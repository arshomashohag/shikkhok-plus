package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.VerifyResponse

/**
 * Maps the verify step's answers when a sign-up's username was taken
 * meanwhile (functional-spec W2, 3.3) [FR2.2].
 *
 * **Its own object, beside [AuthStateMapper]**, so that one stays a
 * readable size; the two share the offline key and the code-step states.
 * Pure: no network, no storage, no clock.
 */
object ReplacementStateMapper {
    /** The verify refusal that opens the replacement step [FR2.2]. */
    const val USERNAME_UNAVAILABLE_KEY: String = "account.username.unavailable"

    /** The refusals that end the held code: a new one is needed. */
    private val SPENT_CODE_KEYS: Set<String> = setOf("auth.otp.expired", "auth.otp.no_tries_left", "auth.otp.not_valid")

    /** The wrong-code refusal, which carries the tries left. */
    private const val WRONG_CODE_KEY: String = "auth.otp.wrong"

    /** The detail a wrong code carries: how many tries are left. */
    private const val ATTEMPTS_LEFT_DETAIL: String = "attempts_left"

    /**
     * Map a refused code check.
     *
     * **Recognised by its `message_key`, never by the status** (W2 step
     * 1): `account.username.unavailable` means the code was right and was
     * NOT consumed, so the replacement step opens with the code kept;
     * every other refusal stays on the code step as before.
     *
     * @param envelope The server's refusal
     * @param previous The username the sign-up form carried, as typed
     * @return The replacement step, or the code step with the refusal
     */
    fun afterVerifyRefused(envelope: ErrorEnvelope, previous: String): AuthUiState =
        if (envelope.error.messageKey == USERNAME_UNAVAILABLE_KEY) {
            AuthUiState.ReplaceUsername(previous = previous)
        } else {
            AuthStateMapper.codeRejected(
                AuthStateMapper.afterError(envelope),
                envelope.error.details?.get(ATTEMPTS_LEFT_DETAIL),
            )
        }

    /**
     * Map what a replacement came to (W2 step 5).
     *
     * A spent or expired code goes back to the code step's own handling,
     * where a new code is asked for; a wrong code there too, with its
     * tries left (it cannot happen for a code that verified once, and is
     * handled as the ordinary wrong code if it arrives). Every other
     * refusal -- a username one, `auth.lookup.too_many`, anything else --
     * stays on the replacement with the server's key: the code still
     * works and the person decides when to press Continue again.
     *
     * @param result The repository's answer
     * @param previous The username the sign-up form carried
     * @return The next step: choosing a password, the replacement with
     *   the refusal, or the code step
     */
    fun afterReplacement(result: AuthResult<VerifyResponse>, previous: String): AuthUiState =
        when (result) {
            // The same continuation as a first verify: choose a password,
            // or have the one from the form sent by the caller.
            is AuthResult.Ok -> PasswordStateMapper.afterCodeVerified(result.value)
            is AuthResult.Refused -> {
                val error = result.envelope.error
                when (error.messageKey) {
                    in SPENT_CODE_KEYS -> AuthUiState.CodeRejected(error.messageKey, error.retryable)
                    WRONG_CODE_KEY ->
                        AuthUiState.CodeRejected(
                            error.messageKey,
                            error.retryable,
                            error.details?.get(ATTEMPTS_LEFT_DETAIL),
                        )
                    else ->
                        AuthUiState.ReplaceUsername(
                            previous,
                            messageKey = error.messageKey,
                            retryable = error.retryable,
                        )
                }
            }
            AuthResult.TransportFailure ->
                AuthUiState.ReplaceUsername(previous, messageKey = AuthStateMapper.OFFLINE_KEY, retryable = true)
        }
}
