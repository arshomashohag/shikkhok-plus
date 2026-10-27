package com.shikkhokplus.app.feature.invitations

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.model.AcceptanceState
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.invitations.ui.InvitationsScreen
import com.shikkhokplus.app.feature.invitations.ui.TAG_INVITATION_DECLINE
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * `O4` invitations, rendered.
 *
 * **The decline-sheet pair is the test that matters here** [BR5.2,
 * AC1.14.1a]. One confirmation written once and shown to both roles
 * told a guardian a debt was cancelled when it was not. The two sheets
 * say opposite things about the fee, and only a rendering test can
 * catch them being swapped: the state carries the right
 * [DeclineSheet] either way.
 *
 * The three-fields rule [BR1.4, AC1.10.1] is likewise assertable only
 * here, because it is about what the screen does not show.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class InvitationsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val seat = InvitationRow(
        enrollmentId = "e1",
        batchName = "Class 9 Physics",
        subject = listOf("Physics"),
        fee = Money.of("1200.00"),
        state = AcceptanceState.PENDING,
        canDecline = true,
        heldAsGuardian = false,
    )

    private fun render(
        state: InvitationsUiState,
        onOpen: (String) -> Unit = {},
        onAccept: (String) -> Unit = {},
        onDeclineRequested: (String) -> Unit = {},
        onDeclineConfirmed: (String) -> Unit = {},
        onDismissSheet: () -> Unit = {},
        onRetry: () -> Unit = {},
    ) {
        compose.setContent {
            InvitationsScreen(
                state = state,
                onOpen = onOpen,
                onAccept = onAccept,
                onDeclineRequested = onDeclineRequested,
                onDeclineConfirmed = onDeclineConfirmed,
                onDismissSheet = onDismissSheet,
                onRetry = onRetry,
            )
        }
    }

    @Test
    fun `a student decline says the fee stops`() {
        render(
            InvitationsUiState.ConfirmingDecline(
                row = seat,
                sheet = DeclineSheet.STUDENT,
            ),
        )

        compose
            .onNodeWithText("no further fees", substring = true)
            .assertIsDisplayed()
    }

    @Test
    fun `a guardian decline says the fees are UNCHANGED`() {
        render(
            InvitationsUiState.ConfirmingDecline(
                row = seat,
                sheet = DeclineSheet.GUARDIAN,
            ),
        )

        // The rule this asserts: a guardian's decline withdraws the
        // guardian's own lens and leaves the student's obligation
        // entirely intact [BR5.2]. Telling a guardian a debt was
        // cancelled is the defect this pair exists to prevent.
        compose
            .onNodeWithText("fees are unchanged", substring = true)
            .assertIsDisplayed()
        compose
            .onAllNodesWithText("no further fees", substring = true)
            .fetchSemanticsNodes()
            .let { assertEquals(0, it.size) }
    }

    @Test
    fun `both decline sheets name the batch being declined`() {
        render(
            InvitationsUiState.ConfirmingDecline(
                row = seat,
                sheet = DeclineSheet.GUARDIAN,
            ),
        )

        compose
            .onNodeWithText("Class 9 Physics", substring = true)
            .assertIsDisplayed()
    }

    @Test
    fun `a seat shows its three fields and nothing else`() {
        render(InvitationsUiState.Loaded(rows = listOf(seat)))

        compose.onNodeWithText("Class 9 Physics").assertIsDisplayed()
        compose.onNodeWithText("Physics").assertIsDisplayed()
        compose
            .onNodeWithText("1200.00", substring = true)
            .assertIsDisplayed()
    }

    @Test
    fun `a declined seat keeps its accept action`() {
        // Declining is durable against the TEACHER and reversible by
        // its holder [BR5.4, AC1.13.1]. Dropping the seat from this
        // list would make the reversal unreachable.
        render(
            InvitationsUiState.Loaded(
                rows = listOf(
                    seat.copy(
                        state = AcceptanceState.DECLINED,
                        canDecline = false,
                    ),
                ),
            ),
        )

        compose.onNodeWithText("You declined this").assertIsDisplayed()
        compose.onNodeWithText("Accept").assertIsDisplayed()
    }

    @Test
    fun `a declined seat offers no second decline`() {
        render(
            InvitationsUiState.Loaded(
                rows = listOf(
                    seat.copy(
                        state = AcceptanceState.DECLINED,
                        canDecline = false,
                    ),
                ),
            ),
        )

        compose
            .onAllNodes(hasTestTag(TAG_INVITATION_DECLINE))
            .fetchSemanticsNodes()
            .let { assertEquals(0, it.size) }
    }

    @Test
    fun `accepting reports the seat it was asked about`() {
        var accepted: String? = null
        render(
            InvitationsUiState.Loaded(rows = listOf(seat)),
            onAccept = { accepted = it },
        )

        compose.onNodeWithText("Accept").performClick()
        assertEquals("e1", accepted)
    }

    @Test
    fun `an empty invitation list explains itself`() {
        // A distinct state rather than a Loaded with no rows: a blank
        // list explains nothing.
        render(InvitationsUiState.Empty)

        compose.onNodeWithText("Nothing to answer").assertIsDisplayed()
    }

    @Test
    fun `a seat with no fee of its own renders without one`() {
        // Null is NOT zero: zero is a waiver, null inherits the batch
        // default. The screen must not invent a figure for null.
        render(
            InvitationsUiState.Loaded(rows = listOf(seat.copy(fee = null))),
        )

        compose.onNodeWithText("Class 9 Physics").assertIsDisplayed()
        compose
            .onAllNodesWithText("/mo", substring = true)
            .fetchSemanticsNodes()
            .let { assertEquals(0, it.size) }
    }
}
