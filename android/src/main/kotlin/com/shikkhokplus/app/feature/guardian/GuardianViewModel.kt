package com.shikkhokplus.app.feature.guardian

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What the guardian home needs from the network. */
interface GuardianRepository {
    /**
     * Read every child this guardian accepted, with their summaries.
     *
     * The route names no child: the server resolves the seats from the
     * authenticated account [BR4.1, NFR14.29].
     *
     * @return The children, an error envelope, or a transport failure
     */
    suspend fun home(): AuthResult<GuardianHomeDto>

    /**
     * Read the guardian's own account, for the empty state's number.
     *
     * @return The account, or a failure
     */
    suspend fun me(): AuthResult<MeDto>
}

/**
 * Holds the guardian home's state. Holds no business logic [TC-9, D-31].
 *
 * **It owns no back stack, deliberately** [BR4.2, NFR14.30]. Switching
 * child replaces a field of the current state; nothing here could push
 * a destination.
 *
 * @property repository The network
 */
class GuardianViewModel(
    private val repository: GuardianRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<GuardianUiState>(GuardianUiState.Idle)

    /** What the screen renders. */
    val state: StateFlow<GuardianUiState> = _state.asStateFlow()

    /** Load this guardian's children, keeping the shown child if still there. */
    fun load() {
        val shown = (_state.value as? GuardianUiState.Loaded)?.child?.key
        _state.value = GuardianUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.home()) {
                    is AuthResult.Ok -> {
                        val phone =
                            if (result.value.children.isEmpty()) {
                                (repository.me() as? AuthResult.Ok)?.value?.phone
                            } else {
                                null
                            }
                        val loaded = GuardianStateMapper.afterLoad(result.value, phone)
                        if (loaded is GuardianUiState.Loaded && shown != null) {
                            GuardianStateMapper.select(loaded, loaded.children.indexOfFirst { it.key == shown })
                        } else {
                            loaded
                        }
                    }
                    is AuthResult.Refused -> GuardianStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure -> GuardianStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Show a different child, **replacing** the current one [BR4.2].
     *
     * @param index The child's place in the list
     */
    fun select(index: Int) {
        val current = _state.value as? GuardianUiState.Loaded ?: return
        _state.value = GuardianStateMapper.select(current, index)
    }

    /** Repeat the load, and only when the user asks [TC-8, D-9]. */
    fun retry() = load()
}
