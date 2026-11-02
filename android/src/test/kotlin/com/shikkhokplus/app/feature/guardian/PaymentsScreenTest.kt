package com.shikkhokplus.app.feature.guardian

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.guardian.ui.PaymentsScreen
import com.shikkhokplus.app.feature.guardian.ui.TAG_PAYMENTS_PAY
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
}
