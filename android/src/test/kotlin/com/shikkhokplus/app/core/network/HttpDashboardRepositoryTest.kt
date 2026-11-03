package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.dashboard.DashboardRange
import com.shikkhokplus.app.feature.dashboard.DashboardReader
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/** The progress dashboard reads, asserted on route and query bytes. */
class HttpDashboardRepositoryTest {
    private val body =
        """{"tiles":{"attendance_percent":null,"present":0,"held":0,"exam_average_percent":null,
           "direction":null,"owed":"0.00"},"attendance_by_month":[],"exams":[],"fee_months":[]}"""

    private fun engine() =
        MockEngine {
            respond(
                body,
                HttpStatusCode.OK,
                headersOf("Content-Type", listOf(ContentType.Application.Json.toString())),
            )
        }

    @Test
    fun `each reader reads over its own path with the range`() =
        runTest {
            val engine = engine()
            val repository =
                HttpDashboardRepository(ApiClient.build("https://staging.example", engine, TokenStore.InMemory()))

            val results =
                listOf(
                    repository.dashboard(DashboardReader.TEACHER, "e-1", DashboardRange.SIX_MONTHS),
                    repository.dashboard(DashboardReader.STUDENT, "e-1", DashboardRange.YEAR),
                    repository.dashboard(DashboardReader.GUARDIAN, "e-1", DashboardRange.ALL),
                )

            results.forEach { assertIs<AuthResult.Ok<DashboardDto>>(it) }
            val urls = engine.requestHistory.map { it.url }
            assertEquals(
                listOf(
                    "/v1/enrollments/e-1/dashboard",
                    "/v1/me/enrollments/e-1/dashboard",
                    "/v1/children/e-1/dashboard",
                ),
                urls.map { it.encodedPath },
            )
            assertEquals(listOf("6m", "year", "all"), urls.map { it.parameters["range"] })
        }

    @Test
    fun `a guardian's children come from the guardian home`() =
        runTest {
            val engine =
                MockEngine {
                    respond(
                        """{"children":[]}""",
                        HttpStatusCode.OK,
                        headersOf("Content-Type", listOf(ContentType.Application.Json.toString())),
                    )
                }
            val repository =
                HttpDashboardRepository(ApiClient.build("https://staging.example", engine, TokenStore.InMemory()))

            assertIs<AuthResult.Ok<GuardianHomeDto>>(repository.children())
            assertEquals("/v1/guardian/home", engine.requestHistory.single().url.encodedPath)
        }
}
