package com.shikkhokplus.app.feature.auth

import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.designsystem.TAG_OTP_FIELD
import com.shikkhokplus.app.feature.auth.ui.AuthScreen
import com.shikkhokplus.app.feature.auth.ui.TAG_ERROR
import com.shikkhokplus.app.feature.auth.ui.TAG_PHONE_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_RECOVERY_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_RECOVERY_SUBMIT
import com.shikkhokplus.app.feature.auth.ui.TAG_RETRY
import com.shikkhokplus.app.feature.auth.ui.TAG_SECOND_STEP
import com.shikkhokplus.app.feature.auth.ui.TAG_SECOND_STEP_BACK
import com.shikkhokplus.app.feature.auth.ui.TAG_SECOND_STEP_ERROR
import com.shikkhokplus.app.feature.auth.ui.TAG_TOGGLE_RECOVERY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The sign-in's authenticator step, rendered [0028]. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class AuthSecondStepScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val submitted = mutableListOf<String>()
    private var toggled = 0
    private var backs = 0

    private fun render(state: AuthUiState) {
        compose.setContent {
            ShikkhokTheme {
                AuthScreen(
                    state = state,
                    onRequestCode = {},
                    onSubmitCode = {},
                    onRetry = {},
                    onChangeNumber = { backs++ },
                    onSubmitSecondStep = { submitted += it },
                    onToggleRecoveryCode = { toggled++ },
                )
            }
        }
    }

    @Test
    fun `it asks for the code from the authenticator app and sends it on the sixth digit`() {
        render(AuthUiState.SecondStep())

        compose.onNodeWithTag(TAG_SECOND_STEP).assertExists()
        compose.onNodeWithText("Enter the code from your authenticator app").assertExists()
        compose.onNodeWithTag(TAG_OTP_FIELD).performTextInput("654321")

        assertEquals(listOf("654321"), submitted)
    }

    @Test
    fun `a recovery code is offered instead, on request`() {
        render(AuthUiState.SecondStep())

        compose.onNodeWithTag(TAG_TOGGLE_RECOVERY).performScrollTo().performClick()

        assertEquals(1, toggled)
    }

    @Test
    fun `a recovery code is typed into a field and sent trimmed by Continue`() {
        render(AuthUiState.SecondStep(useRecovery = true))

        compose.onNodeWithText("Enter a recovery code").assertExists()
        compose.onNodeWithTag(TAG_RECOVERY_SUBMIT).assertIsNotEnabled()
        compose.onNodeWithTag(TAG_RECOVERY_FIELD).performTextInput("ABCDE-FGHJK ")
        compose.onNodeWithTag(TAG_RECOVERY_SUBMIT).assertIsEnabled().performClick()

        assertEquals(listOf("ABCDE-FGHJK"), submitted)
        compose.onNodeWithText("Use the authenticator app instead").assertExists()
    }

    @Test
    fun `a wrong code shows the server's words and no retry`() {
        render(AuthUiState.SecondStep(messageKey = "mfa.code_wrong"))

        compose.onNodeWithTag(TAG_SECOND_STEP_ERROR).assertExists()
        compose.onNodeWithText("That code isn't right", substring = true).assertExists()
        compose.onNodeWithTag(TAG_RETRY).assertDoesNotExist()
    }

    @Test
    fun `the lock is said in the server's words`() {
        render(AuthUiState.SecondStep(messageKey = "mfa.locked"))

        compose.onNodeWithText("Too many wrong codes. Try again in 15 minutes.").assertExists()
    }

    @Test
    fun `a lost connection offers the retry, which sends what was typed again`() {
        render(AuthUiState.SecondStep(useRecovery = true, messageKey = "error.network.unreachable", retryable = true))
        compose.onNodeWithTag(TAG_RECOVERY_FIELD).performTextInput("ABCDE-FGHJK")

        compose.onNodeWithTag(TAG_RETRY).performScrollTo().performClick()

        assertEquals(listOf("ABCDE-FGHJK"), submitted)
    }

    @Test
    fun `back returns to the number`() {
        render(AuthUiState.SecondStep())

        compose.onNodeWithTag(TAG_SECOND_STEP_BACK).performClick()

        assertEquals(1, backs)
    }

    @Test
    fun `a lapsed challenge is shown on the number step with its message`() {
        render(AuthUiState.Failed("mfa.challenge_expired", retryable = false))

        compose.onNodeWithTag(TAG_PHONE_FIELD).assertExists()
        compose.onNodeWithTag(TAG_ERROR).assertExists()
        compose.onNodeWithText("Signing in took too long. Start again with a new SMS code.").assertExists()
        compose.onNodeWithTag(TAG_RETRY).assertDoesNotExist()
    }
}
