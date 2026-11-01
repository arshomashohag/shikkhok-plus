package com.shikkhokplus.app.feature.classcalendar.ui

import com.shikkhokplus.app.feature.classcalendar.ClassCalendarUiState
import com.shikkhokplus.app.feature.classcalendar.calendarClass
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.ui.CalendarDayUi
import com.shikkhokplus.app.core.ui.CalendarState
import com.shikkhokplus.app.core.ui.MonthViewUi
import com.shikkhokplus.app.feature.batchdetail.ui.ClassesTab
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The Classes tab is the month calendar; a tapped day is passed up untouched. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ClassesTabCalendarTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `tapping a day hands that day up`() {
        val day = CalendarDayUi("2026-11-16", CalendarState.UPCOMING, listOf(calendarClass(plannable = true)))
        val view = MonthViewUi(YearMonth(2026, 11), YearMonth(2026, 9), YearMonth(2026, 12), listOf(day))
        var tapped: CalendarDayUi? = null

        compose.setContent {
            ShikkhokTheme {
                ClassesTab(ClassCalendarUiState.Loaded(view), null, {}, { tapped = it }, {})
            }
        }
        compose.onNodeWithTag("calendar_day_upcoming_2026-11-16").performClick()

        assertEquals(day, tapped)
    }
}
