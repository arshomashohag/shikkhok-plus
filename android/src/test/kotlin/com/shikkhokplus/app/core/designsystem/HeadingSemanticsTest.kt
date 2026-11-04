package com.shikkhokplus.app.core.designsystem

import androidx.activity.ComponentActivity
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import com.shikkhokplus.app.R
import com.shikkhokplus.app.feature.today.TodayUiState
import com.shikkhokplus.app.feature.today.ui.TodayScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * Screen titles and section headings are announced as headings.
 *
 * TalkBack's heading navigation is only as good as the headings a
 * screen declares, and none were declared before. Today is the screen
 * this matters most on: a teacher using a screen reader should be able
 * to jump from the classes straight to the payments waiting for them.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class HeadingSemanticsTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val isHeading = SemanticsMatcher.keyIsDefined(SemanticsProperties.Heading)

    private fun text(id: Int): String = compose.activity.getString(id)

    @Test
    fun `asHeading marks a node as a heading and plain text is not one`() {
        compose.setContent {
            ShikkhokTheme {
                Text("Marked", modifier = Modifier.asHeading())
                Text("Plain")
            }
        }
        compose.onNodeWithText("Marked").assert(isHeading)
        compose.onNodeWithText("Plain").assert(isHeading.not())
    }

    @Test
    fun `Today's title and both section headings are headings`() {
        compose.setContent {
            ShikkhokTheme {
                TodayScreen(
                    state = TodayUiState.Loading,
                    onOpenDues = {},
                    onRecord = {},
                    onMarks = {},
                    onVerifyAll = {},
                    onOpenPayment = {},
                    onCreateBatch = {},
                    onRetry = {},
                )
            }
        }
        listOf(R.string.today_title, R.string.today_classes, R.string.today_to_verify).forEach { id ->
            val matches = compose.onAllNodesWithText(text(id)).fetchSemanticsNodes().size
            assertEquals(1, matches, "expected one node reading '${text(id)}'")
            compose.onNodeWithText(text(id)).assert(isHeading and hasText(text(id)))
        }
    }
}
