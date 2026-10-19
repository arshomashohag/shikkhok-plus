package com.shikkhokplus.app.feature.auth

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.feature.auth.ui.AuthScreen
import com.shikkhokplus.app.feature.auth.ui.TAG_CODE_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_ERROR
import com.shikkhokplus.app.feature.auth.ui.TAG_PHONE_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_REQUEST_CODE
import com.shikkhokplus.app.feature.auth.ui.TAG_RETRY
import com.shikkhokplus.app.feature.auth.ui.TAG_SENDING
import com.shikkhokplus.app.feature.auth.ui.TAG_VERIFY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The OTP entry path, which `team.md` names as a Compose UI obligation.
 *
 * Run on the JVM under Robolectric rather than on a device, so the
 * screen is checked on every commit instead of once at the checkpoint.
 * The device run still happens — this is what stops a broken screen
 * reaching it.
 *
 * These assert what the screen RENDERS for a given state, which is the
 * half the mapper tests cannot see: a correct state mapped to a screen
 * that shows the wrong control is still a broken screen.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class AuthScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun render(
        state: AuthUiState,
        onRequestCode: (String) -> Unit = {},
        onSubmitCode: (String) -> Unit = {},
        onRetry: () -> Unit = {},
    ) {
        compose.setContent {
            AuthScreen(
                state = state,
                onRequestCode = onRequestCode,
                onSubmitCode = onSubmitCode,
                onRetry = onRetry,
            )
        }
    }

    @Test
    fun `the idle screen offers the phone field`() {
        render(AuthUiState.Idle)
        compose.onNodeWithTag(TAG_PHONE_FIELD).assertIsDisplayed()
        compose.onNodeWithTag(TAG_REQUEST_CODE).assertIsDisplayed()
    }

    @Test
    fun `typing a number and requesting a code passes it through`() {
        var requested: String? = null
        render(AuthUiState.Idle, onRequestCode = { requested = it })

        compose.onNodeWithTag(TAG_PHONE_FIELD).performTextInput("+8801711111111")
        compose.onNodeWithTag(TAG_REQUEST_CODE).performClick()

        // The number reaching the callback is the one TYPED. There is
        // no path by which it could come from the SIM [AC1.1.6].
        assertEquals("+8801711111111", requested)
    }

    @Test
    fun `the sending state shows progress and no field`() {
        render(AuthUiState.Sending)
        compose.onNodeWithTag(TAG_SENDING).assertIsDisplayed()
        compose.onNodeWithTag(TAG_PHONE_FIELD).assertDoesNotExist()
    }

    @Test
    fun `awaiting a code shows the code field`() {
        render(AuthUiState.AwaitingCode)
        compose.onNodeWithTag(TAG_CODE_FIELD).assertIsDisplayed()
        compose.onNodeWithTag(TAG_VERIFY).assertIsDisplayed()
    }

    @Test
    fun `submitting a code passes it through`() {
        var submitted: String? = null
        render(AuthUiState.AwaitingCode, onSubmitCode = { submitted = it })

        compose.onNodeWithTag(TAG_CODE_FIELD).performTextInput("123456")
        compose.onNodeWithTag(TAG_VERIFY).performClick()

        assertEquals("123456", submitted)
    }

    @Test
    fun `a retryable failure offers a retry button`() {
        render(AuthUiState.Failed("error.network.unreachable", retryable = true))
        compose.onNodeWithTag(TAG_ERROR).assertIsDisplayed()
        compose.onNodeWithTag(TAG_RETRY).assertIsDisplayed()
    }

    @Test
    fun `a NON-retryable failure offers NO retry button`() {
        // THE ONE THAT MATTERS ON THIS SCREEN. A ceiling breach is not
        // retryable, and retrying into a cost ceiling is exactly what
        // the ceiling exists to prevent. If the button appeared anyway,
        // a user tapping it would spend money the server just refused.
        render(
            AuthUiState.Failed(
                "auth.otp.temporarily_unavailable",
                retryable = false,
            ),
        )
        compose.onNodeWithTag(TAG_ERROR).assertIsDisplayed()
        compose.onNodeWithTag(TAG_RETRY).assertDoesNotExist()
    }

    @Test
    fun `the retry button calls back only when tapped`() {
        var retried = 0
        render(
            AuthUiState.Failed("error.network.unreachable", retryable = true),
            onRetry = { retried++ },
        )
        assertEquals(0, retried, "rendering must not trigger a retry")

        compose.onNodeWithTag(TAG_RETRY).performClick()
        assertEquals(1, retried)
    }

    @Test
    fun `a failure keeps the phone field available to correct and resend`() {
        // The failure block renders BESIDE the entry field rather than
        // replacing the screen, so a user whose send failed can try
        // again without navigating back.
        render(AuthUiState.Failed("error.network.unreachable", retryable = true))
        compose.onNodeWithTag(TAG_PHONE_FIELD).assertIsDisplayed()
    }
}
