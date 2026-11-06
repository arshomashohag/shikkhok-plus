package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.centres.CentresRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * Coaching centres, their members and their offers, over HTTP.
 *
 * The centre a manager acts on is the chosen workspace, sent by the
 * client as `X-Workspace-Id`; the server refuses a workspace the account
 * does not manage.
 *
 * @property client The authenticated HTTP client
 */
class HttpCentresRepository(
    private val client: HttpClient,
) : CentresRepository {

    override suspend fun open(name: String, managerName: String): AuthResult<CentreDto> =
        call { client.post("/v1/centres") { setBody(CentreCreateDto(name, managerName)) } }

    override suspend fun members(): AuthResult<List<MemberDto>> = call { client.get("/v1/centre/members") }

    override suspend fun invite(displayName: String, phone: String, role: String): AuthResult<MemberDto> =
        call { client.post("/v1/centre/members") { setBody(MemberInviteDto(displayName, phone, role)) } }

    override suspend fun revoke(memberId: String): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/centre/members/$memberId/revoke") }

    override suspend fun offers(): AuthResult<List<MembershipDto>> = call { client.get("/v1/memberships") }

    override suspend fun accept(memberId: String): AuthResult<MembershipDecisionDto> =
        call { client.post("/v1/memberships/$memberId/accept") }

    override suspend fun decline(memberId: String): AuthResult<MembershipDecisionDto> =
        call { client.post("/v1/memberships/$memberId/decline") }
}
