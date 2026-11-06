package com.shikkhokplus.app.feature.expenses

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.ExpenseMonthDto
import com.shikkhokplus.app.core.network.ExpenseRequestDto
import com.shikkhokplus.app.core.network.MoneySummaryDto
import kotlinx.serialization.encodeToString
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * Money on the expense and summary wire is a JSON **string**, both ways,
 * and a JSON number is a loud failure rather than a quiet conversion
 * [TC-7, D-20]. Decoded with the app's own JSON configuration.
 */
class ExpenseDtoTest {

    private val json = ApiClient.json

    private val month =
        """
        {
          "month": "2026-11",
          "total": "450.00",
          "by_category": [{"category": "printing", "total": "450.00"}],
          "expenses": [{
            "expense_id": "x1", "category": "printing", "what": "Question papers",
            "amount": "450.00", "spent_on": "2026-11-03", "payee": null,
            "voided": false, "batch_id": null, "extra_fee_id": null
          }]
        }
        """.trimIndent()

    private val summary =
        """
        {
          "month": "2026-11",
          "collected": {"monthly": "3000.00", "exam": "500.00", "other": "0.00", "total": "3500.00"},
          "spent_total": "4000.00",
          "spent_by_category": [{"category": "rent", "total": "4000.00"}],
          "net": "500.00",
          "net_kind": "deficit",
          "owed_monthly": "1200.00",
          "owed_extra": "200.00",
          "extra_fees": [{"extra_fee_id": "f1", "label": "Exam", "collected": "500.00", "spent": "300.00"}]
        }
        """.trimIndent()

    @Test
    fun `a month decodes money from JSON strings and ignores fields it does not use`() {
        val decoded = json.decodeFromString<ExpenseMonthDto>(month)
        assertEquals(Money.of("450.00"), decoded.total)
        assertEquals(Money.of("450.00"), decoded.expenses.single().amount)
        assertEquals(Money.of("450.00"), decoded.byCategory.single().total)
    }

    @Test
    fun `a month rejects a JSON number for an expense amount`() {
        assertFailsWith<Exception> {
            json.decodeFromString<ExpenseMonthDto>(month.replace("\"amount\": \"450.00\"", "\"amount\": 450.00"))
        }
    }

    @Test
    fun `a month rejects a JSON number for its total`() {
        assertFailsWith<Exception> {
            json.decodeFromString<ExpenseMonthDto>(month.replace("\"total\": \"450.00\",\n", "\"total\": 450,\n"))
        }
    }

    @Test
    fun `a summary decodes every figure from JSON strings`() {
        val decoded = json.decodeFromString<MoneySummaryDto>(summary)
        assertEquals(Money.of("3500.00"), decoded.collected.total)
        assertEquals(Money.of("500.00"), decoded.net)
        assertEquals(Money.of("300.00"), decoded.extraFees.single().spent)
    }

    @Test
    fun `a summary rejects a JSON number for net`() {
        assertFailsWith<Exception> {
            json.decodeFromString<MoneySummaryDto>(summary.replace("\"net\": \"500.00\"", "\"net\": 500"))
        }
    }

    @Test
    fun `a summary rejects a JSON number inside collected`() {
        assertFailsWith<Exception> {
            json.decodeFromString<MoneySummaryDto>(summary.replace("\"exam\": \"500.00\"", "\"exam\": 500.0"))
        }
    }

    @Test
    fun `a recorded expense sends its amount as a string and always sends the retry key`() {
        val body =
            json.encodeToString(
                ExpenseRequestDto(
                    category = "printing",
                    what = "Question papers",
                    amount = Money.of("450.00"),
                    spentOn = "2026-11-03",
                    clientMutationId = "key-1",
                ),
            )
        assertTrue("\"amount\":\"450.00\"" in body, body)
        assertTrue("\"client_mutation_id\":\"key-1\"" in body, body)
        // Optional fields left out are omitted, not sent as null.
        assertTrue("payee" !in body, body)
    }
}
