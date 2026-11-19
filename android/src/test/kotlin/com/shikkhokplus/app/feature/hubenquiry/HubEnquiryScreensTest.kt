package com.shikkhokplus.app.feature.hubenquiry

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.hubenquiry.ui.EnquiryFormActions
import com.shikkhokplus.app.feature.hubenquiry.ui.EnquiryFormScreen
import com.shikkhokplus.app.feature.hubenquiry.ui.MyEnquiriesActions
import com.shikkhokplus.app.feature.hubenquiry.ui.MyEnquiriesScreen
import com.shikkhokplus.app.feature.hubenquiry.ui.OwnerEnquiryActions
import com.shikkhokplus.app.feature.hubenquiry.ui.OwnerEnquiryDetailScreen
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_CONTACT_EMAIL
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_CONTACT_PHONE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_MINE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_RETRY
import com.shikkhokplus.app.feature.hubenquiry.ui.enquiryActionTag
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * What the join-request screens draw from the server's values [H5]: the
 * guardian's contact only when the server sent one, the answers exactly as
 * offered, the share label by what "share" would share, and a fallback when
 * the owner's listing has gone.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class HubEnquiryScreensTest {

    @get:Rule
    val compose = createComposeRule()

    private fun detail(enquiry: OwnerEnquiry, actions: OwnerEnquiryActions = OwnerEnquiryActions()) =
        compose.setContent {
            ShikkhokTheme {
                OwnerEnquiryDetailScreen(OwnerEnquiryUiState.Ready(OwnerEnquiryView(enquiry)), actions)
            }
        }

    @Test
    fun `owner contact shown only when shared - a phone is a call`() {
        val called = mutableListOf<String>()
        detail(ownerEnquiry(phone = "+8801711000000"), OwnerEnquiryActions(onCall = { called += it }))

        compose.onNodeWithTag(TAG_ENQUIRY_CONTACT_PHONE).assertExists().performClick()
        assertEquals(listOf("+8801711000000"), called)
        compose.onNodeWithText("01711-000000").assertExists()
        assertTrue(compose.onAllNodesWithText("Not shared").fetchSemanticsNodes().isEmpty())
    }

    @Test
    fun `owner contact shown only when shared - an email is a message`() {
        val written = mutableListOf<String>()
        detail(ownerEnquiry(email = "guardian@example.com"), OwnerEnquiryActions(onEmail = { written += it }))

        compose.onNodeWithTag(TAG_ENQUIRY_CONTACT_EMAIL).performClick()
        assertEquals(listOf("guardian@example.com"), written)
    }

    @Test
    fun `owner contact shown only when shared - nothing sent reads Not shared`() {
        detail(ownerEnquiry(allowed = listOf("not_now")))

        compose.onNodeWithText("Not shared").assertExists()
        assertTrue(compose.onAllNodesWithTag(TAG_ENQUIRY_CONTACT_PHONE).fetchSemanticsNodes().isEmpty())
        assertTrue(compose.onAllNodesWithTag(TAG_ENQUIRY_CONTACT_EMAIL).fetchSemanticsNodes().isEmpty())
        // Exactly the answers offered.
        compose.onNodeWithTag(enquiryActionTag(EnquiryOutcome.NOT_NOW)).assertExists()
        assertTrue(compose.onAllNodesWithTag(enquiryActionTag(EnquiryOutcome.ADDED)).fetchSemanticsNodes().isEmpty())
        assertTrue(compose.onAllNodesWithTag(enquiryActionTag(EnquiryOutcome.CALL_US)).fetchSemanticsNodes().isEmpty())
    }

    @Test
    fun `an answered request offers nothing and says how it was answered`() {
        detail(ownerEnquiry(status = "closed", outcome = "call_us"))

        compose.onNodeWithText("Asked them to call you").assertExists()
        EnquiryOutcome.entries.forEach {
            assertTrue(compose.onAllNodesWithTag(enquiryActionTag(it)).fetchSemanticsNodes().isEmpty())
        }
    }

    @Test
    fun `the share label names an email for an account without a phone`() {
        compose.setContent {
            ShikkhokTheme {
                EnquiryFormScreen(
                    EnquiryFormUiState.Ready(EnquiryForm(target(contactKind = "email"))),
                    EnquiryFormActions(),
                )
            }
        }

        compose.onNodeWithText("Share my email address with Rahima").assertExists()
        compose.onNodeWithText("Don't share it").assertExists()
        compose.onNodeWithText("cannot contact you", substring = true).assertExists()
    }

    @Test
    fun `a refusal reads the server's words, with Retry only when it can help`() {
        val refused = EnquiryForm(target(), failure = EnquiryFailure("hub.enquiry.contains_contact", canRetry = false))
        compose.setContent {
            ShikkhokTheme { EnquiryFormScreen(EnquiryFormUiState.Ready(refused), EnquiryFormActions()) }
        }

        compose.onNodeWithText("Your request was not sent.").assertExists()
        compose.onNodeWithText("choose Share", substring = true).assertExists()
        assertTrue(compose.onAllNodesWithTag(TAG_ENQUIRY_RETRY).fetchSemanticsNodes().isEmpty())
    }

    @Test
    fun `already open at send time points to my requests`() {
        val opened = mutableListOf<Unit>()
        val failed =
            EnquiryForm(
                target(),
                failure = EnquiryFailure("hub.enquiry.already_open", canRetry = false, alreadyOpen = true),
            )
        compose.setContent {
            ShikkhokTheme {
                EnquiryFormScreen(EnquiryFormUiState.Ready(failed), EnquiryFormActions(onMine = { opened += Unit }))
            }
        }

        compose.onNodeWithTag(TAG_ENQUIRY_MINE).performClick()
        assertEquals(1, opened.size)
    }

    @Test
    fun `a request whose listing has gone reads as a teacher no longer listed`() {
        compose.setContent {
            ShikkhokTheme {
                MyEnquiriesScreen(
                    MyEnquiriesUiState.Ready(listOf(myEnquiry(owner = null, status = "closed", outcome = "not_now"))),
                    MyEnquiriesActions(),
                )
            }
        }

        compose.onNodeWithText("A teacher no longer listed").assertExists()
        compose.onNodeWithText("The teacher cannot take this request now.").assertExists()
        compose.onNodeWithText("Nadia · Class 8 · Sent 19 Nov 2026").assertExists()
    }
}
