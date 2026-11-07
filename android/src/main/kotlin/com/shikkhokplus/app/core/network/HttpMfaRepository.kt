package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.mfa.MfaRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * The signed-in account's own two-step verification, over HTTP [0028].
 *
 * **Every route is `/v1/me/mfa...`**: the server reads and changes only
 * the authenticated account's own setting, with no lens and no
 * workspace. Nothing is queued: each write needs a connection, and a
 * failure goes back to the screen to retry [TC-8, D-9].
 *
 * @property client The authenticated HTTP client
 */
class HttpMfaRepository(
    private val client: HttpClient,
) : MfaRepository {

    override suspend fun status(): AuthResult<MfaStatusDto> = call { client.get("/v1/me/mfa") }

    override suspend fun setup(): AuthResult<MfaSetupDto> = call { client.post("/v1/me/mfa/setup") }

    override suspend fun confirm(code: String): AuthResult<MfaRecoveryCodesDto> =
        call { client.post("/v1/me/mfa/confirm") { setBody(MfaCodeRequestDto(code)) } }

    override suspend fun disable(code: String?, recoveryCode: String?): AuthResult<MfaStatusDto> =
        call { client.post("/v1/me/mfa/disable") { setBody(MfaProofRequestDto(code, recoveryCode)) } }

    override suspend fun renewRecoveryCodes(code: String): AuthResult<MfaRecoveryCodesDto> =
        call { client.post("/v1/me/mfa/recovery-codes") { setBody(MfaCodeRequestDto(code)) } }
}
