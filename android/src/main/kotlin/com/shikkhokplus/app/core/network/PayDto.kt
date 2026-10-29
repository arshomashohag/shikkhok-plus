package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One month a student can pay for (S3).
 *
 * @property enrollmentId The seat the claim is posted against
 * @property batchName The batch
 * @property period The month a claim would be recorded against
 * @property amountDue What is still owed on it, as the server folded it
 * @property dueDate When it was due, `yyyy-MM-dd`, or null
 * @property totalDue Everything the seat owes, that month included
 * @property laterPeriods How many later months also owe
 * @property daysLate Days past the oldest late due date, or null
 */
@Serializable
data class PayableDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_name") val batchName: String,
    val period: String,
    @SerialName("amount_due") val amountDue: Money,
    @SerialName("due_date") val dueDate: String? = null,
    @SerialName("total_due") val totalDue: Money? = null,
    @SerialName("later_periods") val laterPeriods: Int = 0,
    @SerialName("days_late") val daysLate: Int? = null,
)

/**
 * A seat not offered because its payment is being checked.
 *
 * @property batchName The batch
 * @property period The month the waiting payment is for
 * @property amount What was claimed
 * @property channel Which app it moved through
 * @property submittedAt When it was sent
 */
@Serializable
data class WaitingPaymentDto(
    @SerialName("batch_name") val batchName: String,
    val period: String,
    val amount: Money? = null,
    val channel: String = "",
    @SerialName("submitted_at") val submittedAt: String? = null,
)

/**
 * What the "Pay a fee" screen offers and explains.
 *
 * @property payable Months to pay for, earliest due first
 * @property waiting Seats whose payment is already being checked
 */
@Serializable
data class PayablesDto(
    val payable: List<PayableDto> = emptyList(),
    val waiting: List<WaitingPaymentDto> = emptyList(),
)
