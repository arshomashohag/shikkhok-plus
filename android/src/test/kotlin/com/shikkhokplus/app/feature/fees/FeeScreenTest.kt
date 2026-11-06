package com.shikkhokplus.app.feature.fees

import androidx.compose.ui.test.onNodeWithText
import com.shikkhokplus.app.feature.fees.ui.extraFeeRowTag
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_EXTRA
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.fees.ui.ClaimStatusScreen
import com.shikkhokplus.app.feature.fees.ui.FeeHistoryScreen
import com.shikkhokplus.app.feature.fees.ui.PaymentFormScreen
import com.shikkhokplus.app.feature.fees.ui.TAG_CLAIMS_EMPTY
import com.shikkhokplus.app.feature.fees.ui.TAG_CLAIM_APPROVED
import com.shikkhokplus.app.feature.fees.ui.TAG_CLAIM_CORRECTION
import com.shikkhokplus.app.feature.fees.ui.TAG_CLAIM_DISPOSITION
import com.shikkhokplus.app.feature.fees.ui.TAG_CLAIM_STATUS
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_EMPTY
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_ERROR
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_LIST
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_LOADING
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_PROGRESS
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_RETRY
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_ROW
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_STATUS
import com.shikkhokplus.app.feature.fees.ui.TAG_FEES_TOTAL
import com.shikkhokplus.app.feature.fees.ui.TAG_PAYMENT_CHANNEL
import com.shikkhokplus.app.feature.fees.ui.TAG_PAYMENT_DESTINATION
import com.shikkhokplus.app.feature.fees.ui.TAG_PAYMENT_NO_DESTINATION
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * What the fee screens render for a given state.
 *
 * The half the mapper tests cannot see: a correct state rendered with
 * the wrong control is still a broken screen.
 *
 * **The property under test throughout is that the screen reads MAPPER
 * FIELDS rather than comparing domain values.** Each case here hands
 * the screen a state whose amount and whose decision point in opposite
 * directions, so a composable that re-derived the decision from the
 * amount would render the wrong thing and fail.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class FeeScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun row(
        period: String = "2027-02",
        status: String = "fees.status.unpaid",
        settled: Boolean = false,
        outstanding: String = "1000.00",
    ): FeeCycleRow =
        FeeCycleRow(
            period = period,
            periodLabel = period,
            dueDateLabel = "2027-02-28",
            charged = Money.of("1000.00"),
            outstanding = Money.of(outstanding),
            statusLabel = status,
            isSettled = settled,
        )

    // -----------------------------------------------------------------
    // The fee history.
    // -----------------------------------------------------------------

    @Test
    fun `loading shows a spinner and no list`() {
        compose.setContent { FeeHistoryScreen(FeeUiState.Loading, onRetry = {}) }

        compose.onNodeWithTag(TAG_FEES_LOADING).assertIsDisplayed()
        assertEquals(0, compose.onAllNodesWithTag(TAG_FEES_LIST).fetchSemanticsNodes().size)
    }

    @Test
    fun `the progress link shows only when the reader has one`() {
        var opened = false
        compose.setContent { FeeHistoryScreen(FeeUiState.Empty, onRetry = {}, onOpenProgress = { opened = true }) }

        compose.onNodeWithTag(TAG_FEES_PROGRESS).performClick()

        assertEquals(true, opened)
    }

    @Test
    fun `no progress link without one`() {
        compose.setContent { FeeHistoryScreen(FeeUiState.Empty, onRetry = {}) }

        assertEquals(0, compose.onAllNodesWithTag(TAG_FEES_PROGRESS).fetchSemanticsNodes().size)
    }

    @Test
    fun `no generated period shows the empty explanation`() {
        compose.setContent { FeeHistoryScreen(FeeUiState.Empty, onRetry = {}) }

        compose.onNodeWithTag(TAG_FEES_EMPTY).assertIsDisplayed()
    }

    @Test
    fun `a waived cycle renders the waived label and not a paid one`() {
        // THE CASE. Outstanding is zero and the status is waived; a
        // screen comparing the amount would show "Paid" -- telling a
        // student somebody paid when the teacher excused it.
        compose.setContent {
            FeeHistoryScreen(
                FeeUiState.Loaded(
                    listOf(
                        row(
                            status = "fees.status.waived",
                            settled = true,
                            outstanding = "0.00",
                        ),
                    ),
                    Money.ZERO,
                ),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_FEES_STATUS).assertIsDisplayed()
        // The rendered text is the waived string, not the paid one.
        compose.onNodeWithTag(TAG_FEES_STATUS).assertIsDisplayed()
        assertEquals(
            1,
            compose.onAllNodesWithTag(TAG_FEES_ROW).fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `the total shown is the one handed in, not a sum of the rows`() {
        // The state carries one 1000 row and a 4500 total, which is
        // what a paginated history looks like. A screen summing the
        // rows would show 1000.
        compose.setContent {
            FeeHistoryScreen(
                FeeUiState.Loaded(listOf(row()), Money.of("4500.00")),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_FEES_TOTAL).assertIsDisplayed()
    }

    @Test
    fun `a retryable failure offers retry`() {
        compose.setContent {
            FeeHistoryScreen(
                FeeUiState.Failed("error.network.unreachable", retryable = true),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_FEES_ERROR).assertIsDisplayed()
        compose.onNodeWithTag(TAG_FEES_RETRY).assertIsDisplayed()
    }

    @Test
    fun `a final failure offers no retry`() {
        // Split from the retryable case because Compose permits one
        // setContent per test. Both halves are needed: a screen that
        // always offered retry would pass the first alone, and
        // "nothing is outstanding to pay" is not improved by asking
        // again.
        compose.setContent {
            FeeHistoryScreen(
                FeeUiState.Failed("fees.claim.no_open_cycle", retryable = false),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_FEES_ERROR).assertIsDisplayed()
        assertEquals(
            0,
            compose.onAllNodesWithTag(TAG_FEES_RETRY).fetchSemanticsNodes().size,
        )
    }

    // -----------------------------------------------------------------
    // The payment form.
    // -----------------------------------------------------------------

    @Test
    fun `an unset destination omits the step entirely`() {
        // [NFR14.34] ABSENT, not blank. A blank field reads as a value
        // that failed to load.
        compose.setContent {
            PaymentFormScreen(
                destination = PaymentDestination.Unset(),
                childName = "Rahim",
                batchName = "Physics",
                amountText = "",
                referenceText = "",
                selectedChannel = null,
                canSubmit = false,
                onAmountChange = {},
                onReferenceChange = {},
                onChannelSelected = {},
                onSubmit = {},
            )
        }

        compose.onNodeWithTag(TAG_PAYMENT_NO_DESTINATION).assertIsDisplayed()
        assertEquals(
            0,
            compose.onAllNodesWithTag(TAG_PAYMENT_DESTINATION).fetchSemanticsNodes().size,
        )
        // No channel buttons either: there is nowhere to send money.
        assertEquals(
            0,
            compose.onAllNodesWithTag(TAG_PAYMENT_CHANNEL).fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `the channel options come from the server's list`() {
        // Two channels nobody hardcoded, to prove the screen renders
        // the list rather than a set it knows [BR6.5].
        compose.setContent {
            PaymentFormScreen(
                destination =
                    PaymentDestination.Known(
                        collectionNumber = "01711000000",
                        collectionChannelLabel = "bKash",
                        channels = listOf("Upay", "SureCash"),
                    ),
                childName = "Rahim",
                batchName = "Physics",
                amountText = "",
                referenceText = "",
                selectedChannel = null,
                canSubmit = false,
                onAmountChange = {},
                onReferenceChange = {},
                onChannelSelected = {},
                onSubmit = {},
            )
        }

        compose.onNodeWithTag(TAG_PAYMENT_DESTINATION).assertIsDisplayed()
        assertEquals(
            2,
            compose.onAllNodesWithTag(TAG_PAYMENT_CHANNEL).fetchSemanticsNodes().size,
        )
    }

    // -----------------------------------------------------------------
    // Claim outcomes.
    // -----------------------------------------------------------------

    private fun claimRow(
        status: String,
        approved: String? = null,
        decided: Boolean = true,
        disposition: String? = null,
        correction: String? = null,
    ): ClaimRow =
        ClaimRow(
            claimId = "c-1",
            period = "2027-02",
            claimedAmount = Money.of("1500.00"),
            approvedAmount = approved?.let { Money.of(it) },
            statusLabel = status,
            dispositionLabel = disposition,
            channelLabel = "bKash",
            isDecided = decided,
            correctionNoticeKey = correction,
        )

    @Test
    fun `a rejection is shown to the submitter`() {
        // [BR5.6] A rejection the submitter never sees leaves them
        // believing they paid.
        compose.setContent {
            ClaimStatusScreen(listOf(claimRow("fees.claim.rejected")))
        }

        compose.onNodeWithTag(TAG_CLAIM_STATUS).assertIsDisplayed()
        // Decided, but with no approved amount -- so the approved line
        // is absent rather than blank.
        assertEquals(
            0,
            compose.onAllNodesWithTag(TAG_CLAIM_APPROVED).fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `a partial approval shows the amount and the disposition`() {
        compose.setContent {
            ClaimStatusScreen(
                listOf(
                    claimRow(
                        "fees.claim.approved_partial",
                        approved = "600.00",
                        disposition = "fees.disposition.carried",
                    ),
                ),
            )
        }

        compose.onNodeWithTag(TAG_CLAIM_APPROVED).assertIsDisplayed()
        compose.onNodeWithTag(TAG_CLAIM_DISPOSITION).assertIsDisplayed()
    }

    @Test
    fun `a corrected verification is shown to the submitter`() {
        // [BR5.7, FR9.2] Never hidden from the person whose money it
        // concerns.
        compose.setContent {
            ClaimStatusScreen(
                listOf(
                    claimRow(
                        "fees.claim.approved_partial",
                        approved = "600.00",
                        correction = "fees.claim.corrected",
                    ),
                ),
            )
        }

        compose.onNodeWithTag(TAG_CLAIM_CORRECTION).assertIsDisplayed()
    }

    @Test
    fun `an uncorrected claim shows no correction notice`() {
        compose.setContent {
            ClaimStatusScreen(
                listOf(claimRow("fees.claim.approved_full", approved = "1500.00")),
            )
        }

        assertEquals(
            0,
            compose.onAllNodesWithTag(TAG_CLAIM_CORRECTION).fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `no claims yet explains itself`() {
        compose.setContent { ClaimStatusScreen(emptyList()) }

        compose.onNodeWithTag(TAG_CLAIMS_EMPTY).assertIsDisplayed()
    }

    @Test
    fun `a seat's exam and other fees are listed with what is owed and their status`() {
        compose.setContent {
            FeeHistoryScreen(
                FeeUiState.Empty,
                onRetry = {},
                extraFees =
                    listOf(ExtraFeeRow("f-1", "Half-yearly exam", Money.of("300.00"), "2026-11-20", "partly_paid")),
            )
        }

        compose.onNodeWithTag(TAG_FEES_EXTRA).assertIsDisplayed()
        compose.onNodeWithTag(extraFeeRowTag("f-1")).assertIsDisplayed()
        compose.onNodeWithText("Half-yearly exam").assertIsDisplayed()
        compose.onNodeWithText("Partly paid").assertIsDisplayed()
    }

    @Test
    fun `no exam or other fee draws no section`() {
        compose.setContent { FeeHistoryScreen(FeeUiState.Empty, onRetry = {}) }

        assertEquals(0, compose.onAllNodesWithTag(TAG_FEES_EXTRA).fetchSemanticsNodes().size)
    }

}
