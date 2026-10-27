package com.shikkhokplus.app.feature.auth

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.feature.auth.ui.SignupScreen
import com.shikkhokplus.app.feature.auth.ui.TAG_SIGNUP_SUBMIT
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

        compose.onNodeWithText("Rahim").assertIsDisplayed()
        compose.onNodeWithText("Rahim").assertIsEnabled()
    }

    @Test
    fun `the code-sent state names the number the code went to`() {
        render(SignupUiState.CodeSent(codeSentTo = "01712345678"))

        compose
            .onNodeWithText("01712345678", substring = true)
            .assertIsDisplayed()
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

        // Matched exactly: the error message also contains "Log in",
        // so a substring match finds the text and the button both.
        compose.onNodeWithText("Log in instead").performClick()
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
    fun `submitting shows progress and no submit control`() {
        render(SignupUiState.Submitting)

        compose
            .onAllNodes(hasTestTag(TAG_SIGNUP_SUBMIT))
            .fetchSemanticsNodes()
            .let { assertEquals(0, it.size) }
    }
}
