package com.shikkhokplus.app.core.session.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.core.session.LensOption
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * What the picker renders, which the mapper tests cannot see.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class LensPickerScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun render(
        options: List<LensOption>,
        onChoose: (Lens) -> Unit = {},
    ) {
        compose.setContent {
            ShikkhokTheme { LensPickerScreen(options = options, onChoose = onChoose) }
        }
    }

    @Test
    fun `one row is rendered per offered lens`() {
        render(listOf(LensOption(Lens.TEACHER, 3), LensOption(Lens.GUARDIAN, 1)))

        compose.onNodeWithTag(TAG_LENS_PICKER).assertIsDisplayed()
        assertEquals(2, compose.onAllNodesWithTag(TAG_LENS_OPTION).fetchSemanticsNodes().size)
    }

    @Test
    fun `tapping a row reports that row's lens`() {
        // Not merely "a tap happened": a picker that reported the
        // first row whichever was tapped would pass a looser test and
        // send a parent-teacher to the wrong side of the app.
        var chosen: Lens? = null
        render(
            listOf(LensOption(Lens.TEACHER, 3), LensOption(Lens.GUARDIAN, 1)),
            onChoose = { chosen = it },
        )

        compose.onAllNodesWithTag(TAG_LENS_OPTION)[1].performClick()

        assertEquals(Lens.GUARDIAN, chosen)
    }

    @Test
    fun `rendering alone chooses nothing`() {
        var chosen: Lens? = null
        render(listOf(LensOption(Lens.TEACHER, 1)), onChoose = { chosen = it })

        assertEquals(null, chosen)
    }

    @Test
    fun `the server's order is the order shown`() {
        var chosen: Lens? = null
        render(
            listOf(LensOption(Lens.STUDENT, 1), LensOption(Lens.TEACHER, 9)),
            onChoose = { chosen = it },
        )

        compose.onAllNodesWithTag(TAG_LENS_OPTION)[0].performClick()

        assertEquals(Lens.STUDENT, chosen)
    }
}
