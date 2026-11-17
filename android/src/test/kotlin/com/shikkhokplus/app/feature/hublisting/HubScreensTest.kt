package com.shikkhokplus.app.feature.hublisting

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextReplacement
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.hublisting.ui.BatchListingsActions
import com.shikkhokplus.app.feature.hublisting.ui.BatchListingsScreen
import com.shikkhokplus.app.feature.hublisting.ui.HubListingActions
import com.shikkhokplus.app.feature.hublisting.ui.HubListingScreen
import com.shikkhokplus.app.feature.hublisting.ui.NameConsentScreen
import com.shikkhokplus.app.feature.hublisting.ui.TAG_BATCH_PUBLISH
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_AGREE
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_BADGE
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_CONFIRM_PUBLISH
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_NAME_LATIN
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_PUBLISH
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_RETRY
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_SAVE
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_STREET
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_SUSPENDED
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_UNPUBLISH
import com.shikkhokplus.app.feature.hublisting.ui.batchListingRowTag
import com.shikkhokplus.app.feature.hublisting.ui.nameConsentTag
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

private const val SHEET_SETTLE_MILLIS = 2_000L

/** Click through semantics: a sheet lives in its own window, where injected touches miss under Robolectric. */
private fun SemanticsNodeInteraction.tap() = performSemanticsAction(SemanticsActions.OnClick)

