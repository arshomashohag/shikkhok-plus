package com.shikkhokplus.app.feature.dashboard

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.DashboardAttendanceMonthDto
import com.shikkhokplus.app.core.network.DashboardExamDto
import com.shikkhokplus.app.feature.fees.StripKind

/**
 * A child the guardian can switch to.
 *
 * @property key The child's first seat, which names them
 * @property name The teacher-typed name
 * @property batches The child's batches
 */
data class DashboardChild(
    val key: String,
    val name: String,
    val batches: List<DashboardBatch>,
)

/**
 * A batch the picker can switch to.
 *
 * @property seat The child's or student's seat in it
 * @property name The batch
 */
data class DashboardBatch(
    val seat: String,
    val name: String,
)

/**
 * One month on the fee strip.
 *
 * @property period `YYYY-MM`
 * @property kind The server-decided state
 */
data class DashboardFeeMonth(
    val period: String,
    val kind: StripKind,
)

/** Which way the latest run of exam results went, as the server said. */
enum class DashboardDirection {
    /** Improving. */
    UP,

    /** Unchanged. */
    SAME,

    /** Slipping. */
    DOWN,
}

/** What the progress dashboard (D1, D2) renders. */
sealed interface DashboardUiState {
    /** Nothing has arrived yet. */
    data object Loading : DashboardUiState

    /**
     * The read failed.
     *
     * @property messageKey The server's message key
     * @property retryable Whether the server said retrying could help
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : DashboardUiState

    /**
     * The dashboard, drawn from the server's figures only.
     *
     * @property reader Who is reading
     * @property heading Whose progress
     * @property subheading Which batch
     * @property range How far back
     * @property children A guardian's children; empty for the other readers
     * @property selectedChild The child in view
     * @property batches The batches the picker offers
     * @property seat The seat in view
     * @property attendancePercent Attendance tile, or null
     * @property present Classes attended
     * @property held Classes held
     * @property examAveragePercent Exam tile, or null
     * @property direction The exam run's direction, or null
     * @property owed What the seat owes now, as the server sent it
     * @property attendance Attendance by month, oldest first
     * @property exams Exams, oldest first; empty when marks are not shared
     * @property feeMonths The fee strip, oldest first
     * @property refreshing Whether a new range or seat is being read
     */
    data class Loaded(
        val reader: DashboardReader,
        val heading: String,
        val subheading: String,
        val range: DashboardRange,
        val children: List<DashboardChild>,
        val selectedChild: String?,
        val batches: List<DashboardBatch>,
        val seat: String,
        val attendancePercent: Int?,
        val present: Int,
        val held: Int,
        val examAveragePercent: Int?,
        val direction: DashboardDirection?,
        val owed: Money,
        val attendance: List<DashboardAttendanceMonthDto>,
        val exams: List<DashboardExamDto>,
        val feeMonths: List<DashboardFeeMonth>,
        val refreshing: Boolean = false,
    ) : DashboardUiState {
        /** Whether this reader can send money from here. */
        val canSendMoney: Boolean get() = reader != DashboardReader.TEACHER
    }
}
