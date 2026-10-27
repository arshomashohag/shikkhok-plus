package com.shikkhokplus.app.feature.marks

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.ExamDto
import com.shikkhokplus.app.core.network.ExamResultDto
import com.shikkhokplus.app.core.network.MarksheetDto
import com.shikkhokplus.app.core.network.ProgressDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * One exam's results, with whether they may be written.
 *
 * @property exam The exam
 * @property results One per seat [BR4.3]
 * @property writable Whether marks may be written, decided
 *   server-side [BR5.5]
 */
data class ExamResultsPayload(
    val exam: ExamDto,
    val results: List<ExamResultDto>,
    val writable: Boolean = true,
)

/**
 * Who is reading a marksheet, which decides the route [BR6.2, BR7.2].
 *
 * Not a preference and not a hint the server trusts: it selects which
 * endpoint is called, and each endpoint resolves its own lens. Naming
 * the wrong one is refused by that lens rather than silently served.
 */
enum class MarksheetReader {
    /** The student reading their own seat. */
    SELF,

    /** A guardian reading their recorded child's seat. */
    CHILD,
}

/** What the marks repository must provide. */
interface MarksRepository {
    /**
     * List one batch's exams.
     *
     * @param batchId The batch
     * @return The exams
     */
    suspend fun exams(batchId: String): AuthResult<List<ExamDto>>

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
    suspend fun createExam(
        batchId: String,
        title: String,
        date: String,
        totalMarks: Int,
        batchSubjectId: String,
    ): AuthResult<Unit>

    /**
     * Read one exam's results.
     *
     * @param examId The exam
     * @return The exam and its results
     */
    suspend fun results(examId: String): AuthResult<ExamResultsPayload>

    /**
     * Write one seat's mark [BR4.2, BR4.4].
     *
     * **Interactive, so no version and no mutation id** [BR3.11]. A
     * correction appends a row server-side and supersedes the old one;
     * nothing is updated in place.
     *
     * @param examId The exam
     * @param enrollmentId The seat
     * @param resultState `marked` or `absent`
     * @param marks The score, required for `marked` and null otherwise
     * @return Nothing on success, or why the server refused
     */
    suspend fun writeMark(
        examId: String,
        enrollmentId: String,
        resultState: String,
        marks: Int?,
    ): AuthResult<Unit>

    /**
     * Read one seat's marksheet [BR6.2].
     *
     * **The seat is always named, and `reader` chooses the route.**
     * A student and a guardian read the same marksheet over two
     * different paths — `/v1/me/enrollments/…` and `/v1/children/…` —
     * because each resolves a different lens, and the lens is what
     * decides whether this caller may see this seat [BR7.2]. A single
     * path carrying a "whose is it" flag would make that an
     * application check instead of a routing one.
     *
     * An earlier form of this contract took a nullable seat, meaning
     * "the student's own". It could not be implemented: both server
     * routes parse a seat id from the path, so the student case had
     * no id to send.
     *
     * @param examId The exam
     * @param enrollmentId The seat, in both cases
     * @param reader Which lens is asking
     * @return The marksheet, or a refusal
     */
    suspend fun marksheet(
        examId: String,
        enrollmentId: String,
        reader: MarksheetReader,
    ): AuthResult<MarksheetDto>

    /**
     * Read a child's progress across exams [BR6.6].
     *
     * @param enrollmentId The child's seat, from the path and never
     *   from a client hint [BR7.2]
     * @return The series in the server's date order
     */
    suspend fun progress(enrollmentId: String): AuthResult<ProgressDto>

    /**
     * Set a batch's marksheet visibility [BR5.4].
     *
     * @param batchId The batch
     * @param visible Whether families see marksheets
     * @return Nothing on success, or why the server refused
     */
    suspend fun setMarksheetVisible(
        batchId: String,
        visible: Boolean,
    ): AuthResult<Unit>
}

/**
 * Holds the exam, mark and marksheet screens' state. Holds no business
 * logic [TC-9, D-31].
 *
 * Every decision is delegated to [MarksStateMapper], which is the unit
 * the tests target. In particular **no aggregate is computed here**:
 * rank, average, highest and the bands all arrive decided, because each
 * is a disclosure decision rather than a formatting one [BR6.2–BR6.5].
 *
 * **Every write here is interactive** [BR3.11]. Mark entry does not
 * queue: only attendance and the topic log do [BR3.1], and a mark
 * written offline would be the third queueing path that rule forbids.
 *
 * @property repository Where exams and marks come from
 */
