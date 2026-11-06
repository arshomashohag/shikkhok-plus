package com.shikkhokplus.app.feature.centres

import com.shikkhokplus.app.core.network.CentreDto
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.MembershipDecisionDto
import com.shikkhokplus.app.core.network.MembershipDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the coaching-centre screens need from the network. */
interface CentresRepository {
    /**
     * Open a coaching centre; the signed-in account becomes its first manager.
     *
     * @param name The centre's name
     * @param managerName The opener's name as the centre shows it
     * @return The centre, a refusal, or a transport failure
     */
    suspend fun open(name: String, managerName: String): AuthResult<CentreDto>

    /**
     * List the chosen centre's members, for one of its managers.
     *
     * @return The members, a refusal, or a transport failure
     */
    suspend fun members(): AuthResult<List<MemberDto>>

    /**
     * Invite someone to the chosen centre by phone.
     *
     * @param displayName Their name
     * @param phone Their number
     * @param role `manager` or `teacher`
     * @return The pending member, a refusal, or a transport failure
     */
    suspend fun invite(displayName: String, phone: String, role: String): AuthResult<MemberDto>

    /**
     * Remove a member; the last manager cannot be removed.
     *
     * @param memberId The membership
     * @return Nothing, a refusal, or a transport failure
     */
    suspend fun revoke(memberId: String): AuthResult<Unit>

    /**
     * List the centres' offers to the signed-in account.
     *
     * @return The offers, a refusal, or a transport failure
     */
    suspend fun offers(): AuthResult<List<MembershipDto>>

    /**
     * Accept an offer.
     *
     * @param memberId The membership
     * @return The decision, a refusal, or a transport failure
     */
    suspend fun accept(memberId: String): AuthResult<MembershipDecisionDto>

    /**
     * Decline an offer.
     *
     * @param memberId The membership
     * @return The decision, a refusal, or a transport failure
     */
    suspend fun decline(memberId: String): AuthResult<MembershipDecisionDto>
}
