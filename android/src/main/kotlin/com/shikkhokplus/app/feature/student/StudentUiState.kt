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
 */
data class FeeLine(
    val period: String,
    val statusKey: String,
    val dueDate: String,
    val outstanding: Money,
)

/**
 * One batch on S1.
 *
 * @property enrollmentId The student's seat, which S2 reads by
 * @property batchName The batch
 * @property teacherName The teacher, if they gave a name
 * @property schedule The weekly classes
 * @property fee The latest fee period, or null before the first
 */
data class StudentBatchRow(
    val enrollmentId: String,
    val batchName: String,
    val teacherName: String?,
    val schedule: List<ScheduleSlotDto>,
    val fee: FeeLine?,
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
     */
    data class Loaded(val rows: List<StudentBatchRow>) : MyBatchesUiState

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
 */
data class TopicRow(val date: String, val topic: String)

/**
 * One notice.
 *
 * @property body The text
 * @property postedAt When, as the server formatted it
 */
data class NoticeRow(val body: String, val postedAt: String)

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
 */
data class StudentBatchView(
    val batch: StudentBatchRow,
    val nextClassDate: String?,
    val nextClassStart: String?,
    val results: List<ProgressRow>,
    val notices: List<NoticeRow>,
    val topics: List<TopicRow>,
)

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
