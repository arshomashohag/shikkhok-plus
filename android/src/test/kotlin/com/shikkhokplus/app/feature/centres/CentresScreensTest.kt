package com.shikkhokplus.app.feature.centres

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.MembershipDto
import com.shikkhokplus.app.core.network.WorkspaceDto
import com.shikkhokplus.app.feature.centres.ui.CentreOffersSection
import com.shikkhokplus.app.feature.centres.ui.MembersActions
import com.shikkhokplus.app.feature.centres.ui.MembersScreen
import com.shikkhokplus.app.feature.centres.ui.TAG_MEMBER_REMOVE_CONFIRM
import com.shikkhokplus.app.feature.centres.ui.TAG_OFFERS
import com.shikkhokplus.app.feature.centres.ui.memberRemoveTag
import com.shikkhokplus.app.feature.centres.ui.offerAcceptTag
import com.shikkhokplus.app.feature.profile.ProfileUiState
import com.shikkhokplus.app.feature.profile.ui.MoreActions
import com.shikkhokplus.app.feature.profile.ui.ProfileScreen
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_CENTRE_MEMBERS
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_OPEN_CENTRE
import com.shikkhokplus.app.feature.profile.ui.workspaceRowTag
import com.shikkhokplus.app.core.session.Lens
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** Members, centres' offers and the workspace rows on More, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class CentresScreensTest {

    @get:Rule
    val compose = createComposeRule()

    private fun member(id: String, name: String, isYou: Boolean = false, revoked: Boolean = false) =
        MemberDto(id, name, "+8801711000000", "teacher", "accepted", revoked = revoked, isYou = isYou)

    @Test
    fun `a member can be removed once confirmed, but not yourself or someone already removed`() {
        val removed = mutableListOf<String>()
        compose.setContent {
            MembersScreen(
                state =
                    MembersUiState(
                        body =
                            MembersBody.Loaded(
                                listOf(
                                    member("m-me", "Rahima", isYou = true),
                                    member("m-1", "Karim"),
                                    member("m-2", "Salma", revoked = true),
                                ),
                            ),
                    ),
                actions = MembersActions(onRemove = { removed += it }),
            )
        }

        compose.onNodeWithTag(memberRemoveTag("m-me")).assertDoesNotExist()
        compose.onNodeWithTag(memberRemoveTag("m-2")).assertDoesNotExist()
        compose.onNodeWithTag(memberRemoveTag("m-1")).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_MEMBER_REMOVE_CONFIRM).performClick()

        assertEquals(listOf("m-1"), removed)
    }

    @Test
    fun `an offer names the centre and the role and can be accepted`() {
        val accepted = mutableListOf<String>()
        compose.setContent {
            CentreOffersSection(
                OffersUiState(offers = listOf(MembershipDto("o-1", "Udayan Coaching", "teacher", "pending"))),
                onAccept = { accepted += it },
                onDecline = {},
            )
        }

        compose.onNodeWithText("Udayan Coaching").assertIsDisplayed()
        compose.onNodeWithTag(offerAcceptTag("o-1")).performClick()
        assertEquals(listOf("o-1"), accepted)
    }

    @Test
    fun `no offers draws no section`() {
        compose.setContent { CentreOffersSection(OffersUiState(), onAccept = {}, onDecline = {}) }
        compose.onNodeWithTag(TAG_OFFERS).assertDoesNotExist()
    }

    private val solo = WorkspaceDto("w-solo", "solo")
    private val centre = WorkspaceDto("w-centre", "centre", "Udayan Coaching")

    private fun more(actions: MoreActions) {
        compose.setContent {
            ProfileScreen(
                state = ProfileUiState.Viewing("Rahima", "Dhaka", phone = "+8801711000000"),
                actions = actions,
                lens = Lens.TEACHER,
            )
        }
    }

    @Test
    fun `More lists each workspace to switch to, and the open one is not a switch`() {
        val switched = mutableListOf<String>()
        more(
            MoreActions(
                workspaces = listOf(solo, centre),
                currentWorkspace = solo,
                onSwitchWorkspace = { switched += it },
                onOpenCentre = {},
            ),
        )

        compose.onNodeWithTag(workspaceRowTag("w-solo")).performScrollTo().performClick()
        compose.onNodeWithTag(workspaceRowTag("w-centre")).performScrollTo().performClick()

        assertEquals(listOf("w-centre"), switched)
        compose.onNodeWithTag(TAG_PROFILE_CENTRE_MEMBERS).assertDoesNotExist()
        compose.onNodeWithTag(TAG_PROFILE_OPEN_CENTRE).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `with one workspace there is nothing to switch, only opening a centre`() {
        more(MoreActions(workspaces = listOf(solo), currentWorkspace = solo, onSwitchWorkspace = {}, onOpenCentre = {}))

        compose.onNodeWithTag(workspaceRowTag("w-solo")).assertDoesNotExist()
        compose.onNodeWithTag(TAG_PROFILE_OPEN_CENTRE).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `in a centre More offers its members`() {
        var opened = 0
        more(
            MoreActions(
                workspaces = listOf(solo, centre),
                currentWorkspace = centre,
                onSwitchWorkspace = {},
                onOpenCentre = {},
                onCentreMembers = { opened++ },
            ),
        )

        compose.onNodeWithTag(TAG_PROFILE_CENTRE_MEMBERS).performScrollTo().performClick()
        assertEquals(1, opened)
    }
}
