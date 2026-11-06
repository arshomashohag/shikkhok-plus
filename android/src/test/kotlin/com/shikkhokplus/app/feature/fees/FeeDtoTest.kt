package com.shikkhokplus.app.feature.fees

import com.shikkhokplus.app.core.network.OwedTogetherDto
import com.shikkhokplus.app.core.network.SeatExtraFeesDto
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.BatchFeesDto
import com.shikkhokplus.app.core.network.ClaimDto
import com.shikkhokplus.app.core.network.CollectionsDto
import com.shikkhokplus.app.core.network.FeeHistoryDto
import com.shikkhokplus.app.core.network.HistoryLineDto
import com.shikkhokplus.app.core.network.FeeCycleDto
import com.shikkhokplus.app.core.network.PaymentDestinationDto
import com.shikkhokplus.app.core.network.RosterFeeRowDto
import com.shikkhokplus.app.core.network.toHistoryLine
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Money crosses the wire as a JSON **string**, in both directions.
 *
 * **The dangerous failure is a lenient decoder** [BR6.2, TC-7, D-20]:
 * one that quietly accepts a JSON number and converts it, so a
 * happy-path test on both sides passes while the value has already
 * lost precision on the client — where none of the backend's controls
 * reach. Every money-carrying DTO this unit adds therefore gets a test
 * proving the decode works from a string AND fails loudly on a number.
 *
 * A both-sides happy-path test cannot tell the two apart, which is why
 * the loud-failure half is the one that matters.
 */
class FeeDtoTest {

    private val json = Json { ignoreUnknownKeys = true }

    // -----------------------------------------------------------------
    // FeeCycleDto.
    // -----------------------------------------------------------------

    @Test
    fun `a fee cycle decodes money from a JSON string`() {
        val decoded =
            json.decodeFromString<FeeCycleDto>(
                """
                {
                  "period": "2027-02",
                  "due_date": "2027-02-28",
                  "charged": "1500.00",
                  "outstanding": "800.00",
                  "status": "partly_paid"
                }
                """.trimIndent(),
            )

        assertEquals(Money.of("1500.00"), decoded.charged)
        assertEquals(Money.of("800.00"), decoded.outstanding)
        assertEquals("partly_paid", decoded.status)
    }

    @Test
    fun `a fee cycle rejects a JSON number for charged`() {
        assertFailsWith<Exception> {
            json.decodeFromString<FeeCycleDto>(
                """
                {
                  "period": "2027-02",
                  "due_date": "2027-02-28",
                  "charged": 1500.00,
                  "outstanding": "800.00",
                  "status": "partly_paid"
                }
                """.trimIndent(),
            )
        }
    }

    @Test
    fun `a fee cycle rejects a JSON number for outstanding`() {
        // Both money fields, because a serializer attached to one and
        // forgotten on the other is the exact per-field failure the
        // type-level serializer exists to prevent.
        assertFailsWith<Exception> {
            json.decodeFromString<FeeCycleDto>(
                """
                {
                  "period": "2027-02",
                  "due_date": "2027-02-28",
                  "charged": "1500.00",
                  "outstanding": 800,
                  "status": "partly_paid"
                }
                """.trimIndent(),
            )
        }
    }

    @Test
    fun `a fee cycle rejects a non-canonical money string`() {
        // One decimal place is not the canonical form, and accepting
        // it would let "1500.0" and "1500.00" both arrive.
        assertFailsWith<Exception> {
            json.decodeFromString<FeeCycleDto>(
                """
                {
                  "period": "2027-02",
                  "due_date": "2027-02-28",
                  "charged": "1500.0",
                  "outstanding": "800.00",
                  "status": "unpaid"
                }
                """.trimIndent(),
            )
        }
    }

    // -----------------------------------------------------------------
    // RosterFeeRowDto.
    // -----------------------------------------------------------------

    @Test
    fun `a roster fee row decodes and carries no collection number`() {
        val decoded =
            json.decodeFromString<RosterFeeRowDto>(
                """
                {
                  "enrollment_id": "e-1",
                  "display_name": "Rahim",
                  "outstanding": "1500.00",
                  "current_period": "2027-02",
                  "current_status": "unpaid",
                  "due_date": "2027-02-28"
                }
                """.trimIndent(),
            )

        assertEquals(Money.of("1500.00"), decoded.outstanding)
        // [BR6.4, NFR14.33] The teacher's payment destination reaches
        // exactly one response and a listing is not it. Asserted on
        // the TYPE, so adding the field would fail to compile here.
        val fields = RosterFeeRowDto::class.java.declaredFields.map { it.name }
        assertTrue(
            "collectionNumber" !in fields,
            "the roster fee row declares a collection number: $fields",
        )
    }

