package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.BuildConfig
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.get
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Every request says which app it comes from -- `android` and the app's
 * version -- including the three that reach a token route: verify, the
 * cold-start refresh and the mid-session renewal.
 */
class ClientPlatformTest {

    private val json = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

    private val pair = """{"access_token":"fresh","refresh_token":"r2","expires_in":900}"""

    @Test
    fun `an ordinary request carries the platform and the build's version`() = runTest {
        val engine = MockEngine { respond("""{"ok":true}""", HttpStatusCode.OK, json) }
        val client = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

        client.get("/v1/me")

        val headers = engine.requestHistory.single().headers
        assertEquals("android", headers[ClientPlatform.PLATFORM_HEADER])
        assertEquals(BuildConfig.VERSION_NAME, headers[ClientPlatform.VERSION_HEADER])
        assertEquals(1, headers.getAll(ClientPlatform.PLATFORM_HEADER)?.size, "sent once, not appended twice")
    }

    @Test
    fun `sign-in and the cold-start refresh carry both headers`() = runTest {
        val engine = MockEngine { respond(pair, HttpStatusCode.OK, json) }
        val tokens = TokenStore.InMemory().apply { save("a", "r1") }
        val client = ApiClient.build("https://staging.example", engine, tokens, appVersion = "1.4.0")
        val auth = HttpAuthRepository(client, tokens)

        auth.verify("01711234567", "123456")
        auth.refresh()

        assertEquals(listOf("/v1/auth/verify", "/v1/auth/refresh"), engine.requestHistory.map { it.url.encodedPath })
        engine.requestHistory.forEach {
            assertEquals("android", it.headers[ClientPlatform.PLATFORM_HEADER])
            assertEquals("1.4.0", it.headers[ClientPlatform.VERSION_HEADER])
        }
    }

    @Test
    fun `the mid-session renewal carries both headers too`() = runTest {
        // The renewal is built inside the send stage, past the plugin that
        // writes the headers for every other request, so it writes its own.
        val tokens = TokenStore.InMemory().apply { save("stale", "r1") }
        val engine =
            MockEngine { request ->
                when {
                    request.url.encodedPath == "/v1/auth/refresh" -> respond(pair, HttpStatusCode.OK, json)
                    request.headers[HttpHeaders.Authorization] == "Bearer fresh" ->
                        respond("""{"ok":true}""", HttpStatusCode.OK, json)
                    else -> respond("", HttpStatusCode.Unauthorized, json)
                }
            }
        val client = ApiClient.build("https://staging.example", engine, tokens, appVersion = "1.4.0")

        client.get("/v1/me")

        val refresh = engine.requestHistory.single { it.url.encodedPath == "/v1/auth/refresh" }
        assertEquals("android", refresh.headers[ClientPlatform.PLATFORM_HEADER])
        assertEquals("1.4.0", refresh.headers[ClientPlatform.VERSION_HEADER])
        assertEquals(3, engine.requestHistory.size, "expired, renewed, repeated")
        engine.requestHistory.forEach { assertEquals("android", it.headers[ClientPlatform.PLATFORM_HEADER]) }
    }

    @Test
    fun `a version is reduced to what the server keeps`() {
        assertEquals("1.4.0-rc.1+42", ClientPlatform.version("1.4.0-rc.1+42"))
        assertEquals("1.4.0beta", ClientPlatform.version("1.4.0 beta"))
        assertEquals("1.4.0", ClientPlatform.version("1.4.0১\n"), "non-ASCII digits and control characters go")
        assertEquals(32, ClientPlatform.version("1".repeat(40))?.length)
        assertNull(ClientPlatform.version(" ()/ "))
    }

    @Test
    fun `a version with nothing usable is not sent, the platform still is`() = runTest {
        val engine = MockEngine { respond("""{"ok":true}""", HttpStatusCode.OK, json) }
        val client = ApiClient.build("https://staging.example", engine, TokenStore.InMemory(), appVersion = "???")

        client.get("/v1/me")

        val headers = engine.requestHistory.single().headers
        assertEquals("android", headers[ClientPlatform.PLATFORM_HEADER])
        assertNull(headers[ClientPlatform.VERSION_HEADER])
    }

    @Test
    fun `nothing but the platform and the version is added`() = runTest {
        // Not a device identifier [TC-3, D-37]: the only headers this
        // client adds on its own are the content type and these two.
        val engine = MockEngine { respond("""{"ok":true}""", HttpStatusCode.OK, json) }
        val client = ApiClient.build("https://staging.example", engine, TokenStore.InMemory(), appVersion = "1.4.0")

        client.get("/v1/me")

        val names = engine.requestHistory.single().headers.names().map { it.lowercase() }.toSet()
        val added = names - setOf("content-type", "accept", "accept-charset", "content-length")
        assertEquals(setOf("x-client-platform", "x-client-version"), added)
    }
}
