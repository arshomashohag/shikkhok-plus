package com.shikkhokplus.app.feature.hublisting

import com.shikkhokplus.app.core.network.call
import com.shikkhokplus.app.core.network.callDiscardingBody
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.encodeURLPathPart

/** What the name-consent screen needs from the network. */
interface NameConsentApi {
    /**
     * List the caller's accepted centre memberships and their name consent.
     *
     * @return The memberships, a refusal, or a transport failure
     */
    suspend fun centreMemberships(): AuthResult<List<CentreMembership>>

    /**
     * Agree, or stop agreeing, to be named on a centre's public page.
     *
     * @param centreId The centre
     * @param consent True to be named
     * @return Nothing, a refusal, or a transport failure
     */
    suspend fun setNameConsent(centreId: String, consent: Boolean): AuthResult<Unit>
}

/** What the owner's public-listing screens need from the network. */
interface HubApi : NameConsentApi {
    /**
     * Read the owner's listing, which the server drafts on the first call.
     *
     * @return The listing, a refusal, or a transport failure
     */
    suspend fun listing(): AuthResult<OwnerListingResponse>

    /**
     * Edit the owner's listing.
     *
     * @param body The changed fields
     * @return The listing after the edit, a refusal, or a transport failure
     */
    suspend fun save(body: OwnerListingUpdateRequest): AuthResult<OwnerListingResponse>

    /**
     * Agree to the listing terms and publish.
     *
     * @param consentVersion The version the server named in its last answer
     * @return The published listing, a refusal, or a transport failure
     */
    suspend fun publish(consentVersion: String): AuthResult<OwnerListingResponse>

    /**
     * Hide the listing; the text is kept.
     *
     * @return The listing, a refusal, or a transport failure
     */
    suspend fun unpublish(): AuthResult<OwnerListingResponse>

    /**
     * Ask whether a slug is free.
     *
     * @param slug The wanted slug
     * @return The answer, a refusal, or a transport failure
     */
    suspend fun slugAvailable(slug: String): AuthResult<SlugAvailability>

    /**
     * List the divisions, or the areas directly inside one.
     *
     * @param parent The enclosing area's code, or null for the divisions
     * @return The areas, a refusal, or a transport failure
     */
    suspend fun areas(parent: String?): AuthResult<List<AreaOption>>

    /**
     * List the owner's active batches with their listing state.
     *
     * @return The batches, a refusal, or a transport failure
     */
    suspend fun batchListings(): AuthResult<List<BatchListingResponse>>

    /**
     * Create or edit one batch's listing.
     *
     * @param batchId The batch
     * @param body The changed fields
     * @return The batch, a refusal, or a transport failure
     */
    suspend fun saveBatch(batchId: String, body: BatchListingUpdateRequest): AuthResult<BatchListingResponse>

    /**
     * Make one batch's listing public.
     *
     * @param batchId The batch
     * @return The batch, a refusal, or a transport failure
     */
    suspend fun publishBatch(batchId: String): AuthResult<BatchListingResponse>

    /**
     * Hide one batch's listing.
     *
     * @param batchId The batch
     * @return The batch, a refusal, or a transport failure
     */
    suspend fun unpublishBatch(batchId: String): AuthResult<BatchListingResponse>
}

/**
 * The public-listing screens' network, over HTTP.
 *
 * The server owns every rule and answers a refusal with its one error
 * envelope; nothing here checks a field beyond sending it.
 *
 * @property client The authenticated HTTP client
 */
class HttpHubApi(
    private val client: HttpClient,
) : HubApi {

    override suspend fun listing(): AuthResult<OwnerListingResponse> = call { client.get("/v1/hub/listing") }

    override suspend fun save(body: OwnerListingUpdateRequest): AuthResult<OwnerListingResponse> =
        call { client.put("/v1/hub/listing") { setBody(body) } }

    override suspend fun publish(consentVersion: String): AuthResult<OwnerListingResponse> =
        call { client.post("/v1/hub/listing/publish") { setBody(PublishRequest(consentVersion)) } }

    override suspend fun unpublish(): AuthResult<OwnerListingResponse> =
        call { client.post("/v1/hub/listing/unpublish") }

    override suspend fun slugAvailable(slug: String): AuthResult<SlugAvailability> =
        call { client.get("/v1/hub/slugs/${slug.encodeURLPathPart()}") }

    override suspend fun areas(parent: String?): AuthResult<List<AreaOption>> =
        call { client.get("/v1/hub/areas") { parameter("parent", parent) } }

    override suspend fun batchListings(): AuthResult<List<BatchListingResponse>> =
        call { client.get("/v1/hub/batch-listings") }

    override suspend fun saveBatch(batchId: String, body: BatchListingUpdateRequest): AuthResult<BatchListingResponse> =
        call { client.put("/v1/batches/$batchId/listing") { setBody(body) } }

    override suspend fun publishBatch(batchId: String): AuthResult<BatchListingResponse> =
        call { client.post("/v1/batches/$batchId/listing/publish") }

    override suspend fun unpublishBatch(batchId: String): AuthResult<BatchListingResponse> =
        call { client.post("/v1/batches/$batchId/listing/unpublish") }

    override suspend fun centreMemberships(): AuthResult<List<CentreMembership>> =
        call { client.get("/v1/me/centre-memberships") }

    override suspend fun setNameConsent(centreId: String, consent: Boolean): AuthResult<Unit> =
        callDiscardingBody {
            client.put("/v1/centres/$centreId/members/me/public-name-consent") { setBody(ConsentRequest(consent)) }
        }
}
