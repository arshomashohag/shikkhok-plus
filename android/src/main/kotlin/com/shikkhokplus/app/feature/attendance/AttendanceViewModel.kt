package com.shikkhokplus.app.feature.attendance

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.ConflictDetailDto
import com.shikkhokplus.app.core.network.SessionDetailDto
import com.shikkhokplus.app.core.queue.AttendanceEntry
import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueueTarget
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.sessions.SessionsRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** How an attendance write reaches the server [BR3.3]. */
interface AttendanceRepository {
    /**
     * Submit one roster.
     *
     * The version and the mutation id travel in the **body**, not a
     * header [§ B.8]: a queued write is serialized and replayed hours
     * later, and a body field survives that where a header is the first
     * thing a retry wrapper drops.
     *
     * @param item The queued write to send
     * @return What the server said
     */
    suspend fun submit(item: QueuedWrite): SendOutcome

    /**
     * Read the conflict detail the server returned with a refusal.
     *
     * @param sessionId The session in dispute
     * @return The current version and roster
     */
    suspend fun conflictDetail(sessionId: String): AuthResult<ConflictDetailDto>
}

/**
 * Holds the attendance screens' state. Holds no business logic
 * [TC-9, D-31].
 *
 * Every mapping decision is delegated to [AttendanceStateMapper], which
 * is the unit the tests target. This class owns the coroutine, the
 * state holder and the queue, and nothing else.
 *
 * **This is the one surface in the app that accepts a write without
 * connectivity**, and the two mid-class paths are the only ones
 * [BR3.1, NFR5]. Every other write in the product still refuses offline
 * with an explicit retry prompt.
 *
 * Three properties of that queue are enforced here rather than
 * described:
 *
 * * an enqueued write maps to [AttendanceUiState.Queued] and **never**
 *   to [AttendanceUiState.Confirmed] [BR3.1];
 * * a refusal maps to [AttendanceUiState.Conflicted] and **never** to
 *   [AttendanceUiState.Failed], and schedules **no** automatic retry
 *   [BR3.6];
 * * [reapply] composes a **new** write with the current version and a
 *   **fresh** mutation id [BR3.7].
 *
 * @property repository How a roster reaches the server
 * @property sessions Where a session's roster is read from
 * @property store Where the queue lives
 */
