package com.shikkhokplus.app.core.designsystem

import androidx.activity.ComponentActivity
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.unit.dp
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * [StateFade] fades between kinds of state, and only between kinds.
 *
 * The clock is held still so the test can look mid-transition: a fade
 * shows both the leaving and the arriving content for a moment; a swap
 * within one kind shows only the new content, immediately.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class StateFadeTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private sealed interface Shown {
        data object Loading : Shown

        data class Loaded(val label: String) : Shown
    }

    private fun render(first: Shown): (Shown) -> Unit {
        var state by mutableStateOf(first)
        compose.setContent {
            StateFade(state, spacing = 8.dp) { shown ->
                when (shown) {
                    Shown.Loading -> Text("loading")
                    is Shown.Loaded -> Text(shown.label)
                }
            }
        }
        compose.waitForIdle()
        return { state = it }
    }

    @Test
    fun `loading to loaded is a fade, so both are on screen mid-way`() {
        val set = render(Shown.Loading)
        compose.mainClock.autoAdvance = false

        set(Shown.Loaded("rows"))
        compose.mainClock.advanceTimeByFrame()
        compose.mainClock.advanceTimeBy(Motion.EXIT_MS / 2L)

        compose.onNodeWithText("loading").assertExists()
        compose.onNodeWithText("rows").assertExists()

        compose.mainClock.advanceTimeBy(Motion.ENTER_MS * 2L)
        compose.onNodeWithText("loading").assertDoesNotExist()
    }

    @Test
    fun `new content of the same kind replaces the old without a fade`() {
        val set = render(Shown.Loaded("old rows"))
        compose.mainClock.autoAdvance = false

        set(Shown.Loaded("new rows"))
        compose.mainClock.advanceTimeByFrame()

        compose.onNodeWithText("new rows").assertExists()
        compose.onNodeWithText("old rows").assertDoesNotExist()
    }
}
