package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.sessions.SessionsRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
private data class SessionCreateBody(
    val date: String,
    @SerialName("start_time") val startTime: String,
    @SerialName("batch_subject_id") val batchSubjectId: String? = null,
)

@Serializable
private data class RescheduleBody(
    val date: String,
    @SerialName("start_time") val startTime: String,
)

/**
 * The sessions repository, over HTTP.
 *
 * **`end_time` is deliberately not sent.** The server's
 * `SessionCreateRequest` accepts it and does not require it, and the
 * screen never asks for one: a teacher adding an extra class knows
 * when it starts and rarely when it ends. Sending a guessed value
 * would record something nobody chose.
 *
 * @property client The authenticated HTTP client
 */
class HttpSessionsRepository(
    private val client: HttpClient,
) : SessionsRepository {

    /**
     * List a batch's sessions.
     *
     * @param batchId The batch whose sessions to read
     * @return The sessions, an error envelope, or a transport failure
     */
    override suspend fun sessions(batchId: String): AuthResult<List<SessionDto>> =
        call { client.get("/v1/batches/$batchId/sessions") }

    /**
     * Read one session with its seats, from the server's two paths.
     *
     * The session first, then its roster; a refusal or transport
     * failure on either is the result, so a half-read never renders.
     *
     * @param sessionId The session to read
     * @return The detail, an error envelope, or a transport failure
     */
    override suspend fun sessionDetail(sessionId: String): AuthResult<SessionDetailDto> {
        val session: AuthResult<SessionDto> = call { client.get("/v1/sessions/$sessionId") }
        val roster: AuthResult<SessionRosterDto> =
            when (session) {
                is AuthResult.Ok -> call { client.get("/v1/sessions/$sessionId/attendance") }
                is AuthResult.Refused -> return session
                AuthResult.TransportFailure -> return AuthResult.TransportFailure
            }
        return when (roster) {
            is AuthResult.Ok ->
                AuthResult.Ok(
                    SessionDetailDto(
                        session = (session as AuthResult.Ok).value,
                        seats = roster.value.seats,
                        writable = roster.value.writable,
                    ),
                )
            is AuthResult.Refused -> roster
            AuthResult.TransportFailure -> AuthResult.TransportFailure
        }
    }

    /**
     * Add a session the recurring schedule did not generate.
     *
     * @param batchId The batch to add it to
     * @param date The date it happens
     * @param startTime When it starts
     * @param batchSubjectId Which subject, or null to leave it unset
     * @return Nothing on success, or why the server refused
     */
    override suspend fun createAdHoc(
        batchId: String,
        date: String,
        startTime: String,
        batchSubjectId: String?,
    ): AuthResult<Unit> =
        callDiscardingBody {
            client.post("/v1/batches/$batchId/sessions") {
                setBody(
                    SessionCreateBody(
                        date = date,
                        startTime = startTime,
                        batchSubjectId = batchSubjectId,
                    ),
                )
            }
        }

    /**
     * Move a session, preserving its identity [BR1.7].
     *
     * **A reschedule, not a delete and a create.** The session keeps
     * its id, so attendance already recorded against it stays attached
     * — which is the whole reason this is its own endpoint rather than
     * two calls.
     *
     * @param sessionId The session to move
     * @param date The new date
     * @param startTime The new start time
     * @return Nothing on success, or why the server refused
     */
    override suspend fun reschedule(
        sessionId: String,
        date: String,
        startTime: String,
    ): AuthResult<Unit> =
        callDiscardingBody {
            client.put("/v1/sessions/$sessionId/schedule") {
                setBody(RescheduleBody(date = date, startTime = startTime))
            }
        }

    /**
     * Cancel a session [BR1.6].
     *
     * Takes no body: the server needs only which session, and the
     * cancellation is the act of posting to the sub-resource.
     *
     * @param sessionId The session to cancel
     * @return Nothing on success, or why the server refused
     */
    override suspend fun cancel(sessionId: String): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/sessions/$sessionId/cancellation") }
}
