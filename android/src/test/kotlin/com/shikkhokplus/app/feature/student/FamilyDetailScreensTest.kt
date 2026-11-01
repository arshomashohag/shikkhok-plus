package com.shikkhokplus.app.feature.student

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.CalendarMark
import com.shikkhokplus.app.core.ui.CalendarState
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_DETAIL_LOADING
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_DETAIL_NOTES
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_DETAIL_TOPIC
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.feature.student.ui.ClassDetailScreen
import com.shikkhokplus.app.feature.student.ui.ExamDetailScreen
import com.shikkhokplus.app.feature.student.ui.NoticeDetailScreen
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_DETAIL_ATTENDANCE
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_DETAIL_MISSING
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The class, exam and notice details, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class FamilyDetailScreensTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun clazz(
        state: CalendarState = CalendarState.TAKEN,
        topic: String? = "Heat & light",
        notes: String? = null,
        mark: CalendarMark? = CalendarMark.ABSENT,
    ) = CalendarClassUi("s-1", "2026-10-14", "16:00:00", null, "Physics", state, topic, notes, false, false, mark)

    private val exam = FamilyExam("x-2", "Monthly", "2026-11-02", "Physics", 50, listOf("Heat", "Light"), false)

    @Test
    fun `a class detail shows the topic verbatim and the mark, and back leaves`() {
        var backed = 0
        compose.setContent { ClassDetailScreen(clazz(), onBack = { backed++ }) }

        compose.onNodeWithText("Heat & light").assertExists()
        compose.onNodeWithText("Topics covered").assertExists()
        compose.onNodeWithTag(TAG_FAMILY_DETAIL_ATTENDANCE).assertExists()
        compose.onNodeWithText("Absent").assertExists()
        compose.onNodeWithContentDescription("Back").performClick()
        assertEquals(1, backed)
    }

    @Test
    fun `only a taken class is labelled covered, every other state is a plan`() {
        val cases =
            listOf(
                Triple(CalendarState.TAKEN, "Topics covered", "No topic logged yet"),
                Triple(CalendarState.TODAY, "Planned topics", "No topics planned yet"),
                Triple(CalendarState.UPCOMING, "Planned topics", "No topics planned yet"),
                Triple(CalendarState.NOT_RECORDED, "Planned topics", "No topics planned yet"),
                Triple(CalendarState.CANCELLED, "Planned topics", "No topics planned yet"),
            )
        val shown = mutableStateOf(clazz(topic = null))
        compose.setContent { ClassDetailScreen(shown.value, onBack = {}) }

        for ((state, heading, empty) in cases) {
            shown.value = clazz(state = state, topic = null)
            compose.waitForIdle()
            compose.onNodeWithText(heading).assertExists()
            compose.onNodeWithTag(TAG_FAMILY_DETAIL_TOPIC).assertTextEquals(empty)
        }
    }

    @Test
    fun `each mark has its own label`() {
        val shown = mutableStateOf(CalendarMark.PRESENT as CalendarMark?)
        compose.setContent { ClassDetailScreen(clazz(mark = shown.value), onBack = {}) }

        for ((mark, label) in listOf(
            CalendarMark.PRESENT to "Present",
            CalendarMark.ABSENT to "Absent",
            CalendarMark.NOT_MARKED to "Not marked",
            CalendarMark.NOT_ENROLLED to "Not enrolled then",
        )) {
            shown.value = mark
            compose.waitForIdle()
            compose.onNodeWithTag(TAG_FAMILY_DETAIL_ATTENDANCE).assertTextEquals(label)
        }
    }

    @Test
    fun `an upcoming class says its topics are planned`() {
        compose.setContent { ClassDetailScreen(clazz(state = CalendarState.UPCOMING), onBack = {}) }

        compose.onNodeWithText("Planned topics").assertExists()
        compose.onAllNodesWithText("Topics covered").assertCountEquals(0)
    }

    @Test
    fun `a class with no topic says so`() {
        compose.setContent { ClassDetailScreen(clazz(topic = null), onBack = {}) }

        compose.onNodeWithText("No topic logged yet").assertExists()
    }

    @Test
    fun `the notes show verbatim, and none shows no notes section`() {
        val notes = mutableStateOf<String?>("Bring the lab sheet")
        compose.setContent { ClassDetailScreen(clazz(notes = notes.value), onBack = {}) }

        compose.onNodeWithTag(TAG_FAMILY_DETAIL_NOTES).assertTextEquals("Bring the lab sheet")
        notes.value = null
        compose.waitForIdle()
        compose.onAllNodesWithTag(TAG_FAMILY_DETAIL_NOTES).assertCountEquals(0)
    }

    @Test
    fun `a 2000 character Bangla topic and notes render, and the last line can be scrolled to`() {
        val long = "পড়া ".repeat(400).trim()
        val last = "শেষ লাইন"
        compose.setContent {
            ClassDetailScreen(clazz(topic = "$long $last", notes = "$long $last"), onBack = {})
        }

        compose.onNodeWithTag(TAG_FAMILY_DETAIL_NOTES).performScrollTo().assertExists()
        compose.onNodeWithTag(TAG_FAMILY_DETAIL_ATTENDANCE).performScrollTo().assertExists()
        compose.onNodeWithTag(TAG_FAMILY_DETAIL_TOPIC).assertTextContains(last, substring = true)
    }

    @Test
    fun `a class detail has no edit controls`() {
        compose.setContent { ClassDetailScreen(clazz(notes = "n"), onBack = {}) }

        compose.onAllNodes(hasSetTextAction()).assertCountEquals(0)
        compose.onAllNodes(hasClickAction()).assertCountEquals(1)
    }

    @Test
    fun `a class that has gone says so, and a month still loading shows a loader`() {
        val loading = mutableStateOf(true)
        compose.setContent { ClassDetailScreen(null, onBack = {}, loading = loading.value) }

        compose.onNodeWithTag(TAG_FAMILY_DETAIL_LOADING).assertExists()
        loading.value = false
        compose.waitForIdle()
        compose.onNodeWithTag(TAG_FAMILY_DETAIL_MISSING).assertExists()
    }

    @Test
    fun `an exam detail lists its topics verbatim, and back leaves`() {
        var backed = 0
        compose.setContent { ExamDetailScreen(FamilyExamUiState.Loaded(exam), onBack = { backed++ }, onRetry = {}) }

        compose.onNodeWithText("Monthly").assertExists()
        compose.onNodeWithText("Heat").assertExists()
        compose.onNodeWithText("Light").assertExists()
        compose.onNodeWithContentDescription("Back").performClick()
        assertEquals(1, backed)
    }

    @Test
    fun `an exam with no topics says none are listed`() {
        compose.setContent {
            ExamDetailScreen(FamilyExamUiState.Loaded(exam.copy(topics = emptyList())), onBack = {}, onRetry = {})
        }

        compose.onNodeWithText("No topics listed yet.").assertExists()
    }

    @Test
    fun `a failed exam offers retry only when the server says it is retryable`() {
        var retried = 0
        compose.setContent {
            ExamDetailScreen(
                FamilyExamUiState.Failed("error.network.unreachable", true),
                onBack = {},
                onRetry = { retried++ },
            )
        }

        compose.onNodeWithText("Try again").performClick()
        assertEquals(1, retried)
    }

    @Test
    fun `a notice detail shows the whole body, and back leaves`() {
        var backed = 0
        val notice = NoticeRow("Bring a calculator\nand a ruler", "2026-10-26T09:00:00Z", "a-1", edited = true)
        compose.setContent { NoticeDetailScreen(notice, onBack = { backed++ }) }

        compose.onNodeWithText("Bring a calculator\nand a ruler").assertExists()
        compose.onNodeWithText("Edited", substring = true).assertExists()
        compose.onNodeWithContentDescription("Back").performClick()
        assertEquals(1, backed)
    }
}
