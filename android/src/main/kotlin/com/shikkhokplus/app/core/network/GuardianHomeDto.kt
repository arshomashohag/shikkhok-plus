package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A child's latest marked result in one batch, with the server's trend.
 *
 * @property enrollmentId The seat
 * @property batchName The batch
 * @property title The exam
 * @property date When it was sat
 * @property marks The mark
 * @property totalMarks Out of how many
 * @property previousMarks The mark before it, or null
 * @property trend `up`, `down`, `same` or `first`
 */
@Serializable
data class ChildResultDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_name") val batchName: String,
    val title: String,
    val date: String,
    val marks: Int,
    @SerialName("total_marks") val totalMarks: Int,
    @SerialName("previous_marks") val previousMarks: Int? = null,
    val trend: String,
)

/**
 * One of a child's batches, with its next class.
 *
 * @property enrollmentId The seat
 * @property batchName The batch
 * @property teacherDisplayName The teacher, or null
 * @property nextSession The next class, or null
 */
@Serializable
data class ChildBatchDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("teacher_display_name") val teacherDisplayName: String? = null,
    @SerialName("next_session") val nextSession: UpcomingSessionDto? = null,
)

/**
 * One child on G1.
 *
 * @property key The child's first seat, which names them in other reads
 * @property displayName The teacher-typed name
 * @property batchCount How many batches
 * @property nextPayment The most urgent fee to pay, or null
 * @property waiting Payments sent and being checked
 * @property latestResults Each batch's latest marked result
 * @property batches The batches, with their next classes
 */
@Serializable
data class ChildSummaryDto(
    val key: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("batch_count") val batchCount: Int,
    @SerialName("next_payment") val nextPayment: PayableDto? = null,
    val waiting: List<WaitingPaymentDto> = emptyList(),
    @SerialName("latest_results") val latestResults: List<ChildResultDto> = emptyList(),
    val batches: List<ChildBatchDto> = emptyList(),
)

/**
 * Every child this guardian has accepted.
 *
 * @property children The children; empty before any is linked
 */
@Serializable
data class GuardianHomeDto(
    val children: List<ChildSummaryDto> = emptyList(),
)

/**
 * One batch's fee in one month (G3).
 *
 * @property enrollmentId The seat
 * @property batchName The batch
 * @property amount What the month charged
 * @property state `paid`, `partly_paid`, `waived`, `verifying` or `due`
 * @property dueDate When it was due
 * @property sentOn When the latest payment was sent, or null
 * @property decidedOn When it was approved, or null
 * @property channel Which app, or null
 */
@Serializable
data class PaymentLineDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_name") val batchName: String,
    val amount: Money,
    val state: String,
    @SerialName("due_date") val dueDate: String,
    @SerialName("sent_on") val sentOn: String? = null,
    @SerialName("decided_on") val decidedOn: String? = null,
    val channel: String? = null,
)

/**
 * One month's fees across the child's batches.
 *
 * @property period `YYYY-MM`
 * @property lines One per batch charged that month
 */
@Serializable
data class PaymentMonthDto(
    val period: String,
    val lines: List<PaymentLineDto> = emptyList(),
)

/**
 * A child's fee history, newest month first (G3).
 *
 * @property displayName The child
 * @property year The year the total covers
 * @property paidThisYear What payments approved this year came to
 * @property months The months
 */
@Serializable
data class PaymentsDto(
    @SerialName("display_name") val displayName: String,
    val year: Int,
    @SerialName("paid_this_year") val paidThisYear: Money,
    val months: List<PaymentMonthDto> = emptyList(),
)

/**
 * G2's reading of a child's latest run of results.
 *
 * @property direction `up`, `down` or `same`
 * @property run How many tests the run spans
 * @property firstMarks The run's first mark
 * @property lastMarks Its last mark
 * @property totalMarks The last test's total
 * @property aboveAverage Whether the last mark beats the batch average, or null
 */
@Serializable
data class ProgressSummaryDto(
    val direction: String,
    val run: Int,
    @SerialName("first_marks") val firstMarks: Int,
    @SerialName("last_marks") val lastMarks: Int,
    @SerialName("total_marks") val totalMarks: Int,
    @SerialName("above_average") val aboveAverage: Boolean? = null,
)
