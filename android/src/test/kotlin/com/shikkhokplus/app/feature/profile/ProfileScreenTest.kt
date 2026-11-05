package com.shikkhokplus.app.feature.profile

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.feature.profile.ui.MoreActions
import com.shikkhokplus.app.feature.profile.ui.ProfileScreen
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_CARD
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_COLLECTIONS
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_DELETE
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_EDIT
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_INVITATIONS
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_MY_CHILDREN
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_PAYMENT_METHODS
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_SIGN_OUT
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_SETTINGS
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_SWITCH_LENS
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_OFFLINE
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_UNSENT
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * More (T9, S4, G4), rendered.
 *
 * The obligations assertable only here:
 *
 * * **A row appears only when it leads somewhere.** The lens decides
 *   which rows exist by which destinations the route supplies; a null
 *   destination draws nothing, so nobody is offered a row that opens
 *   nothing.
 * * **The deletion control is present and wired** [TC-19].
 * * **The card shows who is signed in**, with the number formatted the
 *   way every other screen formats it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ProfileScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val viewing = ProfileUiState.Viewing("Rahim", "Dhaka", phone = "+8801611477203")

    private fun render(
        state: ProfileUiState = viewing,
        actions: MoreActions = MoreActions(),
        lens: Lens? = Lens.STUDENT,
        summary: ProfileSummary? = null,
        version: String? = null,
    ) {
        compose.setContent {
            ProfileScreen(
                state = state,
                actions = actions,
                lens = lens,
                summary = summary,
                version = version,
            )
        }
    }

    @Test
    fun `the screen is called More`() {
        render()

        compose.onNodeWithText("More").assertIsDisplayed()
    }

    @Test
    fun `the card shows the name, the role and the formatted number`() {
        render(lens = Lens.TEACHER)

        compose.onNodeWithTag(TAG_PROFILE_CARD).assertIsDisplayed()
        compose.onNodeWithText("Rahim").assertIsDisplayed()
        compose.onNodeWithText("Teacher · 01611-477203").assertIsDisplayed()
    }

    @Test
    fun `a person with no stored name is asked to add one`() {
        // A teacher recorded only the number; the card must not be blank.
        render(state = ProfileUiState.Viewing(selfName = null, address = null, phone = "+8801611477203"))

        compose.onNodeWithText("Add your name").assertIsDisplayed()
    }

    @Test
    fun `while the form is open the card draws from the confirmed profile`() {
        // More stays composed under Edit profile; a half-typed name in
        // the Editing state must not reach the card.
        render(
            state = ProfileUiState.Editing(selfName = "Half-typ", address = ""),
            summary = ProfileSummary(selfName = "Rahim", address = "Dhaka", phone = "+8801611477203"),
        )

        compose.onNodeWithText("Rahim").assertIsDisplayed()
        compose.onNodeWithText("Half-typ").assertDoesNotExist()
    }

    @Test
    fun `a saved profile confirms the save above the card`() {
        render(state = ProfileUiState.Saved("Karim", "Khulna", phone = "+8801611477203"))

        compose.onNodeWithText("Saved.").assertIsDisplayed()
        compose.onNodeWithText("Karim").assertIsDisplayed()
    }

    @Test
    fun `edit, log out and delete each call back only when tapped`() {
        var edits = 0
        var deletes = 0
        var signOuts = 0
        render(
            actions =
                MoreActions(
                    onEdit = { edits++ },
                    onDeleteAccount = { deletes++ },
                    onSignOut = { signOuts++ },
                ),
        )
        assertEquals(0, edits + deletes + signOuts, "rendering must not act")

        compose.onNodeWithTag(TAG_PROFILE_EDIT).performClick()
        compose.onNodeWithTag(TAG_PROFILE_SIGN_OUT).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_PROFILE_DELETE).performScrollTo().performClick()

        assertEquals(1, edits)
        assertEquals(1, signOuts)
        assertEquals(1, deletes)
    }

    @Test
    fun `the profile offers account deletion to every lens`() {
        // One composition, the lens swapped under it: a rule may set its
        // content only once.
        var lens by mutableStateOf<Lens?>(Lens.TEACHER)
        compose.setContent { ProfileScreen(state = viewing, actions = MoreActions(), lens = lens) }

        listOf(Lens.TEACHER, Lens.STUDENT, Lens.GUARDIAN, null).forEach { next ->
            lens = next
            compose.waitForIdle()
            compose.onNodeWithTag(TAG_PROFILE_DELETE).performScrollTo().assertIsDisplayed()
        }
    }

    @Test
    fun `a row with no destination is not drawn`() {
        render(actions = MoreActions())

        compose.onNodeWithTag(TAG_PROFILE_PAYMENT_METHODS).assertDoesNotExist()
        compose.onNodeWithTag(TAG_PROFILE_COLLECTIONS).assertDoesNotExist()
        compose.onNodeWithTag(TAG_PROFILE_INVITATIONS).assertDoesNotExist()
        compose.onNodeWithTag(TAG_PROFILE_MY_CHILDREN).assertDoesNotExist()
        compose.onNodeWithTag(TAG_PROFILE_SWITCH_LENS).assertDoesNotExist()
    }

    @Test
    fun `a teacher's rows sit under their section headers and open their screens`() {
        var methods = 0
        var reports = 0
        render(
            lens = Lens.TEACHER,
            actions = MoreActions(onPaymentMethods = { methods++ }, onCollections = { reports++ }),
        )

        compose.onNodeWithText("GETTING PAID").assertIsDisplayed()
        compose.onNodeWithText("Where students pay").assertIsDisplayed()
        compose.onNodeWithText("YOUR RECORDS").performScrollTo().assertIsDisplayed()

        compose.onNodeWithTag(TAG_PROFILE_PAYMENT_METHODS).performClick()
        compose.onNodeWithTag(TAG_PROFILE_COLLECTIONS).performScrollTo().performClick()

        assertEquals(1, methods)
        assertEquals(1, reports)
    }

    @Test
    fun `a guardian is offered invitations and their children`() {
        var invitations = 0
        var children = 0
        render(
            lens = Lens.GUARDIAN,
            actions = MoreActions(onInvitations = { invitations++ }, onMyChildren = { children++ }),
        )

        compose.onNodeWithText("Children a teacher linked to your number").assertIsDisplayed()
        compose.onNodeWithTag(TAG_PROFILE_INVITATIONS).performClick()
        compose.onNodeWithTag(TAG_PROFILE_MY_CHILDREN).performClick()

        assertEquals(1, invitations)
        assertEquals(1, children)
    }

    @Test
    fun `switch role appears only when there is a role to switch to`() {
        var switches = 0
        render(actions = MoreActions(onSwitchLens = { switches++ }))

        compose.onNodeWithTag(TAG_PROFILE_SWITCH_LENS).performScrollTo().performClick()

        assertEquals(1, switches)
    }

    @Test
    fun `the version sits at the foot`() {
        render(version = "1.0.0")

        compose.onNodeWithText("ShikkhokPlus 1.0.0").performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `a retryable failure offers a retry the server permitted`() {
        var retried = false
        render(
            state = ProfileUiState.Failed(messageKey = "error.network.unreachable", retryable = true),
            actions = MoreActions(onRetry = { retried = true }),
        )

        compose.onNodeWithText("Try again", substring = true).performClick()
        assertEquals(true, retried)
    }

    @Test
    fun `offline keeps the card, says so, and holds back what needs the server`() {
        // T9/S4/G4 "Error · offline".
        var invitations = 0
        render(
            state = viewing.copy(offline = true),
            actions = MoreActions(onInvitations = { invitations++ }),
        )

        compose.onNodeWithTag(TAG_PROFILE_OFFLINE).assertIsDisplayed()
        compose.onNodeWithText("Rahim").assertIsDisplayed()
        compose.onNodeWithTag(TAG_PROFILE_EDIT).assertDoesNotExist()
        compose.onNodeWithTag(TAG_PROFILE_INVITATIONS).assertIsNotEnabled()
        compose.onNodeWithTag(TAG_PROFILE_SIGN_OUT).performScrollTo().assertIsEnabled()
    }

    @Test
    fun `a teacher with unsent records is told how many`() {
        render(lens = Lens.TEACHER, actions = MoreActions(onCollections = {}, unsent = 2))

        compose.onNodeWithTag(TAG_PROFILE_UNSENT).performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("2 records not sent yet").assertExists()
    }

    @Test
    fun `settings is a row under APP, and works offline`() {
        // A theme and a text size are kept on the phone, so nothing about
        // them waits for a connection.
        var opened = 0
        render(state = viewing.copy(offline = true), actions = MoreActions(onSettings = { opened++ }))

        compose.onNodeWithText("APP").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_PROFILE_SETTINGS).performScrollTo().assertIsEnabled().performClick()

        assertEquals(1, opened)
    }
}
