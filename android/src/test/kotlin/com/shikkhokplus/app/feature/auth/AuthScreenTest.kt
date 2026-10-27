package com.shikkhokplus.app.feature.auth

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.core.designsystem.TAG_BRAND_HERO
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.auth.ui.AuthScreen
import com.shikkhokplus.app.core.designsystem.TAG_OTP_FIELD as TAG_CODE_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_ERROR
import com.shikkhokplus.app.feature.auth.ui.TAG_GO_TO_SIGNUP
import com.shikkhokplus.app.feature.auth.ui.TAG_PHONE_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_REQUEST_CODE
import com.shikkhokplus.app.feature.auth.ui.TAG_RETRY
import com.shikkhokplus.app.feature.auth.ui.TAG_SENDING
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
        onGoToSignup: () -> Unit = {},
    ) {
        compose.setContent {
            // The screen now reads MaterialTheme colours for its
            // branding hero, so it must render inside the theme.
            ShikkhokTheme {
            AuthScreen(
                state = state,
                onRequestCode = onRequestCode,
                onSubmitCode = onSubmitCode,
                onRetry = onRetry,
                onGoToSignup = onGoToSignup,
            )
            }
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
    }

    @Test
    fun `the sixth digit submits the code with no button press`() {
        // **Stronger than the assertion it replaces.** The old test
        // typed six digits and clicked a Verify button, which proved
        // the button was wired. This proves the behaviour the design
        // actually specifies: the check fires on the sixth digit and
        // there is no button to press. A regression that reintroduced
        // a required tap would fail here, where before it would have
        // passed.
        var submitted: String? = null
        render(AuthUiState.AwaitingCode, onSubmitCode = { submitted = it })

        compose.onNodeWithTag(TAG_CODE_FIELD).performTextInput("123456")

        assertEquals("123456", submitted)
    }

    @Test
    fun `five digits do not submit`() {
        // The other half of the same rule, and the half that catches a
        // formatter which fired on every keystroke: an incomplete code
        // must not be sent, or the server counts failed attempts
        // against a user who is still typing — and five of those burn
        // the attempt ceiling [BR2.3].
        var submitted: String? = null
        render(AuthUiState.AwaitingCode, onSubmitCode = { submitted = it })

        compose.onNodeWithTag(TAG_CODE_FIELD).performTextInput("12345")

        assertEquals(null, submitted)
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

    @Test
    fun `the phone screen offers a way to register`() {
        // **The dead end this closes.** The code-sent copy says a code
        // is on its way "if this number is registered", which is
        // literally true and told a person whose teacher had not
        // recorded them nothing they could act on. SignupScreen shipped
        // in D1 and no route reached it, so the honest answer to "how
        // do I register?" was that you could not.
        render(AuthUiState.Idle)
        compose.onNodeWithTag(TAG_GO_TO_SIGNUP).assertIsDisplayed()
    }

    @Test
    fun `the register link calls back only when tapped`() {
        var opened = 0
        render(AuthUiState.Idle, onGoToSignup = { opened++ })
        assertEquals(0, opened, "rendering must not navigate")

        compose.onNodeWithTag(TAG_GO_TO_SIGNUP).performClick()
        assertEquals(1, opened)
    }

    @Test
    fun `the register link is absent once a code has been sent`() {
        // Registering mid-verification would abandon a code already
        // sent, and the person at this point has a number the server
        // accepted -- so the path out is the code, not a new account.
        render(AuthUiState.AwaitingCode)
        compose.onNodeWithTag(TAG_GO_TO_SIGNUP).assertDoesNotExist()
    }

    @Test
    fun `the branding hero is shown`() {
        // `O2` opens with a blue band carrying the mark, the wordmark
        // and a tagline. The app went straight into a text field, so
        // nothing said what it was before asking for a phone number.
        render(AuthUiState.Idle)
        compose.onNodeWithTag(TAG_BRAND_HERO).assertIsDisplayed()
    }

    @Test
    fun `every control stays reachable on a short screen`() {
        // **The regression this file already caught once.** These
        // tests render at 320x414dp, and the tall hero alone takes
        // 260 of it — a fixed hero plus a weighted body plus a pinned
        // action bar collapsed the middle band to 6px and scrolled
        // the number field out of a window too small to show it.
        //
        // Asserted together rather than in three tests because the
        // failure is their RELATIONSHIP: any one of them can be
        // visible while another is pushed off.
        render(AuthUiState.Idle)

        compose.onNodeWithTag(TAG_BRAND_HERO).assertIsDisplayed()
        compose.onNodeWithTag(TAG_PHONE_FIELD).assertIsDisplayed()
        compose.onNodeWithTag(TAG_REQUEST_CODE).assertIsDisplayed()
        compose.onNodeWithTag(TAG_GO_TO_SIGNUP).assertIsDisplayed()
    }
}
