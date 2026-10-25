package com.shikkhokplus.app.feature.batches

import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.ErrorEnvelope

/**
 * Maps server responses to a [BatchesUiState].
 *
 * **This object is the unit under test**, rather than "the ViewModel".
 * It is pure: no network, no storage, no clock. A decision needing any
 * of those would be a business rule, and business rules are server-side
 * [TC-9, D-31].
 *
 * *(Moved out of `BatchesViewModel.kt` in D2.)* It was already written
 * as a pure object and already the tests' target; it lived in the
 * ViewModel's file, which is the one place a reader looking for the
 * mapper does not look. `RosterStateMapper` and `InvitationsStateMapper`
 * are each their own file and this now matches them — the test target
 * being findable is the whole reason the practice names mapping
 * functions rather than ViewModels.
 */
object BatchesStateMapper {
    /** Shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /**
     * Map a loaded list.
     *
     * **Both counts are read, never derived** [BR1.3, NFR20.9]. The
     * temptation here is `rows.count { it.acceptedCount > 0 }` or any
     * other client-side tally; that is the client deciding what counts
     * as accepted, and it would be wrong the moment the roster
     * paginates because the client can only count the rows it holds.
     *
     * @param rows The batches the server returned
     * @return The state the screen renders
     */
    fun afterLoad(rows: List<BatchDto>): BatchesUiState =
        if (rows.isEmpty()) {
            BatchesUiState.Empty
        } else {
            BatchesUiState.Loaded(
                rows.map { dto ->
                    BatchRow(
                        id = dto.id,
                        name = dto.name,
                        subjects = dto.subjects,
                        defaultFee = dto.defaultFee,
                        // Counted SERVER-side. A client counting a
                        // roster it has not fetched would be guessing,
                        // and one that fetched every roster to count
                        // would be the N+1 shape on the client.
                        enrollmentCount = dto.enrollmentCount,
                        acceptedCount = dto.acceptedCount,
                        active = dto.active,
                    )
                },
            )
        }

    /**
     * Map a server refusal.
     *
     * `retryable` is **read from the envelope**, never inferred from a
     * status code: the client holds no business logic, so it is told
     * rather than deciding [TC-9].
     *
     * @param envelope The server's error
     * @return The state the screen renders
     */
    fun afterError(envelope: ErrorEnvelope): BatchesUiState =
        BatchesUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope arrived.
     *
     * Always retryable: there is no local write queue in V1, so the
     * screen must offer an explicit retry rather than appearing to have
     * succeeded [TC-8, D-9].
     *
     * @return The offline state
     */
    fun afterTransportFailure(): BatchesUiState =
        BatchesUiState.Failed(OFFLINE_KEY, retryable = true)
}
