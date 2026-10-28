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
            Contract("/v1/batches", ListSerializer(BatchDto.serializer())),
            Contract("/v1/batches/{batch_id}/schedule", ListSerializer(ScheduleSlotDto.serializer())),
            Contract("/v1/batches/{batch_id}/roster", ListSerializer(RosterRowDto.serializer())),
            Contract("/v1/invitations", ListSerializer(InvitationDto.serializer())),
            Contract("/v1/invitations/{enrollment_id}", InvitationDto.serializer()),
            Contract("/v1/accounts/already-added", AlreadyAddedDto.serializer()),
            Contract("/v1/me/today", TodayDto.serializer()),
            Contract("/v1/me/dues", DuesResponseDto.serializer()),
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
            Contract("/v1/me/batches/{enrollment_id}/teaching", FamilyBatchViewDto.serializer()),
            Contract("/v1/children/{enrollment_id}/teaching", FamilyBatchViewDto.serializer()),
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
