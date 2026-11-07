package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Signing in when the account has two-step verification on [0028]: what
 * the token store holds after each step, and that a lapsed challenge is
 * an answer to the sign-in, not an expired session.
 */
class HttpAuthSecondStepTest {

    private val json = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

    private val pair = """{"access_token":"a.b.c","refresh_token":"r1","expires_in":900}"""

    private val expired =
        """{"error":{"code":"MFA_CHALLENGE_EXPIRED","retryable":false,"message_key":"mfa.challenge_expired"}}"""

    @Test
    fun `an account without the second step is signed in by the SMS code, as before`() = runTest {
        val tokens = TokenStore.InMemory()
        val engine = MockEngine { respond(pair.replace("}", ""","mfa_required":false}"""), HttpStatusCode.OK, json) }

        val ok =
            assertIs<AuthResult.Ok<VerifyResponse>>(
                HttpAuthRepository(ApiClient.build(BASE, engine, tokens), tokens).verify("01711234567", "123456"),
            )

        assertEquals(false, ok.value.mfaRequired)
        assertEquals("a.b.c", tokens.accessToken())
        assertEquals("r1", tokens.refreshToken())
    }

    @Test
    fun `an account with the second step stores nothing until it is done`() = runTest {
        val tokens = TokenStore.InMemory()
        val engine =
            MockEngine {
                val body = """{"mfa_required":true,"mfa_challenge":"chal","mfa_expires_in":300}"""
                respond(body, HttpStatusCode.OK, json)
            }

        val ok =
            assertIs<AuthResult.Ok<VerifyResponse>>(
                HttpAuthRepository(ApiClient.build(BASE, engine, tokens), tokens).verify("01711234567", "123456"),
            )

        assertEquals("chal", ok.value.mfaChallenge)
        assertNull(tokens.accessToken(), "a half-finished sign-in must not look signed in")
        assertNull(tokens.refreshToken())
    }

    @Test
    fun `the second step posts the challenge and the code, and stores the pair`() = runTest {
        val tokens = TokenStore.InMemory()
        val engine = MockEngine { respond(pair, HttpStatusCode.OK, json) }
        val repository = HttpAuthRepository(ApiClient.build(BASE, engine, tokens), tokens)

        assertIs<AuthResult.Ok<TokenResponse>>(repository.verifySecondStep("chal", "123456", null))

        val request = engine.requestHistory.single()
        assertEquals("/v1/auth/mfa", request.url.encodedPath)
        assertEquals("""{"challenge":"chal","code":"123456"}""", (request.body as TextContent).text)
        assertEquals("a.b.c", tokens.accessToken())
    }

    @Test
    fun `a recovery code goes in its own field`() = runTest {
        val tokens = TokenStore.InMemory()
        val engine = MockEngine { respond(pair, HttpStatusCode.OK, json) }

        HttpAuthRepository(ApiClient.build(BASE, engine, tokens), tokens).verifySecondStep("chal", null, "ABCDE-FGHJK")

        assertEquals(
            """{"challenge":"chal","recovery_code":"ABCDE-FGHJK"}""",
            (engine.requestHistory.single().body as TextContent).text,
        )
    }

    @Test
    fun `a lapsed challenge's 401 renews nothing and ends no session`() = runTest {
        // **The defect this guards.** A 401 anywhere else means an expired
        // access token, and the client answers it by redeeming the refresh
        // token -- ending the session when that is refused. Here nobody is
        // signed in yet, and the 401 means only "start the sign-in again".
        // Even with a stale pair still in the store, the refusal must come
        // back to the sign-in screen untouched.
        val tokens = TokenStore.InMemory().apply { save("stale", "r-old") }
        var ended = 0
        val engine = MockEngine { respond(expired, HttpStatusCode.Unauthorized, json) }
        val client = ApiClient.build(BASE, engine, tokens, onSessionEnded = { ended++ })

        val result = HttpAuthRepository(client, tokens).verifySecondStep("chal", "123456", null)
        val refused = assertIs<AuthResult.Refused>(result)

        assertEquals("mfa.challenge_expired", refused.envelope.error.messageKey)
        assertEquals(listOf("/v1/auth/mfa"), engine.requestHistory.map { it.url.encodedPath }, "no refresh was tried")
        assertEquals(0, ended, "no session was ended")
        assertEquals("stale", tokens.accessToken())
        assertEquals("r-old", tokens.refreshToken())
    }

    @Test
    fun `a signed-out second step carries no bearer token`() = runTest {
        val tokens = TokenStore.InMemory()
        val engine = MockEngine { respond(expired, HttpStatusCode.Unauthorized, json) }

        HttpAuthRepository(ApiClient.build(BASE, engine, tokens), tokens).verifySecondStep("chal", "123456", null)

        assertTrue(engine.requestHistory.single().headers[HttpHeaders.Authorization] == null)
        assertNull(tokens.accessToken())
    }

    private companion object {
        const val BASE = "https://staging.example"
    }
}
