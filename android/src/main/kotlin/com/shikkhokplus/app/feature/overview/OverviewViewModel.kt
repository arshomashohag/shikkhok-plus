package com.shikkhokplus.app.feature.overview

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.OverviewDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the today's overview screen needs from the network.
 *
 * Declared here rather than in `core.network` for the same reason
 * [com.shikkhokplus.app.feature.auth.AuthRepository] is: the feature
 * states what it needs and the network layer supplies it, so the
 * dependency points inward.
 */
interface OverviewRepository {
    /**
     * Load the today's overview.
     *
     * @return The response, a refusal, or a transport failure
     */
    suspend fun overview(): AuthResult<OverviewDto>
}

/**
 * Holds the today's overview screen's state. Holds no business logic
 * [TC-9, D-31].
 *
 * Every decision is delegated to [OverviewStateMapper], which is the
 * unit the tests target. This class owns the coroutine and the state
 * holder and nothing else.
 *
 * **The half that did not exist.** The screen, its state and its
 * mapper all shipped with tests, and nothing could reach the server —
 * so the screen was unreachable and its navigation tab was disabled.
 */
class OverviewViewModel(
    private val repository: OverviewRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<OverviewUiState>(OverviewUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<OverviewUiState> = _state.asStateFlow()

    /**
     * Load, or load again after a failure.
     *
     * Safe to call from a `LaunchedEffect(Unit)`: it sets the loading
     * state first, so a recomposition mid-flight cannot show stale
     * content as though it were current.
     */
    fun load() {
        _state.value = OverviewUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.overview()) {
                    is AuthResult.Ok -> OverviewStateMapper.afterLoad(result.value)
                    is AuthResult.Refused ->
                        OverviewStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        OverviewStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Retry, when the person asks.
     *
     * Never automatic: V1 has no local queue, so a retry nobody
     * requested would be the app deciding to act without connectivity
     * [TC-8, D-9].
     */
    fun retry() {
        load()
    }
}
