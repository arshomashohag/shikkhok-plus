package com.shikkhokplus.app.feature.account

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
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
import com.shikkhokplus.app.feature.account.ui.TAG_USERNAME_CHANGE
import com.shikkhokplus.app.feature.account.ui.TAG_USERNAME_CHANGED
import com.shikkhokplus.app.feature.account.ui.TAG_USERNAME_CURRENT
import com.shikkhokplus.app.feature.account.ui.TAG_USERNAME_NEW
import com.shikkhokplus.app.feature.account.ui.TAG_USERNAME_PASSWORD
import com.shikkhokplus.app.feature.account.ui.TAG_USERNAME_SAVE
import com.shikkhokplus.app.feature.account.ui.TAG_USERNAME_SET_PASSWORD
import com.shikkhokplus.app.feature.account.ui.UsernameActions
import com.shikkhokplus.app.feature.account.ui.UsernameScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The Username screen, rendered [W5; NFR3.4, NFR3.11].
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class UsernameScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun render(state: UsernameUiState, actions: UsernameActions = UsernameActions()) {
        compose.setContent {
            ShikkhokTheme { UsernameScreen(state = state, availability = AvailabilityState.Idle, actions = actions) }
        }
    }

    @Test
    fun `the stored name is shown, and Change is there with no date known`() {
        var changes = 0
        render(UsernameUiState.Viewing("Nadia_K"), UsernameActions(onChange = { changes++ }))

        compose.onNodeWithText("Nadia_K").assertIsDisplayed()
        compose.onNodeWithTag(TAG_USERNAME_CHANGE).performScrollTo().performClick()

        assertEquals(1, changes)
    }

    @Test
    fun `no name yet reads Choose a username`() {
        render(UsernameUiState.Viewing(null))

        compose.onNodeWithTag(TAG_USERNAME_CURRENT).assert(
            SemanticsMatcher.expectValue(SemanticsProperties.Text, listOf(AnnotatedString("Choose a username"))),
        )
    }

    @Test
    fun `a changed name says so, with or without the next date`() {
        render(UsernameUiState.Changed("Nadia.K", null))

        compose.onNodeWithTag(TAG_USERNAME_CHANGED).assertExists()
        compose.onNodeWithText("Changed.").assertExists()
    }

    @Test
    fun `Save sends the new name and the password as typed`() {
        var sent: Pair<String, String>? = null
        render(UsernameUiState.Editing("nadia_k"), UsernameActions(onSave = { u, p -> sent = u to p }))

        compose.onNodeWithTag(TAG_USERNAME_NEW).performTextInput("Nadia.K")
        compose.onNodeWithTag(TAG_USERNAME_PASSWORD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_USERNAME_SAVE).performScrollTo().performClick()

        assertEquals("Nadia.K" to "correct horse", sent)
    }

    @Test
    fun `no password yet offers setting one`() {
        var opened = 0
        render(
            UsernameUiState.Editing(
                "nadia_k",
                bannerKey = "account.username.password_required",
                offerSetPassword = true,
            ),
            UsernameActions(onSetPassword = { opened++ }),
        )

        compose.onNodeWithTag(TAG_USERNAME_SET_PASSWORD).performScrollTo().performClick()

        assertEquals(1, opened)
    }

    @Test
    fun `after recreation the new name survives and the password is empty`() {
        val restore = StateRestorationTester(compose)
        restore.setContent {
            ShikkhokTheme {
                UsernameScreen(UsernameUiState.Editing("nadia_k"), AvailabilityState.Idle, UsernameActions())
            }
        }
        compose.onNodeWithTag(TAG_USERNAME_NEW).performTextInput("Nadia.K")
        compose.onNodeWithTag(TAG_USERNAME_PASSWORD).performScrollTo().performTextInput("correct horse")

        restore.emulateSavedInstanceStateRestore()

        compose.onNodeWithTag(TAG_USERNAME_NEW)
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString("Nadia.K")))
        compose.onNodeWithTag(TAG_USERNAME_PASSWORD).performScrollTo()
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString("")))
    }
}
