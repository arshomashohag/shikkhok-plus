package com.shikkhokplus.app.feature.classcalendar.ui

import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.ui.CalendarState
import com.shikkhokplus.app.feature.classcalendar.calendarClass
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** A read-only class labels its topics by the server's state, never as covered unless taken. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ClassReadOnlyScreenTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `each state has its heading and its empty wording`() {
        val shown = mutableStateOf(calendarClass())
        compose.setContent { ShikkhokTheme { ClassReadOnlyScreen(shown.value, onBack = {}) } }

        for (state in CalendarState.entries) {
            val taken = state == CalendarState.TAKEN
            shown.value = calendarClass(state = state)
            compose.waitForIdle()
            compose.onNodeWithText(if (taken) "Topics covered" else "Planned topics").assertExists()
            compose.onNodeWithTag(TAG_CLASS_READ_EMPTY)
                .assertTextEquals(if (taken) "No topic logged yet" else "No topics planned yet")
        }
    }

    @Test
    fun `a cancelled class's plan is shown as planned, verbatim`() {
        compose.setContent {
            ShikkhokTheme {
                ClassReadOnlyScreen(calendarClass(state = CalendarState.CANCELLED, topic = "Optics"), onBack = {})
            }
        }

        compose.onNodeWithText("Planned topics").assertExists()
        compose.onNodeWithTag(TAG_CLASS_READ_TOPIC).assertTextEquals("Optics")
    }
}
