package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.queue.AttendanceEntry
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Every write the app makes is one the server would accept, and the
 * app can read what comes back.
 *
 * **The other half of [ContractConformanceTest].** That gate checks
 * what the app reads; this one drives each repository write against a
 * mock server, then checks three things against the committed
 * `openapi.json`: the method and path exist, the body the app sent
 * passes the server's request schema -- which forbids unknown fields,
 * so a misnamed key is a 422 exactly like a missing one -- and the
 * repository reads the server's documented success response as a
 * success rather than as a lost connection.
 *
 * The last test scans the repositories for every write call and fails
 * if one is not listed here.
 */
class WriteContractTest {

    /** One write: the server operation, and how to make the app send it. */
    private class Write(
        val method: String,
        val path: String,
        val send: suspend (HttpClient) -> Any?,
    )

    private val slots = listOf(ScheduleSlotDto(0, "16:00", "17:00"))

    private val writes: List<Write> =
        listOf(
            Write("post", "/v1/auth/otp") {
                HttpAuthRepository(it, TokenStore.InMemory()).issue("01711234567")
            },
            Write("post", "/v1/auth/verify") {
                HttpAuthRepository(it, TokenStore.InMemory()).verify("01711234567", "123456")
            },
            Write("post", "/v1/auth/refresh") {
                val tokens = TokenStore.InMemory().apply { save("access", "refresh") }
                HttpAuthRepository(it, tokens).refresh()
            },
            Write("post", "/v1/accounts") {
                HttpSignupRepository(it).signup("01711234567", "student", "Rafi", null)
            },
            Write("patch", "/v1/me") { HttpProfileRepository(it).save("Rafi", "Mirpur") },
            Write("delete", "/v1/me") { HttpProfileRepository(it).deleteAccount() },
            Write("post", "/v1/invitations/{enrollment_id}/accept") {
                HttpInvitationsRepository(it).accept(ID)
            },
            Write("post", "/v1/invitations/{enrollment_id}/decline") {
                HttpInvitationsRepository(it).decline(ID)
            },
            Write("post", "/v1/batches") {
                HttpBatchesRepository(it).createBatch("Physics", listOf("Physics"), "1200.00", 5, slots)
            },
            Write("put", "/v1/batches/{batch_id}/schedule") {
                HttpScheduleRepository(it).save(ID, slots)
            },
            Write("post", "/v1/batches/{batch_id}/enrollments") {
                HttpRosterRepository(it).addEnrollment(ID, "Rafi", "01711234567", "01811234567", "1200.00")
            },
            Write("patch", "/v1/enrollments/{enrollment_id}/inactive-from") {
                HttpRosterRepository(it).markInactive(ID, "2026-11-04")
            },
            Write("delete", "/v1/enrollments/{enrollment_id}") {
                HttpRosterRepository(it).removeEnrollment(ID)
            },
            Write("post", "/v1/batches/{batch_id}/sessions") {
                HttpSessionsRepository(it).createAdHoc(ID, "2026-11-04", "16:00", ID)
            },
            Write("put", "/v1/sessions/{session_id}/schedule") {
                HttpSessionsRepository(it).reschedule(ID, "2026-11-05", "17:00")
            },
            Write("post", "/v1/sessions/{session_id}/cancellation") {
                HttpSessionsRepository(it).cancel(ID)
            },
            Write("post", "/v1/sessions/{session_id}/attendance") {
                HttpAttendanceRepository(it).submit(
                    QueuedWrite.attendance(ID, 3, listOf(AttendanceEntry(ID, present = true))),
                )
            },
            Write("put", "/v1/sessions/{session_id}/topic") {
                HttpAttendanceRepository(it).submit(QueuedWrite.topic(ID, 2, "Thermodynamics"))
            },
            Write("post", "/v1/batches/{batch_id}/announcements") {
                HttpBatchDetailRepository(it).postNotice(ID, "Bring a calculator")
            },
            Write("put", "/v1/announcements/{announcement_id}") {
                HttpBatchDetailRepository(it).editNotice(ID, "Bring two calculators")
            },
            Write("delete", "/v1/announcements/{announcement_id}") {
                HttpBatchDetailRepository(it).removeNotice(ID)
            },
            Write("put", "/v1/sessions/{session_id}/subject") {
                HttpRecordRepository(it).setSubject(ID, ID)
            },
            Write("post", "/v1/batches/{batch_id}/exams") {
                HttpMarksRepository(it).createExam(ID, "Mid-term", "2026-11-04", 100, ID)
            },
            Write("post", "/v1/exams/{exam_id}/marks") {
                HttpMarksRepository(it).writeMark(ID, ID, "marked", 70)
            },
            Write("post", "/v1/claims/{claim_id}/shortfall") {
                HttpVerificationRepository(it).preview(ID, Money.of("800.00"))
            },
            Write("post", "/v1/claims/{claim_id}/verification") {
                HttpVerificationRepository(it).approve(ID, Money.of("800.00"), "carried")
            },
            Write("post", "/v1/claims/{claim_id}/rejection") {
                HttpVerificationRepository(it).reject(ID)
            },
            Write("patch", "/v1/batches/{batch_id}") {
                HttpBatchDetailRepository(it).editBatch(ID, BatchEdit(name = "Physics B", subjects = listOf("Optics")))
            },
            Write("put", "/v1/exams/{exam_id}") {
                HttpMarksRepository(it).editExam(ID, "Mid-term", "2026-11-04", 50)
            },
            Write("post", "/v1/enrollments/{enrollment_id}/claims") {
                HttpPayRepository(it).submit(ID, ClaimSubmitDto(Money.of("1500.00"), "bKash", "DJ62K0LQ7V"))
            },
            Write("post", "/v1/reminders") { HttpAnalyticsRepository(it).remind(listOf(ID)) },
            Write("post", "/v1/me/notifications/read") { HttpInboxRepository(it).markRead() },
            Write("put", "/v1/batches/{batch_id}/marksheet-visibility") {
                HttpMarksRepository(it).setMarksheetVisible(ID, visible = true)
            },
        )

