package com.shikkhokplus.app.core.network

import io.ktor.client.HttpClient
import io.ktor.client.call.HttpClientCall
import io.ktor.client.plugins.HttpSend
import io.ktor.client.plugins.Sender
import io.ktor.client.plugins.plugin
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.isSuccess
import io.ktor.http.takeFrom
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Renews an expired session in the background, mid-use.
 *
 * **Reported from a device.** An access token lives fifteen minutes, and
 * the stored refresh token was only redeemed when the app STARTED. A
 * person who kept the app open past that window had every request
 * refused with nothing to recover it, and was stuck until they killed
 * the app and opened it again -- which is when the refresh ran.
 *
 * So an expired request now does here what a cold start does: redeem
 * the refresh token for a fresh pair, then repeat the request with it.
 * The person sees nothing.
 *
 * **One renewal at a time** [token family]. A screen fires several
 * requests at once and all of them expire together. Redeeming the same
 * refresh token twice presents a token the server has already rotated
 * out, which it reads as theft and answers by killing the whole token
 * family -- so concurrent renewals would sign the person out on the
 * very path meant to keep them in. A mutex serialises them, and every
 * request after the first finds the token already replaced and simply
 * retries with it.
 *
 * **A refused renewal ends the session; an unreachable one does not.**
 * Refused -- a 400, 401 or 403 -- means the credential is dead, and
 * clearing it routes the person to sign-in rather than leaving them on
 * a screen that can do nothing. A transport failure, a 5xx or a 429
 * says nothing about the token, so the store is left alone and the
 * original 401 goes back to the caller.
 *
 * @property baseUrl The backend's origin
 * @property tokens Where the pair is read and written
 * @property onSessionEnded Called once when a renewal is refused
 * @property appVersion The sanitised app version the refresh carries,
 *   or null for none; see [ClientPlatform]
 */
