package com.shikkhokplus.app.feature.inbox

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.inbox.ui.InboxDetailScreen
import com.shikkhokplus.app.feature.inbox.ui.TAG_INBOX_UNAVAILABLE
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** The detail screen, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class InboxDetailScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun show(content: InboxContent?, kind: InboxKind) {
        val detail = InboxDetail(kind, "Physics", null, content)
        compose.setContent {
            ShikkhokTheme { InboxDetailScreen(InboxDetailUiState.Loaded(detail), onBack = {}, onRetry = {}) }
        }
    }

    @Test
    fun `a long Bangla reason is shown whole`() {
        val reason = "কারণ ".repeat(100).trim()
        show(
            InboxContent.Payment("2026-10", Money.of("1200.00"), null, PaymentOutcome.REJECTED, reason),
            InboxKind.PAYMENT_REJECTED,
        )

        compose.onNodeWithText(reason, useUnmergedTree = true).assertExists()
    }

    @Test
    fun `twenty long topics render without a crash`() {
        val topics = (1..20).map { "বিষয় $it " + "ক".repeat(110) }
        show(InboxContent.Exam("Mid-term", "2026-11-02", "Physics", 50, topics), InboxKind.EXAM_SCHEDULED)

        compose.onNodeWithText(topics.first(), substring = true, useUnmergedTree = true).assertExists()
    }

    @Test
    fun `a notice body is shown verbatim`() {
        show(InboxContent.Notice("Bring a pen", "2026-10-17T06:00:00Z", null), InboxKind.NOTICE)

        compose.onNodeWithText("Bring a pen", useUnmergedTree = true).assertExists()
    }

    @Test
    fun `an unavailable item says so`() {
        compose.setContent {
            ShikkhokTheme { InboxDetailScreen(InboxDetailUiState.Unavailable, onBack = {}, onRetry = {}) }
        }

        compose.onNodeWithTag(TAG_INBOX_UNAVAILABLE).assertExists()
        compose.onNodeWithText("This update is no longer available.", useUnmergedTree = true).assertExists()
    }
}
