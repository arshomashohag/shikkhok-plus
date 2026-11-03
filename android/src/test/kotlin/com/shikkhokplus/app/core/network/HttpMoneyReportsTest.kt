package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * The money-report reads (M1, M2), asserted on route and query bytes.
 */
class HttpMoneyReportsTest {

    private val monthBody =
        """{"period":"2026-10","collected":"900.00","charged":"1200.00",
           "counts":{"paid":1,"checking":0,"owed":1},"seats":[
           {"enrollment_id":"e-1","display_name":"Rahim","outstanding":"100.00","state":"unpaid"}]}"""

    private fun jsonHeaders() = headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))

    private fun client(engine: MockEngine) = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

    @Test
    fun `collections sends every chosen batch id and the month count`() =
        runTest {
            val engine =
                MockEngine {
                    respond(
                        """{"months":[],"outstanding":"0.00","owing_students":0}""",
                        HttpStatusCode.OK,
                        jsonHeaders(),
                    )
                }
            val result = HttpAnalyticsRepository(client(engine)).collections(listOf("b-1", "b-2"), 6)

            assertIs<AuthResult.Ok<CollectionsDto>>(result)
            val url = engine.requestHistory.single().url
            assertEquals("/v1/analytics/collections", url.encodedPath)
            assertEquals(listOf("b-1", "b-2"), url.parameters.getAll("batch_id"))
            assertEquals("6", url.parameters["months"])
        }

    @Test
    fun `a batch month sends its period only when one is chosen`() =
        runTest {
            val engine = MockEngine { respond(monthBody, HttpStatusCode.OK, jsonHeaders()) }
            val repository = HttpAnalyticsRepository(client(engine))

            repository.batchMonth("b-1", null)
            repository.batchMonth("b-1", "2026-09")

            assertEquals(null, engine.requestHistory[0].url.parameters["period"])
            assertEquals("/v1/batches/b-1/fees", engine.requestHistory[1].url.encodedPath)
            assertEquals("2026-09", engine.requestHistory[1].url.parameters["period"])
        }

    @Test
    fun `the batch list reads the batches route`() =
        runTest {
            val engine = MockEngine { respond("[]", HttpStatusCode.OK, jsonHeaders()) }
            assertIs<AuthResult.Ok<List<BatchDto>>>(HttpAnalyticsRepository(client(engine)).batches())
            assertEquals("/v1/batches", engine.requestHistory.single().url.encodedPath)
        }

    @Test
    fun `the batch screen still reads its seats from the month object`() =
        runTest {
            val engine = MockEngine { respond(monthBody, HttpStatusCode.OK, jsonHeaders()) }
            val result = HttpBatchDetailRepository(client(engine)).fees("b-1")

            val ok = assertIs<AuthResult.Ok<List<RosterFeeRowDto>>>(result)
            assertEquals(listOf("e-1"), ok.value.map { it.enrollmentId })
        }

    @Test
    fun `a refused batch fees read stays a refusal for the batch screen`() =
        runTest {
            val engine =
                MockEngine {
                    respond(
                        """{"error":{"code":"X","message_key":"error.forbidden","retryable":false}}""",
                        HttpStatusCode.Forbidden,
                        jsonHeaders(),
                    )
                }
            assertIs<AuthResult.Refused>(HttpBatchDetailRepository(client(engine)).fees("b-1"))
        }

    @Test
    fun `an unreachable server is a transport failure for the batch screen`() =
        runTest {
            val engine = MockEngine { throw java.io.IOException("offline") }
            assertIs<AuthResult.TransportFailure>(HttpBatchDetailRepository(client(engine)).fees("b-1"))
        }
}
