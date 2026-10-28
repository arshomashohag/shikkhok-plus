package com.shikkhokplus.app.feature.today

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
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

    /** Read the day. */
    fun load() {
        _state.value = TodayUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.today()) {
                    is AuthResult.Ok -> TodayStateMapper.afterLoad(result.value)
                    is AuthResult.Refused -> TodayStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure -> TodayStateMapper.afterTransportFailure()
                }
        }
    }

    /** Read again, only when asked [TC-8, D-9]. */
    fun retry() = load()
}
