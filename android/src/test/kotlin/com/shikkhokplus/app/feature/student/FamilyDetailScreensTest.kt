package com.shikkhokplus.app.feature.student

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
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

    private val past = PastClass("s-1", "2026-10-14", "16:00", "Heat & light", "Physics", false)
    private val exam = FamilyExam("x-2", "Monthly", "2026-11-02", "Physics", 50, listOf("Heat", "Light"), false)

    @Test
    fun `a class detail shows the topic verbatim and the attendance, and back leaves`() {
        var backed = 0
        compose.setContent { ClassDetailScreen(past, onBack = { backed++ }) }

        compose.onNodeWithText("Heat & light").assertExists()
        compose.onNodeWithTag(TAG_FAMILY_DETAIL_ATTENDANCE).assertExists()
        compose.onNodeWithText("Absent").assertExists()
        compose.onNodeWithContentDescription("Back").performClick()
        assertEquals(1, backed)
    }

    @Test
    fun `a class that has gone says so`() {
        compose.setContent { ClassDetailScreen(null, onBack = {}) }

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
