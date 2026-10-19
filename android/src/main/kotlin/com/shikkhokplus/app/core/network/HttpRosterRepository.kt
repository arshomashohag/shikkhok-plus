package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.roster.RosterPayload
import com.shikkhokplus.app.feature.roster.RosterRepository
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
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
)

/** The add-student body. */
@Serializable
private data class EnrollmentCreateBody(
    @SerialName("display_name") val displayName: String,
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
        guardianPhone: String?,
        feeAmount: String?,
    ): AuthResult<Unit> =
        try {
            val response =
                client.post("/v1/batches/$batchId/enrollments") {
                    setBody(
                        EnrollmentCreateBody(
                            displayName = displayName,
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
