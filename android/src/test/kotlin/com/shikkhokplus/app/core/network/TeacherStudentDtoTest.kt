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
}
