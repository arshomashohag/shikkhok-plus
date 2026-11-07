package com.shikkhokplus.app.feature.myexams

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.network.ExamExaminerDto
import com.shikkhokplus.app.core.network.ExaminerResultsDto
import com.shikkhokplus.app.core.network.MarkWriteBody
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.MyExamDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.timetable.OFFLINE_KEY
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The result state of a seat with a number entered. */
internal const val STATE_MARKED: String = "marked"

/** The result state of a seat recorded absent. */
internal const val STATE_ABSENT: String = "absent"

/** The result state of a seat that joined after the exam: it cannot be marked. */
internal const val STATE_JOINED_AFTER: String = "joined_after"

/** The result state of a seat nobody has marked yet. */
internal const val STATE_NOT_ENTERED: String = "not_entered"

/**
 * A read that may still be on its way, or failed.
 *
 * @param T What a successful read holds
 */
sealed interface Loadable<out T> {
    /** On its way. */
    data object Loading : Loadable<Nothing>

    /**
     * Read.
     *
     * @property value What was read
     */
    data class Loaded<T>(val value: T) : Loadable<T>

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : Loadable<Nothing>

    companion object {
        /**
         * Read a result into a loadable.
         *
         * @param result The network's answer
         * @return Loaded, or Failed with the server's key
         */
        fun <T> of(result: AuthResult<T>): Loadable<T> =
            when (result) {
                is AuthResult.Ok -> Loaded(result.value)
                is AuthResult.Refused -> Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                AuthResult.TransportFailure -> Failed(OFFLINE_KEY, retryable = true)
            }
    }
}

/** The message key a refusal or a lost request shows. */
private fun failureKey(result: AuthResult<*>): String? =
    when (result) {
        is AuthResult.Ok -> null
        is AuthResult.Refused -> result.envelope.error.messageKey
        AuthResult.TransportFailure -> OFFLINE_KEY
    }

/**
 * Holds the exams a centre asked me to mark.
 *
 * @property repository The network
 */
class MyExamsViewModel(
    private val repository: MyExamsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<Loadable<List<MyExamDto>>>(Loadable.Loading)

    /** What the screen renders. */
    val state: StateFlow<Loadable<List<MyExamDto>>> = _state.asStateFlow()

    /** Read the exams. */
    fun load() {
        viewModelScope.launch { _state.value = Loadable.of(repository.exams()) }
    }

    /** Read again after a failure. */
    fun retry() {
        _state.value = Loadable.Loading
        load()
    }
}

/** What the marks screen last confirmed. */
enum class MarksNotice {
    /** A mark was saved. */
    SAVED,

    /** The results were published. */
    PUBLISHED,
}

/**
 * One exam's marks, as its examiner enters them.
 *
 * @property sheet The exam and its results
 * @property typed What is typed per seat, by enrollment id
 * @property saving Whether a write is in flight
 * @property failureKey Message key for the last refusal, or null
 * @property notice What the last write confirmed, or null
 */
data class MyExamMarksUiState(
    val sheet: Loadable<ExaminerResultsDto> = Loadable.Loading,
    val typed: Map<String, String> = emptyMap(),
    val saving: Boolean = false,
    val failureKey: String? = null,
    val notice: MarksNotice? = null,
) {
    /** Whether publishing is offered: marks may be written and the results are not out. */
    val canPublish: Boolean
        get() = (sheet as? Loadable.Loaded)?.value?.let { it.writable && !it.exam.published } == true
}

/**
 * Holds one exam's marks: a number or absent per seat, then publish.
 * Whether a mark may be entered, and whether the sheet is complete
 * enough to publish, are the server's answers; one moved to another
 * examiner is refused with `EXAM_REASSIGNED`.
 *
 * @property repository The network
 * @property examId The exam
 */
