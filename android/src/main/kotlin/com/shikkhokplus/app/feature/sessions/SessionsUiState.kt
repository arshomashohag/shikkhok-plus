package com.shikkhokplus.app.feature.sessions

/**
 * One session as the list renders it.
 *
 * **Every field here is a decision the mapper already made**, which is
 * the whole reason the type exists: a composable writing
 * `if (session.date < today)` would be comparing a domain value to
 * choose a control, and that is the slip this project corrected on
 * `InvitationCard` in D1 and has guarded against since.
 *
 * @property sessionId The session
 * @property dateLabel The date, as the server formatted it
 * @property timeLabel The start time, as the server formatted it
 * @property subjectName Which subject, or null for a single-subject
 *   batch
 * @property statusLabel A string resource key for the session's status,
 *   chosen from the server's enum [BR1.6]
 * @property isCancelled Whether to mark this row, **decided by the
 *   mapper** from the server's status rather than compared in the
 *   screen
 * @property isAdHoc Whether this was created by hand rather than
 *   generated [BR1.4]
 * @property topicLogged Whether a topic was written at all [BR2.2].
 *
 *   **Read, never derived from [topic] being null.** Null is a topic
 *   never written and an empty string is one deliberately saved blank,
 *   and a client null-check collapses exactly the two cases BR2.2
 *   exists to keep apart — making it impossible to tell a class nobody
 *   logged from one logged as nothing
 * @property topic The topic text, or null when never written
 * @property attendanceRecorded Whether a roster has been submitted
 * @property attendanceVersion The version a roster write composes
 *   against [BR3.3]
 * @property topicVersion The version a topic write composes against
 */
data class SessionRow(
    val sessionId: String,
    val dateLabel: String,
    val timeLabel: String,
    val subjectName: String?,
    val statusLabel: String,
    val isCancelled: Boolean,
    val isAdHoc: Boolean,
    val topicLogged: Boolean,
    val topic: String?,
    val attendanceRecorded: Boolean,
    val attendanceVersion: Int,
    val topicVersion: Int,
)

/**
 * Everything the session list renders.
 *
 * The states are the ones `team.md` requires every ViewModel to ship
 * tests for: loading, success, error, and the explicit retry path for a
 * failed write [TC-8, D-9].
 */
sealed interface SessionsUiState {
    /** Nothing has been asked for yet. */
    data object Idle : SessionsUiState

    /** A request is in flight. */
    data object Loading : SessionsUiState

    /**
     * The sessions loaded.
     *
     * @property batchName Which class
     * @property rows The sessions, in the order the server returned
     *   them. **Never sorted here** — ordering is a server decision
     *   [TC-9]
     */
    data class Loaded(
        val batchName: String,
        val rows: List<SessionRow>,
    ) : SessionsUiState

    /**
     * The batch exists and has no sessions yet.
     *
     * A separate state rather than a success with no rows, because an
     * empty list and "no classes scheduled yet" need different screens
     * and a blank list explains neither.
     *
     * @property batchName Which class
     */
    data class Empty(val batchName: String) : SessionsUiState

    /**
     * Something failed, and the screen can say what to do about it.
     *
     * @property messageKey Names a string resource; never English text
     *   from the server, which the client could not localize
     *   [TC-15, D-43]
     * @property retryable Read from the server's envelope, never
     *   inferred from a status code [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : SessionsUiState
}
