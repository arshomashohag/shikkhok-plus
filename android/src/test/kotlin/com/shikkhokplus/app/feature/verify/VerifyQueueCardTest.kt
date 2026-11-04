package com.shikkhokplus.app.feature.verify

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithText
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_CARD_TRX
import com.shikkhokplus.app.feature.verify.ui.VerifyScreen
import com.shikkhokplus.app.feature.verify.ui.QueueDecisions
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_CARD_APPROVE
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_CARD_PARTIAL
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import kotlin.test.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertNotNull

/**
 * T4's queue card: the transaction ID and the paying account on the
 * card itself, so a teacher can match it against their bKash SMS from
 * the list, and a reused ID is flagged there rather than only in the
 * detail.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class VerifyQueueCardTest {

    @get:Rule
    val compose = createComposeRule()

    private fun show(
        vararg cards: ReviewCard,
        decisions: QueueDecisions = QueueDecisions(),
        onOpen: (String) -> Unit = {},
    ) {
        compose.setContent {
            ShikkhokTheme {
                VerifyScreen(
                    state = VerifyUiState.Waiting(pending = cards.toList(), recent = emptyList()),
                    onBack = {},
                    onOpen = onOpen,
                    onRetry = {},
                    decisions = decisions,
                )
            }
        }
    }

    @Test
    fun `the card shows the transaction ID`() {
        show(assertNotNull(VerifyStateMapper.toCard(review())))

        compose.onNodeWithText("TrxID BJK40OQ1IL", substring = true).assertIsDisplayed()
    }

    @Test
    fun `a cash payment has no transaction line`() {
        show(assertNotNull(VerifyStateMapper.toCard(review().copy(transactionId = null, fromAccount = null))))

        compose.onAllNodesWithTag(TAG_VERIFY_CARD_TRX).assertCountEquals(0)
    }

    @Test
    fun `a matching payment is approved from its card`() {
        val approved = mutableListOf<String>()
        show(
            assertNotNull(VerifyStateMapper.toCard(review())),
            decisions = QueueDecisions(onApprove = { approved += it.submissionId }),
        )

        compose.onNodeWithTag(TAG_VERIFY_CARD_APPROVE).performClick()

        assertEquals(listOf("s-1"), approved)
    }

    @Test
    fun `a short payment offers Partial, which opens the review`() {
        val opened = mutableListOf<String>()
        show(
            assertNotNull(
                VerifyStateMapper.toCard(review(comparison = "short", total = "1500.00", difference = "500.00")),
            ),
            decisions = QueueDecisions(onApprove = {}),
            onOpen = { opened += it },
        )

        compose.onAllNodesWithTag(TAG_VERIFY_CARD_APPROVE).assertCountEquals(0)
        compose.onNodeWithTag(TAG_VERIFY_CARD_PARTIAL).performClick()

        assertEquals(listOf("s-1"), opened)
    }
}
