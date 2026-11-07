package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.auth.SessionResume
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.get
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The cold-start refresh: what ends a session, what keeps it, and that
 * it shares one lock with the mid-session renewal [FE-1, FE-3].
 *
 * Written from the acceptance criteria: only a definitive refusal of
 * the credential sends a teacher to sign-in; no answer, or a server
 * failing to answer, keeps the session; and no refresh token is ever
 * presented twice, whichever of the two redeemers runs first.
 */
class SessionResumeTest {

    private companion object {
        const val BASE = "https://staging.example"
        const val REFUSED =
            """{"error":{"code":"X","message_key":"auth.token.not_valid","retryable":false}}"""
        const val PAIR = """{"access_token":"fresh","refresh_token":"r2","expires_in":900}"""
    }

    private val json = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

    private fun repository(engine: MockEngine, tokens: TokenStore): HttpAuthRepository =
        HttpAuthRepository(ApiClient.build(BASE, engine, tokens), tokens)

    @Test
    fun `an offline cold start keeps the session, unverified`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("stale", "r1") }
        val engine = MockEngine { throw java.io.IOException("no route") }

        val outcome = repository(engine, tokens).resume()

        assertEquals(SessionResume.UNVERIFIED, outcome)
        assertEquals("stale", tokens.accessToken())
        assertEquals("r1", tokens.refreshToken())
    }

    @Test
    fun `a server error or a rate limit at a cold start keeps the session`() = runTest {
        // These used to CLEAR the store: any non-2xx was read as a
        // refusal, so a cold start during an outage signed the teacher
        // out and cost an SMS to recover. Neither says anything about
        // the credential.
        for (status in listOf(HttpStatusCode.ServiceUnavailable, HttpStatusCode.TooManyRequests)) {
            val tokens = TokenStore.InMemory().apply { save("stale", "r1") }
            val engine = MockEngine { respond(REFUSED, status, json) }

            val outcome = repository(engine, tokens).resume()

            assertEquals(SessionResume.UNVERIFIED, outcome, status.toString())
            assertEquals("r1", tokens.refreshToken(), status.toString())
        }
    }

    @Test
    fun `a refused refresh at a cold start ends the session and clears it`() = runTest {
        for (status in listOf(HttpStatusCode.BadRequest, HttpStatusCode.Unauthorized, HttpStatusCode.Forbidden)) {
            val tokens = TokenStore.InMemory().apply { save("stale", "replayed") }
            val engine = MockEngine { respond(REFUSED, status, json) }

            val outcome = repository(engine, tokens).resume()

            assertEquals(SessionResume.ENDED, outcome, status.toString())
            assertNull(tokens.accessToken(), status.toString())
            assertNull(tokens.refreshToken(), status.toString())
        }
    }

    @Test
    fun `no stored session ends without asking the server`() = runTest {
        val tokens = TokenStore.InMemory()
        val engine = MockEngine { respond(PAIR, HttpStatusCode.OK, json) }

        val outcome = repository(engine, tokens).resume()

        assertEquals(SessionResume.ENDED, outcome)
        assertEquals(0, engine.requestHistory.size)
    }

    @Test
    fun `a renewed session stores the new pair`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("stale", "r1") }
        val engine = MockEngine { respond(PAIR, HttpStatusCode.OK, json) }

        val outcome = repository(engine, tokens).resume()

        assertEquals(SessionResume.RENEWED, outcome)
        assertEquals("fresh", tokens.accessToken())
        assertEquals("r2", tokens.refreshToken())
    }

    @Test
    fun `the cold-start refresh and a mid-session renewal never present one refresh token twice`() =
        runTest {
            // **The race FE-3 names.** The start-up refresh ran outside
            // the renewal lock, so a screen whose request expired at the
            // same moment redeemed the same refresh token. The server
            // rotates on first use and reads the second as theft, ending
            // the whole token family. This server does exactly that.
            val server = RotatingServer()
            val tokens = TokenStore.InMemory().apply { save("a0", "r0") }
            val engine = MockEngine { request -> server.answer(this, request) }
            val client = ApiClient.build(BASE, engine, tokens)
            val repository = HttpAuthRepository(client, tokens)

            val resumed = async { repository.resume() }
            val reads = List(3) { async { client.get("/v1/me").status } }

            assertEquals(SessionResume.RENEWED, resumed.await())
            assertEquals(List(3) { HttpStatusCode.OK }, reads.awaitAll())
            assertEquals(emptyList(), server.reused, "a refresh token was presented twice")
            assertEquals(server.current(), tokens.refreshToken())
        }

    /**
     * A refresh endpoint that rotates on use and refuses a reused token,
     * as the real one does, and a read that accepts any token it issued.
     */
    private class RotatingServer {
        private var generation = 0
        private val issuedAccess = mutableSetOf<String>()

        /** Every refresh token presented after it was already rotated out. */
        val reused = mutableListOf<String>()

        private val json = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

        @Synchronized
        fun current(): String = "r$generation"

        @Synchronized
        fun answer(
            scope: io.ktor.client.engine.mock.MockRequestHandleScope,
            request: io.ktor.client.request.HttpRequestData,
        ): io.ktor.client.request.HttpResponseData =
            if (request.url.encodedPath == "/v1/auth/refresh") {
                val presented =
                    Regex(""""refresh_token":"([^"]+)"""")
                        .find((request.body as TextContent).text)
                        ?.groupValues
                        ?.get(1)
                if (presented == current()) {
                    generation++
                    issuedAccess += "a$generation"
                    scope.respond(
                        """{"access_token":"a$generation","refresh_token":"r$generation","expires_in":900}""",
                        HttpStatusCode.OK,
                        json,
                    )
                } else {
                    reused += presented.orEmpty()
                    scope.respond(REFUSED, HttpStatusCode.Unauthorized, json)
                }
            } else {
                val bearer = request.headers[HttpHeaders.Authorization]?.removePrefix("Bearer ")
                if (bearer in issuedAccess) {
                    scope.respond("""{"ok":true}""", HttpStatusCode.OK, json)
                } else {
                    scope.respond(REFUSED, HttpStatusCode.Unauthorized, json)
                }
            }
    }

    @Test
    fun `signing out revokes the session on the server`() = runTest {
        // C-21: sign-out used to clear only the phone, leaving a copied
        // refresh token redeemable for its whole lifetime.
        val tokens = TokenStore.InMemory().apply { save("access", "r1") }
        var sent: String? = null
        var path: String? = null
        val engine =
            MockEngine { request ->
                path = request.url.encodedPath
                sent = (request.body as TextContent).text
                respond("", HttpStatusCode.NoContent)
            }

        val acknowledged = repository(engine, tokens).logout("r1")

        assertEquals(AuthResult.Ok(Unit), acknowledged)
        assertEquals("/v1/auth/logout", path)
        assertEquals("""{"refresh_token":"r1"}""", sent)
    }

    @Test
    fun `signing out offline never throws`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("access", "r1") }
        val engine = MockEngine { throw java.io.IOException("no route") }

        assertEquals(AuthResult.TransportFailure, repository(engine, tokens).logout("r1"))
    }
}
