package com.shikkhokplus.app.feature.auth

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.feature.auth.ui.SignupScreen
import com.shikkhokplus.app.feature.auth.ui.TAG_SIGNUP_NAME
import com.shikkhokplus.app.feature.auth.ui.TAG_SIGNUP_PHONE
import com.shikkhokplus.app.feature.auth.ui.TAG_SIGNUP_SUBMIT
import com.shikkhokplus.app.feature.auth.ui.TAG_SIGNUP_SUBMITTING
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * `O1` signup, rendered.
 *
 * The mapper tests prove the right state is produced; these prove the
 * right screen is shown for it. A correct state rendered as the wrong
 * control is still a broken screen, and that half is invisible to a
 * mapper test.
 *
 * Two of this unit's rules are assertable only here, because they are
 * about what the screen does NOT show:
 *
 * * the already-added notice names neither teacher nor batch
 *   [BR2.3, AC1.12.2];
 * * the role is locked rather than hidden [BR4.5, AC1.12.1].
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class SignupScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun render(
        state: SignupUiState,
        onSubmit: (String, String, String, SignupRole) -> Unit = { _, _, _, _ -> },
        onGoToLogin: () -> Unit = {},
        onRetry: () -> Unit = {},
    ) {
        compose.setContent {
            SignupScreen(
                state = state,
                onSubmit = onSubmit,
                onGoToLogin = onGoToLogin,
                onRetry = onRetry,
            )
        }
    }

    @Test
    fun `the empty form offers every role`() {
        render(SignupUiState.Empty)

        compose.onNodeWithText("Teacher").assertIsEnabled()
        compose.onNodeWithText("Student").assertIsEnabled()
        compose.onNodeWithText("Guardian").assertIsEnabled()
    }

    @Test
    fun `an already-added number locks the role rather than hiding it`() {
        render(
            SignupUiState.AlreadyAdded(
                prefilledName = "Rahim",
                lockedRole = SignupRole.STUDENT,
            ),
        )

        // Present, so the person can see which role the seat carries —
        // asserted as existence rather than display, because the
        // already-added notice can push the chips below the fold on a
        // short viewport and that is a layout fact, not the rule.
        compose.onNodeWithText("Student").assertExists()
        // Not changeable, which IS the rule [BR4.5]: locked, not hidden.
        compose.onNodeWithText("Student").assertIsNotEnabled()
        compose.onNodeWithText("Teacher").assertIsNotEnabled()
    }

    @Test
    fun `an already-added number names neither the teacher nor the batch`() {
        render(
            SignupUiState.AlreadyAdded(
                prefilledName = "Rahim",
                lockedRole = SignupRole.STUDENT,
            ),
        )

        // The notice says a teacher added this number and stops there
        // [AC1.12.2]. The state holds no teacher and no batch, so this
        // asserts the screen invented neither.
        compose
            .onAllNodesWithText("Ms", substring = true)
            .fetchSemanticsNodes()
            .let { assertEquals(0, it.size) }
        compose
            .onAllNodesWithText("batch", substring = true, ignoreCase = true)
            .fetchSemanticsNodes()
            .let { assertEquals(0, it.size) }
    }

    @Test
    fun `the prefilled name is shown and correctable`() {
        render(
            SignupUiState.AlreadyAdded(
                prefilledName = "Rahim",
                lockedRole = SignupRole.STUDENT,
            ),
        )

        // Scrolled to: the board puts the notice, the role cards and the
        // number above the name, which a short test viewport cannot fit.
        compose.onNodeWithText("Rahim").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("Rahim").assertIsEnabled()
    }

    @Test
    fun `the code-sent state never repeats the number back`() {
        render(SignupUiState.CodeSent(codeSentTo = "01712345678"))

        compose.onNodeWithText("We sent a code to your number.").assertExists()
        compose
            .onAllNodesWithText("01712345678", substring = true)
            .fetchSemanticsNodes()
            .let { assertEquals(0, it.size) }
    }

    @Test
    fun `an already-registered number offers a way to log in`() {
        var wentToLogin = false
        render(
            SignupUiState.Failed(
                messageKey = "signup.number.already_registered",
                retryable = false,
            ),
            onGoToLogin = { wentToLogin = true },
        )

        // Under the number, beside the refusal (O1's error board).
        compose.onNodeWithText("This number already has an account.").assertExists()
        compose.onNodeWithText("Log in").performScrollTo().performClick()
        assertEquals(true, wentToLogin)
    }

    @Test
    fun `a non-retryable failure offers no retry`() {
        render(
            SignupUiState.Failed(
                messageKey = "signup.number.already_registered",
                retryable = false,
            ),
        )

        compose
            .onAllNodesWithText("Try again", substring = true)
            .fetchSemanticsNodes()
            .let { assertEquals(0, it.size) }
    }

    @Test
    fun `a refused number keeps the form and says so under the field`() {
        // **Reported from a device: the whole form went blank.** A
        // refusal of the number replaced the form with an error, so the
        // person lost what they had typed to learn one field was wrong.
        render(
            SignupUiState.Failed(
                messageKey = "phone.invalid",
                retryable = false,
            ),
        )

        compose.onNodeWithTag(TAG_SIGNUP_PHONE).assertExists()
        compose.onNodeWithTag(TAG_SIGNUP_SUBMIT).assertExists()
        compose
            .onNodeWithText("Enter an 11-digit mobile number, like 01711-234567")
            .assertExists()
    }

    @Test
    fun `a submit-time check names the number under its field`() {
        render(SignupUiState.Invalid(listOf("signup.phone.invalid")))

        compose.onNodeWithTag(TAG_SIGNUP_SUBMIT).assertExists()
        compose
            .onNodeWithText("Enter an 11-digit mobile number, like 01711-234567")
            .assertExists()
    }

    @Test
    fun `a retryable failure offers a retry the server permitted`() {
        var retried = false
        render(
            SignupUiState.Failed(
                messageKey = "error.network.unreachable",
                retryable = true,
            ),
            onRetry = { retried = true },
        )

        compose.onNodeWithText("Try again", substring = true).performClick()
        assertEquals(true, retried)
    }

    @Test
    fun `submitting shows progress over a form that cannot resubmit`() {
        render(SignupUiState.Submitting)

        compose.onNodeWithTag(TAG_SIGNUP_SUBMITTING).assertIsDisplayed()
        compose.onNodeWithTag(TAG_SIGNUP_SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `no role is chosen for the person, so the form cannot be sent yet`() {
        render(SignupUiState.Empty)
        compose.onNodeWithTag(TAG_SIGNUP_NAME).performTextInput("Rahim")
        compose.onNodeWithTag(TAG_SIGNUP_PHONE).performTextInput("01711-234567")

        compose.onNodeWithTag(TAG_SIGNUP_SUBMIT).assertIsNotEnabled()

        compose.onNodeWithText("Teacher").performClick()
        compose.onNodeWithTag(TAG_SIGNUP_SUBMIT).performScrollTo().assertIsEnabled()
    }

    @Test
    fun `the chosen role is what is submitted`() {
        var submitted: SignupRole? = null
        render(SignupUiState.Empty, onSubmit = { _, _, _, role -> submitted = role })
        compose.onNodeWithText("Guardian").performClick()
        compose.onNodeWithTag(TAG_SIGNUP_NAME).performTextInput("Rokshana")
        compose.onNodeWithTag(TAG_SIGNUP_PHONE).performTextInput("01819-552041")
        compose.onNodeWithTag(TAG_SIGNUP_SUBMIT).performScrollTo().performClick()

        assertEquals(SignupRole.GUARDIAN, submitted)
    }
}