    @Test
    fun `a roster fee row rejects a JSON number for outstanding`() {
        assertFailsWith<Exception> {
            json.decodeFromString<RosterFeeRowDto>(
                """
                {
                  "enrollment_id": "e-1",
                  "display_name": "Rahim",
                  "outstanding": 1500
                }
                """.trimIndent(),
            )
        }
    }

    // -----------------------------------------------------------------
    // ClaimDto, both money fields and the correction record.
    // -----------------------------------------------------------------

    @Test
    fun `a claim decodes both money fields from strings`() {
        val decoded =
            json.decodeFromString<ClaimDto>(
                """
                {
                  "claim_id": "c-1",
                  "period": "2027-02",
                  "claimed_amount": "1500.00",
                  "approved_amount": "600.00",
                  "status": "approved_partial",
                  "shortfall_disposition": "carried",
                  "channel": "bKash",
                  "submitted_at": "2027-02-10T10:00:00Z",
                  "verified_at": "2027-02-11T09:00:00Z"
                }
                """.trimIndent(),
            )

        assertEquals(Money.of("1500.00"), decoded.claimedAmount)
        assertEquals(Money.of("600.00"), decoded.approvedAmount)
        assertEquals("carried", decoded.shortfallDisposition)
    }

    @Test
    fun `a claim rejects a JSON number for the approved amount`() {
        assertFailsWith<Exception> {
            json.decodeFromString<ClaimDto>(
                """
                {
                  "claim_id": "c-1",
                  "period": "2027-02",
                  "claimed_amount": "1500.00",
                  "approved_amount": 600,
                  "status": "approved_partial",
                  "channel": "bKash",
                  "submitted_at": "2027-02-10T10:00:00Z"
                }
                """.trimIndent(),
            )
        }
    }

    @Test
    fun `a pending claim decodes with no approved amount`() {
        val decoded =
            json.decodeFromString<ClaimDto>(
                """
                {
                  "claim_id": "c-1",
                  "period": "2027-02",
                  "claimed_amount": "1500.00",
                  "status": "pending",
                  "channel": "cash",
                  "submitted_at": "2027-02-10T10:00:00Z"
                }
                """.trimIndent(),
            )

        assertNull(decoded.approvedAmount)
        assertNull(decoded.verifiedAt)
        assertNull(decoded.previousDecision)
    }

    @Test
    fun `the previous decision carries its amount as a string too`() {
        // [BR6.2] A money value inside the retained decision crosses
        // the wire under the same rule as every other, which is why
        // the map is typed to strings rather than to Any.
        val decoded =
            json.decodeFromString<ClaimDto>(
                """
                {
                  "claim_id": "c-1",
                  "period": "2027-02",
                  "claimed_amount": "1500.00",
                  "approved_amount": "600.00",
                  "status": "approved_partial",
                  "channel": "bKash",
                  "submitted_at": "2027-02-10T10:00:00Z",
                  "previous_decision": {
                    "status": "approved_full",
                    "approved_amount": "1000.00",
                    "shortfall_disposition": null
                  }
                }
                """.trimIndent(),
            )

        val previous = decoded.previousDecision
        assertEquals("approved_full", previous?.get("status"))
        assertEquals("1000.00", previous?.get("approved_amount"))
    }

    // -----------------------------------------------------------------
    // The payment destination.
    // -----------------------------------------------------------------

    @Test
    fun `a payment destination decodes its server-supplied channels`() {
        val decoded =
            json.decodeFromString<PaymentDestinationDto>(
                """
                {
                  "collection_number": "01711000000",
                  "collection_channel": "bKash",
                  "channels": ["bKash", "Nagad", "Rocket", "cash"]
                }
                """.trimIndent(),
            )

        assertEquals("01711000000", decoded.collectionNumber)
        assertEquals(listOf("bKash", "Nagad", "Rocket", "cash"), decoded.channels)
    }

    @Test
    fun `an unknown channel decodes rather than failing`() {
        // [BR6.5] The set is DATA. A client that failed on an
        // unrecognised channel would make adding one an app release,
        // which is the thing the server-supplied list prevents.
        val decoded =
            json.decodeFromString<PaymentDestinationDto>(
                """
                {
                  "collection_number": "01711000000",
                  "channels": ["Upay"]
                }
                """.trimIndent(),
            )

        assertEquals(listOf("Upay"), decoded.channels)
    }

    // -----------------------------------------------------------------
    // The money-report shapes (M1-M3).
    // -----------------------------------------------------------------

    @Test
    fun `a history line decodes its amount from a string and rejects a number`() {
        val body = """{"amount": "%s", "channel": "Nagad", "paid_on": "2026-10-08", "status": "approved_full"}"""
        val decoded = json.decodeFromString<HistoryLineDto>(body.format("1000.00"))
        assertEquals(Money.of("1000.00"), decoded.amount)
        assertNull(decoded.decisionNote)
        assertFailsWith<Exception> {
            json.decodeFromString<HistoryLineDto>(
                """{"amount": 1000, "channel": "Nagad", "paid_on": "2026-10-08", "status": "approved_full"}""",
            )
        }
    }

