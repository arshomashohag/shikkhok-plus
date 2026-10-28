package com.shikkhokplus.app.feature.roster

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.model.LinkState
import com.shikkhokplus.app.feature.roster.ui.RosterScreen
import com.shikkhokplus.app.feature.roster.ui.RemoveSeatRefused
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_DECLINED_MARK
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_STUDENT_STATE
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_GUARDIAN_STATE
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_REMOVE
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_REMOVE_CONFIRM
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_REMOVE_REFUSED
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_REMEDY
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_MARK_INACTIVE
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_ROW
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_EMPTY
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_ERROR
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_FETCHED_AT
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_LIST
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_LOADING
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_RETRY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * What the roster screen renders for a given state.
 *
 * This is the half the mapper tests cannot see: a correct state mapped
 * to a screen showing the wrong control is still a broken screen.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RosterScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun row(
        name: String,
        status: String = "roster.status.active",
        studentState: LinkState = LinkState.PENDING,
        guardianState: LinkState = LinkState.ABSENT,
        displayLabel: String? = name,
        isDeclined: Boolean = false,
        isRemovable: Boolean = true,
    ) =
        RosterRow(
            enrollmentId = "e-$name",
            displayName = name,
            statusLabel = status,
            fee = null,
            guardianPhone = null,
            studentState = studentState,
            guardianState = guardianState,
            displayLabel = displayLabel,
            isDeclined = isDeclined,
            isRemovable = isRemovable,
        )

    @Test
    fun `loading shows a spinner`() {
        compose.setContent { RosterScreen(RosterUiState.Loading, onRetry = {}) }

        compose.onNodeWithTag(TAG_ROSTER_LOADING).assertIsDisplayed()
    }

    @Test
    fun `an empty batch explains itself rather than showing a blank list`() {
        compose.setContent {
            RosterScreen(RosterUiState.Empty("Physics"), onRetry = {})
        }

        compose.onNodeWithTag(TAG_ROSTER_EMPTY).assertIsDisplayed()
    }

    @Test
    fun `a loaded roster shows the list`() {
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded("Physics", listOf(row("Rahim")), null),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_LIST).assertIsDisplayed()
    }

    @Test
    fun `cached data says so, rather than passing as live`() {
        // The cache is a READ cache. A teacher must know when they are
        // looking at saved data; silently rendering it as current is how
        // a stale roster gets trusted in front of a class.
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded("Physics", listOf(row("Rahim")), "10:05"),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_FETCHED_AT).assertIsDisplayed()
    }

    @Test
    fun `live data shows no staleness notice`() {
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded("Physics", listOf(row("Rahim")), null),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_FETCHED_AT).assertDoesNotExist()
    }

    @Test
    fun `a retryable failure offers retry and calls back once`() {
        var retries = 0
        compose.setContent {
            RosterScreen(
                RosterUiState.Failed("error.network.unreachable", retryable = true),
                onRetry = { retries += 1 },
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_ERROR).assertIsDisplayed()
        compose.onNodeWithTag(TAG_ROSTER_RETRY).performClick()

        assertEquals(1, retries)
    }

    @Test
    fun `a non-retryable failure offers no retry`() {
        // THE RULE [TC-9]: the button appears because the SERVER said
        // retryable. A client that offered retry on every error would be
        // deciding retryability from a status code.
        compose.setContent {
            RosterScreen(
                RosterUiState.Failed("enrollment.remove.claimed", retryable = false),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_ERROR).assertIsDisplayed()
        compose.onNodeWithTag(TAG_ROSTER_RETRY).assertDoesNotExist()
    }

    // ---------------------------------------------------------------
    // D2. These assert what the mapper tests cannot see: a correctly
    // mapped row rendered by a screen that ignores half of it is still
    // a broken screen.
    // ---------------------------------------------------------------

    @Test
    fun `a declined row is marked and a pending row is not`() {
        // [BR1.1, AC1.3.3a]. **Both halves in one test deliberately.**
        // "The declined row is marked" passes against a screen that
        // marks EVERY row, which is precisely the clutter the rule
        // forbids: pending is the normal state of a new seat and
        // decorating most rows would flag normality as a problem.
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded(
                    batchName = "Physics",
                    rows = listOf(
                        row(
                            "Refused",
                            studentState = LinkState.DECLINED,
                            isDeclined = true,
                            displayLabel = "01711-234567",
                        ),
                        row("Waiting", isDeclined = false),
                    ),
                    fetchedAtLabel = null,
                ),
                onRetry = {},
            )
        }

        assertEquals(
            1,
            compose.onAllNodesWithTag(TAG_ROSTER_DECLINED_MARK)
                .fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `a declined row shows the number and NOT the teacher-typed name`() {
        // [BR2.3, NFR14.28, ADR-012]. A mapper test proves the label
        // was chosen; only a rendering test proves the screen shows
        // nothing else. The name is RETAINED on the row — it is the
        // teacher's own record of who they meant to add — and the
        // screen must not reach for it.
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded(
                    batchName = "Physics",
                    rows = listOf(
                        row(
                            "Rahim",
                            studentState = LinkState.DECLINED,
                            isDeclined = true,
                            displayLabel = "01711-234567",
                        ),
                    ),
                    fetchedAtLabel = null,
                ),
                onRetry = {},
            )
        }

        compose.onNodeWithText("01711-234567").assertIsDisplayed()
        compose.onNodeWithText("Rahim").assertDoesNotExist()
    }

    @Test
    fun `a declined row with no number shows a placeholder, never the name`() {
        // [BR2.3]. The case the mapper returns null for: a
        // student-side decline on a seat where the teacher recorded no
        // guardian number. BR2.3's own violation_behaviour is "a name
        // is displayed for a person who has said the seat is not
        // theirs", and it makes no exception for having nothing else
        // to show -- so the screen shows the placeholder and the name
        // still must not appear.
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded(
                    batchName = "Physics",
                    rows = listOf(
                        row(
                            "Rahim",
                            studentState = LinkState.DECLINED,
                            isDeclined = true,
                            displayLabel = null,
                        ),
                    ),
                    fetchedAtLabel = null,
                ),
                onRetry = {},
            )
        }

        compose.onNodeWithText("Rahim").assertDoesNotExist()
    }

    @Test
    fun `a split seat is rendered once with both link states`() {
        // [BR2.1, AC1.10.7]. The student is enrolled and owes a fee;
        // the guardian simply does not watch. One row, two states, and
        // neither collapsed into the other.
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded(
                    batchName = "Physics",
                    rows = listOf(
                        row(
                            "Split",
                            studentState = LinkState.ACCEPTED,
                            guardianState = LinkState.DECLINED,
                            isDeclined = true,
                        ),
                    ),
                    fetchedAtLabel = null,
                ),
                onRetry = {},
            )
        }

        // ONE row, not two.
        assertEquals(
            1,
            compose.onAllNodesWithTag(TAG_ROSTER_ROW).fetchSemanticsNodes().size,
        )
        compose.onNodeWithTag(TAG_ROSTER_STUDENT_STATE).assertIsDisplayed()
        compose.onNodeWithTag(TAG_ROSTER_GUARDIAN_STATE).assertIsDisplayed()
    }

    @Test
    fun `a seat with no guardian says so rather than saying pending`() {
        // [BR2.2]. `absent` is a fourth value: a decision nobody was
        // asked for is not an outstanding one, and rendering it as
        // "not answered yet" would tell the teacher to wait for an
        // answer from a person who does not exist.
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded(
                    batchName = "Physics",
                    rows = listOf(row("Solo", guardianState = LinkState.ABSENT)),
                    fetchedAtLabel = null,
                ),
                onRetry = {},
            )
        }

        compose.onNodeWithText("Guardian · No guardian recorded").assertIsDisplayed()
    }

    @Test
    fun `remove is offered only where the server permits it`() {
        // [BR3.1, NFR14.31]. The control follows `isRemovable`, which
        // the server decided. A screen deriving it from the link states
        // would offer removal on an erased seat.
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded(
                    batchName = "Physics",
                    rows = listOf(
                        row("Removable", isRemovable = true),
                        row("Not removable", isRemovable = false),
                    ),
                    fetchedAtLabel = null,
                ),
                onRetry = {},
            )
        }

        assertEquals(
            1,
            compose.onAllNodesWithTag(TAG_ROSTER_REMOVE).fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `the count renders both server numbers`() {
        // [BR1.2, BR1.3, AC1.3.5a]. Arranged so a client tally would
        // disagree: ONE row on screen against a server count of 9 of
        // 12. A screen counting rows would show "0 of 1".
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded(
                    batchName = "Physics",
                    rows = listOf(row("Only one")),
                    fetchedAtLabel = null,
                    accepted = AcceptedCount(accepted = 9, total = 12),
                ),
                onRetry = {},
            )
        }

        compose.onNodeWithText("9 of 12 accepted").assertIsDisplayed()
    }

    @Test
    fun `THE TWO REFUSALS SHOW DIFFERENT REMEDIES`() {
        // [BR3.2, NFR23.5]. **The pair, asserted as a pair.** A test
        // showing "removal was refused" passes for both and
        // distinguishes neither; the remedies are what differ, and a
        // teacher shown the wrong one tries something that cannot work.
        //
        // The decisive difference is the ACTION, not just the words: a
        // claimed seat offers "mark inactive" and an erased one offers
        // nothing, because there is nothing that would help.
        //
        // Both remedies are rendered in one composition, side by side,
        // so the comparison is of what the screen actually draws rather
        // than of two string ids someone looked up.
        val seat = row("Rahim", isRemovable = false)

        compose.setContent {
            androidx.compose.foundation.layout.Column {
                RemoveSeatRefused(
                    row = seat,
                    remedy = RemovalRemedy.MARK_INACTIVE,
                    onMarkInactive = {},
                    onDismiss = {},
                )
                RemoveSeatRefused(
                    row = seat,
                    remedy = RemovalRemedy.NONE,
                    onMarkInactive = {},
                    onDismiss = {},
                )
            }
        }

        val remedies =
            compose.onAllNodesWithTag(TAG_ROSTER_REMEDY)
                .fetchSemanticsNodes()
                .map { it.config[SemanticsProperties.Text].first().text }

        assertEquals(2, remedies.size)
        // **The pair is distinguishable.** One sentence for both would
        // leave a teacher trying the remedy that cannot work.
        assertEquals(true, remedies[0] != remedies[1])
        // And only the claimed case offers an action.
        assertEquals(
            1,
            compose.onAllNodesWithTag(TAG_ROSTER_MARK_INACTIVE)
                .fetchSemanticsNodes().size,
        )
    }

    @Test
    fun `an erased seat offers NO remedy action, only the message`() {
        // Offering "mark inactive" here would be offering a remedy that
        // cannot work: the seat's marker must stay, because deleting it
        // would let that number reattach [BR6.2].
        compose.setContent {
            RosterScreen(
                RosterUiState.RemovalRefused(
                    row = row("Rahim", isRemovable = false),
                    messageKey = "enrollment.remove.erased",
                    remedy = RemovalRemedy.NONE,
                ),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_REMOVE_REFUSED).assertIsDisplayed()
        compose.onNodeWithTag(TAG_ROSTER_MARK_INACTIVE).assertDoesNotExist()
        // **Neither refusal offers a retry.** Both are conflicts, so
        // repeating the request unchanged cannot succeed.
        compose.onNodeWithTag(TAG_ROSTER_RETRY).assertDoesNotExist()
    }

    @Test
    fun `the removal confirmation names the seat being removed`() {
        // [W4]. "Are you sure?" about nothing in particular is a
        // confirmation people click through.
        compose.setContent {
            RosterScreen(
                RosterUiState.ConfirmingRemoval(
                    row("Rahim", displayLabel = "01711-234567"),
                ),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_REMOVE_CONFIRM).assertIsDisplayed()
        compose.onNodeWithText(
            "01711-234567 will be removed from this batch. Nothing they have " +
                "recorded is affected, because nobody has accepted this place.",
        ).assertIsDisplayed()
    }

}
