package com.shikkhokplus.app.feature.today

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.verify.ClaimCard

/** Where a class stands today, as the server says. */
enum class ClassStatus {
    /** Still to happen, or under way. */
    SCHEDULED,

    /** Attendance has been taken. */
    HELD,

    /** Called off. */
    CANCELLED,
}

/**
 * Money owed across every batch (T1's first card).
 *
 * @property total Everything owed
 * @property overdue The part past its due date
 * @property overdueStudents Students with anything overdue
 * @property batchCount Batches with anything owing
 * @property showOverdue Whether there is anything overdue to show
 */
data class OwedSummary(
    val total: Money,
    val overdue: Money,
    val overdueStudents: Int,
    val batchCount: Int,
    val showOverdue: Boolean,
)

/**
 * One class today.
 *
 * @property sessionId The class
 * @property batchId Its batch
 * @property batchName The batch
 * @property subjectName The subject, where set
 * @property startTime `HH:MM`
 * @property topicVersion The version a topic write composes against
 * @property status Where it stands
 * @property topic What was covered, where logged with text
 * @property isNext The first class still to start
 * @property startsInMinutes Minutes until it starts, by the server's clock
 * @property examId An exam this batch sits today
 * @property examTitle That exam's title
 */
data class ClassRow(
    val sessionId: String,
    val batchId: String,
    val batchName: String,
    val subjectName: String?,
    val startTime: String,
    val topicVersion: Int,
    val status: ClassStatus,
    val topic: String?,
    val isNext: Boolean,
    val startsInMinutes: Int?,
    val examId: String?,
    val examTitle: String?,
)

/** Everything T1 renders. */
sealed interface TodayUiState {
    /** The day is loading. */
    data object Loading : TodayUiState

    /**
     * No batch exists yet: show how to start.
     *
     * @property date Today, `YYYY-MM-DD`
     */
    data class FirstRun(val date: String) : TodayUiState

    /**
     * The day, loaded.
     *
     * @property date Today, `YYYY-MM-DD`
     * @property owed Money owed
     * @property classes Today's classes
     * @property toVerifyCount Payments waiting
     * @property toVerify The first few of them
     */
    data class Loaded(
        val date: String,
        val owed: OwedSummary,
        val classes: List<ClassRow>,
        val toVerifyCount: Int,
        val toVerify: List<ClaimCard>,
    ) : TodayUiState

    /**
     * The day could not be read.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : TodayUiState
}
