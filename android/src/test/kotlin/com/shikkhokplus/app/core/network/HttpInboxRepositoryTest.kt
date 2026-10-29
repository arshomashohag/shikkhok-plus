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

/** The reader's inbox over a mock transport: the route and the bytes. */
class HttpInboxRepositoryTest {

    private fun client(engine: MockEngine) = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

    @Test
    fun `the inbox is read from the reader's own route, money as a string`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"items":[{"notification_id":"n-1","kind":"fee_reminder","batch_name":"Physics",
                    "period":"2026-10","amount":"1200.00","created_at":"2026-10-17T06:00:00Z","read":false}],
                    "unread":1}""",
                    HttpStatusCode.OK,
                    headersOf("Content-Type", listOf(ContentType.Application.Json.toString())),
                )
            }

        val result = HttpInboxRepository(client(engine)).inbox()

        val ok = assertIs<AuthResult.Ok<InboxDto>>(result)
        assertEquals("1200.00", ok.value.items.single().amount.toString())
        assertEquals("/v1/me/notifications", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `marking read posts to the reader's own route`() = runTest {
        val engine = MockEngine { respond("", HttpStatusCode.NoContent) }

        val result = HttpInboxRepository(client(engine)).markRead()

        assertIs<AuthResult.Ok<Unit>>(result)
        val request = engine.requestHistory.single()
        assertEquals(HttpMethod.Post, request.method)
        assertEquals("/v1/me/notifications/read", request.url.encodedPath)
    }
}
