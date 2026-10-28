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
 */
@Serializable
data class PayableDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_name") val batchName: String,
    val period: String,
    @SerialName("amount_due") val amountDue: Money,
    @SerialName("due_date") val dueDate: String? = null,
)

/**
 * A seat not offered because its payment is being checked.
 *
 * @property batchName The batch
 * @property period The month the waiting payment is for
 */
@Serializable
data class WaitingPaymentDto(
    @SerialName("batch_name") val batchName: String,
    val period: String,
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