    @Test
    fun `a waiting history line carries the children the whole payment covers`() {
        val decoded =
            json.decodeFromString<HistoryLineDto>(
                """{"amount": "2000.00", "channel": "bKash", "paid_on": "2026-10-08", "status": "pending",
                   "covered_names": ["Tania", "Tanvir"]}""",
            )
        assertEquals(Money.of("2000.00"), decoded.amount)
        assertEquals(listOf("Tania", "Tanvir"), decoded.coveredNames)
        assertEquals(listOf("Tania", "Tanvir"), decoded.toHistoryLine().coveredNames)
        val approved =
            json.decodeFromString<HistoryLineDto>(
                """{"amount": "1000.00", "channel": "bKash", "paid_on": "2026-10-08", "status": "approved_full"}""",
            )
        assertEquals(emptyList(), approved.coveredNames)
    }

    @Test
    fun `a fee history decodes month states and defaults to none`() {
        val decoded =
            json.decodeFromString<FeeHistoryDto>(
                """
                {"cycles": [], "total_outstanding": "0.00",
                 "month_states": [{"period": "2026-10", "state": "paid"}]}
                """.trimIndent(),
            )
        assertEquals("paid", decoded.monthStates.single().state)
        assertTrue(json.decodeFromString<FeeHistoryDto>("""{"total_outstanding": "0.00"}""").monthStates.isEmpty())
    }

    @Test
    fun `a batch month decodes both totals from strings and rejects numbers`() {
        val body =
            """
            {"period": "2026-10", "collected": %s, "charged": "12000.00",
             "counts": {"paid": 9, "checking": 1, "owed": 2}, "seats": []}
            """.trimIndent()
        val decoded = json.decodeFromString<BatchFeesDto>(body.format("\"9000.00\""))
        assertEquals(Money.of("9000.00"), decoded.collected)
        assertEquals(2, decoded.counts.owed)
        assertFailsWith<Exception> { json.decodeFromString<BatchFeesDto>(body.format("9000")) }
    }

    @Test
    fun `a collections report decodes money from strings and rejects numbers`() {
        val body =
            """
            {"months": [{"period": "2026-11", "charged": "%s", "collected": "0.00",
                         "in_progress": true, "charged_bar": 40, "collected_bar": 0}],
             "outstanding": "9500.00", "owing_students": 11}
            """.trimIndent()
        val decoded = json.decodeFromString<CollectionsDto>(body.format("5000.00"))
        assertEquals(40, decoded.months.single().chargedBar)
        assertTrue(decoded.months.single().inProgress)
        assertEquals(Money.of("9500.00"), decoded.outstanding)
        assertFailsWith<Exception> {
            json.decodeFromString<CollectionsDto>(body.replace("\"%s\"", "5000").replace("\"9500.00\"", "9500"))
        }
    }

    // -----------------------------------------------------------------
    // SeatExtraFeesDto: a seat's exam and other fees.
    // -----------------------------------------------------------------

    private val seatExtra =
        """
        {"fees": [{
          "extra_fee_id": "f-1", "label": "Half-yearly exam", "purpose": "exam",
          "due_on": "2026-11-20", "charged": "500.00", "paid": "200.00",
          "owed": "300.00", "status": "partly_paid"
        }]}
        """.trimIndent()

    @Test
    fun `a seat's extra fees decode money from JSON strings`() {
        val fee = json.decodeFromString<SeatExtraFeesDto>(seatExtra).fees.single()
        assertEquals(Money.of("500.00"), fee.charged)
        assertEquals(Money.of("200.00"), fee.paid)
        assertEquals(Money.of("300.00"), fee.owed)
        assertEquals("partly_paid", fee.status)
    }

    @Test
    fun `a seat's extra fee rejects a JSON number for owed`() {
        assertFailsWith<Exception> {
            json.decodeFromString<SeatExtraFeesDto>(seatExtra.replace("\"owed\": \"300.00\"", "\"owed\": 300"))
        }
    }

    @Test
    fun `what is owed together carries the fees a payment could be for`() {
        val decoded =
            json.decodeFromString<OwedTogetherDto>(
                """
                {"owed_together": "1000.00", "children": [],
                 "extra_fee_options": [{"extra_fee_id": "f-1", "label": "Exam", "purpose": "exam", "due_on": "2026-11-20"}]}
                """.trimIndent(),
            )
        assertEquals(listOf("f-1"), decoded.extraFeeOptions.map { it.extraFeeId })
        assertEquals(Money.of("1000.00"), decoded.owedTogether)
    }

}
