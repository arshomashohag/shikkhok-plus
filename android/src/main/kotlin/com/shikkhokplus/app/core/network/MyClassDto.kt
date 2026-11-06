package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One class a centre assigned to me, from `GET /v1/me/classes`.
 *
 * @property sessionId The class
 * @property centreName The centre it belongs to
 * @property batchName Its batch's name
 * @property subject The subject, or null
 * @property date The day, `yyyy-MM-dd`
 * @property startTime When it starts, `HH:mm`
 * @property endTime When it ends, or null
 * @property status `scheduled`, `held` or `cancelled`
 * @property roomName Where, or null
 * @property topicLogged Whether what was taught has been written
 */
@Serializable
data class MyClassDto(
    @SerialName("session_id") val sessionId: String,
    @SerialName("centre_name") val centreName: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("subject") val subject: String? = null,
    @SerialName("date") val date: String,
    @SerialName("start_time") val startTime: String,
    @SerialName("end_time") val endTime: String? = null,
    @SerialName("status") val status: String,
    @SerialName("room_name") val roomName: String? = null,
    @SerialName("topic_logged") val topicLogged: Boolean = false,
) {
    /** Whether the class was cancelled. */
    val cancelled: Boolean get() = status == "cancelled"
}

/**
 * One assigned class's roster: names and marks only, never a phone,
 * guardian or fee, because the server's schema carries none.
 *
 * @property seats Every seat, with its recorded mark
 * @property attendanceVersion The version a write is based on
 * @property writable Whether a write would be accepted, decided by the server
 * @property topic What was taught, or null
 * @property topicVersion The version a topic write is based on
 */
@Serializable
data class ClassRosterDto(
    @SerialName("seats") val seats: List<RosterSeatDto> = emptyList(),
    @SerialName("attendance_version") val attendanceVersion: Int,
    @SerialName("writable") val writable: Boolean,
    @SerialName("topic") val topic: String? = null,
    @SerialName("topic_version") val topicVersion: Int,
)

/**
 * One seat's mark in an attendance write.
 *
 * @property enrollmentId The seat
 * @property present Whether they came
 */
@Serializable
data class ClassSeatMarkDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("present") val present: Boolean,
)

/**
 * The body of `POST /v1/me/classes/{id}/attendance`: the whole roster at once.
 *
 * @property baseAttendanceVersion The version the marks were taken against
 * @property clientMutationId The replay key, kept across a retry
 * @property seats Every seat's mark
 */
@Serializable
data class ClassAttendanceBodyDto(
    @SerialName("base_attendance_version") val baseAttendanceVersion: Int,
    @SerialName("client_mutation_id") val clientMutationId: String,
    @SerialName("seats") val seats: List<ClassSeatMarkDto>,
)

/**
 * The body of `PUT /v1/me/classes/{id}/topic`: what was taught, not a plan.
 *
 * @property baseTopicVersion The version the topic was written against
 * @property clientMutationId The replay key
 * @property topic What was taught
 * @property plan Always false: a centre teacher logs, not plans
 */
@Serializable
data class ClassTopicBodyDto(
    @SerialName("base_topic_version") val baseTopicVersion: Int,
    @SerialName("client_mutation_id") val clientMutationId: String,
    @SerialName("topic") val topic: String,
    @SerialName("plan") val plan: Boolean,
)

/**
 * What an attendance write answers.
 *
 * @property attendanceVersion The version now in force
 */
@Serializable
data class ClassAttendanceResultDto(@SerialName("attendance_version") val attendanceVersion: Int)

/**
 * What a topic write answers.
 *
 * @property topicVersion The version now in force
 */
@Serializable
data class ClassTopicResultDto(@SerialName("topic_version") val topicVersion: Int)
