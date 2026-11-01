package com.shikkhokplus.app.feature.classcalendar.ui

import com.shikkhokplus.app.feature.classcalendar.ClassDayUiState
import com.shikkhokplus.app.feature.classcalendar.calendarClass
import androidx.compose.ui.test.assertAll
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.performTextReplacement
import com.shikkhokplus.app.core.network.SubjectOptionDto
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
                ClassDayScreen(state, attendance, {}, {}, {}, { _, _ -> }, onSave, {}, {}, {}, {}, {})
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
    fun `topics and notes show a counter and never pass more than 2000 characters on`() {
        var typed = ""
        compose.setContent {
            ShikkhokTheme {
                ClassDayScreen(fields, marking, { typed = it }, {}, {}, { _, _ -> }, {}, {}, {}, {}, {}, {})
            }
        }

        compose.onNodeWithTag(counterTag(TAG_DAY_TOPIC)).assertTextEquals("6 / 2000")
        compose.onNodeWithTag(counterTag(TAG_CLASS_NOTES)).assertTextEquals("2 / 2000")
        compose.onNodeWithTag(TAG_DAY_TOPIC).performTextReplacement("x".repeat(2100))
        assertEquals(2000, typed.length)
    }

    @Test
    fun `a refused topic shows its message and keeps Save, even when the roster could not load`() {
        var saved = 0
        val refused = fields.copy(errorKey = "teaching.session.cancelled")
        render(refused, AttendanceUiState.Failed("error.network.unreachable", retryable = true)) { saved++ }

        compose.onNodeWithTag(TAG_CLASS_ERROR).assertExists()
        compose.onNodeWithTag(TAG_DAY_TOPIC).assertIsEnabled()
        compose.onNodeWithTag(TAG_DAY_SAVE).performScrollTo().assertIsEnabled().performClick()
        assertEquals(1, saved)
    }

    @Test
    fun `Save waits for the roster's first read`() {
        render(fields, AttendanceUiState.Loading)

        compose.onNodeWithTag(TAG_DAY_SAVE).assertIsNotEnabled()
    }

    @Test
    fun `the batch's subjects are offered and a choice is passed on`() {
        var chosen: String? = null
        val withSubjects =
            fields.copy(
                subjects = listOf(SubjectOptionDto("sub-1", "Physics"), SubjectOptionDto("sub-2", "Maths")),
                subjectId = "sub-1",
            )
        compose.setContent {
            ShikkhokTheme {
                ClassDayScreen(withSubjects, marking, {}, {}, { chosen = it }, { _, _ -> }, {}, {}, {}, {}, {}, {})
            }
        }

        compose.onAllNodesWithTag(TAG_CLASS_SUBJECT).assertCountEquals(2)
        compose.onAllNodesWithTag(TAG_CLASS_SUBJECT)[1].performClick()
        assertEquals("sub-2", chosen)
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

    @Test
    fun `a refused plan shows the started choice, and after Save as covered attendance is editable`() {
        var state by androidx.compose.runtime.mutableStateOf(fields.copy(conflictItemId = "q-1"))
        compose.setContent {
            ShikkhokTheme {
                ClassDayScreen(
                    state, marking, {}, {}, {}, { _, _ -> },
                    {}, { state = state.copy(conflictItemId = null, notice = SaveResult.QUEUED) }, {}, {}, {}, {},
                )
            }
        }
        compose.onNodeWithTag(com.shikkhokplus.app.feature.attendance.ui.TAG_CONFLICT_DISCARD).assertExists()
        compose.onAllNodesWithTag(TAG_DAY_TOPIC).assertCountEquals(0)

        compose.onNodeWithTag(com.shikkhokplus.app.feature.attendance.ui.TAG_CONFLICT_REAPPLY)
            .performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.OnClick)
        compose.waitForIdle()

        compose.onNodeWithTag(TAG_CLASS_NOTICE).assertExists()
        compose.onAllNodesWithTag(com.shikkhokplus.app.feature.attendance.ui.TAG_ATTENDANCE_TOGGLE)
            .assertAll(androidx.compose.ui.test.isEnabled())
    }
}
