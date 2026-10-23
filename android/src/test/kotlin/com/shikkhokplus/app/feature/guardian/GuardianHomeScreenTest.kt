package com.shikkhokplus.app.feature.guardian

import androidx.activity.ComponentActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.feature.guardian.ui.GuardianHomeScreen
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_CHIP
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_EMPTY
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_SELECTED
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_SELECTED_NAME
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_SWITCHER
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * `G1` guardian home, rendered.
 *
 * **The Back-after-switch test is the one that must not become a review
 * note** [NFR23.6, NFR14.30, BR4.2, AC9.4.2]. No server-side control
 * can observe the failure it catches: both requests are legitimately
 * authorized, the lens is correct in both, and neither response is
 * anomalous. A guardian switching child moves between two scopes of the
 * SAME lens, so nothing on the server would ever see a problem. This
 * rendering test is the only mechanism there is.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class GuardianHomeScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val rahim =
        GuardianChild("e-1", "Rahim", "Physics", "Karim Sir")

    private val karima =
        GuardianChild("e-2", "Karima", "Chemistry", "Nasrin Miss")

    @Test
    fun `one child draws no switcher`() {
        // A control offering a single option is noise, and the
        // single-child case is the common one.
        compose.setContent {
            GuardianHomeScreen(
                state = GuardianUiState.OneChild(rahim),
                onSelectChild = {},
                onRetry = {},
            )
        }

        compose.onNodeWithText("Rahim").assertIsDisplayed()
        assertEquals(
            0,
            compose.onAllNodesWithTag(TAG_GUARDIAN_SWITCHER)
                .fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `several children draw the switcher and the selected child`() {
        compose.setContent {
            GuardianHomeScreen(
                state = GuardianUiState.SeveralChildren(
                    listOf(rahim, karima),
                    selected = rahim,
                ),
                onSelectChild = {},
                onRetry = {},
            )
        }

        compose.onNode(hasTestTag(TAG_GUARDIAN_SWITCHER)).assertIsDisplayed()
        compose.onNode(hasTestTag(TAG_GUARDIAN_SELECTED)).assertIsDisplayed()
    }

    @Test
    fun `a guardian reaching nothing is told so rather than shown a blank`() {
        compose.setContent {
            GuardianHomeScreen(
                state = GuardianUiState.Empty,
                onSelectChild = {},
                onRetry = {},
            )
        }

        compose.onNode(hasTestTag(TAG_GUARDIAN_EMPTY)).assertIsDisplayed()
    }

    @Test
    fun `BACK AFTER A CHILD SWITCH does not reach the previous child`() {
        // ===========================================================
        // [NFR23.6, NFR14.30, BR4.2, AC9.4.2]. **The obligation with no
        // other verifier.**
        //
        // The failure this catches: a switcher implemented as a
        // navigation push leaves the previous child's screen on the
        // back stack, so Back lands in another scope of the same lens.
        // That is a privacy failure wearing navigation's clothes, and
        // nothing server-side can see it.
        //
        // The assertion is in two halves, and both are needed:
        //
        //  1. after switching, the previous child is NOT on screen --
        //     the switch replaced rather than stacked;
        //  2. after pressing Back, the previous child is STILL not on
        //     screen -- there was no destination to pop back to.
        //
        // Half 2 alone would pass against a screen that never switched
        // at all. Half 1 alone would pass against a push, because the
        // pushed screen covers the old one until Back is pressed.
        // ===========================================================
        var state by mutableStateOf<GuardianUiState>(
            GuardianUiState.SeveralChildren(listOf(rahim, karima), selected = rahim),
        )

        compose.setContent {
            GuardianHomeScreen(
                state = state,
                onSelectChild = { child ->
                    val current = state
                    if (current is GuardianUiState.SeveralChildren) {
                        state = GuardianStateMapper.afterChildSelected(current, child)
                    }
                },
                onRetry = {},
            )
        }

        // Read through the tag, not by text: "Rahim" is on screen TWICE
        // — once as the displayed child and once as his own switcher
        // chip. A bare text query is ambiguous here, and that ambiguity
        // is the whole reason the name carries its own tag.
        assertEquals("Rahim", selectedChildName())

        compose.onAllNodesWithTag(TAG_GUARDIAN_CHIP)[1].performClick()
        compose.waitForIdle()

        // Half 1: the switch REPLACED. Karima is shown as the selected
        // child; Rahim appears only as his own chip in the switcher,
        // never as the child being displayed.
        assertEquals("Karima", selectedChildName())

        // Half 2: Back reaches nothing. There is no back stack to pop,
        // because a selection pushed no destination -- so the activity
        // handles the press itself and the screen is unchanged.
        compose.activityRule.scenario.onActivity { activity ->
            activity.onBackPressedDispatcher.onBackPressed()
        }
        compose.waitForIdle()

        assertEquals("Karima", selectedChildName())
    }

    /**
     * The name inside the selected-child block, not the switcher.
     *
     * Read through `TAG_GUARDIAN_SELECTED_NAME` deliberately: both
     * children's names are on screen at once because both have a chip,
     * so a bare `onNodeWithText("Rahim")` would find the chip and
     * report the previous child as displayed when it is not. That would
     * make this test fail for the wrong reason, and — worse — a
     * differently-written version of it could PASS for the wrong reason.
     *
     * @return The displayed child's name
     */
    private fun selectedChildName(): String {
        val node =
            compose.onNode(hasTestTag(TAG_GUARDIAN_SELECTED_NAME))
                .fetchSemanticsNode()
        return node.config[SemanticsProperties.Text].first().text
    }
}
