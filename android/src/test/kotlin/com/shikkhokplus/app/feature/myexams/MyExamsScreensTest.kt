package com.shikkhokplus.app.feature.myexams

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.network.ExamExaminerDto
import com.shikkhokplus.app.core.network.ExamResultDto
import com.shikkhokplus.app.core.network.ExaminerResultsDto
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.MyExamDto
import com.shikkhokplus.app.feature.myexams.ui.ExaminerControl
import com.shikkhokplus.app.feature.myexams.ui.MyExamMarksActions
import com.shikkhokplus.app.feature.myexams.ui.MyExamMarksScreen
import com.shikkhokplus.app.feature.myexams.ui.MyExamsScreen
import com.shikkhokplus.app.feature.myexams.ui.TAG_MY_EXAM_PUBLISH
import com.shikkhokplus.app.feature.myexams.ui.examinerChoiceTag
import com.shikkhokplus.app.feature.myexams.ui.myExamAbsentTag
import com.shikkhokplus.app.feature.myexams.ui.myExamTag
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** An examiner's screens and the examiner control, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MyExamsScreensTest {

    @get:Rule
    val compose = createComposeRule()

    private val exam =
        MyExamDto(
            examId = "x-1",
            centreName = "Alo Coaching",
            batchName = "Physics",
            subjectName = "Mechanics",
            title = "Class test",
            date = "2026-11-06",
            totalMarks = 20,
        )

    @Test
    fun `an exam names its subject and opens on tap`() {
        val opened = mutableListOf<String>()
        compose.setContent {
            MyExamsScreen(state = Loadable.Loaded(listOf(exam)), onOpen = { opened += it }, onRetry = {})
        }
        compose.onNodeWithText("Class test · Mechanics").assertIsDisplayed()
        compose.onNodeWithTag(myExamTag("x-1")).performClick()
        assertEquals(listOf("x-1"), opened)
    }

    @Test
    fun `a sheet shows each result, marks absent, and offers publish`() {
        val absent = mutableListOf<String>()
        compose.setContent {
            MyExamMarksScreen(
                state =
                    MyExamMarksUiState(
                        sheet =
                            Loadable.Loaded(
                                ExaminerResultsDto(
                                    exam = exam,
                                    results =
                                        listOf(
                                            ExamResultDto("e-1", "Rafi", "marked", 17.5),
                                            ExamResultDto("e-2", "Mitu", "joined_after"),
                                        ),
                                    writable = true,
                                ),
                            ),
                    ),
                actions = MyExamMarksActions(onAbsent = { absent += it }),
            )
        }
        compose.onNodeWithText("17.5 / 20").assertIsDisplayed()
        compose.onNodeWithText("Joined after the exam").assertIsDisplayed()
        compose.onNodeWithTag(myExamAbsentTag("e-2")).assertDoesNotExist()
        compose.onNodeWithTag(myExamAbsentTag("e-1")).performClick()
        assertEquals(listOf("e-1"), absent)
        compose.onNodeWithTag(TAG_MY_EXAM_PUBLISH).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `the examiner control offers nobody and each member`() {
        val chosen = mutableListOf<String?>()
        compose.setContent {
            ExaminerControl(
                state =
                    ExaminerUiState(
                        exam = ExamExaminerDto("x-1", examinerMemberId = "m-1"),
                        members = listOf(MemberDto("m-1", "Karim", "+880", "teacher", "accepted")),
                    ),
                onChoose = { chosen += it },
            )
        }
        compose.onNodeWithText("Karim").assertIsDisplayed()
        compose.onNodeWithTag(examinerChoiceTag("none")).performClick()
        assertEquals(listOf<String?>(null), chosen)
    }
}
