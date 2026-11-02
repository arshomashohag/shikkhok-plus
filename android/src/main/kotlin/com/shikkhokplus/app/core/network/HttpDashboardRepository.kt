package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.dashboard.DashboardRange
import com.shikkhokplus.app.feature.dashboard.DashboardReader
import com.shikkhokplus.app.feature.dashboard.DashboardRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter

/**
 * The progress dashboard, over HTTP.
 *
 * @property client The authenticated HTTP client
 */
class HttpDashboardRepository(
    private val client: HttpClient,
) : DashboardRepository {

    /**
     * Read one seat's dashboard over the reader's own path.
     *
     * @param reader Who is reading
     * @param seat The seat
     * @param range How far back
     * @return The dashboard, an error envelope, or a transport failure
     */
    override suspend fun dashboard(
        reader: DashboardReader,
        seat: String,
        range: DashboardRange,
    ): AuthResult<DashboardDto> =
        call {
            client.get(pathFor(reader, seat)) { parameter("range", range.wire) }
        }

    /**
     * Read the guardian's children.
     *
     * @return The children, an error envelope, or a transport failure
     */
    override suspend fun children(): AuthResult<GuardianHomeDto> = call { client.get("/v1/guardian/home") }

    private fun pathFor(
        reader: DashboardReader,
        seat: String,
    ): String =
        when (reader) {
            DashboardReader.TEACHER -> "/v1/enrollments/$seat/dashboard"
            DashboardReader.STUDENT -> "/v1/me/enrollments/$seat/dashboard"
            DashboardReader.GUARDIAN -> "/v1/children/$seat/dashboard"
        }
}
