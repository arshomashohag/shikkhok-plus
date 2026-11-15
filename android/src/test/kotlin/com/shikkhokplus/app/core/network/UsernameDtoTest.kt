package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.ui.AvailabilityMapper
import com.shikkhokplus.app.core.ui.AvailabilityState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

/**
 * The username and contact wire shapes, decoded from JSON strings written
 * from the committed `openapi.json` schemas and encoded as the server
 * reads them [NFR6.1, NFR6.3, NFR9.1], and never printed [NFR3.2].
 */
class UsernameDtoTest {

    private fun availability(json: String) =
        ApiClient.json.decodeFromString(UsernameAvailabilityDto.serializer(), json)

    private fun change(json: String) = ApiClient.json.decodeFromString(UsernameChangeDto.serializer(), json)

    @Test
    fun `each of the four statuses decodes`() {
        listOf("available", "unavailable", "reserved").forEach {
            assertEquals(it, availability("""{"status":"$it","message_key":null}""").status)
        }
        val invalid = availability("""{"status":"invalid","message_key":"account.username.too_short"}""")
        assertEquals("account.username.too_short", invalid.messageKey)
    }

    @Test
    fun `an unknown status decodes, and reads as could-not-check`() {
        val unknown = availability("""{"status":"pondering","message_key":null,"extra":1}""")

        assertEquals("pondering", unknown.status)
        assertEquals(AvailabilityState.CouldNotCheck, AvailabilityMapper.afterLookup(AuthResult.Ok(unknown)))
    }

    @Test
    fun `a change answer decodes with and without the next change date`() {
        val dated = change("""{"username":"Nadia_K","next_change_at":"2026-12-14T10:00:00Z"}""")
        val undated = change("""{"username":"Nadia_K","next_change_at":null}""")

        assertEquals("Nadia_K", dated.username)
        assertEquals("2026-12-14T10:00:00Z", dated.nextChangeAt)
        assertNull(undated.nextChangeAt)
    }

    @Test
    fun `a first choice leaves the password out of the body, a rename carries it`() {
        val first =
            ApiClient.json.encodeToString(UsernameChangeRequest.serializer(), UsernameChangeRequest("nadia_k"))
        val rename =
            ApiClient.json.encodeToString(
                UsernameChangeRequest.serializer(),
                UsernameChangeRequest("nadia_k", "correct horse"),
            )

        assertEquals("""{"username":"nadia_k"}""", first)
        assertEquals("""{"username":"nadia_k","password":"correct horse"}""", rename)
    }

    @Test
    fun `a removal names the kind and the password`() {
        assertEquals(
            """{"kind":"email","password":"correct horse"}""",
            ApiClient.json.encodeToString(
                ContactRemoveRequest.serializer(),
                ContactRemoveRequest("email", "correct horse"),
            ),
        )
    }

    @Test
    fun `a verify omits the username unless it is a replacement`() {
        val first =
            ApiClient.json.encodeToString(
                VerifyRequest.serializer(),
                VerifyRequest(phone = "+8801711111111", code = "123456"),
            )
        val replacement =
            ApiClient.json.encodeToString(
                VerifyRequest.serializer(),
                VerifyRequest(phone = "+8801711111111", code = "123456", username = "nadia_k2"),
            )

        assertEquals("""{"phone":"+8801711111111","code":"123456"}""", first)
        assertEquals("""{"phone":"+8801711111111","code":"123456","username":"nadia_k2"}""", replacement)
    }

    @Test
    fun `no request or answer here prints a username, a contact, a code or a password`() {
        val printed =
            listOf(
                UsernameAvailabilityRequest("sentinel_user_7"),
                UsernameChangeRequest("sentinel_user_7", "sentinel-pass"),
                UsernameChangeDto("sentinel_user_7", null),
                ContactChangeRequest(phone = "+8801999999999", password = "sentinel-pass"),
                ContactChangeRequest(email = "sentinel@example.invalid", password = "sentinel-pass"),
                ContactRemoveRequest("phone", "sentinel-pass"),
                VerifyRequest(email = "sentinel@example.invalid", code = "123456", username = "sentinel_user_7"),
                PasswordSignInRequest(password = "sentinel-pass", login = "sentinel_user_7"),
                SignupRequestDto(
                    email = "sentinel@example.invalid",
                    role = "student",
                    selfName = "Rafi",
                    addressHouse = "1",
                    addressRoad = "2",
                    addressCity = "Dhaka",
                    addressPostcode = "1205",
                    username = "sentinel_user_7",
                ),
            ).map { it.toString() }

        printed.forEach { text ->
            listOf("sentinel_user_7", "sentinel@example.invalid", "+8801999999999", "sentinel-pass", "123456")
                .forEach { secret -> assertFalse(secret in text, text) }
        }
    }
}
