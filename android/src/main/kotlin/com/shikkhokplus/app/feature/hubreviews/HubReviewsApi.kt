package com.shikkhokplus.app.feature.hubreviews

import com.shikkhokplus.app.core.network.call
import com.shikkhokplus.app.core.network.callDiscardingBody
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.encodeURLPathPart

/**
 * What a guardian's review screens need from the network. The reviewer
 * lens is resolved by the server from the batch in the path; nothing
 * here says who may review.
 */
interface ReviewerApi {
    /**
     * List the batches the caller may review, is waiting to, or has reviewed.
     *
     * @return The rows, a refusal, or a transport failure
     */
    suspend fun reviewable(): AuthResult<List<ReviewableBatch>>

    /**
     * Read where the caller stands with one batch's review.
     *
     * @param batchId The batch
     * @return The state, a refusal, or a transport failure
     */
    suspend fun myReview(batchId: String): AuthResult<MyReviewResponse>

    /**
     * Write the caller's review, or edit it; it goes back to moderation.
     *
     * @param batchId The batch
     * @param body The rating and the optional words
     * @return The state after the write, a refusal, or a transport failure
     */
    suspend fun saveMyReview(batchId: String, body: ReviewWrite): AuthResult<MyReviewResponse>

    /**
     * Delete the caller's review completely; never gated by the switch.
     *
     * @param batchId The batch
     * @return Nothing, a refusal, or a transport failure
     */
    suspend fun deleteMyReview(batchId: String): AuthResult<Unit>
}

/** What the owner's Reviews screen needs from the network. */
interface OwnerReviewsApi {
    /**
     * Read the owner's batches' ratings and their published reviews.
     *
     * @return The page, a refusal (`HUB_REVIEWS_OFF` while switched off), or a transport failure
     */
    suspend fun ownerReviews(): AuthResult<OwnerReviewsResponse>

    /**
     * Write or replace the owner's reply to a review; it is pre-moderated.
     *
     * @param reviewId The review
     * @param body The reply
     * @return The review with the reply as it now stands, a refusal, or a transport failure
     */
    suspend fun saveReply(reviewId: String, body: ReplyWrite): AuthResult<OwnerReview>

    /**
     * Delete the owner's reply to a review; never gated by the switch.
     *
     * @param reviewId The review
     * @return Nothing, a refusal, or a transport failure
     */
    suspend fun deleteReply(reviewId: String): AuthResult<Unit>
}

/**
 * The review routes over HTTP [H4].
 *
 * The server owns every rule and answers a refusal with its one error
 * envelope; nothing here checks a field beyond sending it.
 *
 * @property client The authenticated HTTP client
 */
class HttpHubReviewsApi(
    private val client: HttpClient,
) : ReviewerApi,
    OwnerReviewsApi {

    override suspend fun reviewable(): AuthResult<List<ReviewableBatch>> = call { client.get("/v1/hub/reviewable") }

    override suspend fun myReview(batchId: String): AuthResult<MyReviewResponse> =
        call { client.get(mine(batchId)) }

    override suspend fun saveMyReview(batchId: String, body: ReviewWrite): AuthResult<MyReviewResponse> =
        call { client.put(mine(batchId)) { setBody(body) } }

    override suspend fun deleteMyReview(batchId: String): AuthResult<Unit> =
        callDiscardingBody { client.delete(mine(batchId)) }

    override suspend fun ownerReviews(): AuthResult<OwnerReviewsResponse> = call { client.get("/v1/hub/reviews") }

    override suspend fun saveReply(reviewId: String, body: ReplyWrite): AuthResult<OwnerReview> =
        call { client.put(reply(reviewId)) { setBody(body) } }

    override suspend fun deleteReply(reviewId: String): AuthResult<Unit> =
        callDiscardingBody { client.delete(reply(reviewId)) }

    private fun mine(batchId: String): String = "/v1/hub/batches/${batchId.encodeURLPathPart()}/my-review"

    private fun reply(reviewId: String): String = "/v1/hub/reviews/${reviewId.encodeURLPathPart()}/reply"
}
