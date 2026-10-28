package com.shikkhokplus.app.feature.verify

import androidx.activity.ComponentActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.verify.ui.PartialApprovalSheet
import com.shikkhokplus.app.feature.verify.ui.TAG_PARTIAL_CARRY
import com.shikkhokplus.app.feature.verify.ui.TAG_PARTIAL_CONFIRM
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_APPROVE
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_DUPLICATE
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_PARTIAL
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_REJECT
import com.shikkhokplus.app.feature.verify.ui.TAG_VERIFY_REJECT_CONFIRM
import com.shikkhokplus.app.feature.verify.ui.VerifyScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** T4, rendered: the server's words on the card, and a guarded reject. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class VerifyScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun card(comparison: Comparison, duplicate: DuplicateNote? = null) =
        ClaimCard(
            claimId = "c-1",
            displayName = "Rafsan",
            batchName = "Physics A",
            period = "2026-10",
            claimedAmount = Money.of("800.00"),
            charged = Money.of("1200.00"),
            comparison = comparison,
            difference = Money.of("400.00"),
            channel = "Nagad",
            transactionId = "7HQ2M0X9KD",
            submittedAt = "2026-10-28T10:00:00Z",
            submitterKey = "verify.from.guardian",
            submitterPhone = "+8801819552041",
            duplicate = duplicate,
        )

    private fun render(card: ClaimCard, actions: MutableList<String>) {
        compose.setContent {
            ShikkhokTheme {
                VerifyScreen(
                    state = VerifyUiState.Waiting(listOf(card), emptyList()),
                    sheet = null,
                    onBack = {},
                    onApprove = { actions += "approve" },
                    onPartial = { actions += "partial" },
                    onReject = { actions += "reject" },
                    onRetry = {},
                    onTypePartial = {},
                    onChoose = {},
                    onConfirmPartial = {},
                    onClosePartial = {},
                )
            }
        }
    }

    @Test
    fun `a short claim shows the server's shortfall and no separate partial button`() {
        val actions = mutableListOf<String>()
        render(card(Comparison.SHORT), actions)

        compose.onNodeWithText("৳400 short of ৳1,200", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("01819-552041 (guardian)").assertExists()
        compose.onNodeWithTag(TAG_VERIFY_PARTIAL).assertDoesNotExist()
        compose.onNodeWithText("Approve ৳800…").assertExists()
    }

    @Test
    fun `rejecting asks first, and only the confirmation rejects`() {
        val actions = mutableListOf<String>()
        render(card(Comparison.MATCHES), actions)

        compose.onNodeWithTag(TAG_VERIFY_REJECT).performClick()
        assertEquals(emptyList(), actions)
        compose.onNodeWithTag(TAG_VERIFY_REJECT_CONFIRM).performClick()

        assertEquals(listOf("reject"), actions)
    }

    @Test
    fun `a matching claim offers partial and approve`() {
        val actions = mutableListOf<String>()
        render(card(Comparison.MATCHES), actions)

        compose.onNodeWithTag(TAG_VERIFY_PARTIAL).performClick()
        compose.onNodeWithTag(TAG_VERIFY_APPROVE).performClick()

        assertEquals(listOf("partial", "approve"), actions)
    }

    @Test
    fun `a reused reference is called out on the card`() {
        render(
            card(
                Comparison.MATCHES,
                DuplicateNote("Sakib", "verify.decision.approved_full", Money.of("1500.00"), null),
            ),
            mutableListOf(),
        )

        compose.onNodeWithTag(TAG_VERIFY_DUPLICATE).assertExists()
        compose.onNodeWithText("This ID was already used.").assertExists()
    }

    @Test
    fun `the partial sheet asks carry or waive and approves only once chosen`() {
        val chosen = mutableListOf<String>()
        var confirmed = 0
        var sheet by mutableStateOf(PartialSheet(card(Comparison.SHORT), "800", Money.of("400.00"), true))
        compose.setContent {
            ShikkhokTheme {
                PartialApprovalSheet(
                    sheet = sheet,
                    onType = {},
                    onChoose = {
                        chosen += it
                        sheet = sheet.copy(disposition = it)
                    },
                    onConfirm = { confirmed++ },
                    onDismiss = {},
                )
            }
        }

        compose.onNodeWithText("What happens to the other ৳400?").assertExists()
        compose.onNodeWithTag(TAG_PARTIAL_CONFIRM).assertIsNotEnabled()
        // The sheet is taller than the 320x414 test window, so its
        // options are clicked through their semantics, not by position.
        compose.onNodeWithTag(TAG_PARTIAL_CARRY).performSemanticsAction(SemanticsActions.OnClick)
        compose.onNodeWithText("carry ৳400", substring = true, useUnmergedTree = true).assertExists()
        compose
            .onNodeWithTag(TAG_PARTIAL_CONFIRM)
            .assertIsEnabled()
            .performSemanticsAction(SemanticsActions.OnClick)

        assertEquals(listOf("carried"), chosen)
        assertEquals(1, confirmed)
    }

    @Test
    fun `no choice is offered before the server has stated the shortfall`() {
        compose.setContent {
            ShikkhokTheme {
                PartialApprovalSheet(
                    sheet = PartialSheet(card(Comparison.SHORT), "800"),
                    onType = {},
                    onChoose = {},
                    onConfirm = {},
                    onDismiss = {},
                )
            }
        }

        compose.onNodeWithTag(TAG_PARTIAL_CARRY).assertDoesNotExist()
        compose.onNodeWithTag(TAG_PARTIAL_CONFIRM).assertIsNotEnabled()
    }
}
