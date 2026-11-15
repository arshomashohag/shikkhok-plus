package com.shikkhokplus.app.feature.account

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.junit4.StateRestorationTester
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.text.AnnotatedString
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.feature.account.ui.ContactsActions
import com.shikkhokplus.app.feature.account.ui.ContactsScreen
import com.shikkhokplus.app.feature.account.ui.RemoveContactActions
import com.shikkhokplus.app.feature.account.ui.RemoveContactSheet
import com.shikkhokplus.app.feature.account.ui.ReplaceContactActions
import com.shikkhokplus.app.feature.account.ui.ReplaceContactScreen
import com.shikkhokplus.app.feature.account.ui.TAG_CONTACTS_PASSWORD_NOTE
import com.shikkhokplus.app.feature.account.ui.TAG_REMOVE_ADD_OTHER
import com.shikkhokplus.app.feature.account.ui.TAG_REMOVE_CONFIRM
import com.shikkhokplus.app.feature.account.ui.TAG_REMOVE_PASSWORD
import com.shikkhokplus.app.feature.account.ui.TAG_REPLACE_PASSWORD
import com.shikkhokplus.app.feature.account.ui.TAG_REPLACE_SEND
import com.shikkhokplus.app.feature.account.ui.TAG_REPLACE_VALUE
import com.shikkhokplus.app.feature.account.ui.contactActionTag
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The Contacts screen, the replace screen and the remove sheet, rendered
 * [W6; NFR3.4, NFR3.11].
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ContactsScreensTest {

    @get:Rule
    val compose = createComposeRule()

    private val both =
        ContactsUiState.Loaded(
            phone = ContactCard(IdentifierKind.PHONE, "+8801711111111"),
            email = ContactCard(IdentifierKind.EMAIL, "rafi@example.com"),
            passwordNote = false,
        )

    @Test
    fun `a present contact offers Replace and Remove, an absent one Add`() {
        val calls = mutableListOf<String>()
        compose.setContent {
            ShikkhokTheme {
                ContactsScreen(
                    state = both.copy(email = ContactCard(IdentifierKind.EMAIL, null)),
                    actions =
                        ContactsActions(
                            onAdd = { calls += "add-$it" },
                            onReplace = { calls += "replace-$it" },
                            onRemove = { calls += "remove-${it.kind}" },
                        ),
                )
            }
        }

        compose.onNodeWithTag(contactActionTag(IdentifierKind.PHONE, "replace")).performScrollTo().performClick()
        compose.onNodeWithTag(contactActionTag(IdentifierKind.PHONE, "remove")).performScrollTo().performClick()
        compose.onNodeWithTag(contactActionTag(IdentifierKind.EMAIL, "add")).performScrollTo().performClick()

        assertEquals(listOf("replace-PHONE", "remove-PHONE", "add-EMAIL"), calls)
        compose.onNodeWithTag(contactActionTag(IdentifierKind.EMAIL, "remove")).assertDoesNotExist()
    }

    @Test
    fun `no password shows the note, and the actions stay`() {
        compose.setContent { ShikkhokTheme { ContactsScreen(both.copy(passwordNote = true), ContactsActions()) } }

        compose.onNodeWithTag(TAG_CONTACTS_PASSWORD_NOTE).assertExists()
        compose.onNodeWithTag(contactActionTag(IdentifierKind.EMAIL, "remove")).performScrollTo().assertExists()
    }

    @Test
    fun `replacing sends the new value and the password`() {
        var sent: Pair<String, String>? = null
        compose.setContent {
            ShikkhokTheme {
                ReplaceContactScreen(
                    ReplaceContactUiState.Entering(IdentifierKind.EMAIL),
                    ReplaceContactActions(onRequestCode = { v, p -> sent = v to p }),
                )
            }
        }

        compose.onNodeWithTag(TAG_REPLACE_VALUE).performTextInput("new@example.com")
        compose.onNodeWithTag(TAG_REPLACE_PASSWORD).performScrollTo().performTextInput("correct horse")
        compose.onNodeWithTag(TAG_REPLACE_SEND).performScrollTo().performClick()

        assertEquals("new@example.com" to "correct horse", sent)
    }

    @Test
    fun `after recreation the new value survives and the replace password is empty`() {
        val restore = StateRestorationTester(compose)
        restore.setContent {
            ShikkhokTheme {
                ReplaceContactScreen(ReplaceContactUiState.Entering(IdentifierKind.EMAIL), ReplaceContactActions())
            }
        }
        compose.onNodeWithTag(TAG_REPLACE_VALUE).performTextInput("new@example.com")
        compose.onNodeWithTag(TAG_REPLACE_PASSWORD).performScrollTo().performTextInput("correct horse")

        restore.emulateSavedInstanceStateRestore()

        compose.onNodeWithTag(TAG_REPLACE_VALUE)
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString("new@example.com")))
        compose.onNodeWithTag(TAG_REPLACE_PASSWORD).performScrollTo()
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString("")))
    }

    @Test
    fun `the remove sheet names the contact and removes with the password`() {
        var sent: String? = null
        compose.setContent {
            ShikkhokTheme {
                RemoveContactSheet(
                    RemoveContactUiState.Confirming(IdentifierKind.EMAIL, "rafi@example.com"),
                    RemoveContactActions(onRemove = { sent = it }),
                )
            }
        }

        compose.onNodeWithText("Remove rafi@example.com?", substring = true).assertExists()
        compose.onNodeWithTag(TAG_REMOVE_PASSWORD).performTextInput("correct horse")
        compose.onNodeWithTag(TAG_REMOVE_CONFIRM).performClick()

        assertEquals("correct horse", sent)
    }

    @Test
    fun `the last one offers adding the other kind`() {
        var added = 0
        compose.setContent {
            ShikkhokTheme {
                RemoveContactSheet(
                    RemoveContactUiState.Confirming(
                        IdentifierKind.EMAIL,
                        "rafi@example.com",
                        bannerKey = "account.contact.last_one",
                        offerAddOther = true,
                    ),
                    RemoveContactActions(onAddOther = { added++ }),
                )
            }
        }

        compose.onNodeWithText("You need at least one phone number or email", substring = true).assertExists()
        compose.onNodeWithTag(TAG_REMOVE_ADD_OTHER).performClick()

        assertEquals(1, added)
    }

    @Test
    fun `after recreation the remove password is empty`() {
        val restore = StateRestorationTester(compose)
        restore.setContent {
            ShikkhokTheme {
                RemoveContactSheet(
                    RemoveContactUiState.Confirming(IdentifierKind.EMAIL, "rafi@example.com"),
                    RemoveContactActions(),
                )
            }
        }
        compose.onNodeWithTag(TAG_REMOVE_PASSWORD).performTextInput("correct horse")

        restore.emulateSavedInstanceStateRestore()

        compose.onNodeWithTag(TAG_REMOVE_PASSWORD)
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString("")))
    }

    @Test
    fun `a removal answered tells the route once`() {
        var removed = 0
        compose.setContent {
            ShikkhokTheme {
                RemoveContactSheet(RemoveContactUiState.Removed, RemoveContactActions(onRemoved = { removed++ }))
            }
        }
        compose.waitForIdle()

        assertEquals(1, removed)
    }
}
