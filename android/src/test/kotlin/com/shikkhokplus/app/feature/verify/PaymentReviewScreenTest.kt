package com.shikkhokplus.app.feature.verify

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.verify.ui.PaymentReviewScreen
import com.shikkhokplus.app.feature.verify.ui.ReviewActions
import com.shikkhokplus.app.feature.verify.ui.SheetActions
import com.shikkhokplus.app.feature.verify.ui.TAG_REVIEW_APPROVE_OTHER
import com.shikkhokplus.app.feature.verify.ui.TAG_REVIEW_CHANGE
import com.shikkhokplus.app.feature.verify.ui.TAG_REVIEW_CHILD
import com.shikkhokplus.app.feature.verify.ui.TAG_REVIEW_OWED_TOGETHER
import com.shikkhokplus.app.feature.verify.ui.TAG_REVIEW_DECISION_NOTE
import com.shikkhokplus.app.feature.verify.ui.TAG_SHEET_CARRY
import com.shikkhokplus.app.feature.verify.ui.TAG_SHEET_CONFIRM
import com.shikkhokplus.app.feature.verify.ui.TAG_SHEET_LINE
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_APPROVE
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_REJECT
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_REJECT_CONFIRM
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

/** R2 to R4, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PaymentReviewScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun card(status: String = "pending", note: String? = null) =
        assertNotNull(VerifyStateMapper.toCard(review(status = status, decisionNote = note)))

    private fun actions(log: MutableList<String>) =
        ReviewActions(
            onBack = {},
            onApprove = { log += "approve:$it" },
            onApproveOther = { log += "other" },
            onReject = { log += "reject:$it" },
            onChangeDecision = { log += "change" },
            onRetry = {},
            sheet =
                SheetActions(
                    onType = {},
                    onDisposition = {},
                    onChild = {},
                    onNote = {},
                    onConfirm = { log += "confirm" },
                    onDismiss = {},
                ),
        )

    private fun render(state: ReviewUiState, sheet: ApprovalSheet? = null, log: MutableList<String>) {
        compose.setContent {
            ShikkhokTheme { PaymentReviewScreen(state = state, sheet = sheet, actions = actions(log)) }
        }
    }

    @Test
    fun `a pending payment offers approve reject and a different amount`() {
        val log = mutableListOf<String>()
        render(ReviewUiState.Loaded(card()), log = log)

        compose.onNodeWithTag(TAG_VERIFY_APPROVE).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_REVIEW_APPROVE_OTHER).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_VERIFY_REJECT).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_VERIFY_REJECT_CONFIRM).performClick()

        assertEquals(listOf("approve:", "other", "reject:"), log)
    }

    @Test
    fun `the detail lists each child with the month and what they owe, then the total owed`() {
        render(ReviewUiState.Loaded(card()), log = mutableListOf())

        compose.onNodeWithTag(TAG_REVIEW_CHILD + "_e-1").assertTextContains("Rafsan", substring = true)
        compose.onNodeWithTag(TAG_REVIEW_CHILD + "_e-1").assertTextContains("Oct", substring = true)
        compose.onNodeWithTag(TAG_REVIEW_CHILD + "_e-1").assertTextContains("৳1,000", substring = true)
        compose.onNodeWithTag(TAG_REVIEW_CHILD + "_e-2").assertTextContains("Tasnim", substring = true)
        compose.onNodeWithTag(TAG_REVIEW_OWED_TOGETHER).assertTextContains("৳2,000", substring = true)
    }

    @Test
    fun `a rejected payment shows the teacher's note and offers change decision`() {
        val log = mutableListOf<String>()
        render(ReviewUiState.Loaded(card("rejected", "Wrong number")), log = log)

        compose.onNodeWithTag(TAG_REVIEW_DECISION_NOTE).assertExists()
        compose.onNodeWithTag(TAG_VERIFY_APPROVE).assertDoesNotExist()
        compose.onNodeWithTag(TAG_REVIEW_CHANGE).performScrollTo().performClick()
        assertEquals(listOf("change"), log)
    }

    @Test
    fun `the sheet for an exact amount shows no carry or waive`() {
        val log = mutableListOf<String>()
        val loaded = ReviewUiState.Loaded(card())
        render(loaded, ApprovalSheet(loaded.card, "2000.00"), log)

        compose.onNodeWithTag(TAG_SHEET_LINE).assertExists()
        compose.onNodeWithTag(TAG_SHEET_CARRY).assertDoesNotExist()
        compose.onNodeWithTag(TAG_SHEET_CONFIRM).assertIsEnabled()
    }

    @Test
    fun `the sheet for a short amount holds approve until carry or waive is chosen`() {
        val log = mutableListOf<String>()
        val loaded = ReviewUiState.Loaded(card())
        render(loaded, ApprovalSheet(loaded.card, "1500.00"), log)

        compose.onNodeWithTag(TAG_SHEET_CARRY).assertExists()
        compose.onNodeWithTag(TAG_SHEET_CONFIRM).assertIsNotEnabled()
    }
}
