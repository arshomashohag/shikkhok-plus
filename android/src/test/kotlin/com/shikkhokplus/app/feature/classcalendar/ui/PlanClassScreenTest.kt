package com.shikkhokplus.app.feature.classcalendar.ui

import com.shikkhokplus.app.feature.classcalendar.PlanClassUiState
import com.shikkhokplus.app.feature.classcalendar.calendarClass
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.assertTextEquals
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.attendance.ui.TAG_CONFLICT_DISCARD
import com.shikkhokplus.app.feature.attendance.ui.TAG_CONFLICT_REAPPLY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The plan screen and its class-started conflict view. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PlanClassScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun state(conflict: String? = null) =
        PlanClassUiState(calendarClass(plannable = true), "Friction", "", topicVersion = 3, conflictItemId = conflict)

    private fun render(state: PlanClassUiState, covered: () -> Unit = {}, discard: () -> Unit = {}) {
        compose.setContent {
            ShikkhokTheme {
                PlanClassScreen(state, {}, {}, {}, {}, covered, discard, {}, {})
            }
        }
    }

    @Test
    fun `an upcoming class shows the plan fields and says attendance opens on the day`() {
        render(state())

        compose.onNodeWithTag(TAG_PLAN_TOPIC).assertExists()
        compose.onNodeWithTag(TAG_CLASS_NOTES).assertExists()
        compose.onNodeWithTag(TAG_PLAN_ATTENDANCE_LATER).assertExists()
        compose.onNodeWithTag(TAG_PLAN_SAVE).assertExists()
    }

    @Test
    fun `on the class's own day attendance opens when the class starts`() {
        render(state().copy(onClassDay = true))

        compose.onNodeWithTag(TAG_PLAN_ATTENDANCE_LATER).assertTextEquals("Opens when the class starts")
    }

    @Test
    fun `before the class's day attendance opens on the day`() {
        render(state())

        compose.onNodeWithTag(TAG_PLAN_ATTENDANCE_LATER).assertTextEquals("Opens on the day of the class")
    }

    @Test
    fun `a refused plan's message shows with the form still open`() {
        render(state().copy(errorKey = "teaching.session.cancelled"))

        compose.onNodeWithTag(TAG_CLASS_ERROR).assertExists()
        compose.onNodeWithTag(TAG_PLAN_SAVE).assertExists()
        compose.onNodeWithTag(counterTag(TAG_PLAN_TOPIC)).assertTextEquals("8 / 2000")
    }

    @Test
    fun `a refused plan offers Save as covered and Discard plan, and each does its own thing`() {
        var covered = 0
        var discarded = 0
        render(state(conflict = "q-1"), { covered++ }, { discarded++ })

        compose.onNodeWithTag(TAG_CONFLICT_REAPPLY).performClick()
        compose.onNodeWithTag(TAG_CONFLICT_DISCARD).performClick()

        assertEquals(1, covered)
        assertEquals(1, discarded)
    }
}
