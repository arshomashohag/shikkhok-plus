package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.record.RecordRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
private data class SubjectBody(
    @SerialName("batch_subject_id") val batchSubjectId: String?,
)

/**
 * Recording a class, over HTTP (T2).
 *
 * Reuses the reads and the queued-write sender the other screens own,
 * so a topic travels the same tested path attendance does.
 *
 * @property client The authenticated HTTP client
 */
class HttpRecordRepository(
    private val client: HttpClient,
) : RecordRepository {

    override suspend fun subjects(batchId: String): AuthResult<List<SubjectOptionDto>> =
        HttpMarksRepository(client).subjectOptions(batchId)

    override suspend fun sessions(batchId: String): AuthResult<List<SessionDto>> =
        HttpSessionsRepository(client).sessions(batchId)

    override suspend fun setSubject(sessionId: String, batchSubjectId: String?): AuthResult<Unit> =
        callDiscardingBody {
            client.put("/v1/sessions/$sessionId/subject") { setBody(SubjectBody(batchSubjectId)) }
        }

    override suspend fun send(item: QueuedWrite): SendOutcome = HttpAttendanceRepository(client).submit(item)
}