    @Test
    fun `every write is accepted by the server's schema and read back`() = runTest {
        val failures = writes.flatMap { write -> check(write) }

        assertEquals(emptyList(), failures, failures.joinToString("\n"))
    }

    @Test
    fun `every write the app makes is covered here`() {
        // **The half that makes this a gate rather than a list.**
        val sources =
            generateSequence(File("").absoluteFile) { it.parentFile }
                .map { File(it, "android/src/main/kotlin") }
                .firstOrNull { it.exists() }
                ?: File("src/main/kotlin")
        val called =
            sources.walkTopDown()
                .filter { it.name.startsWith("Http") && it.name.endsWith("Repository.kt") }
                .flatMap { file ->
                    Regex("""client\.(post|put|patch|delete)\(\s*"([^"]+)"""").findAll(file.readText()).map {
                        it.groupValues[1] + " " + it.groupValues[2].replace(Regex("""\$\{?[\w.]+}?"""), "{}")
                    }
                }.toSet()
        val covered = writes.map { "${it.method} ${it.path.replace(Regex("""\{[^}]+}"""), "{}")}" }.toSet()

        assertTrue(called.isNotEmpty(), "the source scan found no calls at all")
        assertEquals(emptySet(), called - covered, "writes with no contract check")
    }

    /**
     * Drive one write against a mock server and check it.
     *
     * @param write The write
     * @return One message per problem
     */
    private suspend fun check(write: Write): List<String> {
        val label = "${write.method.uppercase()} ${write.path}"
        val operation =
            OpenApi.operation(write.method, write.path)
                ?: return listOf("$label: the server has no such operation")
        val (status, responseSchema) = OpenApi.success(operation)
        val reply = responseSchema?.let { OpenApi.example(it) }

        var sent: Pair<String, JsonElement>? = null
        val engine =
            MockEngine { request ->
                val text = (request.body as? TextContent)?.text
                sent = "${request.method.value.lowercase()} ${request.url.encodedPath}" to
                    (text?.let(Json::parseToJsonElement) ?: JsonNull)
                respond(reply?.toString() ?: "", HttpStatusCode.fromValue(status), JSON_HEADERS)
            }
        val result = write.send(ApiClient.build("https://staging.example", engine, TokenStore.InMemory()))

        val (route, body) = sent ?: return listOf("$label: nothing was sent")
        val pattern = Regex("${write.method} " + write.path.replace(Regex("""\{[^}]+}"""), "[^/]+"))
        val requestSchema = OpenApi.requestSchema(operation)
        return buildList {
            if (!pattern.matches(route)) add("$label: the app sent $route")
            if (requestSchema != null) {
                addAll(OpenApi.violations(body, requestSchema).map { "$label: $it" })
            } else if (body != JsonNull) {
                add("$label: a body the server does not read")
            }
            if (result !is AuthResult.Ok<*> && result !is SendOutcome.Applied) {
                add("$label: the documented $status reply read as $result")
            }
        }
    }

    private companion object {
        /** A uuid, which every path parameter and id field accepts. */
        const val ID = "00000000-0000-0000-0000-000000000001"

        val JSON_HEADERS = headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))
    }
}
