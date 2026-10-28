package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The earlier claim that quoted the same transaction id.
 *
 * @property claimId That claim
 * @property displayName Whose seat it was on, as the teacher typed it
 * @property status How it was decided, or `pending`
 * @property amount What was approved, else what was claimed
 * @property decidedAt When it was decided, or null
 */
@Serializable
data class DuplicateClaimDto(
    @SerialName("claim_id") val claimId: String,
    @SerialName("display_name") val displayName: String,
    val status: String,
    val amount: Money,
    @SerialName("decided_at") val decidedAt: String? = null,
)

/**
 * One claim waiting for the teacher (T4).
 *
 * **[comparison] and [difference] are the server's**, measured against
 * what the period charged [BR5.3]. The card shows them; it never
 * subtracts the claim from the charge itself [TC-9].
 *
 * @property claimId The claim
 * @property enrollmentId The seat it is against
 * @property displayName The student, as the teacher typed the name
 * @property batchName The batch
 * @property period The period, `YYYY-MM`
 * @property claimedAmount What the payer says they sent
 * @property charged What that period charged
 * @property comparison `matches`, `short` or `over`
 * @property difference How far from the charge, never negative
 * @property channel bKash, Nagad and so on
 * @property transactionId The reference quoted, if any
 * @property submittedAt When it was sent
 * @property submittedBy `student` or `guardian`, or null
 * @property submitterPhone The number on record for that person
 * @property duplicateOf The earlier claim quoting the same reference
 */
@Serializable
data class ClaimQueueItemDto(
    @SerialName("claim_id") val claimId: String,
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("batch_name") val batchName: String,
    val period: String,
    @SerialName("claimed_amount") val claimedAmount: Money,
    val charged: Money,
    val comparison: String,
    val difference: Money,
    val channel: String,
    @SerialName("transaction_id") val transactionId: String? = null,
    @SerialName("submitted_at") val submittedAt: String,
    @SerialName("submitted_by") val submittedBy: String? = null,
    @SerialName("submitter_phone") val submitterPhone: String? = null,
    @SerialName("duplicate_of") val duplicateOf: DuplicateClaimDto? = null,
)

/**
 * A claim decided in the last day.
 *
 * @property claimId The claim
 * @property displayName The student
 * @property batchName The batch
 * @property status How it was decided
 * @property amount What was approved, else what was claimed
 * @property decidedAt When
 */
@Serializable
data class RecentDecisionDto(
    @SerialName("claim_id") val claimId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("batch_name") val batchName: String,
    val status: String,
    val amount: Money,
    @SerialName("decided_at") val decidedAt: String,
)

/**
 * The teacher's payment queue.
 *
 * @property pending Waiting claims, oldest first
 * @property decidedRecently The last day's decisions, newest first
 */
@Serializable
data class VerificationQueueDto(
    val pending: List<ClaimQueueItemDto> = emptyList(),
    @SerialName("decided_recently") val decidedRecently: List<RecentDecisionDto> = emptyList(),
)

/**
 * What an approval would leave short, before deciding.
 *
 * @property shortfall `charged - approved`, floored at zero
 * @property dispositionRequired Whether carry or waive must be chosen
 */
@Serializable
data class ShortfallPreviewDto(
    val shortfall: Money,
    @SerialName("disposition_required") val dispositionRequired: Boolean,
)
