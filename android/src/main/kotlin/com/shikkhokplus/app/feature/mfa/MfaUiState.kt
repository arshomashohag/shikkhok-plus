package com.shikkhokplus.app.feature.mfa

import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.core.ui.authenticatorCodeSendable
import com.shikkhokplus.app.core.ui.recoveryCodeSendable

/**
 * Two-step verification as the screens show it, decided by [MfaMapper].
 *
 * @property enabled It is on
 * @property enabledAt When it was turned on, as the server's timestamp,
 *   or null
 * @property recoveryCodesLeft Unused recovery codes, shown while it is on
 * @property showRecommended Draw the "Recommended" mark: the server
 *   recommends it and it is off
 * @property required Draw "Required for your account"; there is no way
 *   to turn it off
 * @property canTurnOff Offer Turn off: it is on and not required
 * @property lowOnCodes Warn that few recovery codes are left
 */
data class MfaStatus(
    val enabled: Boolean,
    val enabledAt: String?,
    val recoveryCodesLeft: Int,
    val showRecommended: Boolean,
    val required: Boolean,
    val canTurnOff: Boolean,
    val lowOnCodes: Boolean,
)

/** The status page, apart from any flow on top of it. */
sealed interface MfaStatusUiState {
    /** The first read is in flight. */
    data object Loading : MfaStatusUiState

    /**
     * Read.
     *
     * @property status Where it stands
     */
    data class Loaded(val status: MfaStatus) : MfaStatusUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : MfaStatusUiState
}

/**
 * The step a person is part-way through, drawn over the status page.
 *
 * **What was typed survives a failure** in every step that takes a
 * code, so the explicit retry is one tap and nothing is typed again.
 */
sealed interface MfaFlow {
    /** No step: the status page is shown. */
    data object None : MfaFlow

    /**
     * Turn on, first: asking the server for a secret.
     *
     * @property write In flight, or why it failed
     */
    data class Starting(val write: WriteState = WriteState.Saving) : MfaFlow

    /**
     * Turn on, second: the secret to add to the app, and the first code
     * the app shows, which confirms it.
     *
     * @property secret The secret, for Copy, exactly as the server sent it
     * @property secretGroups The same secret in groups of four, for reading
     * @property otpauthUri The link an authenticator app on this phone opens
     * @property code The code as typed
     * @property write Where the confirmation stands
     * @property noAuthenticator No app on this phone opened the link
     */
    data class Confirming(
        val secret: String,
        val secretGroups: String,
        val otpauthUri: String,
        val code: String = "",
        val write: WriteState = WriteState.Idle,
        val noAuthenticator: Boolean = false,
    ) : MfaFlow {
        /** Whether the code can be sent: six digits and nothing in flight. */
        val canSubmit: Boolean
            get() = authenticatorCodeSendable(code) && write != WriteState.Saving
    }

    /**
     * Recovery codes, shown once: after turning on, or new ones.
     *
     * @property codes The codes, in the server's order
     * @property renewed True for replacements, whose old codes stopped working
     */
    data class Codes(val codes: List<String>, val renewed: Boolean) : MfaFlow

    /**
     * Turn off: a code from the app, or a recovery code.
     *
     * @property useRecovery A recovery code is asked for instead
     * @property input What is typed
     * @property write Where the request stands
     */
    data class TurningOff(
        val useRecovery: Boolean = false,
        val input: String = "",
        val write: WriteState = WriteState.Idle,
    ) : MfaFlow {
        /** Whether it can be sent: the right format and nothing in flight. */
        val canSubmit: Boolean
            get() =
                write != WriteState.Saving &&
                    if (useRecovery) recoveryCodeSendable(input) else authenticatorCodeSendable(input)
    }

    /**
     * New recovery codes: a code from the app.
     *
     * @property code The code as typed
     * @property write Where the request stands
     */
    data class Renewing(
        val code: String = "",
        val write: WriteState = WriteState.Idle,
    ) : MfaFlow {
        /** Whether the code can be sent: six digits and nothing in flight. */
        val canSubmit: Boolean
            get() = authenticatorCodeSendable(code) && write != WriteState.Saving
    }
}

/**
 * Everything the two-step verification screen renders.
 *
 * @property status The status page
 * @property flow The step in progress, or [MfaFlow.None]
 */
data class MfaUiState(
    val status: MfaStatusUiState = MfaStatusUiState.Loading,
    val flow: MfaFlow = MfaFlow.None,
)
