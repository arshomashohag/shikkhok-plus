package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/** The payment-review wire shapes: money as strings, every approval field sent. */
class VerificationDtoTest {

    private val json = Json { ignoreUnknownKeys = false }

    private val payment =
        """
        {"submission_id":"s","batch_name":"B",
         "children":[{"enrollment_id":"e","claim_id":"c","display_name":"A",
                      "period":"2026-10","owed":"1000.00","approved_amount":null}],
         "owed_together":"1000.00","total_amount":"800.00","comparison":"short",
         "difference":"200.00","method":{"kind":"bank","provider":"BRAC","account_number":"1234"},
         "paid_on":"2026-10-28","submitted_at":"2026-10-28T10:00:00Z","status":"pending"}
        """

    @Test
    fun `a payment decodes its amounts from strings`() {
        val dto = json.decodeFromString<PaymentReviewDto>(payment)

        assertEquals(Money.of("800.00"), dto.totalAmount)
        assertEquals(Money.of("1000.00"), dto.children.single().owed)
    }

    @Test
    fun `a payment REFUSES a child's owed figure as a JSON number`() {
        assertFailsWith<Exception> {
            json.decodeFromString<PaymentReviewDto>(payment.replace("\"owed\":\"1000.00\"", "\"owed\":1000.00"))
        }
    }

    @Test
    fun `an approval sends every field including the empty ones`() {
        val body = Json.encodeToString(PaymentApprovalBodyDto(Money.of("800.00")))
        val sent = Json.parseToJsonElement(body).jsonObject

        assertEquals("800.00", sent.getValue("received_amount").jsonPrimitive.content)
        assertEquals(
            setOf(
                "received_amount",
                "shortfall_disposition",
                "carried_by_enrollment_id",
                "credit_to_enrollment_id",
                "note",
                "correcting",
            ),
            sent.keys,
        )
    }
}
