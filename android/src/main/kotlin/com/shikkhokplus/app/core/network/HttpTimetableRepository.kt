package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.timetable.TimetableRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * The chosen centre's timetable, rooms, per-class changes and swaps, over
 * HTTP. Manager-only; the server refuses a teacher or room that clashes.
 *
 * @property client The authenticated HTTP client
 */
class HttpTimetableRepository(
    private val client: HttpClient,
) : TimetableRepository {

    override suspend fun timetable(from: String, to: String): AuthResult<List<TimetableClassDto>> =
        call {
            client.get("/v1/centre/timetable") {
                parameter("from", from)
                parameter("to", to)
            }
        }

    override suspend fun members(): AuthResult<List<MemberDto>> = HttpCentresRepository(client).members()

    override suspend fun rooms(): AuthResult<List<RoomDto>> = call { client.get("/v1/centre/rooms") }

    override suspend fun assign(
        sessionId: String,
        teacherMemberId: String?,
        roomId: String?,
    ): AuthResult<TimetableClassDto> =
        call {
            // **Both fields, null included**: null clears the teacher or
            // the room, and the app's JSON omits nulls, so the body is
            // built here rather than serialized.
            client.post("/v1/sessions/$sessionId/assignment") {
                setBody(
                    buildJsonObject {
                        put("teacher_member_id", teacherMemberId?.let(::JsonPrimitive) ?: JsonNull)
                        put("room_id", roomId?.let(::JsonPrimitive) ?: JsonNull)
                    },
                )
            }
        }

    override suspend fun swap(first: String, second: String): AuthResult<List<TimetableClassDto>> =
        call { client.post("/v1/centre/sessions/swap") { setBody(SwapDto(first, second)) } }

    override suspend fun addRoom(name: String): AuthResult<RoomDto> =
        call { client.post("/v1/centre/rooms") { setBody(RoomCreateDto(name)) } }

    override suspend fun archiveRoom(roomId: String, archived: Boolean): AuthResult<RoomDto> =
        call { client.patch("/v1/centre/rooms/$roomId") { setBody(RoomUpdateDto(archived = archived)) } }
}