class SessionRenewal(
    private val baseUrl: String,
    private val tokens: TokenStore,
    private val onSessionEnded: () -> Unit,
    private val appVersion: String? = null,
) {
    /**
     * Attach renewal to a client's send pipeline.
     *
     * @param client The client whose expired requests are renewed
     */
    fun install(client: HttpClient) {
        client.plugin(HttpSend).intercept { request -> sendRenewing(request) }
    }

    /**
     * Send one request, renewing and repeating it once if it expired.
     *
     * @param request The request to send
     * @return The call, repeated with a fresh token when one was got
     */
    private suspend fun Sender.sendRenewing(request: HttpRequestBuilder): HttpClientCall {
        val sent = request.headers[HttpHeaders.Authorization]?.removePrefix(BEARER)
        val call = execute(request)

        // Only a request that CARRIED a token can have an expired one,
        // and the auth routes are never renewed: a refused refresh or
        // verify is an answer, and renewing it would loop.
        val expired =
            call.response.status == HttpStatusCode.Unauthorized &&
                sent != null &&
                !request.url.buildString().contains(AUTH_PATH)
        if (!expired) return call

        val fresh = renew(sent!!) { refreshToken -> redeem(refreshToken) } ?: return call
        request.headers[HttpHeaders.Authorization] = BEARER + fresh
        return execute(request)
    }

    /**
     * Produce a current access token, renewing at most once at a time.
     *
     * @param expired The token the refused request carried
     * @param redeem Exchanges a refresh token for a new pair
     * @return A token to retry with, or null when there is none
     */
    internal suspend fun renew(
        expired: String,
        redeem: suspend (String) -> Redeemed,
    ): String? =
        RENEWAL_LOCK.withLock {
            val current = tokens.accessToken() ?: return@withLock null

            // Another request renewed while this one waited: use its
            // result rather than redeeming a token it already rotated.
            if (current != expired) return@withLock current

            val refreshToken = tokens.refreshToken() ?: return@withLock null
            when (val result = redeem(refreshToken)) {
                is Redeemed.Pair -> {
                    tokens.save(result.access, result.refresh)
                    result.access
                }
                Redeemed.Refused -> {
                    tokens.clear()
                    onSessionEnded()
                    null
                }
                Redeemed.Unreachable -> null
            }
        }

    /**
     * Ask the server for a fresh pair.
     *
     * Built in full here rather than through the client's defaults:
     * this runs inside the send stage, after the request stage that
     * applies the base URL and serialises bodies, so neither happens
     * for it -- and nor do the platform headers, which is why they are
     * written here too. A refresh is where the server records which app
     * the account uses; leaving them off this one path would record the
     * renewing half of every session as no app at all.
     *
     * @param refreshToken The stored refresh token
     * @return The new pair, a refusal, or no answer at all
     */
    private suspend fun Sender.redeem(refreshToken: String): Redeemed =
        try {
            val body = ApiClient.json.encodeToString(RefreshRequest.serializer(), RefreshRequest(refreshToken))
            val builder =
                HttpRequestBuilder().apply {
                    method = HttpMethod.Post
                    url.takeFrom(baseUrl.trimEnd('/') + REFRESH_PATH)
                    ClientPlatform.applyTo(headers, appVersion)
                    setBody(TextContent(body, ContentType.Application.Json))
                }
            val response = execute(builder).response
            when {
                response.status.isSuccess() -> {
                    val pair = ApiClient.json.decodeFromString(TokenResponse.serializer(), response.bodyAsText())
                    Redeemed.Pair(pair.accessToken, pair.refreshToken)
                }
                // Only these say the credential itself is dead. A 5xx or a
                // 429 is the server not answering the question, and signing
                // the person out on it would end every session in an outage.
                response.status in REFUSED_REFRESH_STATUSES -> Redeemed.Refused
                else -> Redeemed.Unreachable
            }
        } catch (_: Exception) {
            // No response arrived, so the token's status is unknown.
            Redeemed.Unreachable
        }

    /** What redeeming a refresh token came to. */
    sealed interface Redeemed {
        /**
         * A fresh pair.
         *
         * @property access The new access token
         * @property refresh The new refresh token
         */
        data class Pair(val access: String, val refresh: String) : Redeemed

        /** The server answered 400, 401 or 403: the credential is dead. */
        data object Refused : Redeemed

        /** No answer, a 5xx or a 429: the credential's status is unknown. */
        data object Unreachable : Redeemed
    }

    @Serializable
    private data class RefreshRequest(
        @SerialName("refresh_token") val refreshToken: String,
    )

    private companion object {
        const val BEARER = "Bearer "
        const val AUTH_PATH = "/v1/auth/"
        const val REFRESH_PATH = "/v1/auth/refresh"
    }
}

/**
 * One lock for EVERY redemption of the refresh token in the process.
 *
 * The app and the background unread check each build their own client;
 * separate locks let both redeem the same refresh token, which the
 * server reads as theft and answers by ending the session.
 *
 * **Top-level rather than private to [SessionRenewal]**, because the
 * cold-start refresh in [HttpAuthRepository.refresh] is the other
 * redeemer. It used to run outside this lock, so a screen's expired
 * request renewing at the same moment as the start-up refresh presented
 * the same refresh token twice -- the exact race the lock exists to
 * close, on the one path it did not cover.
 */
internal val RENEWAL_LOCK: Mutex = Mutex()

/**
 * The answers to a refresh that mean the credential itself is dead.
 *
 * Shared by both redeemers so a cold start and a mid-session renewal
 * cannot disagree about what ends a session: a 5xx or a 429 is the
 * server not answering the question, and treating it as a refusal would
 * sign every teacher out during an outage.
 */
internal val REFUSED_REFRESH_STATUSES: Set<HttpStatusCode> =
    setOf(HttpStatusCode.BadRequest, HttpStatusCode.Unauthorized, HttpStatusCode.Forbidden)
