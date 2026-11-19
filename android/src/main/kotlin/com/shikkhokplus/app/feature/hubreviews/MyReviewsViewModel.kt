package com.shikkhokplus.app.feature.hubreviews

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What the guardian's review list renders. */
sealed interface MyReviewsUiState {
    /** Waiting for the list. */
    data object Loading : MyReviewsUiState

    /**
     * The server's rows, in its order.
     *
     * @property rows The batches the guardian may review, is waiting to, or has reviewed
     */
    data class Ready(val rows: List<ReviewableBatch>) : MyReviewsUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Whether to offer a retry
     */
    data class Error(val messageKey: String, val retryable: Boolean) : MyReviewsUiState

    /** Reviews are switched off: nothing is drawn. */
    data object Off : MyReviewsUiState
}

/**
 * Whether the guardian home offers its Reviews row: only once the list
 * has loaded with at least one row. Switched off, the server lists only
 * what was already reviewed, so a guardian who never wrote one sees no
 * entry at all.
 */
val MyReviewsUiState.showsEntry: Boolean
    get() = this is MyReviewsUiState.Ready && rows.isNotEmpty()

/**
 * Holds the guardian's reviewable list, for the list screen and for the
 * guardian home's entry to it.
 *
 * @property api The network
 */
class MyReviewsViewModel(
    private val api: ReviewerApi,
) : ViewModel() {

    private val _state = MutableStateFlow<MyReviewsUiState>(MyReviewsUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<MyReviewsUiState> = _state.asStateFlow()

    /** Read the list; rows already shown stay until the answer arrives. */
    fun load() {
        if (_state.value !is MyReviewsUiState.Ready) _state.value = MyReviewsUiState.Loading
        viewModelScope.launch {
            val result = api.reviewable()
            _state.value =
                when {
                    result is AuthResult.Ok -> MyReviewsUiState.Ready(result.value)
                    result.isReviewsOff -> MyReviewsUiState.Off
                    else -> result.readFailure().let { (key, retry) -> MyReviewsUiState.Error(key, retry) }
                }
        }
    }
}
