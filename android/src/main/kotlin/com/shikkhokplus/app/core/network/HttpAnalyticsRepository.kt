package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.dues.DuesRepository
import com.shikkhokplus.app.feature.today.TodayRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * The Today and dues repositories, over HTTP.
 *
 * **Both routes are `/v1/me/...` and carry no identifier.** The server
 * resolves what to show from the authenticated account's own lens, so
 * there is no teacher id, no batch id and nothing a caller could point
 * at someone else's data. That is the same shape the guardian route
 * takes, and for the same reason: a route that accepted an id would
 * rely on the server refusing it, which works until one endpoint
 * forgets.
 *
 * @property client The authenticated HTTP client
 */
class HttpAnalyticsRepository(
    private val client: HttpClient,
) : TodayRepository, DuesRepository {

    /**
     * Read the Today screen for whoever is signed in (T1).
     *
     * @return The day's view, an error envelope, or a transport failure
     */
    override suspend fun today(): AuthResult<TodayDto> = call { client.get("/v1/me/today") }

    /**
     * Read who owes money, across every batch.
     *
     * **Membership is the server's decision** [PU-7.2]. The list is
     * driven by outstanding balance rather than active status, so a
     * student who left owing money still appears — which is exactly
     * the rule the client must not re-derive.
     *
     * @return The dues, an error envelope, or a transport failure
     */
    override suspend fun dues(): AuthResult<DuesResponseDto> =
        call { client.get("/v1/me/dues") }

    /**
     * Remind these seats what they owe, in the app.
     *
     * @param enrollmentIds The seats
     * @return How many were reminded and skipped, an error envelope, or
     *   a transport failure
     */
    override suspend fun remind(enrollmentIds: List<String>): AuthResult<ReminderResultDto> =
        call { client.post("/v1/reminders") { setBody(ReminderBody(enrollmentIds)) } }
}
