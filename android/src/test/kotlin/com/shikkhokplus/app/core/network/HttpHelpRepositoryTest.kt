package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.SerializationException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs

/**
 * The help centre over a mock transport: the routes, the bodies, and
 * decoding the shapes the server documents.
 */
class HttpHelpRepositoryTest {

    private val json = headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))

    private fun client(engine: MockEngine) = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

    private val ticket =
        """{"ticket_id":"t-1","subject":"Cannot add a student","status":"answered",
        "created_at":"2026-11-06T04:00:00Z","updated_at":"2026-11-06T05:30:00.123456Z",
        "has_new_reply":true,"preview":"Try the + button"}"""

    private val detail =
        """{"ticket":$ticket,"messages":[
        {"message_id":"m-1","author":"requester","body":"The add button does nothing.",
        "created_at":"2026-11-06T04:00:00Z"},
        {"message_id":"m-2","author":"support","body":"Try the + button","created_at":"2026-11-06T05:30:00Z"}]}"""

    @Test
    fun `the list is read from the reader's own route`() = runTest {
        val engine = MockEngine { respond("""{"tickets":[$ticket],"new_replies":1}""", HttpStatusCode.OK, json) }

        val ok = assertIs<AuthResult.Ok<HelpTicketListDto>>(HttpHelpRepository(client(engine)).tickets())

        assertEquals("/v1/me/help/tickets", engine.requestHistory.single().url.encodedPath)
        assertEquals(1, ok.value.newReplies)
        val first = ok.value.tickets.single()
        assertEquals("t-1", first.ticketId)
        assertEquals("answered", first.status)
        assertEquals(true, first.hasNewReply)
        assertEquals("2026-11-06T05:30:00.123456Z", first.updatedAt)
    }

    @Test
    fun `asking posts the subject and the question and reads the thread back`() = runTest {
        val engine = MockEngine { respond(detail, HttpStatusCode.Created, json) }

        val ok =
            assertIs<AuthResult.Ok<HelpTicketDetailDto>>(
                HttpHelpRepository(client(engine)).ask("Cannot add a student", "The add button does nothing."),
            )

        val request = engine.requestHistory.single()
        assertEquals(HttpMethod.Post, request.method)
        assertEquals("/v1/me/help/tickets", request.url.encodedPath)
        assertEquals(
            """{"subject":"Cannot add a student","body":"The add button does nothing."}""",
            (request.body as TextContent).text,
        )
        assertEquals(listOf("requester", "support"), ok.value.messages.map { it.author })
    }

    @Test
    fun `one thread is read from its own route`() = runTest {
        val engine = MockEngine { respond(detail, HttpStatusCode.OK, json) }

        val ok = assertIs<AuthResult.Ok<HelpTicketDetailDto>>(HttpHelpRepository(client(engine)).ticket("t-1"))

        assertEquals("/v1/me/help/tickets/t-1", engine.requestHistory.single().url.encodedPath)
        assertEquals("t-1", ok.value.ticket.ticketId)
    }

    @Test
    fun `a reply posts only the body to the thread's messages`() = runTest {
        val engine = MockEngine { respond(detail, HttpStatusCode.OK, json) }

        assertIs<AuthResult.Ok<HelpTicketDetailDto>>(HttpHelpRepository(client(engine)).reply("t-1", "Thanks"))

        val request = engine.requestHistory.single()
        assertEquals(HttpMethod.Post, request.method)
        assertEquals("/v1/me/help/tickets/t-1/messages", request.url.encodedPath)
        assertEquals("""{"body":"Thanks"}""", (request.body as TextContent).text)
    }

    @Test
    fun `the daily limit comes back as the server's envelope`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"HELP_TOO_MANY","retryable":false,"message_key":"help.ticket.too_many"}}""",
                    HttpStatusCode.Conflict,
                    json,
                )
            }

        val refused = assertIs<AuthResult.Refused>(HttpHelpRepository(client(engine)).ask("Hi", "Hello"))

        assertEquals("help.ticket.too_many", refused.envelope.error.messageKey)
        assertEquals(false, refused.envelope.error.retryable)
    }

    @Test
    fun `a field the server adds later is tolerated`() {
        val decoded =
            ApiClient.json.decodeFromString(
                HelpTicketDto.serializer(),
                ticket.replace("\"preview\"", "\"priority\":\"high\",\"preview\""),
            )

        assertEquals("Try the + button", decoded.preview)
    }

    @Test
    fun `a ticket missing a field the server always sends fails loudly`() {
        // `has_new_reply` drives the new-reply mark; a silent default would
        // hide every reply rather than fail.
        assertFailsWith<SerializationException> {
            ApiClient.json.decodeFromString(
                HelpTicketDto.serializer(),
                ticket.replace(""""has_new_reply":true,""", ""),
            )
        }
    }

    @Test
    fun `an empty list decodes`() {
        val decoded =
            ApiClient.json.decodeFromString(HelpTicketListDto.serializer(), """{"tickets":[],"new_replies":0}""")

        assertEquals(emptyList(), decoded.tickets)
        assertEquals(0, decoded.newReplies)
    }
}
