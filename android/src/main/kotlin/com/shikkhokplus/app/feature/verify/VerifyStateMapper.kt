package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.network.DuplicatePaymentDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.PaymentReviewDto
import com.shikkhokplus.app.core.network.RecentDecisionDto
import com.shikkhokplus.app.core.network.ReviewChildDto
import com.shikkhokplus.app.core.network.ReviewMethodDto
import com.shikkhokplus.app.core.network.VerificationQueueDto

/**
 * Maps the payment queue and one payment to what R1 to R3 render.
 *
 * Every figure and every comparison is the server's; this names them
 * for the screen and decides nothing [TC-9, D-31].
 */
object VerifyStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be understood. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /** The error code the server gives a payment someone already decided. */
    const val ALREADY_DECIDED_CODE: String = "PAYMENT_ALREADY_DECIDED"

    private val COMPARISONS: Map<String, Comparison> =
        mapOf("matches" to Comparison.MATCHES, "short" to Comparison.SHORT, "over" to Comparison.OVER)

    private val STATUSES: Map<String, ReviewStatus> =
        mapOf(
            "pending" to ReviewStatus.PENDING,
            "approved" to ReviewStatus.APPROVED,
            "rejected" to ReviewStatus.REJECTED,
        )

    private val SUBMITTERS: Map<String, String> =
        mapOf("student" to "verify.from.student", "guardian" to "verify.from.guardian")

    private val DECISIONS: Map<String, String> =
        mapOf(
            "pending" to "verify.decision.pending",
            "approved" to "verify.decision.approved",
            "rejected" to "verify.decision.rejected",
        )

    private const val CASH_CHANNEL = "cash"

    /**
     * Map the queue.
     *
     * @param dto What the server returned
     * @return The state R1 renders
     */
    fun afterLoad(dto: VerificationQueueDto): VerifyUiState {
        val recent = dto.decidedRecently.map { toRecent(it) ?: return unexpected() }
        if (dto.pending.isEmpty()) return VerifyUiState.AllCaughtUp(recent)
        val cards = dto.pending.map { toCard(it) ?: return unexpected() }
        return VerifyUiState.Waiting(cards, recent)
    }

    /**
     * Map a refusal of the whole read.
     *
     * @param envelope The server's error
     * @return The failure state
     */
    fun afterError(envelope: ErrorEnvelope): VerifyUiState =
        VerifyUiState.Failed(envelope.error.messageKey, envelope.error.retryable)

    /**
     * Map a read that never reached the server.
     *
     * @return The offline failure
     */
    fun afterTransportFailure(): VerifyUiState = VerifyUiState.Failed(OFFLINE_KEY, retryable = true)

    /** @return The state for a response outside the known values. */
    private fun unexpected(): VerifyUiState = VerifyUiState.Failed(UNEXPECTED_KEY, retryable = false)

    /**
     * Map one payment.
     *
     * @param dto What the server returned
     * @return The loaded state, or a failure for a value outside the known set
     */
    fun afterDetail(dto: PaymentReviewDto): ReviewUiState =
        toCard(dto)?.let { ReviewUiState.Loaded(it) }
            ?: ReviewUiState.Failed(UNEXPECTED_KEY, retryable = false)

    /**
     * Map a refusal of a payment read.
     *
     * @param envelope The server's error
     * @return The failure state
     */
    fun detailError(envelope: ErrorEnvelope): ReviewUiState =
        ReviewUiState.Failed(envelope.error.messageKey, envelope.error.retryable)

    /**
     * Map a payment read that never reached the server.
     *
     * @return The offline failure
     */
    fun detailOffline(): ReviewUiState = ReviewUiState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * Convert one payment; shared with Today's preview (T1).
     *
     * @param dto The payment
     * @return The card, or null for a value outside the known set
     */
    fun toCard(dto: PaymentReviewDto): ReviewCard? {
        val comparison = COMPARISONS[dto.comparison] ?: return null
        val status = STATUSES[dto.status] ?: return null
        val method = toMethod(dto.method) ?: return null
        val duplicate = dto.duplicateOf?.let { toDuplicate(it) ?: return null }
        return ReviewCard(
            submissionId = dto.submissionId,
            batchName = dto.batchName,
            children = dto.children.map(::toChild),
            owedTogether = dto.owedTogether,
            totalAmount = dto.totalAmount,
            comparison = comparison,
            difference = dto.difference,
            method = method,
            transactionId = dto.transactionId,
            fromAccount = dto.fromAccount,
            paidOn = dto.paidOn,
            submittedAt = dto.submittedAt,
            submitterKey = dto.submittedBy?.let { SUBMITTERS[it] ?: return null },
            submitterPhone = dto.submitterPhone,
            payerNote = dto.payerNote,
            status = status,
            decisionNote = dto.decisionNote,
            decidedAt = dto.decidedAt,
            duplicate = duplicate,
        )
    }

    /**
     * Convert one child.
     *
     * @param dto The child
     * @return The child
     */
    private fun toChild(dto: ReviewChildDto): ReviewChild =
        ReviewChild(dto.enrollmentId, dto.displayName, dto.period, dto.owed, dto.approvedAmount)

    /**
     * Convert the destination snapshot.
     *
     * @param dto The destination
     * @return The method, or null for a kind this version does not know
     */
    private fun toMethod(dto: ReviewMethodDto): ReviewMethod? {
        val kind =
            when {
                dto.kind == "mobile" -> MethodKind.MOBILE
                dto.kind == "bank" -> MethodKind.BANK
                dto.channel == CASH_CHANNEL -> MethodKind.CASH
                else -> return null
            }
        return ReviewMethod(
            kind = kind,
            provider = dto.provider ?: dto.channel.takeIf { kind != MethodKind.CASH },
            number = dto.mobileNumber ?: dto.accountNumber,
            accountName = dto.accountName,
            branchName = dto.branchName,
            note = dto.note,
        )
    }

    /**
     * Convert the earlier payment a reference repeats.
     *
     * @param dto The earlier payment
     * @return The note, or null for an unknown status
     */
    private fun toDuplicate(dto: DuplicatePaymentDto): DuplicateNote? =
        DECISIONS[dto.status]?.let { DuplicateNote(dto.displayName, it, dto.amount, dto.decidedAt) }

    /**
     * Convert one recent decision.
     *
     * @param dto The decision
     * @return The row, or null for an unknown status
     */
    private fun toRecent(dto: RecentDecisionDto): RecentRow? =
        DECISIONS[dto.status]?.let { key ->
            RecentRow(dto.submissionId, dto.displayName, dto.batchName, key, dto.amount)
        }
}
