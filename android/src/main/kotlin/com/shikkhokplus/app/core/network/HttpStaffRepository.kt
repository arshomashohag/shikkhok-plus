package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.staff.StaffRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * The chosen centre's Teachers & staff console, over HTTP. Manager-only:
 * the server refuses anyone else, and a solo workspace has no staff.
 *
 * @property client The authenticated HTTP client
 */
class HttpStaffRepository(
    private val client: HttpClient,
) : StaffRepository {

    override suspend fun list(): AuthResult<List<StaffDto>> = call { client.get("/v1/centre/staff") }

    override suspend fun inviteTeacher(body: StaffBodyDto): AuthResult<StaffDto> =
        call { client.post("/v1/centre/staff/teachers") { setBody(body.copy(roleLabel = null)) } }

    override suspend fun addOther(body: StaffBodyDto): AuthResult<StaffDto> =
        call { client.post("/v1/centre/staff") { setBody(body) } }

    override suspend fun update(staffId: String, body: StaffBodyDto): AuthResult<StaffDto> =
        call { client.patch("/v1/centre/staff/$staffId") { setBody(body.copy(phone = null)) } }

    override suspend fun leave(staffId: String, leftOn: String?): AuthResult<StaffDto> =
        call { client.post("/v1/centre/staff/$staffId/leave") { setBody(StaffLeaveDto(leftOn)) } }
}
