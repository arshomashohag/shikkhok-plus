package com.shikkhokplus.app.feature.inbox

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.inbox.ui.InboxBell
import com.shikkhokplus.app.feature.inbox.ui.InboxScreen
import com.shikkhokplus.app.feature.inbox.ui.TAG_INBOX_BADGE
import com.shikkhokplus.app.feature.inbox.ui.TAG_INBOX_BELL
import com.shikkhokplus.app.feature.inbox.ui.TAG_INBOX_EMPTY
import com.shikkhokplus.app.feature.inbox.ui.TAG_INBOX_ITEM
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The inbox and its bell, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class InboxScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun `a reminder shows its batch and what is owed`() {
        val message = InboxMessage("n-1", "Physics", Money.of("1200.00"), "2026-10", "2026-10-17T06:00:00Z", true)
        compose.setContent {
            ShikkhokTheme { InboxScreen(InboxUiState.Loaded(listOf(message), 1), onBack = {}, onRetry = {}) }
        }

        compose.onAllNodesWithTag(TAG_INBOX_ITEM).assertCountEquals(1)
        compose.onNodeWithText("Fee reminder · Physics", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("৳1,200 is due, from October.", useUnmergedTree = true).assertExists()
    }

    @Test
    fun `an empty inbox says where reminders will appear`() {
        compose.setContent {
            ShikkhokTheme { InboxScreen(InboxUiState.Loaded(emptyList(), 0), onBack = {}, onRetry = {}) }
        }

        compose.onNodeWithTag(TAG_INBOX_EMPTY).assertExists()
    }

    @Test
    fun `the bell shows the server's unread count and opens the inbox`() {
        var opened = 0
        compose.setContent { ShikkhokTheme { InboxBell(unread = 12, onClick = { opened++ }) } }

        compose.onNodeWithTag(TAG_INBOX_BADGE, useUnmergedTree = true).assertExists()
        compose.onNodeWithText("9+", useUnmergedTree = true).assertExists()
        compose.onNodeWithTag(TAG_INBOX_BELL).performClick()
        assertEquals(1, opened)
    }

    @Test
    fun `no unread means no badge`() {
        compose.setContent { ShikkhokTheme { InboxBell(unread = 0, onClick = {}) } }

        compose.onNodeWithTag(TAG_INBOX_BADGE, useUnmergedTree = true).assertDoesNotExist()
    }
}
