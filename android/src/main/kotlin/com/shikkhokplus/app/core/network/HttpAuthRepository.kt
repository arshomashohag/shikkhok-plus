package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthRepository
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable

@Serializable
private data class IssueBody(val phone: String)

@Serializable
private data class VerifyBody(val phone: String, val code: String)

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

    override suspend fun issue(phone: String): AuthResult<IssueResponse> =
        call { client.post("/v1/auth/otp") { setBody(IssueBody(phone)) } }

    override suspend fun verify(
        phone: String,
        code: String,
    ): AuthResult<TokenResponse> {
        val result: AuthResult<TokenResponse> =
            call { client.post("/v1/auth/verify") { setBody(VerifyBody(phone, code)) } }
        if (result is AuthResult.Ok) {
            tokens.save(result.value.accessToken, result.value.refreshToken)
        }
        return result
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
