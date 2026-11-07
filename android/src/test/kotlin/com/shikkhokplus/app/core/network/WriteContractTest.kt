package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.expenses.ExpenseCategory
import com.shikkhokplus.app.feature.expenses.ExpenseDraft
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.queue.AttendanceEntry
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.paymentmethods.MethodKind
import com.shikkhokplus.app.feature.paymentmethods.PaymentMethodDraft
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

/** A complete address, for the two writes that carry one. */
private val ADDRESS = PostalAddress("House 1", "Road 2", "Dhaka", "1205")

class WriteContractTest {

    /** One write: the server operation, and how to make the app send it. */
    private class Write(
        val method: String,
        val path: String,
        val send: suspend (HttpClient) -> Any?,
    )

    private val staffBody =
        StaffBodyDto(
            displayName = "Karim",
            email = "karim@example.com",
            staffHouse = "12",
            staffRoad = "Road 5",
            staffCity = "Dhaka",
            staffPostcode = "1205",
            payBasis = "monthly",
            payRate = Money.of("8000.00"),
            joinedOn = "2026-01-01",
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
                HttpSignupRepository(it).signup("01711234567", "student", "Rafi", ADDRESS)
            },
            // Signing up as a coaching centre, with its name.
            Write("post", "/v1/accounts") {
                HttpSignupRepository(it).signup("01711234567", "coaching", "Rahima", ADDRESS, "Udayan Coaching")
            },
            Write("patch", "/v1/me") { HttpProfileRepository(it).save("Rafi", ADDRESS) },
            Write("post", "/v1/exams/{exam_id}/publish") { HttpMarksRepository(it).publish(ID) },
            // Cancelling an unpublished exam [0019], with and without a reason.
            Write("post", "/v1/exams/{exam_id}/cancel") { HttpMarksRepository(it).cancelExam(ID, "Hartal") },
            Write("post", "/v1/exams/{exam_id}/cancel") { HttpMarksRepository(it).cancelExam(ID, null) },
            // A teacher records money received by hand, short and carried.
            Write("post", "/v1/enrollments/{enrollment_id}/payments") {
                HttpFeesRepository(it).recordPayment(
                    ID,
                    RecordPaymentBodyDto(
                        amount = Money.of("1000.00"),
                        channel = "bKash",
                        reference = "9KD7Q2XL1M",
                        note = "Rest next month",
                        shortfallDisposition = "carried",
                        clientMutationId = ID,
                    ),
                )
            },
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
                HttpMarksRepository(it).createExam(ID, "Mid-term", "2026-11-04", 100, ID, listOf("Motion"))
            },
            Write("post", "/v1/exams/{exam_id}/marks") {
                HttpMarksRepository(it).writeMark(ID, ID, "marked", 70.5)
            },
            Write("post", "/v1/payments/{submission_id}/approval") {
                HttpVerificationRepository(it).approve(
                    ID,
                    PaymentApprovalBodyDto(Money.of("800.00"), "carried", carriedByEnrollmentId = ID),
                )
            },
            // Applying a payment to an exam or other fee, and to the monthly fee.
            Write("post", "/v1/payments/{submission_id}/approval") {
                HttpVerificationRepository(it).approve(
                    ID,
                    PaymentApprovalBodyDto(Money.of("500.00"), purpose = "extra", extraFeeId = ID),
                )
            },
            Write("post", "/v1/payments/{submission_id}/approval") {
                HttpVerificationRepository(it).approve(
                    ID,
                    PaymentApprovalBodyDto(Money.of("500.00"), purpose = "monthly"),
                )
            },
            Write("post", "/v1/payments/{submission_id}/rejection") {
                HttpVerificationRepository(it).reject(ID, "Not received", false)
            },
            Write("patch", "/v1/batches/{batch_id}") {
                HttpBatchDetailRepository(it).editBatch(ID, BatchEdit(name = "Physics B", subjects = listOf("Optics")))
            },
            Write("put", "/v1/exams/{exam_id}") {
                HttpMarksRepository(it).editExam(ID, "Mid-term", "2026-11-04", 50, listOf("Motion"))
            },
            Write("post", "/v1/payments") {
                // With its replay key, as the form always sends it, so the
                // server's schema is checked against the real body.
                HttpPayRepository(it).submit(
                    PaymentSubmitDto(
                        listOf(ID),
                        null,
                        true,
                        Money.of("1500.00"),
                        "2026-11-02",
                        clientMutationId = ID,
                    ),
                )
            },
            // A payment for one exam or other fee carries its purpose.
            Write("post", "/v1/payments") {
                HttpPayRepository(it).submit(
                    PaymentSubmitDto(
                        listOf(ID),
                        null,
                        true,
                        Money.of("300.00"),
                        "2026-11-02",
                        clientMutationId = ID,
                        purpose = "extra",
                        extraFeeId = ID,
                    ),
                )
            },
            // Raising a fee with a waiver and an exclusion, and recording
            // cash against one.
            Write("post", "/v1/batches/{batch_id}/extra-fees") {
                HttpExtraFeesRepository(it).raise(
                    ID,
                    ExtraFeeRaiseRequestDto(
                        purpose = "exam",
                        label = "Half-yearly exam",
                        examId = ID,
                        amount = Money.of("500.00"),
                        dueOn = "2026-11-20",
                        seatAmounts = listOf(SeatAmountDto(ID, Money.ZERO)),
                        excludedEnrollmentIds = listOf(ID),
                        clientMutationId = ID,
                    ),
                )
            },
            Write("post", "/v1/enrollments/{enrollment_id}/payments") {
                HttpFeesRepository(it).recordPayment(
                    ID,
                    RecordPaymentBodyDto(
                        amount = Money.of("300.00"),
                        shortfallDisposition = "carried",
                        clientMutationId = ID,
                        purpose = "extra",
                        extraFeeId = ID,
                    ),
                )
            },
            // Opening a centre, inviting and removing a member, and
            // answering a centre's offer.
            Write("post", "/v1/centres") { HttpCentresRepository(it).open("Udayan Coaching", "Rahima") },
            Write("post", "/v1/centre/members") {
                HttpCentresRepository(it).invite("Karim", "01811223344", "teacher")
            },
            Write("post", "/v1/centre/members/{member_id}/revoke") { HttpCentresRepository(it).revoke(ID) },
            Write("post", "/v1/memberships/{member_id}/accept") { HttpCentresRepository(it).accept(ID) },
            Write("post", "/v1/memberships/{member_id}/decline") { HttpCentresRepository(it).decline(ID) },
            // Inviting a teacher, adding other staff, correcting a record
            // and marking someone as left.
            Write("post", "/v1/centre/staff/teachers") {
                HttpStaffRepository(it).inviteTeacher(staffBody.copy(phone = "01811223344"))
            },
            Write("post", "/v1/centre/staff") {
                HttpStaffRepository(it).addOther(staffBody.copy(roleLabel = "Office"))
            },
            Write("patch", "/v1/centre/staff/{staff_id}") { HttpStaffRepository(it).update(ID, staffBody) },
            Write("post", "/v1/centre/staff/{staff_id}/leave") { HttpStaffRepository(it).leave(ID, "2026-11-06") },
            Write("post", "/v1/centre/staff/{staff_id}/leave") { HttpStaffRepository(it).leave(ID, null) },
            // One class's teacher and room, a swap, and the rooms.
            Write("post", "/v1/sessions/{session_id}/assignment") { HttpTimetableRepository(it).assign(ID, ID, ID) },
            Write("post", "/v1/sessions/{session_id}/assignment") {
                HttpTimetableRepository(it).assign(ID, null, null)
            },
            Write("post", "/v1/centre/sessions/swap") { HttpTimetableRepository(it).swap(ID, ID) },
            Write("post", "/v1/centre/rooms") { HttpTimetableRepository(it).addRoom("Room A") },
            Write("patch", "/v1/centre/rooms/{room_id}") { HttpTimetableRepository(it).archiveRoom(ID, true) },
            // A centre teacher's attendance and topic for one assigned class.
            Write("post", "/v1/me/classes/{session_id}/attendance") {
                HttpMyClassesRepository(it).submitAttendance(
                    ID,
                    ClassAttendanceBodyDto(1, ID, listOf(ClassSeatMarkDto(ID, true))),
                )
            },
            // A centre's payroll: draw, adjust, approve and pay.
            Write("post", "/v1/centre/payroll/{period}/lines") { HttpPayrollRepository(it).draw("2026-10") },
            Write("post", "/v1/centre/payroll/lines/{line_id}/adjustments") {
                HttpPayrollRepository(it).adjust(ID, AdjustmentBodyDto("addition", "Bonus", Money.of("500.00")))
            },
            Write("delete", "/v1/centre/payroll/lines/{line_id}/adjustments/{adjustment_id}") {
                HttpPayrollRepository(it).removeAdjustment(ID, ID)
            },
            Write("post", "/v1/centre/payroll/lines/{line_id}/approve") { HttpPayrollRepository(it).approve(ID) },
            Write("post", "/v1/centre/payroll/lines/{line_id}/payments") {
                HttpPayrollRepository(it).pay(ID, SalaryPaymentBodyDto(Money.of("500.00"), ID))
            },
            Write("post", "/v1/centre/payroll/lines/{line_id}/payments") {
                HttpPayrollRepository(it).pay(ID, SalaryPaymentBodyDto(Money.of("500.00"), ID, "2026-11-01", "Cash"))
            },
            // An examiner's marks and publish, and naming an exam's examiner.
            Write("post", "/v1/me/exams/{exam_id}/marks") {
                HttpMyExamsRepository(it).mark(ID, MarkWriteBody(ID, "marked", 18.0))
            },
            Write("post", "/v1/me/exams/{exam_id}/marks") {
                HttpMyExamsRepository(it).mark(ID, MarkWriteBody(ID, "absent"))
            },
            Write("post", "/v1/me/exams/{exam_id}/publish") { HttpMyExamsRepository(it).publish(ID) },
            Write("put", "/v1/exams/{exam_id}/examiner") { HttpExaminerRepository(it).setExaminer(ID, ID) },
            Write("put", "/v1/exams/{exam_id}/examiner") { HttpExaminerRepository(it).setExaminer(ID, null) },
            Write("put", "/v1/me/classes/{session_id}/topic") {
                HttpMyClassesRepository(it).writeTopic(ID, ClassTopicBodyDto(1, ID, "Vectors", plan = false))
            },
            Write("post", "/v1/payment-methods") {
                HttpPaymentMethodsRepository(it).create(MOBILE_DRAFT)
            },
            Write("patch", "/v1/payment-methods/{method_id}") {
                HttpPaymentMethodsRepository(it).update(ID, MOBILE_DRAFT)
            },
            Write("delete", "/v1/payment-methods/{method_id}") {
                HttpPaymentMethodsRepository(it).retire(ID)
            },
            // A teacher's students, apart from any batch [0018].
            Write("post", "/v1/students") {
                HttpTeacherStudentsRepository(it).create(
                    "Rafiq",
                    "01812345678",
                    "01711223344",
                    listOf(StudentSeatBody(ID, null), StudentSeatBody(ID, "900.00")),
                )
            },
            Write("patch", "/v1/students/{student_id}") {
                HttpTeacherStudentsRepository(it).rename(ID, "Rafiqul", null, null)
            },
            Write("delete", "/v1/students/{student_id}") { HttpTeacherStudentsRepository(it).removeStudent(ID) },
            Write("post", "/v1/students/{student_id}/enrollments") {
                HttpTeacherStudentsRepository(it).enroll(ID, ID)
            },
            Write("post", "/v1/batches/{batch_id}/students") {
                HttpTeacherStudentsRepository(it).addToBatch(ID, listOf(ID))
            },
            Write("post", "/v1/reminders") { HttpAnalyticsRepository(it).remind(listOf(ID)) },
            Write("post", "/v1/me/notifications/read") { HttpInboxRepository(it).markAllRead() },
            Write("post", "/v1/me/notifications/{notification_id}/read") { HttpInboxRepository(it).markRead(ID) },
            Write("put", "/v1/batches/{batch_id}/marksheet-visibility") {
                HttpMarksRepository(it).setMarksheetVisible(ID, visible = true)
            },
            // Recording an expense, with its retry key, and voiding one.
            Write("post", "/v1/expenses") {
                HttpExpensesRepository(it).record(
                    ExpenseDraft(
                        category = ExpenseCategory.PRINTING,
                        what = "Question papers",
                        amount = Money.of("450.00"),
                        spentOn = "2026-11-03",
                        payee = "Nilkhet Press",
                        note = null,
                        clientMutationId = ID,
                    ),
                )
            },
            Write("post", "/v1/expenses/{expense_id}/void") { HttpExpensesRepository(it).void(ID, "Typed twice") },
            Write("post", "/v1/expenses/{expense_id}/void") { HttpExpensesRepository(it).void(ID, null) },
            // The help centre: asking a question, and adding to one.
            Write("post", "/v1/me/help/tickets") {
                HttpHelpRepository(it).ask("Cannot add a student", "The add button does nothing.")
            },
            Write("post", "/v1/me/help/tickets/{ticket_id}/messages") {
                HttpHelpRepository(it).reply(ID, "It works now, thank you.")
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

        val MOBILE_DRAFT =
            PaymentMethodDraft(
                kind = MethodKind.MOBILE,
                provider = "bKash",
                mobileNumber = "01712345678",
            )

        val JSON_HEADERS = headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))
    }
}
