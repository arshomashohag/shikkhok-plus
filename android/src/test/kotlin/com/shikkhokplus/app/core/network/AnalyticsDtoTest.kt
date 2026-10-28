package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlinx.serialization.json.Json

/**
 * D5's money-carrying models decode from a JSON **string** and fail
 * loudly on a JSON **number**.
 *
 * **The loud failure is the obligation, not the happy path.** A lenient
 * decoder that quietly accepts a number and converts it is the actual
 * failure mode, and it passes a happy-path-only test on both sides
 * while the value is already a float [TC-7, D-20].
 */
class AnalyticsDtoTest {

    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun `a dues row decodes its outstanding from a JSON string`() {
        val decoded =
            json.decodeFromString<DuesRowDto>(
                """
                {
                  "enrollment_id": "seat-1",
                  "batch_id": "batch-1",
                  "batch_name": "Physics",
                  "display_name": "Rahim",
                  "outstanding": "1500.00",
                  "oldest_unpaid_period": "2027-01"
                }
                """,
            )

        assertEquals(Money.of("1500.00"), decoded.outstanding)
        assertEquals("2027-01", decoded.oldestUnpaidPeriod)
    }

    @Test
    fun `a dues row REFUSES an outstanding sent as a JSON number`() {
        assertFailsWith<Exception> {
            json.decodeFromString<DuesRowDto>(
                """
                {
                  "enrollment_id": "seat-1",
                  "batch_id": "batch-1",
                  "batch_name": "Physics",
                  "display_name": "Rahim",
                  "outstanding": 1500.00
                }
                """,
            )
        }
    }

    @Test
    fun `an absent oldest unpaid period decodes as null`() {
        val decoded =
            json.decodeFromString<DuesRowDto>(
                """
                {
                  "enrollment_id": "seat-1",
                  "batch_id": "batch-1",
                  "batch_name": "Physics",
                  "display_name": "Rahim",
                  "outstanding": "1500.00"
                }
                """,
            )

        assertNull(decoded.oldestUnpaidPeriod)
    }

    @Test
    fun `an empty dues response decodes to an empty list, not a failure`() {
        val decoded =
            json.decodeFromString<DuesResponseDto>(
                """{"summary":{"total":"0.00","count":0,"late_total":"0.00",
                "remindable":0,"groups":[]},"rows": []}""",
            )

        assertEquals(emptyList(), decoded.rows)
    }

    @Test
    fun `an unknown field on a D5 response does not break the parse`() {
        // The client handles unknown fields rather than failing to
        // parse, because /v1/ endpoints stay additive and an installed
        // app cannot be forced to update [D-26].
        val decoded =
            json.decodeFromString<OutstandingDto>(
                """
                {
                  "total": "4500.00",
                  "overdue": "1200.00",
                  "overdue_students": 1,
                  "batch_count": 2,
                  "collection_rate": "0.82"
                }
                """,
            )

        assertEquals(Money.of("4500.00"), decoded.total)
    }

    @Test
    fun `today's owed figures decode from JSON strings`() {
        val decoded =
            json.decodeFromString<OutstandingDto>(
                """{"total":"48600.00","overdue":"31200.00","overdue_students":12,"batch_count":7}""",
            )

        assertEquals(Money.of("48600.00"), decoded.total)
        assertEquals(Money.of("31200.00"), decoded.overdue)
    }

    @Test
    fun `today's owed figures REFUSE a JSON number`() {
        assertFailsWith<Exception> {
            json.decodeFromString<OutstandingDto>(
                """{"total":48600.00,"overdue":"0.00","overdue_students":0,"batch_count":0}""",
            )
        }
    }

    @Test
    fun `a payment to check REFUSES its amounts as JSON numbers`() {
        assertFailsWith<Exception> {
            json.decodeFromString<ClaimQueueItemDto>(
                """
                {"claim_id":"c","enrollment_id":"e","display_name":"A","batch_name":"B",
                 "period":"2026-10","claimed_amount":800,"charged":"1200.00",
                 "comparison":"short","difference":"400.00","channel":"bKash",
                 "submitted_at":"2026-10-28T10:00:00Z"}
                """,
            )
        }
    }
}
