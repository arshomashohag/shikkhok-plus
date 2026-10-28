package com.shikkhokplus.app.feature.batchdetail

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.LinkState
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ScheduleSlotDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.batchdetail.ui.BatchDetailScreen
import com.shikkhokplus.app.feature.batchdetail.ui.NoticesTab
import com.shikkhokplus.app.feature.batchdetail.ui.StudentsTab
import com.shikkhokplus.app.feature.batchdetail.ui.TAG_BATCH_FAB
import com.shikkhokplus.app.feature.batchdetail.ui.TAG_BATCH_TAB
import com.shikkhokplus.app.feature.batchdetail.ui.TAG_FEES_FAILED
import com.shikkhokplus.app.feature.batchdetail.ui.TAG_STUDENT_ROW
import com.shikkhokplus.app.feature.roster.AcceptedCount
import com.shikkhokplus.app.feature.roster.RosterRow
import com.shikkhokplus.app.feature.roster.RosterUiState
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** T7, rendered: the header, the chips in the board's words, the tabs. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class BatchDetailScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun student(id: String, name: String, phone: String? = "+8801819207735") =
        RosterRow(
            enrollmentId = id,
            displayName = name,
            statusLabel = "roster.status.active",
            fee = null,
            guardianPhone = phone,
            studentState = LinkState.ACCEPTED,
            guardianState = LinkState.ACCEPTED,
            displayLabel = null,
            isDeclined = false,
            isRemovable = true,
        )

    @Test
    fun `the header names the fee and its day, and the tabs switch`() {
        val chosen = mutableListOf<BatchTab>()
        var added = 0
        compose.setContent {
            ShikkhokTheme {
                BatchDetailScreen(
                    batchName = "Physics A",
                    header =
                        BatchHeader(
                            "Physics A",
                            Money.of("1200.00"),
                            10,
                            listOf(ScheduleSlotDto(5, "16:00:00", "17:30:00")),
                            listOf("1st paper"),
                        ),
                    tab = BatchTab.STUDENTS,
                    onSelect = { chosen += it },
                    onBack = {},
                    onAdd = { added++ },
                    onSchedule = {},
                ) {}
            }
        }

        compose.onNodeWithText("৳1,200/mo · fee due on the 10th").assertExists()
        compose.onNodeWithText("4:00–5:30 pm", useUnmergedTree = true).assertExists()
        compose.onAllNodesWithTag(TAG_BATCH_TAB)[3].performClick()
        compose.onNodeWithTag(TAG_BATCH_FAB).performClick()

        assertEquals(listOf(BatchTab.NOTICES), chosen)
        assertEquals(1, added)
    }

    @Test
    fun `each student shows the server's fee position in the board's words`() {
        compose.setContent {
            ShikkhokTheme {
                StudentsTab(
                    roster =
                        RosterUiState.Loaded(
                            "Physics A",
                            listOf(student("e-1", "Jannatul"), student("e-2", "Nusrat", phone = null)),
                            null,
                            AcceptedCount(5, 7),
                        ),
                    fees =
                        FeeChips.Loaded(
                            mapOf(
                                "e-1" to FeeChip(FeeChipKind.OVERDUE, Money.of("3600.00"), 68),
                                "e-2" to FeeChip(FeeChipKind.PARTIAL, Money.of("400.00")),
                            ),
                        ),
                    onAddFirst = {},
                    onFeeHistory = {},
                    onMarkInactive = {},
                    onAskRemove = {},
                    onRemove = {},
                    onCancelRemoval = {},
                    onRetry = {},
                    onRetryFees = {},
                )
            }
        }

        compose.onNodeWithText("৳3,600 · 68 days", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("৳400 left", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("Guardian 01819-207735", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("No guardian added", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("5 of 7 accepted.").assertExists()
    }

    @Test
    fun `tapping a student offers fee history, inactive and remove`() {
        val history = mutableListOf<String>()
        compose.setContent {
            ShikkhokTheme {
                StudentsTab(
                    roster = RosterUiState.Loaded("Physics A", listOf(student("e-1", "Jannatul")), null),
                    fees = FeeChips.Failed,
                    onAddFirst = {},
                    onFeeHistory = { history += it.enrollmentId },
                    onMarkInactive = {},
                    onAskRemove = {},
                    onRemove = {},
                    onCancelRemoval = {},
                    onRetry = {},
                    onRetryFees = {},
                )
            }
        }

        compose.onNodeWithTag(TAG_FEES_FAILED).assertExists()
        compose.onNodeWithTag(TAG_STUDENT_ROW).performClick()
        compose.onNodeWithText("Fee history").performClick()

        assertEquals(listOf("e-1"), history)
    }

    @Test
    fun `a notice can be taken down after confirming`() {
        val removed = mutableListOf<String>()
        compose.setContent {
            ShikkhokTheme {
                NoticesTab(
                    notices = listOf(Notice("n-1", "Bring a calculator", "2026-10-26T09:00:00Z", edited = true)),
                    write = WriteState.Idle,
                    composing = false,
                    onCloseCompose = {},
                    onPost = {},
                    onEdit = { _, _ -> },
                    onRemove = { removed += it.id },
                    onAcknowledge = {},
                )
            }
        }

        compose.onNodeWithText("Bring a calculator").assertExists()
        compose.onNodeWithText("Remove").performClick()
        assertEquals(emptyList<String>(), removed)
        compose.onNodeWithText("Take this notice down?").assertExists()
        compose.onAllNodesWithText("Remove")[1].performClick()

        assertEquals(listOf("n-1"), removed)
    }
}
