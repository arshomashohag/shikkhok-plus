package com.shikkhokplus.app.feature.attendance

import com.shikkhokplus.app.core.queue.QueueState

/**
 * One seat as the marking screen renders it.
 *
 * @property enrollmentId The seat
 * @property displayName The teacher-typed name
 * @property present Whether the teacher has this seat marked present.
 *
 *   **Defaults to present on a fresh roster** [AC3.1.4], which is one
 *   of the two structural properties standing in for the dropped
 *   latency target [BR7.4]: marking a class is mostly confirming
 *   attendance, so the roster opens in the state that needs the fewest
 *   taps
 */
data class AttendanceSeat(
    val enrollmentId: String,
    val displayName: String,
    val present: Boolean,
)

/**
 * How a queued write shows on screen [BR3.1, BR3.2].
 *
 * **Four labels for four states, and never three.** AC3.1.10 requires
 * `failed` and `conflicted` to be visually distinct, and BR3.1's
 * violation_behaviour (a) requires `queued` never to render as
 * confirmed. Mapping the states to labels here — rather than in a
 * composable — is what makes both assertable without a Compose test.
 *
 * @property state Which of the four
 * @property labelKey A string resource key naming it
 * @property itemId The device-local queue item, so a control can
 *   address this specific write
 */
data class QueueBadge(
    val state: QueueState,
    val labelKey: String,
    val itemId: String,
)

/**
 * Everything the attendance screens render.
 */
sealed interface AttendanceUiState {
    /** Nothing has been asked for yet. */
    data object Idle : AttendanceUiState

    /** A request is in flight. */
    data object Loading : AttendanceUiState

    /**
     * The roster is open for marking.
     *
     * @property sessionId The session being marked
     * @property dateLabel The session's date, as the server formatted it
     * @property seats The roster [BR1.5], in the server's order
     * @property attendanceVersion The version a submit composes against
     *   [BR3.3]
     * @property writable Whether a write would be accepted, **decided
     *   server-side** [BR1.6, BR5.5]. A cancelled session and an
     *   inactive batch both refuse, and the client is told rather than
     *   testing the status itself
     * @property queued The badge for this session's queued write, or
     *   null when nothing is pending.
     *
     *   **Never rendered as confirmed while present** [BR3.1]: a queued
     *   item means the server does not have this roster, and a screen
     *   that showed a tick would be the silent queue `project.md`
     *   forbids
     */
    data class Marking(
        val sessionId: String,
        val dateLabel: String,
        val seats: List<AttendanceSeat>,
        val attendanceVersion: Int,
        val writable: Boolean,
        val queued: QueueBadge? = null,
    ) : AttendanceUiState

    /**
     * The server refused a queued write; the teacher must decide
     * [BR3.6].
     *
     * **Not a [Failed].** `failed` means "try again", and retrying a
     * conflict as-is is guaranteed to be refused again — the version it
     * carries is stale by definition. Worse, a retry affordance invites
     * a wrapper that strips the version, which would overwrite the
     * correction somebody else made.
     *
     * **Nothing is merged and nothing is discarded** until the teacher
     * says so. Merging would mean inventing a rule for a student the
     * two rosters disagree about, which is a business decision a sync
     * layer must not make.
     *
     * @property itemId The conflicted queue item
     * @property sessionId The session in dispute
     * @property dateLabel The session's date
     * @property mine What the teacher recorded offline, preserved
     * @property theirs What the record now says, from the refusal's
     *   `current_state`
     * @property currentVersion The version a re-apply composes against
     *   [BR3.7]
     * @property messageKey Names the refusal's string resource
     */
    data class Conflicted(
        val itemId: String,
        val sessionId: String,
        val dateLabel: String,
        val mine: List<AttendanceSeat>,
        val theirs: List<AttendanceSeat>,
        val currentVersion: Int,
        val messageKey: String,
    ) : AttendanceUiState

    /**
     * The write is on the phone and not yet on the server [BR3.1].
     *
     * A distinct state rather than a success with a badge, so the
     * screen cannot render it as a confirmation by omission.
     *
     * @property itemId The queued item
     * @property dateLabel The session's date
     */
    data class Queued(
        val itemId: String,
        val dateLabel: String,
    ) : AttendanceUiState

    /**
     * The server has it.
     *
     * @property attendanceVersion The version the server now holds
     */
    data class Confirmed(val attendanceVersion: Int) : AttendanceUiState

    /**
     * Something failed, and retrying is the right remedy.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     * @property itemId The queue item that failed, when one exists
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
        val itemId: String? = null,
    ) : AttendanceUiState
}