class MarksViewModel(
    private val repository: MarksRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<MarksUiState>(MarksUiState.Idle)

    /** What the screen renders. */
    val state: StateFlow<MarksUiState> = _state.asStateFlow()

    private var lastBatchId: String? = null
    private var lastBatchName: String = ""
    private var lastExamId: String? = null

    // What last failed, so `retry` repeats the user's intent rather
    // than degrading into a reload.
    private var lastWrite: (suspend () -> AuthResult<Unit>)? = null

    /**
     * Load a batch's exams.
     *
     * @param batchId The batch
     * @param batchName Which class, for the heading
     */
    fun loadExams(batchId: String, batchName: String = "") {
        lastBatchId = batchId
        lastBatchName = batchName
        lastWrite = null
        _state.value = MarksUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.exams(batchId)) {
                    is AuthResult.Ok ->
                        MarksStateMapper.afterExams(batchName, result.value)
                    is AuthResult.Refused -> MarksStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        MarksStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Create an exam [BR4.1].
     *
     * The subject-belongs-to-batch check is the server's, and its
     * refusal is `NOT_AVAILABLE` rather than descriptive — naming the
     * subject id as wrong would be the oracle.
     *
     * @param title The title
     * @param date The exam date
     * @param totalMarks The total, at least one
     * @param batchSubjectId Which subject
     */
    fun createExam(
        title: String,
        date: String,
        totalMarks: Int,
        batchSubjectId: String,
    ) {
        val batchId = lastBatchId ?: return
        runWrite({ repository.createExam(batchId, title, date, totalMarks, batchSubjectId) }) {
            loadExams(batchId, lastBatchName)
        }
    }

    /**
     * Load one exam's results, open for entry.
     *
     * @param examId The exam
     */
    fun loadResults(examId: String) {
        lastExamId = examId
        lastWrite = null
        _state.value = MarksUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.results(examId)) {
                    is AuthResult.Ok ->
                        MarksStateMapper.afterResults(
                            examId = result.value.exam.examId,
                            examTitle = result.value.exam.title,
                            totalMarks = result.value.exam.totalMarks,
                            results = result.value.results,
                            writable = result.value.writable,
                        )
                    is AuthResult.Refused -> MarksStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        MarksStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Write one seat's mark [BR4.2, BR4.4].
     *
     * **The range check is the server's** — `0 <= marks <= total_marks`
     * spans a foreign key and is enforced in the write path there. The
     * screen's own check is format-only (is this an integer), never
     * policy, which is the standing division on this surface.
     *
     * @param enrollmentId The seat
     * @param resultState `marked` or `absent`
     * @param marks The score, or null for an absence
     */
    fun writeMark(enrollmentId: String, resultState: String, marks: Int?) {
        val examId = lastExamId ?: return
        runWrite({ repository.writeMark(examId, enrollmentId, resultState, marks) }) {
            loadResults(examId)
        }
    }

    /**
     * Load a marksheet for a student or guardian [BR6.2].
     *
     * @param examId The exam
     * @param enrollmentId The seat being read
     * @param reader Which lens is asking, which chooses the route
     */
    fun loadMarksheet(
        examId: String,
        enrollmentId: String,
        reader: MarksheetReader,
    ) {
        _state.value = MarksUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.marksheet(examId, enrollmentId, reader)) {
                    is AuthResult.Ok -> MarksStateMapper.afterMarksheet(result.value)
                    // **The toggle-off case is NOT distinguishable
                    // here, and that is the server's deliberate
                    // choice rather than a gap** [BR5.4].
                    //
                    // `app/marks/views.py` refuses a family lens whose
                    // batch has `marksheet_visible` false through the
                    // same shared `refuse()` it uses for a seat the
                    // lens does not reach -- so the client receives
                    // `NOT_AVAILABLE` / `teaching.not_available` in
                    // both cases and cannot tell them apart.
                    //
                    // That is correct: a distinct code would let a
                    // family learn that a marksheet EXISTS and is
                    // merely hidden, which is a fact about the batch
                    // they are not entitled to. An earlier draft of
                    // this file branched on a `MARKSHEET_NOT_PUBLISHED`
                    // code; the backend emits no such code, so that
                    // branch was unreachable and has been removed
                    // rather than left to look like working behaviour.
                    is AuthResult.Refused -> MarksStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        MarksStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Load a child's progress across exams [BR6.6].
     *
     * @param enrollmentId The child's seat, which arrives as a path
     *   parameter and never from a client hint [BR7.2]
     */
    fun loadProgress(enrollmentId: String) {
        _state.value = MarksUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.progress(enrollmentId)) {
                    is AuthResult.Ok -> MarksStateMapper.afterProgress(result.value)
                    is AuthResult.Refused -> MarksStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        MarksStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Set whether families see this batch's marksheets [BR5.4].
     *
     * @param visible Whether to publish
     */
    fun setMarksheetVisible(visible: Boolean) {
        val batchId = lastBatchId ?: return
        runWrite({ repository.setMarksheetVisible(batchId, visible) }) {
            loadExams(batchId, lastBatchName)
        }
    }

    /**
     * Run one interactive write, then reload.
     *
     * @param write The write to attempt
     * @param reload What to read afterwards
     */
    private fun runWrite(
        write: suspend () -> AuthResult<Unit>,
        reload: () -> Unit,
    ) {
        lastWrite = write
        _state.value = MarksUiState.Loading
        viewModelScope.launch {
            when (val result = write()) {
                is AuthResult.Ok -> {
                    lastWrite = null
                    reload()
                }
                is AuthResult.Refused ->
                    _state.value = MarksStateMapper.afterError(result.envelope)
                AuthResult.TransportFailure ->
                    _state.value = MarksStateMapper.afterTransportFailure()
            }
        }
    }

    /**
     * Repeat whatever last failed, and only when the user asks.
     *
     * A failed mark write is retried **as that write**, not as a
     * reload: degrading it would drop the teacher's entry silently and
     * leave the seat unmarked with nothing on screen to say so.
     */
    fun retry() {
        val write = lastWrite
        if (write != null) {
            val examId = lastExamId
            runWrite(write) {
                if (examId != null) loadResults(examId) else reloadExams()
            }
            return
        }
        reloadExams()
    }

    /** Reload the exam list, when one was loaded. */
    private fun reloadExams() {
        lastBatchId?.let { loadExams(it, lastBatchName) }
    }
}
