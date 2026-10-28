package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.utils.io.ByteReadChannel
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * The guardian and sessions repositories, over a mock transport.
 *
 * **These assert the ROUTE and the BYTES**, not a decoded object. The
 * properties that can be silently wrong here are the path a request
 * goes to and the field names it carries: a repository that posts the
 * right data to the wrong route, or the right route with a
 * camelCase key the server ignores, compiles and passes any test that
 * hands it a pre-built object.
 */
class HttpTeachingRepositoryTest {

    private fun jsonHeaders() =
        headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))

    private fun client(engine: MockEngine) =
        ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

    @Test
    fun `the guardian route carries no child identifier`() = runTest {
        // **The property that matters, and it is an absence.** The
        // server resolves the seats from the authenticated account's
        // own guardian_account_id [BR4.1, NFR14.29]. A route taking a
        // child id would let a guardian ask about a child who is not
        // theirs and rely on the server to refuse — which works until
        // one endpoint forgets.
        val engine =
            MockEngine { respond("""{"children":[]}""", HttpStatusCode.OK, jsonHeaders()) }
        val result = HttpGuardianRepository(client(engine)).home()

        assertIs<AuthResult.Ok<GuardianHomeDto>>(result)
        assertEquals("/v1/guardian/home", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `a refusal carries the server's own envelope`() = runTest {
        // The client decides neither the message nor whether a retry
        // would help. Both are read from what the server sent.
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"NOT_AVAILABLE","message_key":"error.not_available","retryable":false}}""",
                    HttpStatusCode.Forbidden,
                    jsonHeaders(),
                )
            }
        val result = HttpGuardianRepository(client(engine)).home()

        val refused = assertIs<AuthResult.Refused>(result)
        assertEquals("error.not_available", refused.envelope.error.messageKey)
        assertEquals(false, refused.envelope.error.retryable)
    }

    @Test
    fun `no response at all is a transport failure, not a refusal`() = runTest {
        // The distinction the three-outcome result exists for: there
        // is no envelope to read a retry policy from, so the client
        // must not invent one.
        val engine = MockEngine { throw java.io.IOException("no route to host") }
        val result = HttpGuardianRepository(client(engine)).home()

        assertIs<AuthResult.TransportFailure>(result)
    }

    @Test
    fun `creating a session posts snake_case keys`() = runTest {
        // A camelCase key is silently ignored by the server, which
        // then rejects the request for a missing required field — or
        // worse, accepts it with the field unset.
        val engine =
            MockEngine { respond("{}", HttpStatusCode.Created, jsonHeaders()) }
        val result =
            HttpSessionsRepository(client(engine)).createAdHoc(
                batchId = "b-1",
                date = "2026-11-02",
                startTime = "16:00",
                batchSubjectId = "s-9",
            )

        assertIs<AuthResult.Ok<Unit>>(result)
        val sent = engine.requestHistory.single()
        assertEquals(HttpMethod.Post, sent.method)
        assertEquals("/v1/batches/b-1/sessions", sent.url.encodedPath)

        val body = (sent.body as io.ktor.http.content.TextContent).text
        assertTrue(body.contains("\"start_time\""), body)
        assertTrue(body.contains("\"batch_subject_id\""), body)
        assertTrue("startTime" !in body, "camelCase must not reach the wire: $body")
    }

    @Test
    fun `a session with no subject omits the field rather than sending null text`() =
        runTest {
            val engine =
                MockEngine { respond("{}", HttpStatusCode.Created, jsonHeaders()) }
            HttpSessionsRepository(client(engine)).createAdHoc(
                batchId = "b-1",
                date = "2026-11-02",
                startTime = "16:00",
                batchSubjectId = null,
            )

            val body =
                (engine.requestHistory.single().body as io.ktor.http.content.TextContent).text
            assertTrue("\"null\"" !in body, "null must not be sent as a string: $body")
        }

    @Test
    fun `rescheduling preserves the session identity in the route`() = runTest {
        // **A reschedule, not a delete and a create** [BR1.7]. The
        // session keeps its id so attendance already recorded against
        // it stays attached, which is why this is its own endpoint.
        val engine =
            MockEngine { respond("{}", HttpStatusCode.OK, jsonHeaders()) }
        HttpSessionsRepository(client(engine)).reschedule(
            sessionId = "s-42",
            date = "2026-11-03",
            startTime = "17:30",
        )

        val sent = engine.requestHistory.single()
        assertEquals(HttpMethod.Put, sent.method)
        assertEquals("/v1/sessions/s-42/schedule", sent.url.encodedPath)
    }

    @Test
    fun `cancelling posts to the sub-resource with no body`() = runTest {
        val engine =
            MockEngine { respond("{}", HttpStatusCode.OK, jsonHeaders()) }
        HttpSessionsRepository(client(engine)).cancel("s-7")

        val sent = engine.requestHistory.single()
        assertEquals(HttpMethod.Post, sent.method)
        assertEquals("/v1/sessions/s-7/cancellation", sent.url.encodedPath)
    }

    @Test
    fun `a write refusal is a refusal, never a success`() = runTest {
        // The failure the body-discarding helper exists to get right:
        // a non-2xx must not become Ok(Unit) just because the body was
        // going to be thrown away.
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"CONFLICT","message_key":"session.already_cancelled","retryable":false}}""",
                    HttpStatusCode.Conflict,
                    jsonHeaders(),
                )
            }
        val result = HttpSessionsRepository(client(engine)).cancel("s-7")

        val refused = assertIs<AuthResult.Refused>(result)
        assertEquals("session.already_cancelled", refused.envelope.error.messageKey)
    }

    @Test
    fun `a session list decodes into its DTOs`() = runTest {
        val engine =
            MockEngine {
                respond(
                    ByteReadChannel(
                        """
                        [{"session_id":"s-1","date":"2026-11-02",
                          "start_time":"16:00","origin":"recurring",
                          "status":"scheduled"}]
                        """.trimIndent(),
                    ),
                    HttpStatusCode.OK,
                    jsonHeaders(),
                )
            }
        val result = HttpSessionsRepository(client(engine)).sessions("b-1")

        val ok = assertIs<AuthResult.Ok<List<SessionDto>>>(result)
        assertEquals("s-1", ok.value.single().sessionId)
    }
}
