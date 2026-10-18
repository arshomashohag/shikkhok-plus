package com.shikkhokplus.app.feature.batches

import com.shikkhokplus.app.core.model.Money

/**
 * One batch as the list renders it.
 *
 * `defaultFee` stays a [Money] all the way to the renderer. Formatting
 * it here would put the rendering decision on the client, and the
 * Bangla rendering specification is deliberately server-side [OQ-B1-1].
 *
 * @property id The batch
 * @property name The teacher's name for the class
 * @property subjects The subjects taught
 * @property defaultFee The fee an enrollment inherits, or null
 * @property enrollmentCount How many seats, counted SERVER-side
 * @property active False means read-only history
 */
data class BatchRow(
    val id: String,
    val name: String,
    val subjects: List<String>,
    val defaultFee: Money?,
    val enrollmentCount: Int,
    val active: Boolean,
)

/**
 * Everything the batch list renders.
 *
 * The four states `team.md` requires of every ViewModel: loading,
 * success, error, and an explicit retry path. [Empty] is separate from
 * a success with no rows because "no classes yet" and a blank list need
 * different screens, and a blank list explains neither.
 */
sealed interface BatchesUiState {
    /** Nothing has been asked for yet. */
    data object Idle : BatchesUiState

    /** A request is in flight. */
    data object Loading : BatchesUiState

    /**
     * The list loaded and holds at least one batch.
     *
     * @property rows The batches, in the order the server returned them
     */
    data class Loaded(val rows: List<BatchRow>) : BatchesUiState

    /** The teacher has no batches yet. */
    data object Empty : BatchesUiState

    /**
     * Something failed.
     *
     * @property messageKey Names a string resource, never English text
     *   from the server, which could not be localized [TC-15, D-43]
     * @property retryable Read from the server's envelope, never
     *   inferred from a status code [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : BatchesUiState
}
