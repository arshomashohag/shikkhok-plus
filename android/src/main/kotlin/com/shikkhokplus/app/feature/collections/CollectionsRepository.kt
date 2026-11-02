package com.shikkhokplus.app.feature.collections

import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.BatchFeesDto
import com.shikkhokplus.app.core.network.CollectionsDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the money reports (M1, M2) read from the network. */
interface CollectionsRepository {
    /**
     * List the teacher's batches, for the filter chips.
     *
     * @return The batches, a refusal, or a transport failure
     */
    suspend fun batches(): AuthResult<List<BatchDto>>

    /**
     * Read collected versus charged by month.
     *
     * @param batchIds The batches to narrow to; empty means all
     * @param months How many months, ending at the current one
     * @return The report, a refusal, or a transport failure
     */
    suspend fun collections(
        batchIds: List<String>,
        months: Int,
    ): AuthResult<CollectionsDto>

    /**
     * Read one batch in one month.
     *
     * @param batchId The batch
     * @param period `YYYY-MM`, or null for the current month
     * @return The month, a refusal, or a transport failure
     */
    suspend fun batchMonth(
        batchId: String,
        period: String?,
    ): AuthResult<BatchFeesDto>
}
