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
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * Two-step verification settings over a mock transport [0028]: the
 * routes, the bodies, and decoding what the server documents.
 */
class HttpMfaRepositoryTest {

    private val json = headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))

    private fun client(engine: MockEngine) = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

    private val status =
        """{"enabled":true,"enabled_at":"2026-11-06T04:00:00Z","recovery_codes_left":2,
        "recommended":true,"required":false}"""

    private val codes = """{"recovery_codes":["AAAAA-BBBBB","CCCCC-DDDDD"]}"""

    @Test
    fun `the status is read from the account's own route`() = runTest {
        val engine = MockEngine { respond(status, HttpStatusCode.OK, json) }

        val ok = assertIs<AuthResult.Ok<MfaStatusDto>>(HttpMfaRepository(client(engine)).status())

        val request = engine.requestHistory.single()
        assertEquals(HttpMethod.Get, request.method)
        assertEquals("/v1/me/mfa", request.url.encodedPath)
        assertEquals(2, ok.value.recoveryCodesLeft)
        assertEquals(true, ok.value.enabled)
    }

    @Test
    fun `setup posts nothing and reads the secret back`() = runTest {
        val engine =
            MockEngine {
                respond("""{"secret":"JBSWY3DPEHPK3PXP","otpauth_uri":"otpauth://totp/x"}""", HttpStatusCode.OK, json)
            }

        val ok = assertIs<AuthResult.Ok<MfaSetupDto>>(HttpMfaRepository(client(engine)).setup())

        val request = engine.requestHistory.single()
        assertEquals(HttpMethod.Post, request.method)
        assertEquals("/v1/me/mfa/setup", request.url.encodedPath)
        assertEquals("JBSWY3DPEHPK3PXP", ok.value.secret)
    }

    @Test
    fun `confirming posts the code and reads the ten codes`() = runTest {
        val engine = MockEngine { respond(codes, HttpStatusCode.OK, json) }

        val ok = assertIs<AuthResult.Ok<MfaRecoveryCodesDto>>(HttpMfaRepository(client(engine)).confirm("123456"))

        val request = engine.requestHistory.single()
        assertEquals("/v1/me/mfa/confirm", request.url.encodedPath)
        assertEquals("""{"code":"123456"}""", (request.body as TextContent).text)
        assertEquals(2, ok.value.recoveryCodes.size)
    }

    @Test
    fun `turning off posts only the code given and reads the new status`() = runTest {
        val off = """{"enabled":false,"recovery_codes_left":0,"recommended":true,"required":false}"""
        val engine = MockEngine { respond(off, HttpStatusCode.OK, json) }
        val repository = HttpMfaRepository(client(engine))

        assertIs<AuthResult.Ok<MfaStatusDto>>(repository.disable("123456", null))
        assertIs<AuthResult.Ok<MfaStatusDto>>(repository.disable(null, "ABCDE-FGHJK"))

        val (byCode, byRecovery) = engine.requestHistory
        assertEquals("/v1/me/mfa/disable", byCode.url.encodedPath)
        assertEquals("""{"code":"123456"}""", (byCode.body as TextContent).text)
        assertEquals("""{"recovery_code":"ABCDE-FGHJK"}""", (byRecovery.body as TextContent).text)
    }

    @Test
    fun `new recovery codes post the code to their own route`() = runTest {
        val engine = MockEngine { respond(codes, HttpStatusCode.OK, json) }

        assertIs<AuthResult.Ok<MfaRecoveryCodesDto>>(HttpMfaRepository(client(engine)).renewRecoveryCodes("654321"))

        val request = engine.requestHistory.single()
        assertEquals("/v1/me/mfa/recovery-codes", request.url.encodedPath)
        assertEquals("""{"code":"654321"}""", (request.body as TextContent).text)
    }

    @Test
    fun `an administrator turning it off comes back as the server's envelope`() = runTest {
        val engine =
            MockEngine {
                respond(
                    """{"error":{"code":"MFA_REQUIRED","retryable":false,"message_key":"mfa.required_for_admin"}}""",
                    HttpStatusCode.Conflict,
                    json,
                )
            }

        val refused = assertIs<AuthResult.Refused>(HttpMfaRepository(client(engine)).disable("123456", null))

        assertEquals("mfa.required_for_admin", refused.envelope.error.messageKey)
        assertEquals(false, refused.envelope.error.retryable)
    }

    @Test
    fun `no answer at all is a transport failure`() = runTest {
        val engine = MockEngine { error("offline") }

        assertEquals(AuthResult.TransportFailure, HttpMfaRepository(client(engine)).confirm("123456"))
    }
}
