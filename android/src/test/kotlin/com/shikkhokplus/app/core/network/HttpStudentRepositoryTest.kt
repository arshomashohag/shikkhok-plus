package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.student.FamilyReader
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/** The family reads over a mock transport: which route each reader takes. */
class HttpStudentRepositoryTest {

    private fun client(engine: MockEngine) = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

    private fun engine(body: String) =
        MockEngine {
            respond(body, HttpStatusCode.OK, headersOf("Content-Type", listOf(ContentType.Application.Json.toString())))
        }

    private val view = """{"served_at":"2026-10-28T09:00:00Z"}"""

    @Test
    fun `a student reads their own seat's routes`() = runTest {
        val engine = engine(view)
        val repository = HttpStudentRepository(client(engine), FamilyReader.SELF)

        repository.batchView("e-1")

        assertEquals("/v1/me/batches/e-1/teaching", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `a guardian reads the child's routes for the view, progress and an exam`() = runTest {
        val engine = engine(view)
        val repository = HttpStudentRepository(client(engine), FamilyReader.GUARDIAN)

        repository.batchView("e-1")
        repository.progress("e-1")
        repository.exam("e-1", "x-1")

        assertEquals(
            listOf("/v1/children/e-1/teaching", "/v1/children/e-1/progress", "/v1/children/e-1/exams/x-1"),
            engine.requestHistory.map { it.url.encodedPath },
        )
    }

    @Test
    fun `a student reads an exam from their own enrollments route`() = runTest {
        val engine =
            engine(
                """{"exam_id":"x-1","title":"Monthly","date":"2026-11-02","subject_name":"Physics",
                "total_marks":50,"topics":["Heat"],"state":"upcoming"}""",
            )

        val result = HttpStudentRepository(client(engine)).exam("e-1", "x-1")

        assertEquals(listOf("Heat"), assertIs<AuthResult.Ok<FamilyExamDto>>(result).value.topics)
        assertEquals("/v1/me/enrollments/e-1/exams/x-1", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `a guardian's seats come from the home read, each carrying the child's name`() = runTest {
        val engine =
            engine(
                """{"children":[{"key":"e-1","display_name":"Tasnim","batch_count":1,
                "batches":[{"enrollment_id":"e-1","batch_name":"Physics A","teacher_display_name":"Karim"}]}]}""",
            )

        val result = HttpStudentRepository(client(engine), FamilyReader.GUARDIAN).batches()

        val seat = assertIs<AuthResult.Ok<List<StudentBatchDto>>>(result).value.single()
        assertEquals("Tasnim", seat.childName)
        assertEquals("Physics A", seat.batchName)
        assertEquals("/v1/guardian/home", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `each reader reads the month from its own calendar route`() = runTest {
        val body = """{"year":2026,"month":11,"first_month":"2026-01","last_month":"2026-12","days":[]}"""
        val own = engine(body)
        val guardian = engine(body)

        HttpStudentRepository(client(own), FamilyReader.SELF).month("e-1", 2026, 11)
        HttpStudentRepository(client(guardian), FamilyReader.GUARDIAN).month("e-1", 2026, 11)

        val ownRequest = own.requestHistory.single().url
        assertEquals("/v1/me/enrollments/e-1/calendar", ownRequest.encodedPath)
        assertEquals("2026", ownRequest.parameters["year"])
        assertEquals("11", ownRequest.parameters["month"])
        assertEquals("/v1/children/e-1/calendar", guardian.requestHistory.single().url.encodedPath)
    }
}
