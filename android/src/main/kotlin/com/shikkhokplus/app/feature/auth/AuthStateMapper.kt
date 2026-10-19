package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse

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
}
