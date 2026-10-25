package com.shikkhokplus.app.feature.dues

import com.shikkhokplus.app.core.network.DuesResponseDto
import com.shikkhokplus.app.core.network.DuesRowDto
import com.shikkhokplus.app.core.network.ErrorEnvelope

/**
 * Maps the dues response to a [DuesUiState].
 *
 * **This function is the unit under test**, rather than "the
 * ViewModel". It is pure: no network, no storage, no clock. A decision
 * needing any of those would be a business rule, and business rules are
 * server-side [TC-9, D-31].
 */
object DuesStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /**
     * Map a loaded dues response.
     *
     * **An empty list becomes [DuesUiState.Empty], and that is the only
     * decision this function makes.** It is a presentation decision
     * rather than a domain one: the server already decided who owes,
     * and this chooses between two screens for the answer "nobody".
     *
     * **The rows are not sorted, filtered or grouped here.** The server
     * returned them largest debt first, and re-ordering would be the
     * client deciding a domain list's order — the second of the five
     * erosion paths. Grouping by batch would be the same mistake in a
     * friendlier shape: the batch name is on every row precisely so a
     * grouping is unnecessary.
     *
     * @param response The dues the server returned
     * @return The state the screen renders
     */
    fun afterLoad(response: DuesResponseDto): DuesUiState {
        if (response.rows.isEmpty()) {
            return DuesUiState.Empty
        }
        return DuesUiState.Loaded(response.rows.map(::toRow))
    }

    /**
     * Convert one dues row.
     *
     * No branch and no comparison: every value is carried through.
     * **If this function ever needs an `if`, the server should have
     * sent a decision** — that is the checkable form of the layer rule
     * and the test a reader can apply to any change here.
     *
     * @param dto The row the server returned
     * @return The row the screen renders
     */
    private fun toRow(dto: DuesRowDto): DuesRow =
        DuesRow(
            enrollmentId = dto.enrollmentId,
            displayName = dto.displayName,
            batchName = dto.batchName,
            outstanding = dto.outstanding,
            oldestUnpaidPeriod = dto.oldestUnpaidPeriod,
        )

    /**
     * Map a server error envelope.
     *
     * `retryable` is **read from the envelope**, never inferred from a
     * status code: the client holds no business logic, so it is told
     * rather than deciding [TC-9].
     *
     * @param envelope The server's error
     * @return The state the screen renders
     */
    fun afterError(envelope: ErrorEnvelope): DuesUiState =
        DuesUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * Always retryable: there is no local write queue in V1, so the
     * screen offers an explicit retry rather than appearing to have
     * succeeded [TC-8, D-9].
     *
     * @return The offline state
     */
    fun afterTransportFailure(): DuesUiState =
        DuesUiState.Failed(OFFLINE_KEY, retryable = true)
}
