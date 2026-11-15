package com.shikkhokplus.app.feature.account

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.StateRestorationTester
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.text.AnnotatedString
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.designsystem.TAG_SCAFFOLD_BACK
import com.shikkhokplus.app.core.ui.AvailabilityState
import com.shikkhokplus.app.feature.account.ui.ChooseUsernameGate
import com.shikkhokplus.app.feature.account.ui.TAG_CHOOSE_USERNAME_BUSY
import com.shikkhokplus.app.feature.account.ui.TAG_CHOOSE_USERNAME_CONTINUE
import com.shikkhokplus.app.feature.account.ui.TAG_CHOOSE_USERNAME_ERROR
import com.shikkhokplus.app.feature.account.ui.TAG_CHOOSE_USERNAME_FIELD
import com.shikkhokplus.app.feature.account.ui.TAG_CHOOSE_USERNAME_GATE
import com.shikkhokplus.app.feature.account.ui.TAG_CHOOSE_USERNAME_RETRY
import com.shikkhokplus.app.feature.account.ui.TAG_CHOOSE_USERNAME_SIGN_OUT
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The choose-username gate, rendered [FR5.2, W4]: a root screen with no
 * back arrow, Continue, Sign out, and the typed name surviving a
 * recreation.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ChooseUsernameGateTest {

    @get:Rule
    val compose = createComposeRule()

    private class Calls {
        val submitted = mutableListOf<String>()
        var retries = 0
        var signOuts = 0
    }

    private fun render(
        state: ChooseUsernameUiState,
        calls: Calls = Calls(),
        hint: AvailabilityState = AvailabilityState.Idle,
    ) {
        compose.setContent {
            ShikkhokTheme {
                ChooseUsernameGate(
                    state = state,
                    availability = hint,
                    onEdited = {},
                    onSubmit = { calls.submitted += it },
                    onRetry = { calls.retries++ },
                    onSignOut = { calls.signOuts++ },
                )
            }
        }
    }

    @Test
    fun `the gate renders with no back arrow, and Continue waits for a name`() {
        render(ChooseUsernameUiState.Editing())

        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_GATE).assertIsDisplayed()
        compose.onNodeWithText("Choose your username").assertIsDisplayed()
        compose.onNodeWithTag(TAG_SCAFFOLD_BACK).assertDoesNotExist()
        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_CONTINUE).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `Continue sends the name typed, and Sign out signs out`() {
        val calls = Calls()
        render(ChooseUsernameUiState.Editing(), calls)

        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_FIELD).performTextInput("nadia_k")
        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_CONTINUE).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_SIGN_OUT).performScrollTo().performClick()

        assertEquals(listOf("nadia_k"), calls.submitted)
        assertEquals(1, calls.signOuts)
    }

    @Test
    fun `a name refusal is under the field, a failure is a banner with a retry`() {
        val calls = Calls()
        render(ChooseUsernameUiState.Editing(messageKey = "error.network.unreachable", retryable = true), calls)

        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_ERROR).assertExists()
        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_RETRY).performScrollTo().performClick()

        assertEquals(1, calls.retries)
    }

    @Test
    fun `a taken name is said under the field, not as a banner`() {
        render(ChooseUsernameUiState.Editing(messageKey = "account.username.unavailable"))

        compose.onNodeWithText("This username is not available.").assertExists()
        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_ERROR).assertDoesNotExist()
    }

    @Test
    fun `saving and re-reading show the loader`() {
        render(ChooseUsernameUiState.Rereading)

        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_BUSY).assertExists()
    }

    @Test
    fun `the typed name survives a recreation`() {
        val restore = StateRestorationTester(compose)
        restore.setContent {
            ShikkhokTheme {
                ChooseUsernameGate(ChooseUsernameUiState.Editing(), AvailabilityState.Idle, {}, {}, {}, {})
            }
        }
        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_FIELD).performTextInput("nadia_k")

        restore.emulateSavedInstanceStateRestore()

        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_FIELD)
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString("nadia_k")))
    }
}
