package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.pay.PayRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * Paying a fee (S3), over HTTP.
 *
 * @property client The authenticated HTTP client
 */
class HttpPayRepository(
    private val client: HttpClient,
) : PayRepository {

    override suspend fun payables(): AuthResult<PayablesDto> = call { client.get("/v1/me/payables") }

    override suspend fun destination(enrollmentId: String): AuthResult<PaymentDestinationDto?> =
        call { client.get("/v1/enrollments/$enrollmentId/payment-destination") }

    override suspend fun submit(enrollmentId: String, claim: ClaimSubmitDto): AuthResult<ClaimDto> =
        call { client.post("/v1/enrollments/$enrollmentId/claims") { setBody(claim) } }
}
