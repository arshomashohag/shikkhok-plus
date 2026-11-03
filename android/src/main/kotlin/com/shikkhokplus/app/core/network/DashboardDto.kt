package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The headline figures on the progress dashboard.
 *
 * Every figure is the server's. [owed] is a [Money], so it decodes from
 * a JSON string and fails loudly on a JSON number [TC-7, D-20].
 *
 * @property attendancePercent Present as a percent of held, or null
 * @property present Held classes attended
 * @property held Classes held
 * @property examAveragePercent Mean of the seat's exam percents, or null
 * @property direction `up`, `down` or `same`, or null
 * @property owed What the seat owes now
 */
@Serializable
data class DashboardTilesDto(
    @SerialName("attendance_percent") val attendancePercent: Int? = null,
    val present: Int,
    val held: Int,
    @SerialName("exam_average_percent") val examAveragePercent: Int? = null,
    val direction: String? = null,
    val owed: Money,
)

/**
 * One month of attendance.
 *
 * @property period `YYYY-MM`
 * @property held Classes held
 * @property present Classes attended
 * @property percent Present as a percent of held, or null
 * @property inProgress Whether the month contains today
 */
@Serializable
data class DashboardAttendanceMonthDto(
    val period: String,
    val held: Int,
    val present: Int,
    val percent: Int? = null,
    @SerialName("in_progress") val inProgress: Boolean,
)

/**
 * One exam on the chart.
 *
 * @property examId The exam
 * @property title Its title
 * @property date `yyyy-MM-dd`
 * @property subject The subject, or null
 * @property marks The seat's mark, or null for an absence
 * @property total The exam's denominator
 * @property percent The mark as a whole percent, or null
 * @property batchAverage The batch's mean mark, or null
 * @property batchHighest The batch's highest mark, or null
 */
@Serializable
data class DashboardExamDto(
    @SerialName("exam_id") val examId: String,
    val title: String,
    val date: String,
    val subject: String? = null,
    val marks: Int? = null,
    val total: Int,
    val percent: Int? = null,
    @SerialName("batch_average") val batchAverage: Int? = null,
    @SerialName("batch_highest") val batchHighest: Int? = null,
)

/**
 * One month on the fee strip.
 *
 * @property period `YYYY-MM`
 * @property state `paid`, `partly_paid`, `unpaid`, `waived` or `checking`
 */
@Serializable
data class DashboardFeeMonthDto(
    val period: String,
    val state: String,
)

/**
 * Everything the dashboard draws for one seat.
 *
 * @property tiles The headline figures
 * @property attendanceByMonth Oldest first
 * @property exams Oldest first; empty when the marksheet is not shared
 * @property feeMonths Oldest first
 */
@Serializable
data class DashboardDto(
    val tiles: DashboardTilesDto,
    @SerialName("attendance_by_month") val attendanceByMonth: List<DashboardAttendanceMonthDto> = emptyList(),
    val exams: List<DashboardExamDto> = emptyList(),
    @SerialName("fee_months") val feeMonths: List<DashboardFeeMonthDto> = emptyList(),
)
