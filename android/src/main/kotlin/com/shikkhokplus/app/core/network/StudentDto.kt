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
 * @property charged What the period charged
 * @property verifying Whether a payment for it is being checked
 * @property paidOn The day it was last approved, `yyyy-MM-dd`, or null
 */
@Serializable
data class CurrentFeeDto(
    val period: String,
    val status: String,
    @SerialName("due_date") val dueDate: String,
    val outstanding: Money,
    val charged: Money? = null,
    val verifying: Boolean = false,
    @SerialName("paid_on") val paidOn: String? = null,
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
 * @property nextSession This batch's next class, or null
 * @property isNext Whether that is the student's next class across every batch
 * @property lastResult The latest marked result, or null
 */
@Serializable
data class StudentBatchDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("teacher_display_name") val teacherDisplayName: String? = null,
    val subjects: List<String> = emptyList(),
    val schedule: List<ScheduleSlotDto> = emptyList(),
    @SerialName("current_fee") val currentFee: CurrentFeeDto? = null,
    @SerialName("next_session") val nextSession: UpcomingSessionDto? = null,
    @SerialName("is_next") val isNext: Boolean = false,
    @SerialName("last_result") val lastResult: LastResultDto? = null,
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
 * @property subjectName What the class taught, or null
 */
@Serializable
data class AttendanceEntryDto(
    @SerialName("session_id") val sessionId: String,
    val date: String,
    @SerialName("start_time") val startTime: String,
    val present: Boolean? = null,
    val topic: String? = null,
    @SerialName("topic_logged") val topicLogged: Boolean = false,
    @SerialName("subject_name") val subjectName: String? = null,
)

/**
 * One batch from the family's side: next class, past classes, notices (S2).
 *
 * @property nextSessionDate The next class's date, or null
 * @property nextSessionStartTime Its start, or null
 * @property pastSessions Classes held, newest first as the server orders
 * @property announcements The batch's notices
 * @property servedAt When the server produced this
 * @property nextSession The next class, or null
 * @property followingSessions The classes after it
 * @property upcomingExam The next exam to sit, or null
 */
@Serializable
data class FamilyBatchViewDto(
    @SerialName("next_session_date") val nextSessionDate: String? = null,
    @SerialName("next_session_start_time") val nextSessionStartTime: String? = null,
    @SerialName("past_sessions") val pastSessions: List<AttendanceEntryDto> = emptyList(),
    val announcements: List<AnnouncementDto> = emptyList(),
    @SerialName("served_at") val servedAt: String,
    @SerialName("next_session") val nextSession: UpcomingSessionDto? = null,
    @SerialName("following_sessions") val followingSessions: List<UpcomingSessionDto> = emptyList(),
    @SerialName("upcoming_exam") val upcomingExam: UpcomingExamDto? = null,
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

/**
 * A class still to come, with the server's comparisons made.
 *
 * @property date Its date
 * @property startTime When it starts
 * @property endTime When it ends, or null
 * @property startsInMinutes Minutes until it starts when that is today, else null
 * @property moved Whether the teacher moved it from its usual time
 * @property subjectName What it teaches, or null
 */
@Serializable
data class UpcomingSessionDto(
    val date: String,
    @SerialName("start_time") val startTime: String,
    @SerialName("end_time") val endTime: String? = null,
    @SerialName("starts_in_minutes") val startsInMinutes: Int? = null,
    val moved: Boolean = false,
    @SerialName("subject_name") val subjectName: String? = null,
)

/**
 * The latest marked result on a seat ("Last test 44/50 · rank 5").
 *
 * @property title The exam
 * @property marks The mark
 * @property totalMarks Out of how many
 * @property rank The rank, only where the marksheet publishes it
 */
@Serializable
data class LastResultDto(
    val title: String,
    val marks: Int,
    @SerialName("total_marks") val totalMarks: Int,
    val rank: Int? = null,
)

/**
 * The next exam to sit ("Coming up").
 *
 * @property title The exam
 * @property date When
 * @property totalMarks Out of how many
 * @property subjectName Which subject
 */
@Serializable
data class UpcomingExamDto(
    val title: String,
    val date: String,
    @SerialName("total_marks") val totalMarks: Int,
    @SerialName("subject_name") val subjectName: String,
)
