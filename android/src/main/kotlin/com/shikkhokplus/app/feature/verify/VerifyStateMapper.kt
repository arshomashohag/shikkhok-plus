package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.network.ClaimQueueItemDto
import com.shikkhokplus.app.core.network.DuplicateClaimDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RecentDecisionDto
import com.shikkhokplus.app.core.network.VerificationQueueDto

/**
 * Maps the payment queue to what T4 renders.
 *
 * Every figure and every comparison is the server's; this names them
 * for the screen and decides nothing [TC-9, D-31].
 */
object VerifyStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be understood. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    private val COMPARISONS: Map<String, Comparison> =
        mapOf("matches" to Comparison.MATCHES, "short" to Comparison.SHORT, "over" to Comparison.OVER)

    private val SUBMITTERS: Map<String, String> =
        mapOf("student" to "verify.from.student", "guardian" to "verify.from.guardian")

    private val DECISIONS: Map<String, String> =
        mapOf(
            "pending" to "verify.decision.pending",
            "approved_full" to "verify.decision.approved_full",
            "approved_partial" to "verify.decision.approved_partial",
            "rejected" to "verify.decision.rejected",
        )

    /**
     * Map the queue.
     *
     * @param dto What the server returned
     * @return The state T4 renders
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
     * Convert one waiting claim; shared with Today's preview (T1).
     *
     * @param dto The claim
     * @return The card, or null for a value outside the known set
     */
    fun toCard(dto: ClaimQueueItemDto): ClaimCard? {
        val comparison = COMPARISONS[dto.comparison] ?: return null
        val duplicate = dto.duplicateOf?.let { toDuplicate(it) ?: return null }
        return ClaimCard(
            claimId = dto.claimId,
            displayName = dto.displayName,
            batchName = dto.batchName,
            period = dto.period,
            claimedAmount = dto.claimedAmount,
            charged = dto.charged,
            comparison = comparison,
            difference = dto.difference,
            channel = dto.channel,
            transactionId = dto.transactionId,
            submittedAt = dto.submittedAt,
            submitterKey = dto.submittedBy?.let { SUBMITTERS[it] ?: return null },
            submitterPhone = dto.submitterPhone,
            duplicate = duplicate,
        )
    }

    /**
     * Convert the earlier claim a reference repeats.
     *
     * @param dto The earlier claim
     * @return The note, or null for an unknown status
     */
    private fun toDuplicate(dto: DuplicateClaimDto): DuplicateNote? =
        DECISIONS[dto.status]?.let { DuplicateNote(dto.displayName, it, dto.amount, dto.decidedAt) }

    /**
     * Convert one recent decision.
     *
     * @param dto The decision
     * @return The row, or null for an unknown status
     */
    private fun toRecent(dto: RecentDecisionDto): RecentRow? =
        DECISIONS[dto.status]?.let { key ->
            RecentRow(dto.displayName, dto.batchName, key, dto.amount)
        }
}
