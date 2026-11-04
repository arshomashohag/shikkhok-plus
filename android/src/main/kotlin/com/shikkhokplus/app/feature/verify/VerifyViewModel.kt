package com.shikkhokplus.app.feature.verify

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.PaymentApprovalBodyDto
import com.shikkhokplus.app.core.ui.RefreshGate
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds R1: the payments waiting for the teacher. Reviewing one is
 * [PaymentReviewViewModel]'s work.
 *
 * @property repository The queue read
 */
class VerifyViewModel(
    private val repository: VerifyRepository,
    private val decisions: PaymentReviewRepository? = null,
) : ViewModel() {

    private val _state = MutableStateFlow<VerifyUiState>(VerifyUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<VerifyUiState> = _state.asStateFlow()

    private val gate = RefreshGate()

    /** Whether a pull-to-refresh is in flight. */
    val refreshing: StateFlow<Boolean> = gate.refreshing

    /** Load the queue. */
    fun load() {
        _state.value = VerifyUiState.Loading
        viewModelScope.launch { _state.value = read() }
    }

    /**
     * Re-read on a pull, keeping what is on screen until the answer
     * arrives. Started only by the person pulling [TC-8, D-9].
     */
    fun refresh() {
        gate.run(viewModelScope) { _state.value = read() }
    }

    private suspend fun read(): VerifyUiState =
        when (val result = repository.queue()) {
            is AuthResult.Ok -> VerifyStateMapper.afterLoad(result.value)
            is AuthResult.Refused -> VerifyStateMapper.afterError(result.envelope)
            AuthResult.TransportFailure -> VerifyStateMapper.afterTransportFailure()
        }

    /** Repeat the load, only when asked [TC-8, D-9]. */
    fun retry() = load()

    private val _deciding = MutableStateFlow<String?>(null)

    /** The payment whose inline approval is in flight, or null. */
    val deciding: StateFlow<String?> = _deciding.asStateFlow()

    private val _decisionError = MutableStateFlow<String?>(null)

    /** Why the last inline approval failed, as a message key, or null. */
    val decisionError: StateFlow<String?> = _decisionError.asStateFlow()

    /**
     * Approve a payment straight from the queue (T4), as reported.
     *
     * **Only a payment that needs no further choice**: one the server
     * says matches what is owed, with a transaction ID nobody used
     * before. Anything short, over or reused needs the review screen,
     * where carry-forward, waive and the duplicate warning live, so this
     * refuses it rather than guessing. One approval at a time.
     *
     * @param card The payment
     */
    fun approveAsReported(card: ReviewCard) {
        val writer = decisions ?: return
        if (card.comparison != Comparison.MATCHES || card.duplicate != null || _deciding.value != null) return
        _deciding.value = card.submissionId
        _decisionError.value = null
        viewModelScope.launch {
            val body = PaymentApprovalBodyDto(receivedAmount = card.totalAmount)
            when (val result = writer.approve(card.submissionId, body)) {
                is AuthResult.Ok -> _state.value = read()
                is AuthResult.Refused -> {
                    _decisionError.value = result.envelope.error.messageKey
                    // Decided elsewhere meanwhile: show the queue as it is now.
                    if (result.envelope.error.code == VerifyStateMapper.ALREADY_DECIDED_CODE) _state.value = read()
                }
                AuthResult.TransportFailure -> _decisionError.value = VerifyStateMapper.OFFLINE_KEY
            }
            _deciding.value = null
        }
    }
}
