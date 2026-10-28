package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.marks.MarksheetReader
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
 * The marks repository, over a mock transport.
 *
 * **What these assert is the ROUTE and the BODY**, because that is the
 * half no mapper test can see: a correctly mapped state built from a
 * call to the wrong path is still a broken screen, and a body whose
 * field names do not match the server's is dropped silently and then
 * refused for a missing required field.
 */
class HttpMarksRepositoryTest {

    private fun jsonHeaders() =
        headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))

    private fun repo(engine: MockEngine) =
        HttpMarksRepository(
            ApiClient.build("https://staging.example", engine, TokenStore.InMemory()),
        )

    private fun ok(body: String) = MockEngine {
        respond(body, HttpStatusCode.OK, jsonHeaders())
    }

    private val resultsBody =
        """
        {"exam":{"exam_id":"x-1","title":"Mid-term","date":"2026-03-04",
        "total_marks":100,"entered_count":2,"seat_count":5},
        "results":[{"enrollment_id":"e-1","display_name":"Rafi",
        "result_state":"marked","marks":72}],"writable":false}
        """.trimIndent()

    private val marksheetBody =
        """
        {"exam_id":"x-1","exam_title":"Mid","total_marks":100,
        "own_result_state":"marked","own_marks":72}
        """.trimIndent()

    @Test
    fun `exams are read from the batch's own path`() = runTest {
        val engine = ok("""[{"exam_id":"x-1","title":"Mid","date":"2026-03-04","total_marks":100}]""")

        val result = repo(engine).exams("b-1")

        val ok = assertIs<AuthResult.Ok<List<ExamDto>>>(result)
        assertEquals("x-1", ok.value.single().examId)
        assertEquals("/v1/batches/b-1/exams", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `creating an exam sends the server's field names`() = runTest {
        val engine = ok("""{"exam_id":"x-9","title":"T","date":"2026-03-04","total_marks":50}""")

        repo(engine).createExam(
            batchId = "b-1",
            title = "Unit test",
            date = "2026-03-04",
            totalMarks = 50,
            batchSubjectId = "bs-7",
        )

        val sent = engine.requestHistory.single()
        val body = (sent.body as TextContent).text
        assertEquals(HttpMethod.Post, sent.method)
        assertEquals("/v1/batches/b-1/exams", sent.url.encodedPath)
        assertTrue(body.contains("\"total_marks\":50"), body)
        assertTrue(body.contains("\"batch_subject_id\":\"bs-7\""), body)
    }

    @Test
    fun `writable is carried through, never re-derived`() = runTest {
        // **The field this wrapper exists for** [BR5.5]. The server
        // said false for a non-empty result list, so nothing about
        // the results could have been used to guess it. A client that
        // inferred writability would offer an entry field whose save
        // is refused.
        val engine = ok(resultsBody)

        val result = repo(engine).results("x-1")

        val ok = assertIs<AuthResult.Ok<com.shikkhokplus.app.feature.marks.ExamResultsPayload>>(
            result,
        )
        assertEquals(false, ok.value.writable)
        assertEquals("Mid-term", ok.value.exam.title)
        assertEquals(72, ok.value.results.single().marks)
    }

    @Test
    fun `a refused results read keeps the server's envelope`() = runTest {
        // The mapping arm must not lose `retryable`: the client is
        // told whether to retry and never decides [TC-9].
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"NOT_AVAILABLE","message_key":"marks.exam.missing","retryable":false}}""",
                    HttpStatusCode.NotFound,
                    jsonHeaders(),
                )
            }

        val result = repo(engine).results("x-1")

        val refused = assertIs<AuthResult.Refused>(result)
        assertEquals("marks.exam.missing", refused.envelope.error.messageKey)
        assertEquals(false, refused.envelope.error.retryable)
    }

    @Test
    fun `a transport failure survives the results mapping`() = runTest {
        val engine = MockEngine { throw java.io.IOException("no route") }

        assertEquals(AuthResult.TransportFailure, repo(engine).results("x-1"))
    }

    @Test
    fun `a mark write carries no version and no mutation id`() = runTest {
        // **The difference from attendance, asserted** [BR3.11]. Mark
        // entry is interactive, so adding either field here would be
        // the queued-write shape spreading to a path that must not
        // conflict.
        val engine = ok("""{"status":"ok"}""")

        repo(engine).writeMark(
            examId = "x-1",
            enrollmentId = "e-1",
            resultState = "marked",
            marks = 72,
        )

        val sent = engine.requestHistory.single()
        val body = (sent.body as TextContent).text
        assertEquals("/v1/exams/x-1/marks", sent.url.encodedPath)
        assertTrue(body.contains("\"result_state\":\"marked\""), body)
        assertTrue(body.contains("\"marks\":72"), body)
        assertTrue("version" !in body, body)
        assertTrue("mutation" !in body, body)
    }

    @Test
    fun `an absence is written with no marks at all`() = runTest {
        // A zero would be a mark, and publishing one where the teacher
        // recorded an absence is the conflation [BR4.3] forbids.
        val engine = ok("""{"status":"ok"}""")

        repo(engine).writeMark("x-1", "e-1", resultState = "absent", marks = null)

        val body = (engine.requestHistory.single().body as TextContent).text
        assertTrue("\"marks\":0" !in body, body)
    }

    @Test
    fun `a student and a guardian read the same seat over different paths`() = runTest {
        // **The routing decision the reader exists for** [BR7.2]. Each
        // path resolves a different lens, so sending a guardian down
        // the student route would ask the wrong lens about the seat.
        val selfEngine = ok(marksheetBody)
        repo(selfEngine).marksheet("x-1", "e-1", MarksheetReader.SELF)

        val childEngine = ok(marksheetBody)
        repo(childEngine).marksheet("x-1", "e-1", MarksheetReader.CHILD)

        assertEquals(
            "/v1/me/enrollments/e-1/exams/x-1/marksheet",
            selfEngine.requestHistory.single().url.encodedPath,
        )
        assertEquals(
            "/v1/children/e-1/exams/x-1/marksheet",
            childEngine.requestHistory.single().url.encodedPath,
        )
    }

    @Test
    fun `progress reads the child's seat from the path`() = runTest {
        val engine =
            ok("""{"child_display_name":"Rafi","batch_name":"Class 9","entries":[]}""")

        val result = repo(engine).progress("e-1")

        val ok = assertIs<AuthResult.Ok<ProgressDto>>(result)
        assertEquals("Rafi", ok.value.childDisplayName)
        assertEquals(
            "/v1/children/e-1/progress",
            engine.requestHistory.single().url.encodedPath,
        )
    }

    @Test
    fun `the visibility toggle is a PUT carrying the new value`() = runTest {
        val engine = ok("""{"visible":true}""")

        repo(engine).setMarksheetVisible("b-1", visible = true)

        val sent = engine.requestHistory.single()
        assertEquals(HttpMethod.Put, sent.method)
        assertEquals("/v1/batches/b-1/marksheet-visibility", sent.url.encodedPath)
        assertTrue((sent.body as TextContent).text.contains("\"visible\":true"))
    }

    @Test
    fun `subject options come from this batch, keys included`() = runTest {
        // The key is the point: exam creation was impossible because
        // no response carried one.
        val engine =
            ok(
                """
                [{"id":"b-1","name":"A","subjects":["Physics"],
                  "subject_options":[{"id":"bs-1","name":"Physics"}]},
                 {"id":"b-2","name":"B","subjects":["Maths"],
                  "subject_options":[{"id":"bs-9","name":"Maths"}]}]
                """.trimIndent(),
            )

        val result = repo(engine).subjectOptions("b-2")

        val ok = assertIs<AuthResult.Ok<List<SubjectOptionDto>>>(result)
        assertEquals(listOf(SubjectOptionDto("bs-9", "Maths")), ok.value)
        assertEquals("/v1/batches", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `a batch missing from the list yields no subjects`() = runTest {
        val engine = ok("""[{"id":"b-1","name":"A","subject_options":[]}]""")

        val ok = assertIs<AuthResult.Ok<List<SubjectOptionDto>>>(repo(engine).subjectOptions("gone"))

        assertEquals(emptyList(), ok.value)
    }
}
