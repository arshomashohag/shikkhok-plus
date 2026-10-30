package com.shikkhokplus.app.core.network

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.client.request.get
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * An expired session is renewed mid-use, the way a cold start renews it.
 *
 * Reported from a device: once the fifteen-minute access token expired,
 * every request was refused until the app was killed and reopened.
 */
class SessionRenewalTest {

    private companion object {
        const val REFUSED =
            """{"error":{"code":"X","message_key":"auth.token.not_valid","retryable":false}}"""
    }

    private val json = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

    private fun MockRequestHandleScope.answer(
        request: HttpRequestData,
        refreshStatus: HttpStatusCode,
    ): HttpResponseData =
        when (request.url.encodedPath) {
            "/v1/auth/refresh" ->
                if (refreshStatus == HttpStatusCode.OK) {
                    respond(
                        """{"access_token":"fresh","refresh_token":"r2","expires_in":900}""",
                        HttpStatusCode.OK,
                        json,
                    )
                } else {
                    respond(REFUSED, refreshStatus, json)
                }
            else ->
                if (request.headers[HttpHeaders.Authorization] == "Bearer fresh") {
                    respond("""{"ok":true}""", HttpStatusCode.OK, json)
                } else {
                    respond(REFUSED, HttpStatusCode.Unauthorized, json)
                }
        }

    @Test
    fun `an expired request is renewed and repeated with no prompt`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("stale", "r1") }
        val engine = MockEngine { answer(it, HttpStatusCode.OK) }
        val client = ApiClient.build("https://staging.example", engine, tokens)

        val response = client.get("/v1/me")

        assertEquals(HttpStatusCode.OK, response.status)
        assertEquals("fresh", tokens.accessToken())
        assertEquals("r2", tokens.refreshToken())
    }

    @Test
    fun `concurrent expired requests redeem the refresh token once`() = runTest {
        // Redeeming the same refresh token twice is what the server reads
        // as theft, and it would end the session it is meant to keep.
        val tokens = TokenStore.InMemory().apply { save("stale", "r1") }
        val engine = MockEngine { answer(it, HttpStatusCode.OK) }
        val client = ApiClient.build("https://staging.example", engine, tokens)

        val statuses = List(4) { async { client.get("/v1/me").status } }.awaitAll()

        assertEquals(List(4) { HttpStatusCode.OK }, statuses)
        val refreshes = engine.requestHistory.count { it.url.encodedPath == "/v1/auth/refresh" }
        assertEquals(1, refreshes)
    }

    @Test
    fun `a refused renewal ends the session`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("stale", "r1") }
        var ended = 0
        val engine = MockEngine { answer(it, HttpStatusCode.Unauthorized) }
        val client =
            ApiClient.build("https://staging.example", engine, tokens, onSessionEnded = { ended++ })

        val response = client.get("/v1/me")

        assertEquals(HttpStatusCode.Unauthorized, response.status)
        assertEquals(1, ended)
        assertNull(tokens.accessToken())
    }

    @Test
    fun `an unreachable renewal keeps the stored session`() = runTest {
        // No answer says nothing about the token: discarding a valid
        // session because the network dropped would force a new code.
        val tokens = TokenStore.InMemory().apply { save("stale", "r1") }
        var ended = 0
        val engine =
            MockEngine { request ->
                if (request.url.encodedPath == "/v1/auth/refresh") {
                    throw java.io.IOException("offline")
                }
                answer(request, HttpStatusCode.OK)
            }
        val client =
            ApiClient.build("https://staging.example", engine, tokens, onSessionEnded = { ended++ })

        val response = client.get("/v1/me")

        assertEquals(HttpStatusCode.Unauthorized, response.status)
        assertEquals(0, ended)
        assertEquals("r1", tokens.refreshToken())
    }

    @Test
    fun `a request with no token is never renewed`() = runTest {
        val tokens = TokenStore.InMemory()
        val engine = MockEngine { answer(it, HttpStatusCode.OK) }
        val client = ApiClient.build("https://staging.example", engine, tokens)

        client.get("/v1/me")

        assertEquals(0, engine.requestHistory.count { it.url.encodedPath == "/v1/auth/refresh" })
    }
}
