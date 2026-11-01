package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.student.FamilyReader
import com.shikkhokplus.app.feature.student.StudentRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter

/**
 * The family's reads of one batch, over HTTP.
 *
 * **Every path names the reader's own seat or none.** The server
 * resolves the seats from the signed-in account's accepted enrollments
 * or guardianships; an id in a path is checked against that, never
 * trusted [BR7.2].
 *
 * @property client The authenticated HTTP client
 * @property reader Whether a student or a guardian is reading
 */
class HttpStudentRepository(
    private val client: HttpClient,
    private val reader: FamilyReader = FamilyReader.SELF,
) : StudentRepository {

    override suspend fun batches(): AuthResult<List<StudentBatchDto>> =
        when (reader) {
            FamilyReader.SELF -> call { client.get("/v1/me/enrollments") }
            FamilyReader.GUARDIAN -> guardianSeats()
        }

    override suspend fun phone(): AuthResult<MeDto> = call { client.get("/v1/me") }

    override suspend fun batchView(enrollmentId: String): AuthResult<FamilyBatchViewDto> =
        when (reader) {
            FamilyReader.SELF -> call { client.get("/v1/me/batches/$enrollmentId/teaching") }
            FamilyReader.GUARDIAN -> call { client.get("/v1/children/$enrollmentId/teaching") }
        }

    override suspend fun progress(enrollmentId: String): AuthResult<List<ProgressEntryDto>> =
        when (reader) {
            FamilyReader.SELF -> call { client.get("/v1/me/enrollments/$enrollmentId/progress") }
            FamilyReader.GUARDIAN -> call { client.get("/v1/children/$enrollmentId/progress") }
        }

    override suspend fun exam(enrollmentId: String, examId: String): AuthResult<FamilyExamDto> =
        when (reader) {
            FamilyReader.SELF -> call { client.get("/v1/me/enrollments/$enrollmentId/exams/$examId") }
            FamilyReader.GUARDIAN -> call { client.get("/v1/children/$enrollmentId/exams/$examId") }
        }

    override suspend fun month(enrollmentId: String, year: Int, month: Int): AuthResult<MonthViewDto> {
        val path =
            when (reader) {
                FamilyReader.SELF -> "/v1/me/enrollments/$enrollmentId/calendar"
                FamilyReader.GUARDIAN -> "/v1/children/$enrollmentId/calendar"
            }
        return call {
            client.get(path) {
                parameter("year", year)
                parameter("month", month)
            }
        }
    }

    /**
     * A guardian's seats, flattened from the home read so the batch
     * screen finds its seat the way a student's does.
     *
     * @return One row per child seat, each carrying the child's name
     */
    private suspend fun guardianSeats(): AuthResult<List<StudentBatchDto>> =
        when (val home = call<GuardianHomeDto> { client.get("/v1/guardian/home") }) {
            is AuthResult.Ok ->
                AuthResult.Ok(
                    home.value.children.flatMap { child ->
                        child.batches.map { batch ->
                            StudentBatchDto(
                                enrollmentId = batch.enrollmentId,
                                batchName = batch.batchName,
                                teacherDisplayName = batch.teacherDisplayName,
                                nextSession = batch.nextSession,
                                childName = child.displayName,
                            )
                        }
                    },
                )
            is AuthResult.Refused -> home
            AuthResult.TransportFailure -> AuthResult.TransportFailure
        }
}
