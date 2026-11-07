package com.shikkhokplus.app.feature.myclasses

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.dhakaTodayIso
import com.shikkhokplus.app.core.network.ClassAttendanceBodyDto
import com.shikkhokplus.app.core.network.ClassRosterDto
import com.shikkhokplus.app.core.network.ClassSeatMarkDto
import com.shikkhokplus.app.core.network.ClassTopicBodyDto
import com.shikkhokplus.app.core.network.MyClassDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.timetable.OFFLINE_KEY
import com.shikkhokplus.app.feature.timetable.plusDays
import com.shikkhokplus.app.feature.timetable.weekFrom
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

/** How many days a week moves by. */
private const val WEEK_DAYS: Int = 7

/** The longest topic the server accepts. */
internal const val TOPIC_MAX: Int = 2000

/** What My classes renders below its week bar. */
sealed interface MyClassesBody {
    /** Waiting for the week. */
    data object Loading : MyClassesBody

    /**
     * The week's days that hold a class, in order.
     *
     * @property days Each day with my classes on it; empty when I teach none
     */
    data class Loaded(val days: List<Pair<String, List<MyClassDto>>>) : MyClassesBody

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : MyClassesBody
}

/**
 * My classes.
 *
 * @property weekStart The week's first day
 * @property body The week
 */
data class MyClassesUiState(
    val weekStart: String,
    val body: MyClassesBody = MyClassesBody.Loading,
)

/**
 * Holds a centre teacher's classes, a week at a time, across every
 * centre they teach at. The list is the server's: only classes assigned
 * to this account appear.
 *
 * @property repository The network
 * @param today The first week's start, overridden by tests
 */
class MyClassesViewModel(
    private val repository: MyClassesRepository,
    today: String = dhakaTodayIso(),
) : ViewModel() {

    private val _state = MutableStateFlow(MyClassesUiState(weekStart = today))

    /** What the screen renders. */
    val state: StateFlow<MyClassesUiState> = _state.asStateFlow()

    /** Read the week shown. */
    fun load() {
        val start = _state.value.weekStart
        viewModelScope.launch {
            val body = read(start)
            _state.update { if (it.weekStart == start) it.copy(body = body) else it }
        }
    }

    /** Read again after a failure. */
    fun retry() {
        _state.update { it.copy(body = MyClassesBody.Loading) }
        load()
    }

    /**
     * Move a week.
     *
     * @param weeks How many weeks, negative for earlier
     */
    fun shift(weeks: Int) {
        _state.update {
            it.copy(weekStart = plusDays(it.weekStart, weeks * WEEK_DAYS), body = MyClassesBody.Loading)
        }
        load()
    }

    private suspend fun read(start: String): MyClassesBody {
        val days = weekFrom(start)
        return when (val result = repository.classes(days.first(), days.last())) {
            is AuthResult.Ok ->
                MyClassesBody.Loaded(
                    days.map { day -> day to result.value.filter { it.date == day } }.filter { it.second.isNotEmpty() },
                )
            is AuthResult.Refused ->
                MyClassesBody.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> MyClassesBody.Failed(OFFLINE_KEY, retryable = true)
        }
    }
}

/** What one class's screen renders. */
sealed interface MyClassBody {
    /** Waiting for the roster. */
    data object Loading : MyClassBody

    /**
     * The roster as last read or written.
     *
     * @property roster The seats, versions and topic
     */
    data class Loaded(val roster: ClassRosterDto) : MyClassBody

