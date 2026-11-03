package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * The pay-any-time DTOs: every money value crosses the wire as a JSON
 * string, inbound and outbound, and a JSON number fails loudly.
 */
class PayDtoTest {

    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun `an owed total decodes from a json string`() {
        val dto =
            json.decodeFromString<OwedTogetherDto>(
                """{"owed_together":"2000.00","children":[
                  |{"enrollment_id":"e-1","display_name":"Tanvir","owed":"1000.00"}]}
                """.trimMargin(),
            )

        assertEquals(Money.of("2000.00"), dto.owedTogether)
        assertEquals(Money.of("1000.00"), dto.children.single().owed)
    }

    @Test
    fun `an owed total fails loudly on a json number`() {
        assertFailsWith<SerializationException> {
            json.decodeFromString<OwedTogetherDto>("""{"owed_together":2000.00,"children":[]}""")
        }
    }

    @Test
    fun `a child's owed figure fails loudly on a json number`() {
        assertFailsWith<SerializationException> {
            json.decodeFromString<OwedChildDto>("""{"enrollment_id":"e-1","display_name":"T","owed":1000}""")
        }
    }

    @Test
    fun `a recorded payment decodes its amounts from json strings`() {
        val dto =
            json.decodeFromString<PaymentSubmittedDto>(
                """{"submission_id":"s-1","status":"pending","total_amount":"1000.00","paid_on":"2026-11-02",
                  |"claims":[{"claim_id":"c-1","claimed_amount":"1000.00","display_name":"Tanvir",
                  |"enrollment_id":"e-1","period":"2026-11"}]}
                """.trimMargin(),
            )

        assertEquals(Money.of("1000.00"), dto.totalAmount)
        assertEquals(Money.of("1000.00"), dto.claims.single().claimedAmount)
    }

    @Test
    fun `a recorded payment fails loudly on a json number`() {
        assertFailsWith<SerializationException> {
            json.decodeFromString<PaymentSubmittedDto>(
                """{"submission_id":"s-1","status":"pending","total_amount":1000,"paid_on":"2026-11-02","claims":[]}""",
            )
        }
    }

    @Test
    fun `a submitted amount encodes as a json string and every field is sent`() {
        val encoded =
            json.encodeToString(
                PaymentSubmitDto.serializer(),
                PaymentSubmitDto(listOf("e-1"), null, true, Money.of("500.00"), "2026-11-02"),
            )

        assertTrue(""""amount":"500.00"""" in encoded, "the amount was not a JSON string: $encoded")
        assertTrue(""""payment_method_id":null""" in encoded, encoded)
        assertTrue(""""transaction_id":null""" in encoded, encoded)
        assertTrue(""""cash":true""" in encoded, encoded)
    }

    @Test
    fun `the replay key goes on the wire as client_mutation_id`() {
        // [PA-DB-1] The server's contract: an optional JSON string field
        // named exactly this. Encoded with the app's own client settings,
        // since those are what reach the server.
        val encoded =
            ApiClient.json.encodeToString(
                PaymentSubmitDto.serializer(),
                PaymentSubmitDto(
                    listOf("e-1"),
                    null,
                    true,
                    Money.of("500.00"),
                    "2026-11-02",
                    clientMutationId = "8b6f3d1e-5c2a-4e7b-9f10-2a3b4c5d6e7f",
                ),
            )

        assertTrue(
            """"client_mutation_id":"8b6f3d1e-5c2a-4e7b-9f10-2a3b4c5d6e7f"""" in encoded,
            "the key was not sent as a JSON string under its wire name: $encoded",
        )
    }

    @Test
    fun `the family methods response decodes with no methods`() {
        val dto =
            json.decodeFromString<FamilyPaymentMethodsDto>(
                """{"methods":[],"services":["bKash"],"teacher_display_name":null}""",
            )

        assertEquals(emptyList(), dto.methods)
        assertEquals(null, dto.teacherDisplayName)
    }
}
