package com.shikkhokplus.app.feature.collections

import com.shikkhokplus.app.core.model.HistoryLine
import com.shikkhokplus.app.core.model.Money

/** The filters on a batch-month screen. */
enum class MonthFilter {
    /** Every seat. */
    ALL,

    /** Settled seats, waived ones included. */
    PAID,

    /** Seats with a payment waiting to be checked. */
    CHECKING,

    /** Seats still owing, wholly or partly. */
    OWED,
}

/** How a seat looks in the month, chosen from the server's state. */
enum class SeatKind {
    /** Settled in full. */
    PAID,

    /** Settled by a waiver. */
    WAIVED,

    /** Part paid. */
    PARTIAL,

    /** Owes, not yet late. */
    DUE,

    /** Owes and is late by the server's day count. */
    OVERDUE,

    /** A payment is waiting to be checked. */
    CHECKING,

    /** Nothing was charged for the month. */
    NONE,
}

/**
 * One seat in the month.
 *
 * @property enrollmentId The seat
 * @property displayName The teacher-typed name
 * @property kind How it looks
 * @property outstanding What it owes in total, shown as text
 * @property daysOverdue The server's day count, or null
 * @property verifying The sum waiting to be checked, or null
 * @property historyLine The latest claim for the month, or null
 */
data class MonthSeat(
    val enrollmentId: String,
    val displayName: String,
    val kind: SeatKind,
    val outstanding: Money,
    val daysOverdue: Int?,
    val verifying: Money?,
    val historyLine: HistoryLine?,
)

/**
 * Everything the batch-month screen (M2) can be showing.
 */
sealed interface BatchMonthUiState {
    /** The first load, or a month switch in flight. */
    data object Loading : BatchMonthUiState

    /**
     * The month.
     *
     * @property period The month as `YYYY-MM`
     * @property collected Cash in for it
     * @property charged What it was billed
     * @property counts The server's seat counts per filter
     * @property filter The open filter
     * @property seats The seats the filter lets through
     * @property canGoNext Whether a later month than this one exists
     */
    data class Loaded(
        val period: String,
        val collected: Money,
        val charged: Money,
        val counts: SeatCounts,
        val filter: MonthFilter,
        val seats: List<MonthSeat>,
        val canGoNext: Boolean,
    ) : BatchMonthUiState

    /**
     * The load failed.
     *
     * @property messageKey A string resource key
     * @property retryable Whether the server said retrying could help
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : BatchMonthUiState
}
