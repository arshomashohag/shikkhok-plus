package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * Sign-up over HTTP: the body carries exactly one identifier, the
 * username and no password; the already-added lookup asks about a number
 * or an email; and the public username lookup sends the name in a body,
 * never in the URL [FR2.1, FR3.1, W9; NFR3.1].
 */
class HttpSignupRepositoryTest {

    private val json = headersOf("Content-Type", "application/json")

    private class Seen {
        var method: HttpMethod? = null
        var path: String? = null
        var query: String? = null
        var body: String? = null
    }

    private fun repository(status: HttpStatusCode, reply: String, seen: Seen = Seen()): HttpSignupRepository {
        val engine =
            MockEngine { request ->
                seen.method = request.method
                seen.path = request.url.encodedPath
                seen.query = request.url.encodedQuery
                seen.body = (request.body as? TextContent)?.text
                respond(reply, status, json)
            }
        return HttpSignupRepository(ApiClient.build("https://staging.example", engine, TokenStore.InMemory()))
    }

    @Test
    fun `an email sign-up sends the email, the username, no phone, and no password`() = runTest {
        val seen = Seen()
        val repository =
            repository(HttpStatusCode.Created, """{"account_id":"a1","code_sent_to":"rafi@example.com"}""", seen)

        val ok =
            assertIs<AuthResult.Ok<SignupResponseDto>>(
                repository.signup(
                    Identifier.email(" rafi@example.com "),
                    "student",
                    "Rafi",
                    PostalAddress("House 1", "Road 2", "Dhaka", "1205"),
                    username = " rahim_math ",
                ),
            )

        assertEquals("rafi@example.com", ok.value.codeSentTo)
        assertEquals(HttpMethod.Post, seen.method)
        assertEquals("/v1/accounts", seen.path)
        assertEquals(
            """{"email":"rafi@example.com","role":"student","self_name":"Rafi","address_house":"House 1",""" +
                """"address_road":"Road 2","address_city":"Dhaka","address_postcode":"1205",""" +
                """"username":"rahim_math"}""",
            seen.body,
        )
    }

    @Test
    fun `a username refusal at sign-up comes back Refused with its key`() = runTest {
        val repository =
            repository(
                HttpStatusCode.Conflict,
                """{"error":{"code":"USERNAME_UNAVAILABLE","retryable":false,""" +
                    """"message_key":"account.username.unavailable"}}""",
            )

        val refused =
            assertIs<AuthResult.Refused>(
                repository.signup(
                    Identifier.phone("01711234567"),
                    "student",
                    "Rafi",
                    PostalAddress("House 1", "Road 2", "Dhaka", "1205"),
                    username = "nadia_k",
                ),
            )

        assertEquals("account.username.unavailable", refused.envelope.error.messageKey)
    }

    @Test
    fun `the already-added lookup asks about the number typed`() = runTest {
        var query: String? = null
        val engine =
            MockEngine { request ->
                query = request.url.parameters["phone"]
                respond("""{"already_added":false}""", HttpStatusCode.OK, json)
            }
        val repository = HttpSignupRepository(ApiClient.build("https://staging.example", engine, TokenStore.InMemory()))

        assertIs<AuthResult.Ok<AlreadyAddedDto>>(repository.lookup("01711234567"))
        assertEquals("01711234567", query)
    }

    @Test
    fun `the already-added lookup by email asks about the address, trimmed`() = runTest {
        val seen = Seen()
        val repository = repository(HttpStatusCode.OK, """{"already_added":true,"role":"student"}""", seen)

        val ok = assertIs<AuthResult.Ok<AlreadyAddedDto>>(repository.lookupEmail(" rina@example.com "))

        assertEquals(HttpMethod.Get, seen.method)
        assertEquals("/v1/accounts/already-added", seen.path)
        // The one query string allowed: C2 defines it for the person's own typed address.
        assertEquals("email=rina%40example.com", seen.query)
        assertEquals("student", ok.value.role)
    }

    @Test
    fun `the public username lookup posts the name in a body with no query string`() = runTest {
        val seen = Seen()
        val repository = repository(HttpStatusCode.OK, """{"status":"available","message_key":null}""", seen)

        val ok = assertIs<AuthResult.Ok<UsernameAvailabilityDto>>(repository.checkUsername(" Rahim.Uddin "))

        assertEquals(HttpMethod.Post, seen.method)
        assertEquals("/v1/accounts/username-availability", seen.path)
        assertEquals("", seen.query)
        assertEquals("""{"username":"Rahim.Uddin"}""", seen.body)
        assertEquals("available", ok.value.status)
    }

    @Test
    fun `a lookup ceiling comes back Refused with its key`() = runTest {
        val repository =
            repository(
                HttpStatusCode.TooManyRequests,
                """{"error":{"code":"TOO_MANY","retryable":false,"message_key":"auth.lookup.too_many"}}""",
            )

        val refused = assertIs<AuthResult.Refused>(repository.checkUsername("nadia_k"))

        assertEquals("auth.lookup.too_many", refused.envelope.error.messageKey)
    }
}
