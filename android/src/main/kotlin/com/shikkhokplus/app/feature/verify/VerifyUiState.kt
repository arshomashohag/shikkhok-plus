package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.model.Money

/** How a claim stands against its charge, as the server decided it. */
enum class Comparison {
    /** The claim equals the charge. */
    MATCHES,

    /** Less than the charge; approving it needs carry or waive. */
    SHORT,

    /** More than the charge. */
    OVER,
}

/**
 * The earlier claim that used the same transaction id.
 *
 * @property displayName Whose it was
 * @property statusKey A message key for how it was decided
 * @property amount Its amount
 * @property decidedAt When it was decided, or null while pending
 */
data class DuplicateNote(
    val displayName: String,
    val statusKey: String,
    val amount: Money,
    val decidedAt: String?,
)

/**
 * One claim card (T4).
 *
 * @property claimId The claim
 * @property displayName The student
 * @property batchName The batch
 * @property period `YYYY-MM`
 * @property claimedAmount What was sent
 * @property charged What the period charged
 * @property comparison The server's comparison
 * @property difference How far from the charge
 * @property channel The service used
 * @property transactionId The reference, if any
 * @property submittedAt When it was sent, as the server wrote it
 * @property submitterKey A message key naming who sent it, or null
 * @property submitterPhone The number on record for them, or null
 * @property duplicate The earlier claim with the same reference, or null
 */
data class ClaimCard(
    val claimId: String,
    val displayName: String,
    val batchName: String,
    val period: String,
    val claimedAmount: Money,
    val charged: Money,
    val comparison: Comparison,
    val difference: Money,
    val channel: String,
    val transactionId: String?,
    val submittedAt: String,
    val submitterKey: String?,
    val submitterPhone: String?,
    val duplicate: DuplicateNote?,
)

/**
 * A decision from the last day, for "Approved today".
 *
 * @property displayName The student
 * @property batchName The batch
 * @property statusKey A message key for the decision
 * @property amount The amount
 */
data class RecentRow(
    val displayName: String,
    val batchName: String,
    val statusKey: String,
    val amount: Money,
)

/**
 * The partial-approval sheet: an amount, and what it leaves short.
 *
 * @property card The claim being approved in part
 * @property typed The amount as typed
 * @property shortfall What it leaves short, from the server, or null
 *   until the server has answered for this amount
 * @property dispositionRequired Whether carry or waive must be chosen
 * @property disposition `carried` or `waived`, once chosen
 */
data class PartialSheet(
    val card: ClaimCard,
    val typed: String,
    val shortfall: Money? = null,
    val dispositionRequired: Boolean = false,
    val disposition: String? = null,
)

/** Everything T4 renders. */
sealed interface VerifyUiState {
    /** The queue is loading. */
    data object Loading : VerifyUiState

    /**
     * Claims are waiting.
     *
     * @property pending The waiting claims, oldest first
     * @property recent The last day's decisions
     * @property busyClaimId A claim whose decision is being sent, or null
     * @property errorKey A refused decision's message, shown on the list
     */
    data class Waiting(
        val pending: List<ClaimCard>,
        val recent: List<RecentRow>,
        val busyClaimId: String? = null,
        val errorKey: String? = null,
    ) : VerifyUiState

    /**
     * Nothing waits.
     *
     * @property recent The last day's decisions
     */
    data class AllCaughtUp(val recent: List<RecentRow>) : VerifyUiState

    /**
     * The queue could not be read.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : VerifyUiState
}
