package com.shikkhokplus.app.feature.hubenquiry

import com.shikkhokplus.app.core.network.call
import com.shikkhokplus.app.core.network.callDiscardingBody
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.encodeURLPathPart

/**
 * What a guardian's join-request screens need from the network. These act
 * as the signed-in account alone, whatever the lens; the list and the
 * withdrawal are never switched off, so a request sent before the switch
 * went off can still be withdrawn.
 */
interface EnquirerApi {
    /**
     * Read who a request would reach, and what "share" would share.
     *
     * @param ownerSlug The owner's public slug
     * @param batchId The batch asked about, or null for the owner
     * @return The target, a refusal (`HUB_ENQUIRIES_OFF`, `ENQUIRY_TARGET_NOT_FOUND`), or a transport failure
     */
    suspend fun target(ownerSlug: String, batchId: String?): AuthResult<EnquiryTarget>

    /**
     * Send a request; the declaration is checked by the server and not stored.
     *
     * @param ownerSlug The owner's public slug
     * @param body The request
     * @return The request as sent, a refusal, or a transport failure
     */
    suspend fun send(ownerSlug: String, body: EnquiryWrite): AuthResult<MyEnquiry>

    /**
     * List the caller's own requests, newest first.
     *
     * @return The rows, a refusal, or a transport failure
     */
    suspend fun mine(): AuthResult<List<MyEnquiry>>

    /**
     * Withdraw one of the caller's requests: it is deleted completely.
     *
     * @param enquiryId The request
     * @return Nothing, a refusal, or a transport failure
     */
    suspend fun withdraw(enquiryId: String): AuthResult<Unit>
}

/** What the owner's join-request screens need; the server resolves the teacher lens of the workspace. */
interface OwnerEnquiriesApi {
    /**
     * List the owner's requests, open first, as the server orders them.
     *
     * @return The rows, a refusal (`HUB_ENQUIRIES_OFF` while switched off), or a transport failure
     */
    suspend fun inbox(): AuthResult<List<OwnerEnquiry>>

    /**
     * Read one request.
     *
     * @param enquiryId The request
     * @return The request, a refusal, or a transport failure
     */
    suspend fun read(enquiryId: String): AuthResult<OwnerEnquiry>

    /**
     * Answer a request with one of its `outcomes_allowed`.
     *
     * @param enquiryId The request
     * @param outcome The answer
     * @return The request as answered, a refusal, or a transport failure
     */
    suspend fun close(enquiryId: String, outcome: EnquiryOutcome): AuthResult<OwnerEnquiry>
}

/**
 * The join-request routes over HTTP [H5].
 *
 * The server owns every rule and answers a refusal with its one error
 * envelope; nothing here checks a field beyond sending it.
 *
 * @property client The authenticated HTTP client
 */
class HttpHubEnquiryApi(
    private val client: HttpClient,
) : EnquirerApi,
    OwnerEnquiriesApi {

    override suspend fun target(ownerSlug: String, batchId: String?): AuthResult<EnquiryTarget> =
        call { client.get("${owner(ownerSlug)}/enquiry-target") { batchId?.let { parameter("batch_id", it) } } }

    override suspend fun send(ownerSlug: String, body: EnquiryWrite): AuthResult<MyEnquiry> =
        call { client.post("${owner(ownerSlug)}/enquiries") { setBody(body) } }

    override suspend fun mine(): AuthResult<List<MyEnquiry>> = call { client.get(MINE) }

    override suspend fun withdraw(enquiryId: String): AuthResult<Unit> =
        callDiscardingBody { client.delete("$MINE/${enquiryId.encodeURLPathPart()}") }

    override suspend fun inbox(): AuthResult<List<OwnerEnquiry>> = call { client.get(INBOX) }

    override suspend fun read(enquiryId: String): AuthResult<OwnerEnquiry> =
        call { client.get("$INBOX/${enquiryId.encodeURLPathPart()}") }

    override suspend fun close(enquiryId: String, outcome: EnquiryOutcome): AuthResult<OwnerEnquiry> =
        call {
            client.post("$INBOX/${enquiryId.encodeURLPathPart()}/close") { setBody(EnquiryClose(outcome.wire)) }
        }

    private fun owner(slug: String): String = "/v1/hub/owners/${slug.encodeURLPathPart()}"

    private companion object {
        const val MINE = "/v1/me/hub/enquiries"
        const val INBOX = "/v1/hub/enquiries"
    }
}
