package com.shikkhokplus.app.feature.myclasses

import com.shikkhokplus.app.core.network.ClassAttendanceBodyDto
import com.shikkhokplus.app.core.network.ClassAttendanceResultDto
import com.shikkhokplus.app.core.network.ClassRosterDto
import com.shikkhokplus.app.core.network.ClassTopicBodyDto
import com.shikkhokplus.app.core.network.ClassTopicResultDto
import com.shikkhokplus.app.core.network.MyClassDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What a centre teacher's classes need from the network. */
interface MyClassesRepository {
    /**
     * Read my classes between two days, across every centre.
     *
     * @param from The first day, `yyyy-MM-dd`
     * @param to The last day; at most 31 days after [from]
     * @return The classes, a refusal, or a transport failure
     */
    suspend fun classes(from: String, to: String): AuthResult<List<MyClassDto>>

    /**
     * Read one class's roster and topic.
     *
     * @param sessionId The class
     * @return The roster, a refusal, or a transport failure
     */
    suspend fun roster(sessionId: String): AuthResult<ClassRosterDto>

    /**
     * Take attendance for the whole roster.
     *
     * @param sessionId The class
     * @param body The version, replay key and marks
     * @return The new version, a refusal, or a transport failure
     */
    suspend fun submitAttendance(sessionId: String, body: ClassAttendanceBodyDto): AuthResult<ClassAttendanceResultDto>

    /**
     * Write what was taught.
     *
     * @param sessionId The class
     * @param body The version, replay key and topic
     * @return The new version, a refusal, or a transport failure
     */
    suspend fun writeTopic(sessionId: String, body: ClassTopicBodyDto): AuthResult<ClassTopicResultDto>
}
