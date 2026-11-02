package com.shikkhokplus.app.core.model

/** How the teacher decided a payment claim, from the server's status. */
enum class ClaimOutcome {
    /** Waiting to be checked. */
    PENDING,

    /** Accepted in full. */
    APPROVED_FULL,

    /** Accepted for less than claimed. */
    APPROVED_PARTIAL,

    /** Turned down. */
    REJECTED,
}

/**
 * The latest payment claim for a month, as data the screen words in
 * the person's language. The server sends no English sentence.
 *
 * @property amount What was claimed
 * @property channel Which service, or `cash`
 * @property paidOn When the money was sent, `YYYY-MM-DD`
 * @property outcome How the claim stands
 * @property decisionNote The teacher's note, if any
 */
data class HistoryLine(
    val amount: Money,
    val channel: String,
    val paidOn: String,
    val outcome: ClaimOutcome,
    val decisionNote: String?,
)
