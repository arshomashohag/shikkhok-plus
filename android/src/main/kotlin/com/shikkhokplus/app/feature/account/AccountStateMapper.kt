package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.auth.PasswordRules

/**
 * Maps the account screens' responses to their states.
 *
 * **This object is the unit under test**, rather than the ViewModels.
 * It is pure: no network, no storage, no clock [TC-9, D-31].
 */
object AccountStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be acted on. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /** The key a missing current password is refused with, client-side. */
    const val CURRENT_REQUIRED_KEY: String = "auth.password.current_required"

    /**
     * Check the password form before it is sent: length and match, and a
     * current password when the account has one.
     *
     * @param form The form as it is
     * @param current The current password typed, or empty
     * @param newPassword The new password
     * @param confirm Its second copy
     * @return The form with the client's refusal, or null when it may be sent
     */
    fun checkPassword(
        form: PasswordChangeUiState.Editing,
        current: String,
        newPassword: String,
        confirm: String,
    ): PasswordChangeUiState.Editing? {
        val key =
            if (form.hasPassword && current.isEmpty()) {
                CURRENT_REQUIRED_KEY
            } else {
                PasswordRules.check(newPassword, confirm)
            }
        return key?.let { form.copy(saving = false, messageKey = it, retryable = false) }
    }

    /**
     * Map what setting the password came to.
     *
     * A pair with either half empty is a reply this client cannot store,
     * and storing it would end the session; it is a failure instead, on
     * the form, not retryable.
     *
     * @param result The repository's answer
     * @param form The form as it was when sent
     * @return Done, or the form with the refusal
     */
    fun afterPassword(
        result: AuthResult<TokenResponse>,
        form: PasswordChangeUiState.Editing,
    ): PasswordChangeUiState =
        when (result) {
            is AuthResult.Ok ->
                if (result.value.accessToken.isEmpty() || result.value.refreshToken.isEmpty()) {
                    form.copy(saving = false, messageKey = UNEXPECTED_KEY, retryable = false)
                } else {
                    PasswordChangeUiState.Done
                }
            is AuthResult.Refused ->
                form.copy(
                    saving = false,
                    messageKey = result.envelope.error.messageKey,
                    retryable = result.envelope.error.retryable,
                )
            AuthResult.TransportFailure -> form.copy(saving = false, messageKey = OFFLINE_KEY, retryable = true)
        }

    /**
     * Map the code request for a phone or email being added.
     *
     * @param result The repository's answer
     * @param form The form as it was when sent
     * @return The code step, or the form with the refusal
     */
    fun afterContactRequested(
        result: AuthResult<IssueResponse>,
        form: AddContactUiState.Entering,
    ): AddContactUiState =
        when (result) {
            is AuthResult.Ok ->
                if (result.value.status.isEmpty()) {
                    form.copy(sending = false, messageKey = UNEXPECTED_KEY, retryable = true)
                } else {
                    AddContactUiState.AwaitingCode(form.kind)
                }
            is AuthResult.Refused ->
                form.copy(
                    sending = false,
                    messageKey = result.envelope.error.messageKey,
                    retryable = result.envelope.error.retryable,
                )
            AuthResult.TransportFailure -> form.copy(sending = false, messageKey = OFFLINE_KEY, retryable = true)
        }

    /**
     * Map a new code asked for from the code step, which stays on screen
     * whatever the answer.
     *
     * @param result The repository's answer
     * @param step The code step as it was
     * @return A fresh code step, or the same step with the refusal
     */
    fun afterContactResent(
        result: AuthResult<IssueResponse>,
        step: AddContactUiState.AwaitingCode,
    ): AddContactUiState =
        when (result) {
            is AuthResult.Ok -> AddContactUiState.AwaitingCode(step.kind)
            is AuthResult.Refused ->
                step.copy(
                    checking = false,
                    messageKey = result.envelope.error.messageKey,
                    retryable = false,
                    attemptsLeft = null,
                )
            AuthResult.TransportFailure ->
                step.copy(checking = false, messageKey = OFFLINE_KEY, retryable = false, attemptsLeft = null)
        }

    /**
     * Map the code check for a phone or email being added.
     *
     * Every refusal stays on the code step with the server's key; a wrong
     * code also carries the server's tries-left count, rendered as sent.
     *
     * @param result The repository's answer
     * @param step The code step as it was when sent
     * @return Added, or the code step with the refusal
     */
    fun afterContactVerified(
        result: AuthResult<MeDto>,
        step: AddContactUiState.AwaitingCode,
    ): AddContactUiState =
        when (result) {
            is AuthResult.Ok -> AddContactUiState.Added(step.kind)
            is AuthResult.Refused ->
                step.copy(
                    checking = false,
                    messageKey = result.envelope.error.messageKey,
                    retryable = result.envelope.error.retryable,
                    attemptsLeft = result.envelope.error.details?.get(ATTEMPTS_LEFT),
                )
            AuthResult.TransportFailure ->
                step.copy(checking = false, messageKey = OFFLINE_KEY, retryable = true, attemptsLeft = null)
        }

    /** The detail a wrong code carries: how many tries are left. */
    private const val ATTEMPTS_LEFT = "attempts_left"
}