    /**
     * The read failed; a class moved to another teacher lands here.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : MyClassBody
}

/**
 * One assigned class.
 *
 * @property body The roster
 * @property absent The seats marked absent, by enrollment id; everyone else is present
 * @property topic What was taught, as typed
 * @property saving Whether a write is in flight
 * @property failureKey Message key for the last refusal, or null
 * @property saved Whether the last write was saved, until acknowledged
 */
data class MyClassUiState(
    val body: MyClassBody = MyClassBody.Loading,
    val absent: Set<String> = emptySet(),
    val topic: String = "",
    val saving: Boolean = false,
    val failureKey: String? = null,
    val saved: Boolean = false,
) {
    /** Whether attendance may be changed and sent. */
    val writable: Boolean get() = (body as? MyClassBody.Loaded)?.roster?.writable == true
}

/**
 * Holds one assigned class: the whole roster's attendance at once, and
 * what was taught. A class a manager moved to another teacher is
 * refused with `CLASS_REASSIGNED`, shown as the server's own message;
 * nothing is saved.
 *
 * **The attendance replay key survives a failed send**, so a retry after
 * an unknown outcome is recognised by the server rather than recorded
 * twice; it is replaced only once a write is saved.
 *
 * @property repository The network
 * @property sessionId The class
 * @property newMutationId Makes a replay key, overridden by tests
 */
class MyClassViewModel(
    private val repository: MyClassesRepository,
    private val sessionId: String,
    private val newMutationId: () -> String = { UUID.randomUUID().toString() },
) : ViewModel() {

    private val _state = MutableStateFlow(MyClassUiState())

    /** What the screen renders. */
    val state: StateFlow<MyClassUiState> = _state.asStateFlow()

    private var attendanceKey: String = newMutationId()

    /** Read the roster and topic. */
    fun load() {
        viewModelScope.launch {
            val next =
                when (val result = repository.roster(sessionId)) {
                    is AuthResult.Ok -> loaded(result.value)
                    is AuthResult.Refused -> {
                        val error = result.envelope.error
                        MyClassUiState(body = MyClassBody.Failed(error.messageKey, error.retryable))
                    }
                    AuthResult.TransportFailure -> MyClassUiState(body = MyClassBody.Failed(OFFLINE_KEY, true))
                }
            _state.value = next
        }
    }

    /** Read again after a failure. */
    fun retry() {
        _state.value = MyClassUiState()
        load()
    }

    /**
     * Mark one seat present or absent.
     *
     * @param enrollmentId The seat
     */
    fun toggle(enrollmentId: String) =
        _state.update {
            val roster = (it.body as? MyClassBody.Loaded)?.roster ?: return@update it
            if (!roster.writable || it.saving || roster.seats.none { s -> s.enrollmentId == enrollmentId }) {
                return@update it
            }
            val absent = if (enrollmentId in it.absent) it.absent - enrollmentId else it.absent + enrollmentId
            it.copy(absent = absent, failureKey = null, saved = false)
        }

    /**
     * Type what was taught.
     *
     * @param text The topic
     */
    fun topic(text: String) = _state.update { it.copy(topic = text.take(TOPIC_MAX), failureKey = null, saved = false) }

    /** Send every seat's mark. */
    fun saveAttendance() {
        val current = _state.value
        val roster = (current.body as? MyClassBody.Loaded)?.roster ?: return
        if (!roster.writable || current.saving) return
        val marks = roster.seats.map { ClassSeatMarkDto(it.enrollmentId, it.enrollmentId !in current.absent) }
        val body = ClassAttendanceBodyDto(roster.attendanceVersion, attendanceKey, marks)
        write(
            send = { repository.submitAttendance(sessionId, body) },
            apply = { result ->
                attendanceKey = newMutationId()
                val present = marks.associate { it.enrollmentId to it.present }
                roster.copy(
                    attendanceVersion = result.attendanceVersion,
                    seats = roster.seats.map { it.copy(present = present[it.enrollmentId]) },
                )
            },
        )
    }

    /** Send what was taught. */
    fun saveTopic() {
        val current = _state.value
        val roster = (current.body as? MyClassBody.Loaded)?.roster ?: return
        val topic = current.topic.trim()
        if (topic.isEmpty() || current.saving) return
        val body = ClassTopicBodyDto(roster.topicVersion, newMutationId(), topic, plan = false)
        write(
            send = { repository.writeTopic(sessionId, body) },
            apply = { result -> roster.copy(topic = topic, topicVersion = result.topicVersion) },
        )
    }

    private fun <T> write(send: suspend () -> AuthResult<T>, apply: (T) -> ClassRosterDto) {
        _state.update { it.copy(saving = true, failureKey = null, saved = false) }
        viewModelScope.launch {
            when (val result = send()) {
                is AuthResult.Ok ->
                    _state.update {
                        it.copy(body = MyClassBody.Loaded(apply(result.value)), saving = false, saved = true)
                    }
                is AuthResult.Refused ->
                    _state.update { it.copy(saving = false, failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(saving = false, failureKey = OFFLINE_KEY) }
            }
        }
    }

    private fun loaded(roster: ClassRosterDto): MyClassUiState =
        MyClassUiState(
            body = MyClassBody.Loaded(roster),
            absent = roster.seats.filter { it.present == false }.map { it.enrollmentId }.toSet(),
            topic = roster.topic.orEmpty(),
        )
}
