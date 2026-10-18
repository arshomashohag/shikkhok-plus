package com.shikkhokplus.app.feature.roster

import com.shikkhokplus.app.core.model.Money

/**
 * One roster row as the screen renders it.
 *
 * **`statusLabel` is a string resource key, not text**, and it is
 * chosen from the server's `status` enum rather than computed from
 * `inactiveFrom`. A client that decided "inactive" by comparing a date
 * would be holding a business rule [TC-9, D-31].
 *
 * `fee` stays a [Money] all the way to the renderer: converting it to a
 * string here would put the rendering decision on the client, and
 * converting it to a number would lose exactness [TC-7].
 *
 * @property enrollmentId The teacher-facing key
 * @property displayName The teacher-typed name
 * @property statusLabel A string resource key for the seat's status
 * @property fee This seat's fee, or null when it inherits
 * @property guardianPhone The teacher-typed guardian contact, if any
 */
data class RosterRow(
    val enrollmentId: String,
    val displayName: String,
    val statusLabel: String,
    val fee: Money?,
    val guardianPhone: String?,
)

/**
 * Everything the roster screen renders.
 *
 * The four states are the ones `team.md` requires every ViewModel to
 * ship tests for: loading, success, error, and the explicit retry path
 * for a failed write [TC-8, D-9]. There is no offline queue in V1, so a
 * failed write surfaces [Failed] with `retryable` rather than
 * succeeding locally and reconciling later.
 */
sealed interface RosterUiState {
    /** Nothing has been asked for yet. */
    data object Idle : RosterUiState

    /** A request is in flight. */
    data object Loading : RosterUiState

    /**
     * The roster loaded.
     *
     * [Empty] is a separate state rather than a success with no rows,
     * because an empty list and "this batch has no students yet" need
     * different screens and a blank list explains neither.
     *
     * @property batchName Which class this is
     * @property rows The seats, in the order the server returned them
     * @property fetchedAtLabel When this was fetched, for the staleness
     *   notice the cache requires
     */
    data class Loaded(
        val batchName: String,
        val rows: List<RosterRow>,
        val fetchedAtLabel: String?,
    ) : RosterUiState

    /**
     * The batch exists and holds no seats yet.
     *
     * @property batchName Which class this is
     */
    data class Empty(val batchName: String) : RosterUiState

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
    ) : RosterUiState
}
