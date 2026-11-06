package com.shikkhokplus.app.feature.extrafees

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.BatchExtraFeesDto
import com.shikkhokplus.app.core.network.ExtraFeeDetailDto
import com.shikkhokplus.app.core.network.ExtraFeeRaiseRequestDto
import com.shikkhokplus.app.core.network.SeatAmountDto
import kotlinx.serialization.encodeToString
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * A fee's money is a JSON **string** both ways, and a JSON number is a
 * loud failure rather than a quiet conversion [TC-7, D-20].
 */
class ExtraFeeDtoTest {

    private val json = ApiClient.json

    private val batch =
        """
        {"fees": [{
          "extra_fee_id": "f-1", "purpose": "exam", "label": "Exam", "exam_title": null,
          "amount": "500.00", "due_on": "2026-11-20", "created_at": "2026-11-06T10:00:00Z",
          "student_count": 2, "paid_count": 1, "owing_count": 1,
          "charged_total": "1000.00", "collected_total": "700.00", "owed_total": "300.00",
          "waived_count": 0
        }],
         "chargeable_students": [{"enrollment_id": "e-1", "display_name": "Tanvir"}]}
        """.trimIndent()

    private val detail =
        """
        {"extra_fee_id": "f-1", "purpose": "other", "label": "Printing", "amount": "50.00",
         "due_on": "2026-11-20", "charged_total": "100.00", "collected_total": "50.00",
         "owed_total": "50.00", "created_at": "2026-11-06T10:00:00Z", "student_count": 2,
         "paid_count": 1, "owing_count": 1, "waived_count": 0,
         "students": [{"enrollment_id": "e-1", "display_name": "Tanvir", "charged": "50.00",
                       "paid": "0.00", "owed": "50.00", "status": "unpaid"}]}
        """.trimIndent()

    @Test
    fun `a batch's fees decode money from JSON strings`() {
        val decoded = json.decodeFromString<BatchExtraFeesDto>(batch)
        val fee = decoded.fees.single()
        assertEquals(Money.of("500.00"), fee.amount)
        assertEquals(Money.of("300.00"), fee.owedTotal)
        assertEquals(listOf("Tanvir"), decoded.chargeableStudents.map { it.displayName })
    }

    @Test
    fun `a batch's fee rejects a JSON number for a total`() {
        assertFailsWith<Exception> {
            json.decodeFromString<BatchExtraFeesDto>(batch.replace("\"owed_total\": \"300.00\"", "\"owed_total\": 300"))
        }
    }

    @Test
    fun `a fee's students decode money from JSON strings and reject a number`() {
        assertEquals(Money.of("50.00"), json.decodeFromString<ExtraFeeDetailDto>(detail).students.single().owed)
        assertFailsWith<Exception> {
            json.decodeFromString<ExtraFeeDetailDto>(detail.replace("\"paid\": \"0.00\"", "\"paid\": 0"))
        }
    }

    @Test
    fun `a raise sends amounts as strings and always sends its lists`() {
        val body =
            json.encodeToString(
                ExtraFeeRaiseRequestDto(
                    purpose = "exam",
                    label = "Exam",
                    amount = Money.of("500.00"),
                    dueOn = "2026-11-20",
                    seatAmounts = listOf(SeatAmountDto("e-2", Money.ZERO)),
                    clientMutationId = "k",
                ),
            )
        assertTrue("\"amount\":\"500.00\"" in body, body)
        assertTrue("\"seat_amounts\":[{\"enrollment_id\":\"e-2\",\"amount\":\"0.00\"}]" in body, body)
        assertTrue("\"excluded_enrollment_ids\":[]" in body, body)
    }
}
