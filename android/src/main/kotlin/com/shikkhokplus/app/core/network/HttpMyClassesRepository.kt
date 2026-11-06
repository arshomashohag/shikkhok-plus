package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.myclasses.MyClassesRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody

/**
 * A centre teacher's own classes, over HTTP. Only classes assigned to
 * this account are listed or reached; one moved to another teacher is
 * refused with `CLASS_REASSIGNED` and nothing is saved.
 *
 * @property client The authenticated HTTP client
 */
class HttpMyClassesRepository(
    private val client: HttpClient,
) : MyClassesRepository {

    override suspend fun classes(from: String, to: String): AuthResult<List<MyClassDto>> =
        call {
            client.get("/v1/me/classes") {
                parameter("from", from)
                parameter("to", to)
            }
        }

    override suspend fun roster(sessionId: String): AuthResult<ClassRosterDto> =
        call { client.get("/v1/me/classes/$sessionId/attendance") }

    override suspend fun submitAttendance(
        sessionId: String,
        body: ClassAttendanceBodyDto,
    ): AuthResult<ClassAttendanceResultDto> =
        call { client.post("/v1/me/classes/$sessionId/attendance") { setBody(body) } }

    override suspend fun writeTopic(sessionId: String, body: ClassTopicBodyDto): AuthResult<ClassTopicResultDto> =
        call { client.put("/v1/me/classes/$sessionId/topic") { setBody(body) } }
}
