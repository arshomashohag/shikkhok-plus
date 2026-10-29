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
    /**
     * A stored session is being redeemed, before anything is shown.
     *
     * **Distinct from [Idle], and the distinction is the defect it
     * fixes.** `Idle` meant both "never signed in" and "still
     * checking", so the graph started at the sign-in screen and jumped
     * to the home screen once the refresh landed — a returning teacher
     * saw the login screen flash for a second or two before being
     * taken somewhere else.
     *
     * This is the FIRST state, not [Idle]: the app opens on the loader
     * and resolves to one destination or the other.
     */
    data object Restoring : AuthUiState

    /** Nothing has been asked for yet; the sign-in screen is shown. */
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

    /** The six digits are with the server; the code boxes stay up. */
    data object CheckingCode : AuthUiState

    /**
     * The code was refused or could not be checked. The code boxes stay
     * up, so the person can type it again, ask for a new one, or
     * change the number, rather than being sent back to the start.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class CodeRejected(
        val messageKey: String,
        val retryable: Boolean,
    ) : AuthUiState

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
