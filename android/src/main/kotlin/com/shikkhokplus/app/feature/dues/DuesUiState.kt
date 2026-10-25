package com.shikkhokplus.app.feature.dues

import com.shikkhokplus.app.core.model.Money

/**
 * One dues row as the screen renders it.
 *
 * **Every field here is carried, not computed.** The temptation on a
 * dues screen is `if (outstanding > 0) "Due"` or
 * `if (daysLate > 30) OVERDUE`, and both are business rules about what
 * counts as due wearing presentation's clothes [TC-9, D-31]. The server
 * decided membership; the row's presence IS the decision.
 *
 * `outstanding` stays a [Money] all the way to the renderer.
 * Converting it to a string here would put the rendering decision on
 * the client, and converting it to a number would lose exactness
 * [TC-7].
 *
 * @property enrollmentId The teacher-facing key
 * @property displayName The teacher-typed name
 * @property batchName Which class the debt is in. Shown on every row
 *   rather than grouped, because the same person may owe in two and a
 *   client-side grouping would be the client deciding the list's shape
 * @property outstanding What this seat owes
 * @property oldestUnpaidPeriod Which period the debt starts in, or
 *   null when the server sent none
 */
data class DuesRow(
    val enrollmentId: String,
    val displayName: String,
    val batchName: String,
    val outstanding: Money,
    val oldestUnpaidPeriod: String?,
)

/**
 * Everything the cross-batch dues screen renders.
 *
 * The four states are the ones `team.md` requires every ViewModel to
 * ship tests for: loading, success, error, and the explicit retry path
 * [TC-8, D-9]. There is no offline queue in V1.
 */
sealed interface DuesUiState {
    /** Nothing has been asked for yet. */
    data object Idle : DuesUiState

    /** A request is in flight. */
    data object Loading : DuesUiState

    /**
     * Somebody owes money.
     *
     * @property rows The seats, **in the order the server returned
     *   them** — largest debt first, decided server-side. Re-sorting
     *   here would be the client deciding the list's order
     */
    data class Loaded(val rows: List<DuesRow>) : DuesUiState

    /**
     * Nobody owes anything.
     *
     * **A separate state rather than a [Loaded] with no rows**, and the
     * distinction matters more here than on most screens: an empty dues
     * list is *good news* and deserves a sentence saying so. A blank
     * list explains nothing, and a teacher seeing one cannot tell it
     * apart from a failed load.
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
