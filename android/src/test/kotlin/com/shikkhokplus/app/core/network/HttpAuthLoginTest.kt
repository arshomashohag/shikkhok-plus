package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * The one-field sign-in and the verify replacement, on the wire [FR2.2,
 * FR4.1; NFR1.2, NFR3.1].
 *
 * The sign-in body carries `login` and NO `phone` or `email` key, so the
 * request shape says nothing about what the person meant; and nothing
 * typed ever goes in the URL.
 */
class HttpAuthLoginTest {

    private val json = headersOf("Content-Type", "application/json")

    private class Seen {
        var method: HttpMethod? = null
        var path: String? = null
        var query: String? = null
        var body: String? = null
    }

    private fun repository(status: HttpStatusCode, reply: String, seen: Seen): HttpAuthRepository {
        val engine =
            MockEngine { request ->
                seen.method = request.method
                seen.path = request.url.encodedPath
                seen.query = request.url.encodedQuery
                seen.body = (request.body as? TextContent)?.text
                respond(reply, status, json)
            }
        val tokens = TokenStore.InMemory()
        return HttpAuthRepository(ApiClient.build("https://staging.example", engine, tokens), tokens)
    }

    private val pair = """{"access_token":"a.b.c","refresh_token":"r1","expires_in":900,"mfa_required":false}"""

    @Test
    fun `a sign-in sends login and no phone or email, with no query string`() = runTest {
        val seen = Seen()

        assertIs<AuthResult.Ok<VerifyResponse>>(
            repository(HttpStatusCode.OK, pair, seen).signIn("  Rahim.Uddin ", "correct horse"),
        )

        assertEquals(HttpMethod.Post, seen.method)
        assertEquals("/v1/auth/password", seen.path)
        assertEquals("", seen.query)
        val body = Json.parseToJsonElement(seen.body.orEmpty()).jsonObject
        assertEquals(setOf("login", "password"), body.keys)
        assertEquals("\"Rahim.Uddin\"", body.getValue("login").toString())
    }

    @Test
    fun `a number typed into the field is still sent as login`() = runTest {
        val seen = Seen()

        repository(HttpStatusCode.OK, pair, seen).signIn("01711234567", "correct horse")

        assertEquals("""{"password":"correct horse","login":"01711234567"}""", seen.body)
    }

    @Test
    fun `a refused sign-in comes back with its key`() = runTest {
        val seen = Seen()
        val refused =
            assertIs<AuthResult.Refused>(
                repository(
                    HttpStatusCode.BadRequest,
                    """{"error":{"code":"X","retryable":false,"message_key":"auth.password.wrong"}}""",
                    seen,
                ).signIn("nobody_here", "correct horse"),
            )

        assertEquals("auth.password.wrong", refused.envelope.error.messageKey)
    }

    @Test
    fun `a first verify carries no username`() = runTest {
        val seen = Seen()

        repository(HttpStatusCode.OK, """{"password_setup_token":"t"}""", seen)
            .verify(Identifier.phone("01711234567"), "123456")

        assertEquals("""{"phone":"01711234567","code":"123456"}""", seen.body)
    }

    @Test
    fun `a replacement verify carries the same code and the new name, trimmed`() = runTest {
        val seen = Seen()

        repository(HttpStatusCode.OK, """{"password_setup_token":"t"}""", seen)
            .verify(Identifier.email("rafi@example.com"), "123456", " nadia_k2 ")

        assertEquals("/v1/auth/verify", seen.path)
        assertEquals("", seen.query)
        assertEquals("""{"email":"rafi@example.com","code":"123456","username":"nadia_k2"}""", seen.body)
    }

    @Test
    fun `an unavailable name at verify comes back with its key`() = runTest {
        val seen = Seen()
        val refused =
            assertIs<AuthResult.Refused>(
                repository(
                    HttpStatusCode.Conflict,
                    """{"error":{"code":"X","retryable":false,"message_key":"account.username.unavailable"}}""",
                    seen,
                ).verify(Identifier.phone("01711234567"), "123456"),
            )

        assertEquals("account.username.unavailable", refused.envelope.error.messageKey)
    }
}
