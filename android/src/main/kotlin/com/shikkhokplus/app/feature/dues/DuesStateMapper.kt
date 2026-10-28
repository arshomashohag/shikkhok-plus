package com.shikkhokplus.app.feature.dues

import com.shikkhokplus.app.core.network.DuesGroupDto
import com.shikkhokplus.app.core.network.DuesResponseDto
import com.shikkhokplus.app.core.network.DuesRowDto
import com.shikkhokplus.app.core.network.DuesSummaryDto
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
     * **The rows are not sorted here.** The server returned them
     * latest debt first, and re-ordering would be the client deciding a
     * domain list's order — the second of the five erosion paths. The
     * groups are the server's too: each row carries its bucket.
     *
     * @param response The dues the server returned
     * @return The state the screen renders
     */
    fun afterLoad(response: DuesResponseDto): DuesUiState {
        if (response.rows.isEmpty()) {
            return DuesUiState.Empty
        }
        val rows = response.rows.map(::toRow)
        return DuesUiState.Loaded(
            summary = summary(response.summary),
            rows = rows,
            batches = response.rows.map { DuesBatch(it.batchId, it.batchName) }.distinctBy { it.id },
        )
    }

    /**
     * The rows a filter lets through, in the server's order.
     *
     * Each filter keys on a value the server sent — its group, whether
     * it was ever reminded, its batch — so nothing here compares money
     * or dates.
     *
     * @param rows Every row, in the server's order
     * @param filter The open filter
     * @param batchId The batch narrowed to, or null for all
     * @return The visible rows
     */
    fun visible(
        rows: List<DuesRow>,
        filter: DuesFilter,
        batchId: String?,
    ): List<DuesRow> =
        rows.filter { row ->
            val inBatch = batchId == null || row.batchId == batchId
            val passes =
                when (filter) {
                    DuesFilter.ALL -> true
                    DuesFilter.LATE_ONLY -> row.group != DuesGroupKind.NOT_LATE
                    DuesFilter.NOT_REMINDED -> row.lastRemindedAt == null
                }
            inBatch && passes
        }

    /**
     * The seats a "Remind" would send to: the ones the server marked.
     *
     * @param rows Every row
     * @return Their seat ids
     */
    fun remindTargets(rows: List<DuesRow>): List<String> = rows.filter { it.remindable }.map { it.enrollmentId }

    /**
     * Convert the headline.
     *
     * @param dto The server's totals
     * @return The card's figures
     */
    private fun summary(dto: DuesSummaryDto): DuesSummary =
        DuesSummary(
            total = dto.total,
            count = dto.count,
            remindable = dto.remindable,
            groups = dto.groups.mapNotNull(::group),
        )

    /**
     * Convert one group, dropping a bucket this app does not know.
     *
     * @param dto The server's group
     * @return The group, or null for an unknown bucket
     */
    private fun group(dto: DuesGroupDto): DuesGroupTotal? =
        kindOf(dto.bucket)?.let { DuesGroupTotal(it, dto.total, dto.count, dto.share) }

    /**
     * Name a server bucket.
     *
     * @param bucket The wire value
     * @return Its kind, or null when unknown
     */
    private fun kindOf(bucket: String): DuesGroupKind? =
        when (bucket) {
            "over_30" -> DuesGroupKind.OVER_30
            "late" -> DuesGroupKind.LATE
            "not_late" -> DuesGroupKind.NOT_LATE
            else -> null
        }

    /**
     * Convert one dues row.
     *
     * No comparison: every value is carried through, and the bucket is
     * only named. **If this function ever needs to compare a domain
     * value, the server should have sent a decision** — that is the
     * checkable form of the layer rule.
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
            batchId = dto.batchId,
            latestUnpaidPeriod = dto.latestUnpaidPeriod,
            daysLate = dto.daysLate,
            group = kindOf(dto.bucket) ?: DuesGroupKind.NOT_LATE,
            lastRemindedAt = dto.lastRemindedAt,
            remindable = dto.remindable,
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
