package com.shikkhokplus.app.feature.today

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.ui.RefreshGate
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds T1's state. Decisions are [TodayStateMapper]'s.
 *
 * @property repository The Today read
 */
class TodayViewModel(
    private val repository: TodayRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<TodayUiState>(TodayUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<TodayUiState> = _state.asStateFlow()

    private val gate = RefreshGate()

    /** Whether a pull-to-refresh is in flight. */
    val refreshing: StateFlow<Boolean> = gate.refreshing

    /** Read the day. */
    fun load() {
        _state.value = TodayUiState.Loading
        viewModelScope.launch { _state.value = read() }
    }

    /**
     * Re-read on a pull, keeping what is on screen until the answer
     * arrives. Started only by the person pulling [TC-8, D-9].
     */
    fun refresh() {
        gate.run(viewModelScope) { _state.value = read() }
    }

    private suspend fun read(): TodayUiState =
        when (val result = repository.today()) {
            is AuthResult.Ok -> TodayStateMapper.afterLoad(result.value)
            is AuthResult.Refused -> TodayStateMapper.afterError(result.envelope)
            AuthResult.TransportFailure -> TodayStateMapper.afterTransportFailure()
        }

    /** Read again, only when asked [TC-8, D-9]. */
    fun retry() = load()
}
