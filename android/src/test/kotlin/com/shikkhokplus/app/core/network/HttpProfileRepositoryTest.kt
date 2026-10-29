package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/** The profile repository's deletion call, over a mock transport. */
class HttpProfileRepositoryTest {

    private fun repo(engine: MockEngine) =
        HttpProfileRepository(
            ApiClient.build("https://staging.example", engine, TokenStore.InMemory()),
        )

    @Test
    fun `deletion is a DELETE of the caller's own row`() = runTest {
        // No id in the path: the token names the account, so there is
        // nothing a caller could point at someone else [BR3.1].
        val engine =
            MockEngine {
                respond(
                    """{"deleted":true}""",
                    HttpStatusCode.OK,
                    headersOf("Content-Type", ContentType.Application.Json.toString()),
                )
            }

        val result = repo(engine).deleteAccount()

        assertEquals(AuthResult.Ok(Unit), result)
        val sent = engine.requestHistory.single()
        assertEquals(HttpMethod.Delete, sent.method)
        assertEquals("/v1/me", sent.url.encodedPath)
    }

    @Test
    fun `a refusal keeps the server's message`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """
                    {"error":{"code":"NOT_AVAILABLE",
                    "message_key":"authz.lens.not_available","retryable":false}}
                    """.trimIndent(),
                    HttpStatusCode.Conflict,
                    headersOf("Content-Type", ContentType.Application.Json.toString()),
                )
            }

        val refused = assertIs<AuthResult.Refused>(repo(engine).deleteAccount())

        assertEquals("authz.lens.not_available", refused.envelope.error.messageKey)
    }

    @Test
    fun `the number arrives with the profile`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"lenses":[],"self_name":"Rahim","address":null,"phone":"+8801611477203"}""",
                    HttpStatusCode.OK,
                    headersOf("Content-Type", ContentType.Application.Json.toString()),
                )
            }

        val ok = assertIs<AuthResult.Ok<MeDto>>(repo(engine).profile())

        assertEquals("+8801611477203", ok.value.phone)
    }
}