/** What the owner's listing screens render, and the rules that are visible only as absences. */
@RunWith(RobolectricTestRunner::class)
// A tall screen: the sheets are taller than Robolectric's default phone and a click below the fold misses.
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class HubScreensTest {

    @get:Rule
    val compose = createComposeRule()

    private fun listingState(
        listing: OwnerListingResponse,
        draft: HubDraft = draftOf(listing),
        publishing: Boolean = false,
        agreed: Boolean = false,
        failure: HubFailure? = null,
    ) = HubListingState(
        body = listing.toUiState(),
        draft = draft,
        publishing = publishing,
        agreed = agreed,
        failure = failure,
    )

    @Test
    fun `publish follows the servers publishable and waits for the consent box`() {
        val opened = mutableListOf<String>()
        val published = mutableListOf<String>()
        var state by mutableStateOf(listingState(owner(publishable = true)))
        compose.setContent {
            HubListingScreen(
                state = state,
                actions =
                    HubListingActions(
                        onOpenPublish = {
                            opened += "open"
                            state = state.copy(publishing = true)
                        },
                        onAgree = { state = state.copy(agreed = it) },
                        onPublish = { published += "publish" },
                    ),
            )
        }

        compose.onNodeWithTag(TAG_HUB_PUBLISH).performScrollTo().assertIsEnabled().performClick()
        compose.mainClock.advanceTimeBy(SHEET_SETTLE_MILLIS)
        compose.onNodeWithTag(TAG_HUB_CONFIRM_PUBLISH).assertIsNotEnabled()
        compose.onNodeWithTag(TAG_HUB_AGREE).tap()
        compose.onNodeWithTag(TAG_HUB_CONFIRM_PUBLISH).assertIsEnabled().tap()

        assertEquals(listOf("open"), opened)
        assertEquals(listOf("publish"), published)
    }

    @Test
    fun `an unpublishable listing offers no publish, whatever is typed`() {
        compose.setContent {
            HubListingScreen(listingState(owner(publishable = false)), HubListingActions())
        }
        compose.onNodeWithTag(TAG_HUB_PUBLISH).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `a suspended listing shows how to appeal and offers no editing`() {
        var appealed = 0
        compose.setContent {
            HubListingScreen(
                listingState(owner(status = "suspended", publishable = true)),
                HubListingActions(onAppeal = { appealed++ }),
            )
        }

        compose.onNodeWithTag(TAG_HUB_SUSPENDED).assertIsDisplayed()
        compose.onNodeWithText("Appeal through Help").performClick()
        compose.onNodeWithTag(TAG_HUB_SAVE).assertDoesNotExist()
        compose.onNodeWithTag(TAG_HUB_PUBLISH).assertDoesNotExist()
        assertEquals(1, appealed)
    }

    @Test
    fun `the street address and the badge appear only when the server says so`() {
        compose.setContent {
            HubListingScreen(listingState(owner(isCentre = true, runsClasses = true)), HubListingActions())
        }
        compose.onNodeWithTag(TAG_HUB_STREET).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_HUB_BADGE).assertExists()
    }

    @Test
    fun `a person's own listing shows no street address and no badge`() {
        compose.setContent { HubListingScreen(listingState(owner()), HubListingActions()) }
        compose.onNodeWithTag(TAG_HUB_STREET).assertDoesNotExist()
        compose.onNodeWithTag(TAG_HUB_BADGE).assertDoesNotExist()
    }

    @Test
    fun `the optional latin name field shows the draft and edits it`() {
        var draft by mutableStateOf(HubDraft(publicName = "রহিমা", publicNameLatin = "Rahima"))
        compose.setContent {
            HubListingScreen(
                listingState(owner(), draft = draft),
                HubListingActions(onEdit = { edit -> draft = edit(draft) }),
            )
        }

        compose.onNodeWithTag(TAG_HUB_NAME_LATIN).performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("Rahima").assertExists()
        compose.onNodeWithTag(TAG_HUB_NAME_LATIN).performTextReplacement("Rahima Akter")
        assertEquals("Rahima Akter", draft.publicNameLatin)
    }

    @Test
    fun `a failed save shows the servers message with retry that keeps the form`() {
        var retried = 0
        compose.setContent {
            HubListingScreen(
                listingState(
                    owner(),
                    draft = HubDraft(publicName = "Rahima", headlineEn = "kept"),
                    failure = HubFailure("error.network.unreachable", canRetry = true),
                ),
                HubListingActions(onRetry = { retried++ }),
            )
        }

        compose.onNodeWithTag(TAG_HUB_RETRY).performScrollTo().performClick()
        compose.onNodeWithText("kept").assertExists()
        assertEquals(1, retried)
    }

    @Test
    fun `a published listing offers unpublish instead of publish`() {
        compose.setContent {
            HubListingScreen(listingState(owner(status = "published", publishable = true)), HubListingActions())
        }
        compose.onNodeWithTag(TAG_HUB_UNPUBLISH).performScrollTo().assertIsEnabled()
        compose.onNodeWithTag(TAG_HUB_PUBLISH).assertDoesNotExist()
    }

    @Test
    fun `the batch list shows the servers fee string and a localized fallback for hidden names`() {
        val state =
            BatchListingsState(
                BatchListingsBody.Loaded(
                    listOf(
                        batchListing(
                            name = "পদার্থবিজ্ঞান নবম শ্রেণি দীর্ঘ নাম যা লাইনে ভাঙবে",
                            fee = Money.of("1500.50"),
                            teacherNames = listOf("Rahima", "Centre faculty"),
                        ),
                        batchListing(id = "b-2", name = "Maths", fee = null),
                    ),
                ),
            )
        var opened = ""
        compose.setContent {
            BatchListingsScreen(state, BatchListingsActions(onEdit = { opened = it }))
        }

        compose.onNodeWithText("Fee ৳1500.50").assertIsDisplayed()
        compose.onNodeWithText("Fee not shown publicly").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(batchListingRowTag("b-2")).performClick()
        assertEquals("b-2", opened)
    }

    @Test
    fun `a batch editor publishes only when the server says it is publishable`() {
        val batch = batchListing(publishable = true, status = "draft")
        val published = mutableListOf<String>()
        compose.setContent {
            BatchListingsScreen(
                BatchListingsState(BatchListingsBody.Loaded(listOf(batch)), BatchEditorState(batch)),
                BatchListingsActions(onPublish = { published += "p" }),
            )
        }
        compose.mainClock.advanceTimeBy(SHEET_SETTLE_MILLIS)
        compose.onNodeWithTag(TAG_BATCH_PUBLISH).performScrollTo().assertIsEnabled().tap()
        assertEquals(listOf("p"), published)
    }

    @Test
    fun `the name consent box shows the servers last answer and asks to change it`() {
        val asked = mutableListOf<Pair<String, Boolean>>()
        compose.setContent {
            NameConsentScreen(
                NameConsentState(
                    NameConsentBody.Loaded(
                        listOf(
                            ConsentRow(
                                CentreMembership(
                                    "m-1",
                                    "c-1",
                                    "Udayan",
                                    "teacher",
                                    publicNameConsent = false,
                                    nameShown = "Karim Sir",
                                ),
                            ),
                        ),
                    ),
                ),
                onSet = { id, v -> asked += id to v },
                onRetry = {},
                onRetryLoad = {},
                onBack = {},
            )
        }
        compose.onNodeWithText("Shown as: Karim Sir").assertIsDisplayed()
        compose.onNodeWithTag(nameConsentTag("c-1")).performClick()
        assertEquals(listOf("c-1" to true), asked)
    }

    @Test
    fun `a batch row names its saved levels and curriculum in words`() {
        val state =
            BatchListingsState(
                BatchListingsBody.Loaded(
                    listOf(batchListing(classLevels = listOf("class_9", "hsc"), curriculum = "madrasah")),
                ),
            )
        compose.setContent { BatchListingsScreen(state, BatchListingsActions()) }

        compose.onNodeWithText("Class 9, HSC · Madrasah").assertIsDisplayed()
        compose.onNodeWithText("class_9", substring = true).assertDoesNotExist()
    }
}
