package com.shikkhokplus.app.feature.guardian

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.GuardianChildDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What the guardian repository must provide. */
interface GuardianRepository {
    /**
     * List the seats this guardian was recorded on.
     *
     * Resolved server-side through `guardian_account_id`, never through
     * the child [BR4.1, NFR14.29].
     *
     * @return The children, an error envelope, or a transport failure
     */
    suspend fun children(): AuthResult<List<GuardianChildDto>>
}

/**
 * Holds the guardian home's state. Holds no business logic [TC-9, D-31].
 *
 * Every decision is delegated to [GuardianStateMapper], which is the
 * unit the tests target. This class owns the coroutine and the state
 * holder and nothing else.
 *
 * **It owns no back stack, deliberately** [BR4.2, NFR14.30]. Switching
 * child replaces a field of the current state; there is nothing here
 * that could push a destination, which is what makes the Back
 * obligation satisfiable rather than merely asserted.
 */
class GuardianViewModel(
    private val repository: GuardianRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<GuardianUiState>(GuardianUiState.Idle)

    /** What the screen renders. */
    val state: StateFlow<GuardianUiState> = _state.asStateFlow()

    /** Load this guardian's children. */
    fun load() {
        _state.value = GuardianUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.children()) {
                    is AuthResult.Ok -> GuardianStateMapper.afterLoad(result.value)
                    is AuthResult.Refused -> GuardianStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        GuardianStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Show a different child, **replacing** the current view.
     *
     * No request is made and nothing is pushed: this is a selection
     * within one screen [BR4.2]. A call arriving in any state other
     * than [GuardianUiState.SeveralChildren] is ignored rather than
     * guessed at — there is no switcher drawn in those states, so such
     * a call did not come from the user.
     *
     * @param child The child to show instead
     */
    fun selectChild(child: GuardianChild) {
        val current = _state.value
        if (current !is GuardianUiState.SeveralChildren) return
        _state.value = GuardianStateMapper.afterChildSelected(current, child)
    }

    /** Repeat the load, and only when the user asks [TC-8, D-9]. */
    fun retry() = load()
}
