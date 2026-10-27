package com.shikkhokplus.app.feature.fees

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ClaimDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.FeeCycleDto
import com.shikkhokplus.app.core.network.PaymentDestinationDto
import com.shikkhokplus.app.core.network.RosterFeeRowDto

/**
 * Maps server responses to a [FeeUiState].
 *
 * **This object is the unit under test**, rather than "the ViewModel".
 * It is pure: no network, no storage, no clock. A decision needing any
 * of those would be a business rule, and business rules are
 * server-side [TC-9, D-31].
 *
 * **Every status mapping is exhaustive and an unknown value is an
 * error**, never a silent default. A server that added a fifth status
 * would otherwise render every affected row under whichever label
 * happened to be the fallback — worse than showing nothing, because it
 * looks correct.
 *
 * **No function here compares a money amount to decide anything the
 * server already decided.** `outstanding` is rendered; `statusLabel`
 * comes from the server's enum. The one derived boolean, [isSettled],
 * is derived from that enum rather than from the amount, so a waived
 * cycle is not reported as paid.
 */
object FeeStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be parsed. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /** Shown beside a claim whose verification was corrected [BR5.7]. */
    const val CORRECTION_KEY: String = "fees.claim.corrected"

    /**
     * String resource keys for the four server-decided fee statuses.
     *
     * **Four, and the fourth is the reason this map exists.** A fully
     * waived cycle has a zero balance and is not "paid"; a two-value
     * client-side test cannot express the difference.
     */
    private val STATUS_KEYS: Map<String, String> =
        mapOf(
            "paid" to "fees.status.paid",
            "partly_paid" to "fees.status.partly_paid",
            "unpaid" to "fees.status.unpaid",
            "waived" to "fees.status.waived",
        )

    /**
     * The statuses meaning nothing is still owed for that period.
     *
     * Derived from the server's ENUM rather than from the amount, which
     * is the whole point: both members here have a zero balance and
     * they are different facts.
     */
    private val SETTLED_STATUSES: Set<String> = setOf("paid", "waived")

    /** String resource keys for the four claim statuses [BR6.3]. */
    private val CLAIM_STATUS_KEYS: Map<String, String> =
        mapOf(
            "pending" to "fees.claim.pending",
            "approved_full" to "fees.claim.approved_full",
            "approved_partial" to "fees.claim.approved_partial",
            "rejected" to "fees.claim.rejected",
        )

    /** Claim statuses a teacher has already decided. */
    private val DECIDED_STATUSES: Set<String> =
        setOf("approved_full", "approved_partial", "rejected")

    /** String resource keys for the two shortfall dispositions [BR5.4]. */
    private val DISPOSITION_KEYS: Map<String, String> =
        mapOf(
            "carried" to "fees.disposition.carried",
            "waived" to "fees.disposition.waived",
        )

    /**
     * Map a loaded fee history.
     *
     * @param cycles The periods the server returned
     * @param totalOutstanding The total the SERVER computed. Summing
     *   [cycles] here would be the client doing money arithmetic, and
     *   it would be wrong the moment the history paginates
     * @return The state the screen renders
     */
    fun afterLoad(
        cycles: List<FeeCycleDto>,
        totalOutstanding: Money,
    ): FeeUiState {
        if (cycles.isEmpty()) {
            return FeeUiState.Empty
        }
        val mapped =
            cycles.map { cycle ->
                toRow(cycle) ?: return FeeUiState.Failed(UNEXPECTED_KEY, retryable = false)
            }
        return FeeUiState.Loaded(mapped.sortedByDescending { it.period }, totalOutstanding)
    }

    /**
     * Convert one period, or null when the status is unrecognised.
     *
     * @param cycle The period the server described
     * @return The row, or null on an unknown status
     */
    fun toRow(cycle: FeeCycleDto): FeeCycleRow? {
        val statusKey = STATUS_KEYS[cycle.status] ?: return null
        return FeeCycleRow(
            period = cycle.period,
            periodLabel = cycle.period,
            dueDateLabel = cycle.dueDate,
            charged = cycle.charged,
            outstanding = cycle.outstanding,
            statusLabel = statusKey,
            // From the ENUM, never from `outstanding`. A waived cycle
            // and a paid one both read zero and are different facts.
            isSettled = cycle.status in SETTLED_STATUSES,
        )
    }

    /**
     * Convert one roster fee row, or null on an unknown status.
     *
     * @param row The seat the server described
     * @return The row, or null when its status is unrecognised
     */
    fun toRosterRow(row: RosterFeeRowDto): RosterFeeRow? {
        val statusKey =
            row.currentStatus?.let { STATUS_KEYS[it] ?: return null }
        return RosterFeeRow(
            enrollmentId = row.enrollmentId,
            displayName = row.displayName,
            outstanding = row.outstanding,
            statusLabel = statusKey,
            dueDateLabel = row.dueDate,
            // **From the server's STATUS, not from the amount**, and
            // `Money` is the reason that is not merely preferable: the
            // type exposes no comparison at all, so `outstanding >
            // Money.ZERO` does not compile. The client performs no
            // money arithmetic [TC-9, D-31] and the type enforces it,
            // which is the boundary being mechanical rather than
            // reviewed.
            //
            // A seat with no generated period owes nothing, which is
            // the null case rather than a zero one.
            owesSomething =
                row.currentStatus != null && row.currentStatus !in SETTLED_STATUSES,
        )
    }

    /**
     * Convert one claim, or null on an unknown status.
     *
     * @param claim The claim the server described
     * @return The row, or null when its status is unrecognised
     */
    fun toClaimRow(claim: ClaimDto): ClaimRow? {
        val statusKey = CLAIM_STATUS_KEYS[claim.status] ?: return null
        val dispositionKey =
            claim.shortfallDisposition?.let { DISPOSITION_KEYS[it] ?: return null }
        return ClaimRow(
            claimId = claim.claimId,
            period = claim.period,
            claimedAmount = claim.claimedAmount,
            approvedAmount = claim.approvedAmount,
            statusLabel = statusKey,
            dispositionLabel = dispositionKey,
            channelLabel = claim.channel,
            isDecided = claim.status in DECIDED_STATUSES,
            // Shown to BOTH parties. A correction hidden from the
            // person whose money it concerns is the asymmetry FR9.2
            // forbids, and this field is what puts it on their screen.
            correctionNoticeKey =
                if (claim.previousDecision != null) CORRECTION_KEY else null,
        )
    }

    /**
     * Convert the payment destination, absent or known.
     *
     * @param destination What the server returned, or null where the
     *   teacher set no collection number
     * @return The destination state the form renders
     */
    fun toDestination(destination: PaymentDestinationDto?): PaymentDestination =
        if (destination == null) {
            PaymentDestination.Unset()
        } else {
            PaymentDestination.Known(
                collectionNumber = destination.collectionNumber,
                collectionChannelLabel = destination.collectionChannel,
                // Rendered as labels from the server's list. NOT a
                // sealed type with a branch per channel: that is the
                // idiomatic Kotlin choice and the wrong one, because
                // adding a channel would then need an app release and
                // an installed app cannot be forced to update.
                channels = destination.channels,
            )
        }

    /**
     * Map a failure the device could not even send.
     *
     * @return The offline state
     */
    fun offline(): FeeUiState = FeeUiState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * Map a server error envelope.
     *
     * @param messageKey The key the server named
     * @param retryable What the server said about retrying
     * @return The failed state
     */
    fun failed(
        messageKey: String,
        retryable: Boolean,
    ): FeeUiState = FeeUiState.Failed(messageKey, retryable)

    /**
     * Map a server error envelope.
     *
     * **The client decides neither half.** The server names the
     * string and states whether a retry would help; inferring either
     * from a status code is how a non-retryable refusal grows a retry
     * button that spends money the server just declined [TC-9].
     *
     * @param envelope The server's error
     * @return The failure state
     */
    fun afterError(envelope: ErrorEnvelope): FeeUiState =
        FeeUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * Retryable, because nothing reached the server: there is no
     * refusal to respect, only a connection that did not open.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): FeeUiState =
        FeeUiState.Failed(OFFLINE_KEY, retryable = true)
}
