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
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The HTTP layer, driven against a mock engine.
 *
 * **These tests assert the RAW BYTES the client sends and receives**,
 * not a decoded object. The money rule is about what crosses the wire,
 * and a test that hands the repository a pre-built object proves
 * nothing about serialization.
 */
class HttpRepositoryTest {

    private fun jsonHeaders() =
        headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))

    private fun engineReturning(
        status: HttpStatusCode,
        body: String,
    ) = MockEngine { respond(body, status, jsonHeaders()) }

    private fun client(engine: MockEngine, tokens: TokenStore = TokenStore.InMemory()) =
        ApiClient.build("https://staging.example", engine, tokens)

    @Test
    fun `a plaintext base url is refused`() {
        // The manifest sets no usesCleartextTraffic, so this would fail
        // at the platform anyway -- with a generic network error that
        // sends a developer to the manifest. Refusing it here names the
        // actual problem.
        val error =
            assertFailsWith<IllegalArgumentException> {
                ApiClient.build("http://staging.example", MockEngine { respond("") })
            }

        assertTrue(error.message!!.contains("https"))
    }

    @Test
    fun `loopback is exempt, for local development only`() {
        // The emulator reaches the host machine at 10.0.2.2, which is
        // loopback from the only point of view this exemption serves.
        ApiClient.build("http://localhost:8000", MockEngine { respond("") })
        ApiClient.build("http://10.0.2.2:8000", MockEngine { respond("") })
    }

    @Test
    fun `a successful issue returns Ok`() = runTest {
        val engine = engineReturning(HttpStatusCode.OK, """{"status":"requested"}""")
        val repository = HttpAuthRepository(client(engine), TokenStore.InMemory())

        val result = repository.issue("+8801711111111")

        assertIs<AuthResult.Ok<IssueResponse>>(result)
        assertEquals("requested", result.value.status)
    }

    @Test
    fun `a refusal decodes the envelope rather than inferring from status`() =
        runTest {
            // retryable is a SERVER-provided boolean [TC-9]. A client
            // deciding it from the status code would be holding a
            // business rule.
            val engine =
                engineReturning(
                    HttpStatusCode.Conflict,
                    """{"error":{"code":"TEMPORARILY_UNAVAILABLE",
                       "retryable":false,
                       "message_key":"auth.otp.temporarily_unavailable"}}""",
                )
            val repository = HttpAuthRepository(client(engine), TokenStore.InMemory())

            val result = repository.issue("+8801711111111")

            val refused = assertIs<AuthResult.Refused>(result)
            assertEquals("auth.otp.temporarily_unavailable", refused.envelope.error.messageKey)
            assertEquals(false, refused.envelope.error.retryable)
        }

    @Test
    fun `a transport failure is distinct from a refusal`() = runTest {
        val engine = MockEngine { throw java.io.IOException("no route to host") }
        val repository = HttpAuthRepository(client(engine), TokenStore.InMemory())

        assertIs<AuthResult.TransportFailure>(repository.issue("+8801711111111"))
    }

    @Test
    fun `an unparseable error body is a refusal, not a transport failure`() =
        runTest {
            // The server ANSWERED. Treating that as a transport failure
            // would invite a retry against a server that is responding.
            val engine = engineReturning(HttpStatusCode.BadGateway, "<html>502</html>")
            val repository = HttpAuthRepository(client(engine), TokenStore.InMemory())

            val result = repository.issue("+8801711111111")

            val refused = assertIs<AuthResult.Refused>(result)
            assertEquals("error.unexpected", refused.envelope.error.messageKey)
        }

    @Test
    fun `a successful verify records the token pair`() = runTest {
        val engine =
            engineReturning(
                HttpStatusCode.OK,
                """{"access_token":"at","refresh_token":"rt","expires_in":900}""",
            )
        val tokens = TokenStore.InMemory()
        val repository = HttpAuthRepository(client(engine, tokens), tokens)

        repository.verify("+8801711111111", "123456")

        assertEquals("at", tokens.accessToken())
        assertEquals("rt", tokens.refreshToken())
    }

    @Test
    fun `a failed verify records nothing`() = runTest {
        val engine =
            engineReturning(
                HttpStatusCode.Unauthorized,
                """{"error":{"code":"OTP_NOT_VALID","retryable":false,
                   "message_key":"auth.otp.not_valid"}}""",
            )
        val tokens = TokenStore.InMemory()
        val repository = HttpAuthRepository(client(engine, tokens), tokens)

        repository.verify("+8801711111111", "000000")

        assertNull(tokens.accessToken())
    }

    @Test
    fun `the access token is sent as a bearer header`() = runTest {
        val tokens = TokenStore.InMemory().apply { save("the-token", "rt") }
        var seen: String? = null
        val engine =
            MockEngine { request ->
                seen = request.headers["Authorization"]
                respond("[]", HttpStatusCode.OK, jsonHeaders())
            }

        HttpRosterRepository(client(engine, tokens)).roster("b-1")

        assertEquals("Bearer the-token", seen)
    }

    @Test
    fun `no Authorization header is sent when signed out`() = runTest {
        var seen: String? = "sentinel"
        val engine =
            MockEngine { request ->
                seen = request.headers["Authorization"]
                respond("[]", HttpStatusCode.OK, jsonHeaders())
            }

        HttpRosterRepository(client(engine)).roster("b-1")

        assertNull(seen)
    }

    @Test
    fun `a money field arriving as a JSON number fails the request`() = runTest {
        // THE RULE AT THE BOUNDARY [TC-7, D-20]. A lenient decoder that
        // quietly converted would pass a happy-path test on both sides
        // while the value was already an IEEE 754 double.
        val engine =
            engineReturning(
                HttpStatusCode.OK,
                """[{"enrollment_id":"e-1","display_name":"Rahim",
                   "fee_amount":1500.00,"status":"active"}]""",
            )

        val result = HttpRosterRepository(client(engine)).roster("b-1")

        // Decoding failed, so no response arrived intact. The repository
        // reports that rather than handing up a corrupted row.
        assertIs<AuthResult.TransportFailure>(result)
    }

    @Test
    fun `a money field arriving as a JSON string decodes`() = runTest {
        val engine =
            engineReturning(
                HttpStatusCode.OK,
                """[{"enrollment_id":"e-1","display_name":"Rahim",
                   "fee_amount":"1500.00","status":"active"}]""",
            )

        val result = HttpRosterRepository(client(engine)).roster("b-1")

        val ok = assertIs<AuthResult.Ok<*>>(result)
        assertTrue(ok.value.toString().contains("1500.00"))
    }

    @Test
    fun `an unknown field does not break decoding`() = runTest {
        // An installed app cannot be forced to update [D-26]. A client
        // that refused an unknown field would break on every additive
        // server deploy until the user updated.
        val engine =
            engineReturning(
                HttpStatusCode.OK,
                """[{"enrollment_id":"e-1","display_name":"Rahim",
                   "status":"active","a_field_from_a_later_unit":42}]""",
            )

        assertIs<AuthResult.Ok<*>>(HttpRosterRepository(client(engine)).roster("b-1"))
    }
}
