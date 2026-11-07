package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.core.network.VerifyResponse

/**
 * Maps a server response to a [AuthUiState].
 *
 * **This function is the unit under test**, rather than "the
 * ViewModel". Pulling it out of the coroutine machinery is what makes
 * the state machine testable without a dispatcher, and it is where
 * every decision the screen depends on lives.
 *
 * It is pure: no network, no storage, no clock. A decision that needed
 * any of those would be a business rule, and business rules are
 * server-side [TC-9, D-31].
 */
object AuthStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be parsed. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /**
     * Map a successful issue response.
     *
     * The response is identical for a known and an unknown number, so
     * this returns the same state for both — the client never implies
     * the number was recognised [BR2.7].
     *
     * @param response The server's reply
     * @return The state the screen renders
     */
    fun afterIssue(response: IssueResponse): AuthUiState =
        if (response.status.isEmpty()) {
            AuthUiState.Failed(UNEXPECTED_KEY, retryable = true)
        } else {
            AuthUiState.AwaitingCode
        }

    /**
     * Map what redeeming the stored session came to.
     *
     * **Only a session that ENDED goes to sign-in.** An unverified one
     * is kept signed in: the phone being offline, or the server failing
     * to answer, says nothing about the credential, and sending the
     * teacher to the OTP screen for it made the offline queue
     * unreachable and cost an SMS to recover from [TC-8, D-9].
     *
     * @param resume The outcome of the cold-start refresh
     * @return Signed in, or the sign-in screen
     */
    fun afterResume(resume: SessionResume): AuthUiState =
        when (resume) {
            SessionResume.RENEWED, SessionResume.UNVERIFIED -> AuthUiState.SignedIn
            SessionResume.ENDED -> AuthUiState.Idle
        }

    /**
     * Map a successful verify response.
     *
     * @param response The token pair
     * @return The signed-in state
     */
    fun afterVerify(response: TokenResponse): AuthUiState =
        if (response.accessToken.isEmpty() || response.refreshToken.isEmpty()) {
            AuthUiState.Failed(UNEXPECTED_KEY, retryable = false)
        } else {
            AuthUiState.SignedIn
        }

    /**
     * Map a successful verify response, which is either the token pair
     * or the authenticator step [0028].
     *
     * The server decides which: `mfa_required` with a challenge goes to
     * the second step, a complete pair is signed in, and anything else
     * — a pair with a half missing, or a second step with no challenge
     * to carry it — is a response this client cannot act on.
     *
     * @param response The server's reply
     * @return Signed in, the second step, or a failure
     */
    fun afterVerify(response: VerifyResponse): AuthUiState {
        val access = response.accessToken
        val refresh = response.refreshToken
        return when {
            response.mfaRequired && !response.mfaChallenge.isNullOrEmpty() -> AuthUiState.SecondStep()
            response.mfaRequired -> AuthUiState.Failed(UNEXPECTED_KEY, retryable = false)
            access != null && refresh != null -> afterVerify(TokenResponse(access, refresh, response.expiresIn ?: 0))
            else -> AuthUiState.Failed(UNEXPECTED_KEY, retryable = false)
        }
    }

    /**
     * Map what the second step came to.
     *
     * **A lapsed challenge goes back to the number.** The challenge is
     * spent, so neither the code boxes nor a retry can help: the way on
     * is a new SMS code, from the step where it is asked for. It is the
     * one refusal here that leaves the second step, and it is shown as
     * not retryable because the retry the server means is the whole
     * sign-in, which the number step already offers.
     *
     * Every other refusal — a wrong code, the fifteen-minute lock — stays
     * on the second step with the server's key and retryability, and a
     * lost connection stays there with an explicit retry.
     *
     * @param result The repository's answer
     * @param useRecovery Whether a recovery code was sent
     * @return Signed in, the second step with a refusal, or the number step
     */
    fun afterSecondStep(result: AuthResult<TokenResponse>, useRecovery: Boolean): AuthUiState =
        when (result) {
            is AuthResult.Ok -> afterVerify(result.value)
            is AuthResult.Refused ->
                if (result.envelope.error.messageKey == CHALLENGE_EXPIRED_KEY) {
                    AuthUiState.Failed(CHALLENGE_EXPIRED_KEY, retryable = false)
                } else {
                    AuthUiState.SecondStep(
                        useRecovery = useRecovery,
                        messageKey = result.envelope.error.messageKey,
                        retryable = result.envelope.error.retryable,
                    )
                }
            AuthResult.TransportFailure ->
                AuthUiState.SecondStep(useRecovery = useRecovery, messageKey = OFFLINE_KEY, retryable = true)
        }

    /** The refusal of a second step whose challenge has lapsed. */
    const val CHALLENGE_EXPIRED_KEY: String = "mfa.challenge_expired"

    /**
     * Map a server error envelope.
     *
     * `retryable` is taken **from the envelope**, never derived from
     * the status code: the client is told whether a retry is
     * appropriate rather than deciding [TC-9].
     *
     * @param envelope The server's error body
     * @return The failed state
     */
    fun afterError(envelope: ErrorEnvelope): AuthUiState =
        AuthUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope arrived.
     *
     * Retryable, because the request may never have reached the server
     * — and **V1 accepts no write without connectivity** [TC-8, D-9],
     * so the screen offers an explicit retry rather than queueing
     * silently.
     *
     * @return The failed state
     */
    fun afterTransportFailure(): AuthUiState =
        AuthUiState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * Keep a failed code check on the code screen.
     *
     * @param failed What the server or transport said
     * @param attemptsLeft The server's tries-left count, or null
     * @return The same failure, shown beside the code boxes
     */
    fun codeRejected(
        failed: AuthUiState,
        attemptsLeft: String? = null,
    ): AuthUiState =
        if (failed is AuthUiState.Failed) {
            AuthUiState.CodeRejected(failed.messageKey, failed.retryable, attemptsLeft)
        } else {
            failed
        }
}
