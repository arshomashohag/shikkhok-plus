package com.shikkhokplus.app.feature.auth

import androidx.compose.ui.test.assertIsDisplayed
import com.shikkhokplus.app.feature.auth.ui.TAG_RESEND_CODE
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.core.designsystem.TAG_BRAND_HERO
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.auth.ui.AuthScreen
import com.shikkhokplus.app.core.designsystem.TAG_OTP_FIELD as TAG_CODE_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_ERROR
import com.shikkhokplus.app.feature.auth.ui.TAG_GO_TO_SIGNUP
import com.shikkhokplus.app.feature.auth.ui.TAG_NO_CODE_SIGNUP
import com.shikkhokplus.app.feature.auth.ui.AuthActions
import com.shikkhokplus.app.feature.auth.ui.TAG_CHOOSE_PASSWORD
import com.shikkhokplus.app.feature.auth.ui.TAG_SETUP_BACK
import com.shikkhokplus.app.feature.auth.ui.TAG_SETUP_CHECKING
import com.shikkhokplus.app.feature.auth.ui.TAG_SETUP_SECOND_CODE
import com.shikkhokplus.app.feature.auth.ui.TAG_SETUP_SUBMIT
import com.shikkhokplus.app.core.ui.TAG_CONFIRM_PASSWORD
import com.shikkhokplus.app.core.ui.TAG_NEW_PASSWORD
import com.shikkhokplus.app.feature.auth.ui.TAG_CODE_REQUEST
import com.shikkhokplus.app.feature.auth.ui.TAG_CODE_REQUEST_BACK
import com.shikkhokplus.app.feature.auth.ui.TAG_FIRST_PASSWORD
import com.shikkhokplus.app.feature.auth.ui.TAG_FORGOT_PASSWORD
import com.shikkhokplus.app.feature.auth.ui.TAG_HINT_GET_CODE
import com.shikkhokplus.app.feature.auth.ui.TAG_IDENTIFIER_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_PASSWORD_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_SIGNING_IN
import com.shikkhokplus.app.feature.auth.ui.TAG_SIGN_IN
import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.ui.TAG_KIND_EMAIL
import com.shikkhokplus.app.core.ui.TAG_KIND_PHONE
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
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
        actions: AuthActions = AuthActions(),
        codeDestination: IdentifierKind = IdentifierKind.PHONE,
    ) {
        compose.setContent {
            // The screen reads MaterialTheme colours for its branding
            // hero, so it must render inside the theme.
            ShikkhokTheme {
                AuthScreen(state = state, actions = actions, codeDestination = codeDestination)
            }
        }
    }

    // --- The password sign-in ---------------------------------------------

    @Test
    fun `the sign-in form offers phone or email and a password`() {
        render(AuthUiState.Idle)
        compose.onNodeWithTag(TAG_KIND_PHONE).assertIsDisplayed()
        compose.onNodeWithTag(TAG_KIND_EMAIL).assertIsDisplayed()
        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).assertIsDisplayed()
        compose.onNodeWithTag(TAG_PASSWORD_FIELD).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_SIGN_IN).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `typing a number and a password signs in with exactly what was typed`() {
        var signedIn: Pair<Identifier, String>? = null
        render(AuthUiState.Idle, AuthActions(onSignIn = { id, pw -> signedIn = id to pw }))

        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).performTextInput("+8801711111111")
        compose.onNodeWithTag(TAG_PASSWORD_FIELD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_SIGN_IN).performScrollTo().performClick()

        // The number reaching the callback is the one TYPED. There is
        // no path by which it could come from the SIM [AC1.1.6].
        assertEquals(Identifier.phone("+8801711111111") to "correct horse", signedIn)
    }

    @Test
    fun `switching to email signs in with an email`() {
        var signedIn: Pair<Identifier, String>? = null
        render(AuthUiState.Idle, AuthActions(onSignIn = { id, pw -> signedIn = id to pw }))

        compose.onNodeWithTag(TAG_KIND_EMAIL).performClick()
        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).performTextInput("rafi@example.com")
        compose.onNodeWithTag(TAG_PASSWORD_FIELD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_SIGN_IN).performScrollTo().performClick()

        assertEquals(Identifier.email("rafi@example.com") to "correct horse", signedIn)
    }

    @Test
    fun `the password is masked`() {
        render(AuthUiState.Idle)

        compose.onNodeWithTag(TAG_PASSWORD_FIELD).performScrollTo().assert(
            SemanticsMatcher.keyIsDefined(SemanticsProperties.Password),
        )
    }

    @Test
    fun `a malformed number is named under the field and not sent`() {
        var signedIn: Pair<Identifier, String>? = null
        render(AuthUiState.Idle, AuthActions(onSignIn = { id, pw -> signedIn = id to pw }))

        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).performTextInput("0171")
        compose.onNodeWithTag(TAG_PASSWORD_FIELD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_SIGN_IN).performScrollTo().performClick()

        assertEquals(null, signedIn)
        compose.onNodeWithText("Bangladeshi mobile numbers have 11 digits, starting 01.").assertExists()
    }

    @Test
    fun `sign in waits for both fields`() {
        render(AuthUiState.Idle)
        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).performTextInput("01711111111")

        compose.onNodeWithTag(TAG_SIGN_IN).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `signing in shows progress over a form that cannot be sent twice`() {
        render(AuthUiState.SigningIn)
        compose.onNodeWithTag(TAG_SIGNING_IN).assertIsDisplayed()
        compose.onNodeWithTag(TAG_SIGN_IN).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `a wrong password shows the hint that leads to the code flow`() {
        var opened = 0
        render(
            AuthUiState.Failed("auth.password.wrong", retryable = false, offerCodeFlow = true),
            AuthActions(onStartCodeFlow = { opened++ }),
        )

        compose.onNodeWithText("That phone or email and password don't match.").assertExists()
        compose
            .onNodeWithText("First time signing in with a password, or forgot it? Get a code.")
            .assertExists()
        compose.onNodeWithTag(TAG_HINT_GET_CODE).performScrollTo().performClick()
        assertEquals(1, opened)
    }

    @Test
    fun `a failure the mapper did not mark shows no code-flow hint`() {
        render(AuthUiState.Failed("error.network.unreachable", retryable = true))
        compose.onNodeWithTag(TAG_HINT_GET_CODE).assertDoesNotExist()
    }

    @Test
    fun `forgot password and first password both open the code flow`() {
        var opened = 0
        render(AuthUiState.Idle, AuthActions(onStartCodeFlow = { opened++ }))

        compose.onNodeWithTag(TAG_FORGOT_PASSWORD).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_FIRST_PASSWORD).performScrollTo().performClick()

        assertEquals(2, opened)
    }

    // --- The code flow ---------------------------------------------------------

    @Test
    fun `the code flow asks where to send the code`() {
        render(AuthUiState.CodeFlowStart)
        compose.onNodeWithTag(TAG_CODE_REQUEST).assertIsDisplayed()
        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).assertIsDisplayed()
        compose.onNodeWithTag(TAG_REQUEST_CODE).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `typing a number and requesting a code passes it through`() {
        var requested: Identifier? = null
        render(AuthUiState.CodeFlowStart, AuthActions(onRequestCode = { requested = it }))

        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).performTextInput("+8801711111111")
        compose.onNodeWithTag(TAG_REQUEST_CODE).performScrollTo().performClick()

        assertEquals(Identifier.phone("+8801711111111"), requested)
    }

    @Test
    fun `a malformed email is named under the field and not sent`() {
        var requested: Identifier? = null
        render(AuthUiState.CodeFlowStart, AuthActions(onRequestCode = { requested = it }))

        compose.onNodeWithTag(TAG_KIND_EMAIL).performClick()
        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).performTextInput("rafi.example.com")
        compose.onNodeWithTag(TAG_REQUEST_CODE).performScrollTo().performClick()

        assertEquals(null, requested)
        compose.onNodeWithText("Enter an email address, like name@example.com.").assertExists()
    }

    @Test
    fun `the sending state shows progress over a form that cannot resend`() {
        // O2's loading board keeps the form on screen beneath the
        // progress, and "Send code" cannot be pressed a second time.
        render(AuthUiState.Sending)
        compose.onNodeWithTag(TAG_SENDING).assertIsDisplayed()
        compose.onNodeWithTag(TAG_REQUEST_CODE).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `back from the code flow returns to the sign-in form`() {
        var back = 0
        render(AuthUiState.CodeFlowStart, AuthActions(onBackToSignIn = { back++ }))

        compose.onNodeWithTag(TAG_CODE_REQUEST_BACK).performClick()

        assertEquals(1, back)
    }

    @Test
    fun `a wrong code shows the tries the server says are left`() {
        render(AuthUiState.CodeRejected("auth.otp.wrong", retryable = false, attemptsLeft = "3"))
        compose.onNodeWithText("That code isn't right. 3 tries left.").assertExists()
    }

    @Test
    fun `an expired code says so and offers a new one`() {
        var resent = 0
        render(
            AuthUiState.CodeRejected("auth.otp.expired", retryable = false),
            AuthActions(onResendCode = { resent++ }),
        )
        compose.onNodeWithText("This code has expired").assertExists()
        compose.onNodeWithTag(TAG_RESEND_CODE).performScrollTo().performClick()
        assertEquals(1, resent)
    }

    @Test
    fun `the code step never repeats the number back`() {
        render(AuthUiState.AwaitingCode)
        compose
            .onNodeWithText("If this number has an account, we sent it a 6-digit code by SMS.")
            .assertExists()
    }

    @Test
    fun `a code sent by email says so, still without naming the address`() {
        render(AuthUiState.AwaitingCode, codeDestination = IdentifierKind.EMAIL)
        compose.onNodeWithText("If this email has an account, we sent it a 6-digit code.").assertExists()
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
        render(AuthUiState.AwaitingCode, AuthActions(onSubmitCode = { submitted = it }))

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
        render(AuthUiState.AwaitingCode, AuthActions(onSubmitCode = { submitted = it }))

        compose.onNodeWithTag(TAG_CODE_FIELD).performTextInput("12345")

        assertEquals(null, submitted)
    }

    @Test
    fun `a retryable failure offers a retry button`() {
        render(AuthUiState.Failed("error.network.unreachable", retryable = true))
        compose.onNodeWithTag(TAG_ERROR).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_RETRY).performScrollTo().assertIsDisplayed()
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
        compose.onNodeWithTag(TAG_ERROR).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_RETRY).assertDoesNotExist()
    }

    @Test
    fun `the retry button calls back only when tapped`() {
        var retried = 0
        render(
            AuthUiState.Failed("error.network.unreachable", retryable = true),
            AuthActions(onRetry = { retried++ }),
        )
        assertEquals(0, retried, "rendering must not trigger a retry")

        compose.onNodeWithTag(TAG_RETRY).performScrollTo().performClick()
        assertEquals(1, retried)
    }

    @Test
    fun `a failure keeps the identifier field available to correct and resend`() {
        // The failure block renders BESIDE the entry field rather than
        // replacing the screen, so a user whose send failed can try
        // again without navigating back.
        render(AuthUiState.Failed("error.network.unreachable", retryable = true, step = AuthStep.CODE_REQUEST))
        compose.onNodeWithTag(TAG_CODE_REQUEST).assertIsDisplayed()
        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).assertIsDisplayed()
    }

    @Test
    fun `the sign-in form offers a way to register`() {
        // **The dead end this closes.** The code-sent copy says a code
        // is on its way "if this number is registered", which is
        // literally true and told a person whose teacher had not
        // recorded them nothing they could act on. SignupScreen shipped
        // in D1 and no route reached it, so the honest answer to "how
        // do I register?" was that you could not.
        render(AuthUiState.Idle)
        compose.onNodeWithTag(TAG_GO_TO_SIGNUP).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `the register link calls back only when tapped`() {
        var opened = 0
        render(AuthUiState.Idle, AuthActions(onGoToSignup = { opened++ }))
        assertEquals(0, opened, "rendering must not navigate")

        compose.onNodeWithTag(TAG_GO_TO_SIGNUP).performScrollTo().performClick()
        assertEquals(1, opened)
    }

    @Test
    fun `the code screen tells a new person to create an account`() {
        // **Reported from a device.** A student a teacher had added
        // pressed Sign in rather than Sign up, and this screen was
        // where they were left. The server answers every number the
        // same way, so reaching it says nothing about whether the
        // number is registered -- and an unregistered number is now
        // sent no code at all. The way out has to be on this screen.
        var opened = 0
        render(AuthUiState.AwaitingCode, AuthActions(onGoToSignup = { opened++ }))

        compose.onNodeWithTag(TAG_NO_CODE_SIGNUP).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_NO_CODE_SIGNUP).performClick()
        assertEquals(1, opened)
    }

    @Test
    fun `a rejected code still offers the way to create an account`() {
        render(AuthUiState.CodeRejected("auth.otp.not_valid", retryable = false))
        compose.onNodeWithTag(TAG_NO_CODE_SIGNUP).performScrollTo().assertIsDisplayed()
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
        // With a password field the form no longer fits 414dp without
        // scrolling, so the assertion is that each control can be
        // REACHED: the column scrolls rather than squeezing a band away.
        render(AuthUiState.Idle)

        compose.onNodeWithTag(TAG_BRAND_HERO).assertIsDisplayed()
        compose.onNodeWithTag(TAG_IDENTIFIER_FIELD).assertIsDisplayed()
        compose.onNodeWithTag(TAG_PASSWORD_FIELD).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_SIGN_IN).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_GO_TO_SIGNUP).performScrollTo().assertIsDisplayed()
    }

    // --- Choosing a password ---------------------------------------------------

    @Test
    fun `a verified code asks for a password twice, and sends both as typed`() {
        var sent: Triple<String, String, String>? = null
        render(AuthUiState.ChoosePassword(), AuthActions(onChoosePassword = { a, b, c -> sent = Triple(a, b, c) }))

        compose.onNodeWithTag(TAG_CHOOSE_PASSWORD).assertIsDisplayed()
        compose.onNodeWithTag(TAG_SETUP_SECOND_CODE).assertDoesNotExist()
        compose.onNodeWithTag(TAG_NEW_PASSWORD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_CONFIRM_PASSWORD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_SETUP_SUBMIT).performScrollTo().performClick()

        assertEquals(Triple("correct horse", "correct horse", ""), sent)
    }

    @Test
    fun `an account with two-step verification is asked for its app code too`() {
        var sent: Triple<String, String, String>? = null
        render(
            AuthUiState.ChoosePassword(mfaRequired = true),
            AuthActions(onChoosePassword = { a, b, c -> sent = Triple(a, b, c) }),
        )

        compose.onNodeWithTag(TAG_NEW_PASSWORD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_CONFIRM_PASSWORD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_SETUP_SUBMIT).performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag(TAG_SETUP_SECOND_CODE).performScrollTo().performTextInput("654321")
        compose.onNodeWithTag(TAG_SETUP_SUBMIT).performScrollTo().performClick()

        assertEquals(Triple("correct horse", "correct horse", "654321"), sent)
    }

    @Test
    fun `a password refusal is said, and a retry offered only when the server allows`() {
        render(AuthUiState.ChoosePassword(messageKey = "auth.password.too_common"))
        compose
            .onNodeWithText("That password is too common. Choose one that is harder to guess.")
            .performScrollTo()
            .assertIsDisplayed()
        compose.onNodeWithTag(TAG_RETRY).assertDoesNotExist()
    }

    @Test
    fun `saving the password shows progress over the form`() {
        render(AuthUiState.ChoosePassword(checking = true))
        compose.onNodeWithTag(TAG_SETUP_CHECKING).assertIsDisplayed()
        compose.onNodeWithTag(TAG_SETUP_SUBMIT).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `back from choosing a password returns to the code flow`() {
        var back = 0
        render(AuthUiState.ChoosePassword(), AuthActions(onChangeNumber = { back++ }))

        compose.onNodeWithTag(TAG_SETUP_BACK).performClick()

        assertEquals(1, back)
    }

    @Test
    fun `an email the server refuses is named under the email field, not as a banner`() {
        render(AuthUiState.Failed("email.invalid", retryable = false, step = AuthStep.CODE_REQUEST))
        compose.onNodeWithTag(TAG_KIND_EMAIL).performClick()

        compose.onNodeWithText("Enter an email address, like name@example.com.").assertExists()
        compose.onNodeWithTag(TAG_ERROR).assertDoesNotExist()
    }
}
