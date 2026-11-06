package com.shikkhokplus.app.core.network

import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonObject
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Every response the app reads decodes from what the SERVER says it sends.
 *
 * **Why this exists.** The app's DTOs were written against the design
 * documents and tested against hand-written JSON in the app's own assumed
 * shape, while the server was tested against itself. Nothing compared
 * the two, and an audit found nine reads that did not match: attendance,
 * marksheets and guardian progress could never load, because the app
 * REQUIRED fields the server never sent, and the decode failure read on
 * screen as a lost connection.
 *
 * This builds an example of each response from the committed
 * `openapi.json` -- the contract the server's schema-diff gate keeps
 * current -- and decodes it with the app's real [ApiClient.json]. A field
 * the app requires and the server does not send fails here. So does a
 * list where the server sends an object.
 *
 * **It cannot be skipped by forgetting.** The last test scans the
 * repositories for every `client.get` path and fails if one is not in
 * [CONTRACTS].
 */
class ContractConformanceTest {

    /** One read: the server path, and how the app decodes its 200 body. */
    private class Contract(val path: String, val serializer: KSerializer<*>)

    /**
     * Every GET the app makes, by the server's path template.
     *
     * Where a repository decodes into an intermediate DTO and maps it,
     * the INTERMEDIATE is what is listed: it is the thing that meets the
     * wire.
     */
    private val contracts: List<Contract> =
        listOf(
            Contract("/v1/me", MeDto.serializer()),
            Contract("/v1/me/fees", FeeHistoryDto.serializer()),
            Contract("/v1/children/{enrollment_id}/fees", FeeHistoryDto.serializer()),
            Contract("/v1/enrollments/{enrollment_id}/fees", FeeHistoryDto.serializer()),
            // A seat's exam and other fees, read by every lens.
            Contract("/v1/enrollments/{enrollment_id}/extra-fees", SeatExtraFeesDto.serializer()),
            // A batch's exam and other fees, for its teacher.
            Contract("/v1/batches/{batch_id}/extra-fees", BatchExtraFeesDto.serializer()),
            Contract("/v1/extra-fees/{extra_fee_id}", ExtraFeeDetailDto.serializer()),
            // A centre's members, for its managers, and centres' offers.
            Contract("/v1/centre/members", ListSerializer(MemberDto.serializer())),
            Contract("/v1/memberships", ListSerializer(MembershipDto.serializer())),
            // The centre's Teachers & staff console.
            Contract("/v1/centre/staff", ListSerializer(StaffDto.serializer())),
            // The centre's timetable and rooms.
            Contract("/v1/centre/timetable", ListSerializer(TimetableClassDto.serializer())),
            Contract("/v1/centre/rooms", ListSerializer(RoomDto.serializer())),
            // A centre teacher's own classes, and one class's roster.
            Contract("/v1/me/classes", ListSerializer(MyClassDto.serializer())),
            Contract("/v1/me/classes/{session_id}/attendance", ClassRosterDto.serializer()),
            // An examiner's exams and one exam's results, and who marks an exam.
            Contract("/v1/me/exams", ListSerializer(MyExamDto.serializer())),
            Contract("/v1/me/exams/{exam_id}/results", ExaminerResultsDto.serializer()),
            Contract("/v1/exams/{exam_id}", ExamExaminerDto.serializer()),
            Contract("/v1/batches", ListSerializer(BatchDto.serializer())),
            Contract("/v1/batches/{batch_id}/schedule", ListSerializer(ScheduleSlotDto.serializer())),
            Contract("/v1/batches/{batch_id}/roster", ListSerializer(RosterRowDto.serializer())),
            // A teacher's students, apart from any batch [0018].
            Contract("/v1/students", ListSerializer(TeacherStudentDto.serializer())),
            Contract("/v1/students/{student_id}", TeacherStudentDto.serializer()),
            Contract("/v1/invitations", ListSerializer(InvitationDto.serializer())),
            Contract("/v1/invitations/{enrollment_id}", InvitationDto.serializer()),
            Contract("/v1/accounts/already-added", AlreadyAddedDto.serializer()),
            Contract("/v1/me/today", TodayDto.serializer()),
            Contract("/v1/me/dues", DuesResponseDto.serializer()),
            Contract("/v1/payment-methods", ListSerializer(PaymentMethodDto.serializer())),
            Contract("/v1/me/notifications", InboxDto.serializer()),
            Contract("/v1/me/notifications/{notification_id}", NotificationDetailDto.serializer()),
            Contract("/v1/me/deletion-summary", DeletionSummaryDto.serializer()),
            Contract("/v1/me/payables", PayablesDto.serializer()),
            Contract("/v1/enrollments/{enrollment_id}/dashboard", DashboardDto.serializer()),
            Contract("/v1/me/enrollments/{enrollment_id}/dashboard", DashboardDto.serializer()),
            Contract("/v1/children/{enrollment_id}/dashboard", DashboardDto.serializer()),
            Contract("/v1/guardian/home", GuardianHomeDto.serializer()),
            Contract("/v1/children/{enrollment_id}/payables", PayablesDto.serializer()),
            Contract("/v1/children/{enrollment_id}/payments", PaymentsDto.serializer()),
            Contract("/v1/children/{enrollment_id}/payment-methods", FamilyPaymentMethodsDto.serializer()),
            Contract("/v1/me/enrollments/{enrollment_id}/payment-methods", FamilyPaymentMethodsDto.serializer()),
            Contract("/v1/payments/owed", OwedTogetherDto.serializer()),
            Contract(
                "/v1/exams/{exam_id}/marks/{enrollment_id}/history",
                ListSerializer(CorrectionDto.serializer()),
            ),
            Contract("/v1/guardian/children", ListSerializer(GuardianChildDto.serializer())),
            Contract("/v1/batches/{batch_id}/sessions", ListSerializer(SessionDto.serializer())),
            Contract("/v1/sessions/{session_id}", SessionDto.serializer()),
            Contract("/v1/sessions/{session_id}/attendance", SessionRosterDto.serializer()),
            Contract("/v1/batches/{batch_id}/exams", ListSerializer(ExamDto.serializer())),
            Contract("/v1/exams/{exam_id}/results", ExamResultsResponseDto.serializer()),
            Contract(
                "/v1/me/enrollments/{enrollment_id}/exams/{exam_id}/marksheet",
                MarksheetDto.serializer(),
            ),
            Contract(
                "/v1/children/{enrollment_id}/exams/{exam_id}/marksheet",
                MarksheetDto.serializer(),
            ),
            Contract("/v1/children/{enrollment_id}/progress", ListSerializer(ProgressEntryDto.serializer())),
            Contract(
                "/v1/me/enrollments/{enrollment_id}/progress",
                ListSerializer(ProgressEntryDto.serializer()),
            ),
            Contract("/v1/me/enrollments", ListSerializer(StudentBatchDto.serializer())),
            Contract("/v1/claims/queue", VerificationQueueDto.serializer()),
            Contract("/v1/payments/{submission_id}", PaymentReviewDto.serializer()),
            Contract("/v1/batches/{batch_id}/fees", BatchFeesDto.serializer()),
            Contract("/v1/analytics/collections", CollectionsDto.serializer()),
            Contract("/v1/batches/{batch_id}/announcements", ListSerializer(AnnouncementDto.serializer())),
            Contract("/v1/me/batches/{enrollment_id}/teaching", FamilyBatchViewDto.serializer()),
            Contract("/v1/children/{enrollment_id}/teaching", FamilyBatchViewDto.serializer()),
            Contract("/v1/batches/{batch_id}/calendar", MonthViewDto.serializer()),
            Contract("/v1/me/enrollments/{enrollment_id}/exams/{exam_id}", FamilyExamDto.serializer()),
            Contract("/v1/children/{enrollment_id}/exams/{exam_id}", FamilyExamDto.serializer()),
            // The owner's spending and the month's money in and out.
            Contract("/v1/expenses", ExpenseMonthDto.serializer()),
            Contract("/v1/money/summary", MoneySummaryDto.serializer()),
        )

