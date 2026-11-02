package com.shikkhokplus.app.feature.collections

import com.shikkhokplus.app.core.model.Money

/**
 * One batch the report can be narrowed to.
 *
 * @property id The batch
 * @property name Its name
 * @property selected Whether the report is narrowed to it
 */
data class BatchChip(
    val id: String,
    val name: String,
    val selected: Boolean,
)

/**
 * One month on the collected-versus-charged chart.
 *
 * **The bars are the server's whole percents**, so a bar's height is
 * an integer times a height in dp and the phone never reads [charged]
 * or [collected] as a number to draw with [TC-9, D-20].
 *
 * @property period The month as `YYYY-MM`
 * @property charged What was billed, shown as text only
 * @property collected What came in, shown as text only
 * @property chargedBar Charged as a whole percent of the largest month
 * @property collectedBar Collected on the same scale
 * @property inProgress Whether the month contains today, so it is
 *   marked as still being collected
 */
data class MonthBar(
    val period: String,
    val charged: Money,
    val collected: Money,
    val chargedBar: Int,
    val collectedBar: Int,
    val inProgress: Boolean,
)

/**
 * Seats per filter, as the server counted them.
 *
 * @property paid Settled seats
 * @property checking Seats with a payment waiting to be checked
 * @property owed Seats still owing
 */
data class SeatCounts(
    val paid: Int,
    val checking: Int,
    val owed: Int,
)

/** One batch's row on the report: its figures, or why they are missing. */
sealed interface BatchRowItem {
    /** The batch. */
    val batchId: String

    /** Its name. */
    val name: String
}

/**
 * One batch whose figures could not be read, so only its row says so.
 *
 * @property batchId The batch
 * @property name Its name
 * @property messageKey A string resource key, never server English
 * @property retryable Whether the server said retrying could help
 */
data class BatchRowFailed(
    override val batchId: String,
    override val name: String,
    val messageKey: String,
    val retryable: Boolean,
) : BatchRowItem

/**
 * One batch's figures for the month the headline shows.
 *
 * @property batchId The batch
 * @property name Its name
 * @property period The month as `YYYY-MM`
 * @property collected Cash in for the month
 * @property charged What the month was billed
 * @property counts Seats per filter, the server's counts
 */
data class BatchMonthRow(
    override val batchId: String,
    override val name: String,
    val period: String,
    val collected: Money,
    val charged: Money,
    val counts: SeatCounts,
) : BatchRowItem

/**
 * Everything the collections screen (M1) can be showing.
 */
sealed interface CollectionsUiState {
    /** The first load, with nothing to show yet. */
    data object Loading : CollectionsUiState

    /**
     * The report.
     *
     * @property batches The chips; none selected means all batches
     * @property months The chart, oldest first
     * @property headlinePeriod The month the first tile and the batch
     *   rows describe: the latest month that is not still in progress
     * @property headlineCollected Cash in for that month
     * @property headlineCharged What that month was billed
     * @property outstanding Still owed, all months
     * @property owingStudents How many seats owe it
     * @property batchRows One row per batch in view for the headline month
     */
    data class Loaded(
        val batches: List<BatchChip>,
        val months: List<MonthBar>,
        val headlinePeriod: String?,
        val headlineCollected: Money?,
        val headlineCharged: Money?,
        val outstanding: Money,
        val owingStudents: Int,
        val batchRows: List<BatchRowItem>,
    ) : CollectionsUiState

    /**
     * The load failed.
     *
     * @property messageKey A string resource key, never server English
     * @property retryable Whether the server said retrying could help
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : CollectionsUiState
}
