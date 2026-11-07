package com.shikkhokplus.app.feature.mfa

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MfaSetupDto
import com.shikkhokplus.app.core.network.MfaStatusDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * Maps the two-step verification responses to UI states. Pure: no
 * network, no storage, no clock.
 *
 * **Whether it is recommended or required is the server's word**, read
 * as sent. The client never works it out from a role or a lens
 * [TC-9, D-31]; the only decisions here are about what to draw.
 */
object MfaMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /**
     * At or below this many unused recovery codes the status page warns.
     *
     * Two, because the next lost phone could spend one and a mistyped
     * attempt is not a spent code: with two left there is still a spare,
     * and with one there is none.
     */
    const val LOW_RECOVERY_CODES: Int = 2

    /** How many characters of the secret are shown together. */
    private const val SECRET_GROUP: Int = 4

    /**
     * Convert the server's status.
     *
     * @param dto The server's status
     * @return What to draw
     */
    fun statusOf(dto: MfaStatusDto): MfaStatus =
        MfaStatus(
            enabled = dto.enabled,
            enabledAt = dto.enabledAt,
            recoveryCodesLeft = dto.recoveryCodesLeft,
            showRecommended = dto.recommended && !dto.enabled,
            required = dto.required,
            canTurnOff = dto.enabled && !dto.required,
            lowOnCodes = dto.enabled && dto.recoveryCodesLeft <= LOW_RECOVERY_CODES,
        )

    /**
     * Map a read of the status.
     *
     * @param result The repository's answer
     * @return The status page to render
     */
    fun status(result: AuthResult<MfaStatusDto>): MfaStatusUiState =
        when (result) {
            is AuthResult.Ok -> MfaStatusUiState.Loaded(statusOf(result.value))
            is AuthResult.Refused ->
                MfaStatusUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> MfaStatusUiState.Failed(OFFLINE_KEY, retryable = true)
        }

    /**
     * The second step of turning it on, from a new secret.
     *
     * @param dto The server's secret
     * @return The step that shows it and asks for the first code
     */
    fun confirming(dto: MfaSetupDto): MfaFlow.Confirming =
        MfaFlow.Confirming(
            secret = dto.secret,
            secretGroups = groupSecret(dto.secret),
            otpauthUri = dto.otpauthUri,
        )

    /**
     * The secret in groups of four, so it can be read across and typed
     * into an app by hand without losing the place.
     *
     * @param secret The secret as the server sent it
     * @return The same characters, grouped with spaces
     */
    fun groupSecret(secret: String): String =
        secret.filterNot(Char::isWhitespace).chunked(SECRET_GROUP).joinToString(" ")

    /**
     * Whether to offer two-step verification right after signing in.
     *
     * Only when the server recommends it and it is off, only once per
     * account on this phone, and never for an account the phone cannot
     * name -- a dismissal it could not remember would be asked again on
     * every start.
     *
     * @param status The status the server sent
     * @param account The signed-in account, or null when unknown
     * @param seen Whether this account already answered the offer here
     * @return True to show the offer
     */
    fun shouldPrompt(status: MfaStatus, account: String?, seen: Boolean): Boolean =
        status.showRecommended && account != null && !seen

    /**
     * Map a write that was refused.
     *
     * @param envelope The server's error
     * @return The failed write, carrying the server's key and retryability
     */
    fun writeFailed(envelope: ErrorEnvelope): WriteState.Failed =
        WriteState.Failed(envelope.error.messageKey, envelope.error.retryable)

    /**
     * Map a write that got no answer.
     *
     * @return The failed write; a lost connection is always worth retrying
     */
    fun writeUnanswered(): WriteState.Failed = WriteState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * Map any failed write result. Never called with a success.
     *
     * @param result The repository's answer
     * @return The failed write
     */
    fun failure(result: AuthResult<*>): WriteState.Failed =
        (result as? AuthResult.Refused)?.let { writeFailed(it.envelope) } ?: writeUnanswered()
}