    @Test
    fun `every read decodes every shape the server documents`() {
        val failures =
            contracts.flatMap { contract ->
                OpenApi.examples(schemaOf(contract.path)).mapNotNull { (label, body) ->
                    runCatching { ApiClient.json.decodeFromJsonElement(contract.serializer, body) }
                        .exceptionOrNull()
                        ?.let { "${contract.path} [$label]: ${it.message?.lineSequence()?.first()}" }
                }
            }

        assertEquals(emptyList(), failures, failures.joinToString("\n"))
    }

    @Test
    fun `no read expects a field the server never sends`() {
        // **The half decoding cannot see.** A field with a default
        // decodes silently when the server omits it, so the screen
        // shows the default forever and every decode test passes.
        val failures =
            contracts.flatMap { contract ->
                OpenApi.unknownFields(
                    contract.serializer.descriptor,
                    schemaOf(contract.path),
                    contract.path,
                )
            }

        assertEquals(emptyList(), failures, failures.joinToString("\n"))
    }

    @Test
    fun `every GET the app makes is covered here`() {
        // **The half that makes this a gate rather than a list.** A new
        // repository call with no entry above fails, rather than meeting
        // the wire unchecked.
        val sources =
            generateSequence(File("").absoluteFile) { it.parentFile }
                .map { File(it, "android/src/main/kotlin") }
                .firstOrNull { it.exists() }
                ?: File("src/main/kotlin")
        val called =
            sources.walkTopDown()
                .filter { it.name.startsWith("Http") && it.name.endsWith("Repository.kt") }
                .flatMap { file ->
                    Regex("""client\.get\(\s*"([^"]+)"""").findAll(file.readText()).map {
                        it.groupValues[1].replace(Regex("""\$\{?[\w.]+}?"""), "{}")
                    }
                }.toSet()
        val covered = contracts.map { it.path.replace(Regex("""\{[^}]+}"""), "{}") }.toSet()

        assertTrue(called.isNotEmpty(), "the source scan found no calls at all")
        assertEquals(emptySet(), called - covered, "reads with no contract check")
    }

    /**
     * The 200 body schema of one GET.
     *
     * @param path The server's path template
     * @return Its schema
     */
    private fun schemaOf(path: String): JsonObject =
        OpenApi.operation("get", path)
            ?.let { OpenApi.success(it).second }
            ?: error("no GET 200 body documented for $path")
}
