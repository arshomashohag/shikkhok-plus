package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One session as the teacher's list shows it.
 *
 * **`status` and `topicLogged` arrive decided** [TC-9, D-31]. The
 * client never compares `date` against today to decide whether a class
 * has happened, and never tests `topic != null` to decide whether it
 * was logged — both are server decisions, and the second is BR2.2's
 * whole point: null is a topic never written and an empty string is one
 * deliberately saved blank, so a client null-check would collapse the
 * two the rule exists to keep apart.
 *
 * @property sessionId The session
 * @property date The date, as the server formatted it
 * @property startTime The start time, as the server formatted it
 * @property subjectName Which subject, or null for a batch with one
 * @property origin `recurrence` or `ad_hoc` [BR1.4]
 * @property status `scheduled`, `held` or `cancelled` [BR1.6]
 * @property topic The topic text; null means never written [BR2.2]
 * @property topicLogged Whether a topic was written at all, **decided
 *   server-side** [BR2.2]. Carried separately from [topic] precisely so
 *   logged-and-blank is distinguishable from never-logged
 * @property attendanceVersion The version a roster write must be
 *   composed against [BR3.3]
 * @property topicVersion The version a topic write guards [BR2.1]
 */
@Serializable
data class SessionDto(
    @SerialName("session_id") val sessionId: String,
    val date: String,
    @SerialName("start_time") val startTime: String,
    @SerialName("subject_name") val subjectName: String? = null,
    val origin: String,
    val status: String,
    val topic: String? = null,
    @SerialName("topic_logged") val topicLogged: Boolean = false,
    @SerialName("attendance_version") val attendanceVersion: Int = 0,
    @SerialName("topic_version") val topicVersion: Int = 0,
)

/**
 * One seat on a session's roster [BR1.5].
 *
 * **Membership is the server's** — the four-clause predicate over
 * `inactive_from`, `student_decision` and `joined_on` runs in one
 * indexed query there, and a client filtering this list would be
 * reimplementing it against data it does not hold.
 *
 * **No profile field and no account id** [BR5.3]. A roster is the most
 * natural place in the product to leak a student's self-authored name
 * to a teacher, because it is a list of people. What arrives is the
 * teacher's own typed name and the enrollment id.
 *
 * @property enrollmentId The teacher-facing key
 * @property displayName The teacher-typed name
 * @property present The recorded mark, or null when not yet recorded.
 *
 *   **Null is not absent.** A fresh roster arrives with every seat
 *   defaulted present [AC3.1.4]; null here means no roster has been
 *   submitted for this session at all
 */
@Serializable
data class RosterSeatDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
    val present: Boolean? = null,
)

/**
 * A session with its roster, for the marking screen.
 *
 * **Not a wire shape.** The repository composes it from two reads,
 * `GET /v1/sessions/{id}` and `GET /v1/sessions/{id}/attendance`,
 * because the server keeps the session and its roster on separate
 * paths. An earlier version decoded this from the first path alone,
 * which carries neither `seats` nor `writable`, so the marking screen
 * could never load.
 *
 * @property session The session being marked
 * @property seats The roster [BR1.5]
 * @property writable Whether a roster write would be accepted,
 *   **decided server-side** [BR1.6, BR5.5].
 *
 *   A cancelled session and an inactive batch both refuse, and the
 *   client is told rather than testing `status == "cancelled"` itself —
 *   which would be right today and wrong the moment a third refusing
 *   condition appears on the server
 */
data class SessionDetailDto(
    val session: SessionDto,
    val seats: List<RosterSeatDto> = emptyList(),
    val writable: Boolean = true,
)

/**
 * What a version conflict looks like to the resolution screen [BR3.10].
 *
 * **Not a wire shape.** Built from the refused write and a re-read of
 * `GET /v1/sessions/{id}/attendance`: the 409's own details carry the
 * roster as a flat string meant for logs, not for rendering.
 *
 * @property expectedVersion What the refused write was composed against
 * @property currentVersion What the server holds now, which a re-apply
 *   composes against [BR3.7]
 * @property currentState The roster as it now stands, so the
 *   conflict-resolution screen can show it beside the teacher's own
 */
data class ConflictDetailDto(
    val expectedVersion: Int,
    val currentVersion: Int,
    val currentState: List<RosterSeatDto> = emptyList(),
)

/**
 * One announcement [BR7.1].
 *
 * **No expiry field, and that is an assertion rather than an
 * omission.** An announcement never expires: no job and no column
 * removes it on the passage of time, because a silently expiring
 * announcement is a message the teacher believes was delivered.
 *
 * @property announcementId The announcement
 * @property body The text
 * @property postedAt When it was posted, as the server formatted it.
 *   The wire name is `created_at`: this was `posted_at`, which the
 *   server never sent, and nothing caught it until the contract gate
 * @property edited Whether it has been edited, **decided server-side**
 *   rather than inferred from an `edited_at` comparison
 */
@Serializable
data class AnnouncementDto(
    @SerialName("announcement_id") val announcementId: String,
    val body: String,
    @SerialName("created_at") val postedAt: String,
    val edited: Boolean = false,
)
