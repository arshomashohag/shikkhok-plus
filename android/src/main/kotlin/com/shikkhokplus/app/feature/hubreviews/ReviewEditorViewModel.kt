package com.shikkhokplus.app.feature.hubreviews

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * One batch's review form.
 *
 * @property review The server's state: standing, `can_write`, `edit_until` and the review
 * @property rating The chosen rating, or null before one is chosen
 * @property text The words as typed, at most [REVIEW_TEXT_MAX] characters
 * @property failure Why the last write failed, or null
 * @property confirmingDelete Whether the delete confirmation is open
 * @property deleted Whether to say the review was just deleted
 */
data class ReviewForm(
    val review: MyReviewResponse,
    val rating: Int? = review.review?.rating,
    val text: String = review.review?.body.orEmpty(),
    val failure: ReviewFailure? = null,
    val confirmingDelete: Boolean = false,
    val deleted: Boolean = false,
) {
    /** Whether Submit or Save does anything: the server says writable, and a rating is chosen. */
    val canSave: Boolean get() = review.canWrite && rating != null

    /** Why a member cannot write yet, in the server's words; null for an author. */
    val note: StandingNote? get() = review.standingNote()
}

/** What the review editor renders. */
sealed interface ReviewEditorUiState {
    /** Waiting for the state. */
    data object Loading : ReviewEditorUiState

    /**
     * The form, idle.
     *
     * @property form What is shown and typed
     */
    data class Ready(val form: ReviewForm) : ReviewEditorUiState

    /**
     * A write is in flight; the form is shown and nothing can be changed.
     *
     * @property form What is shown and typed
     */
    data class Saving(val form: ReviewForm) : ReviewEditorUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Whether to offer a retry
     */
    data class Error(val messageKey: String, val retryable: Boolean) : ReviewEditorUiState

    /** Reviews are switched off: nothing is drawn. */
    data object Off : ReviewEditorUiState
}

/**
 * Holds one batch's review as its guardian author writes, edits and
 * deletes it.
 *
 * **The server decides; this carries.** `can_write` alone says whether
 * a rating or the words may change, and the server's refusal is shown in
 * its own words with the day it names. A failed write keeps the rating
 * and the words; Retry is offered only when the server, or the dropped
 * connection, says trying again can help, and it repeats the call with
 * what is on screen when it is pressed [TC-8]. A delete is sent only from
 * its confirmation, and is never gated: an author can always remove
 * their words.
 *
 * @property api The network
 * @property batchId The batch reviewed
 */
class ReviewEditorViewModel(
    private val api: ReviewerApi,
    private val batchId: String,
) : ViewModel() {

    private val _state = MutableStateFlow<ReviewEditorUiState>(ReviewEditorUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<ReviewEditorUiState> = _state.asStateFlow()

    /** The form while it is idle; null while loading or saving. */
    private val idle: ReviewForm? get() = (_state.value as? ReviewEditorUiState.Ready)?.form

    /**
     * Read where the guardian stands. Does nothing once the form is showing
     * or a write is in flight: the route loads on every return to the
     * screen and on recreation, and that must never wipe a half-written
     * review, a failure with its Retry, or a save under way [TC-8].
     */
    fun load() {
        val shown = _state.value
        if (shown is ReviewEditorUiState.Ready || shown is ReviewEditorUiState.Saving) return
        _state.value = ReviewEditorUiState.Loading
        viewModelScope.launch {
            val result = api.myReview(batchId)
            _state.value =
                when {
                    result is AuthResult.Ok -> ReviewEditorUiState.Ready(ReviewForm(result.value))
                    result.isReviewsOff -> ReviewEditorUiState.Off
                    else -> result.readFailure().let { (key, retry) -> ReviewEditorUiState.Error(key, retry) }
                }
        }
    }

    /** Read again after a failed read. */
    fun retryLoad() {
        if ((_state.value as? ReviewEditorUiState.Error)?.retryable == true) load()
    }

    /**
     * Choose a rating, while the server says the review is writable.
     *
     * @param rating 1 to [RATING_MAX]
     */
    fun pickRating(rating: Int) {
        val form = idle ?: return
        if (form.review.canWrite && rating in 1..RATING_MAX) update(form.copy(rating = rating))
    }

    /**
     * Change the words, while writable; anything past the server's limit is not kept.
     *
     * @param text The words as typed
     */
    fun editText(text: String) {
        val form = idle ?: return
        if (form.review.canWrite) update(form.copy(text = text.take(REVIEW_TEXT_MAX)))
    }

    /** Send the rating and the words, stripped; an empty body is sent as none. */
    fun save() {
        val form = idle ?: return
        val rating = form.rating
        if (!form.canSave || rating == null) return
        val sending = form.copy(failure = null, deleted = false)
        _state.value = ReviewEditorUiState.Saving(sending)
        viewModelScope.launch {
            val result = api.saveMyReview(batchId, ReviewWrite(rating, form.text.trim().ifEmpty { null }))
            update(
                when (result) {
                    is AuthResult.Ok -> sending.copy(review = result.value)
                    else -> sending.copy(failure = result.reviewFailure(WriteKind.SAVE))
                },
            )
        }
    }

    /** Open the delete confirmation, when there is a review to delete. */
    fun askDelete() {
        val form = idle ?: return
        if (form.review.review != null) update(form.copy(confirmingDelete = true, failure = null))
    }

    /** Close it without deleting. */
    fun cancelDelete() {
        idle?.let { update(it.copy(confirmingDelete = false)) }
    }

    /** Delete, from the confirmation only; then ask the server what may be written now. */
    fun confirmDelete() {
        val form = idle ?: return
        if (!form.confirmingDelete) return
        val deleting = form.copy(confirmingDelete = false, failure = null)
        _state.value = ReviewEditorUiState.Saving(deleting)
        viewModelScope.launch {
            val result = api.deleteMyReview(batchId)
            if (result !is AuthResult.Ok) {
                update(deleting.copy(failure = result.reviewFailure(WriteKind.DELETE)))
                return@launch
            }
            // Until the server answers, nothing is offered that it did not confirm.
            val after =
                (api.myReview(batchId) as? AuthResult.Ok)?.value
                    ?: deleting.review.copy(review = null, editUntil = null, canWrite = false)
            update(ReviewForm(after, rating = null, text = "", deleted = true))
        }
    }

    /** Repeat the write that last failed, when that can help; a delete asks again first. */
    fun retry() {
        val failure = idle?.failure ?: return
        if (!failure.canRetry) return
        when (failure.kind) {
            WriteKind.SAVE -> save()
            WriteKind.DELETE -> askDelete()
        }
    }

    /** Forget the "deleted" confirmation. */
    fun dismissNotice() {
        idle?.let { update(it.copy(deleted = false)) }
    }

    private fun update(form: ReviewForm) {
        _state.value = ReviewEditorUiState.Ready(form)
    }
}
