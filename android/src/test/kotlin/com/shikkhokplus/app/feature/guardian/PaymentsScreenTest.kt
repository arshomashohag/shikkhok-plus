package com.shikkhokplus.app.feature.guardian

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.guardian.ui.PaymentsScreen
import com.shikkhokplus.app.feature.guardian.ui.TAG_PAYMENTS_NOTHING_DUE
import com.shikkhokplus.app.feature.guardian.ui.TAG_PAYMENTS_OWED
import com.shikkhokplus.app.feature.guardian.ui.TAG_PAYMENTS_PAY
import com.shikkhokplus.app.core.network.PayableDto

import androidx.compose.ui.test.assertIsNotEnabled
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** F1: the Send money button is always there once the history loads. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PaymentsScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun `send money shows with nothing owed`() {
        var sends = 0
        val loaded = PaymentsUiState.Loaded("Tanvir", 2026, Money.of("0.00"), emptyList(), next = null)
        compose.setContent {
            ShikkhokTheme { PaymentsScreen(loaded, onBack = {}, onPay = { sends++ }, onRetry = {}) }
        }

        compose.onNodeWithTag(TAG_PAYMENTS_PAY).assertExists().performClick()

        assertEquals(1, sends)
    }

    @Test
    fun `nothing due now is said, and Send money stays`() {
        val loaded = PaymentsUiState.Loaded("Tanvir", 2026, Money.of("0.00"), emptyList(), next = null)
        compose.setContent {
            ShikkhokTheme { PaymentsScreen(loaded, onBack = {}, onPay = {}, onRetry = {}) }
        }

        compose.onNodeWithTag(TAG_PAYMENTS_NOTHING_DUE).assertExists()
        compose.onNodeWithTag(TAG_PAYMENTS_PAY).assertExists()
    }

    @Test
    fun `owed now shows the server's total due, unsummed`() {
        val next =
            GuardianStateMapper.option(
                PayableDto(
                    "e-1", "Physics", "2026-11", Money.of("1000.00"), "2026-11-10",
                    totalDue = Money.of("1500.00"),
                ),
            )
        val loaded = PaymentsUiState.Loaded("Tanvir", 2026, Money.of("0.00"), emptyList(), next)
        compose.setContent {
            ShikkhokTheme { PaymentsScreen(loaded, onBack = {}, onPay = {}, onRetry = {}) }
        }

        compose.onNodeWithTag(TAG_PAYMENTS_OWED).assertExists()
        compose.onNodeWithText("৳1,500", substring = true, useUnmergedTree = true).assertExists()
        compose.onNodeWithTag(TAG_PAYMENTS_PAY).assertExists()
    }

    @Test
    fun `the mapper keeps the server's total due`() {
        val dto = PayableDto("e-1", "Physics", "2026-11", Money.of("1000.00"), null, totalDue = Money.of("1500.00"))

        assertEquals(Money.of("1500.00"), GuardianStateMapper.option(dto).totalDue)
    }

    @Test
    fun `while loading, send money is held in place and cannot be pressed`() {
        // G3: paying before the history shows what is paid is how a
        // guardian pays twice.
        var sends = 0
        compose.setContent {
            ShikkhokTheme { PaymentsScreen(PaymentsUiState.Loading, onBack = {}, onPay = { sends++ }, onRetry = {}) }
        }

        compose.onNodeWithTag(TAG_PAYMENTS_PAY).assertIsNotEnabled()
        assertEquals(0, sends)
    }
}
