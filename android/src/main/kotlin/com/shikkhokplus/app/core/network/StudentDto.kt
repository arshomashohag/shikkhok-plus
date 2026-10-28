package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A seat's latest fee period, as a student sees it on S1.
 *
 * The status is the server's [TC-9]: the app renders it and decides
 * nothing from the amount.
 *
 * @property period `YYYY-MM`
 * @property status `paid`, `partly_paid`, `unpaid` or `waived`
 * @property dueDate When it is due, as the server formatted it
 * @property outstanding What is still owed for it
 */
@Serializable
data class CurrentFeeDto(
    val period: String,
    val status: String,
    @SerialName("due_date") val dueDate: String,
    val outstanding: Money,
)

/**
 * One batch a student has accepted a seat in (S1).
 *
 * @property enrollmentId Their seat; every other student read takes it
 * @property batchName The batch
 * @property teacherDisplayName What the teacher is called, or null
 * @property subjects The subjects taught
 * @property schedule The weekly classes
 * @property currentFee The latest fee period, or null before the first
 */
@Serializable
data class StudentBatchDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("teacher_display_name") val teacherDisplayName: String? = null,
    val subjects: List<String> = emptyList(),
    val schedule: List<ScheduleSlotDto> = emptyList(),
    @SerialName("current_fee") val currentFee: CurrentFeeDto? = null,
)

/**
 * One past class, as a student or guardian sees it.
 *
 * @property sessionId The class
 * @property date Its date
 * @property startTime When it started
 * @property present Whether this seat was marked present, or null if
 *   attendance was not taken
 * @property topic What was covered, or null
 * @property topicLogged Whether the teacher recorded a topic
 */
@Serializable
data class AttendanceEntryDto(
    @SerialName("session_id") val sessionId: String,
    val date: String,
    @SerialName("start_time") val startTime: String,
    val present: Boolean? = null,
    val topic: String? = null,
    @SerialName("topic_logged") val topicLogged: Boolean = false,
)

/**
 * One batch from the family's side: next class, past classes, notices (S2).
 *
 * @property nextSessionDate The next class's date, or null
 * @property nextSessionStartTime Its start, or null
 * @property pastSessions Classes held, newest first as the server orders
 * @property announcements The batch's notices
 * @property servedAt When the server produced this
 */
@Serializable
data class FamilyBatchViewDto(
    @SerialName("next_session_date") val nextSessionDate: String? = null,
    @SerialName("next_session_start_time") val nextSessionStartTime: String? = null,
    @SerialName("past_sessions") val pastSessions: List<AttendanceEntryDto> = emptyList(),
    val announcements: List<AnnouncementDto> = emptyList(),
    @SerialName("served_at") val servedAt: String,
)

/**
 * A session's roster with its version, from `GET /v1/sessions/{id}/attendance`.
 *
 * What the attendance screen marks, and what a conflict compares against.
 *
 * @property seats One entry per seat
 * @property attendanceVersion The version a submission composes against
 * @property writable Whether a roster write would be accepted now,
 *   decided by the server's own write refusals [BR1.6, BR5.5]
 */
@Serializable
data class SessionRosterDto(
    val seats: List<RosterSeatDto> = emptyList(),
    @SerialName("attendance_version") val attendanceVersion: Int,
    val writable: Boolean,
)
