package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.myexams.ExaminerRepository
import com.shikkhokplus.app.feature.myexams.MyExamsRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * The exams a centre asked me to mark, over HTTP. One moved to another
 * examiner is refused with `EXAM_REASSIGNED` and nothing is saved.
 *
 * @property client The authenticated HTTP client
 */
class HttpMyExamsRepository(
    private val client: HttpClient,
) : MyExamsRepository {

    override suspend fun exams(): AuthResult<List<MyExamDto>> = call { client.get("/v1/me/exams") }

    override suspend fun results(examId: String): AuthResult<ExaminerResultsDto> =
        call { client.get("/v1/me/exams/$examId/results") }

    override suspend fun mark(examId: String, body: MarkWriteBody): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/me/exams/$examId/marks") { setBody(body) } }

    override suspend fun publish(examId: String): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/me/exams/$examId/publish") }
}

/**
 * Who marks a centre's exam, over HTTP: manager-only.
 *
 * @property client The authenticated HTTP client
 */
class HttpExaminerRepository(
    private val client: HttpClient,
) : ExaminerRepository {

    override suspend fun exam(examId: String): AuthResult<ExamExaminerDto> = call { client.get("/v1/exams/$examId") }

    override suspend fun members(): AuthResult<List<MemberDto>> = HttpCentresRepository(client).members()

    override suspend fun setExaminer(examId: String, memberId: String?): AuthResult<ExamExaminerDto> =
        call {
            // **The field is sent even when null**: null means nobody,
            // and the app's JSON omits nulls, so the body is built here.
            client.put("/v1/exams/$examId/examiner") {
                setBody(buildJsonObject { put("examiner_member_id", memberId?.let(::JsonPrimitive) ?: JsonNull) })
            }
        }
}
