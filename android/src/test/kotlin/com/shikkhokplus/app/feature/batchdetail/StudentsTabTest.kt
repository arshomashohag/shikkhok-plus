package com.shikkhokplus.app.feature.batchdetail

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.designsystem.TAG_ERROR_RETRY
import com.shikkhokplus.app.core.designsystem.TAG_SKELETON
import com.shikkhokplus.app.core.model.LinkState
import com.shikkhokplus.app.feature.batchdetail.ui.StudentsTab
import com.shikkhokplus.app.feature.batchdetail.ui.TAG_STUDENTS_SAVED
import com.shikkhokplus.app.feature.batchdetail.ui.TAG_STUDENT_ROW
import com.shikkhokplus.app.feature.roster.RemovalRemedy
import com.shikkhokplus.app.feature.roster.RosterRow
import com.shikkhokplus.app.feature.roster.RosterUiState
import com.shikkhokplus.app.feature.roster.ui.RemoveSeatRefused
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_MARK_INACTIVE
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_REMEDY
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_REMOVE_CONFIRM
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_REMOVE_REFUSED
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The Students tab's roster rules (D2), moved here with the roster when
 * it became T7's first tab. These assert what the mapper tests cannot
 * see: that a correctly mapped row is drawn the way the rule requires.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class StudentsTabTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun row(
        name: String,
        studentState: LinkState = LinkState.ACCEPTED,
        guardianState: LinkState = LinkState.ABSENT,
        displayLabel: String? = name,
        isDeclined: Boolean = false,
        isRemovable: Boolean = true,
        guardianPhone: String? = null,
    ) = RosterRow(
        enrollmentId = "e-$name",
        displayName = name,
        statusLabel = "roster.status.active",
        fee = null,
        guardianPhone = guardianPhone,
        studentState = studentState,
        guardianState = guardianState,
        displayLabel = displayLabel,
        isDeclined = isDeclined,
        isRemovable = isRemovable,
    )

    private fun render(state: RosterUiState, retries: MutableList<Unit> = mutableListOf()) {
        compose.setContent {
            ShikkhokTheme {
                StudentsTab(
                    roster = state,
                    fees = FeeChips.Loaded(emptyMap()),
                    onAddFirst = {},
                    onFeeHistory = {},
                    onMarkInactive = {},
                    onAskRemove = {},
                    onRemove = {},
                    onCancelRemoval = {},
                    onRetry = { retries += Unit },
                    onRetryFees = {},
                )
            }
        }
    }

    @Test
    fun `loading draws placeholders, not a blank page`() {
        render(RosterUiState.Loading)

        compose.onNodeWithTag(TAG_SKELETON).assertExists()
    }

    @Test
    fun `an empty batch explains itself and offers the first student`() {
        render(RosterUiState.Empty("Physics A"))

        compose.onNodeWithText("No students yet").assertExists()
        compose.onNodeWithText("Add first student").assertExists()
    }

    @Test
    fun `saved data says so, and live data does not`() {
        render(RosterUiState.Loaded("Physics A", listOf(row("Rahim")), fetchedAtLabel = "10:42 am"))

        compose.onNodeWithTag(TAG_STUDENTS_SAVED).assertExists()
    }

    @Test
    fun `live data shows no staleness notice`() {
        render(RosterUiState.Loaded("Physics A", listOf(row("Rahim")), fetchedAtLabel = null))

        compose.onNodeWithTag(TAG_STUDENTS_SAVED).assertDoesNotExist()
    }

    @Test
    fun `a retryable failure offers retry and calls back once`() {
        val retries = mutableListOf<Unit>()
        render(RosterUiState.Failed("error.network.unreachable", retryable = true), retries)

        compose.onNodeWithTag(TAG_ERROR_RETRY).performClick()

        assertEquals(1, retries.size)
    }

    @Test
    fun `a non-retryable failure offers no retry`() {
        render(RosterUiState.Failed("error.unexpected", retryable = false))

        compose.onNodeWithTag(TAG_ERROR_RETRY).assertDoesNotExist()
    }

    @Test
    fun `a declined row shows the number and NOT the teacher-typed name`() {
        // [BR2.3, NFR14.28]. A name names a person who said the seat is
        // not theirs; the number is what the teacher must correct.
        render(
            RosterUiState.Loaded(
                "Physics A",
                listOf(row("Rahim", LinkState.DECLINED, displayLabel = "+8801711234567", isDeclined = true)),
                null,
            ),
        )

        compose.onNodeWithText("01711-234567", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("Rahim", useUnmergedTree = true).assertDoesNotExist()
        compose.onNodeWithText("Declined", useUnmergedTree = true).assertExists()
    }

    @Test
    fun `a declined row with no number shows a placeholder, never the name`() {
        render(
            RosterUiState.Loaded(
                "Physics A",
                listOf(row("Rahim", LinkState.DECLINED, displayLabel = null, isDeclined = true)),
                null,
            ),
        )

        compose.onNodeWithText("Declined seat (no number recorded)", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("Rahim", useUnmergedTree = true).assertDoesNotExist()
    }

    @Test
    fun `a seat with no guardian says so, and a guardian who declined says that`() {
        render(
            RosterUiState.Loaded(
                "Physics A",
                listOf(
                    row("Rahim"),
                    row("Karima", guardianState = LinkState.DECLINED, guardianPhone = "+8801819552041"),
                ),
                null,
            ),
        )

        compose.onNodeWithText("No guardian added", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("Guardian declined", useUnmergedTree = true).assertExists()
    }

    @Test
    fun `a student who has not answered is named as such`() {
        render(RosterUiState.Loaded("Physics A", listOf(row("Rahim", studentState = LinkState.PENDING)), null))

        compose.onNodeWithText("No guardian added · Not answered yet", useUnmergedTree = true).assertExists()
    }

    @Test
    fun `remove is offered only where the server permits it`() {
        render(
            RosterUiState.Loaded(
                "Physics A",
                listOf(row("Rahim", isRemovable = true), row("Karima", isRemovable = false)),
                null,
            ),
        )

        compose.onAllNodesWithTag(TAG_STUDENT_ROW)[0].performClick()
        compose.onNodeWithText("Remove").assertExists()
        compose.onAllNodesWithTag(TAG_STUDENT_ROW)[1].performClick()
        compose.onNodeWithText("Remove").assertDoesNotExist()
    }

    @Test
    fun `THE TWO REFUSALS SHOW DIFFERENT REMEDIES`() {
        // [BR3.2, NFR23.5]. The remedies differ and only the claimed
        // case offers an action; a teacher shown the wrong one tries
        // something that cannot work.
        val seat = row("Rahim", isRemovable = false)
        compose.setContent {
            ShikkhokTheme {
                Column {
                    RemoveSeatRefused(seat, RemovalRemedy.MARK_INACTIVE, {}, {})
                    RemoveSeatRefused(seat, RemovalRemedy.NONE, {}, {})
                }
            }
        }

        val remedies =
            compose.onAllNodesWithTag(TAG_ROSTER_REMEDY)
                .fetchSemanticsNodes()
                .map { it.config[SemanticsProperties.Text].first().text }

        assertEquals(2, remedies.size)
        assertEquals(true, remedies[0] != remedies[1])
        assertEquals(1, compose.onAllNodesWithTag(TAG_ROSTER_MARK_INACTIVE).fetchSemanticsNodes().size)
    }

    @Test
    fun `an erased seat's refusal offers no remedy action and no retry`() {
        render(
            RosterUiState.RemovalRefused(
                row("Rahim", isRemovable = false),
                "enrollment.remove.erased",
                RemovalRemedy.NONE,
            ),
        )

        compose.onNodeWithTag(TAG_ROSTER_REMOVE_REFUSED).assertExists()
        compose.onNodeWithTag(TAG_ROSTER_MARK_INACTIVE).assertDoesNotExist()
        compose.onNodeWithTag(TAG_ERROR_RETRY).assertDoesNotExist()
    }

    @Test
    fun `the removal confirmation names the seat being removed`() {
        render(RosterUiState.ConfirmingRemoval(row("Rahim", displayLabel = "01711-234567")))

        compose.onNodeWithTag(TAG_ROSTER_REMOVE_CONFIRM).assertExists()
        compose.onNodeWithText("01711-234567", substring = true).assertExists()
    }
}
