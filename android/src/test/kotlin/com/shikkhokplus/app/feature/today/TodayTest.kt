package com.shikkhokplus.app.feature.today

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.OutstandingDto
import com.shikkhokplus.app.core.network.TodayClassDto
import com.shikkhokplus.app.core.network.TodayDto
import com.shikkhokplus.app.feature.today.ui.TAG_TODAY_FIRST_RUN
import com.shikkhokplus.app.feature.today.ui.TAG_TODAY_MARKS
import com.shikkhokplus.app.feature.today.ui.TAG_TODAY_OWED
import com.shikkhokplus.app.feature.today.ui.TAG_TODAY_RECORD
import com.shikkhokplus.app.feature.today.ui.TodayScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * T1, the teacher's day, rendered: what the screen offers.
 *
 * Every figure and every "next" arrives from the server; these pin
 * that the client shows them and decides nothing.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TodayTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun lesson(
        id: String,
        start: String,
        next: Boolean = false,
        topic: String? = null,
        exam: String? = null,
        status: String = "scheduled",
    ) = TodayClassDto(
        sessionId = id,
        batchId = "b-1",
        batchName = "Batch A",
        subjectName = "Physics",
        startTime = start,
        status = status,
        topic = topic,
        topicLogged = topic != null,
        attendanceVersion = 0,
        topicVersion = 0,
        isNext = next,
        startsInMinutes = if (next) 35 else null,
        examId = exam?.let { "x-1" },
        examTitle = exam,
    )

    private fun day(
        classes: List<TodayClassDto> = emptyList(),
        overdueStudents: Int = 12,
        hasBatches: Boolean = true,
    ) = TodayDto(
        date = "2026-10-17",
        outstanding = OutstandingDto(Money.of("48600.00"), Money.of("31200.00"), overdueStudents, 7),
        classes = classes,
        toVerifyCount = 0,
        hasBatches = hasBatches,
    )

    @Test
    fun `the next class offers Record, an exam class offers Marks, a recorded one neither`() {
        val recorded = mutableListOf<String>()
        val marked = mutableListOf<String>()
        val state =
            TodayStateMapper.afterLoad(
                day(
                    listOf(
                        lesson("s-1", "10:00:00", topic = "Trigonometry"),
                        lesson("s-2", "16:00:00", next = true),
                        lesson("s-3", "19:30:00", exam = "Class test 2"),
                    ),
                ),
            )
        compose.setContent {
            ShikkhokTheme {
                TodayScreen(
                    state = state,
                    onOpenDues = {},
                    onRecord = { recorded += it.sessionId },
                    onMarks = { marked += it },
                    onVerifyAll = {},
                    onCreateBatch = {},
                    onRetry = {},
                )
            }
        }

        compose.onNodeWithText("Next · in 35 min").assertExists()
        compose.onNodeWithText("Exam · Class test 2").assertExists()
        compose.onNodeWithTag(TAG_TODAY_RECORD).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_TODAY_MARKS).performScrollTo().performClick()

        assertEquals(listOf("s-2"), recorded)
        assertEquals(listOf("x-1"), marked)
    }

    @Test
    fun `the owed card shows the server's figures and opens dues`() {
        var opened = 0
        compose.setContent {
            ShikkhokTheme {
                TodayScreen(
                    state = TodayStateMapper.afterLoad(day()),
                    onOpenDues = { opened++ },
                    onRecord = {},
                    onMarks = {},
                    onVerifyAll = {},
                    onCreateBatch = {},
                    onRetry = {},
                )
            }
        }

        compose.onNodeWithText("৳48,600", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("৳31,200 overdue · 12 students", useUnmergedTree = true).assertExists()
        compose.onNodeWithTag(TAG_TODAY_OWED).performClick()

        assertEquals(1, opened)
    }

    @Test
    fun `the first run offers to create a batch`() {
        var created = 0
        compose.setContent {
            ShikkhokTheme {
                TodayScreen(
                    state = TodayUiState.FirstRun("2026-10-17"),
                    onOpenDues = {},
                    onRecord = {},
                    onMarks = {},
                    onVerifyAll = {},
                    onCreateBatch = { created++ },
                    onRetry = {},
                )
            }
        }

        compose.onNodeWithTag(TAG_TODAY_FIRST_RUN).assertExists()
        compose.onNodeWithText("Create batch").performClick()

        assertEquals(1, created)
    }
}
