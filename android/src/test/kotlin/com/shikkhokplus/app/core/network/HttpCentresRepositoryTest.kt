package com.shikkhokplus.app.core.network

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
import kotlin.test.assertNull

/**
 * Centre invitations by phone or email, and the members list with an
 * email-only member [FR6.4, W8; NFR6.2].
 */
class HttpCentresRepositoryTest {

    private val json = headersOf("Content-Type", "application/json")

    private val created =
        """{"member_id":"m1","display_name":"Rina","phone":null,"invited_email":"rina@example.com",""" +
            """"invited_at":"2026-11-14T10:00:00Z","role":"teacher","decision":"pending",""" +
            """"revoked":false,"is_you":false}"""

    private fun repository(status: HttpStatusCode, reply: String, sent: MutableList<Pair<String, String?>>) =
        HttpCentresRepository(
            ApiClient.build(
                "https://staging.example",
                MockEngine { request ->
                    sent += "${request.method.value} ${request.url.encodedPath}" to (request.body as? TextContent)?.text
                    respond(reply, status, json)
                },
                TokenStore.InMemory(),
            ),
        )

    @Test
    fun `an email-only invitation omits the phone`() = runTest {
        val sent = mutableListOf<Pair<String, String?>>()

        val ok =
            assertIs<AuthResult.Ok<MemberDto>>(
                repository(HttpStatusCode.Created, created, sent).invite("Rina", null, " rina@example.com ", "teacher"),
            )

        assertEquals(
            listOf<Pair<String, String?>>(
                "POST /v1/centre/members" to """{"display_name":"Rina","role":"teacher","email":"rina@example.com"}""",
            ),
            sent,
        )
        assertNull(ok.value.phone)
    }

    @Test
    fun `a phone-only invitation omits the email, and blanks count as absent`() = runTest {
        val sent = mutableListOf<Pair<String, String?>>()

        repository(HttpStatusCode.Created, created, sent).invite("Karim", "01811223344", "  ", "manager")

        assertEquals(
            """{"display_name":"Karim","phone":"01811223344","role":"manager"}""",
            sent.single().second,
        )
    }

    @Test
    fun `an already-invited contact comes back with its key`() = runTest {
        val refused =
            assertIs<AuthResult.Refused>(
                repository(
                    HttpStatusCode.Conflict,
                    """{"error":{"code":"X","retryable":false,"message_key":"centre.member.already_invited"}}""",
                    mutableListOf(),
                ).invite("Rina", null, "rina@example.com", "teacher"),
            )

        assertEquals("centre.member.already_invited", refused.envelope.error.messageKey)
    }

    @Test
    fun `the members list loads with a member invited by email alone`() = runTest {
        val sent = mutableListOf<Pair<String, String?>>()

        val ok =
            assertIs<AuthResult.Ok<List<MemberDto>>>(repository(HttpStatusCode.OK, "[$created]", sent).members())

        assertEquals("rina@example.com", ok.value.single().invitedEmail)
    }
}
