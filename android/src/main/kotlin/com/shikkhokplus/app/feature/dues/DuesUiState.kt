package com.shikkhokplus.app.feature.dues

import com.shikkhokplus.app.core.model.Money

/**
 * How late a debt is, as the server grouped it.
 *
 * The server compared the due dates; this only names its answer.
 */
enum class DuesGroupKind {
    /** More than 30 days late. */
    OVER_30,

    /** 1 to 30 days late. */
    LATE,

    /** Owing, not yet past its due date. */
    NOT_LATE,
}

/** Which rows the screen shows. Each keys on a value the server sent. */
enum class DuesFilter {
    /** Every row. */
    ALL,

    /** Rows the server grouped as late. */
    LATE_ONLY,

    /** Rows the server says were never reminded. */
    NOT_REMINDED,
}

/**
 * One dues row as the screen renders it.
 *
 * **Every field here is carried, not computed.** The temptation on a
 * dues screen is `if (outstanding > 0) "Due"` or
 * `if (daysLate > 30) OVERDUE`, and both are business rules about what
 * counts as due wearing presentation's clothes [TC-9, D-31]. The server
 * decided membership, lateness and the group.
 *
 * @property enrollmentId The teacher-facing key
 * @property batchId The batch, for the batch filter
 * @property displayName The teacher-typed name
 * @property batchName Which class the debt is in
 * @property outstanding What this seat owes
 * @property oldestUnpaidPeriod Which period the debt starts in, or null
 * @property latestUnpaidPeriod Which period it runs to, or null
 * @property daysLate Days late, or null when nothing is past due
 * @property group Which group the server put it in
 * @property lastRemindedAt When a reminder last went out, or null
 * @property remindable Whether "Remind" would reach this seat now
 */
data class DuesRow(
    val enrollmentId: String,
    val displayName: String,
    val batchName: String,
    val outstanding: Money,
    val oldestUnpaidPeriod: String?,
    val batchId: String = "",
    val latestUnpaidPeriod: String? = null,
    val daysLate: Int? = null,
    val group: DuesGroupKind = DuesGroupKind.NOT_LATE,
    val lastRemindedAt: String? = null,
    val remindable: Boolean = false,
)

/**
 * One group's total.
 *
 * @property kind Which group
 * @property total What it owes
 * @property count How many rows
 * @property share Its whole-percent share of everything, for the bar
 */
data class DuesGroupTotal(
    val kind: DuesGroupKind,
    val total: Money,
    val count: Int,
    val share: Int,
)

/**
 * The headline card.
 *
 * @property total Everything owed
 * @property count How many seats owe it
 * @property remindable How many seats "Remind" would reach
 * @property groups One per group, latest first
 */
data class DuesSummary(
    val total: Money,
    val count: Int,
    val remindable: Int,
    val groups: List<DuesGroupTotal>,
)

/**
 * A batch the filter can narrow to.
 *
 * @property id The batch
 * @property name Its name
 */
data class DuesBatch(val id: String, val name: String)

/** Where a "Remind" tap stands. */
sealed interface RemindState {
    /** Nothing asked. */
    data object Idle : RemindState

    /** The teacher is confirming. */
    data object Confirming : RemindState

    /** Sent and waiting for the server. */
    data object Sending : RemindState

    /**
     * The server answered.
     *
     * @property sent Seats reminded
     */
    data class Sent(val sent: Int) : RemindState

    /**
     * It failed.
     *
     * @property messageKey Names a string resource
     */
    data class Failed(val messageKey: String) : RemindState
}

/**
 * Everything the cross-batch dues screen renders.
 *
 * The four load states are the ones `team.md` requires every ViewModel
 * to ship tests for: loading, success, error, and the explicit retry
 * path [TC-8, D-9]. There is no offline queue in V1.
 */
sealed interface DuesUiState {
    /** Nothing has been asked for yet. */
    data object Idle : DuesUiState

    /** A request is in flight. */
    data object Loading : DuesUiState

    /**
     * Somebody owes money.
     *
     * @property summary The headline figures
     * @property rows The rows the filter lets through, **in the order
     *   the server returned them** -- latest debt first
     * @property filter The open filter
     * @property batch The batch narrowed to, or null for all
     * @property batches Every batch with a row, for the batch filter
     * @property remind Where a "Remind" tap stands
     */
    data class Loaded(
        val summary: DuesSummary,
        val rows: List<DuesRow>,
        val filter: DuesFilter = DuesFilter.ALL,
        val batch: DuesBatch? = null,
        val batches: List<DuesBatch> = emptyList(),
        val remind: RemindState = RemindState.Idle,
    ) : DuesUiState

    /**
     * Nobody owes anything.
     *
     * **A separate state rather than a [Loaded] with no rows**: an
     * empty dues list is good news and deserves a sentence saying so.
     */
    data object Empty : DuesUiState

    /**
     * Something failed, and the screen can say what to do about it.
     *
     * @property messageKey Names a string resource; never English text
     *   from the server, which could not be localized [TC-15, D-43]
     * @property retryable Read from the server's envelope, never
     *   inferred from a status code [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : DuesUiState
}
