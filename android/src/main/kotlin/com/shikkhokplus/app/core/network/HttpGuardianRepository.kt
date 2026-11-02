package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.guardian.ChildProgressRepository
import com.shikkhokplus.app.feature.guardian.GuardianRepository
import com.shikkhokplus.app.feature.guardian.PaymentsRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get

/**
 * The guardian repository, over HTTP.
 *
 * **The home names no child**: the server resolves the seats from the
 * authenticated account's own `guardian_account_id` [BR4.1, NFR14.29].
 * The per-child reads name one of the child's seats, which the server
 * re-checks against that same account.
 *
 * @property client The authenticated HTTP client
 */
class HttpGuardianRepository(
    private val client: HttpClient,
) : GuardianRepository, PaymentsRepository, ChildProgressRepository {

    override suspend fun home(): AuthResult<GuardianHomeDto> = call { client.get("/v1/guardian/home") }

    override suspend fun me(): AuthResult<MeDto> = call { client.get("/v1/me") }

    override suspend fun payments(seat: String): AuthResult<PaymentsDto> =
        call { client.get("/v1/children/$seat/payments") }

    override suspend fun payables(seat: String): AuthResult<PayablesDto> =
        call { client.get("/v1/children/$seat/payables") }

    override suspend fun progress(seat: String): AuthResult<List<ProgressEntryDto>> =
        call { client.get("/v1/children/$seat/progress") }

    override suspend fun progressSummary(seat: String): AuthResult<ProgressSummaryDto?> =
        call { client.get("/v1/children/$seat/progress/summary") }
}