class MyExamMarksViewModel(
    private val repository: MyExamsRepository,
    private val examId: String,
) : ViewModel() {

    private val _state = MutableStateFlow(MyExamMarksUiState())

    /** What the screen renders. */
    val state: StateFlow<MyExamMarksUiState> = _state.asStateFlow()

    /** Read the exam and its results. */
    fun load() {
        viewModelScope.launch {
            val sheet = Loadable.of(repository.results(examId))
            _state.update { it.copy(sheet = sheet, typed = typedFrom(sheet)) }
        }
    }

    /** Read again after a failure. */
    fun retry() {
        _state.value = MyExamMarksUiState()
        load()
    }

    /**
     * Type one seat's mark.
     *
     * @param enrollmentId The seat
     * @param text What is typed
     */
    fun type(enrollmentId: String, text: String) =
        _state.update { it.copy(typed = it.typed + (enrollmentId to text), failureKey = null, notice = null) }

    /**
     * Send one seat's typed mark; nothing is sent while it is not a number.
     *
     * @param enrollmentId The seat
     */
    fun save(enrollmentId: String) {
        val marks = Numerals.parseAmount(_state.value.typed[enrollmentId].orEmpty())?.toDouble() ?: return
        write(notice = MarksNotice.SAVED) { repository.mark(examId, MarkWriteBody(enrollmentId, STATE_MARKED, marks)) }
    }

    /**
     * Record one seat absent: no marks at all, never a zero.
     *
     * @param enrollmentId The seat
     */
    fun absent(enrollmentId: String) =
        write(notice = MarksNotice.SAVED) { repository.mark(examId, MarkWriteBody(enrollmentId, STATE_ABSENT)) }

    /** Publish the results. */
    fun publish() {
        if (!_state.value.canPublish) return
        write(notice = MarksNotice.PUBLISHED) { repository.publish(examId) }
    }

    private fun write(notice: MarksNotice, send: suspend () -> AuthResult<Unit>) {
        val sheet = (_state.value.sheet as? Loadable.Loaded)?.value ?: return
        if (!sheet.writable || _state.value.saving) return
        _state.update { it.copy(saving = true, failureKey = null, notice = null) }
        viewModelScope.launch {
            val result = send()
            val key = failureKey(result)
            if (key != null) {
                _state.update { it.copy(saving = false, failureKey = key) }
                return@launch
            }
            val next = Loadable.of(repository.results(examId))
            _state.update {
                if (next is Loadable.Loaded) {
                    it.copy(sheet = next, typed = typedFrom(next), saving = false, notice = notice)
                } else {
                    it.copy(saving = false, notice = notice)
                }
            }
        }
    }

    private fun typedFrom(sheet: Loadable<ExaminerResultsDto>): Map<String, String> =
        (sheet as? Loadable.Loaded)?.value?.results.orEmpty().associate { row ->
            row.enrollmentId to row.marks?.let(Numerals::mark).orEmpty()
        }
}

/**
 * Who marks one exam, and who may be named.
 *
 * @property exam The exam's examiner, once read
 * @property members Who may be named: live members who have not declined
 * @property saving Whether a change is in flight
 * @property failureKey Message key for the last refusal, or null
 * @property changed Whether the last change was saved
 */
data class ExaminerUiState(
    val exam: ExamExaminerDto? = null,
    val members: List<MemberDto> = emptyList(),
    val saving: Boolean = false,
    val failureKey: String? = null,
    val changed: Boolean = false,
)

/**
 * Holds the examiner control on a centre's exam: shows who marks it and
 * changes it. Whether one may be named at all is the server's rule.
 *
 * @property repository The network
 * @property examId The exam
 */
class ExaminerViewModel(
    private val repository: ExaminerRepository,
    private val examId: String,
) : ViewModel() {

    private val _state = MutableStateFlow(ExaminerUiState())

    /** What the control renders. */
    val state: StateFlow<ExaminerUiState> = _state.asStateFlow()

    /** Read the exam's examiner and the members to choose from. */
    fun load() {
        viewModelScope.launch {
            coroutineScope {
                val members = async { repository.members() }
                val exam = repository.exam(examId)
                _state.update {
                    it.copy(
                        exam = (exam as? AuthResult.Ok)?.value,
                        members =
                            (members.await() as? AuthResult.Ok)?.value.orEmpty()
                                .filter { m -> !m.revoked && m.decision != "declined" },
                    )
                }
            }
        }
    }

    /**
     * Name the examiner.
     *
     * @param memberId A member the picker offers, or null for nobody
     */
    fun choose(memberId: String?) {
        val current = _state.value
        val exam = current.exam ?: return
        if (current.saving || exam.cancelled || exam.examinerMemberId == memberId) return
        if (memberId != null && current.members.none { it.memberId == memberId }) return
        _state.update { it.copy(saving = true, failureKey = null, changed = false) }
        viewModelScope.launch {
            when (val result = repository.setExaminer(examId, memberId)) {
                is AuthResult.Ok -> _state.update { it.copy(exam = result.value, saving = false, changed = true) }
                else -> _state.update { it.copy(saving = false, failureKey = failureKey(result)) }
            }
        }
    }
}
