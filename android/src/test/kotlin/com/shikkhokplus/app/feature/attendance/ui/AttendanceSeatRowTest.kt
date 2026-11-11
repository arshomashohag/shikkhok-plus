package com.shikkhokplus.app.feature.attendance.ui

import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isToggleable
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.attendance.AttendanceSeat
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * TalkBack hears the student's name with the switch [UX-2]: the node that
 * toggles is the one that carries the name, the Switch role and a
 * Present/Absent state, on both attendance screens.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class AttendanceSeatRowTest {

    @get:Rule
    val compose = createComposeRule()

    private val name = "মোহাম্মদ আব্দুল্লাহ আল মামুন"

    private fun hasRole(role: Role) = SemanticsMatcher.expectValue(SemanticsProperties.Role, role)

    private fun hasStateDescription(text: String) =
        SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, text)

    private fun seatNode() = compose.onNode(hasText(name) and isToggleable() and hasRole(Role.Switch))

    @Test
    fun `the toggleable node is named by the student and says Present or Absent`() {
        val toggles = mutableListOf<Boolean>()
        compose.setContent {
            ShikkhokTheme {
                var present by remember { mutableStateOf(true) }
                AttendanceSeatRow(AttendanceSeat("e-1", name, present), enabled = true, showWord = true) { _, now ->
                    toggles += now
                    present = now
                }
            }
        }

        // Exactly one toggleable node, and it is the one holding the name.
        seatNode().assertIsOn().assert(hasStateDescription("Present"))
        // The visible word is not read twice.
        assertEquals(listOf(name), seatNode().fetchSemanticsNode().config[SemanticsProperties.Text].map { it.text })

        seatNode().performClick()
        seatNode().assertIsOff().assert(hasStateDescription("Absent"))
        assertEquals(listOf(false), toggles)
    }

    @Test
    fun `a seat the server will not let change is a disabled switch, still named`() {
        compose.setContent {
            ShikkhokTheme {
                AttendanceSeatRow(AttendanceSeat("e-1", name, false), enabled = false, showWord = false) { _, _ -> }
            }
        }
        seatNode().assertIsOff().assertIsNotEnabled()
    }

    @Test
    fun `the attendance screen's seats are named switches`() {
        var toggled: Pair<String, Boolean>? = null
        compose.setContent {
            ShikkhokTheme {
                AttendanceScreen(
                    AttendanceUiState.Marking(
                        "s-1",
                        "2026-11-11",
                        listOf(AttendanceSeat("e-1", name, true)),
                        attendanceVersion = 2,
                        writable = true,
                    ),
                    onToggle = { seat, now -> toggled = seat.enrollmentId to now },
                    onSubmit = {},
                    onRetry = {},
                )
            }
        }
        seatNode().assertIsOn()
        compose.onNodeWithTag(TAG_ATTENDANCE_TOGGLE).performClick()
        assertEquals("e-1" to false, toggled)
    }
}
