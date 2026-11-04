package com.shikkhokplus.app.feature.guardian

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.ui.RefreshGate
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

    private val gate = RefreshGate()

    /** Whether a pull-to-refresh is in flight. */
    val refreshing: StateFlow<Boolean> = gate.refreshing

    /** Load this guardian's children, keeping the shown child if still there. */
    fun load() {
        val shown = shownChild()
        _state.value = GuardianUiState.Loading
        viewModelScope.launch { _state.value = read { shown } }
    }

    /**
     * Re-read on a pull, keeping the screen until the answer arrives.
     *
     * The child to keep is read when the answer lands, not when the
     * pull starts: a guardian who switches child while the refresh is
     * in flight keeps the child they switched to [BR4.2]. Started only
     * by the person pulling [TC-8, D-9].
     */
    fun refresh() {
        gate.run(viewModelScope) { _state.value = read(::shownChild) }
    }

    private fun shownChild(): String? = (_state.value as? GuardianUiState.Loaded)?.child?.key

    /**
     * Read the children and keep the shown one if it is still there.
     *
     * @param shown Which child to keep, asked once the answer is in
     * @return The state to show
     */
    private suspend fun read(shown: () -> String?): GuardianUiState =
        when (val result = repository.home()) {
            is AuthResult.Ok -> {
                val phone =
                    if (result.value.children.isEmpty()) {
                        (repository.me() as? AuthResult.Ok)?.value?.phone
                    } else {
                        null
                    }
                val loaded = GuardianStateMapper.afterLoad(result.value, phone)
                val keep = shown()
                if (loaded is GuardianUiState.Loaded && keep != null) {
                    GuardianStateMapper.select(loaded, loaded.children.indexOfFirst { it.key == keep })
                } else {
                    loaded
                }
            }
            is AuthResult.Refused -> GuardianStateMapper.afterError(result.envelope)
            // **Offline keeps this session's children** (G1), marked so:
            // results stay, payments are withheld until they can be
            // confirmed, so a guardian never pays against a stale figure.
            AuthResult.TransportFailure ->
                lastLoaded?.copy(offline = true) ?: GuardianStateMapper.afterTransportFailure()
        }.also { if (it is GuardianUiState.Loaded && !it.offline) lastLoaded = it }

    /** The children the server returned last this session, for offline. */
    private var lastLoaded: GuardianUiState.Loaded? = null

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
