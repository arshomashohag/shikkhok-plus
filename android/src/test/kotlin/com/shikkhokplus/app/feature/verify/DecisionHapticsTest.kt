package com.shikkhokplus.app.feature.verify

import androidx.activity.ComponentActivity
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import com.shikkhokplus.app.core.designsystem.FakeHaptics
import com.shikkhokplus.app.core.designsystem.LocalHaptics
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.verify.ui.PaymentReviewScreen
import com.shikkhokplus.app.feature.verify.ui.ReviewActions
import com.shikkhokplus.app.feature.verify.ui.SheetActions
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

/**
 * The review screen buzzes when a decision LANDS — not on the tap, not
 * when a decided payment is merely opened, and not when the write failed.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class DecisionHapticsTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun card(status: String) = assertNotNull(VerifyStateMapper.toCard(review(status = status)))

    private val actions =
        ReviewActions(
            onBack = {},
            onApprove = {},
            onApproveOther = {},
            onReject = {},
            onChangeDecision = {},
            onRetry = {},
            sheet =
                SheetActions(
                    onType = {},
                    onDisposition = {},
                    onChild = {},
                    onNote = {},
                    onConfirm = {},
                    onDismiss = {},
                ),
        )

    /** Render [first], then move to [then], and return what was felt. */
    private fun feel(first: ReviewUiState, then: ReviewUiState? = null): List<String> {
        val haptics = FakeHaptics()
        var state by mutableStateOf(first)
        compose.setContent {
            CompositionLocalProvider(LocalHaptics provides haptics) {
                ShikkhokTheme { PaymentReviewScreen(state = state, sheet = null, actions = actions) }
            }
        }
        compose.waitForIdle()
        if (then != null) {
            state = then
            compose.waitForIdle()
        }
        return haptics.felt
    }

    @Test
    fun `an approval the server accepted confirms`() {
        val felt =
            feel(
                ReviewUiState.Loaded(card("pending"), busy = true),
                ReviewUiState.Loaded(card("approved")),
            )
        assertEquals(listOf("confirm"), felt)
    }

    @Test
    fun `a rejection the server accepted feels like a rejection`() {
        val felt =
            feel(
                ReviewUiState.Loaded(card("pending"), busy = true),
                ReviewUiState.Loaded(card("rejected")),
            )
        assertEquals(listOf("reject"), felt)
    }

    @Test
    fun `opening a payment that was already decided is silent`() {
        assertEquals(emptyList(), feel(ReviewUiState.Loaded(card("approved"))))
    }

    @Test
    fun `a write that failed is silent`() {
        val felt =
            feel(
                ReviewUiState.Loaded(card("pending"), busy = true),
                ReviewUiState.Loaded(card("pending"), errorKey = VerifyStateMapper.OFFLINE_KEY),
            )
        assertEquals(emptyList(), felt)
    }
}
