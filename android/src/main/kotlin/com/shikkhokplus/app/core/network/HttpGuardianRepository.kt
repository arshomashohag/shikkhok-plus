package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.guardian.GuardianRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get

/**
 * The guardian repository, over HTTP.
 *
 * **The guardian never names the child.** The route carries no
 * identifier at all: the server resolves the seats from the
 * authenticated account's own `guardian_account_id` [BR4.1,
 * NFR14.29]. A route that took a child id would let a guardian ask
 * about a child who is not theirs and rely on the server to refuse —
 * which works until one endpoint forgets, and is why the id is absent
 * from the request rather than checked in it.
 *
 * @property client The authenticated HTTP client
 */
class HttpGuardianRepository(
    private val client: HttpClient,
) : GuardianRepository {

    /**
     * List the seats this guardian was recorded on.
     *
     * @return The children, an error envelope, or a transport failure
     */
    override suspend fun children(): AuthResult<List<GuardianChildDto>> =
        call { client.get("/v1/guardian/children") }
}
