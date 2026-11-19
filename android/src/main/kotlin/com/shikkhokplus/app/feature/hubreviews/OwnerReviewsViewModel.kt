package com.shikkhokplus.app.feature.hubreviews

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * One published review, with the owner's reply box.
 *
 * @property review The review and the reply as the server last sent them
 * @property draft The reply as typed, at most [REVIEW_TEXT_MAX] characters
 * @property failure Why the last write on this review failed, or null
 * @property confirmingDelete Whether the reply's delete confirmation is open
 */
data class ReplyCard(
    val review: OwnerReview,
    val draft: String = review.myReplyBody.orEmpty(),
    val failure: ReviewFailure? = null,
    val confirmingDelete: Boolean = false,
)

/**
 * The owner's Reviews screen, loaded.
 *
 * @property batches Every published batch's rating row
 * @property cards The published reviews, newest month first as the server sent them
 * @property replyDeleted Whether to say a reply was just deleted
 */
data class OwnerReviewsContent(
    val batches: List<OwnerBatchRating>,
    val cards: List<ReplyCard>,
    val replyDeleted: Boolean = false,
) {
    /**
     * A batch's public title, for a review card.
     *
     * @param batchId The batch
     * @return Its title, or null
     */
    fun titleOf(batchId: String): String? = batches.firstOrNull { it.batchId == batchId }?.batchTitle
}

/** What the owner's Reviews screen renders. */
sealed interface OwnerReviewsUiState {
    /** Waiting for the page. */
    data object Loading : OwnerReviewsUiState

    /**
     * The page, idle.
     *
     * @property content The ratings and the reviews
     */
    data class Ready(val content: OwnerReviewsContent) : OwnerReviewsUiState

    /**
     * A reply is being sent or deleted; nothing can be changed meanwhile.
     *
     * @property content The ratings and the reviews
     * @property reviewId The review whose reply is in flight
     */
    data class Saving(val content: OwnerReviewsContent, val reviewId: String) : OwnerReviewsUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Whether to offer a retry
     */
    data class Error(val messageKey: String, val retryable: Boolean) : OwnerReviewsUiState

    /** `HUB_REVIEWS_OFF`: nothing is drawn, and no error. */
    data object Off : OwnerReviewsUiState
}

/** Whether the listing editor offers its Reviews row: only once the read succeeded. */
val OwnerReviewsUiState.showsEntry: Boolean
    get() = this is OwnerReviewsUiState.Ready || this is OwnerReviewsUiState.Saving

/**
 * Holds the owner's Reviews screen: each published batch's rating
 * exactly as the public sees it, and a reply box per review.
 *
 * A reply is checked before it appears, so a sent reply comes back
 * awaiting review. A failed send keeps the words and offers Retry when
 * the server, or the dropped connection, says it can help [TC-8]; a
 * failed delete keeps the reply and Retry asks again. `HUB_REVIEWS_OFF`
 * is [OwnerReviewsUiState.Off], which renders nothing.
 *
 * @property api The network
 */
