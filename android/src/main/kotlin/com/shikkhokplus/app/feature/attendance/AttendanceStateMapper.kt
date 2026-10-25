package com.shikkhokplus.app.feature.attendance

import com.shikkhokplus.app.core.network.ConflictDetailDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RosterSeatDto
import com.shikkhokplus.app.core.network.SessionDetailDto
import com.shikkhokplus.app.core.queue.AttendanceEntry
import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueuedWrite

/**
 * Maps server responses and queue states to an [AttendanceUiState].
 *
 * **This object is the unit under test**, rather than "the ViewModel".
 * Pure: no network, no storage, no clock.
 *
 * It carries the two decisions this unit most needs to get right, and
 * both are here rather than in a composable so they are assertable
 * without a Compose test:
 *
 * * a queued write is **never** mapped to a confirmed state [BR3.1];
 * * a refusal becomes [AttendanceUiState.Conflicted] and **never**
 *   [AttendanceUiState.Failed] [BR3.6], because the two carry different
 *   remedies and a screen showing one for both leaves a teacher
 *   repeating a request that cannot succeed.
 */
object AttendanceStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be parsed. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /**
     * The server's code for a refused queued write [BR3.10].
     *
     * Reached only after the lens check, so it never reaches a caller
     * who cannot already see the session — which is what permits it to
     * be descriptive where `NOT_AVAILABLE` is deliberately not.
     */
    const val VERSION_CONFLICT_CODE: String = "ATTENDANCE_VERSION_CONFLICT"

    /**
     * String resource keys for the four queue states [BR3.2].
     *
     * **Four entries, one per state, resolved by an exhaustive `when`
     * rather than a map lookup** — so a fifth state added to
     * [QueueState] fails to compile here rather than rendering under
     * whichever branch happened to be the fallback. For a queue, that
     * fallback would be a claim about whether the server has the
     * teacher's roster.
     *
     * @param state The queue state
     * @return The string resource key naming it
     */
    fun queueLabelKey(state: QueueState): String = when (state) {
        QueueState.QUEUED -> "queue.state.queued"
        QueueState.CONFIRMED -> "queue.state.confirmed"
        QueueState.FAILED -> "queue.state.failed"
        QueueState.CONFLICTED -> "queue.state.conflicted"
    }

    /**
     * Map a session's roster, open for marking.
     *
     * **A seat with no recorded mark opens present** [AC3.1.4]. That is
     * a default, not a decision about the student: marking a class is
     * mostly confirming attendance, and it is one of the two structural
     * properties that stand in for the latency target BR7.4 removed.
     *
     * @param detail The session and its roster
     * @param queued This session's pending write, or null
     * @return The state the screen renders
     */
    fun afterLoad(
        detail: SessionDetailDto,
        queued: QueuedWrite? = null,
    ): AttendanceUiState {
        val badge =
            queued?.let {
                QueueBadge(
                    state = it.state,
                    labelKey = queueLabelKey(it.state),
                    itemId = it.id,
                )
            }

        return AttendanceUiState.Marking(
            sessionId = detail.session.sessionId,
            dateLabel = detail.session.date,
            // A queued write is what the teacher last recorded, so the
            // screen shows THEIR marks rather than the server's stale
            // ones. Preserving the offline entry is BR3.6's
            // requirement and it starts here, not at the conflict.
            seats = queued?.let { seatsFrom(detail.seats, it.entries) }
                ?: detail.seats.map(::toSeat),
            attendanceVersion = detail.session.attendanceVersion,
            // READ, never derived from `status == "cancelled"`. The
            // server refuses for two reasons -- a cancelled session
            // [BR1.6] and an inactive batch [BR5.5] -- and a client
            // testing only the first would offer a write the server
            // refuses.
            writable = detail.writable,
            queued = badge,
        )
    }

    /**
     * Overlay a queued write's marks onto the server's roster.
     *
     * The roster's membership stays the server's [BR1.5]; only the
     * presence booleans come from the queue. A seat the queue knows
     * about but the roster no longer holds is dropped, because the
     * teacher may not mark a seat that has left the batch.
     *
     * @param seats The server's roster
     * @param entries What the teacher recorded offline
     * @return The roster carrying the teacher's marks
     */
    private fun seatsFrom(
        seats: List<RosterSeatDto>,
        entries: List<AttendanceEntry>,
    ): List<AttendanceSeat> {
        val recorded = entries.associate { it.enrollmentId to it.present }
        return seats.map { seat ->
            AttendanceSeat(
                enrollmentId = seat.enrollmentId,
                displayName = seat.displayName,
                present = recorded[seat.enrollmentId] ?: (seat.present ?: true),
            )
        }
    }

    /**
     * Convert one seat the server returned.
     *
     * @param dto The seat
     * @return The seat as the screen renders it
     */
    private fun toSeat(dto: RosterSeatDto): AttendanceSeat =
        AttendanceSeat(
            enrollmentId = dto.enrollmentId,
            displayName = dto.displayName,
            // Null means no roster was ever submitted, which opens
            // present [AC3.1.4]. A recorded `false` is an absence the
            // teacher marked and is preserved.
            present = dto.present ?: true,
        )

    /**
     * Map an accepted write to the queued state [BR3.1].
     *
     * **[AttendanceUiState.Queued], never
     * [AttendanceUiState.Confirmed].** The write is on the phone and
     * the server does not have it; rendering a confirmation here is
     * precisely the silent-queue failure `project.md`'s NEVER protects
     * against, and this is the function where it would be introduced.
     *
     * @param item The write that was enqueued
     * @param dateLabel The session's date
     * @return The queued state
     */
    fun afterEnqueue(item: QueuedWrite, dateLabel: String): AttendanceUiState =
        AttendanceUiState.Queued(itemId = item.id, dateLabel = dateLabel)

    /**
     * Map a write the server applied.
     *
     * @param attendanceVersion The version the server now holds
     * @return The confirmed state
     */
    fun afterApplied(attendanceVersion: Int): AttendanceUiState =
        AttendanceUiState.Confirmed(attendanceVersion)

    /**
     * Map a refused write to the conflict screen [BR3.6].
     *
     * **This returns [AttendanceUiState.Conflicted] and never
     * [AttendanceUiState.Failed].** The distinction is the rule: a
     * failure invites a retry, and a retry of this request cannot
     * succeed because the version it carries is stale by definition.
     *
     * The teacher's offline entry is carried through as `mine` and the
     * server's as `theirs`, side by side, so the screen shows both and
     * decides neither. **Nothing is merged** — a merge would mean
     * inventing a rule for a student the two rosters disagree about.
     *
     * A refusal carrying a code other than
     * [VERSION_CONFLICT_CODE] falls through to [afterError] rather than
     * being rendered as a conflict: showing a conflict screen for an
     * inactive-batch refusal would offer a re-apply that cannot work.
     *
     * @param item The queued write that was refused
     * @param dateLabel The session's date
     * @param detail The conflict detail the server returned
     * @param envelope The refusal
     * @return The conflict state, or a failure for another code
     */
    fun afterConflict(
        item: QueuedWrite,
        dateLabel: String,
        detail: ConflictDetailDto,
        envelope: ErrorEnvelope,
    ): AttendanceUiState {
        if (envelope.error.code != VERSION_CONFLICT_CODE) {
            return afterError(envelope)
        }

        return AttendanceUiState.Conflicted(
            itemId = item.id,
            sessionId = item.sessionId,
            dateLabel = dateLabel,
            // **Preserved, not recomputed.** BR3.6 requires the
            // offline entry to survive until the teacher chooses, and
            // the queue item is where it survives.
            mine = item.entries.map { entry ->
                AttendanceSeat(
                    enrollmentId = entry.enrollmentId,
                    displayName = displayNameFor(entry.enrollmentId, detail),
                    present = entry.present,
                )
            },
            theirs = detail.currentState.map(::toSeat),
            currentVersion = detail.currentVersion,
            messageKey = envelope.error.messageKey,
        )
    }

    /**
     * The teacher-typed name for a seat, from the server's current
     * state.
     *
     * The queue holds no names — only enrollment ids, booleans and
     * UUIDs [security-design § 7.1] — so the conflict screen takes
     * names from the refusal's `current_state`, which is the roster the
     * server just sent. A seat the server no longer lists falls back to
     * its id rather than to a blank, so the row is still addressable.
     *
     * @param enrollmentId The seat
     * @param detail The conflict detail
     * @return The name, or the id when the server did not list it
     */
    private fun displayNameFor(
        enrollmentId: String,
        detail: ConflictDetailDto,
    ): String =
        detail.currentState
            .firstOrNull { it.enrollmentId == enrollmentId }
            ?.displayName
            ?: enrollmentId

    /**
     * Map a server error envelope.
     *
     * @param envelope The server's error
     * @param itemId The queue item it concerns, when one exists
     * @return The failure state
     */
    fun afterError(
        envelope: ErrorEnvelope,
        itemId: String? = null,
    ): AttendanceUiState =
        AttendanceUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
            itemId = itemId,
        )

    /**
     * Map a transport failure on a **read**.
     *
     * Reads are not queued [BR3.1]: only the two mid-class write paths
     * queue, and a queued read would be a cache this unit does not
     * build.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): AttendanceUiState =
        AttendanceUiState.Failed(OFFLINE_KEY, retryable = true)
}
