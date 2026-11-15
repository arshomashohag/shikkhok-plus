package com.shikkhokplus.app.feature.auth

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
import com.shikkhokplus.app.core.ui.AvailabilityState
import com.shikkhokplus.app.feature.auth.ui.AuthActions
import com.shikkhokplus.app.feature.auth.ui.AuthScreen
import com.shikkhokplus.app.feature.auth.ui.TAG_ERROR
import com.shikkhokplus.app.feature.auth.ui.TAG_REPLACE_USERNAME
import com.shikkhokplus.app.feature.auth.ui.TAG_REPLACE_USERNAME_BACK
import com.shikkhokplus.app.feature.auth.ui.TAG_REPLACE_USERNAME_CONTINUE
import com.shikkhokplus.app.feature.auth.ui.TAG_REPLACE_USERNAME_FIELD
import com.shikkhokplus.app.feature.auth.ui.TAG_RETRY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * "Choose another username", rendered inside the sign-in screen [FR2.2,
 * W2; NFR3.4].
 *
 * There is no password and no code on this step: the code is in the
 * ViewModel, so after a recreation the typed name survives and Continue
 * still sends.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ReplaceUsernameStepTest {

    @get:Rule
    val compose = createComposeRule()

    private fun render(
        state: AuthUiState.ReplaceUsername,
        actions: AuthActions = AuthActions(),
        availability: AvailabilityState = AvailabilityState.Idle,
    ) {
        compose.setContent {
            ShikkhokTheme {
                AuthScreen(state = state, actions = actions, replacementAvailability = availability)
            }
        }
    }

    @Test
    fun `the step names the taken name and asks for another`() {
        render(AuthUiState.ReplaceUsername(previous = "nadia_k"))

        compose.onNodeWithTag(TAG_REPLACE_USERNAME).assertIsDisplayed()
        compose.onNodeWithText("Someone took nadia_k while you were confirming.", substring = true).assertExists()
        compose.onNodeWithTag(TAG_REPLACE_USERNAME_CONTINUE).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `Continue sends what was typed, and each edit is reported`() {
        val edited = mutableListOf<String>()
        var sent: String? = null
        render(
            AuthUiState.ReplaceUsername("nadia_k"),
            AuthActions(onReplacementEdited = { edited += it }, onSubmitReplacement = { sent = it }),
        )

        compose.onNodeWithTag(TAG_REPLACE_USERNAME_FIELD).performTextInput("nadia_k2")
        compose.onNodeWithTag(TAG_REPLACE_USERNAME_CONTINUE).performScrollTo().performClick()

        assertEquals("nadia_k2", sent)
        assertEquals("nadia_k2", edited.last())
    }

    @Test
    fun `a name refusal is shown under the field, not as a banner`() {
        render(AuthUiState.ReplaceUsername("nadia_k", messageKey = "account.username.unavailable"))

        compose.onNodeWithText("This username is not available.").assertExists()
        compose.onNodeWithTag(TAG_ERROR).assertDoesNotExist()
    }

    @Test
    fun `no answer offers a retry that resends the name`() {
        var sent: String? = null
        render(
            AuthUiState.ReplaceUsername("nadia_k", messageKey = AuthStateMapper.OFFLINE_KEY, retryable = true),
            AuthActions(onSubmitReplacement = { sent = it }),
        )
        compose.onNodeWithTag(TAG_REPLACE_USERNAME_FIELD).performTextInput("nadia_k2")

        compose.onNodeWithTag(TAG_RETRY).performScrollTo().performClick()

        assertEquals("nadia_k2", sent)
    }

    @Test
    fun `the availability hint is shown under the field`() {
        render(AuthUiState.ReplaceUsername("nadia_k"), availability = AvailabilityState.Available)

        compose.onNodeWithText("Available").assertExists()
    }

    @Test
    fun `Back goes to the code flow's start`() {
        var changed = 0
        render(AuthUiState.ReplaceUsername("nadia_k"), AuthActions(onChangeNumber = { changed++ }))

        compose.onNodeWithTag(TAG_REPLACE_USERNAME_BACK).performClick()

        assertEquals(1, changed)
    }

    @Test
    fun `after recreation the typed name survives and the step still submits`() {
        var sent: String? = null
        val restore = StateRestorationTester(compose)
        restore.setContent {
            ShikkhokTheme {
                AuthScreen(
                    state = AuthUiState.ReplaceUsername("nadia_k"),
                    actions = AuthActions(onSubmitReplacement = { sent = it }),
                )
            }
        }
        compose.onNodeWithTag(TAG_REPLACE_USERNAME_FIELD).performTextInput("nadia_k2")

        restore.emulateSavedInstanceStateRestore()

        compose.onNodeWithTag(TAG_REPLACE_USERNAME_FIELD)
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString("nadia_k2")))
        compose.onNodeWithTag(TAG_REPLACE_USERNAME_CONTINUE).performScrollTo().performClick()
        assertEquals("nadia_k2", sent)
    }
}