class AttendanceViewModel(
    private val repository: AttendanceRepository,
    private val sessions: SessionsRepository,
    private val store: QueueStore,
) : ViewModel() {

    private val _state = MutableStateFlow<AttendanceUiState>(AttendanceUiState.Idle)

    /** What the screen renders. */
    val state: StateFlow<AttendanceUiState> = _state.asStateFlow()

    private var detail: SessionDetailDto? = null

    /**
     * Open a session for marking.
     *
     * The queue is consulted as well as the server: an item pending for
     * this session means the teacher's own marks are the ones to show,
     * and its state is what the badge renders.
     *
     * @param sessionId The session to mark
     */
    fun load(sessionId: String) {
        _state.value = AttendanceUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = sessions.sessionDetail(sessionId)) {
                    is AuthResult.Ok -> {
                        detail = result.value
                        AttendanceStateMapper.afterLoad(
                            result.value,
                            pendingFor(sessionId),
                        )
                    }
                    is AuthResult.Refused ->
                        AttendanceStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        AttendanceStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Record one seat's mark, on the device only [BR3.5].
     *
     * **Nothing is sent here.** The teacher marks a whole roster and
     * commits it once: the write is one item covering every seat, so
     * a per-toggle send would be the per-seat queue [BR3.5] forbids,
     * and mid-class it would be a request per tap on a phone that may
     * have no signal.
     *
     * Ignored outside [AttendanceUiState.Marking] and when the server
     * said the session is not writable — the screen hides the control
     * then, and refusing again here keeps a stale recomposition from
     * editing a roster that cannot be sent [BR1.6, BR5.5].
     *
     * @param seat The seat whose mark changed
     * @param present Whether they are now marked present
     */
    fun toggle(seat: AttendanceSeat, present: Boolean) {
        val marking = _state.value as? AttendanceUiState.Marking ?: return
        if (!marking.writable) return
        _state.value =
            marking.copy(
                seats =
                    marking.seats.map {
                        if (it.enrollmentId == seat.enrollmentId) {
                            it.copy(present = present)
                        } else {
                            it
                        }
                    },
            )
    }

    /**
     * Accept a roster, queue it, and try to send it [BR3.1, BR3.5].
     *
     * **The write is queued first and sent second**, which is the order
     * that makes the guarantee: a process death between the two leaves
     * the roster on the device rather than losing it. The whole roster
     * goes as one item, never one write per seat [BR3.5] — a per-seat
     * queue leaves attendance half-saved after a mid-roster drop, and a
     * retry cannot reconcile that on screen.
     *
     * @param sessionId The session
     * @param baseVersion The version the roster was composed against
     * @param seats The roster as the teacher marked it
     */
    fun submit(
        sessionId: String,
        baseVersion: Int,
        seats: List<AttendanceSeat>,
    ) {
        val item =
            QueuedWrite.attendance(
                sessionId = sessionId,
                baseVersion = baseVersion,
                entries = seats.map { AttendanceEntry(it.enrollmentId, it.present) },
            )
        store.enqueue(item)

        // **Queued, not confirmed.** The server does not have this yet,
        // and saying otherwise is the silent-queue failure that
        // `project.md`'s NEVER protects against [BR3.1].
        _state.value =
            AttendanceStateMapper.afterEnqueue(
                item,
                detail?.session?.date.orEmpty(),
            )

        viewModelScope.launch { send(item) }
    }

    /**
     * Try to send one queued item, mapping whatever comes back.
     *
     * @param item The item to send
     */
    private suspend fun send(item: QueuedWrite) {
        when (val outcome = repository.submit(item)) {
            is SendOutcome.Applied -> {
                store.remove(item.id)
                _state.value = AttendanceStateMapper.afterApplied(outcome.resultingVersion)
            }

            is SendOutcome.Conflicted -> {
                // **Conflicted, and no automatic retry** [BR3.6]. The
                // offline entry stays in the queue until the teacher
                // re-applies or discards it; nothing is merged and
                // nothing is silently dropped.
                val conflicted =
                    item.copy(
                        state = QueueState.CONFLICTED,
                        conflictCurrentVersion = outcome.currentVersion,
                    )
                store.replace(conflicted)
                _state.value =
                    AttendanceStateMapper.afterConflict(
                        item = conflicted,
                        dateLabel = detail?.session?.date.orEmpty(),
                        detail =
                            ConflictDetailDto(
                                expectedVersion = item.baseVersion,
                                currentVersion = outcome.currentVersion,
                                currentState = emptyList(),
                            ),
                        envelope = outcome.envelope,
                    )
                refreshConflictDetail(conflicted, outcome)
            }

            is SendOutcome.Failed -> {
                store.replace(item.failed(outcome.envelope))
                _state.value =
                    outcome.envelope
                        ?.let { AttendanceStateMapper.afterError(it, item.id) }
                        ?: AttendanceUiState.Failed(
                            AttendanceStateMapper.OFFLINE_KEY,
                            retryable = true,
                            itemId = item.id,
                        )
            }
        }
    }

    /**
     * Fetch the roster the server now holds, for the conflict screen.
     *
     * The refusal already carries `current_state` on the wire; this
     * second read is the fallback for a transport that did not surface
     * it. A failure here leaves the conflict state standing with an
     * empty `theirs` rather than replacing it with an error — the
     * teacher's own entry is the thing that must not be lost, and it is
     * in the queue regardless.
     *
     * @param item The conflicted item
     * @param outcome What the server said
     */
    private suspend fun refreshConflictDetail(
        item: QueuedWrite,
        outcome: SendOutcome.Conflicted,
    ) {
        val fetched = repository.conflictDetail(item.sessionId)
        if (fetched is AuthResult.Ok) {
            _state.value =
                AttendanceStateMapper.afterConflict(
                    item = item,
                    dateLabel = detail?.session?.date.orEmpty(),
                    detail = fetched.value,
                    envelope = outcome.envelope,
                )
        }
    }

    /**
     * Re-apply a conflicted write as a NEW write [BR3.7].
     *
     * **The fresh `client_mutation_id` is the whole point.** The
     * obvious implementation resends the queued item unchanged; that id
     * carries a unique constraint, so the server would take the replay
     * path, return the ORIGINAL stored result with 200 and write
     * nothing — reporting success for the exact opposite of what the
     * teacher asked. [QueuedWrite.reapplied] composes the new id and
     * the current version together, and refuses to produce an item that
     * reuses the old id.
     *
     * @param itemId The conflicted item the teacher chose to re-apply
     */
    fun reapply(itemId: String) {
        val existing = store.read().firstOrNull { it.id == itemId } ?: return
        if (existing.state != QueueState.CONFLICTED) return

        val fresh = existing.reapplied()
        store.write(store.read().map { if (it.id == itemId) fresh else it })

        _state.value =
            AttendanceStateMapper.afterEnqueue(fresh, detail?.session?.date.orEmpty())
        viewModelScope.launch { send(fresh) }
    }

    /**
     * Discard a conflicted write, keeping what the server holds
     * [BR3.6].
     *
     * The other half of the teacher's explicit choice. Runs only when
     * they ask: nothing is ever silently discarded.
     *
     * @param itemId The item to drop
     */
    fun discard(itemId: String) {
        store.remove(itemId)
        detail?.let { load(it.session.sessionId) }
    }

    /**
     * Retry a failed write, and only when the user asks [TC-8, D-9].
     *
     * **Applies to [QueueState.FAILED] only.** A conflicted item is
     * deliberately unreachable from here: retrying it as-is is
     * guaranteed to be refused again, and the control that looks like
     * this one is the one that acquires a version-stripping wrapper.
     * Re-applying is [reapply], which composes a new write.
     *
     * @param itemId The failed item to send again
     */
    fun retry(itemId: String) {
        val item = store.read().firstOrNull { it.id == itemId } ?: return
        if (item.state != QueueState.FAILED) return

        val requeued = item.copy(state = QueueState.QUEUED)
        store.replace(requeued)
        _state.value =
            AttendanceStateMapper.afterEnqueue(requeued, detail?.session?.date.orEmpty())
        viewModelScope.launch { send(requeued) }
    }

    /**
     * The attendance write pending for one session, if any.
     *
     * @param sessionId The session
     * @return The queued item, or null
     */
    private fun pendingFor(sessionId: String): QueuedWrite? =
        store.read().firstOrNull {
            it.sessionId == sessionId && it.target == QueueTarget.ATTENDANCE
        }
}
