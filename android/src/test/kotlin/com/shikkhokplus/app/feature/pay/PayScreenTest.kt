package com.shikkhokplus.app.feature.pay

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.assertIsSelected
import com.shikkhokplus.app.feature.pay.ui.payForFeeTag
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_FOR_MONTHLY
import com.shikkhokplus.app.core.network.ExtraFeeRefDto
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.OwedChildDto
import com.shikkhokplus.app.core.network.OwedTogetherDto
import com.shikkhokplus.app.core.network.PaymentMethodDto
import com.shikkhokplus.app.core.network.PaymentSubmittedDto
import com.shikkhokplus.app.core.network.SubmittedClaimDto
import com.shikkhokplus.app.feature.pay.ui.PayActions
import com.shikkhokplus.app.feature.pay.ui.PayScreen
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_ACCOUNT
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_CASH
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_CHILD
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_ID
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_METHOD
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_OWED
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_SEND
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_SENT
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The pay screens rendered: choosing, each form's send rule, and the sent page. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PayScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val bkash = PaymentMethodDto("m-1", "mobile", "bKash", mobileNumber = "01712345678")
    private val bank = PaymentMethodDto("m-2", "bank", "Dutch-Bangla", accountNumber = "1051", branchName = "Mirpur")
    private val twin =
        PayBatch("b", "Physics", listOf(PaySeat("e-1", "Tanvir"), PaySeat("e-2", "Tania")))
    private val scope = PayScope(listOf(twin), twin, listOf("e-1", "e-2"), listOf(bkash, bank), "Rahima")

    private fun filling(choice: PayChoice, form: PayForm, sending: Boolean = false) =
        PayUiState.Filling(
            scope,
            choice,
            OwedTogetherDto(
                Money.of("2000.00"),
                listOf(
                    OwedChildDto("e-1", "Tanvir", Money.of("1000.00")),
                    OwedChildDto("e-2", "Tania", Money.of("1000.00")),
                ),
            ),
            form,
            sending = sending,
        )

    @Test
    fun `choosing lists the methods and cash`() {
        val chosen = mutableListOf<PayChoice>()
        compose.setContent {
            ShikkhokTheme { PayScreen(PayUiState.Methods(scope), PayActions(onChoose = { chosen += it })) }
        }

        compose.onAllNodesWithTag(TAG_PAY_METHOD)[1].performScrollTo().performClick()
        compose.onNodeWithTag(TAG_PAY_CASH).performScrollTo().performClick()

        assertEquals(listOf(PayChoice.Method(bank), PayChoice.Cash), chosen)
    }

    @Test
    fun `mobile form sends once it has an id and an amount`() {
        var sends = 0
        compose.setContent {
            ShikkhokTheme {
                PayScreen(
                    filling(
                        PayChoice.Method(bkash),
                        PayForm("2026-11-02", transactionId = "9KD7Q2XL1M", amount = "2000.00"),
                    ),
                    PayActions(onSend = { sends++ }),
                    todayIso = "2026-11-02",
                )
            }
        }

        compose.onNodeWithTag(TAG_PAY_SEND).assertIsEnabled().performClick()

        assertEquals(1, sends)
        compose.onNodeWithTag(TAG_PAY_ID).assertExists()
        compose.onNodeWithTag(TAG_PAY_OWED, useUnmergedTree = true).assertExists()
    }

    @Test
    fun `mobile form without an id cannot send, and a bank form asks for the account`() {
        compose.setContent {
            ShikkhokTheme {
                PayScreen(
                    filling(PayChoice.Method(bank), PayForm("2026-11-02", amount = "2000.00")),
                    PayActions(),
                    todayIso = "2026-11-02",
                )
            }
        }

        compose.onNodeWithTag(TAG_PAY_SEND).assertIsNotEnabled()
        compose.onNodeWithTag(TAG_PAY_ACCOUNT).assertExists()
    }

    @Test
    fun `send is disabled while sending`() {
        compose.setContent {
            ShikkhokTheme {
                PayScreen(
                    filling(PayChoice.Cash, PayForm("2026-11-02", amount = "500.00"), sending = true),
                    PayActions(),
                    todayIso = "2026-11-02",
                )
            }
        }

        compose.onNodeWithTag(TAG_PAY_SEND).assertIsNotEnabled()
    }

    @Test
    fun `the for field lets a guardian toggle each child`() {
        val toggled = mutableListOf<String>()
        compose.setContent {
            ShikkhokTheme {
                PayScreen(
                    filling(PayChoice.Cash, PayForm("2026-11-02")),
                    PayActions(onToggleChild = { toggled += it }),
                    todayIso = "2026-11-02",
                )
            }
        }

        compose.onAllNodesWithTag(TAG_PAY_CHILD)[1].performScrollTo().performClick()

        assertEquals(2, compose.onAllNodesWithTag(TAG_PAY_CHILD).fetchSemanticsNodes().size)
    }

    @Test
    fun `the sent page shows the payment and that it is pending`() {
        val payment =
            PaymentSubmittedDto(
                "s-1",
                "pending",
                Money.of("1000.00"),
                "2026-11-02",
                listOf(SubmittedClaimDto("c-1", Money.of("1000.00"), "Tanvir", "e-1", "2026-11")),
            )
        compose.setContent {
            ShikkhokTheme {
                PayScreen(
                    PayUiState.Sent("Physics", "Rahima", PayChoice.Method(bkash), payment, "9KD7Q2XL1M"),
                    PayActions(),
                )
            }
        }

        compose.onNodeWithTag(TAG_PAY_SENT).assertExists()
    }

    @Test
    fun `a resend the teacher already approved says so rather than pending`() {
        // A replay returns the original submission with its stored
        // status; "Sent for checking" would be false for a payment the
        // teacher has already approved.
        val payment =
            PaymentSubmittedDto(
                "s-1",
                "approved",
                Money.of("1000.00"),
                "2026-11-02",
                listOf(SubmittedClaimDto("c-1", Money.of("1000.00"), "Tanvir", "e-1", "2026-11")),
            )
        compose.setContent {
            ShikkhokTheme {
                PayScreen(
                    PayUiState.Sent(
                        "Physics",
                        "Rahima",
                        PayChoice.Method(bkash),
                        payment,
                        "9KD7Q2XL1M",
                        SentOutcome.APPROVED,
                    ),
                    PayActions(),
                )
            }
        }

        val shown = { id: Int -> compose.onAllNodesWithText(compose.activity.getString(id)).fetchSemanticsNodes() }
        assertTrue(shown(R.string.pay_recorded_title).isNotEmpty(), "the decided title")
        assertTrue(shown(R.string.inbox_outcome_approved).isNotEmpty(), "the approved status")
        assertTrue(shown(R.string.pay_pending).isEmpty(), "nothing says pending")
    }

    @Test
    fun `the payment-for question lists monthly and each fee and reports the choice`() {
        val chosen = mutableListOf<String?>()
        val fee = ExtraFeeRefDto("f-1", "Half-yearly exam", "exam", "2026-11-20")
        compose.setContent {
            ShikkhokTheme {
                PayScreen(
                    filling(PayChoice.Cash, PayForm("2026-11-02", amount = "2000.00"))
                        .copy(feeOptions = listOf(fee)),
                    PayActions(onChooseFee = { chosen += it }),
                    todayIso = "2026-11-02",
                )
            }
        }

        compose.onNodeWithText("What is this payment for?").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_PAY_FOR_MONTHLY).performScrollTo().assertIsSelected()
        compose.onNodeWithTag(payForFeeTag("f-1")).performScrollTo().performClick()

        assertEquals(listOf<String?>("f-1"), chosen)
    }

    @Test
    fun `with no fee to choose the payment-for question is not asked`() {
        compose.setContent {
            ShikkhokTheme {
                PayScreen(
                    filling(PayChoice.Cash, PayForm("2026-11-02", amount = "2000.00")),
                    PayActions(),
                    todayIso = "2026-11-02",
                )
            }
        }

        compose.onNodeWithTag(TAG_PAY_FOR_MONTHLY).assertDoesNotExist()
    }

}
