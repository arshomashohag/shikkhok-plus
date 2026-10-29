package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.student.StudentRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get

/**
 * The student's own reads, over HTTP.
 *
 * **Every path names the student's own seat or none.** The server
 * resolves the seats from the signed-in account's accepted enrollments;
 * an id in a path is checked against that, never trusted [BR7.2].
 *
 * @property client The authenticated HTTP client
 */
class HttpStudentRepository(
    private val client: HttpClient,
) : StudentRepository {

    override suspend fun batches(): AuthResult<List<StudentBatchDto>> =
        call { client.get("/v1/me/enrollments") }

    override suspend fun phone(): AuthResult<MeDto> = call { client.get("/v1/me") }

    override suspend fun batchView(enrollmentId: String): AuthResult<FamilyBatchViewDto> =
        call { client.get("/v1/me/batches/$enrollmentId/teaching") }

    override suspend fun progress(enrollmentId: String): AuthResult<List<ProgressEntryDto>> =
        call { client.get("/v1/me/enrollments/$enrollmentId/progress") }
}
