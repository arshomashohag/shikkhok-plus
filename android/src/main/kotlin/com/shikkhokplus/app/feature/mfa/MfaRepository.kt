package com.shikkhokplus.app.feature.mfa

import com.shikkhokplus.app.core.network.MfaRecoveryCodesDto
import com.shikkhokplus.app.core.network.MfaSetupDto
import com.shikkhokplus.app.core.network.MfaStatusDto
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * What two-step verification needs from the network [0028].
 *
 * Every call is about the signed-in account's own setting: the server
 * reads no lens and no workspace for them, so every role reaches them.
 * Nothing is queued: each write needs a connection, and a failure goes
 * back to the screen with an explicit retry [TC-8, D-9].
 */
interface MfaRepository {
    /**
     * Read whether it is on, and whether the server recommends or
     * requires it for this account.
     *
     * @return The status, a refusal, or a transport failure
     */
    suspend fun status(): AuthResult<MfaStatusDto>

    /**
     * Start turning it on: the server makes a new secret.
     *
     * @return The secret and its `otpauth://` link, a refusal, or a
     *   transport failure
     */
    suspend fun setup(): AuthResult<MfaSetupDto>

    /**
     * Finish turning it on with the first code the app shows.
     *
     * @param code Six digits from the authenticator app
     * @return The ten recovery codes, shown once, a refusal, or a
     *   transport failure
     */
    suspend fun confirm(code: String): AuthResult<MfaRecoveryCodesDto>

    /**
     * Turn it off, with exactly one of the two codes.
     *
     * @param code Six digits from the authenticator app, or null
     * @param recoveryCode A recovery code, or null
     * @return The status as it now stands, a refusal, or a transport failure
     */
    suspend fun disable(code: String?, recoveryCode: String?): AuthResult<MfaStatusDto>

    /**
     * Replace the recovery codes; the old ones stop working.
     *
     * @param code Six digits from the authenticator app
     * @return The new codes, shown once, a refusal, or a transport failure
     */
    suspend fun renewRecoveryCodes(code: String): AuthResult<MfaRecoveryCodesDto>
}
