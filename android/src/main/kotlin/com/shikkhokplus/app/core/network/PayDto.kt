package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
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

/**
 * The methods a family may pay a batch's teacher with.
 *
 * An empty [methods] list is the "ask the teacher" state, and cash is
 * still on offer beside it.
 *
 * @property methods The teacher's live methods, in display order
 * @property services Mobile service names the server suggests
 * @property teacherDisplayName Who the money goes to, or null
 */
@Serializable
data class FamilyPaymentMethodsDto(
    val methods: List<PaymentMethodDto> = emptyList(),
    val services: List<String> = emptyList(),
    @SerialName("teacher_display_name") val teacherDisplayName: String? = null,
)

/**
 * One child in the form's "Owed for" line.
 *
 * @property enrollmentId The child's seat
 * @property displayName The name the teacher typed
 * @property owed What the seat owes now, as the server folded it
 */
@Serializable
data class OwedChildDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
    val owed: Money,
)

/**
 * What the chosen children owe together, summed by the server.
 *
 * @property owedTogether The server's total; the client never adds
 * @property children Each child, in the server's child order
 */
@Serializable
data class OwedTogetherDto(
    @SerialName("owed_together") val owedTogether: Money,
    val children: List<OwedChildDto> = emptyList(),
)

/**
 * One payment a student or guardian reports.
 *
 * Every field is sent, null included, because the server reads exactly
 * one of the reference fields and one of the destination fields.
 *
 * @property enrollmentIds The children covered, all in one batch
 * @property paymentMethodId The teacher's method, or null for cash
 * @property cash Whether the money was handed over in person
 * @property amount The whole amount sent, as a JSON string
 * @property paidOn The day the money moved, `yyyy-MM-dd`
 * @property transactionId The mobile reference, or null
 * @property fromAccount The paying bank account, or null
 * @property note Free text for the teacher, or null
 * @property clientMutationId The server's replay key for this payment
 *   attempt, a random UUID [PA-DB-1]. A send that timed out after the
 *   server committed it is retried with the SAME key, and the server
 *   answers with the original submission instead of recording a second
 *   claim. Null only where no attempt exists yet; the form always sets it
 *   before sending
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class PaymentSubmitDto(
    @EncodeDefault @SerialName("enrollment_ids") val enrollmentIds: List<String>,
    @EncodeDefault @SerialName("payment_method_id") val paymentMethodId: String?,
    @EncodeDefault val cash: Boolean,
    @EncodeDefault val amount: Money,
    @EncodeDefault @SerialName("paid_on") val paidOn: String,
    @EncodeDefault @SerialName("transaction_id") val transactionId: String? = null,
    @EncodeDefault @SerialName("from_account") val fromAccount: String? = null,
    @EncodeDefault val note: String? = null,
    @SerialName("client_mutation_id") val clientMutationId: String? = null,
)

/**
 * One child's share of a recorded payment.
 *
 * @property claimId The claim
 * @property claimedAmount What it claimed
 * @property displayName The child
 * @property enrollmentId The child's seat
 * @property period The month it was recorded against
 */
@Serializable
data class SubmittedClaimDto(
    @SerialName("claim_id") val claimId: String,
    @SerialName("claimed_amount") val claimedAmount: Money,
    @SerialName("display_name") val displayName: String,
    @SerialName("enrollment_id") val enrollmentId: String,
    val period: String,
)

/**
 * A payment as recorded, waiting for the teacher.
 *
 * @property submissionId The submission
 * @property status Always `pending` when just submitted
 * @property totalAmount The whole amount sent
 * @property paidOn The day the money moved
 * @property claims Each child's share, in child order
 */
@Serializable
data class PaymentSubmittedDto(
    @SerialName("submission_id") val submissionId: String,
    val status: String,
    @SerialName("total_amount") val totalAmount: Money,
    @SerialName("paid_on") val paidOn: String,
    val claims: List<SubmittedClaimDto> = emptyList(),
)
