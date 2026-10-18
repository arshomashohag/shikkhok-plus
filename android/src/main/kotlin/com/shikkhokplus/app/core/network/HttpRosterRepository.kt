package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.roster.RosterPayload
import com.shikkhokplus.app.feature.roster.RosterRepository
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.statement.HttpResponse
import io.ktor.http.isSuccess

/**
 * The real roster repository, over HTTP.
 *
 * @property client The configured HTTP client
 */
class HttpRosterRepository(
    private val client: HttpClient,
) : RosterRepository {

    override suspend fun roster(batchId: String): AuthResult<RosterPayload> =
        try {
            val response: HttpResponse = client.get("/v1/batches/$batchId/roster")
            if (response.status.isSuccess()) {
                AuthResult.Ok(
                    RosterPayload(
                        // The batch NAME is not on the roster response.
                        // Carrying an empty string rather than inventing
                        // one: the screen titles itself from the batch
                        // list, and a fabricated name here would render
                        // as though the server had sent it.
                        batchName = "",
                        rows = response.body(),
                        fetchedAtLabel = null,
                    ),
                )
            } else {
                AuthResult.Refused(decodeEnvelope(response))
            }
        } catch (_: Exception) {
            AuthResult.TransportFailure
        }

    override suspend fun removeEnrollment(
        enrollmentId: String,
    ): AuthResult<Unit> =
        try {
            val response = client.delete("/v1/enrollments/$enrollmentId")
            if (response.status.isSuccess()) {
                AuthResult.Ok(Unit)
            } else {
                AuthResult.Refused(decodeEnvelope(response))
            }
        } catch (_: Exception) {
            AuthResult.TransportFailure
        }
}
