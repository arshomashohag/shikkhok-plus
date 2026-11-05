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

    /** The day the server returned last this session, for offline. */
    private var lastLoaded: TodayUiState.Loaded? = null

    /**
     * Read the day.
     *
     * **Offline keeps this session's day** (T1), marked as such, so a
     * teacher mid-class still sees their classes and can record a topic,
     * which queues [BR3.1], rather than an error in place of the list.
     *
     * @return The state to show
     */
    private suspend fun read(): TodayUiState =
        when (val result = repository.today()) {
            is AuthResult.Ok ->
                TodayStateMapper.afterLoad(result.value).let { state ->
                    // The phone's saved copy, read back with no connection:
                    // shown, and marked offline.
                    if (result.savedAt != null && state is TodayUiState.Loaded) state.copy(offline = true) else state
                }.also { if (it is TodayUiState.Loaded && !it.offline) lastLoaded = it }
            is AuthResult.Refused -> TodayStateMapper.afterError(result.envelope)
            AuthResult.TransportFailure ->
                lastLoaded?.copy(offline = true) ?: TodayStateMapper.afterTransportFailure()
        }

    /** Read again, only when asked [TC-8, D-9]. */
    fun retry() = load()
}
