package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.serialization.json.Json

/**
 * A teacher's student decodes its amounts from JSON **strings** and
 * fails loudly on a JSON **number** [TC-7, D-20].
 *
 * The loud failure is the obligation: a lenient decoder that accepts a
 * number passes a happy-path test while the value is already a float.
 */
class TeacherStudentDtoTest {

    private val json = Json { ignoreUnknownKeys = true }

    private fun student(total: String, seatOwes: String) =
        """
        {
          "student_id": "s-1",
          "display_name": "Rafiq Hasan",
          "student_phone": "+8801812345678",
          "guardian_phone": null,
          "student_state": "accepted",
          "guardian_state": "absent",
          "enrollments": [
            {
              "enrollment_id": "e-1",
              "batch_id": "b-1",
              "batch_name": "Physics",
              "fee_amount": "1200.00",
              "status": "active",
              "inactive_from": null,
              "outstanding": $seatOwes,
              "is_removable": false
            }
          ],
          "total_outstanding": $total,
          "is_removable": false
        }
        """

    @Test
    fun `a student decodes every amount from a JSON string`() {
        val decoded = json.decodeFromString<TeacherStudentDto>(student("\"1200.00\"", "\"1200.00\""))

        assertEquals(Money.of("1200.00"), decoded.totalOutstanding)
        assertEquals(Money.of("1200.00"), decoded.enrollments.single().outstanding)
        assertEquals(Money.of("1200.00"), decoded.enrollments.single().feeAmount)
        assertNull(decoded.guardianPhone)
    }

    @Test
    fun `a student REFUSES a total sent as a JSON number`() {
        assertFailsWith<Exception> {
            json.decodeFromString<TeacherStudentDto>(student("1200.00", "\"1200.00\""))
        }
    }

    @Test
    fun `a seat REFUSES what it owes sent as a JSON number`() {
        assertFailsWith<Exception> {
            json.decodeFromString<TeacherStudentDto>(student("\"1200.00\"", "1200.00"))
        }
    }

    @Test
    fun `a student in no batch decodes with no seats`() {
        val decoded =
            json.decodeFromString<TeacherStudentDto>(
                """
                {
                  "student_id": "s-2",
                  "display_name": "Mehedi",
                  "student_state": "pending",
                  "guardian_state": "absent",
                  "enrollments": [],
                  "total_outstanding": "0.00",
                  "is_removable": true
                }
                """,
            )

        assertTrue(decoded.enrollments.isEmpty())
        assertTrue(decoded.isRemovable)
    }

    // --- U3: emails [FR6.1, W7.5, NFR3.2, NFR9.1] -----------------------------

    private fun withEmails(student: String, guardian: String?): TeacherStudentDto {
        val fields =
            listOfNotNull(
                """"student_email": $student""",
                guardian?.let { """"guardian_email": $it""" },
            ).joinToString(",")
        return ApiClient.json.decodeFromString(
            TeacherStudentDto.serializer(),
            """{"student_id":"s-1","display_name":"Rafiq","student_state":"pending","guardian_state":"absent",""" +
                """"enrollments":[],"total_outstanding":"0.00","is_removable":true,$fields}""",
        )
    }

    @Test
    fun `the emails decode when present, null, or absent`() {
        val present = withEmails("\"rafiq@example.com\"", "\"parent@example.com\"")
        val nulls = withEmails("null", "null")
        val absent = withEmails("null", null)

        assertEquals("rafiq@example.com", present.studentEmail)
        assertEquals("parent@example.com", present.guardianEmail)
        assertNull(nulls.studentEmail)
        assertNull(absent.guardianEmail)
    }

    @Test
    fun `a create carries the emails it has and leaves blanks out`() {
        val body =
            ApiClient.json.encodeToString(
                StudentCreateBody.serializer(),
                StudentCreateBody(displayName = "Rafiq", studentEmail = "rafiq@example.com"),
            )

        assertEquals("""{"display_name":"Rafiq","student_email":"rafiq@example.com"}""", body)
    }

    @Test
    fun `an edit omits an unchanged email, sends a set one, and sends null to clear`() {
        val unchanged =
            ApiClient.json.encodeToString(StudentUpdateBody.serializer(), StudentUpdateBody(displayName = "R"))
        val setAndClear =
            ApiClient.json.encodeToString(
                StudentUpdateBody.serializer(),
                StudentUpdateBody(
                    studentEmail = com.shikkhokplus.app.core.model.EmailEdit.Set(" rafiq@example.com "),
                    guardianEmail = com.shikkhokplus.app.core.model.EmailEdit.Clear,
                ),
            )

        assertEquals("""{"display_name":"R"}""", unchanged)
        // The explicit null survives `explicitNulls = false`: that is the clear.
        assertEquals("""{"student_email":"rafiq@example.com","guardian_email":null}""", setAndClear)
    }

    @Test
    fun `an edit body is write-only`() {
        assertFailsWith<Exception> {
            ApiClient.json.decodeFromString(StudentUpdateBody.serializer(), """{"display_name":"R"}""")
        }
    }

    @Test
    fun `a student and its bodies never print a contact`() {
        val printed =
            listOf(
                withEmails("\"sentinel@example.invalid\"", null).copy(studentPhone = "+8801999999999").toString(),
                StudentCreateBody(
                    displayName = "R",
                    studentPhone = "+8801999999999",
                    guardianEmail = "sentinel@example.invalid",
                ).toString(),
                StudentUpdateBody(
                    guardianPhone = "+8801999999999",
                    studentEmail = com.shikkhokplus.app.core.model.EmailEdit.Set("sentinel@example.invalid"),
                ).toString(),
            )

        printed.forEach { text ->
            assertTrue("+8801999999999" !in text && "sentinel@example.invalid" !in text, text)
        }
    }
}
