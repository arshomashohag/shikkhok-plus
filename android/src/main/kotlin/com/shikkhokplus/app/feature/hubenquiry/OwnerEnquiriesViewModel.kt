package com.shikkhokplus.app.feature.hubenquiry

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What the owner's join-request inbox renders. */
sealed interface OwnerEnquiriesUiState {
    /** Waiting for the list. */
    data object Loading : OwnerEnquiriesUiState

    /**
     * The server's rows, open first, in its order; the client sorts nothing.
     *
     * @property rows The owner's requests
     */
    data class Ready(val rows: List<OwnerEnquiry>) : OwnerEnquiriesUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Whether to offer a retry
     */
    data class Error(val messageKey: String, val retryable: Boolean) : OwnerEnquiriesUiState

    /**
     * Join requests are switched off. The screen says so plainly; the
     * listing editor draws no row.
     *
     * @property messageKey The server's sentence
     */
    data class Off(val messageKey: String) : OwnerEnquiriesUiState
}

/**
 * Whether the listing editor offers its "Join requests" row: only once
 * `GET /v1/hub/enquiries` answered. Switched off, or on any failure, there
 * is no row and no error.
 */
val OwnerEnquiriesUiState.showsEntry: Boolean
    get() = this is OwnerEnquiriesUiState.Ready

/**
 * Holds the owner's join-request inbox, for the inbox screen and for the
 * listing editor's entry to it.
 *
 * @property api The network
 */
class OwnerEnquiriesViewModel(
    private val api: OwnerEnquiriesApi,
) : ViewModel() {

    private val _state = MutableStateFlow<OwnerEnquiriesUiState>(OwnerEnquiriesUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<OwnerEnquiriesUiState> = _state.asStateFlow()

    /**
     * Read the inbox; rows already shown stay until the answer arrives, so
     * a return from a request shows its answer without a loader.
     */
    fun load() {
        if (_state.value !is OwnerEnquiriesUiState.Ready) _state.value = OwnerEnquiriesUiState.Loading
        viewModelScope.launch {
            val result = api.inbox()
            _state.value =
                when {
                    result is AuthResult.Ok -> OwnerEnquiriesUiState.Ready(result.value)
                    result.isEnquiriesOff -> OwnerEnquiriesUiState.Off(result.enquiryFailure().messageKey)
                    else -> result.enquiryFailure().let { OwnerEnquiriesUiState.Error(it.messageKey, it.canRetry) }
                }
        }
    }
}
