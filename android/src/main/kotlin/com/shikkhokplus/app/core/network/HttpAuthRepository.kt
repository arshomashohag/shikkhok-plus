package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.feature.auth.AuthRepository
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.auth.SessionResume
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.isSuccess
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable

@Serializable
private data class RefreshBody(
    @kotlinx.serialization.SerialName("refresh_token") val refreshToken: String,
)

/**
 * The real auth repository, over HTTP.
 *
 * **Three outcomes, not two** [TC-9]. A transport failure and a server
 * refusal need different handling: the server tells the client whether
 * a retry is appropriate, and when no response arrived there is nothing
 * to read it from. Collapsing them would mean the client inventing a
 * retry policy, which is business logic.
 *
 * @property client The configured HTTP client
 * @property tokens Where a successful verify records its pair
 */
class HttpAuthRepository(
    private val client: HttpClient,
    private val tokens: TokenStore,
) : AuthRepository {

    override suspend fun issue(identifier: Identifier): AuthResult<IssueResponse> =
        call { client.post("/v1/auth/otp") { setBody(IssueRequest(identifier.phone, identifier.email)) } }

    /**
     * Present a one-time code.
     *
     * **Saves nothing.** A verified code no longer signs anyone in: the
     * server answers with a password-setup token, and the session begins
     * only when [setupPassword] exchanges it, with a chosen password, for
     * a pair.
     */
    override suspend fun verify(
        identifier: Identifier,
        code: String,
    ): AuthResult<VerifyResponse> =
        call {
            client.post("/v1/auth/verify") {
                setBody(VerifyRequest(phone = identifier.phone, email = identifier.email, code = code))
            }
        }

    /**
     * Sign in with an identifier and a password.
     *
     * **A pair is saved only when the server sent one.** An account with
     * two-step verification gets a challenge instead, and there is no
     * session until [verifySecondStep] succeeds; saving nothing here is
     * what keeps a half-finished sign-in from looking signed in.
     */
    override suspend fun signIn(
        identifier: Identifier,
        password: String,
    ): AuthResult<VerifyResponse> {
        val result: AuthResult<VerifyResponse> =
            call {
                client.post("/v1/auth/password") {
                    setBody(PasswordSignInRequest(identifier.phone, identifier.email, password))
                }
            }
        val pair = (result as? AuthResult.Ok)?.value?.takeUnless { it.mfaRequired }
        val access = pair?.accessToken
        val refresh = pair?.refreshToken
        if (access != null && refresh != null) tokens.save(access, refresh)
        return result
    }

    /**
     * Finish the code flow by choosing a password, and save the pair.
     *
     * **Never renewed, and its 401 ends no session**, for the same
     * reason as [verifySecondStep]: nobody is signed in yet, and a lapsed
     * setup token (`401 auth.password.setup_expired`) comes back to the
     * screen as an ordinary envelope.
     */
    override suspend fun setupPassword(
        token: String,
        password: String,
        code: String?,
        recoveryCode: String?,
    ): AuthResult<TokenResponse> {
        val result: AuthResult<TokenResponse> =
            call {
                client.post("/v1/auth/password/setup") {
                    setBody(PasswordSetupRequest(token, password, code, recoveryCode))
                }
            }
        if (result is AuthResult.Ok) {
            tokens.save(result.value.accessToken, result.value.refreshToken)
        }
        return result
    }

    /**
     * Finish signing in with the authenticator code or a recovery code.
     *
     * **Never renewed, and its 401 ends no session.** A lapsed challenge
     * is answered `401 mfa.challenge_expired`, and nobody is signed in
     * yet: the request carries no bearer token, and [SessionRenewal]
     * leaves every `/v1/auth/` route alone besides, so the refusal comes
     * back to the sign-in screen as an ordinary envelope.
     */
    override suspend fun verifySecondStep(
        challenge: String,
        code: String?,
        recoveryCode: String?,
    ): AuthResult<TokenResponse> {
        val result: AuthResult<TokenResponse> =
            call { client.post("/v1/auth/mfa") { setBody(MfaSignInRequest(challenge, code, recoveryCode)) } }
        if (result is AuthResult.Ok) {
            tokens.save(result.value.accessToken, result.value.refreshToken)
        }
        return result
    }

    /**
     * Exchange a stored refresh token for a fresh pair.
     *
     * **This is what makes "remember the device" real.** Persisting a
     * token nothing redeems would change nothing: the app would hold a
     * credential and still ask for an OTP.
     *
     * **A definitive refusal CLEARS the store**, which is the
     * security-critical half. The server invalidates the whole token
     * family on reuse detection, so a 400, 401 or 403 means the
     * credential is dead -- and retrying with it would be presenting a
     * token the server has already decided was stolen.
     *
     * **Anything else clears nothing.** A transport failure, a 5xx or a
     * 429 says nothing about the token: no answer to the question
     * arrived. This used to clear on ANY non-2xx, so a cold start during
     * a server outage signed the teacher out and cost an SMS to get back
     * in, while the mid-session renewal three files away kept the
     * session on the same answer. Both now read
     * [REFUSED_REFRESH_STATUSES].
     *
     * **Under [RENEWAL_LOCK], the same lock as the mid-session
     * renewal.** The stored token is read INSIDE the lock, so a renewal
     * that rotated it while this one waited is seen, and the token sent
     * is always the current one rather than one already rotated out.
     *
     * @return The new pair, a refusal, or a transport failure. A
     *   missing stored token is reported as a transport failure and
     *   sends nothing; [resume] is what tells the two apart
     */
    suspend fun refresh(): AuthResult<TokenResponse> =
        RENEWAL_LOCK.withLock {
            val stored = tokens.refreshToken() ?: return@withLock AuthResult.TransportFailure

            var credentialDead = false
            val result: AuthResult<TokenResponse> =
                call {
                    client.post("/v1/auth/refresh") { setBody(RefreshBody(stored)) }
                        .also { credentialDead = it.status in REFUSED_REFRESH_STATUSES }
                }

            when (result) {
                is AuthResult.Ok ->
                    tokens.save(result.value.accessToken, result.value.refreshToken)
                is AuthResult.Refused -> if (credentialDead) tokens.clear()
                AuthResult.TransportFailure -> Unit
            }
            result
        }

    /**
     * End a session on the server, revoking its whole token family, so a
     * copy of the refresh token taken before sign-out stops working
     * [audit C-21].
     *
     * **Best-effort, and never throws.** Signing out must work offline:
     * the caller clears local state whatever this returns.
     *
     * @param refreshToken The session's refresh token, read before clearing
     * @return Ok when the server acknowledged it; a transport failure for
     *   anything else, which the caller ignores
     */
    suspend fun logout(refreshToken: String): AuthResult<Unit> =
        try {
            val response = client.post("/v1/auth/logout") { setBody(RefreshBody(refreshToken)) }
            if (response.status.isSuccess()) AuthResult.Ok(Unit) else AuthResult.TransportFailure
        } catch (_: Exception) {
            AuthResult.TransportFailure
        }

    /**
     * Redeem the stored session at a cold start, and say what came of it.
     *
     * **The store is the witness, not the HTTP result.** After [refresh]
     * a cleared store means the credential is dead or was never there,
     * and a store still holding a token means its status is simply
     * unknown -- the phone is offline, or the server did not answer.
     * Reading the outcome back from the store keeps the one rule about
     * what ends a session in [refresh], rather than repeating it here
     * where it could drift.
     *
     * @return Renewed, unverified-but-kept, or ended
     */
    suspend fun resume(): SessionResume =
        when (refresh()) {
            is AuthResult.Ok -> SessionResume.RENEWED
            else ->
                if (tokens.refreshToken() == null) SessionResume.ENDED else SessionResume.UNVERIFIED
        }
}

