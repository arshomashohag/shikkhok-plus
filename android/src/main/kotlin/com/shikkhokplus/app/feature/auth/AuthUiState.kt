package com.shikkhokplus.app.feature.auth

/**
 * Everything the OTP screen renders, decided here rather than in a
 * composable.
 *
 * **A composable receives a UiState and renders it with no conditionals
 * depending on domain values.** That rule is what stops badge and
 * empty-state logic — which is business logic wearing presentation
 * clothes — from landing somewhere untestable [TC-9, D-31].
 *
 * Mapping a response to one of these is the target of the tests, rather
 * than an untargeted "test the ViewModel".
 */
sealed interface AuthUiState {
    /** Nothing has been asked for yet. */
    data object Idle : AuthUiState

    /** A request is in flight; the screen shows a spinner. */
    data object Sending : AuthUiState

    /**
     * A code was requested. The screen shows the code entry field.
     *
     * Reached for **any** number, known or not, because the server's
     * response is identical either way [BR2.7]. The client must not
     * imply a number was recognised.
     */
    data object AwaitingCode : AuthUiState

    /** The code was accepted and a session exists. */
    data object SignedIn : AuthUiState

    /**
     * Something failed, and the screen can say what to do about it.
     *
     * @property messageKey Names a string resource; never English text
     *   from the server, which could not be localized [TC-15, D-43].
     * @property retryable Read from the server's envelope, never
     *   inferred from a status code [TC-9].
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : AuthUiState
}