class OwnerReviewsViewModel(
    private val api: OwnerReviewsApi,
) : ViewModel() {

    private val _state = MutableStateFlow<OwnerReviewsUiState>(OwnerReviewsUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<OwnerReviewsUiState> = _state.asStateFlow()

    /** The page while it is idle; null while loading or a write is in flight. */
    private val idle: OwnerReviewsContent? get() = (_state.value as? OwnerReviewsUiState.Ready)?.content

    /**
     * Read the page. Does nothing once it is showing or a reply is in
     * flight: the route loads on every return to the screen (Back from a
     * Report) and on recreation, and that must never wipe a draft, a
     * failure with its Retry, or a send under way [TC-8].
     */
    fun load() {
        val shown = _state.value
        if (shown is OwnerReviewsUiState.Ready || shown is OwnerReviewsUiState.Saving) return
        _state.value = OwnerReviewsUiState.Loading
        viewModelScope.launch {
            val result = api.ownerReviews()
            _state.value =
                when {
                    result is AuthResult.Ok ->
                        OwnerReviewsUiState.Ready(
                            OwnerReviewsContent(result.value.batches, result.value.reviews.map(::ReplyCard)),
                        )
                    result.isReviewsOff -> OwnerReviewsUiState.Off
                    else -> result.readFailure().let { (key, retry) -> OwnerReviewsUiState.Error(key, retry) }
                }
        }
    }

    /** Read again after a failed read. */
    fun retryLoad() {
        if ((_state.value as? OwnerReviewsUiState.Error)?.retryable == true) load()
    }

    /**
     * Change a reply as typed; anything past the server's limit is not kept.
     *
     * @param reviewId The review
     * @param text The reply as typed
     */
    fun editReply(reviewId: String, text: String) {
        change(reviewId) { it.copy(draft = text.take(REVIEW_TEXT_MAX)) }
    }

    /**
     * Send a reply, stripped; a blank one is not sent.
     *
     * @param reviewId The review
     */
    fun sendReply(reviewId: String) {
        val content = idle ?: return
        val card = content.cards.firstOrNull { it.review.id == reviewId } ?: return
        val body = card.draft.trim()
        if (body.isEmpty()) return
        val sending = content.with(reviewId) { it.copy(failure = null) }.copy(replyDeleted = false)
        _state.value = OwnerReviewsUiState.Saving(sending, reviewId)
        viewModelScope.launch {
            val result = api.saveReply(reviewId, ReplyWrite(body))
            _state.value =
                OwnerReviewsUiState.Ready(
                    sending.with(reviewId) {
                        when (result) {
                            is AuthResult.Ok -> ReplyCard(result.value, draft = result.value.myReplyBody ?: body)
                            else -> it.copy(failure = result.reviewFailure(WriteKind.SAVE))
                        }
                    },
                )
        }
    }

    /**
     * Open a reply's delete confirmation, when there is a reply.
     *
     * @param reviewId The review
     */
    fun askDeleteReply(reviewId: String) {
        change(reviewId) { card ->
            if (card.review.myReplyStatus != null) card.copy(confirmingDelete = true, failure = null) else card
        }
    }

    /**
     * Close it without deleting.
     *
     * @param reviewId The review
     */
    fun cancelDeleteReply(reviewId: String) {
        change(reviewId) { it.copy(confirmingDelete = false) }
    }

    /**
     * Delete a reply, from its confirmation only. Never gated: the owner can
     * always remove their words, in any status.
     *
     * @param reviewId The review
     */
    fun confirmDeleteReply(reviewId: String) {
        val content = idle ?: return
        if (content.cards.none { it.review.id == reviewId && it.confirmingDelete }) return
        val deleting = content.with(reviewId) { it.copy(confirmingDelete = false, failure = null) }
        _state.value = OwnerReviewsUiState.Saving(deleting, reviewId)
        viewModelScope.launch {
            val result = api.deleteReply(reviewId)
            _state.value =
                OwnerReviewsUiState.Ready(
                    if (result is AuthResult.Ok) {
                        deleting.with(reviewId) { ReplyCard(it.review.withoutReply(), draft = "") }
                            .copy(replyDeleted = true)
                    } else {
                        deleting.with(reviewId) { it.copy(failure = result.reviewFailure(WriteKind.DELETE)) }
                    },
                )
        }
    }

    /**
     * Repeat the write on a review that last failed, when that can help; a
     * delete asks again first.
     *
     * @param reviewId The review
     */
    fun retry(reviewId: String) {
        val failure = idle?.cards?.firstOrNull { it.review.id == reviewId }?.failure ?: return
        if (!failure.canRetry) return
        when (failure.kind) {
            WriteKind.SAVE -> sendReply(reviewId)
            WriteKind.DELETE -> askDeleteReply(reviewId)
        }
    }

    /** Forget the "reply deleted" confirmation. */
    fun dismissNotice() {
        idle?.let { _state.value = OwnerReviewsUiState.Ready(it.copy(replyDeleted = false)) }
    }

    private fun change(reviewId: String, edit: (ReplyCard) -> ReplyCard) {
        idle?.let { _state.value = OwnerReviewsUiState.Ready(it.with(reviewId, edit)) }
    }
}

/**
 * The page with one review's card changed.
 *
 * @param reviewId The review
 * @param edit The change
 * @return The changed page
 */
private fun OwnerReviewsContent.with(reviewId: String, edit: (ReplyCard) -> ReplyCard): OwnerReviewsContent =
    copy(cards = cards.map { if (it.review.id == reviewId) edit(it) else it })

/** The review once its reply is gone, in every status: a 204 says so. */
private fun OwnerReview.withoutReply(): OwnerReview =
    copy(replyBody = null, replyMonth = null, myReplyStatus = null, myReplyBody = null, myReplyRejectionCode = null)
