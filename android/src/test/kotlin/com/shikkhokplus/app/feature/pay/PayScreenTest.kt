package com.shikkhokplus.app.feature.pay

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.pay.ui.PayActions
import com.shikkhokplus.app.feature.pay.ui.PayScreen
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_CHANNEL
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_OPTION
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_SEND
import com.shikkhokplus.app.feature.pay.ui.TAG_PAY_SENT
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** S3 rendered: choosing, the form's send rule, and the sent page. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PayScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val option = PayOption("e-1", "Maths", "2026-10", Money.of("1500.00"), "2026-10-20")
    private val destination = PayDestination("01712345678", "bKash", "Najma")

    private fun filling(form: PayForm) =
        PayUiState.Filling(option, destination, listOf("bKash", "Nagad", "Rocket"), form)

    @Test
    fun `choosing a fee calls back with it`() {
        val chosen = mutableListOf<PayOption>()
        compose.setContent {
            ShikkhokTheme {
                PayScreen(PayUiState.Choosing(listOf(option), emptyList()), PayActions(onChoose = { chosen += it }))
            }
        }

        compose.onNodeWithTag(TAG_PAY_OPTION).performClick()

        assertEquals(listOf(option), chosen)
        compose.onNodeWithTag(TAG_PAY_SEND).assertIsNotEnabled()
    }

    @Test
    fun `send waits for an app and an ID, then sends`() {
        var sends = 0
        compose.setContent {
            ShikkhokTheme {
                PayScreen(filling(PayForm("bKash", "DJ62K0LQ7V", "1500.00")), PayActions(onSend = { sends++ }))
            }
        }

        compose.onNodeWithTag(TAG_PAY_SEND).assertIsEnabled().performClick()

        assertEquals(1, sends)
        compose.onNodeWithText("1. Send money to Najma", useUnmergedTree = true).assertExists()
    }

    @Test
    fun `without an ID nothing can be sent, and an app can be picked`() {
        val typed = mutableListOf<PayForm>()
        compose.setContent {
            ShikkhokTheme { PayScreen(filling(PayForm(null, "", "1500.00")), PayActions(onType = { typed += it })) }
        }

        compose.onNodeWithTag(TAG_PAY_SEND).assertIsNotEnabled()
        compose.onAllNodesWithTag(TAG_PAY_CHANNEL)[1].performScrollTo().performClick()

        assertEquals("Nagad", typed.single().channel)
    }

    @Test
    fun `the sent page shows the payment and that it is being checked`() {
        compose.setContent {
            ShikkhokTheme {
                PayScreen(
                    PayUiState.Sent(
                        option,
                        SentPayment(Money.of("1500.00"), "bKash", "DJ62K0LQ7V", "2026-10-17T09:22:00Z"),
                        "Najma",
                    ),
                    PayActions(),
                )
            }
        }

        compose.onNodeWithTag(TAG_PAY_SENT).assertExists()
        compose.onNodeWithText("DJ62K0LQ7V", useUnmergedTree = true).assertExists()
    }
}
