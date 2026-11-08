package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.core.network.VerifyResponse

/**
 * Maps the code flow's last two answers -- a verified code, and the
 * password chosen after it -- to a [AuthUiState].
 *
 * **Beside [AuthStateMapper], not inside it**, only to keep each object
 * small enough to read: the same rules hold. It is pure, it is the unit
 * the tests target, and every decision the choose-password step depends
 * on is made here or by the server [TC-9, D-31].
 */
object PasswordStateMapper {
    /**
     * Map a verified one-time code, which now leads to choosing a
     * password rather than to a session.
     *
     * The server returns a setup token and says whether the account has
     * an authenticator app on. A reply without the token is one this
     * client cannot act on -- including a server from before passwords,
     * which would send a pair instead.
     *
     * @param response The server's reply
     * @return The choose-password step, or a failure
     */
    fun afterCodeVerified(response: VerifyResponse): AuthUiState =
        if (response.passwordSetupToken.isNullOrEmpty()) {
            AuthUiState.Failed(AuthStateMapper.UNEXPECTED_KEY, retryable = false, step = AuthStep.CODE_REQUEST)
        } else {
            AuthUiState.ChoosePassword(mfaRequired = response.mfaRequired)
        }

    /**
     * Map what choosing a password came to.
     *
     * **A lapsed setup token goes back to the code flow's first step.**
     * The token is spent or expired, so neither this form nor a retry can
     * help: the way on is a new code. It is shown as not retryable for
     * the same reason a lapsed challenge is.
     *
     * Every other refusal -- a password the server thinks too common, a
     * wrong authenticator code, the lock -- stays on the form with the
     * server's key and retryability, and a lost connection stays there
     * with an explicit retry.
     *
     * @param result The repository's answer
     * @param form The form as it was when sent
     * @return Signed in, the form with a refusal, or the code flow's start
     */
    fun afterPasswordSetup(
        result: AuthResult<TokenResponse>,
        form: AuthUiState.ChoosePassword,
    ): AuthUiState =
        when (result) {
            is AuthResult.Ok -> AuthStateMapper.afterVerify(result.value)
            is AuthResult.Refused ->
                if (result.envelope.error.messageKey == SETUP_EXPIRED_KEY) {
                    AuthUiState.Failed(SETUP_EXPIRED_KEY, retryable = false, step = AuthStep.CODE_REQUEST)
                } else {
                    form.copy(
                        checking = false,
                        messageKey = result.envelope.error.messageKey,
                        retryable = result.envelope.error.retryable,
                    )
                }
            AuthResult.TransportFailure ->
                form.copy(checking = false, messageKey = AuthStateMapper.OFFLINE_KEY, retryable = true)
        }

    /**
     * Check a chosen password before it is sent: length and match only.
     *
     * @param form The form as it is
     * @param password The password typed
     * @param confirm Its second copy
     * @return The form with the client's refusal, or null when it may be sent
     */
    fun checkChosen(
        form: AuthUiState.ChoosePassword,
        password: String,
        confirm: String,
    ): AuthUiState.ChoosePassword? =
        PasswordRules.check(password, confirm)?.let { key ->
            form.copy(checking = false, messageKey = key, retryable = false)
        }

    /** The refusal of a setup token that has lapsed or was already used. */
    const val SETUP_EXPIRED_KEY: String = "auth.password.setup_expired"
}
