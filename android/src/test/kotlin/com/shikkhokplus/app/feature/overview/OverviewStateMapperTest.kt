package com.shikkhokplus.app.feature.overview

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MonthlyEarningsDto
import com.shikkhokplus.app.core.network.NextExamDto
import com.shikkhokplus.app.core.network.OverviewDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The overview mapper's state machine, and the three absences.
 *
 * **The absences are the point of this file.** `earnings` is never
 * absent, `trend` is null under two months, and `next_exam` is null
 * when nothing is scheduled — three different things, and collapsing
 * any pair of them is the defect.
 */
class OverviewStateMapperTest {

    private fun month(period: String, received: String): MonthlyEarningsDto =
        MonthlyEarningsDto(period = period, received = Money.of(received))

    private val exam =
        NextExamDto(
            examId = "exam-1",
            title = "Mid-term",
            batchName = "Physics",
            subjectName = "Mechanics",
            date = "2027-06-20",
            daysRemaining = 5,
        )

    @Test
    fun `all three blocks map when all three are present`() {
        val state =
            OverviewStateMapper.afterLoad(
                OverviewDto(
                    earnings = month("2027-06", "4500.00"),
                    trend = listOf(month("2027-05", "3000.00"), month("2027-06", "4500.00")),
                    nextExam = exam,
                ),
            )

        val loaded = assertIs<OverviewUiState.Loaded>(state)
        assertEquals(Money.of("4500.00"), loaded.thisMonth.received)
        assertEquals(2, assertNotNull(loaded.trend).size)
        assertEquals("Mid-term", assertNotNull(loaded.nextExam).title)
    }

    @Test
    fun `a zero month is a VALUE and never an absence`() {
        // Rendering zero as "no data" tells a teacher their records are
        // missing when they are complete, in the month they most need
        // to know the number is really zero.
        val loaded =
            assertIs<OverviewUiState.Loaded>(
                OverviewStateMapper.afterLoad(
                    OverviewDto(earnings = month("2027-06", "0.00")),
                ),
            )

        assertEquals(Money.of("0.00"), loaded.thisMonth.received)
        assertEquals("2027-06", loaded.thisMonth.period)
    }

    @Test
    fun `an absent trend stays null and never becomes an empty list`() {
        // **The assertion that catches `trend ?: emptyList()`.** Null
        // means under two months of history; an empty list would mean
        // the server had two months that both earned nothing. The
        // screen omits the block for one and draws an empty frame for
        // the other, so collapsing them is visible to a teacher.
        val loaded =
            assertIs<OverviewUiState.Loaded>(
                OverviewStateMapper.afterLoad(
                    OverviewDto(earnings = month("2027-06", "500.00"), trend = null),
                ),
            )

        assertNull(loaded.trend)
    }

    @Test
    fun `an absent exam stays null rather than becoming a placeholder`() {
        val loaded =
            assertIs<OverviewUiState.Loaded>(
                OverviewStateMapper.afterLoad(
                    OverviewDto(earnings = month("2027-06", "500.00"), nextExam = null),
                ),
            )

        assertNull(loaded.nextExam)
    }

    @Test
    fun `a zero earnings figure and an absent trend coexist in one state`() {
        // The two absences asserted together, because a test checking
        // each in isolation passes against an implementation that
        // encodes both the same way.
        val loaded =
            assertIs<OverviewUiState.Loaded>(
                OverviewStateMapper.afterLoad(
                    OverviewDto(earnings = month("2027-06", "0.00"), trend = null),
                ),
            )

        assertEquals(Money.of("0.00"), loaded.thisMonth.received)
        assertNull(loaded.trend)
    }

    @Test
    fun `the trend keeps the server's ascending order`() {
        val loaded =
            assertIs<OverviewUiState.Loaded>(
                OverviewStateMapper.afterLoad(
                    OverviewDto(
                        earnings = month("2027-06", "4500.00"),
                        trend =
                            listOf(
                                month("2027-04", "1000.00"),
                                month("2027-05", "3000.00"),
                                month("2027-06", "4500.00"),
                            ),
                    ),
                ),
            )

        assertEquals(
            listOf("2027-04", "2027-05", "2027-06"),
            assertNotNull(loaded.trend).map { it.period },
        )
    }

    @Test
    fun `days remaining is carried from the server and never recomputed`() {
        // A client computing it from the date would use the device
        // clock, which this product rules out for decisions, and would
        // disagree across time zones. The date here is far in the past
        // relative to any plausible "today", so a recomputation would
        // produce a negative number rather than 5.
        val loaded =
            assertIs<OverviewUiState.Loaded>(
                OverviewStateMapper.afterLoad(
                    OverviewDto(
                        earnings = month("2027-06", "0.00"),
                        nextExam = exam.copy(date = "2020-01-01", daysRemaining = 5),
                    ),
                ),
            )

        assertEquals(5, assertNotNull(loaded.nextExam).daysRemaining)
    }

    @Test
    fun `a server error carries its message key and the server's retryable`() {
        val envelope =
            ErrorEnvelope(
                ErrorBody(
                    code = "NO_TEACHER_LENS",
                    retryable = false,
                    messageKey = "authz.lens.not_available",
                ),
            )

        val failed =
            assertIs<OverviewUiState.Failed>(OverviewStateMapper.afterError(envelope))

        assertEquals("authz.lens.not_available", failed.messageKey)
        assertTrue(!failed.retryable)
    }

    @Test
    fun `a transport failure is always retryable`() {
        val failed =
            assertIs<OverviewUiState.Failed>(
                OverviewStateMapper.afterTransportFailure(),
            )

        assertEquals(OverviewStateMapper.OFFLINE_KEY, failed.messageKey)
        assertTrue(failed.retryable)
    }
}
