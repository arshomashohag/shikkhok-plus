package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One class on a centre's timetable, with its teacher and room.
 *
 * @property sessionId The class
 * @property batchId Its batch
 * @property batchName The batch's name
 * @property subject The subject, or null
 * @property date The day, `yyyy-MM-dd`
 * @property startTime When it starts, `HH:mm`
 * @property endTime When it ends, or null
 * @property status `scheduled`, `held` or `cancelled`
 * @property teacherMemberId Who teaches it, or null while unassigned
 * @property teacherName Their name, or null
 * @property roomId Where, or null
 * @property roomName The room's name, or null
 * @property overridden Whether this class was changed apart from its weekly slot
 */
@Serializable
data class TimetableClassDto(
    @SerialName("session_id") val sessionId: String,
    @SerialName("batch_id") val batchId: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("subject") val subject: String? = null,
    @SerialName("date") val date: String,
    @SerialName("start_time") val startTime: String,
    @SerialName("end_time") val endTime: String? = null,
    @SerialName("status") val status: String,
    @SerialName("teacher_member_id") val teacherMemberId: String? = null,
    @SerialName("teacher_name") val teacherName: String? = null,
    @SerialName("room_id") val roomId: String? = null,
    @SerialName("room_name") val roomName: String? = null,
    @SerialName("overridden") val overridden: Boolean = false,
) {
    /** Whether the class was cancelled. */
    val cancelled: Boolean get() = status == "cancelled"
}

/**
 * One of a centre's rooms; an archived one is kept for the record.
 *
 * @property roomId The room
 * @property name Its name
 * @property archived Whether it is no longer in use
 */
@Serializable
data class RoomDto(
    @SerialName("room_id") val roomId: String,
    @SerialName("name") val name: String,
    @SerialName("archived") val archived: Boolean = false,
)

/**
 * The body of `POST /v1/centre/rooms`.
 *
 * @property name The room's name
 */
@Serializable
data class RoomCreateDto(@SerialName("name") val name: String)

/**
 * The body of `PATCH /v1/centre/rooms/{id}`: rename, or stop or resume using it.
 *
 * @property name A new name, or null to keep it
 * @property archived Whether it is no longer in use, or null to keep it
 */
@Serializable
data class RoomUpdateDto(
    @SerialName("name") val name: String? = null,
    @SerialName("archived") val archived: Boolean? = null,
)

/**
 * The body of `POST /v1/centre/sessions/swap`.
 *
 * @property firstSessionId One class
 * @property secondSessionId The other
 */
@Serializable
data class SwapDto(
    @SerialName("first_session_id") val firstSessionId: String,
    @SerialName("second_session_id") val secondSessionId: String,
)
