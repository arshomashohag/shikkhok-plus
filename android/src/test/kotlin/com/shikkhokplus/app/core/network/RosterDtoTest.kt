package com.shikkhokplus.app.core.network

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

/**
 * A roster row's emails, decoded from JSON strings written from
 * `RosterRowResponse` [FR6.1, NFR6.1, NFR9.1], and never printed [NFR3.2].
 */
class RosterDtoTest {

    private fun row(extra: String): RosterRowDto =
        ApiClient.json.decodeFromString(
            RosterRowDto.serializer(),
            """{"enrollment_id":"e-1","student_id":"s-1","display_name":"Rafiq","guardian_phone":null,""" +
                """"fee_amount":null,"status":"active","student_state":"accepted","guardian_state":"pending",""" +
                """"is_removable":false,"inactive_from":null$extra}""",
        )

    @Test
    fun `both emails decode when present`() {
        val decoded = row(""","student_email":"rafiq@example.com","guardian_email":"parent@example.com"""")

        assertEquals("rafiq@example.com", decoded.studentEmail)
        assertEquals("parent@example.com", decoded.guardianEmail)
    }

    @Test
    fun `null emails decode as null`() {
        val decoded = row(""","student_email":null,"guardian_email":null""")

        assertNull(decoded.studentEmail)
        assertNull(decoded.guardianEmail)
    }

    @Test
    fun `absent emails decode as null, so an older server still reads`() {
        val decoded = row("")

        assertNull(decoded.studentEmail)
        assertNull(decoded.guardianEmail)
    }

    @Test
    fun `a row never prints a contact`() {
        val decoded =
            row(""","student_email":"sentinel@example.invalid","guardian_email":null""")
                .copy(guardianPhone = "+8801999999999")

        val text = decoded.toString()
        assertFalse("sentinel@example.invalid" in text, text)
        assertFalse("+8801999999999" in text, text)
    }
}
