package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * Sign-up over HTTP: the body carries exactly one identifier and no
 * password, and the already-added lookup asks about a number.
 */
class HttpSignupRepositoryTest {

    private val json = headersOf("Content-Type", "application/json")

    @Test
    fun `an email sign-up sends the email, no phone, and no password`() = runTest {
        var sent: String? = null
        val engine =
            MockEngine { request ->
                sent = (request.body as TextContent).text
                respond("""{"account_id":"a1","code_sent_to":"rafi@example.com"}""", HttpStatusCode.Created, json)
            }
        val repository = HttpSignupRepository(ApiClient.build("https://staging.example", engine, TokenStore.InMemory()))

        val ok =
            assertIs<AuthResult.Ok<SignupResponseDto>>(
                repository.signup(
                    Identifier.email(" rafi@example.com "),
                    "student",
                    "Rafi",
                    PostalAddress("House 1", "Road 2", "Dhaka", "1205"),
                ),
            )

        assertEquals("rafi@example.com", ok.value.codeSentTo)
        assertEquals(
            """{"email":"rafi@example.com","role":"student","self_name":"Rafi","address_house":"House 1",""" +
                """"address_road":"Road 2","address_city":"Dhaka","address_postcode":"1205"}""",
            sent,
        )
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
}
