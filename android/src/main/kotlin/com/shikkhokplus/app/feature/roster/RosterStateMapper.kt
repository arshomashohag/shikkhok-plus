package com.shikkhokplus.app.feature.roster

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RosterRowDto

/**
 * Maps server responses to a [RosterUiState].
 *
 * **This function is the unit under test**, rather than "the
 * ViewModel". It is pure: no network, no storage, no clock. A decision
 * needing any of those would be a business rule, and business rules are
 * server-side [TC-9, D-31].
 */
object RosterStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be parsed. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /**
     * String resource keys for the three server-decided statuses.
     *
     * **The mapping is exhaustive and an unknown value is an error**,
     * not a silent default. A server that added a fourth status would
     * otherwise render every new seat under whichever label happened to
     * be the fallback, which is worse than showing nothing.
     */
    private val STATUS_KEYS: Map<String, String> =
        mapOf(
            "dormant" to "roster.status.dormant",
            "active" to "roster.status.active",
            "inactive" to "roster.status.inactive",
        )

    /**
     * Map a loaded roster.
     *
     * @param batchName Which class this is
     * @param rows The seats the server returned
     * @param fetchedAtLabel When this was fetched, or null when live
     * @return The state the screen renders
     */
    fun afterLoad(
        batchName: String,
        rows: List<RosterRowDto>,
        fetchedAtLabel: String? = null,
    ): RosterUiState {
        if (rows.isEmpty()) {
            return RosterUiState.Empty(batchName)
        }

        val mapped =
            rows.map { row ->
                val label =
                    STATUS_KEYS[row.status]
                        ?: return RosterUiState.Failed(UNEXPECTED_KEY, retryable = false)
                RosterRow(
                    enrollmentId = row.enrollmentId,
                    displayName = row.displayName,
                    statusLabel = label,
                    fee = row.feeAmount,
                    guardianPhone = row.guardianPhone,
                )
            }
        return RosterUiState.Loaded(batchName, mapped, fetchedAtLabel)
    }

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
    fun afterError(envelope: ErrorEnvelope): RosterUiState =
        RosterUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * Always retryable: there is no local write queue in V1, so the
     * screen must offer an explicit retry rather than appearing to have
     * succeeded [TC-8, D-9].
     *
     * @return The offline state
     */
    fun afterTransportFailure(): RosterUiState =
        RosterUiState.Failed(OFFLINE_KEY, retryable = true)
}
