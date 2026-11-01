package com.shikkhokplus.app.feature.student

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ScheduleSlotDto
import com.shikkhokplus.app.feature.marks.ProgressRow

/**
 * A seat's latest fee period, as the student's screens show it.
 *
 * @property period `YYYY-MM`
 * @property statusKey A message key for the server's status, never a
 *   comparison of the amount [TC-9]
 * @property dueDate When it is due, as the server formatted it
 * @property outstanding What is still owed, shown as the server sent it
 * @property charged What the period charged, or null
 * @property verifying Whether a payment for it is being checked
 * @property paidOn The day it was last approved, `yyyy-MM-dd`, or null
 */
data class FeeLine(
    val period: String,
    val statusKey: String,
    val dueDate: String,
    val outstanding: Money,
    val charged: Money? = null,
    val verifying: Boolean = false,
    val paidOn: String? = null,
)

/**
 * A class still to come, as the server described it.
 *
 * @property date `yyyy-MM-dd`
 * @property startTime `HH:MM`
 * @property endTime `HH:MM`, or null
 * @property startsInMinutes Minutes until it starts when that is today,
 *   else null -- which is also how the screen knows to say "Today"
 * @property moved Whether the teacher moved it from its usual time
 * @property subjectName What it teaches, or null
 */
data class NextClass(
    val date: String,
    val startTime: String,
    val endTime: String?,
    val startsInMinutes: Int?,
    val moved: Boolean,
    val subjectName: String?,
)

/**
 * The latest marked result on a seat.
 *
 * @property title The exam
 * @property marks The mark
 * @property totalMarks Out of how many
 * @property rank The rank, only where the marksheet publishes it
 */
data class LastResult(val title: String, val marks: Int, val totalMarks: Int, val rank: Int?)

/**
 * The next exam to sit.
 *
 * @property title The exam
 * @property date `yyyy-MM-dd`
 * @property totalMarks Out of how many
 * @property subjectName Which subject
 */
data class UpcomingExam(val title: String, val date: String, val totalMarks: Int, val subjectName: String)

/**
 * One batch on S1.
 *
 * @property enrollmentId The student's seat, which S2 reads by
 * @property batchName The batch
 * @property teacherName The teacher, if they gave a name
 * @property schedule The weekly classes
 * @property fee The latest fee period, or null before the first
 * @property nextClass This batch's next class, or null
 * @property isNext Whether that is the student's next class anywhere
 * @property lastResult The latest marked result, or null
 * @property childName Whose seat, when a guardian is reading; else null
 */
data class StudentBatchRow(
    val enrollmentId: String,
    val batchName: String,
    val teacherName: String?,
    val schedule: List<ScheduleSlotDto>,
    val fee: FeeLine?,
    val nextClass: NextClass? = null,
    val isNext: Boolean = false,
    val lastResult: LastResult? = null,
    val childName: String? = null,
)

/** Everything S1, "My batches", renders. */
sealed interface MyBatchesUiState {
    /** A request is in flight. */
    data object Loading : MyBatchesUiState

    /**
     * Not in any batch yet.
     *
     * @property phone The number a teacher adds this student by, or
     *   null if it could not be read
     */
    data class Empty(val phone: String?) : MyBatchesUiState

    /**
     * The student's batches, in the server's order.
     *
     * @property rows One per accepted seat
     * @property name The student's own name, if they set one
     * @property phone Their number, if it could be read
     */
    data class Loaded(
        val rows: List<StudentBatchRow>,
        val name: String? = null,
        val phone: String? = null,
    ) : MyBatchesUiState

