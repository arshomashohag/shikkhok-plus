package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.payroll.PayrollRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * A centre's payroll, and my own pay, over HTTP. The centre's routes are
 * manager-only; `GET /v1/me/pay` returns only lines that pay this account.
 *
 * @property client The authenticated HTTP client
 */
class HttpPayrollRepository(
    private val client: HttpClient,
) : PayrollRepository {

    override suspend fun month(period: String): AuthResult<List<SalaryLineDto>> =
        call { client.get("/v1/centre/payroll/$period") }

    override suspend fun draw(period: String): AuthResult<List<SalaryLineDto>> =
        call { client.post("/v1/centre/payroll/$period/lines") }

    override suspend fun adjust(lineId: String, body: AdjustmentBodyDto): AuthResult<SalaryLineDto> =
        call { client.post("/v1/centre/payroll/lines/$lineId/adjustments") { setBody(body) } }

    override suspend fun removeAdjustment(lineId: String, adjustmentId: String): AuthResult<SalaryLineDto> =
        call { client.delete("/v1/centre/payroll/lines/$lineId/adjustments/$adjustmentId") }

    override suspend fun approve(lineId: String): AuthResult<SalaryLineDto> =
        call { client.post("/v1/centre/payroll/lines/$lineId/approve") }

    override suspend fun pay(lineId: String, body: SalaryPaymentBodyDto): AuthResult<SalaryLineDto> =
        call { client.post("/v1/centre/payroll/lines/$lineId/payments") { setBody(body) } }

    override suspend fun myPay(): AuthResult<List<SalaryLineDto>> = call { client.get("/v1/me/pay") }
}
