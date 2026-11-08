package com.shikkhokplus.app.feature.auth

/**
 * Everything the sign-in screen renders, decided here rather than in a
 * composable: the password sign-in, the code flow, choosing a password
 * and the authenticator step.
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

    /**
     * The sign-in form: Phone | Email, the identifier, and a password.
     *
     * Nothing has been asked for yet. Reached at a cold start with no
     * session, after signing out, and from "Back to sign in".
     */
    data object Idle : AuthUiState

    /** A password sign-in is with the server; the form stays beneath a loader. */
    data object SigningIn : AuthUiState

    /**
     * The code flow's first step: "Forgot password?" and "First time with
     * a password? Get a code" both land here. The person names the phone
     * or email a code should go to.
     */
    data object CodeFlowStart : AuthUiState

    /** A code request is in flight; the screen shows a spinner. */
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
     * @property attemptsLeft The server's count of tries left for this
     *   code, shown as it arrived; null when the refusal carries none
     */
    data class CodeRejected(
        val messageKey: String,
        val retryable: Boolean,
        val attemptsLeft: String? = null,
    ) : AuthUiState

    /**
     * The SMS code was right and the account has two-step verification
     * on [0028]: the code from the authenticator app is asked for, or a
     * recovery code when the person switched to one.
     *
     * **No session exists yet.** Nothing was stored, and leaving this
     * step goes back to the number, not forward.
     *
     * @property useRecovery True while a recovery code is asked for
     *   instead of the authenticator code
     * @property checking The code is with the server
     * @property messageKey Why the last code was refused, as the
     *   server's key, or null when nothing was refused
     * @property retryable Read from the server's envelope; true only for
     *   a refusal a second attempt with the same code can fix
     */
    data class SecondStep(
        val useRecovery: Boolean = false,
        val checking: Boolean = false,
        val messageKey: String? = null,
        val retryable: Boolean = false,
    ) : AuthUiState

    /**
     * The code was right; the person now chooses a password, which is
     * what finishes the code flow and creates the session.
     *
     * **No session exists yet.** What the server returned is a setup
     * token, held in the ViewModel's memory only, which lapses on its own.
     *
     * @property mfaRequired The account has an authenticator app on: the
     *   form also asks for its code, or a recovery code instead
     * @property useRecovery True while a recovery code is asked for
     *   instead of the authenticator code
     * @property checking The password is with the server
     * @property messageKey Why the last attempt was refused, as a string
     *   key, or null when nothing was refused
     * @property retryable Read from the server's envelope; true only when
     *   sending the same form again could succeed
     */
    data class ChoosePassword(
        val mfaRequired: Boolean = false,
        val useRecovery: Boolean = false,
        val checking: Boolean = false,
        val messageKey: String? = null,
        val retryable: Boolean = false,
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
     * @property step Which form the failure is shown on: the password
     *   sign-in, or the code flow's identifier step
     * @property offerCodeFlow Whether to show the static hint that leads
     *   to the code flow: decided by the mapper from the server's key, so
     *   the screen holds no rule about which refusal earns it
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
        val step: AuthStep = AuthStep.SIGN_IN,
        val offerCodeFlow: Boolean = false,
    ) : AuthUiState
}

/** Which form a [AuthUiState.Failed] belongs on. */
enum class AuthStep {
    /** The password sign-in form. */
    SIGN_IN,

    /** The code flow's identifier form. */
    CODE_REQUEST,
}
