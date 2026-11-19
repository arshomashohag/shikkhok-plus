package com.shikkhokplus.app.feature.hubreviews

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.HUB_OFFLINE_KEY
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/*
 * Guardian reviews on the wire, and the closed tables that word them [H4].
 *
 * **Nothing here decides anything the server owns.** Eligibility is
 * `standing` and `can_write`, the edit window is `edit_until`, a status
 * is `status`, a reason is `rejection_code`, and an average is
 * `average_label`, already rendered. Below three published reviews a
 * batch's figures arrive as nulls [T2-a], and the rating is a whole
 * number: no `Float` or `Double` appears here, and `average_tenths` is
 * not read at all [F13, T6-a].
 */

/** The longest review or reply the server accepts, once stripped. */
const val REVIEW_TEXT_MAX: Int = 1000

/** The highest rating; the lowest is 1. */
const val RATING_MAX: Int = 5

/** The code every switch-gated review route answers with while reviews are off. */
internal const val HUB_REVIEWS_OFF: String = "HUB_REVIEWS_OFF"

/**
 * One batch the guardian may review, is waiting to, or has reviewed.
 *
 * @property batchId The batch
 * @property batchTitle Its public title
 * @property ownerPublicName Its owner's public name
 * @property state `eligible`, `not_yet` or `reviewed`
 * @property eligibleFrom The day a `not_yet` guardian's tenure is met, or null
 */
@Serializable
data class ReviewableBatch(
    @SerialName("batch_id") val batchId: String,
    @SerialName("batch_title") val batchTitle: String,
    @SerialName("owner_public_name") val ownerPublicName: String,
    @SerialName("state") val state: String,
    @SerialName("eligible_from") val eligibleFrom: String? = null,
)

/**
 * The guardian's own review, as its author sees it.
 *
 * @property rating 1 to 5
 * @property body The words, or null
 * @property status Where it is in moderation
 * @property rejectionCode Why it was rejected or removed
 * @property tenure The tenure bucket frozen at the first submit
 * @property publishedMonth `YYYY-MM` once published
 * @property replyBody The owner's reply while it is published
 */
@Serializable
data class MyReviewBody(
    @SerialName("rating") val rating: Int,
    @SerialName("body") val body: String? = null,
    @SerialName("status") val status: String,
    @SerialName("rejection_code") val rejectionCode: String? = null,
    @SerialName("tenure") val tenure: String,
    @SerialName("published_month") val publishedMonth: String? = null,
    @SerialName("reply_body") val replyBody: String? = null,
)

/**
 * Where the guardian stands with one batch's review.
 *
 * @property standing `eligible`, `not_yet`, `closed` or `author_only`
 * @property waitingOn What a `not_yet` guardian still needs: `tenure` or `attendance`
 * @property eligibleFrom The day a `not_yet` guardian's tenure is met
 * @property canWrite Whether a write now would be accepted; alone decides the form
 * @property editUntil The last day an edit is accepted
 * @property review The guardian's review, or null
 */
@Serializable
data class MyReviewResponse(
    @SerialName("standing") val standing: String,
    @SerialName("waiting_on") val waitingOn: String? = null,
    @SerialName("eligible_from") val eligibleFrom: String? = null,
    @SerialName("can_write") val canWrite: Boolean,
    @SerialName("edit_until") val editUntil: String? = null,
    @SerialName("review") val review: MyReviewBody? = null,
)

/**
 * A review as `PUT …/my-review` takes it.
 *
 * @property rating 1 to 5
 * @property body The words, or null for none
 */
@Serializable
data class ReviewWrite(
    @SerialName("rating") val rating: Int,
    @SerialName("body") val body: String? = null,
)

/**
 * A reply as `PUT …/reply` takes it.
 *
 * @property body 1 to 1000 characters once stripped
 */
@Serializable
data class ReplyWrite(
    @SerialName("body") val body: String,
)

/**
 * One of the owner's published batches with its rating, over the threshold.
 *
 * @property batchId The batch
 * @property batchTitle Its public title
 * @property reviewCount Published reviews, or null below the threshold
 * @property averageLabel The average as shown, `"4.3"`, or null below it
 * @property distribution Reviews per star from one to five, or null below it
 */
