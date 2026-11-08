package com.shikkhokplus.app.feature.account

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
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
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.ui.TAG_CONFIRM_PASSWORD
import com.shikkhokplus.app.core.ui.TAG_NEW_PASSWORD
import com.shikkhokplus.app.feature.account.ui.AddContactScreen
import com.shikkhokplus.app.feature.account.ui.PasswordChangeScreen
import com.shikkhokplus.app.feature.account.ui.PasswordPrompt
import com.shikkhokplus.app.feature.account.ui.TAG_ACCOUNT_BUSY
import com.shikkhokplus.app.feature.account.ui.TAG_ACCOUNT_RETRY
import com.shikkhokplus.app.feature.account.ui.TAG_CONTACT_FIELD
import com.shikkhokplus.app.feature.account.ui.TAG_CONTACT_SEND
import com.shikkhokplus.app.feature.account.ui.TAG_CURRENT_PASSWORD
import com.shikkhokplus.app.feature.account.ui.TAG_PASSWORD_PROMPT_ACTION
import com.shikkhokplus.app.feature.account.ui.TAG_PASSWORD_SAVE
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The signed-in password and contact screens, rendered: what each state
 * shows, and that what is typed is what is sent.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class AccountScreensTest {

    @get:Rule
    val compose = createComposeRule()

    // --- The password ------------------------------------------------------------

    private fun renderPassword(
        state: PasswordChangeUiState,
        onSubmit: (String, String, String) -> Unit = { _, _, _ -> },
    ) {
        compose.setContent { ShikkhokTheme { PasswordChangeScreen(state, onSubmit, onBack = {}) } }
    }

    @Test
    fun `a first password asks for no current one`() {
        renderPassword(PasswordChangeUiState.Editing(hasPassword = false))

        compose.onNodeWithText("Set a password").assertExists()
        compose.onNodeWithTag(TAG_CURRENT_PASSWORD).assertDoesNotExist()
    }

    @Test
    fun `a change asks for the current one and sends all three as typed`() {
        var sent: Triple<String, String, String>? = null
        renderPassword(
            PasswordChangeUiState.Editing(hasPassword = true),
            onSubmit = { a, b, c -> sent = Triple(a, b, c) },
        )

        compose.onNodeWithTag(TAG_PASSWORD_SAVE).performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag(TAG_CURRENT_PASSWORD).performTextInput("old horse")
        compose.onNodeWithTag(TAG_NEW_PASSWORD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_CONFIRM_PASSWORD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_PASSWORD_SAVE).performScrollTo().assertIsEnabled().performClick()

        assertEquals(Triple("old horse", "correct horse", "correct horse"), sent)
    }

    @Test
    fun `every password field is masked`() {
        renderPassword(PasswordChangeUiState.Editing(hasPassword = true))

        listOf(TAG_CURRENT_PASSWORD, TAG_NEW_PASSWORD, TAG_CONFIRM_PASSWORD).forEach { tag ->
            compose
                .onNodeWithTag(tag)
                .performScrollTo()
                .assert(SemanticsMatcher.keyIsDefined(SemanticsProperties.Password))
        }
    }

    @Test
    fun `a retryable failure offers a retry, and a refusal does not`() {
        renderPassword(
            PasswordChangeUiState.Editing(
                hasPassword = false,
                messageKey = "error.network.unreachable",
                retryable = true,
            ),
        )
        compose.onNodeWithTag(TAG_ACCOUNT_RETRY).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `a wrong current password is said, with no retry`() {
        renderPassword(PasswordChangeUiState.Editing(hasPassword = true, messageKey = "auth.password.current_wrong"))

        compose.onNodeWithText("That isn't your current password.").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_ACCOUNT_RETRY).assertDoesNotExist()
    }

    @Test
    fun `saving shows progress`() {
        renderPassword(PasswordChangeUiState.Editing(hasPassword = false, saving = true))
        compose.onNodeWithTag(TAG_ACCOUNT_BUSY).assertIsDisplayed()
    }

    // --- Adding a phone or an email ---------------------------------------------------

    private fun renderContact(
        state: AddContactUiState,
        onRequest: (String) -> Unit = {},
        onCode: (String) -> Unit = {},
    ) {
        compose.setContent {
            ShikkhokTheme {
                AddContactScreen(state, onRequest, onCode, onResend = {}, onChange = {}, onBack = {})
            }
        }
    }

    @Test
    fun `adding a phone says why teachers need it`() {
        renderContact(AddContactUiState.Entering(IdentifierKind.PHONE))

        compose
            .onNodeWithText("Teachers find students and guardians by phone number.", substring = true)
            .assertExists()
    }

    @Test
    fun `a well-formed number is sent, a malformed one is named and not sent`() {
        val sent = mutableListOf<String>()
        renderContact(AddContactUiState.Entering(IdentifierKind.PHONE), onRequest = { sent += it })

        compose.onNodeWithTag(TAG_CONTACT_FIELD).performTextInput("0171")
        compose.onNodeWithTag(TAG_CONTACT_SEND).performScrollTo().performClick()
        assertEquals(emptyList(), sent)
        compose.onNodeWithText("Bangladeshi mobile numbers have 11 digits, starting 01.").assertExists()

        compose.onNodeWithTag(TAG_CONTACT_FIELD).performTextInput("1234567")
        compose.onNodeWithTag(TAG_CONTACT_SEND).performScrollTo().performClick()
        assertEquals(listOf("01711234567"), sent)
    }

    @Test
    fun `the code step sends the six digits on the sixth`() {
        val sent = mutableListOf<String>()
        renderContact(AddContactUiState.AwaitingCode(IdentifierKind.EMAIL), onCode = { sent += it })

        compose.onNodeWithText("We sent a 6-digit code to this email.").assertExists()
        compose.onNodeWithTag(TAG_OTP_FIELD).performTextInput("123456")

        assertEquals(listOf("123456"), sent)
    }

    @Test
    fun `a number another account uses is said in the server's words`() {
        renderContact(AddContactUiState.AwaitingCode(IdentifierKind.PHONE, messageKey = "account.contact.taken"))

        compose.onNodeWithText("Another account already uses this.").performScrollTo().assertIsDisplayed()
    }

    // --- The prompt ------------------------------------------------------------

    @Test
    fun `the prompt says why and leads to the password screen`() {
        var opened = 0
        compose.setContent { ShikkhokTheme { PasswordPrompt(onSetPassword = { opened++ }) } }

        compose.onNodeWithText("Set a password so you can log in without a code.").assertIsDisplayed()
        compose.onNodeWithTag(TAG_PASSWORD_PROMPT_ACTION).performClick()

        assertEquals(1, opened)
    }
}
