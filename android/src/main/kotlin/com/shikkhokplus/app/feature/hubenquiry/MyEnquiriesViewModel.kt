package com.shikkhokplus.app.feature.hubenquiry

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * A withdrawal that failed, on the row it was for.
 *
 * @property enquiryId The request
 * @property failure Why, and whether trying again can help
 */
data class WithdrawFailure(val enquiryId: String, val failure: EnquiryFailure)

/** What the guardian's join-request list renders. */
sealed interface MyEnquiriesUiState {
    /** Waiting for the list. */
    data object Loading : MyEnquiriesUiState

    /**
     * The server's rows, in its order.
     *
     * @property rows The caller's requests
     * @property confirming The request whose withdrawal is being confirmed, or null
     * @property withdrawing Whether a withdrawal is in flight
     * @property failure The last failed withdrawal, or null
     * @property withdrawn Whether to say a request was just withdrawn
     * @property refreshFailure Why the last quiet re-read failed, or null: the
     *   rows shown are the last ones read, and the screen says so
     */
    data class Ready(
        val rows: List<MyEnquiry>,
        val confirming: String? = null,
        val withdrawing: Boolean = false,
        val failure: WithdrawFailure? = null,
        val withdrawn: Boolean = false,
        val refreshFailure: EnquiryFailure? = null,
    ) : MyEnquiriesUiState {
        /** Whether anything is in hand that a re-read must not wipe. */
        val busy: Boolean get() = confirming != null || withdrawing || failure != null
    }

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Whether to offer a retry
     */
    data class Error(val messageKey: String, val retryable: Boolean) : MyEnquiriesUiState
}

/**
 * Whether More offers "My join requests": only once the server lists at
 * least one. The list is never switched off, so a guardian with a request
 * sent before the switch went off can still reach it to withdraw it.
 */
val MyEnquiriesUiState.showsEntry: Boolean
    get() = this is MyEnquiriesUiState.Ready && rows.isNotEmpty()

/**
 * Holds the caller's own join requests, for the list screen and for More's
 * entry to it.
 *
 * **Withdrawal deletes completely** and is sent only from the confirmation
 * that says so. A failed withdrawal keeps the row and offers Retry, which
 * reopens the confirmation, only when the server or the dropped connection
 * says trying again can help [TC-8].
 *
 * @property api The network
 */
class MyEnquiriesViewModel(
    private val api: EnquirerApi,
) : ViewModel() {

    private val _state = MutableStateFlow<MyEnquiriesUiState>(MyEnquiriesUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<MyEnquiriesUiState> = _state.asStateFlow()

    private val ready: MyEnquiriesUiState.Ready? get() = _state.value as? MyEnquiriesUiState.Ready

    /** The read in flight, so two never race and a withdrawal can stop a late one. */
    private var reading: Job? = null

    /**
     * Read the list. Rows already shown stay until the answer arrives, so a
     * return to the screen refreshes the owners' answers quietly; a
     * confirmation, a withdrawal under way or a failure with its Retry is
     * never wiped by it, and a re-read that fails keeps the rows and says
     * they could not be refreshed [TC-8]. One read at a time.
     */
    fun load() {
        if (ready?.busy == true || reading?.isActive == true) return
        if (ready == null) _state.value = MyEnquiriesUiState.Loading
        reading = viewModelScope.launch { read(withdrawnId = null) }
    }

    /**
     * Open the confirmation for one request.
     *
     * @param enquiryId The request
     */
    fun askWithdraw(enquiryId: String) {
        val shown = ready ?: return
        if (shown.withdrawing) return
        // A re-read landing now would close the confirmation under the guardian's finger.
        reading?.cancel()
        _state.value = shown.copy(confirming = enquiryId, failure = null, withdrawn = false)
    }

    /** Close the confirmation without withdrawing. */
    fun cancelWithdraw() {
        ready?.let { _state.value = it.copy(confirming = null) }
    }

    /** Withdraw, from the confirmation only; then read the list again. */
    fun confirmWithdraw() {
        val shown = ready ?: return
        val id = shown.confirming ?: return
        if (shown.withdrawing) return
        reading?.cancel()
        _state.value = shown.copy(confirming = null, withdrawing = true)
        reading = viewModelScope.launch {
            val result = api.withdraw(id)
            if (result is AuthResult.Ok) {
                read(withdrawnId = id)
            } else {
                _state.update {
                    (it as? MyEnquiriesUiState.Ready)
                        ?.copy(withdrawing = false, failure = WithdrawFailure(id, result.enquiryFailure()))
                        ?: it
                }
            }
        }
    }

    /** After a failed withdrawal that can be retried, ask again. */
    fun retryWithdraw() {
        val failed = ready?.failure ?: return
        if (failed.failure.canRetry) askWithdraw(failed.enquiryId)
    }

    /** Forget the "withdrawn" confirmation. */
    fun dismissNotice() {
        ready?.let { _state.value = it.copy(withdrawn = false) }
    }

    /**
     * Read the list and show it.
     *
     * @param withdrawnId The request just withdrawn, or null for a plain read.
     *   If the list cannot be read again after a withdrawal, that row alone
     *   is dropped, since the server said it is gone.
     */
    private suspend fun read(withdrawnId: String?) {
        val result = api.mine()
        val shown = ready
        _state.value =
            when {
                result is AuthResult.Ok && withdrawnId == null && shown != null ->
                    shown.copy(rows = result.value, refreshFailure = null)
                result is AuthResult.Ok -> MyEnquiriesUiState.Ready(result.value, withdrawn = withdrawnId != null)
                withdrawnId != null && shown != null ->
                    shown.copy(
                        rows = shown.rows.filterNot { it.id == withdrawnId },
                        withdrawing = false,
                        withdrawn = true,
                    )
                // A quiet re-read that failed keeps what is shown, and says so.
                shown != null -> shown.copy(refreshFailure = result.enquiryFailure())
                else -> result.enquiryFailure().let { MyEnquiriesUiState.Error(it.messageKey, it.canRetry) }
            }
    }
}