    /**
     * Something failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : MyBatchesUiState
}

/**
 * One past class whose topic the teacher logged.
 *
 * @property date The class date, as the server formatted it
 * @property topic What was covered
 * @property subjectName What the class taught, or null
 */
data class TopicRow(val date: String, val topic: String, val subjectName: String? = null)

/**
 * One notice.
 *
 * @property body The text, as the teacher typed it
 * @property postedAt When, as the server formatted it
 * @property noticeId The notice, which its detail is opened by
 * @property edited Whether the teacher changed it after posting
 */
data class NoticeRow(
    val body: String,
    val postedAt: String,
    val noticeId: String = "",
    val edited: Boolean = false,
)

/**
 * One exam, with the server's word on where it stands.
 *
 * @property examId The exam
 * @property title Its title
 * @property date `yyyy-MM-dd`
 * @property subjectName Which subject
 * @property totalMarks Out of how many
 * @property topics What it covers, as the teacher typed it
 * @property done Whether the server calls it `done` [TC-9]
 */
data class FamilyExam(
    val examId: String,
    val title: String,
    val date: String,
    val subjectName: String,
    val totalMarks: Int,
    val topics: List<String>,
    val done: Boolean,
)

/**
 * The batch's teacher as a family sees them.
 *
 * @property displayName What they are called, or null
 * @property subjects The batch's subjects
 */
data class FamilyTeacher(val displayName: String?, val subjects: List<String>) {
    /** The first letters of the first two words of the name, or null with no name. */
    val initials: String?
        get() =
            displayName
                ?.split(' ')
                ?.filter { it.isNotBlank() }
                ?.take(INITIALS)
                ?.joinToString("") { it.take(1).uppercase() }
                ?.takeIf { it.isNotEmpty() }

    private companion object {
        const val INITIALS = 2
    }
}

/** The four tabs of a batch, as a student or guardian sees it. */
enum class FamilyTab {
    /** The next class and the past ones. */
    CLASSES,

    /** Exams, upcoming then done. */
    EXAMS,

    /** The teacher's notices. */
    NOTICES,

    /** The teacher's name and subjects. */
    TEACHER,
}

/**
 * One batch from the student's side (S2).
 *
 * @property batch The batch, its teacher, schedule and fee
 * @property nextClassDate The next class's date, or null when none is
 *   scheduled
 * @property nextClassStart Its start, `HH:MM`, or null
 * @property results The student's own results, oldest first
 * @property notices The teacher's notices, newest first
 * @property topics Past classes with a logged topic, newest first
 * @property next The next class, or null
 * @property following The classes after it
 * @property upcomingExam The next exam to sit, or null
 * @property upcomingExams Exams the server calls `upcoming`, in its order
 * @property doneExams Exams the server calls `done`, in its order
 * @property teacher The teacher
 */
data class StudentBatchView(
    val batch: StudentBatchRow,
    val nextClassDate: String?,
    val nextClassStart: String?,
    val results: List<ProgressRow>,
    val notices: List<NoticeRow>,
    val topics: List<TopicRow>,
    val next: NextClass? = null,
    val following: List<NextClass> = emptyList(),
    val upcomingExam: UpcomingExam? = null,
    val upcomingExams: List<FamilyExam> = emptyList(),
    val doneExams: List<FamilyExam> = emptyList(),
    val teacher: FamilyTeacher = FamilyTeacher(null, emptyList()),
) {
    /**
     * One notice, by id.
     *
     * @param noticeId The notice
     * @return The notice, or null when it is not in this batch
     */
    fun notice(noticeId: String): NoticeRow? = notices.firstOrNull { it.noticeId == noticeId }
}

/** Everything S2 renders. */
sealed interface StudentBatchUiState {
    /** A request is in flight. */
    data object Loading : StudentBatchUiState

    /**
     * The batch, loaded.
     *
     * @property view What the screen shows
     */
    data class Loaded(val view: StudentBatchView) : StudentBatchUiState

    /**
     * Something failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : StudentBatchUiState
}

/** Everything one exam's detail renders. */
sealed interface FamilyExamUiState {
    /** A request is in flight. */
    data object Loading : FamilyExamUiState

    /**
     * The exam, loaded.
     *
     * @property exam What the screen shows
     */
    data class Loaded(val exam: FamilyExam) : FamilyExamUiState

    /**
     * Something failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : FamilyExamUiState
}
