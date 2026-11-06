package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One exam or other fee on a batch, with the server's totals.
 *
 * Every figure is the server's [TC-9]: the client adds and compares none.
 *
 * @property extraFeeId The fee
 * @property purpose `exam` or `other`
 * @property label Its name, as families see it
 * @property examTitle The exam it is for, or null
 * @property amount The amount per student
 * @property dueOn When it is due, `yyyy-MM-dd`
 * @property studentCount How many students it charges
 * @property paidCount How many have paid in full
 * @property owingCount How many still owe
 * @property chargedTotal What it charges in all
 * @property collectedTotal What has been approved against it
 * @property owedTotal What is still owed on it
 */
@Serializable
data class ExtraFeeSummaryDto(
    @SerialName("extra_fee_id") val extraFeeId: String,
    @SerialName("purpose") val purpose: String,
    @SerialName("label") val label: String,
    @SerialName("exam_title") val examTitle: String? = null,
    @SerialName("amount") val amount: Money,
    @SerialName("due_on") val dueOn: String,
    @SerialName("student_count") val studentCount: Int,
    @SerialName("paid_count") val paidCount: Int,
    @SerialName("owing_count") val owingCount: Int,
    @SerialName("charged_total") val chargedTotal: Money,
    @SerialName("collected_total") val collectedTotal: Money,
    @SerialName("owed_total") val owedTotal: Money,
)

/**
 * A student a new fee could charge, as the server lists them.
 *
 * @property enrollmentId The seat
 * @property displayName The name the teacher typed
 */
@Serializable
data class ChargeableStudentDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
)

/**
 * A batch's exam and other fees: `GET /v1/batches/{id}/extra-fees`.
 *
 * @property fees The fees, newest first
 * @property chargeableStudents Who a new fee would charge
 */
@Serializable
data class BatchExtraFeesDto(
    @SerialName("fees") val fees: List<ExtraFeeSummaryDto> = emptyList(),
    @SerialName("chargeable_students") val chargeableStudents: List<ChargeableStudentDto> = emptyList(),
)

/**
 * One student's part of a fee.
 *
 * @property enrollmentId The seat
 * @property displayName The name the teacher typed
 * @property charged What they were charged
 * @property paid What has been approved against it
 * @property owed What is still owed
 * @property status `paid`, `partly_paid`, `unpaid` or `waived`
 */
@Serializable
data class ExtraFeeStudentDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("charged") val charged: Money,
    @SerialName("paid") val paid: Money,
    @SerialName("owed") val owed: Money,
    @SerialName("status") val status: String,
)

/**
 * One fee and its students: `GET /v1/extra-fees/{id}`.
 *
 * @property extraFeeId The fee
 * @property purpose `exam` or `other`
 * @property label Its name
 * @property examTitle The exam it is for, or null
 * @property amount The amount per student
 * @property dueOn When it is due
 * @property chargedTotal What it charges in all
 * @property collectedTotal What has been approved against it
 * @property owedTotal What is still owed on it
 * @property students Each student it charges
 */
@Serializable
data class ExtraFeeDetailDto(
    @SerialName("extra_fee_id") val extraFeeId: String,
    @SerialName("purpose") val purpose: String,
    @SerialName("label") val label: String,
    @SerialName("exam_title") val examTitle: String? = null,
    @SerialName("amount") val amount: Money,
    @SerialName("due_on") val dueOn: String,
    @SerialName("charged_total") val chargedTotal: Money,
    @SerialName("collected_total") val collectedTotal: Money,
    @SerialName("owed_total") val owedTotal: Money,
    @SerialName("students") val students: List<ExtraFeeStudentDto> = emptyList(),
)

/**
 * A student charged other than the fee's amount; zero waives it.
 *
 * @property enrollmentId The seat
 * @property amount What they are charged
 */
@Serializable
data class SeatAmountDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("amount") val amount: Money,
)

/**
 * The body of `POST /v1/batches/{id}/extra-fees`.
 *
 * @property purpose `exam` or `other`
 * @property label Its name, as families see it
 * @property examId The exam it is for, or null
 * @property amount The amount per student
 * @property dueOn When it is due
 * @property seatAmounts Students charged another amount; zero waives
 * @property excludedEnrollmentIds Students left out entirely
 * @property clientMutationId The retry key: a resend under it is a replay
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class ExtraFeeRaiseRequestDto(
    @SerialName("purpose") val purpose: String,
    @SerialName("label") val label: String,
    @EncodeDefault @SerialName("exam_id") val examId: String? = null,
    @SerialName("amount") val amount: Money,
    @SerialName("due_on") val dueOn: String,
    @EncodeDefault @SerialName("seat_amounts") val seatAmounts: List<SeatAmountDto> = emptyList(),
    @EncodeDefault @SerialName("excluded_enrollment_ids") val excludedEnrollmentIds: List<String> = emptyList(),
    @SerialName("client_mutation_id") val clientMutationId: String,
)
