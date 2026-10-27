package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.fees.FeesRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter

/**
 * The fee history repository, over HTTP.
 *
 * **Three routes for the same shape, one per lens** [BR6.3]. A
 * student reads their own seat, a guardian reads a child's, a teacher
 * reads one in a batch they own — and each is a different path
 * because the server resolves a different lens for it. One route
 * taking a role parameter would be the client choosing which lens to
 * be, which [TC-11, D-2] forbids.
 *
 * Every response carries the server's own `total_outstanding`. The
 * client never sums the rows [D-20].
 *
 * @property client The authenticated HTTP client
 */
class HttpFeesRepository(
    private val client: HttpClient,
) : FeesRepository {

    /**
     * Read the signed-in student's own history for one seat.
     *
     * The seat is a query parameter and the grant is checked against
     * it, never the other way round.
     *
     * @param enrollmentId The seat to read
     * @return The history, a refusal, or a transport failure
     */
    override suspend fun myFees(
        enrollmentId: String,
    ): AuthResult<FeeHistoryDto> =
        call {
            client.get("/v1/me/fees") { parameter("enrollment_id", enrollmentId) }
        }

    /**
     * Read one child's history, for their recorded guardian.
     *
     * The child is a **path parameter**, never a client-supplied lens
     * hint [BR5.1].
     *
     * @param enrollmentId The child's seat
     * @return The history, a refusal, or a transport failure
     */
    override suspend fun childFees(
        enrollmentId: String,
    ): AuthResult<FeeHistoryDto> =
        call { client.get("/v1/children/$enrollmentId/fees") }

    /**
     * Read one seat's history, for the teacher who owns its batch.
     *
     * @param enrollmentId The seat to read
     * @return The history, a refusal, or a transport failure
     */
    override suspend fun enrollmentFees(
        enrollmentId: String,
    ): AuthResult<FeeHistoryDto> =
        call { client.get("/v1/enrollments/$enrollmentId/fees") }
}
