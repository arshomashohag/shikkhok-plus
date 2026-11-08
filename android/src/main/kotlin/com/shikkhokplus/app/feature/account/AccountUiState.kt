package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.model.IdentifierKind

/**
 * Everything the set-or-change-password screen renders.
 *
 * A composable receives one of these and renders it with no
 * conditionals on a domain value [TC-9, D-31]: whether the current
 * password is asked for is [Editing.hasPassword], read from the server.
 */
sealed interface PasswordChangeUiState {
    /**
     * The form.
     *
     * @property hasPassword The account already has a password, so the
     *   current one is asked for and the screen says "Change"; false for
     *   an account from before passwords, which is setting its first
     * @property saving The form is with the server
     * @property messageKey Why the last attempt was refused, or null
     * @property retryable Read from the server's envelope; true only when
     *   sending the same form again could succeed
     */
    data class Editing(
        val hasPassword: Boolean,
        val saving: Boolean = false,
        val messageKey: String? = null,
        val retryable: Boolean = false,
    ) : PasswordChangeUiState

    /** The password is set and the new pair is stored. */
    data object Done : PasswordChangeUiState
}

/**
 * Everything the add-a-phone-or-email screen renders.
 */
sealed interface AddContactUiState {
    /** Which kind is being added: fixed for the screen's lifetime. */
    val kind: IdentifierKind

    /**
     * The phone or email is being typed.
     *
     * @property kind Phone or email
     * @property sending The code request is with the server
     * @property messageKey Why the last request was refused, or null
     * @property retryable Read from the server's envelope
     */
    data class Entering(
        override val kind: IdentifierKind,
        val sending: Boolean = false,
        val messageKey: String? = null,
        val retryable: Boolean = false,
    ) : AddContactUiState

    /**
     * A code was sent; the six digits are asked for.
     *
     * @property kind Phone or email
     * @property checking The code is with the server
     * @property messageKey Why the last code was refused, or null
     * @property retryable Read from the server's envelope
     * @property attemptsLeft The server's tries-left count, shown as it
     *   arrived, or null
     */
    data class AwaitingCode(
        override val kind: IdentifierKind,
        val checking: Boolean = false,
        val messageKey: String? = null,
        val retryable: Boolean = false,
        val attemptsLeft: String? = null,
    ) : AddContactUiState

    /**
     * Added. The account's lenses and invitations may have changed --
     * a phone links the seats teachers recorded for it -- so the caller
     * re-reads them.
     *
     * @property kind Phone or email
     */
    data class Added(override val kind: IdentifierKind) : AddContactUiState
}
