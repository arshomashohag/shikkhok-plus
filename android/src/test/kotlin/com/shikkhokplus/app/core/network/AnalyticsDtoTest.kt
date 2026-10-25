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
        val decoded = json.decodeFromString<DuesResponseDto>("""{"rows": []}""")

        assertEquals(emptyList(), decoded.rows)
    }

    @Test
    fun `the earnings figure decodes from a JSON string`() {
        val decoded =
            json.decodeFromString<MonthlyEarningsDto>(
                """{"period": "2027-06", "received": "4500.00"}""",
            )

        assertEquals(Money.of("4500.00"), decoded.received)
    }

    @Test
    fun `the earnings figure REFUSES a JSON number`() {
        assertFailsWith<Exception> {
            json.decodeFromString<MonthlyEarningsDto>(
                """{"period": "2027-06", "received": 4500.00}""",
            )
        }
    }

    @Test
    fun `a zero month decodes as a value rather than as an absence`() {
        val decoded =
            json.decodeFromString<MonthlyEarningsDto>(
                """{"period": "2027-06", "received": "0.00"}""",
            )

        assertEquals(Money.of("0.00"), decoded.received)
    }

    @Test
    fun `an overview without a trend decodes it as null, not an empty list`() {
        // The wire distinction this whole feature rests on: an absent
        // `trend` key means under two months of history. Decoding it
        // as an empty list would lose the difference before the mapper
        // ever sees it.
        val decoded =
            json.decodeFromString<OverviewDto>(
                """{"earnings": {"period": "2027-06", "received": "0.00"}}""",
            )

        assertNull(decoded.trend)
        assertNull(decoded.nextExam)
    }

    @Test
    fun `an overview with a trend decodes every point`() {
        val decoded =
            json.decodeFromString<OverviewDto>(
                """
                {
                  "earnings": {"period": "2027-06", "received": "4500.00"},
                  "trend": [
                    {"period": "2027-05", "received": "3000.00"},
                    {"period": "2027-06", "received": "4500.00"}
                  ],
                  "next_exam": {
                    "exam_id": "exam-1",
                    "title": "Mid-term",
                    "batch_name": "Physics",
                    "subject_name": "Mechanics",
                    "date": "2027-06-20",
                    "days_remaining": 5
                  }
                }
                """,
            )

        assertEquals(2, decoded.trend?.size)
        assertEquals(Money.of("3000.00"), decoded.trend?.get(0)?.received)
        assertEquals(5, decoded.nextExam?.daysRemaining)
    }

    @Test
    fun `an unknown field on a D5 response does not break the parse`() {
        // The client handles unknown fields rather than failing to
        // parse, because /v1/ endpoints stay additive and an installed
        // app cannot be forced to update [D-26].
        val decoded =
            json.decodeFromString<MonthlyEarningsDto>(
                """
                {
                  "period": "2027-06",
                  "received": "4500.00",
                  "collection_rate": "0.82"
                }
                """,
            )

        assertEquals(Money.of("4500.00"), decoded.received)
    }
}
