package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.verify.PaymentReviewRepository
import com.shikkhokplus.app.feature.verify.VerifyRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * The teacher's payment checks, over HTTP (R1 to R4).
 *
 * @property client The authenticated HTTP client
 */
class HttpVerificationRepository(
    private val client: HttpClient,
) : VerifyRepository, PaymentReviewRepository {

    override suspend fun queue(): AuthResult<VerificationQueueDto> = call { client.get("/v1/claims/queue") }

    override suspend fun detail(
        submissionId: String,
        purpose: String?,
        extraFeeId: String?,
    ): AuthResult<PaymentReviewDto> =
        call {
            client.get("/v1/payments/$submissionId") {
                purpose?.let { parameter("purpose", it) }
                extraFeeId?.let { parameter("extra_fee_id", it) }
            }
        }

    override suspend fun approve(
        submissionId: String,
        body: PaymentApprovalBodyDto,
    ): AuthResult<PaymentReviewDto> =
        call { client.post("/v1/payments/$submissionId/approval") { setBody(body) } }

    override suspend fun reject(
        submissionId: String,
        note: String?,
        correcting: Boolean,
    ): AuthResult<PaymentReviewDto> =
        call {
            client.post("/v1/payments/$submissionId/rejection") {
                setBody(PaymentRejectionBodyDto(note, correcting))
            }
        }
}
