package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.queue.AttendanceEntry
import com.shikkhokplus.app.core.queue.QueueTarget
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * The attendance repository, over a mock transport.
 *
 * **Three outcomes, and the middle one is the point** [TC-8, D-9].
 * Attendance is recorded mid-class on a phone that may lose signal:
 * applied, refused for a version conflict, or never delivered. A
 * conflict is NOT a failure — somebody else wrote against the same
 * session — and treating it as one sends a teacher into a retry loop
 * against a version that will never match.
 */
class HttpAttendanceRepositoryTest {

    private fun jsonHeaders() =
        headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))

    private fun client(engine: MockEngine) =
        ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

    private fun write() =
        QueuedWrite(
            id = "q-1",
            target = QueueTarget.ATTENDANCE,
            sessionId = "s-1",
            baseVersion = 3,
            clientMutationId = "m-1",
            entries = listOf(AttendanceEntry(enrollmentId = "e-1", present = true)),
        )

    @Test
    fun `an applied write reports the version the server returned`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"attendance_version":4,"submission_id":"sub-1"}""",
                    HttpStatusCode.OK,
                    jsonHeaders(),
                )
            }

        val outcome = HttpAttendanceRepository(client(engine)).submit(write())

        val applied = assertIs<SendOutcome.Applied>(outcome)
        assertEquals(4, applied.resultingVersion)
    }

    @Test
    fun `the body uses seats, which is what the server requires`() = runTest {
        // A differently-named key is dropped silently and the request
        // then fails for a missing required field, which reads as a
        // server fault rather than a client one.
        val engine =
            MockEngine {
                respond(
                    """{"attendance_version":4,"submission_id":"s"}""",
                    HttpStatusCode.OK,
                    jsonHeaders(),
                )
            }

        HttpAttendanceRepository(client(engine)).submit(write())

        val sent = engine.requestHistory.single()
        val body = (sent.body as io.ktor.http.content.TextContent).text
        assertEquals("/v1/sessions/s-1/attendance", sent.url.encodedPath)
        assertTrue(body.contains("\"seats\""), body)
        assertTrue(body.contains("\"base_attendance_version\""), body)
        assertTrue(body.contains("\"client_mutation_id\""), body)
        assertTrue("entries" !in body, "the server's field is `seats`: $body")
    }

    @Test
    fun `a 409 is a conflict, never a failure`() = runTest {
        // **The distinction the three outcomes exist for.** A conflict
        // means somebody else recorded against this session; the
        // person needs to see what changed, not retry blindly over it.
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"CONFLICT","message_key":"attendance.stale","retryable":false}}""",
                    HttpStatusCode.Conflict,
                    jsonHeaders(),
                )
            }

        val outcome = HttpAttendanceRepository(client(engine)).submit(write())

        val conflicted = assertIs<SendOutcome.Conflicted>(outcome)
        assertEquals("attendance.stale", conflicted.envelope.error.messageKey)
    }

    @Test
    fun `a refusal that is not a conflict is a failure`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"FORBIDDEN","message_key":"error.forbidden","retryable":false}}""",
                    HttpStatusCode.Forbidden,
                    jsonHeaders(),
                )
            }

        val outcome = HttpAttendanceRepository(client(engine)).submit(write())

        val failed = assertIs<SendOutcome.Failed>(outcome)
        assertEquals("error.forbidden", failed.envelope?.error?.messageKey)
    }

    @Test
    fun `no response at all carries no envelope to read a policy from`() = runTest {
        // The client must not invent a retry policy where the server
        // stated none.
        val engine = MockEngine { throw java.io.IOException("no route to host") }

        val outcome = HttpAttendanceRepository(client(engine)).submit(write())

        val failed = assertIs<SendOutcome.Failed>(outcome)
        assertEquals(null, failed.envelope)
    }

    @Test
    fun `after a conflict the current roster is re-read`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"seats":[],"attendance_version":5,"writable":true}""",
                    HttpStatusCode.OK,
                    jsonHeaders(),
                )
            }

        val result = HttpAttendanceRepository(client(engine)).currentRoster("s-1")

        val ok = assertIs<com.shikkhokplus.app.feature.auth.AuthResult.Ok<SessionRosterDto>>(
            result,
        )
        assertEquals(5, ok.value.attendanceVersion)
        assertEquals(
            "/v1/sessions/s-1/attendance",
            engine.requestHistory.single().url.encodedPath,
        )
    }
}
