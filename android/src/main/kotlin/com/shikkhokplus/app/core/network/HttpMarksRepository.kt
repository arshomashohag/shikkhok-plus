package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.marks.ExamResultsPayload
import com.shikkhokplus.app.feature.marks.MarksRepository
import com.shikkhokplus.app.feature.marks.MarksheetReader
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody

/**
 * The marks repository, over HTTP.
 *
 * **Two marksheet routes, chosen by who is asking, not by a flag.** A
 * guardian reads a child's marksheet at `/v1/children/{enrollment}/…`
 * and a student reads their own at `/v1/me/enrollments/{enrollment}/…`.
 * The seat is always in the PATH and never in a body or a header, so a
 * guardian naming someone else's child is refused by the route's own
 * lens rather than by a check somebody has to remember to write
 * [BR7.2].
 *
 * **Every write here is interactive** [BR3.11]. None of them carries a
 * version or a mutation id: mark entry does not queue, so there is no
 * conflict to resolve and no replay to deduplicate. Attendance is the
 * endpoint that does, and keeping the difference visible in the two
 * repositories is what stops one shape spreading into the other.
 *
 * @property client The authenticated HTTP client
 */
class HttpMarksRepository(
    private val client: HttpClient,
) : MarksRepository {

    /**
     * List one batch's exams.
     *
     * @param batchId The batch
     * @return The exams, an error envelope, or a transport failure
     */
    override suspend fun exams(batchId: String): AuthResult<List<ExamDto>> =
        call { client.get("/v1/batches/$batchId/exams") }

    /**
     * List one batch's subjects with their keys.
     *
     * **Read from the batch list, filtered here.** No per-batch read
     * exists, and adding one to save a few rows on a teacher's list --
     * a handful of batches -- would be a second route describing a
     * batch that could drift from the first. Filtering by id is not a
     * business rule: it selects the batch the person is already in.
     *
     * A batch absent from the list is answered as no subjects, which
     * the form shows as a failure to load rather than as an empty
     * choice.
     *
     * @param batchId The batch
     * @return Its subjects, or a refusal
     */
    override suspend fun subjectOptions(batchId: String): AuthResult<List<SubjectOptionDto>> {
        val batches: AuthResult<List<BatchDto>> = call { client.get("/v1/batches") }
        return when (batches) {
            is AuthResult.Ok ->
                AuthResult.Ok(
                    batches.value.firstOrNull { it.id == batchId }?.subjectOptions.orEmpty(),
                )
            is AuthResult.Refused -> AuthResult.Refused(batches.envelope)
            AuthResult.TransportFailure -> AuthResult.TransportFailure
        }
    }

    /**
     * Create an exam [BR4.1].
     *
     * @param batchId The batch
     * @param title The title
     * @param date The exam date
     * @param totalMarks The total, at least one
     * @param batchSubjectId Which of the batch's subjects
     * @return Nothing on success, or why the server refused
     */
    override suspend fun createExam(
        batchId: String,
        title: String,
        date: String,
        totalMarks: Int,
        batchSubjectId: String,
    ): AuthResult<Unit> =
        callDiscardingBody {
            client.post("/v1/batches/$batchId/exams") {
                setBody(
                    ExamCreateRequestDto(
                        title = title,
                        date = date,
                        totalMarks = totalMarks,
                        batchSubjectId = batchSubjectId,
                    ),
                )
            }
        }

    /**
     * Read one exam's results, with whether they may be written.
     *
     * `writable` is carried through unchanged. Deriving it here — from
     * an empty result list, say, or from the exam's date — would be the
     * client deciding an authorization question [TC-9, BR5.5].
     *
     * @param examId The exam
     * @return The exam and its results, or a refusal
     */
    override suspend fun results(examId: String): AuthResult<ExamResultsPayload> {
        val response: AuthResult<ExamResultsResponseDto> =
            call { client.get("/v1/exams/$examId/results") }
        // Each refusal is rebuilt rather than cast. `Refused` and
        // `TransportFailure` are `AuthResult<Nothing>`, but a `when`
        // over all three resolves to their common supertype before
        // the expected type is known, and the alternative — casting
        // the whole result — would be an unchecked cast guarding
        // nothing.
        return when (response) {
            is AuthResult.Ok ->
                AuthResult.Ok(
                    ExamResultsPayload(
                        exam = response.value.exam,
                        results = response.value.results,
                        writable = response.value.writable,
                    ),
                )
            is AuthResult.Refused -> AuthResult.Refused(response.envelope)
            AuthResult.TransportFailure -> AuthResult.TransportFailure
        }
    }

    /**
     * Write one seat's mark [BR4.2, BR4.4].
     *
     * @param examId The exam
     * @param enrollmentId The seat
     * @param resultState `marked` or `absent`
     * @param marks The score, required for `marked` and null otherwise
     * @return Nothing on success, or why the server refused
     */
    override suspend fun writeMark(
        examId: String,
        enrollmentId: String,
        resultState: String,
        marks: Int?,
    ): AuthResult<Unit> =
        callDiscardingBody {
            client.post("/v1/exams/$examId/marks") {
                setBody(
                    MarkWriteBody(
                        enrollmentId = enrollmentId,
                        resultState = resultState,
                        marks = marks,
                    ),
                )
            }
        }

    /**
     * Read one seat's marksheet [BR6.2].
     *
     * **The reader chooses the path, and the seat is in it either
     * way.** Both endpoints parse a seat id; what differs is the lens
     * each resolves, so a guardian naming a seat that is not their
     * child's is refused by the route rather than by a check inside
     * the handler [BR7.2].
     *
     * @param examId The exam
     * @param enrollmentId The seat being read
     * @param reader Which lens is asking
     * @return The marksheet, or a refusal
     */
    override suspend fun marksheet(
        examId: String,
        enrollmentId: String,
        reader: MarksheetReader,
    ): AuthResult<MarksheetDto> =
        call {
            when (reader) {
                MarksheetReader.SELF ->
                    client.get(
                        "/v1/me/enrollments/$enrollmentId/exams/$examId/marksheet",
                    )
                MarksheetReader.CHILD ->
                    client.get(
                        "/v1/children/$enrollmentId/exams/$examId/marksheet",
                    )
            }
        }

    /**
     * Read one seat's progress across exams [BR6.6].
     *
     * Two paths for the same reason as [marksheet]: each resolves its
     * own lens over the seat named in it.
     *
     * @param enrollmentId The seat, from the path and never from a
     *   client hint [BR7.2]
     * @param reader Which lens is asking
     * @return The series in the server's date order
     */
    override suspend fun progress(
        enrollmentId: String,
        reader: MarksheetReader,
    ): AuthResult<List<ProgressEntryDto>> =
        call {
            when (reader) {
                MarksheetReader.SELF ->
                    client.get("/v1/me/enrollments/$enrollmentId/progress")
                MarksheetReader.CHILD ->
                    client.get("/v1/children/$enrollmentId/progress")
            }
        }

    /**
     * Set a batch's marksheet visibility [BR5.4].
     *
     * @param batchId The batch
     * @param visible Whether families see marksheets
     * @return Nothing on success, or why the server refused
     */
    override suspend fun setMarksheetVisible(
        batchId: String,
        visible: Boolean,
    ): AuthResult<Unit> =
        callDiscardingBody {
            client.put("/v1/batches/$batchId/marksheet-visibility") {
                setBody(MarksheetToggleRequestDto(visible = visible))
            }
        }
}
