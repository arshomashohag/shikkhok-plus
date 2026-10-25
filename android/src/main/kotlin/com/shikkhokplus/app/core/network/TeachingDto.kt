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
 * @property attendanceRecorded Whether a roster has been submitted
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
    @SerialName("attendance_recorded") val attendanceRecorded: Boolean = false,
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
@Serializable
data class SessionDetailDto(
    val session: SessionDto,
    val seats: List<RosterSeatDto> = emptyList(),
    val writable: Boolean = true,
)

/**
 * The body of a queued attendance write [BR3.3, § B.8].
 *
 * **The version travels in the BODY, not an `If-Match` header.** A
 * queued write is serialized into the device's queue and replayed hours
 * later; a body field survives that naturally, where a header is a
 * second thing the queue must remember and the first thing a retry
 * wrapper drops.
 *
 * @property baseAttendanceVersion The version this roster was composed
 *   against
 * @property clientMutationId The replay key [BR3.8]. **Freshly
 *   generated for a re-apply** [BR3.7] — reusing one returns the
 *   original stored result with 200 and writes nothing
 * @property entries One entry per seat, written atomically [BR3.5]
 */
@Serializable
data class AttendanceWriteBody(
    @SerialName("base_attendance_version") val baseAttendanceVersion: Int,
    @SerialName("client_mutation_id") val clientMutationId: String,
    val entries: List<AttendanceEntryBody>,
)

/**
 * One seat in an attendance write.
 *
 * @property enrollmentId The seat
 * @property present Whether the student was there
 */
@Serializable
data class AttendanceEntryBody(
    @SerialName("enrollment_id") val enrollmentId: String,
    val present: Boolean,
)

/**
 * The body of a queued topic write [BR2.1].
 *
 * @property baseTopicVersion The version this write guards
 * @property clientMutationId The replay key
 * @property topic The topic text. May be empty — a deliberately blank
 *   topic is a logged topic [BR2.2] — but never null, because "do not
 *   write" is expressed by not sending the request
 */
@Serializable
data class TopicWriteBody(
    @SerialName("base_topic_version") val baseTopicVersion: Int,
    @SerialName("client_mutation_id") val clientMutationId: String,
    val topic: String,
)

/**
 * What the server returns when a queued write applies.
 *
 * **No `queue_state` field, here or anywhere** [BR3.9]. The states are
 * client-side vocabulary; the server cannot know whether an item is
 * queued on a device it has never heard from.
 *
 * @property attendanceVersion The version the server now holds, for an
 *   attendance write
 * @property topicVersion The version the server now holds, for a topic
 *   write
 */
@Serializable
data class WriteAppliedDto(
    @SerialName("attendance_version") val attendanceVersion: Int? = null,
    @SerialName("topic_version") val topicVersion: Int? = null,
)

/**
 * The detail a version conflict carries [BR3.10].
 *
 * **Reachable only after authorization.** A descriptive conflict code
 * returned before the lens check would be an existence oracle: a caller
 * probes session ids and reads the difference between "not yours" and
 * "yours but stale". The server refuses an unreachable session with the
 * shared `NOT_AVAILABLE` first, so this shape never reaches a stranger.
 *
 * That matters here specifically because `currentState` **is the
 * roster** — the detail that makes a mis-ordered refusal a disclosure
 * rather than a nuisance.
 *
 * @property expectedVersion What the refused write was composed against
 * @property currentVersion What the server holds now, which a re-apply
 *   composes against [BR3.7]
 * @property currentState The roster as it now stands, so the
 *   conflict-resolution screen can show it beside the teacher's own
 */
@Serializable
data class ConflictDetailDto(
    @SerialName("expected_version") val expectedVersion: Int,
    @SerialName("current_version") val currentVersion: Int,
    @SerialName("current_state") val currentState: List<RosterSeatDto> = emptyList(),
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
 * @property postedAt When it was posted, as the server formatted it
 * @property edited Whether it has been edited, **decided server-side**
 *   rather than inferred from an `edited_at` comparison
 */
@Serializable
data class AnnouncementDto(
    @SerialName("announcement_id") val announcementId: String,
    val body: String,
    @SerialName("posted_at") val postedAt: String,
    val edited: Boolean = false,
)
