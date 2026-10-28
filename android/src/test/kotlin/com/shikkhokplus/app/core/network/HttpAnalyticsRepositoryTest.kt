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
import kotlin.test.assertTrue

/**
 * The Today and dues repositories, over a mock transport.
 *
 * **These assert the ROUTE and the BYTES**, not a decoded object. A
 * repository that reads the right data from the wrong route, or
 * mis-decodes a money value, compiles and passes any test handed a
 * pre-built object.
 */
class HttpAnalyticsRepositoryTest {

    private fun jsonHeaders() =
        headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))

    private fun client(engine: MockEngine) =
        ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

    @Test
    fun `the dues route carries no identifier either`() = runTest {
        val engine =
            MockEngine { respond("""{"rows":[]}""", HttpStatusCode.OK, jsonHeaders()) }
        val result = HttpAnalyticsRepository(client(engine)).dues()

        assertIs<AuthResult.Ok<DuesResponseDto>>(result)
        assertEquals("/v1/me/dues", engine.requestHistory.single().url.encodedPath)
    }

    @Test
    fun `money decodes from a JSON string`() = runTest {
        // [TC-7, D-20]. Every money value crosses the API as a string,
        // asserted on both sides.
        val engine =
            MockEngine {
                respond(
                    """{"rows":[{"enrollment_id":"e-1","batch_id":"b-1",
                       "batch_name":"HSC Physics","display_name":"Rahim",
                       "outstanding":"1200.00"}]}""".trimIndent(),
                    HttpStatusCode.OK,
                    jsonHeaders(),
                )
            }
        val result = HttpAnalyticsRepository(client(engine)).dues()

        val ok = assertIs<AuthResult.Ok<DuesResponseDto>>(result)
        assertEquals("1200.00", ok.value.rows.single().outstanding.toString())
    }

    @Test
    fun `money as a JSON number fails loudly rather than converting`() = runTest {
        // **The actual failure mode.** A lenient decoder that quietly
        // accepts a number and converts it passes a happy-path test on
        // both sides and loses precision in production.
        val engine =
            MockEngine {
                respond(
                    """{"rows":[{"enrollment_id":"e-1","batch_id":"b-1",
                       "batch_name":"HSC Physics","display_name":"Rahim",
                       "outstanding":1200.00}]}""".trimIndent(),
                    HttpStatusCode.OK,
                    jsonHeaders(),
                )
            }
        val result = HttpAnalyticsRepository(client(engine)).dues()

        // A decode failure arrives as a transport failure: no usable
        // response was produced. What must NOT happen is an Ok.
        assertTrue(result !is AuthResult.Ok, "a JSON number must not decode: $result")
    }

    @Test
    fun `a refusal carries the server's own envelope`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"FORBIDDEN","message_key":"error.forbidden","retryable":false}}""",
                    HttpStatusCode.Forbidden,
                    jsonHeaders(),
                )
            }
        val result = HttpAnalyticsRepository(client(engine)).today()

        val refused = assertIs<AuthResult.Refused>(result)
        assertEquals("error.forbidden", refused.envelope.error.messageKey)
    }

    @Test
    fun `no response at all is a transport failure, not a refusal`() = runTest {
        val engine = MockEngine { throw java.io.IOException("no route to host") }
        val result = HttpAnalyticsRepository(client(engine)).dues()

        assertIs<AuthResult.TransportFailure>(result)
    }
}
