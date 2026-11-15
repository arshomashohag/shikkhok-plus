package com.shikkhokplus.app.core.network

import kotlinx.serialization.builtins.ListSerializer
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The centre members list, decoded from the JSON the server sends.
 *
 * **The regression for functional-spec § 1 defect 1, written first.**
 * `MemberResponse.phone` became `string | null` when invitations by
 * email arrived (C2). A client that declares it non-null fails the
 * WHOLE list on one email-only invitation, so every manager of that
 * centre loses the members screen -- the place they revoke access.
 * Decoded from a JSON string through the app's own [ApiClient.json],
 * because the contract gates build only the non-null arm of a nullable
 * field and cannot see this.
 */
class CentreDtoTest {

    private val members = ListSerializer(MemberDto.serializer())

    @Test
    fun `a member invited by email alone decodes with no phone and the email kept`() {
        val decoded =
            ApiClient.json.decodeFromString(
                members,
                """[{"member_id":"m1","display_name":"Rina","phone":null,""" +
                    """"invited_email":"rina@example.com","invited_at":"2026-11-14T10:00:00Z",""" +
                    """"role":"teacher","decision":"pending","revoked":false,"is_you":false}]""",
            )

        val member = decoded.single()
        assertNull(member.phone)
        assertEquals("rina@example.com", member.invitedEmail)
        assertEquals("Rina", member.displayName)
    }

    @Test
    fun `a member invited by phone decodes the number unchanged`() {
        val decoded =
            ApiClient.json.decodeFromString(
                members,
                """[{"member_id":"m2","display_name":"Karim","phone":"+8801712345678",""" +
                    """"invited_email":null,"invited_at":"2026-11-14T10:00:00Z",""" +
                    """"role":"manager","decision":"accepted","revoked":false,"is_you":true}]""",
            )

        val member = decoded.single()
        assertEquals("+8801712345678", member.phone)
        assertNull(member.invitedEmail)
    }

    @Test
    fun `a member and an invitation never print a contact`() {
        val member =
            MemberDto("m1", "Rina", "+8801999999999", "teacher", "pending", invitedEmail = "sentinel@example.invalid")
        val invite = MemberInviteDto("Rina", "+8801999999999", "teacher", "sentinel@example.invalid")

        listOf(member.toString(), invite.toString()).forEach { text ->
            kotlin.test.assertFalse("+8801999999999" in text || "sentinel@example.invalid" in text, text)
        }
    }

    @Test
    fun `an email-only invitation leaves the phone out of the body`() {
        assertEquals(
            """{"display_name":"Rina","role":"teacher","email":"rina@example.com"}""",
            ApiClient.json.encodeToString(
                MemberInviteDto.serializer(),
                MemberInviteDto(displayName = "Rina", role = "teacher", email = "rina@example.com"),
            ),
        )
    }

    @Test
    fun `one email-only member does not fail the rest of the list`() {
        val decoded =
            ApiClient.json.decodeFromString(
                members,
                """[{"member_id":"m1","display_name":"Rina","phone":null,"invited_email":"rina@example.com",""" +
                    """"invited_at":"2026-11-14T10:00:00Z","role":"teacher","decision":"pending",""" +
                    """"revoked":false,"is_you":false},""" +
                    """{"member_id":"m2","display_name":"Karim","phone":"+8801712345678","invited_email":null,""" +
                    """"invited_at":"2026-11-14T10:00:00Z","role":"manager","decision":"accepted",""" +
                    """"revoked":false,"is_you":true}]""",
            )

        assertEquals(listOf("m1", "m2"), decoded.map { it.memberId })
    }
}
