package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.batchdetail.BatchDetailRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import kotlinx.serialization.Serializable

@Serializable
private data class NoticeBody(val body: String)

/**
 * The batch screen's reads and writes, over HTTP (T7).
 *
 * @property client The authenticated HTTP client
 */
class HttpBatchDetailRepository(
    private val client: HttpClient,
) : BatchDetailRepository {

    override suspend fun batch(batchId: String): AuthResult<BatchDto> {
        val batches: AuthResult<List<BatchDto>> = call { client.get("/v1/batches") }
        return when (batches) {
            is AuthResult.Ok ->
                batches.value.firstOrNull { it.id == batchId }?.let { AuthResult.Ok(it) }
                    ?: AuthResult.TransportFailure
            is AuthResult.Refused -> batches
            AuthResult.TransportFailure -> AuthResult.TransportFailure
        }
    }

    override suspend fun fees(batchId: String): AuthResult<List<RosterFeeRowDto>> =
        call { client.get("/v1/batches/$batchId/fees") }

    override suspend fun notices(batchId: String): AuthResult<List<AnnouncementDto>> =
        call { client.get("/v1/batches/$batchId/announcements") }

    override suspend fun postNotice(batchId: String, body: String): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/batches/$batchId/announcements") { setBody(NoticeBody(body)) } }

    override suspend fun editNotice(noticeId: String, body: String): AuthResult<Unit> =
        callDiscardingBody { client.put("/v1/announcements/$noticeId") { setBody(NoticeBody(body)) } }

    override suspend fun removeNotice(noticeId: String): AuthResult<Unit> =
        callDiscardingBody { client.delete("/v1/announcements/$noticeId") }
}