/**
 * Run one request and map it to the three-way result.
 *
 * **The error envelope is decoded, never inferred from the status.**
 * `retryable` is a server-provided boolean because the client holds no
 * business logic: it is told whether to retry rather than deciding from
 * a status code [TC-9].
 *
 * A malformed error body is itself a refusal rather than a crash — a
 * server that answered with something unparseable has still answered,
 * and treating that as a transport failure would invite a retry against
 * a server that is responding.
 *
 * @param request The request to run
 * @return Ok, Refused with the envelope, or TransportFailure
 */
internal suspend inline fun <reified T> call(
    request: () -> HttpResponse,
): AuthResult<T> =
    try {
        val response = request()
        if (response.status.isSuccess()) {
            AuthResult.Ok(response.body<T>())
        } else {
            AuthResult.Refused(decodeEnvelope(response))
        }
    } catch (_: Exception) {
        // Every exception reaching here is a TRANSPORT failure: no
        // response arrived. A non-2xx is a response and is handled
        // above, so this arm cannot swallow a server refusal.
        AuthResult.TransportFailure
    }

/**
 * Decode an error envelope, falling back to a generic refusal.
 *
 * @param response The non-success response
 * @return The envelope the server sent, or a synthesized one
 */
suspend fun decodeEnvelope(response: HttpResponse): ErrorEnvelope =
    try {
        response.body<ErrorEnvelope>()
    } catch (_: Exception) {
        ErrorEnvelope(
            ErrorBody(
                code = "UNEXPECTED",
                retryable = false,
                messageKey = "error.unexpected",
            ),
        )
    }

/**
 * Run a request whose successful response body is discarded.
 *
 * **The sibling of [call], for the write side.** `call` deserialises
 * the body into `T`; these endpoints answer with a representation the
 * client does not need, and `AuthResult<Unit>` cannot be produced by
 * deserialising into `Unit`. Written once here rather than repeated
 * per method: the shape was already copied four times across the
 * roster and batches repositories, and a copy that drifts is how one
 * write starts treating a refusal as a success.
 *
 * The three outcomes are the same ones [call] produces, for the same
 * reason — a refusal carries a server-set `retryable`, and a transport
 * failure has no envelope to read it from.
 *
 * @param request The request to run
 * @return Ok(Unit), Refused with the envelope, or TransportFailure
 */
internal suspend inline fun callDiscardingBody(
    request: () -> HttpResponse,
): AuthResult<Unit> =
    try {
        val response = request()
        if (response.status.isSuccess()) {
            AuthResult.Ok(Unit)
        } else {
            AuthResult.Refused(decodeEnvelope(response))
        }
    } catch (_: Exception) {
        // Every exception reaching here is a TRANSPORT failure: no
        // response arrived. A non-2xx is a response and is handled
        // above, so this arm cannot swallow a server refusal.
        AuthResult.TransportFailure
    }
