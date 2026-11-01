package com.shikkhokplus.app.feature.classcalendar.ui

import com.shikkhokplus.app.feature.classcalendar.ClassDayUiState
import com.shikkhokplus.app.feature.classcalendar.calendarClass
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.ui.CalendarState
import com.shikkhokplus.app.feature.attendance.AttendanceSeat
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.attendance.ui.TAG_ATTENDANCE_SEAT
import com.shikkhokplus.app.feature.record.SaveResult
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** Today's class: fields, the roster, one Save. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ClassDayScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val marking =
        AttendanceUiState.Marking(
            "s-1",
            "2026-11-11",
            listOf(AttendanceSeat("e-1", "তাসনিম জাহান", true), AttendanceSeat("e-2", "Karim", false)),
            attendanceVersion = 2,
            writable = true,
        )

    private val fields =
        ClassDayUiState(calendarClass(state = CalendarState.TODAY, recordable = true), "Newton", "hw")

    private fun render(state: ClassDayUiState, attendance: AttendanceUiState, onSave: () -> Unit = {}) {
        compose.setContent {
            ShikkhokTheme {
                ClassDayScreen(state, attendance, {}, {}, { _, _ -> }, onSave, {}, {}, {})
            }
        }
    }

    @Test
    fun `it shows topics, notes, every seat and Save`() {
        var saved = 0
        render(fields, marking) { saved++ }

        compose.onNodeWithTag(TAG_DAY_TOPIC).assertExists()
        compose.onNodeWithTag(TAG_CLASS_NOTES).assertExists()
        compose.onAllNodesWithTag(TAG_ATTENDANCE_SEAT).assertCountEquals(2)
        compose.onNodeWithTag(TAG_DAY_SAVE).performScrollTo().performClick()
        assertEquals(1, saved)
    }

    @Test
    fun `after a save the outcome and Done replace the Save button`() {
        val saved = fields.copy(result = SaveResult.QUEUED)
        render(saved, AttendanceUiState.Queued("q", "2026-11-11"))

        compose.onNodeWithTag(TAG_CLASS_RESULT).assertExists()
        compose.onNodeWithTag(TAG_DAY_ATTENDANCE_RESULT).assertExists()
        compose.onNodeWithTag(TAG_CLASS_DONE).assertExists()
        compose.onAllNodesWithTag(TAG_DAY_SAVE).assertCountEquals(0)
    }
}