@Serializable
data class OwnerBatchRating(
    @SerialName("batch_id") val batchId: String,
    @SerialName("batch_title") val batchTitle: String? = null,
    @SerialName("review_count") val reviewCount: Int? = null,
    @SerialName("average_label") val averageLabel: String? = null,
    @SerialName("distribution") val distribution: List<Int>? = null,
)

/**
 * One published review of the owner's batch, with the owner's reply.
 *
 * @property id The review, to reply to and to report
 * @property batchId The batch
 * @property rating 1 to 5
 * @property body The words, or null
 * @property tenure The author's tenure bucket
 * @property publishedMonth `YYYY-MM`
 * @property replyBody The reply as the public sees it, while published
 * @property replyMonth `YYYY-MM` the reply was published in
 * @property myReplyStatus The owner's reply's status, or null without one
 * @property myReplyBody The owner's reply's words in any status
 * @property myReplyRejectionCode Why the reply was rejected or removed
 */
@Serializable
data class OwnerReview(
    @SerialName("id") val id: String,
    @SerialName("batch_id") val batchId: String,
    @SerialName("rating") val rating: Int,
    @SerialName("body") val body: String? = null,
    @SerialName("tenure") val tenure: String,
    @SerialName("published_month") val publishedMonth: String,
    @SerialName("reply_body") val replyBody: String? = null,
    @SerialName("reply_month") val replyMonth: String? = null,
    @SerialName("my_reply_status") val myReplyStatus: String? = null,
    @SerialName("my_reply_body") val myReplyBody: String? = null,
    @SerialName("my_reply_rejection_code") val myReplyRejectionCode: String? = null,
)

/**
 * The owner's published batches' ratings and their reviews.
 *
 * @property batches One row per published batch listing
 * @property reviews Published reviews, newest month first as the server sends them
 */
@Serializable
data class OwnerReviewsResponse(
    @SerialName("batches") val batches: List<OwnerBatchRating> = emptyList(),
    @SerialName("reviews") val reviews: List<OwnerReview> = emptyList(),
)

/**
 * A row of the reviewable list, as its `state` says.
 *
 * @property wire The server's word
 */
enum class ReviewableState(val wire: String) {
    /** May write a review now. */
    ELIGIBLE("eligible"),

    /** A member, not yet eligible. */
    NOT_YET("not_yet"),

    /** Has written one. */
    REVIEWED("reviewed"),
    ;

    companion object {
        /**
         * Name a state.
         *
         * @param wire The server's word
         * @return The state, or null for one this version does not know
         */
        fun fromWire(wire: String): ReviewableState? = entries.firstOrNull { it.wire == wire }
    }
}

/**
 * Who wrote a review, as the public reads it: a tenure, never a name.
 *
 * @property wire The server's bucket
 */
enum class Tenure(val wire: String) {
    /** Enrolled under six months. */
    LT_6M("lt_6m"),

    /** Six to twelve months. */
    M6_12("6_12m"),

    /** Over a year. */
    GT_1Y("gt_1y"),
    ;

    companion object {
        /**
         * Name a bucket.
         *
         * @param wire The server's bucket
         * @return The bucket, or null for one this version does not know
         */
        fun fromWire(wire: String): Tenure? = entries.firstOrNull { it.wire == wire }
    }
}

/** A review's or a reply's status, in the words its author reads. */
enum class ReviewStatusWords {
    /** Pending, or held: either way it is back with the moderators. */
    AWAITING,

    /** Approved; it appears with the weekly publication. */
    APPROVED,

    /** Public. */
    PUBLISHED,

    /** Rejected or removed, with the reason. */
    NOT_PUBLISHED,
}

/**
 * The words for a status. A held item reads "Awaiting review": that
 * someone reported it is not its author's to learn [T11-c].
 *
 * @param status The server's status
 * @return The words, or null for a status this version does not know
 */
fun statusWords(status: String): ReviewStatusWords? =
    when (status) {
        "pending", "held" -> ReviewStatusWords.AWAITING
        "approved" -> ReviewStatusWords.APPROVED
        "published" -> ReviewStatusWords.PUBLISHED
        "rejected", "removed" -> ReviewStatusWords.NOT_PUBLISHED
        else -> null
    }

/**
 * Why a review or reply was not published: the moderators' closed
 * vocabulary (`REVIEW_REJECTION_CODES`).
 *
 * @property wire The server's code
 */
