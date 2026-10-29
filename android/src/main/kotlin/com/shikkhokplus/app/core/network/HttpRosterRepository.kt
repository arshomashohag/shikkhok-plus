package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.roster.RosterPayload
import com.shikkhokplus.app.feature.roster.RosterRepository
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.isSuccess
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The create-batch body.
 *
 * `defaultFee` is a canonical money STRING, never a number [TC-7].
 * Omitted entirely when null, because the server distinguishes "not
 * supplied" from "explicitly null".
 */
@Serializable
private data class BatchCreateBody(
    val name: String,
    val subjects: List<String>,
    @SerialName("default_fee") val defaultFee: String? = null,
    @SerialName("fee_due_day") val feeDueDay: Int? = null,
    val schedule: List<ScheduleSlotDto> = emptyList(),
)

/** The replace-schedule body. */
@Serializable
private data class ScheduleBody(
    val slots: List<ScheduleSlotDto>,
)

/**
 * The mark-inactive body.
 *
 * Nullable on purpose: null reactivates the seat on the server.
 */
@Serializable
private data class InactiveFromBody(
    @SerialName("inactive_from") val inactiveFrom: String?,
)

/**
 * The add-student body.
 *
 * `student_phone` is what links the seat to the student's own account.
 * It was never sent, so no student a teacher added could reach their
 * seat; the server canonicalises it, so it is sent as typed.
 */
@Serializable
private data class EnrollmentCreateBody(
    @SerialName("display_name") val displayName: String,
    @SerialName("student_phone") val studentPhone: String? = null,
    @SerialName("guardian_phone") val guardianPhone: String? = null,
    @SerialName("fee_amount") val feeAmount: String? = null,
)

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
                        // The COUNTS are not on the roster response
                        // either: they belong to `BatchResponse`, which
                        // the batch list already carries [BR1.2]. Null
                        // rather than a tally over `rows` -- counting
                        // them here is exactly the client-side
                        // derivation BR1.3 forbids, and it would be
                        // wrong the moment the roster paginates. The
                        // caller that holds the batch summary supplies
                        // them; a caller that does not renders no
                        // count rather than an invented one.
                        acceptedCount = null,
                        seatCount = null,
                    ),
                )
            } else {
                AuthResult.Refused(decodeEnvelope(response))
            }
        } catch (_: Exception) {
            AuthResult.TransportFailure
        }

    override suspend fun addEnrollment(
        batchId: String,
        displayName: String,
        studentPhone: String?,
        guardianPhone: String?,
        feeAmount: String?,
    ): AuthResult<Unit> =
        try {
            val response =
                client.post("/v1/batches/$batchId/enrollments") {
                    setBody(
                        EnrollmentCreateBody(
                            displayName = displayName,
                            studentPhone = studentPhone?.ifBlank { null },
                            guardianPhone = guardianPhone?.ifBlank { null },
                            // A canonical money STRING or nothing. Null
                            // means inherit the batch default; zero is a
                            // waiver, and sending "0.00" for an empty
                            // field would silently waive every fee
                            // [AC2.2.5].
                            feeAmount = feeAmount?.ifBlank { null },
                        ),
                    )
                }
            if (response.status.isSuccess()) {
                AuthResult.Ok(Unit)
            } else {
                AuthResult.Refused(decodeEnvelope(response))
            }
        } catch (_: Exception) {
            AuthResult.TransportFailure
        }

    override suspend fun markInactive(
        enrollmentId: String,
        fromDate: String,
    ): AuthResult<Unit> =
        callDiscardingBody {
            client.patch("/v1/enrollments/$enrollmentId/inactive-from") {
                setBody(InactiveFromBody(inactiveFrom = fromDate))
            }
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

/**
 * The real batches repository, over HTTP.
 *
 * @property client The configured HTTP client
 */
class HttpBatchesRepository(
    private val client: HttpClient,
) : com.shikkhokplus.app.feature.batches.BatchesRepository {

    override suspend fun createBatch(
        name: String,
        subjects: List<String>,
        defaultFee: String?,
        feeDueDay: Int?,
        schedule: List<ScheduleSlotDto>,
    ): AuthResult<BatchDto> =
        try {
            val response =
                client.post("/v1/batches") {
                    setBody(
                        BatchCreateBody(
                            name = name,
                            subjects = subjects,
                            defaultFee = defaultFee?.ifBlank { null },
                            feeDueDay = feeDueDay,
                            schedule = schedule,
                        ),
                    )
                }
            if (response.status.isSuccess()) {
                AuthResult.Ok(response.body())
            } else {
                AuthResult.Refused(decodeEnvelope(response))
            }
        } catch (_: Exception) {
            AuthResult.TransportFailure
        }

    override suspend fun batches(): AuthResult<List<BatchDto>> =
        try {
            val response: HttpResponse = client.get("/v1/batches")
            if (response.status.isSuccess()) {
                AuthResult.Ok(response.body())
            } else {
                AuthResult.Refused(decodeEnvelope(response))
            }
        } catch (_: Exception) {
            AuthResult.TransportFailure
        }
}

/**
 * A batch's weekly schedule, over HTTP.
 *
 * Saving REPLACES the schedule and the server generates the batch's
 * sessions at once, so attendance can be taken without waiting for the
 * nightly job.
 *
 * @property client The authenticated HTTP client
 */
class HttpScheduleRepository(
    private val client: HttpClient,
) : com.shikkhokplus.app.feature.schedule.ScheduleRepository {

    override suspend fun schedule(batchId: String): AuthResult<List<ScheduleSlotDto>> =
        call { client.get("/v1/batches/$batchId/schedule") }

    override suspend fun save(
        batchId: String,
        slots: List<ScheduleSlotDto>,
    ): AuthResult<List<ScheduleSlotDto>> =
        call {
            client.put("/v1/batches/$batchId/schedule") { setBody(ScheduleBody(slots)) }
        }
}
