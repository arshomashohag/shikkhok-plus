package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.feature.account.AccountRepository
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import kotlinx.coroutines.sync.withLock

/**
 * The signed-in account's password and contacts, over HTTP.
 *
 * @property client The authenticated HTTP client
 * @property tokens Where a password change records the new pair
 */
class HttpAccountRepository(
    private val client: HttpClient,
    private val tokens: TokenStore,
) : AccountRepository {

    /**
     * Set or change the password, and replace the stored pair.
     *
     * **The server ends every session, this one included**, so the pair
     * in the store is dead the moment this succeeds. The new one is saved
     * under [RENEWAL_LOCK], the lock every redemption of the refresh token
     * takes, so a renewal already under way finishes before the store
     * changes and none starts from a half-written pair.
     */
    override suspend fun setPassword(
        currentPassword: String?,
        newPassword: String,
    ): AuthResult<TokenResponse> {
        val result: AuthResult<TokenResponse> =
            call { client.post("/v1/me/password") { setBody(MePasswordRequest(currentPassword, newPassword)) } }
        if (result is AuthResult.Ok) {
            RENEWAL_LOCK.withLock { tokens.save(result.value.accessToken, result.value.refreshToken) }
        }
        return result
    }

    override suspend fun requestContact(identifier: Identifier): AuthResult<IssueResponse> =
        call { client.post("/v1/me/contact") { setBody(IssueRequest(identifier.phone, identifier.email)) } }

    override suspend fun verifyContact(
        identifier: Identifier,
        code: String,
    ): AuthResult<MeDto> =
        call {
            client.post("/v1/me/contact/verify") {
                setBody(VerifyRequest(phone = identifier.phone, email = identifier.email, code = code))
            }
        }
}
