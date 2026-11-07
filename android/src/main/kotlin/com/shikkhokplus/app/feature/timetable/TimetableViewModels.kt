package com.shikkhokplus.app.feature.timetable

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.dhakaTodayIso
import com.shikkhokplus.app.core.format.isoDate
import com.shikkhokplus.app.core.format.isoToUtcMillis
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.RoomDto
import com.shikkhokplus.app.core.network.TimetableClassDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The message key for a request that never got an answer. */
internal const val OFFLINE_KEY: String = "error.network.unreachable"

/** How many days the timetable shows at once. */
private const val WEEK_DAYS: Int = 7

/** A day in milliseconds, for stepping ISO dates. */
private const val DAY_MILLIS: Long = 24L * 60 * 60 * 1000

/**
 * Move an ISO date by some days.
 *
 * @param iso `yyyy-MM-dd`
 * @param days How many days, negative for earlier
 * @return The moved date, or [iso] unchanged if it does not parse
 */
internal fun plusDays(iso: String, days: Int): String =
    isoToUtcMillis(iso)?.let { isoDate(it + days * DAY_MILLIS) } ?: iso

/**
 * The seven days starting at [start].
 *
 * @param start `yyyy-MM-dd`
 * @return The days, in order
 */
internal fun weekFrom(start: String): List<String> = (0 until WEEK_DAYS).map { plusDays(start, it) }

/**
 * A refusal, with the class it clashes with when the server named one.
 *
 * @property messageKey The server's key, or the offline key
 * @property clashBatch The other class's batch, or null
 * @property clashTime The other class's start time, or null
 */
data class TimetableFailure(
    val messageKey: String,
    val clashBatch: String? = null,
    val clashTime: String? = null,
) {
    companion object {
        /**
         * Read a refusal, keeping a clash's details.
         *
         * @param envelope The server's refusal
         * @return The failure
         */
        fun of(envelope: ErrorEnvelope): TimetableFailure {
            val details = envelope.error.details.takeIf { envelope.error.code == CLASH_CODE }
            return TimetableFailure(envelope.error.messageKey, details?.get("batch"), details?.get("start_time"))
        }

        /** The code a teacher or room clash is refused with. */
        const val CLASH_CODE: String = "CLASS_CLASH"
    }
}

/**
 * The class being changed, and what the change sheet has chosen.
 *
 * @property target The class
 * @property teacherMemberId The chosen teacher, or null for nobody yet
 * @property roomId The chosen room, or null for none
 * @property swapWith Another class to swap teachers with, or null
 */
data class ClassChange(
    val target: TimetableClassDto,
    val teacherMemberId: String? = target.teacherMemberId,
    val roomId: String? = target.roomId,
    val swapWith: String? = null,
)

/** What the timetable renders below its week bar. */
sealed interface TimetableBody {
    /** Waiting for the week. */
    data object Loading : TimetableBody

    /**
     * The week, every day present even when empty.
     *
     * @property days Each day with its classes, in the server's order
     */
    data class Loaded(val days: List<Pair<String, List<TimetableClassDto>>>) : TimetableBody

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : TimetableBody
}

/**
 * The centre timetable.
 *
 * @property weekStart The week's first day
 * @property body The week
 * @property teachers Who a class may be given: live members who have not declined
 * @property rooms The rooms still in use
 * @property change The class being changed, or null
 * @property saving Whether a change is in flight
 * @property failure Why the last change was refused, or null
 */
data class TimetableUiState(
    val weekStart: String,
    val body: TimetableBody = TimetableBody.Loading,
    val teachers: List<MemberDto> = emptyList(),
    val rooms: List<RoomDto> = emptyList(),
    val change: ClassChange? = null,
    val saving: Boolean = false,
    val failure: TimetableFailure? = null,
) {
    /** The other classes the one being changed may swap teachers with: same day, not cancelled. */
    val swapCandidates: List<TimetableClassDto>
        get() {
            val target = change?.target ?: return emptyList()
            val day = (body as? TimetableBody.Loaded)?.days?.firstOrNull { it.first == target.date }?.second
            return day.orEmpty().filter { it.sessionId != target.sessionId && !it.cancelled }
        }
}

/**
 * Holds the centre timetable: a week at a time, changing one class's
 * teacher and room, and swapping two classes' teachers. A clash is the
 * server's to find; its refusal names the other class.
 *
 * @property repository The network
 * @param today The first week's start, overridden by tests
 */
