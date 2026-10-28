package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.attendance.AttendanceRepository
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.HttpStatusCode
import io.ktor.http.isSuccess
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
private data class SeatBody(
    @SerialName("enrollment_id") val enrollmentId: String,
    val present: Boolean,
)

@Serializable
private data class SubmitBody(
    @SerialName("base_attendance_version") val baseAttendanceVersion: Int,
    @SerialName("client_mutation_id") val clientMutationId: String,
    // **`seats`, not `entries`.** The server's AttendanceSubmitRequest
    // names this field `seats`; a camelCase or differently-named key
    // is dropped silently and the request then fails for a missing
    // required field, which reads as a server fault rather than a
    // client one.
    val seats: List<SeatBody>,
)

@Serializable
private data class SubmitResponse(
    @SerialName("attendance_version") val attendanceVersion: Int,
)

/**
 * The attendance repository, over HTTP.
 *
 * **Three outcomes, and the middle one is the point** [TC-8, D-9].
 * Attendance is recorded mid-class on a phone that may lose signal, so
 * a write can be applied, refused for a version conflict, or fail to
 * reach the server at all — and each needs different handling. A
 * conflict is NOT a failure: somebody else recorded against the same
 * session, and the person needs to see what changed rather than
 * retrying blindly over it.
 *
 * @property client The authenticated HTTP client
 */
class HttpAttendanceRepository(
    private val client: HttpClient,
) : AttendanceRepository {

    /**
     * Send one queued write.
     *
     * The `client_mutation_id` travels with it, so a retry after an
     * unknown outcome is recognised by the server rather than
     * recorded twice.
     *
     * @param item The write to send
     * @return Applied with the new version, Conflicted, or Failed
     */
    override suspend fun submit(item: QueuedWrite): SendOutcome =
        try {
            val response =
                client.post("/v1/sessions/${item.sessionId}/attendance") {
                    setBody(
                        SubmitBody(
                            baseAttendanceVersion = item.baseVersion,
                            clientMutationId = item.clientMutationId,
                            seats =
                                item.entries.map {
                                    SeatBody(it.enrollmentId, it.present)
                                },
                        ),
                    )
                }

            when {
                response.status.isSuccess() ->
                    SendOutcome.Applied(
                        response.body<SubmitResponse>().attendanceVersion,
                    )

                // **409 is a conflict, not a failure.** Treating it as
                // one would send the person into a retry loop against
                // a version that will never match.
                response.status == HttpStatusCode.Conflict ->
                    SendOutcome.Conflicted(
                        currentVersion = item.baseVersion,
                        envelope = decodeEnvelope(response),
                    )

                else -> SendOutcome.Failed(decodeEnvelope(response))
            }
        } catch (_: Exception) {
            // No response arrived, so there is no envelope to read a
            // retry policy from and the client must not invent one.
            SendOutcome.Failed(null)
        }

    /**
     * Read the roster as it stands now, after a conflict.
     *
     * @param sessionId The session that conflicted
     * @return The current roster and version, a refusal, or a
     *   transport failure
     */
    override suspend fun currentRoster(
        sessionId: String,
    ): AuthResult<SessionRosterDto> =
        call { client.get("/v1/sessions/$sessionId/attendance") }
}
