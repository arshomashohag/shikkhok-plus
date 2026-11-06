package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One child a payment covers.
 *
 * @property enrollmentId The seat
 * @property claimId The claim the payment made for that seat
 * @property displayName The child, as the teacher typed the name
 * @property period The period, `YYYY-MM`
 * @property owed What that seat owes, the server's figure
 * @property approvedAmount What was approved for the seat, once decided
 */
@Serializable
data class ReviewChildDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("claim_id") val claimId: String,
    @SerialName("display_name") val displayName: String,
    val period: String,
    val owed: Money,
    @SerialName("approved_amount") val approvedAmount: Money? = null,
)

/**
 * The destination the family was shown when they paid.
 *
 * @property kind `mobile` or `bank`
 * @property methodId The method it was, while that method still exists
 * @property provider The mobile service or the bank
 * @property channel The built-in channel, such as `cash`
 * @property mobileNumber The number, mobile methods only
 * @property accountNumber The account number, bank methods only
 * @property accountName The account holder, bank methods only
 * @property branchName The branch, bank methods only
 * @property note Text the teacher showed with the method
 */
@Serializable
data class ReviewMethodDto(
    val kind: String,
    @SerialName("method_id") val methodId: String? = null,
    val provider: String? = null,
    val channel: String? = null,
    @SerialName("mobile_number") val mobileNumber: String? = null,
    @SerialName("account_number") val accountNumber: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("branch_name") val branchName: String? = null,
    val note: String? = null,
)

/**
 * The earlier payment that quoted the same reference.
 *
 * @property submissionId That payment
 * @property displayName Whose it was
 * @property status `pending`, `approved` or `rejected`
 * @property amount What it was for
 * @property decidedAt When it was decided, or null
 */
@Serializable
data class DuplicatePaymentDto(
    @SerialName("submission_id") val submissionId: String,
    @SerialName("display_name") val displayName: String,
    val status: String,
    val amount: Money,
    @SerialName("decided_at") val decidedAt: String? = null,
)

/**
 * One payment as its teacher reviews it (R1 to R3).
 *
 * **[comparison], [difference] and [owedTogether] are the server's.**
 * The screen shows them and subtracts nothing [TC-9].
 *
 * @property submissionId The payment
 * @property batchName The batch
 * @property children The children covered, in the server's order
 * @property owedTogether What they owe together now; for a decided payment, before the decision
 * @property totalAmount What the payer says they sent
 * @property comparison `matches`, `short` or `over`
 * @property difference How far from what is owed, never negative
 * @property method The destination snapshot
 * @property transactionId The mobile reference, if any
 * @property fromAccount The paying bank account, if any
 * @property paidOn The day the money moved
 * @property submittedAt When it was reported
 * @property submittedBy `student` or `guardian`, or null
 * @property submitterPhone The number the teacher holds for them
 * @property payerNote The payer's note
 * @property status `pending`, `approved` or `rejected`
 * @property decisionNote The teacher's note on the decision
 * @property decidedAt When it was decided
 * @property duplicateOf The earlier payment quoting the same reference
 * @property purpose What the payment is applied to: `monthly` or `extra`;
 *   while previewing, what it would be applied to
 * @property extraFee The fee it is applied to, with `extra`
 * @property requestedPurpose What the family said it was for
 * @property requestedExtraFee The fee the family chose, with `extra`
 * @property extraFeeOptions The fees the teacher may apply it to instead
 */
@Serializable
data class PaymentReviewDto(
    @SerialName("submission_id") val submissionId: String,
    @SerialName("batch_name") val batchName: String,
    val children: List<ReviewChildDto>,
    @SerialName("owed_together") val owedTogether: Money,
    @SerialName("total_amount") val totalAmount: Money,
    val comparison: String,
    val difference: Money,
    val method: ReviewMethodDto,
    @SerialName("transaction_id") val transactionId: String? = null,
    @SerialName("from_account") val fromAccount: String? = null,
    @SerialName("paid_on") val paidOn: String,
    @SerialName("submitted_at") val submittedAt: String,
    @SerialName("submitted_by") val submittedBy: String? = null,
    @SerialName("submitter_phone") val submitterPhone: String? = null,
    @SerialName("payer_note") val payerNote: String? = null,
    val status: String,
    @SerialName("decision_note") val decisionNote: String? = null,
    @SerialName("decided_at") val decidedAt: String? = null,
    @SerialName("duplicate_of") val duplicateOf: DuplicatePaymentDto? = null,
    @SerialName("purpose") val purpose: String = MONTHLY_PURPOSE,
    @SerialName("extra_fee") val extraFee: ExtraFeeRefDto? = null,
    @SerialName("requested_purpose") val requestedPurpose: String = MONTHLY_PURPOSE,
    @SerialName("requested_extra_fee") val requestedExtraFee: ExtraFeeRefDto? = null,
    @SerialName("extra_fee_options") val extraFeeOptions: List<ExtraFeeRefDto> = emptyList(),
)

