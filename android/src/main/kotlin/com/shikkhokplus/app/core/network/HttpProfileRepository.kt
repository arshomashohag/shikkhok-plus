package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.profile.ProfileRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.patch
import io.ktor.client.request.setBody

/**
 * The profile repository, over HTTP.
 *
 * **Both routes are `/v1/me` and name no account.** The row is keyed
 * on the authenticated id, so there is no field through which a
 * caller could reach somebody else's profile — and row-level security
 * is the second bound beneath that, admitting only the owner's row
 * [TC-13, D-7].
 *
 * @property client The authenticated HTTP client
 */
class HttpProfileRepository(
    private val client: HttpClient,
) : ProfileRepository {

    /**
     * Read this person's own name and address.
     *
     * @return The profile, a refusal, or a transport failure
     */
    override suspend fun profile(): AuthResult<MeDto> =
        call { client.get("/v1/me") }

    /**
     * Save an edited name and address.
     *
     * @param selfName The new name, or null to leave it alone
     * @param address The new address, or null to leave it alone
     * @return The updated profile, or why the server refused
     */
    override suspend fun save(
        selfName: String?,
        address: String?,
    ): AuthResult<MeDto> =
        call {
            client.patch("/v1/me") {
                setBody(ProfileUpdateDto(selfName = selfName, address = address))
            }
        }

    /**
     * Delete this account [TC-19].
     *
     * The access token is the ownership proof; the server runs the same
     * deletion function the web route runs, so the two paths cannot
     * remove different things [BR3.1].
     *
     * @return Nothing on success, or why the server refused
     */
    override suspend fun deleteAccount(): AuthResult<Unit> =
        callDiscardingBody { client.delete("/v1/me") }
}
