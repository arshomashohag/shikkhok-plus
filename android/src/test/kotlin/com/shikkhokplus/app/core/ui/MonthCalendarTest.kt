package com.shikkhokplus.app.core.ui

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.format.YearMonth
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The month grid draws the state the server decided and never decides one itself. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MonthCalendarTest {

    @get:Rule
    val compose = createComposeRule()

    private fun klass(date: String, state: CalendarState) =
        CalendarClassUi("s-$date", date, "16:00:00", null, null, state, null, null, false, false, null)

    private fun day(date: String, state: CalendarState, count: Int = 1) =
        CalendarDayUi(date, state, List(count) { klass(date, state) })

    private val days = listOf(
        day("2026-11-02", CalendarState.TAKEN),
        day("2026-11-03", CalendarState.TODAY),
        day("2026-11-04", CalendarState.UPCOMING),
        day("2026-11-05", CalendarState.NOT_RECORDED),
        day("2026-11-06", CalendarState.CANCELLED),
        day("2026-11-09", CalendarState.UPCOMING, count = 2),
    )

    private fun render(
        shown: YearMonth = YearMonth(2026, 11),
        first: YearMonth = YearMonth(2026, 9),
        last: YearMonth = YearMonth(2026, 12),
        onPick: (YearMonth) -> Unit = {},
        onDay: (CalendarDayUi) -> Unit = {},
    ) {
        compose.setContent {
            ShikkhokTheme {
                MonthCalendar(
                    year = shown.year,
                    month = shown.month,
                    days = days,
                    firstMonth = first,
                    lastMonth = last,
                    onPickMonth = onPick,
                    onDay = onDay,
                )
            }
        }
    }

    @Test
    fun `each state renders its own tag`() {
        render()
        compose.onNodeWithTag("calendar_day_taken_2026-11-02").assertExists()
        compose.onNodeWithTag("calendar_day_today_2026-11-03").assertExists()
        compose.onNodeWithTag("calendar_day_upcoming_2026-11-04").assertExists()
        compose.onNodeWithTag("calendar_day_not_recorded_2026-11-05").assertExists()
        compose.onNodeWithTag("calendar_day_cancelled_2026-11-06").assertExists()
    }

    @Test
    fun `a day with two classes shows a count and one class does not`() {
        render()
        compose.onNodeWithTag("calendar_count_2026-11-09", useUnmergedTree = true).assertExists()
        compose.onAllNodesWithTag("calendar_count_2026-11-02", useUnmergedTree = true)
            .assertCountEquals(0)
    }

    @Test
    fun `tapping a day calls onDay with that day`() {
        var tapped: CalendarDayUi? = null
        render(onDay = { tapped = it })
        compose.onNodeWithTag("calendar_day_upcoming_2026-11-04").performClick()
        assertEquals("2026-11-04", tapped?.date)
    }

    @Test
    fun `arrows step a month and are disabled at the ends`() {
        val picked = mutableListOf<YearMonth>()
        render(onPick = { picked += it })
        compose.onNodeWithTag("calendar_prev").assertIsEnabled().performClick()
        compose.onNodeWithTag("calendar_next").assertIsEnabled().performClick()
        assertEquals(listOf(YearMonth(2026, 10), YearMonth(2026, 12)), picked)
    }

    @Test
    fun `previous is disabled at the first month and next at the last`() {
        render(shown = YearMonth(2026, 9))
        compose.onNodeWithTag("calendar_prev").assertIsNotEnabled()
        compose.onNodeWithTag("calendar_next").assertIsEnabled()
    }

    @Test
    fun `next is disabled at the last month`() {
        render(shown = YearMonth(2026, 12))
        compose.onNodeWithTag("calendar_next").assertIsNotEnabled()
    }

    @Test
    fun `the picker offers only months inside the range`() {
        val picked = mutableListOf<YearMonth>()
        render(onPick = { picked += it })
        compose.onNodeWithTag("calendar_header").performClick()
        compose.onNodeWithTag("calendar_picker_month_2026-09").assertExists()
        compose.onNodeWithTag("calendar_picker_month_2026-12").assertExists()
        compose.onAllNodesWithTag("calendar_picker_month_2026-08").assertCountEquals(0)
        compose.onAllNodesWithTag("calendar_picker_month_2026-01").assertCountEquals(0)
        compose.onNodeWithTag("calendar_picker_month_2026-09").performClick()
        assertEquals(listOf(YearMonth(2026, 9)), picked)
        compose.onAllNodesWithTag("calendar_picker_month_2026-09").assertCountEquals(0)
    }
}
