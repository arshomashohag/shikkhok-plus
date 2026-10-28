package com.shikkhokplus.app.feature.dues

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.DuesResponseDto
import com.shikkhokplus.app.core.network.ReminderResultDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * What the cross-batch dues screen needs from the network.
 *
 * Declared here rather than in `core.network` for the same reason
 * [com.shikkhokplus.app.feature.auth.AuthRepository] is: the feature
 * states what it needs and the network layer supplies it, so the
 * dependency points inward.
 */
interface DuesRepository {
    /**
     * Load the cross-batch dues.
     *
     * @return The response, a refusal, or a transport failure
     */
    suspend fun dues(): AuthResult<DuesResponseDto>

    /**
     * Remind these seats what they owe, in the app.
     *
     * @param enrollmentIds The seats
     * @return How many were reminded, a refusal, or a transport failure
     */
    suspend fun remind(enrollmentIds: List<String>): AuthResult<ReminderResultDto>
}

/**
 * Holds the cross-batch dues screen's state. Holds no business logic
 * [TC-9, D-31].
 *
 * Every decision is delegated to [DuesStateMapper], which is the unit
 * the tests target. This class owns the coroutine, the full row list
 * the filters narrow, the open filters (kept across a reload), and the
 * reminder's progress.
 */
class DuesViewModel(
    private val repository: DuesRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<DuesUiState>(DuesUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<DuesUiState> = _state.asStateFlow()

    private var allRows: List<DuesRow> = emptyList()

    private var filter: DuesFilter = DuesFilter.ALL

    private var batch: DuesBatch? = null

    /**
     * Load, or load again after a failure.
     *
     * Safe to call from a `LaunchedEffect(Unit)`: it sets the loading
     * state first, so a recomposition mid-flight cannot show stale
     * content as though it were current.
     */
    fun load() {
        _state.value = DuesUiState.Loading
        viewModelScope.launch { _state.value = read() }
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

    /**
     * Show only the rows a filter lets through.
     *
     * @param filter The filter
     */
    fun filter(filter: DuesFilter) {
        this.filter = filter
        updateLoaded { it.copy(filter = filter, rows = DuesStateMapper.visible(allRows, filter, batch?.id)) }
    }

    /**
     * Narrow to one batch, or back to all.
     *
     * @param batch The batch, or null for all
     */
    fun narrow(batch: DuesBatch?) {
        this.batch = batch
        updateLoaded { it.copy(batch = batch, rows = DuesStateMapper.visible(allRows, filter, batch?.id)) }
    }

    /** Ask the teacher to confirm a reminder. */
    fun askToRemind() {
        updateLoaded { it.copy(remind = RemindState.Confirming) }
    }

    /** Forget a confirmation, a result or a failure, once dismissed. */
    fun dismissRemind() {
        updateLoaded { it.copy(remind = RemindState.Idle) }
    }

    /** Send the reminder to every seat the server marked remindable. */
    fun remind() {
        val loaded = _state.value as? DuesUiState.Loaded ?: return
        if (loaded.remind == RemindState.Sending) return
        val targets = DuesStateMapper.remindTargets(allRows)
        updateLoaded { it.copy(remind = RemindState.Sending) }
        viewModelScope.launch {
            val outcome =
                when (val result = repository.remind(targets)) {
                    is AuthResult.Ok -> RemindState.Sent(result.value.sent)
                    is AuthResult.Refused -> RemindState.Failed(result.envelope.error.messageKey)
                    AuthResult.TransportFailure -> RemindState.Failed(DuesStateMapper.OFFLINE_KEY)
                }
            if (outcome is RemindState.Sent) {
                val fresh = read()
                _state.value = (fresh as? DuesUiState.Loaded)?.copy(remind = outcome) ?: fresh
            } else {
                updateLoaded { it.copy(remind = outcome) }
            }
        }
    }

    /**
     * Read the dues and keep the full list for the filters.
     *
     * @return The state to show
     */
    private suspend fun read(): DuesUiState {
        val next =
            when (val result = repository.dues()) {
                is AuthResult.Ok -> DuesStateMapper.afterLoad(result.value)
                is AuthResult.Refused -> DuesStateMapper.afterError(result.envelope)
                AuthResult.TransportFailure -> DuesStateMapper.afterTransportFailure()
            }
        if (next !is DuesUiState.Loaded) return next
        allRows = next.rows
        batch = batch?.takeIf { kept -> next.batches.any { it.id == kept.id } }
        return next.copy(filter = filter, batch = batch, rows = DuesStateMapper.visible(allRows, filter, batch?.id))
    }

    /**
     * Change the loaded state, if loaded.
     *
     * @param change The change
     */
    private fun updateLoaded(change: (DuesUiState.Loaded) -> DuesUiState.Loaded) {
        _state.update { current -> (current as? DuesUiState.Loaded)?.let(change) ?: current }
    }
}
