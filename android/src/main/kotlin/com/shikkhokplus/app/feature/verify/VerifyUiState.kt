package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.model.Money

/** How a payment stands against what is owed, as the server decided it. */
enum class Comparison {
    /** The payment equals what is owed. */
    MATCHES,

    /** Less than what is owed. */
    SHORT,

    /** More than what is owed. */
    OVER,
}

/** Where a payment is in its review. */
enum class ReviewStatus {
    /** Waiting for the teacher. */
    PENDING,

    /** The teacher recorded it as received. */
    APPROVED,

    /** The teacher did not accept it. */
    REJECTED,
}

/** Where the money was sent, as the family was shown it. */
enum class MethodKind {
    /** A mobile-money number. */
    MOBILE,

    /** A bank account. */
    BANK,

    /** Handed over in person. */
    CASH,
}

/**
 * The destination snapshot on a payment.
 *
 * @property kind What sort of destination it was
 * @property provider The mobile service or the bank, if any
 * @property number The mobile number or account number, if any
 * @property accountName The account holder, banks only
 * @property branchName The branch, banks only
 * @property note Text the teacher showed with it
 */
data class ReviewMethod(
    val kind: MethodKind,
    val provider: String?,
    val number: String?,
    val accountName: String?,
    val branchName: String?,
    val note: String?,
)

/**
 * One child a payment covers.
 *
 * @property enrollmentId The seat
 * @property displayName The child
 * @property period `YYYY-MM`
 * @property owed What the seat owes, the server's figure
 * @property approvedAmount What was approved for the seat, once decided
 */
data class ReviewChild(
    val enrollmentId: String,
    val displayName: String,
    val period: String,
    val owed: Money,
    val approvedAmount: Money?,
)

/**
 * The earlier payment that used the same reference.
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
 * One payment under review (R1 to R3).
 *
 * @property submissionId The payment
 * @property batchName The batch
 * @property children The children covered, in the server's order
 * @property owedTogether What they owe together now
 * @property totalAmount What the payer says they sent
 * @property comparison The server's comparison
 * @property difference How far from what is owed
 * @property method Where it was sent
 * @property transactionId The mobile reference, if any
 * @property fromAccount The paying bank account, if any
 * @property paidOn The day the money moved, `YYYY-MM-DD`
 * @property submittedAt When it was reported
 * @property submitterKey A message key naming who sent it, or null
 * @property submitterPhone The number on record for them, or null
 * @property payerNote The payer's note, if any
 * @property status Where the review stands
 * @property decisionNote The teacher's note on the decision, if any
 * @property decidedAt When it was decided, or null while pending
 * @property duplicate The earlier payment with the same reference, or null
 */
data class ReviewCard(
    val submissionId: String,
    val batchName: String,
    val children: List<ReviewChild>,
    val owedTogether: Money,
    val totalAmount: Money,
    val comparison: Comparison,
    val difference: Money,
    val method: ReviewMethod,
    val transactionId: String?,
    val fromAccount: String?,
    val paidOn: String,
    val submittedAt: String,
    val submitterKey: String?,
    val submitterPhone: String?,
    val payerNote: String?,
    val status: ReviewStatus,
    val decisionNote: String?,
    val decidedAt: String?,
    val duplicate: DuplicateNote?,
) {
    /** The children's names together, in the server's order. */
    val displayName: String get() = children.joinToString(", ") { it.displayName }

    /** The first child's period, which names the month on a row. */
    val period: String get() = children.firstOrNull()?.period.orEmpty()
}

/**
 * A decision from the last day.
 *
 * @property submissionId The payment
 * @property displayName The children
 * @property batchName The batch
 * @property statusKey A message key for the decision
 * @property amount The amount
 */
data class RecentRow(
    val submissionId: String,
    val displayName: String,
    val batchName: String,
    val statusKey: String,
    val amount: Money,
)

/** Everything R1 renders. */
sealed interface VerifyUiState {
    /** The queue is loading. */
    data object Loading : VerifyUiState

    /**
     * Payments are waiting.
     *
     * @property pending The waiting payments, oldest first
     * @property recent The last day's decisions
     */
    data class Waiting(
        val pending: List<ReviewCard>,
        val recent: List<RecentRow>,
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
