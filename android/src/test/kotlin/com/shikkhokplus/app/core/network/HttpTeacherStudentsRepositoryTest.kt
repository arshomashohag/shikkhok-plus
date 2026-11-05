package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.students.StudentFilter
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * The students repository against a mock engine [0018].
 *
 * Asserts what crosses the wire: the filter as query parameters (the
 * SERVER filters), money as strings, and refusals as envelopes.
 */
class HttpTeacherStudentsRepositoryTest {

    private val student =
        """
        {"student_id":"s-1","display_name":"Rafiq","student_state":"pending",
         "guardian_state":"absent","enrollments":[],"total_outstanding":"0.00",
         "is_removable":true}
        """

    private fun engine(status: HttpStatusCode = HttpStatusCode.OK, body: String = "[]") =
        MockEngine {
            respond(body, status, headersOf("Content-Type", listOf(ContentType.Application.Json.toString())))
        }

    private fun repository(engine: MockEngine) =
        HttpTeacherStudentsRepository(ApiClient.build("https://staging.example", engine, TokenStore.InMemory()))

    @Test
    fun `each filter travels as a query parameter`() = runTest {
        val engine = engine()
        val repository = repository(engine)

        repository.students(StudentFilter.All, "")
        repository.students(StudentFilter.Unassigned, "")
        repository.students(StudentFilter.InBatch("b-1"), " raf ")
        repository.students(StudentFilter.NotInBatch("b-2"), "")

        val queries = engine.requestHistory.map { it.url.encodedQuery }
        assertEquals("", queries[0])
        assertEquals("unassigned=true", queries[1])
        assertEquals("batch_id=b-1&q=raf", queries[2])
        assertEquals("exclude_batch_id=b-2", queries[3])
    }

    @Test
    fun `a new student is sent with its batches and fees as strings`() = runTest {
        val engine = engine(HttpStatusCode.Created, student)
        val result =
            repository(engine).create(
                "Rafiq",
                "01812345678",
                "",
                listOf(StudentSeatBody("b-1", null), StudentSeatBody("b-2", "900.00")),
            )

        val created = assertIs<AuthResult.Ok<TeacherStudentDto>>(result)
        assertEquals(Money.of("0.00"), created.value.totalOutstanding)
        val sent = (engine.requestHistory.single().body as TextContent).text
        assertTrue("\"fee_amount\":\"900.00\"" in sent, sent)
        // A blank guardian number is not sent at all.
        assertTrue("guardian_phone" !in sent, sent)
    }

    @Test
    fun `a refused number comes back as the server's envelope`() = runTest {
        val engine =
            engine(
                HttpStatusCode.Conflict,
                """{"error":{"code":"STUDENT_PHONE_TAKEN","retryable":false,"message_key":"student.phone_taken"}}""",
            )

        val result = repository(engine).create("Rafiq", "01812345678", null, emptyList())

        val refused = assertIs<AuthResult.Refused>(result)
        assertEquals("student.phone_taken", refused.envelope.error.messageKey)
    }

    @Test
    fun `the seat and student writes reach their routes`() = runTest {
        val engine = engine(HttpStatusCode.OK, student)
        val repository = repository(engine)

        repository.student("s-1")
        repository.rename("s-1", "Rafiqul", null, null)
        repository.enroll("s-1", "b-3")
        repository.addToBatch("b-3", listOf("s-1", "s-2"))
        repository.leaveBatch("e-1", "2026-11-05")
        repository.removeSeat("e-2")
        repository.removeStudent("s-1")
        repository.batches()

        val seen = engine.requestHistory.map { it.method to it.url.encodedPath }
        assertEquals(
            listOf(
                HttpMethod.Get to "/v1/students/s-1",
                HttpMethod.Patch to "/v1/students/s-1",
                HttpMethod.Post to "/v1/students/s-1/enrollments",
                HttpMethod.Post to "/v1/batches/b-3/students",
                HttpMethod.Patch to "/v1/enrollments/e-1/inactive-from",
                HttpMethod.Delete to "/v1/enrollments/e-2",
                HttpMethod.Delete to "/v1/students/s-1",
                HttpMethod.Get to "/v1/batches",
            ),
            seen,
        )
        val added = (engine.requestHistory[3].body as TextContent).text
        assertEquals("""{"student_ids":["s-1","s-2"]}""", added)
    }

    @Test
    fun `no response is a transport failure`() = runTest {
        val engine = MockEngine { error("offline") }

        assertEquals(AuthResult.TransportFailure, repository(engine).removeStudent("s-1"))
    }
}