class TimetableViewModel(
    private val repository: TimetableRepository,
    today: String = dhakaTodayIso(),
) : ViewModel() {

    private val _state = MutableStateFlow(TimetableUiState(weekStart = today))

    /** What the screen renders. */
    val state: StateFlow<TimetableUiState> = _state.asStateFlow()

    /** Read the week, and the teachers and rooms the pickers offer. */
    fun load() {
        val start = _state.value.weekStart
        viewModelScope.launch {
            coroutineScope {
                val members = async { repository.members() }
                val rooms = async { repository.rooms() }
                val body = read(start)
                _state.update {
                    it.copy(
                        body = body,
                        teachers =
                            (members.await() as? AuthResult.Ok)?.value.orEmpty()
                                .filter { m -> !m.revoked && m.decision != "declined" },
                        rooms = (rooms.await() as? AuthResult.Ok)?.value.orEmpty().filter { r -> !r.archived },
                    )
                }
            }
        }
    }

    /** Read again after a failure. */
    fun retry() {
        _state.update { it.copy(body = TimetableBody.Loading) }
        load()
    }

    /**
     * Move a week.
     *
     * @param weeks How many weeks, negative for earlier
     */
    fun shift(weeks: Int) {
        val start = plusDays(_state.value.weekStart, weeks * WEEK_DAYS)
        _state.update { it.copy(weekStart = start, body = TimetableBody.Loading, change = null, failure = null) }
        viewModelScope.launch {
            val body = read(start)
            _state.update { if (it.weekStart == start) it.copy(body = body) else it }
        }
    }

    /**
     * Open the change sheet for one class.
     *
     * @param sessionId The class
     */
    fun open(sessionId: String) {
        val target =
            (_state.value.body as? TimetableBody.Loaded)?.days?.flatMap { it.second }
                ?.firstOrNull { it.sessionId == sessionId && !it.cancelled } ?: return
        _state.update { it.copy(change = ClassChange(target), failure = null) }
    }

    /** Close the change sheet. */
    fun close() = _state.update { it.copy(change = null, failure = null) }

    /**
     * Choose the class's teacher.
     *
     * @param memberId A teacher the picker offers, or null for nobody yet
     */
    fun teacher(memberId: String?) =
        _state.update { form ->
            if (memberId != null && form.teachers.none { it.memberId == memberId }) return@update form
            form.copy(change = form.change?.copy(teacherMemberId = memberId, swapWith = null), failure = null)
        }

    /**
     * Choose the class's room.
     *
     * @param roomId A room the picker offers, or null for none
     */
    fun room(roomId: String?) =
        _state.update { form ->
            if (roomId != null && form.rooms.none { it.roomId == roomId }) return@update form
            form.copy(change = form.change?.copy(roomId = roomId), failure = null)
        }

    /**
     * Choose a class to swap teachers with instead, or none.
     *
     * @param sessionId A swap candidate, or null
     */
    fun swapWith(sessionId: String?) =
        _state.update { form ->
            if (sessionId != null && form.swapCandidates.none { it.sessionId == sessionId }) return@update form
            form.copy(change = form.change?.copy(swapWith = sessionId), failure = null)
        }

    /** Send the change: a swap when one is chosen, else this class's teacher and room. */
    fun save() {
        val change = _state.value.change ?: return
        if (_state.value.saving) return
        _state.update { it.copy(saving = true, failure = null) }
        viewModelScope.launch {
            val result =
                change.swapWith?.let { repository.swap(change.target.sessionId, it) }
                    ?: repository.assign(change.target.sessionId, change.teacherMemberId, change.roomId)
            when (result) {
                is AuthResult.Ok -> {
                    val body = read(_state.value.weekStart)
                    _state.update { it.copy(body = body, change = null, saving = false) }
                }
                is AuthResult.Refused ->
                    _state.update { it.copy(saving = false, failure = TimetableFailure.of(result.envelope)) }
                AuthResult.TransportFailure ->
                    _state.update { it.copy(saving = false, failure = TimetableFailure(OFFLINE_KEY)) }
            }
        }
    }

    private suspend fun read(start: String): TimetableBody {
        val days = weekFrom(start)
        return when (val result = repository.timetable(days.first(), days.last())) {
            is AuthResult.Ok -> TimetableBody.Loaded(days.map { day -> day to result.value.filter { it.date == day } })
            is AuthResult.Refused ->
                TimetableBody.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> TimetableBody.Failed(OFFLINE_KEY, retryable = true)
        }
    }
}

/**
 * The rooms screen.
 *
 * @property rooms Every room, archived included
 * @property loading Whether the list is being read
 * @property typedName The add form's name
 * @property saving Whether a write is in flight
 * @property failureKey Message key for the last refusal, or null
 */
data class RoomsUiState(
    val rooms: List<RoomDto> = emptyList(),
    val loading: Boolean = true,
    val typedName: String = "",
    val saving: Boolean = false,
    val failureKey: String? = null,
)

/**
 * Holds the centre's rooms: adding one, and stopping or resuming one.
 * A room is never deleted: classes held in it keep naming it.
 *
 * @property repository The network
 */
class RoomsViewModel(
    private val repository: TimetableRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(RoomsUiState())

    /** What the screen renders. */
    val state: StateFlow<RoomsUiState> = _state.asStateFlow()

    /** Read the rooms. */
    fun load() {
        viewModelScope.launch { refresh(failureKey = null) }
    }

    /**
     * Type a new room's name.
     *
     * @param text The name
     */
    fun name(text: String) = _state.update { it.copy(typedName = text.take(ROOM_NAME_MAX), failureKey = null) }

    /** Add the typed room. */
    fun add() {
        val name = _state.value.typedName.trim()
        if (name.isEmpty() || _state.value.saving) return
        write { repository.addRoom(name) }
    }

    /**
     * Stop or resume using a room.
     *
     * @param roomId The room
     * @param archived Whether it is no longer in use
     */
    fun archive(roomId: String, archived: Boolean) = write { repository.archiveRoom(roomId, archived) }

    private fun write(call: suspend () -> AuthResult<RoomDto>) {
        _state.update { it.copy(saving = true, failureKey = null) }
        viewModelScope.launch {
            when (val result = call()) {
                is AuthResult.Ok -> {
                    _state.update { it.copy(typedName = "") }
                    refresh(failureKey = null)
                }
                is AuthResult.Refused ->
                    _state.update { it.copy(saving = false, failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(saving = false, failureKey = OFFLINE_KEY) }
            }
        }
    }

    private suspend fun refresh(failureKey: String?) {
        val result = repository.rooms()
        _state.update {
            when (result) {
                is AuthResult.Ok ->
                    it.copy(rooms = result.value, loading = false, saving = false, failureKey = failureKey)
                is AuthResult.Refused ->
                    it.copy(loading = false, saving = false, failureKey = result.envelope.error.messageKey)
                AuthResult.TransportFailure -> it.copy(loading = false, saving = false, failureKey = OFFLINE_KEY)
            }
        }
    }

    private companion object {
        const val ROOM_NAME_MAX = 60
    }
}
