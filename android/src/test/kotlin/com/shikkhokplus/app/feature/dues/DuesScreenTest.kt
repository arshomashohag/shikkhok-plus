package com.shikkhokplus.app.feature.dues

import androidx.activity.ComponentActivity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performSemanticsAction
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.dues.ui.DuesActions
import com.shikkhokplus.app.feature.dues.ui.DuesScreen
import com.shikkhokplus.app.feature.dues.ui.TAG_DUES_DAYS
import com.shikkhokplus.app.feature.dues.ui.TAG_DUES_EMPTY
import com.shikkhokplus.app.feature.dues.ui.TAG_DUES_GROUP
import com.shikkhokplus.app.feature.dues.ui.TAG_DUES_LIST
import com.shikkhokplus.app.feature.dues.ui.TAG_DUES_REMIND
import com.shikkhokplus.app.feature.dues.ui.TAG_DUES_REMIND_RESULT
import com.shikkhokplus.app.feature.dues.ui.TAG_DUES_REMIND_SEND
import com.shikkhokplus.app.feature.dues.ui.TAG_DUES_SUMMARY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * T5, rendered: the headline, the groups, and the reminder flow.
 *
 * Every figure and every group arrives from the server; these pin that
 * the screen shows them and that "Remind" asks before it sends.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class DuesScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun loaded(remindable: Int = 1): DuesUiState.Loaded =
        DuesStateMapper.afterLoad(
            duesResponse(
                duesRow("Jannatul", bucket = "over_30", remindable = true),
                duesRow("Sakib", bucket = "late", reminded = "2026-10-14T06:00:00Z"),
                duesRow("Nusrat"),
                remindable = remindable,
            ),
        ) as DuesUiState.Loaded

    private fun show(state: DuesUiState, actions: DuesActions = DuesActions()) {
        compose.setContent { ShikkhokTheme { DuesScreen(state = state, actions = actions) } }
    }

    @Test
    fun `the headline, three groups and each row's lateness are shown`() {
        show(loaded())

        compose.onNodeWithTag(TAG_DUES_SUMMARY).assertExists()
        compose.onNodeWithText("৳6,000").assertExists()
        // The list is lazy: each part is composed once scrolled to.
        for (name in listOf("Jannatul", "Sakib", "Nusrat")) {
            compose.onNodeWithTag(TAG_DUES_LIST).performScrollToNode(hasText(name))
            compose.onNodeWithText(name, useUnmergedTree = true).assertExists()
        }
        compose.onNodeWithTag(TAG_DUES_LIST).performScrollToNode(hasText("Jannatul"))
        compose.onNodeWithText("Never reminded", useUnmergedTree = true).assertExists()
        compose.onAllNodesWithTag(TAG_DUES_DAYS, useUnmergedTree = true)[0].assertExists()
        compose.onAllNodesWithTag(TAG_DUES_GROUP)[0].assertExists()
    }

    @Test
    fun `remind asks first rather than sending`() {
        var asked = 0
        var sent = 0
        show(loaded(), DuesActions(onAskRemind = { asked++ }, onRemind = { sent++ }))

        compose.onNodeWithTag(TAG_DUES_REMIND).performClick()

        assertEquals(1, asked)
        assertEquals(0, sent)
    }

    @Test
    fun `the confirmation sends`() {
        var sent = 0
        show(loaded().copy(remind = RemindState.Confirming), DuesActions(onRemind = { sent++ }))

        compose.onNodeWithTag(TAG_DUES_REMIND_SEND).performSemanticsAction(SemanticsActions.OnClick)

        assertEquals(1, sent)
    }

    @Test
    fun `nobody to remind means no remind button`() {
        show(loaded(remindable = 0))

        compose.onNodeWithTag(TAG_DUES_REMIND).assertDoesNotExist()
    }

    @Test
    fun `a sent reminder says how many it reached`() {
        show(loaded().copy(remind = RemindState.Sent(4)))

        compose.onNodeWithTag(TAG_DUES_REMIND_RESULT).assertExists()
        compose.onNodeWithText("Reminded 4 students", useUnmergedTree = true).assertExists()
    }

    @Test
    fun `nobody owing is good news, not a blank`() {
        show(DuesUiState.Empty)

        compose.onNodeWithTag(TAG_DUES_EMPTY).assertExists()
    }
}
