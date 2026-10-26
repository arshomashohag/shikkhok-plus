package com.shikkhokplus.app.core.designsystem

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsNotSelected
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.graphics.painter.ColorPainter
import androidx.compose.ui.graphics.Color
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The bottom navigation bar.
 *
 * **Reported missing from a device**: there was no way to move between
 * the teacher's screens at all, because every destination was reachable
 * only by pushing onto a stack and coming back.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class BottomNavTest {

    @get:Rule
    val compose = createComposeRule()

    private fun tab(
        label: String,
        tag: String,
        enabled: Boolean = true,
    ) = NavDestination(
        label = label,
        icon = ColorPainter(Color.Black),
        tag = tag,
        enabled = enabled,
    )

    private fun render(
        selectedIndex: Int = 0,
        onSelect: (Int) -> Unit = {},
        duesEnabled: Boolean = false,
    ) {
        compose.setContent {
            ShikkhokTheme {
                BottomNav(
                    destinations =
                        listOf(
                            tab("Today", "t_today", enabled = false),
                            tab("Batches", "t_batches"),
                            tab("Dues", "t_dues", enabled = duesEnabled),
                            tab("More", "t_more", enabled = false),
                        ),
                    selectedIndex = selectedIndex,
                    onSelect = onSelect,
                )
            }
        }
    }

    @Test
    fun `all four destinations are shown`() {
        // The bar keeps its shape as units land. A tab that appeared
        // only once its screen worked would change the bar under a
        // person who had already learned where things are.
        render()

        compose.onNodeWithTag(TAG_BOTTOM_NAV).assertIsDisplayed()
        listOf("t_today", "t_batches", "t_dues", "t_more").forEach {
            compose.onNodeWithTag(it).assertIsDisplayed()
        }
    }

    @Test
    fun `an enabled tab reports the index it was given`() {
        var chosen = -1
        render(selectedIndex = 1, onSelect = { chosen = it })

        compose.onNodeWithTag("t_batches").performClick()

        assertEquals(1, chosen)
    }

    @Test
    fun `a disabled tab does not navigate`() {
        // **The honest half of showing four tabs.** Today, Dues and
        // More have no repository and no ViewModel yet, so opening one
        // would show a screen that cannot load.
        var chosen = -1
        render(onSelect = { chosen = it })

        compose.onNodeWithTag("t_dues").performClick()

        assertEquals(-1, chosen, "a disabled tab must not navigate")
    }

    @Test
    fun `a tab becomes usable when its screen is ready`() {
        // The same tab, enabled: no other change should be needed when
        // the Dues repository lands.
        var chosen = -1
        render(onSelect = { chosen = it }, duesEnabled = true)

        compose.onNodeWithTag("t_dues").performClick()

        assertEquals(2, chosen)
    }

    @Test
    fun `the selected index highlights the tab it names`() {
        // **An off-by-one here is silent.** The route passes a constant
        // for the current tab; if it indexed the wrong one the bar
        // would highlight a destination the person is not on, and
        // nothing would fail. Asserted by selection state rather than
        // by colour, which is what TalkBack reads too.
        render(selectedIndex = 1)

        compose.onNodeWithTag("t_batches").assertIsSelected()
        compose.onNodeWithTag("t_today").assertIsNotSelected()
        compose.onNodeWithTag("t_dues").assertIsNotSelected()
        compose.onNodeWithTag("t_more").assertIsNotSelected()
    }

    @Test
    fun `a disabled tab is announced as disabled, not merely inert`() {
        // Silently ignoring a tap looks like a broken app. The
        // semantics must say the control is unavailable so TalkBack
        // announces it and the label's reduced emphasis is not the
        // only signal.
        render()

        compose.onNodeWithTag("t_dues").assertIsNotEnabled()
        compose.onNodeWithTag("t_batches").assertIsEnabled()
    }
}
