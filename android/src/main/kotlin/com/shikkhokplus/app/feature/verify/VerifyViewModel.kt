package com.shikkhokplus.app.feature.verify

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
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
}
