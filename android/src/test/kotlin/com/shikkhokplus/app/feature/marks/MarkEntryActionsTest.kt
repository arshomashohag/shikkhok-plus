package com.shikkhokplus.app.feature.marks

import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_TO_ENTER
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_PUBLISHED
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_PUBLISH
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.activity.ComponentActivity
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.FakeHaptics
import com.shikkhokplus.app.core.designsystem.LocalHaptics
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.marks.ui.MarkEntryScreen
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_ABSENT
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_EDIT_EXAM
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_HISTORY
import androidx.compose.ui.test.onNodeWithText
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_EMPTY
import androidx.compose.ui.test.assertTextEquals
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_KEY
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_NEXT
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_BACKSPACE
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_COUNTER
import com.shikkhokplus.app.feature.marks.ui.TAG_MARK_ENTRY_DOCK
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
            rows = listOf(MarkRow("e-1", "Rahim", "mark.state.marked", 40.0, isEditable = writable, hasHistory = true)),
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

    @Test
    fun `marking a student absent ticks once`() {
        val haptics = FakeHaptics()
        compose.setContent {
            CompositionLocalProvider(LocalHaptics provides haptics) {
                ShikkhokTheme { MarkEntryScreen(state = entry()) }
            }
        }

        compose.onNodeWithTag(TAG_MARK_ENTRY_ABSENT).performClick()

        assertEquals(listOf("tick"), haptics.felt)
    }

    @Test
    fun `the exam is the title and what it is out of the subtitle`() {
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = entry()) } }

        compose.onNodeWithText("Mid-term").assertExists()
        compose.onNodeWithText("out of 50").assertExists()
    }

    @Test
    fun `an exam in a batch with no students says so`() {
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = entry().copy(rows = emptyList())) } }

        compose.onNodeWithTag(TAG_MARK_ENTRY_EMPTY).assertExists()
    }

    private fun two() =
        entry().copy(
            rows =
                listOf(
                    MarkRow("e-1", "Rahim", "mark.state.marked", 40.0, isEditable = true),
                    MarkRow("e-2", "Karim", "mark.state.not_entered", null, isEditable = true),
                    MarkRow("e-3", "Selim", "mark.state.not_entered", null, isEditable = true),
                ),
        )

    @Test
    fun `entry opens on the first seat with no mark`() {
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = two()) } }

        compose.onNodeWithText("02 · now entering").assertExists()
    }

    @Test
    fun `digits typed on the keypad are saved by Next, which moves down`() {
        val saved = mutableListOf<Pair<String, Double>>()
        compose.setContent {
            ShikkhokTheme {
                MarkEntryScreen(state = two(), onMark = { row, mark -> saved += row.enrollmentId to mark })
            }
        }

        compose.onNodeWithTag(TAG_MARK_ENTRY_KEY + "_2").performClick()
        compose.onNodeWithTag(TAG_MARK_ENTRY_KEY + "_2").performClick()
        compose.onNodeWithTag(TAG_MARK_ENTRY_NEXT).performClick()

        assertEquals(listOf("e-2" to 22.0), saved)
        compose.onNodeWithText("03 · now entering").assertExists()
    }

    @Test
    fun `next with nothing typed saves nothing, because empty is not zero`() {
        val saved = mutableListOf<Double>()
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = two(), onMark = { _, mark -> saved += mark }) } }

        compose.onNodeWithTag(TAG_MARK_ENTRY_NEXT).performClick()

        assertEquals(emptyList(), saved)
    }

    @Test
    fun `backspace removes the last digit before it is saved`() {
        val saved = mutableListOf<Double>()
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = two(), onMark = { _, mark -> saved += mark }) } }

        compose.onNodeWithTag(TAG_MARK_ENTRY_KEY + "_1").performClick()
        compose.onNodeWithTag(TAG_MARK_ENTRY_KEY + "_9").performClick()
        compose.onNodeWithTag(TAG_MARK_ENTRY_BACKSPACE).performClick()
        compose.onNodeWithTag(TAG_MARK_ENTRY_NEXT).performClick()

        assertEquals(listOf(1.0), saved)
    }

    @Test
    fun `the counter says how many seats have a mark`() {
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = two()) } }

        compose.onNodeWithTag(TAG_MARK_ENTRY_COUNTER).assertTextEquals("1/3")
    }

    @Test
    fun `a closed exam has no keypad`() {
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = two().copy(writable = false)) } }

        compose.onNodeWithTag(TAG_MARK_ENTRY_DOCK).assertDoesNotExist()
    }

    @Test
    fun `the point key types a decimal mark, two places at most`() {
        // Decided 2026-11-05: a mark may be decimal, such as 19.5.
        val saved = mutableListOf<Double>()
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = two(), onMark = { _, mark -> saved += mark }) } }

        listOf("1", "9", ".", ".", "2", "5", "7").forEach { key ->
            compose.onNodeWithTag(TAG_MARK_ENTRY_KEY + "_" + key).performClick()
        }
        compose.onNodeWithTag(TAG_MARK_ENTRY_NEXT).performClick()

        assertEquals(listOf(19.25), saved, "a second point and a third decimal are ignored")
    }

    @Test
    fun `publish appears once every seat has a result, and says when it is out`() {
        // Decided 2026-11-05: marks are the teacher's draft until published.
        var publishes = 0
        var state by mutableStateOf<MarksUiState>(entry().copy(toEnter = 2))
        compose.setContent { ShikkhokTheme { MarkEntryScreen(state = state, onPublish = { publishes++ }) } }

        compose.onNodeWithTag(TAG_MARK_ENTRY_TO_ENTER).assertExists()
        compose.onNodeWithTag(TAG_MARK_ENTRY_PUBLISH).assertDoesNotExist()

        state = entry()
        compose.waitForIdle()
        compose.onNodeWithTag(TAG_MARK_ENTRY_PUBLISH).performClick()
        assertEquals(1, publishes)

        state = entry().copy(published = true)
        compose.waitForIdle()
        compose.onNodeWithTag(TAG_MARK_ENTRY_PUBLISHED).assertExists()
        compose.onNodeWithTag(TAG_MARK_ENTRY_PUBLISH).assertDoesNotExist()
    }
}
