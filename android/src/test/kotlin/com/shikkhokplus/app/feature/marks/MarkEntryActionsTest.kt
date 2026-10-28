package com.shikkhokplus.app.feature.marks

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.marks.ui.MarkEntryScreen
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_EDIT_EXAM
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_HISTORY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The mark-entry screen's two teacher actions: edit the exam, see a seat's history. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MarkEntryActionsTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun entry(writable: Boolean = true) =
        MarksUiState.EntryLoaded(
            examId = "x-1",
            examTitle = "Mid-term",
            totalMarks = 50,
            rows = listOf(MarkRow("e-1", "Rahim", "mark.state.marked", 40, isEditable = writable, hasHistory = true)),
            writable = writable,
            examDate = "2026-11-04",
        )

    @Test
    fun `the pencil edits the exam and the history link opens a seat's marks`() {
        var edits = 0
        val opened = mutableListOf<String>()
        compose.setContent {
            ShikkhokTheme {
                MarkEntryScreen(
                    state = entry(),
                    onEditExam = { edits++ },
                    onHistory = { opened += it.enrollmentId },
                )
            }
        }

        compose.onNodeWithTag(TAG_MARK_ENTRY_EDIT_EXAM).performClick()
        compose.onNodeWithTag(TAG_MARK_ENTRY_HISTORY, useUnmergedTree = true).performClick()

        assertEquals(1, edits)
        assertEquals(listOf("e-1"), opened)
    }

    @Test
    fun `a closed batch's exam offers no edit`() {
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = entry(writable = false)) } }

        compose.onNodeWithTag(TAG_MARK_ENTRY_EDIT_EXAM).assertDoesNotExist()
    }
}
