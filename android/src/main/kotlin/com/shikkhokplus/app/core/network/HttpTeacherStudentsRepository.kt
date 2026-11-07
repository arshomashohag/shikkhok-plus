package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.students.StudentFilter
import com.shikkhokplus.app.feature.students.StudentsRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * A teacher's students, over HTTP [0018].
 *
 * **Filtering is the server's.** The batch, "not in a batch" and search
 * filters travel as query parameters and the server answers with the
 * matching list; the client never filters a domain list itself.
 *
 * @property client The authenticated HTTP client
 */
class HttpTeacherStudentsRepository(
    private val client: HttpClient,
) : StudentsRepository {

    override suspend fun students(filter: StudentFilter, query: String): AuthResult<List<TeacherStudentDto>> =
        call {
            client.get("/v1/students") {
                when (filter) {
                    StudentFilter.All -> Unit
                    StudentFilter.Unassigned -> parameter("unassigned", true)
                    is StudentFilter.InBatch -> parameter("batch_id", filter.batchId)
                    is StudentFilter.NotInBatch -> parameter("exclude_batch_id", filter.batchId)
                }
                if (query.isNotBlank()) parameter("q", query.trim())
            }
        }

    override suspend fun student(studentId: String): AuthResult<TeacherStudentDto> =
        call { client.get("/v1/students/$studentId") }

    override suspend fun batches(): AuthResult<List<BatchDto>> = call { client.get("/v1/batches") }

    override suspend fun create(
        displayName: String,
        studentPhone: String?,
        guardianPhone: String?,
        seats: List<StudentSeatBody>,
        clientMutationId: String?,
    ): AuthResult<TeacherStudentDto> =
        call {
            client.post("/v1/students") {
                setBody(
                    StudentCreateBody(
                        displayName = displayName,
                        studentPhone = studentPhone?.ifBlank { null },
                        guardianPhone = guardianPhone?.ifBlank { null },
                        enrollments = seats,
                        clientMutationId = clientMutationId,
                    ),
                )
            }
        }

    override suspend fun rename(
        studentId: String,
        displayName: String?,
        studentPhone: String?,
        guardianPhone: String?,
    ): AuthResult<TeacherStudentDto> =
        call {
            client.patch("/v1/students/$studentId") {
                setBody(
                    StudentUpdateBody(
                        displayName = displayName?.ifBlank { null },
                        studentPhone = studentPhone?.ifBlank { null },
                        guardianPhone = guardianPhone?.ifBlank { null },
                    ),
                )
            }
        }

    override suspend fun enroll(studentId: String, batchId: String): AuthResult<TeacherStudentDto> =
        call {
            client.post("/v1/students/$studentId/enrollments") {
                setBody(StudentEnrollBody(batchId = batchId))
            }
        }

    override suspend fun addToBatch(batchId: String, studentIds: List<String>): AuthResult<Unit> =
        callDiscardingBody {
            client.post("/v1/batches/$batchId/students") { setBody(AddStudentsBody(studentIds)) }
        }

    override suspend fun leaveBatch(enrollmentId: String, onDate: String): AuthResult<Unit> =
        callDiscardingBody {
            client.patch("/v1/enrollments/$enrollmentId/inactive-from") {
                setBody(LeaveBatchBody(inactiveFrom = onDate))
            }
        }

    override suspend fun removeSeat(enrollmentId: String): AuthResult<Unit> =
        callDiscardingBody { client.delete("/v1/enrollments/$enrollmentId") }

    override suspend fun removeStudent(studentId: String): AuthResult<Unit> =
        callDiscardingBody { client.delete("/v1/students/$studentId") }
}
