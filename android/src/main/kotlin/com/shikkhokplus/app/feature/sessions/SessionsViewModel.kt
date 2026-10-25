package com.shikkhokplus.app.feature.sessions

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.SessionDetailDto
import com.shikkhokplus.app.core.network.SessionDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What the sessions repository must provide. */
interface SessionsRepository {
    /**
     * List one batch's sessions.
     *
     * @param batchId The batch
     * @return The sessions, an error envelope, or a transport failure
     */
    suspend fun sessions(batchId: String): AuthResult<List<SessionDto>>

    /**
     * Read one session with its roster [BR1.5].
     *
     * @param sessionId The session
     * @return The session and its roster
     */
    suspend fun sessionDetail(sessionId: String): AuthResult<SessionDetailDto>

    /**
     * Create an ad-hoc session [BR1.4].
     *
     * @param batchId The batch
     * @param date The date
     * @param startTime The start time
     * @param batchSubjectId Which subject, or null
     * @return Nothing on success, or why the server refused
     */
    suspend fun createAdHoc(
        batchId: String,
        date: String,
        startTime: String,
        batchSubjectId: String?,
    ): AuthResult<Unit>

    /**
     * Reschedule a session, preserving its identity [BR1.7].
     *
     * @param sessionId The session
     * @param date The new date
     * @param startTime The new start time
     * @return Nothing on success, or why the server refused
     */
    suspend fun reschedule(
        sessionId: String,
        date: String,
        startTime: String,
    ): AuthResult<Unit>

    /**
     * Cancel a session [BR1.6].
     *
     * @param sessionId The session
     * @return Nothing on success, or why the server refused
     */
    suspend fun cancel(sessionId: String): AuthResult<Unit>
}

/**
 * Holds the session list's state. Holds no business logic [TC-9, D-31].
 *
 * Every decision is delegated to [SessionsStateMapper], which is the
 * unit the tests target. This class owns the coroutine and the state
 * holder and nothing else.
 *
 * **These writes are interactive and do not queue** [BR3.1, BR3.11].
 * Only attendance and the topic log queue; creating, rescheduling and
 * cancelling a session all require connectivity and surface an explicit
 * retry on failure. A queue here would be the third path BR3.1's
 * violation_behaviour (b) asserts against.
 *
 * @property repository Where sessions come from
 */
class SessionsViewModel(
    private val repository: SessionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<SessionsUiState>(SessionsUiState.Idle)

    /** What the screen renders. */
    val state: StateFlow<SessionsUiState> = _state.asStateFlow()

    private var lastBatchId: String? = null
    private var lastBatchName: String = ""

    // The action that last failed, so `retry` repeats the user's intent
    // rather than degrading into a reload -- which would silently drop
    // what they asked for and leave no error on screen.
    private var lastWrite: (suspend () -> AuthResult<Unit>)? = null

    /**
     * Load a batch's sessions.
     *
     * @param batchId The batch
     * @param batchName Which class, for the heading
     */
    fun load(batchId: String, batchName: String = "") {
        lastBatchId = batchId
        lastBatchName = batchName
        lastWrite = null
        _state.value = SessionsUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.sessions(batchId)) {
                    is AuthResult.Ok ->
                        SessionsStateMapper.afterLoad(batchName, result.value)
                    is AuthResult.Refused ->
                        SessionsStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        SessionsStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Create an ad-hoc session for a date with no scheduled slot
     * [BR1.4].
     *
     * @param date The date
     * @param startTime The start time
     * @param batchSubjectId Which subject, or null
     */
    fun createAdHoc(date: String, startTime: String, batchSubjectId: String? = null) {
        val batchId = lastBatchId ?: return
        runWrite { repository.createAdHoc(batchId, date, startTime, batchSubjectId) }
    }

    /**
     * Reschedule a session [BR1.7].
     *
     * The session keeps its id, its topic and its attendance; the
     * server does not re-key anything, so nothing is cleared here
     * either.
     *
     * @param sessionId The session
     * @param date The new date
     * @param startTime The new start time
     */
    fun reschedule(sessionId: String, date: String, startTime: String) {
        runWrite { repository.reschedule(sessionId, date, startTime) }
    }

    /**
     * Cancel a session [BR1.6].
     *
     * Existing attendance is left untouched by the server; cancelling
     * stops further writes rather than erasing what was recorded.
     *
     * @param sessionId The session
     */
    fun cancel(sessionId: String) {
        runWrite { repository.cancel(sessionId) }
    }

    /**
     * Run one interactive write, then reload.
     *
     * **No optimistic insert and no local queue** [TC-8, D-9, BR3.1].
     * The list reloads from the server rather than being patched here,
     * so what the screen shows is what the server holds.
     *
     * @param write The write to attempt
     */
    private fun runWrite(write: suspend () -> AuthResult<Unit>) {
        lastWrite = write
        _state.value = SessionsUiState.Loading
        viewModelScope.launch {
            when (val result = write()) {
                is AuthResult.Ok -> {
                    lastWrite = null
                    lastBatchId?.let { load(it, lastBatchName) }
                }
                is AuthResult.Refused ->
                    _state.value = SessionsStateMapper.afterError(result.envelope)
                AuthResult.TransportFailure ->
                    _state.value = SessionsStateMapper.afterTransportFailure()
            }
        }
    }

    /**
     * Repeat whatever last failed, and only when the user asks.
     *
     * A failed write is retried **as that write** rather than
     * degrading into a reload, which would drop the user's intent
     * silently and leave the session unchanged with nothing on screen
     * to say so.
     */
    fun retry() {
        val write = lastWrite
        if (write != null) {
            runWrite(write)
            return
        }
        lastBatchId?.let { load(it, lastBatchName) }
    }
}
