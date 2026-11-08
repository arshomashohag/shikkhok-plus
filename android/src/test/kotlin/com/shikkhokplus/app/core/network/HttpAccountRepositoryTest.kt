package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * The signed-in password and contacts, over HTTP: what is sent, and that
 * a password change replaces the stored pair the server just ended.
 */
class HttpAccountRepositoryTest {

    private val json = headersOf("Content-Type", "application/json")

    @Test
    fun `a password change replaces the stored pair with the new one`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("old-access", "old-refresh") }
        var sent: String? = null
        val engine =
            MockEngine { request ->
                sent = (request.body as TextContent).text
                respond(
                    """{"access_token":"new-access","refresh_token":"new-refresh","expires_in":900}""",
                    HttpStatusCode.OK,
                    json,
                )
            }
        val repository = HttpAccountRepository(ApiClient.build("https://staging.example", engine, tokens), tokens)

        assertIs<AuthResult.Ok<TokenResponse>>(repository.setPassword("old horse", "correct horse"))

        assertEquals("""{"current_password":"old horse","new_password":"correct horse"}""", sent)
        assertEquals("new-access", tokens.accessToken())
        assertEquals("new-refresh", tokens.refreshToken())
    }

    @Test
    fun `a first password leaves the current one out of the body`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("a", "r") }
        var sent: String? = null
        val engine =
            MockEngine { request ->
                sent = (request.body as TextContent).text
                respond("""{"access_token":"n","refresh_token":"m","expires_in":900}""", HttpStatusCode.OK, json)
            }

        HttpAccountRepository(ApiClient.build("https://staging.example", engine, tokens), tokens)
            .setPassword(null, "correct horse")

        assertEquals("""{"new_password":"correct horse"}""", sent)
    }

    @Test
    fun `a refused change keeps the stored pair`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("a", "r") }
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"X","retryable":false,"message_key":"auth.password.wrong"}}""",
                    HttpStatusCode.BadRequest,
                    json,
                )
            }

        val refused =
            assertIs<AuthResult.Refused>(
                HttpAccountRepository(ApiClient.build("https://staging.example", engine, tokens), tokens)
                    .setPassword("guess", "correct horse"),
            )

        assertEquals("auth.password.wrong", refused.envelope.error.messageKey)
        assertEquals("a", tokens.accessToken())
        assertEquals("r", tokens.refreshToken())
    }

    @Test
    fun `adding a contact posts exactly one identifier, then the code`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("a", "r") }
        val sent = mutableListOf<Pair<String, String>>()
        val engine =
            MockEngine { request ->
                sent += request.url.encodedPath to (request.body as TextContent).text
                val body =
                    if (request.url.encodedPath.endsWith("verify")) {
                        """{"lenses":[],"phone":null,"email":"rafi@example.com","has_password":true}"""
                    } else {
                        """{"status":"requested"}"""
                    }
                respond(body, HttpStatusCode.OK, json)
            }
        val repository = HttpAccountRepository(ApiClient.build("https://staging.example", engine, tokens), tokens)

        repository.requestContact(Identifier.email("rafi@example.com"))
        val me =
            assertIs<AuthResult.Ok<MeDto>>(repository.verifyContact(Identifier.email("rafi@example.com"), "123456"))

        assertEquals(
            listOf(
                "/v1/me/contact" to """{"email":"rafi@example.com"}""",
                "/v1/me/contact/verify" to """{"email":"rafi@example.com","code":"123456"}""",
            ),
            sent,
        )
        assertEquals("rafi@example.com", me.value.email)
    }
}
