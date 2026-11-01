package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One class on a calendar day, as the server sends it.
 *
 * `state` and `mark` stay strings so a value this build has never
 * heard of decodes instead of failing the whole month [D-26]; the
 * mapper decides what to do with it.
 *
 * @property sessionId The class
 * @property date `YYYY-MM-DD`
 * @property startTime `HH:MM:SS`
 * @property endTime `HH:MM:SS`, when the class has one
 * @property subjectName The subject, when set
 * @property state `taken`, `today`, `upcoming`, `not_recorded` or `cancelled`
 * @property topic The planned topic, if any
 * @property notes The teacher's notes, if any
 * @property plannable Whether the viewer may plan this class
 * @property recordable Whether the viewer may record this class
 * @property mark `present`, `absent`, `not_marked` or `not_enrolled`, for a student view
 * @property topicVersion The topic log's version, which a topic write composes against
 * @property attendanceVersion The roster's version
 */
@Serializable
data class CalendarClassDto(
    @SerialName("session_id") val sessionId: String,
    val date: String,
    @SerialName("start_time") val startTime: String,
    @SerialName("end_time") val endTime: String? = null,
    @SerialName("subject_name") val subjectName: String? = null,
    val state: String,
    val topic: String? = null,
    val notes: String? = null,
    val plannable: Boolean = false,
    val recordable: Boolean = false,
    val mark: String? = null,
    @SerialName("topic_version") val topicVersion: Int = 0,
    @SerialName("attendance_version") val attendanceVersion: Int = 0,
)

/**
 * One day that has at least one class.
 *
 * @property date `YYYY-MM-DD`
 * @property state The day's state, decided by the server
 * @property classes The classes that day
 */
@Serializable
data class CalendarDayDto(
    val date: String,
    val state: String,
    val classes: List<CalendarClassDto> = emptyList(),
)

/**
 * A month of classes, as every calendar endpoint answers.
 *
 * @property year The month's year
 * @property month The month, 1 to 12
 * @property firstMonth Earliest month worth showing, `YYYY-MM`
 * @property lastMonth Latest month worth showing, `YYYY-MM`
 * @property servedAt When the server built it
 * @property days Only the days that have a class
 * @property today Bangladesh's date when the server built it, `YYYY-MM-DD`
 */
@Serializable
data class MonthViewDto(
    val year: Int,
    val month: Int,
    @SerialName("first_month") val firstMonth: String,
    @SerialName("last_month") val lastMonth: String,
    @SerialName("served_at") val servedAt: String? = null,
    val days: List<CalendarDayDto> = emptyList(),
    val today: String? = null,
)
