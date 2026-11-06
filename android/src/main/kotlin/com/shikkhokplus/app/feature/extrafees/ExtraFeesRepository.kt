package com.shikkhokplus.app.feature.extrafees

import com.shikkhokplus.app.core.network.BatchExtraFeesDto
import com.shikkhokplus.app.core.network.ExamDto
import com.shikkhokplus.app.core.network.ExtraFeeDetailDto
import com.shikkhokplus.app.core.network.ExtraFeeRaiseRequestDto
import com.shikkhokplus.app.core.network.ExtraFeeSummaryDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the teacher's exam and other fee screens need from the network. */
interface ExtraFeesRepository {
    /**
     * Read a batch's fees and who a new one could charge.
     *
     * @param batchId The batch
     * @return The fees, a refusal, or a transport failure
     */
    suspend fun batchFees(batchId: String): AuthResult<BatchExtraFeesDto>

    /**
     * Read one fee and its students.
     *
     * @param extraFeeId The fee
     * @return The fee, a refusal, or a transport failure
     */
    suspend fun fee(extraFeeId: String): AuthResult<ExtraFeeDetailDto>

    /**
     * Raise a fee on a batch.
     *
     * @param batchId The batch
     * @param request What the teacher chose
     * @return The raised fee, a refusal, or a transport failure
     */
    suspend fun raise(batchId: String, request: ExtraFeeRaiseRequestDto): AuthResult<ExtraFeeSummaryDto>

    /**
     * Read the batch's exams, for linking an exam fee to one.
     *
     * @param batchId The batch
     * @return The exams, a refusal, or a transport failure
     */
    suspend fun exams(batchId: String): AuthResult<List<ExamDto>>
}
