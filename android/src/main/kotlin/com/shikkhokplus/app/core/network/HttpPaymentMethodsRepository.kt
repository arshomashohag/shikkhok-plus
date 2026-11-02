package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.paymentmethods.PaymentMethodDraft
import com.shikkhokplus.app.feature.paymentmethods.PaymentMethodsRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * The teacher's payment methods, over HTTP.
 *
 * The server owns validation and answers a refusal with its one error
 * envelope; nothing here checks a field beyond sending it.
 *
 * @property client The authenticated HTTP client
 */
class HttpPaymentMethodsRepository(
    private val client: HttpClient,
) : PaymentMethodsRepository {

    override suspend fun list(): AuthResult<List<PaymentMethodDto>> =
        call { client.get("/v1/payment-methods") }

    override suspend fun create(draft: PaymentMethodDraft): AuthResult<PaymentMethodDto> =
        call { client.post("/v1/payment-methods") { setBody(draft.toRequest()) } }

    override suspend fun update(
        methodId: String,
        draft: PaymentMethodDraft,
    ): AuthResult<PaymentMethodDto> =
        call { client.patch("/v1/payment-methods/$methodId") { setBody(draft.toRequest()) } }

    override suspend fun retire(methodId: String): AuthResult<Unit> =
        callDiscardingBody { client.delete("/v1/payment-methods/$methodId") }
}

private fun PaymentMethodDraft.toRequest(): PaymentMethodRequestDto =
    PaymentMethodRequestDto(
        kind = kind.wire,
        provider = provider,
        mobileNumber = mobileNumber,
        accountNumber = accountNumber,
        accountName = accountName,
        branchName = branchName,
        note = note,
    )
