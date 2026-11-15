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

    // --- U3: usernames and contacts [FR5.4, FR7.1, FR8.2, FR8.4; NFR3.1] ------

    /** What one request looked like on the wire. */
    private data class Wire(val method: String, val path: String, val query: String, val body: String?)

    private fun recording(status: HttpStatusCode, reply: String, seen: MutableList<Wire>): HttpAccountRepository {
        val tokens = TokenStore.InMemory().apply { save("a", "r") }
        val engine =
            MockEngine { request ->
                seen +=
                    Wire(
                        request.method.value,
                        request.url.encodedPath,
                        request.url.encodedQuery,
                        (request.body as? TextContent)?.text,
                    )
                respond(reply, status, json)
            }
        return HttpAccountRepository(ApiClient.build("https://staging.example", engine, tokens), tokens)
    }

    @Test
    fun `the authenticated lookup posts the name in a body with no query string`() = runTest {
        val seen = mutableListOf<Wire>()

        val ok =
            assertIs<AuthResult.Ok<UsernameAvailabilityDto>>(
                recording(HttpStatusCode.OK, """{"status":"available"}""", seen).checkUsername(" nadia_k "),
            )

        assertEquals(listOf(Wire("POST", "/v1/me/username-availability", "", """{"username":"nadia_k"}""")), seen)
        assertEquals("available", ok.value.status)
    }

    @Test
    fun `a first choice sends no password, a rename sends one, and neither puts the name in the URL`() = runTest {
        val seen = mutableListOf<Wire>()
        val repository =
            recording(HttpStatusCode.OK, """{"username":"Nadia_K","next_change_at":"2026-12-14T10:00:00Z"}""", seen)

        repository.changeUsername("nadia_k", null)
        val renamed = assertIs<AuthResult.Ok<UsernameChangeDto>>(repository.changeUsername("Nadia_K", "correct horse"))

        assertEquals(
            listOf(
                Wire("PUT", "/v1/me/username", "", """{"username":"nadia_k"}"""),
                Wire("PUT", "/v1/me/username", "", """{"username":"Nadia_K","password":"correct horse"}"""),
            ),
            seen,
        )
        assertEquals("2026-12-14T10:00:00Z", renamed.value.nextChangeAt)
    }

    @Test
    fun `a rename too soon comes back with its key and the date`() = runTest {
        val refused =
            assertIs<AuthResult.Refused>(
                recording(
                    HttpStatusCode.Conflict,
                    """{"error":{"code":"X","retryable":false,"message_key":"account.username.change_too_soon",""" +
                        """"details":{"next_change_at":"2026-12-14T10:00:00Z"}}}""",
                    mutableListOf(),
                ).changeUsername("nadia_k2", "correct horse"),
            )

        assertEquals("account.username.change_too_soon", refused.envelope.error.messageKey)
        assertEquals("2026-12-14T10:00:00Z", refused.envelope.error.details?.get("next_change_at"))
    }

    @Test
    fun `a replacement posts the new contact with the password`() = runTest {
        val seen = mutableListOf<Wire>()

        recording(HttpStatusCode.OK, """{"status":"requested"}""", seen)
            .replaceContact(Identifier.phone("01811223344"), "correct horse")

        assertEquals(
            listOf(Wire("POST", "/v1/me/contact", "", """{"phone":"01811223344","password":"correct horse"}""")),
            seen,
        )
    }

    @Test
    fun `a removal posts the kind and the password`() = runTest {
        val seen = mutableListOf<Wire>()

        val me =
            assertIs<AuthResult.Ok<MeDto>>(
                recording(HttpStatusCode.OK, """{"lenses":[],"phone":"+8801711111111","email":null}""", seen)
                    .removeContact(com.shikkhokplus.app.core.model.IdentifierKind.EMAIL, "correct horse"),
            )

        assertEquals(
            listOf(Wire("POST", "/v1/me/contact/remove", "", """{"kind":"email","password":"correct horse"}""")),
            seen,
        )
        assertEquals(null, me.value.email)
    }

    @Test
    fun `the last contact is refused with its key`() = runTest {
        val refused =
            assertIs<AuthResult.Refused>(
                recording(
                    HttpStatusCode.Conflict,
                    """{"error":{"code":"X","retryable":false,"message_key":"account.contact.last_one"}}""",
                    mutableListOf(),
                ).removeContact(com.shikkhokplus.app.core.model.IdentifierKind.PHONE, "correct horse"),
            )

        assertEquals("account.contact.last_one", refused.envelope.error.messageKey)
    }

    @Test
    fun `a username change writes nothing to the token store`() = runTest {
        // FR7.5: a rename ends no session and returns no tokens.
        val tokens = TokenStore.InMemory().apply { save("a", "r") }
        val engine = MockEngine { respond("""{"username":"Nadia_K","next_change_at":null}""", HttpStatusCode.OK, json) }

        HttpAccountRepository(ApiClient.build("https://staging.example", engine, tokens), tokens)
            .changeUsername("Nadia_K", "correct horse")

        assertEquals("a", tokens.accessToken())
        assertEquals("r", tokens.refreshToken())
    }
}