enum class ReviewReason(val wire: String) {
    /** It could identify a child. */
    IDENTIFIABLE_CHILD("identifiable_child"),

    /** It shows personal information. */
    PERSONAL_INFO("personal_info"),

    /** It is abusive or offensive. */
    ABUSIVE("abusive"),

    /** It is not about the class. */
    OFF_TOPIC("off_topic"),

    /** Anything else. */
    OTHER("other"),
    ;

    companion object {
        /**
         * Name a reason.
         *
         * @param code The server's code, if any
         * @return The reason; a code this version does not know reads as [OTHER]
         */
        fun fromWire(code: String?): ReviewReason = entries.firstOrNull { it.wire == code } ?: OTHER
    }
}

/**
 * Why a member cannot write yet: the server's message key, and its day.
 *
 * @property messageKey The key of the matching refusal, so a read and a
 *   refused write say the same thing
 * @property eligibleFrom The day it becomes possible, when the server sent one
 */
data class StandingNote(val messageKey: String, val eligibleFrom: String?)

/**
 * The server's standing in the words of the matching refusal. Null while
 * nothing stands in the way, and for an author: `can_write` already says
 * whether they may edit.
 *
 * @return The note, or null
 */
fun MyReviewResponse.standingNote(): StandingNote? =
    when {
        review != null -> null
        standing == "not_yet" ->
            StandingNote(
                if (waitingOn == "attendance") "hub.review.needs_attendance" else "hub.review.not_yet_eligible",
                eligibleFrom,
            )
        standing == "closed" -> StandingNote("hub.review.window_closed", null)
        else -> null
    }

/** What an owner's batch row shows. */
sealed interface RatingLine {
    /** Below the threshold: the neutral line, the same for 0, 1 or 2 reviews. */
    data object BelowThreshold : RatingLine

    /**
     * Over it.
     *
     * @property averageLabel The server's rendered average, shown as sent
     * @property count Published reviews, when sent
     * @property distribution Reviews per star from one to five, when sent
     */
    data class Shown(val averageLabel: String, val count: Int?, val distribution: List<Int>?) : RatingLine
}

/**
 * The row, from the server's nulls and never from a count compared here.
 *
 * @return The line
 */
fun OwnerBatchRating.ratingLine(): RatingLine =
    averageLabel?.let { RatingLine.Shown(it, reviewCount, distribution) } ?: RatingLine.BelowThreshold

/** Which write failed, so Retry repeats the right one. */
enum class WriteKind {
    /** A review or a reply was being saved. */
    SAVE,

    /** It was being deleted. */
    DELETE,
}

/**
 * A failed write, as the screen shows it.
 *
 * @property messageKey The server's key, or the offline key
 * @property canRetry Whether repeating the call can help
 * @property kind Which write failed
 * @property eligibleFrom The day a refused first review becomes possible, when sent
 */
data class ReviewFailure(
    val messageKey: String,
    val canRetry: Boolean,
    val kind: WriteKind,
    val eligibleFrom: String? = null,
)

/**
 * Read a failed write.
 *
 * @param kind Which write it was
 * @return The failure, or null for a success
 */
internal fun AuthResult<*>.reviewFailure(kind: WriteKind): ReviewFailure? =
    when (this) {
        is AuthResult.Ok -> null
        is AuthResult.Refused ->
            ReviewFailure(
                envelope.error.messageKey,
                envelope.error.retryable,
                kind,
                envelope.error.details?.get("eligible_from"),
            )
        AuthResult.TransportFailure -> ReviewFailure(HUB_OFFLINE_KEY, canRetry = true, kind = kind)
    }

/** Whether a read was refused because reviews are switched off. */
internal val AuthResult<*>.isReviewsOff: Boolean
    get() = this is AuthResult.Refused && envelope.error.code == HUB_REVIEWS_OFF

/**
 * A failed read, as `(messageKey, retryable)`.
 *
 * @return The pair; the offline key for a transport failure
 */
internal fun AuthResult<*>.readFailure(): Pair<String, Boolean> =
    when (this) {
        is AuthResult.Refused -> envelope.error.messageKey to envelope.error.retryable
        else -> HUB_OFFLINE_KEY to true
    }