/** The purpose the server assumes when a payment names none. */
const val MONTHLY_PURPOSE: String = "monthly"

/** The purpose of a payment for one exam or other fee. */
const val EXTRA_PURPOSE: String = "extra"

/**
 * A payment decided in the last day.
 *
 * @property submissionId The payment
 * @property displayName The children's names
 * @property batchName The batch
 * @property status `approved` or `rejected`
 * @property amount What was received, else what was reported
 * @property decidedAt When
 */
@Serializable
data class RecentDecisionDto(
    @SerialName("submission_id") val submissionId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("batch_name") val batchName: String,
    val status: String,
    val amount: Money,
    @SerialName("decided_at") val decidedAt: String,
)

/**
 * The teacher's payment queue.
 *
 * @property pending Waiting payments, oldest first
 * @property decidedRecently The last day's decisions, newest first
 */
@Serializable
data class VerificationQueueDto(
    val pending: List<PaymentReviewDto> = emptyList(),
    @SerialName("decided_recently") val decidedRecently: List<RecentDecisionDto> = emptyList(),
)

/**
 * The body of an approval.
 *
 * Every field is sent, null included, so the server reads an absent
 * choice as "none" rather than guessing.
 *
 * @property receivedAmount What the teacher received
 * @property shortfallDisposition `carried` or `waived`, when short
 * @property carriedByEnrollmentId The child who carries a shortfall
 * @property creditToEnrollmentId The child who gets an excess as credit
 * @property note Shown to the family with the decision
 * @property correcting True when revising a decided payment
 * @property purpose `monthly` or `extra` when the teacher applies the
 *   payment to something other than what is stored; omitted otherwise
 * @property extraFeeId The fee, alongside `extra`
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class PaymentApprovalBodyDto(
    @EncodeDefault @SerialName("received_amount") val receivedAmount: Money,
    @EncodeDefault @SerialName("shortfall_disposition") val shortfallDisposition: String? = null,
    @EncodeDefault @SerialName("carried_by_enrollment_id") val carriedByEnrollmentId: String? = null,
    @EncodeDefault @SerialName("credit_to_enrollment_id") val creditToEnrollmentId: String? = null,
    @EncodeDefault @SerialName("note") val note: String? = null,
    @EncodeDefault @SerialName("correcting") val correcting: Boolean = false,
    @SerialName("purpose") val purpose: String? = null,
    @SerialName("extra_fee_id") val extraFeeId: String? = null,
)

/**
 * The body of a rejection.
 *
 * @property note Why, shown to the family
 * @property correcting True when revising a decided payment
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class PaymentRejectionBodyDto(
    @EncodeDefault @SerialName("note") val note: String? = null,
    @EncodeDefault @SerialName("correcting") val correcting: Boolean = false,
)

/**
 * Money a teacher received by hand for one seat, recorded as approved
 * (`POST /v1/enrollments/{enrollment_id}/payments`).
 *
 * **The server decides the money.** It settles the seat's months oldest
 * first, holds any excess as credit, and refuses a short amount without
 * [shortfallDisposition] or a disposition on an amount that is not
 * short. The client only asks the question when the typed amount looks
 * short, exactly as the approval sheet does.
 *
 * @property amount What was received; more than zero
 * @property channel `cash`, or a mobile service sent straight to the teacher
 * @property reference A transaction id or receipt number, if any
 * @property note Shown to the family with the record
 * @property shortfallDisposition `carried` or `waived`, when short
 * @property clientMutationId One UUID per opened sheet, reused on every
 *   resend, so a record whose response was lost is replayed rather
 *   than recorded twice
 * @property purpose `extra` when the money is for one exam or other fee;
 *   omitted for the monthly fee
 * @property extraFeeId The fee, alongside `extra`
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class RecordPaymentBodyDto(
    @EncodeDefault @SerialName("amount") val amount: Money,
    @EncodeDefault @SerialName("channel") val channel: String = "cash",
    @EncodeDefault @SerialName("reference") val reference: String? = null,
    @EncodeDefault @SerialName("note") val note: String? = null,
    @EncodeDefault @SerialName("shortfall_disposition") val shortfallDisposition: String? = null,
    @EncodeDefault @SerialName("client_mutation_id") val clientMutationId: String? = null,
    @SerialName("purpose") val purpose: String? = null,
    @SerialName("extra_fee_id") val extraFeeId: String? = null,
)
