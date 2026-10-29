package com.shikkhokplus.app.feature.student

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ScheduleSlotDto
import com.shikkhokplus.app.feature.marks.ProgressRow
import com.shikkhokplus.app.feature.student.ui.MyBatchesScreen
import com.shikkhokplus.app.feature.student.ui.StudentBatchScreen
import com.shikkhokplus.app.feature.student.ui.TAG_MY_BATCHES_EMPTY
import com.shikkhokplus.app.feature.student.ui.TAG_MY_BATCH_FEE
import com.shikkhokplus.app.feature.student.ui.TAG_MY_BATCH_ROW
import com.shikkhokplus.app.feature.student.ui.TAG_STUDENT_RESULT
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** S1 and S2, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class StudentScreensTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val row =
        StudentBatchRow(
            enrollmentId = "e-1",
            batchName = "Physics A",
            teacherName = "Mahfuz",
            schedule = listOf(ScheduleSlotDto(5, "16:00:00", "17:30:00"), ScheduleSlotDto(0, "16:00:00", "17:30:00")),
            fee = FeeLine("2026-10", "fees.status.paid", "2026-10-10", Money.of("0.00")),
        )

    @Test
    fun `a batch card shows its days, time and the server's fee status, and opens`() {
        var opened: String? = null
        compose.setContent {
            MyBatchesScreen(MyBatchesUiState.Loaded(listOf(row)), onOpen = { opened = it }, onRetry = {})
        }

        compose.onNodeWithText("Mahfuz · Sat · Mon · 4:00 pm", useUnmergedTree = true).assertExists()
        compose.onNodeWithTag(TAG_MY_BATCH_FEE, useUnmergedTree = true).assertExists()
        compose.onNodeWithText("Paid", useUnmergedTree = true).assertExists()
        compose.onNodeWithTag(TAG_MY_BATCH_ROW).performClick()
        assertEquals("e-1", opened)
    }

    @Test
    fun `the empty state gives the number a teacher adds the student by`() {
        compose.setContent {
            MyBatchesScreen(MyBatchesUiState.Empty("+8801611477203"), onOpen = {}, onRetry = {})
        }

        compose.onNodeWithTag(TAG_MY_BATCHES_EMPTY).assertIsDisplayed()
        compose.onAllNodesWithTag(TAG_MY_BATCH_ROW).fetchSemanticsNodes().let { assertEquals(0, it.size) }
    }

    @Test
    fun `a result opens its marksheet, and an absence shows as one`() {
        var exam: String? = null
        val view =
            StudentBatchView(
                batch = row,
                nextClassDate = "2026-10-31",
                nextClassStart = "16:00",
                results = listOf(ProgressRow("x-1", "Weekly 3", "2026-10-05", 50, "mark.state.absent", null)),
                notices = emptyList(),
                topics = emptyList(),
            )
        compose.setContent {
            StudentBatchScreen(
                StudentBatchUiState.Loaded(view),
                onBack = {},
                onOpenExam = { exam = it },
                onOpenFees = {},
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_STUDENT_RESULT).performScrollTo().performClick()
        assertEquals("x-1", exam)
        compose.onNodeWithText("Absent", substring = true).assertExists()
    }
}
