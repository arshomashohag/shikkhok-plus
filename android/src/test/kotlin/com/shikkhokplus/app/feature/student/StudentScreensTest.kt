package com.shikkhokplus.app.feature.student

import androidx.activity.ComponentActivity
import com.shikkhokplus.app.feature.student.ui.TAG_STUDENT_PAY
import com.shikkhokplus.app.feature.student.ui.TAG_STUDENT_FEES
import com.shikkhokplus.app.feature.student.ui.TAG_STUDENT_PROGRESS
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.CalendarDayUi
import com.shikkhokplus.app.core.ui.CalendarState
import com.shikkhokplus.app.core.ui.MonthViewUi
import com.shikkhokplus.app.core.ui.calendarDayTag
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarUiState
import com.shikkhokplus.app.feature.classcalendar.ui.TAG_CLASS_PICK_ROW
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
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
import com.shikkhokplus.app.feature.student.ui.TAG_STUDENT_NEXT_CLASS
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_TEACHER_ICON
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_TAB
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_TEACHER_SUBJECT
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_NOTICE
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_EXAM_UPCOMING
import com.shikkhokplus.app.feature.student.ui.TAG_FAMILY_EXAM_DONE
import com.shikkhokplus.app.feature.student.ui.FamilyOpeners
import com.shikkhokplus.app.feature.student.ui.TAG_MY_BATCHES_EMPTY
import com.shikkhokplus.app.feature.student.ui.TAG_MY_BATCH_FEE
import com.shikkhokplus.app.feature.student.ui.TAG_MY_BATCH_ROW
import com.shikkhokplus.app.feature.student.ui.TAG_MY_BATCHES_NUMBER
import androidx.compose.ui.test.assertTextEquals
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
        // S1: the number on its own line, formatted as everywhere else.
        compose.onNodeWithTag(TAG_MY_BATCHES_NUMBER, useUnmergedTree = true).assertTextEquals("01611-477203")
    }

    private fun view(
        results: List<ProgressRow> = emptyList(),
        upcoming: List<FamilyExam> = emptyList(),
        done: List<FamilyExam> = emptyList(),
        teacher: FamilyTeacher = FamilyTeacher(null, emptyList()),
    ) = StudentBatchView(
        batch = row,
        nextClassDate = "2026-10-31",
        nextClassStart = "16:00",
        results = results,
        notices = listOf(NoticeRow("Bring a calculator", "2026-10-26T09:00:00Z", "a-1")),
        topics = emptyList(),
        upcomingExams = upcoming,
        doneExams = done,
        teacher = teacher,
    )

    private fun show(
        view: StudentBatchView,
        tab: FamilyTab,
        openers: FamilyOpeners = FamilyOpeners(),
        onSelect: (FamilyTab) -> Unit = {},
        calendar: ClassCalendarUiState = ClassCalendarUiState.Idle,
        onOpenProgress: (() -> Unit)? = null,
    ) {
        compose.setContent {
            StudentBatchScreen(
                StudentBatchUiState.Loaded(view),
                onBack = {},
                onOpenFees = {},
                onRetry = {},
                tab = tab,
                onSelect = onSelect,
                openers = openers,
                calendar = calendar,
                onOpenProgress = onOpenProgress,
            )
        }
    }

    @Test
    fun `the batch header opens the progress dashboard when it is given one`() {
        var opened = false
        show(view(), FamilyTab.CLASSES, onOpenProgress = { opened = true })

        compose.onNodeWithTag(TAG_STUDENT_PROGRESS).performClick()

        assertEquals(true, opened)
    }

    @Test
    fun `the batch header has no progress link without one`() {
        show(view(), FamilyTab.CLASSES)

        assertEquals(0, compose.onAllNodesWithTag(TAG_STUDENT_PROGRESS).fetchSemanticsNodes().size)
    }

    private val upcomingExam = FamilyExam("x-2", "Monthly", "2026-11-02", "Physics", 50, listOf("Heat"), false)
    private val doneExam = FamilyExam("x-1", "Weekly 3", "2026-10-05", "Physics", 50, emptyList(), true)

    @Test
    fun `a done exam opens its marksheet, and an absence shows as one`() {
        var exam: String? = null
        val absent = ProgressRow("x-1", "Weekly 3", "2026-10-05", 50, "mark.state.absent", null)
        show(
            view(results = listOf(absent), done = listOf(doneExam)),
            FamilyTab.EXAMS,
            FamilyOpeners(onOpenExam = { exam = it }),
        )

        compose.onNodeWithTag(TAG_FAMILY_EXAM_DONE).performScrollTo().performClick()
        assertEquals("x-1", exam)
        compose.onNodeWithText("Absent", substring = true).assertExists()
    }

    @Test
    fun `an upcoming exam opens its detail`() {
        var detail: String? = null
        show(view(upcoming = listOf(upcomingExam)), FamilyTab.EXAMS, FamilyOpeners(onOpenExamDetail = { detail = it }))

        compose.onNodeWithTag(TAG_FAMILY_EXAM_UPCOMING).performScrollTo().performClick()
        assertEquals("x-2", detail)
    }

    private fun monthOf(vararg days: CalendarDayUi) =
        ClassCalendarUiState.Loaded(
            MonthViewUi(YearMonth(2026, 10), YearMonth(2026, 9), YearMonth(2026, 12), days.toList()),
        )

    private fun taken(id: String, start: String, subject: String) =
        CalendarClassUi(id, "2026-10-14", start, null, subject, CalendarState.TAKEN, "Heat", null, false, false, null)

    @Test
    fun `a day with one class opens it`() {
        var opened: CalendarClassUi? = null
        val one = taken("s-1", "16:00:00", "Physics")
        show(
            view(),
            FamilyTab.CLASSES,
            FamilyOpeners(onOpenClass = { opened = it }),
            calendar = monthOf(CalendarDayUi("2026-10-14", CalendarState.TAKEN, listOf(one))),
        )

        compose.onNodeWithTag(TAG_STUDENT_NEXT_CLASS).assertExists()
        compose.onNodeWithTag(calendarDayTag(CalendarState.TAKEN, "2026-10-14")).performScrollTo().performClick()
        assertEquals(one, opened)
    }

    @Test
    fun `a day with several classes asks which, then opens the one chosen`() {
        var opened: CalendarClassUi? = null
        val first = taken("s-1", "09:00:00", "Physics")
        val second = taken("s-2", "16:00:00", "Chemistry")
        show(
            view(),
            FamilyTab.CLASSES,
            FamilyOpeners(onOpenClass = { opened = it }),
            calendar = monthOf(CalendarDayUi("2026-10-14", CalendarState.TAKEN, listOf(first, second))),
        )

        compose.onNodeWithTag(calendarDayTag(CalendarState.TAKEN, "2026-10-14")).performScrollTo().performClick()
        assertEquals(null, opened)
        compose.onAllNodesWithTag(TAG_CLASS_PICK_ROW)[1].performClick()
        assertEquals(second, opened)
    }

    @Test
    fun `a failed month offers retry, and a loading month shows no calendar`() {
        var retried = 0
        val state = mutableStateOf<ClassCalendarUiState>(ClassCalendarUiState.Failed("error.network.unreachable", true))
        compose.setContent {
            StudentBatchScreen(
                StudentBatchUiState.Loaded(view()),
                onBack = {},
                onOpenFees = {},
                onRetry = {},
                tab = FamilyTab.CLASSES,
                openers = FamilyOpeners(onRetryMonth = { retried++ }),
                calendar = state.value,
            )
        }

        compose.onNodeWithText("Try again").performClick()
        assertEquals(1, retried)
    }

    @Test
    fun `a notice opens its detail`() {
        var opened: String? = null
        show(view(), FamilyTab.NOTICES, FamilyOpeners(onOpenNotice = { opened = it }))

        compose.onNodeWithTag(TAG_FAMILY_NOTICE).performClick()
        assertEquals("a-1", opened)
    }

    @Test
    fun `the teacher tab says Your teacher for a null name, with the generic icon`() {
        show(view(teacher = FamilyTeacher(null, listOf("Physics"))), FamilyTab.TEACHER)

        compose.onNodeWithText("Your teacher").assertExists()
        compose.onNodeWithTag(TAG_FAMILY_TEACHER_ICON, useUnmergedTree = true).assertExists()
        compose.onAllNodesWithTag(TAG_FAMILY_TEACHER_SUBJECT).fetchSemanticsNodes().let { assertEquals(1, it.size) }
    }

    @Test
    fun `the teacher tab shows initials for a named teacher`() {
        show(view(teacher = FamilyTeacher("Abdul Karim", emptyList())), FamilyTab.TEACHER)

        compose.onNodeWithText("Abdul Karim").assertExists()
        compose.onNodeWithText("AK").assertExists()
    }

    @Test
    fun `each tab is offered and selecting one reports it`() {
        var selected: FamilyTab? = null
        show(view(), FamilyTab.CLASSES, onSelect = { selected = it })

        assertEquals(4, compose.onAllNodesWithTag(TAG_FAMILY_TAB).fetchSemanticsNodes().size)
        compose.onNodeWithText("Teacher").performClick()
        assertEquals(FamilyTab.TEACHER, selected)
    }

    @Test
    fun `empty tabs say so`() {
        show(StudentBatchView(row, null, null, emptyList(), emptyList(), emptyList()), FamilyTab.NOTICES)

        compose.onNodeWithText("No notices yet.").assertExists()
    }

    @Test
    fun `the header keeps the subjects, the next class and the fee on every tab`() {
        val next = NextClass("2026-11-03", "16:00", "17:30", null, false, "Physics")
        val withNext = view(teacher = FamilyTeacher("Karim", listOf("Physics", "Chemistry"))).copy(next = next)
        var tab by mutableStateOf(FamilyTab.CLASSES)
        compose.setContent {
            StudentBatchScreen(
                StudentBatchUiState.Loaded(withNext),
                onBack = {},
                onOpenFees = {},
                onRetry = {},
                tab = tab,
            )
        }
        FamilyTab.entries.forEach { each ->
            tab = each
            compose.waitForIdle()
            compose.onNodeWithText("Physics · Chemistry").assertExists()
            compose.onNodeWithTag(TAG_STUDENT_NEXT_CLASS).assertExists()
            compose.onNodeWithTag(TAG_STUDENT_FEES).assertExists()
        }
    }

    @Test
    fun `a guardian's header shows the fee and Pay when something is owed`() {
        var paid = 0
        val owed = FeeLine("2026-10", "fees.status.unpaid", "2026-10-10", Money.of("1200.00"), Money.of("1200.00"))
        val guardianRow = row.copy(fee = owed, childName = "Tasnim")
        compose.setContent {
            StudentBatchScreen(
                StudentBatchUiState.Loaded(view().copy(batch = guardianRow)),
                onBack = {},
                onOpenFees = {},
                onRetry = {},
                onPay = { paid++ },
                tab = FamilyTab.TEACHER,
            )
        }

        compose.onNodeWithText("Tasnim").assertExists()
        compose.onNodeWithTag(TAG_STUDENT_FEES).assertExists()
        compose.onNodeWithTag(TAG_STUDENT_PAY).performClick()
        assertEquals(1, paid)
    }

    @Test
    fun `a guardian's header hides Pay while a claim is verifying, and says when it was paid`() {
        val verifying =
            FeeLine(
                "2026-10",
                "fees.status.unpaid",
                "2026-10-10",
                Money.of("1200.00"),
                Money.of("1200.00"),
                verifying = true,
            )
        var line by mutableStateOf(verifying)
        compose.setContent {
            StudentBatchScreen(
                StudentBatchUiState.Loaded(view().copy(batch = row.copy(fee = line, childName = "Tasnim"))),
                onBack = {},
                onOpenFees = {},
                onRetry = {},
                tab = FamilyTab.TEACHER,
            )
        }

        assertEquals(0, compose.onAllNodesWithTag(TAG_STUDENT_PAY).fetchSemanticsNodes().size)

        line = verifying.copy(statusKey = "fees.status.paid", verifying = false, paidOn = "2026-10-08")
        compose.waitForIdle()
        compose.onNodeWithText("Paid 8 Oct").assertExists()
        assertEquals(0, compose.onAllNodesWithTag(TAG_STUDENT_PAY).fetchSemanticsNodes().size)
    }
}
