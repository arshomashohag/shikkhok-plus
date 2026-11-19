package com.shikkhokplus.app.feature.hubreviews

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * The review routes in memory: each call is recorded, and answered with
 * the next queued result for its route, the last one repeating.
 */
internal class FakeReviewsApi :
    ReviewerApi,
    OwnerReviewsApi {

    /** Every call, as `METHOD path body`. */
    val calls = mutableListOf<String>()

    var reviewable: List<AuthResult<List<ReviewableBatch>>> = listOf(AuthResult.Ok(emptyList()))
    var reads: List<AuthResult<MyReviewResponse>> = emptyList()
    var saves: List<AuthResult<MyReviewResponse>> = emptyList()
    var deletes: List<AuthResult<Unit>> = listOf(AuthResult.Ok(Unit))
    var owner: List<AuthResult<OwnerReviewsResponse>> = emptyList()
    var replies: List<AuthResult<OwnerReview>> = emptyList()
    var replyDeletes: List<AuthResult<Unit>> = listOf(AuthResult.Ok(Unit))

    private val counts = mutableMapOf<String, Int>()

    private fun <T> next(route: String, queue: List<AuthResult<T>>): AuthResult<T> {
        val n = counts.getOrDefault(route, 0)
        counts[route] = n + 1
        return queue[minOf(n, queue.size - 1)]
    }

    override suspend fun reviewable(): AuthResult<List<ReviewableBatch>> {
        calls += "GET reviewable"
        return next("reviewable", reviewable)
    }

    override suspend fun myReview(batchId: String): AuthResult<MyReviewResponse> {
        calls += "GET $batchId"
        return next("read", reads)
    }

    override suspend fun saveMyReview(batchId: String, body: ReviewWrite): AuthResult<MyReviewResponse> {
        calls += "PUT $batchId ${body.rating} ${body.body}"
        return next("save", saves)
    }

    override suspend fun deleteMyReview(batchId: String): AuthResult<Unit> {
        calls += "DELETE $batchId"
        return next("delete", deletes)
    }

    override suspend fun ownerReviews(): AuthResult<OwnerReviewsResponse> {
        calls += "GET owner"
        return next("owner", owner)
    }

    override suspend fun saveReply(reviewId: String, body: ReplyWrite): AuthResult<OwnerReview> {
        calls += "PUT reply $reviewId ${body.body}"
        return next("reply", replies)
    }

    override suspend fun deleteReply(reviewId: String): AuthResult<Unit> {
        calls += "DELETE reply $reviewId"
        return next("replyDelete", replyDeletes)
    }
}

/** A refusal as the server sends it. */
internal fun refused(
    code: String,
    key: String,
    retryable: Boolean = false,
    details: Map<String, String>? = null,
): AuthResult<Nothing> = AuthResult.Refused(ErrorEnvelope(ErrorBody(code, retryable, key, details)))

/** The switch is off. */
internal val reviewsOff: AuthResult<Nothing> = refused("HUB_REVIEWS_OFF", "hub.review.off")

/** A guardian who may write a first review. */
internal val eligible =
    MyReviewResponse(standing = "eligible", canWrite = true)

/** A guardian's own review, as its author reads it. */
internal fun mine(
    rating: Int = 4,
    body: String? = "Clear teaching",
    status: String = "pending",
    canWrite: Boolean = true,
    editUntil: String? = "2026-12-19",
    reply: String? = null,
    code: String? = null,
) = MyReviewResponse(
    standing = "eligible",
    canWrite = canWrite,
    editUntil = editUntil,
    review =
        MyReviewBody(
            rating = rating,
            body = body,
            status = status,
            rejectionCode = code,
            tenure = "lt_6m",
            replyBody = reply,
        ),
)

/** One published review of the owner's batch. */
internal fun ownerReview(
    id: String = "r-1",
    myReplyStatus: String? = null,
    myReplyBody: String? = null,
) = OwnerReview(
    id = id,
    batchId = "b-1",
    rating = 5,
    body = "Patient with questions",
    tenure = "6_12m",
    publishedMonth = "2026-11",
    myReplyStatus = myReplyStatus,
    myReplyBody = myReplyBody,
)
