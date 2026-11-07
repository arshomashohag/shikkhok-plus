package com.shikkhokplus.app.feature.timetable

import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.RoomDto
import com.shikkhokplus.app.core.network.TimetableClassDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the centre timetable and its rooms need from the network. */
interface TimetableRepository {
    /**
     * Read the chosen centre's classes between two days.
     *
     * @param from The first day, `yyyy-MM-dd`
     * @param to The last day; at most 31 days after [from]
     * @return The classes, a refusal, or a transport failure
     */
    suspend fun timetable(from: String, to: String): AuthResult<List<TimetableClassDto>>

    /**
     * Read the centre's members, for the teacher picker.
     *
     * @return The members, a refusal, or a transport failure
     */
    suspend fun members(): AuthResult<List<MemberDto>>

    /**
     * Read the centre's rooms, archived included.
     *
     * @return The rooms, a refusal, or a transport failure
     */
    suspend fun rooms(): AuthResult<List<RoomDto>>

    /**
     * Give one class a teacher and a room, apart from its weekly slot.
     *
     * @param sessionId The class
     * @param teacherMemberId The teacher, or null for nobody yet
     * @param roomId The room, or null for none
     * @return The class, a refusal (a clash names the other class), or a transport failure
     */
    suspend fun assign(sessionId: String, teacherMemberId: String?, roomId: String?): AuthResult<TimetableClassDto>

    /**
     * Swap two classes' teachers, in one step.
     *
     * @param first One class
     * @param second The other
     * @return Both classes, a refusal, or a transport failure
     */
    suspend fun swap(first: String, second: String): AuthResult<List<TimetableClassDto>>

    /**
     * Add a room.
     *
     * @param name Its name
     * @return The room, a refusal, or a transport failure
     */
    suspend fun addRoom(name: String): AuthResult<RoomDto>

    /**
     * Stop or resume using a room.
     *
     * @param roomId The room
     * @param archived Whether it is no longer in use
     * @return The room, a refusal, or a transport failure
     */
    suspend fun archiveRoom(roomId: String, archived: Boolean): AuthResult<RoomDto>
}
