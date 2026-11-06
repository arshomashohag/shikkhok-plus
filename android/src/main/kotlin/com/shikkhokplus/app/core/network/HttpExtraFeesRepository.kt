package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.extrafees.ExtraFeesRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * A batch's exam and other fees, over HTTP. The server validates every
 * field and computes every figure.
 *
 * @property client The authenticated HTTP client
 */
class HttpExtraFeesRepository(
    private val client: HttpClient,
) : ExtraFeesRepository {

    override suspend fun batchFees(batchId: String): AuthResult<BatchExtraFeesDto> =
        call { client.get("/v1/batches/$batchId/extra-fees") }

    override suspend fun fee(extraFeeId: String): AuthResult<ExtraFeeDetailDto> =
        call { client.get("/v1/extra-fees/$extraFeeId") }

    override suspend fun raise(
        batchId: String,
        request: ExtraFeeRaiseRequestDto,
    ): AuthResult<ExtraFeeSummaryDto> = call { client.post("/v1/batches/$batchId/extra-fees") { setBody(request) } }

    override suspend fun exams(batchId: String): AuthResult<List<ExamDto>> = HttpMarksRepository(client).exams(batchId)
}
