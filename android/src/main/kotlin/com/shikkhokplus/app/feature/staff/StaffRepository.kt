package com.shikkhokplus.app.feature.staff

import com.shikkhokplus.app.core.network.StaffBodyDto
import com.shikkhokplus.app.core.network.StaffDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the Teachers & staff console needs from the network. */
interface StaffRepository {
    /**
     * List the chosen centre's teachers and staff.
     *
     * @return The records, a refusal, or a transport failure
     */
    suspend fun list(): AuthResult<List<StaffDto>>

    /**
     * Invite a teacher: their record and a pending app invitation, together.
     *
     * @param body Their details; the phone is required
     * @return The record, a refusal, or a transport failure
     */
    suspend fun inviteTeacher(body: StaffBodyDto): AuthResult<StaffDto>

    /**
     * Add someone who works here but does not use the app.
     *
     * @param body Their details
     * @return The record, a refusal, or a transport failure
     */
    suspend fun addOther(body: StaffBodyDto): AuthResult<StaffDto>

    /**
     * Correct a record's details.
     *
     * @param staffId The record
     * @param body The details as they now read
     * @return The record, a refusal, or a transport failure
     */
    suspend fun update(staffId: String, body: StaffBodyDto): AuthResult<StaffDto>

    /**
     * Mark someone as left; any app access ends in the same step.
     *
     * @param staffId The record
     * @param leftOn Their last day, or null for today
     * @return The record, a refusal, or a transport failure
     */
    suspend fun leave(staffId: String, leftOn: String?): AuthResult<StaffDto>
}
