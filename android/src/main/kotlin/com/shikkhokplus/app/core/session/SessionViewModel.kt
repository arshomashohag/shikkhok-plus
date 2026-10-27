package com.shikkhokplus.app.core.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.profile.ProfileRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds which lens the app is showing. Holds no business logic
 * [TC-9, D-31].
 *
 * **Reuses [ProfileRepository] rather than adding one.** `GET /v1/me`
 * already returns the lens list beside the name and address, so a
 * second repository over the same route would be two callers that can
 * disagree about one response.
 *
 * **The chosen lens lives here and nowhere else.** It is deliberately
 * NOT persisted to disk: it is a view selector, and a stored one
 * would be a cached role — the exact thing [TC-11, D-2] forbid,
 * because a seat accepted or removed between launches would leave the
 * device showing a lens the server no longer grants. Re-reading it
 * each launch costs one request that startup already makes.
 *
 * @property repository Where the lens list comes from
 */
class SessionViewModel(
    private val repository: ProfileRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<SessionUiState>(SessionUiState.Resolving)

    /** What the app routes on. */
    val state: StateFlow<SessionUiState> = _state.asStateFlow()

    /**
     * Read which lenses this account holds.
     *
     * Called once at startup, behind the loader the app already
     * shows, so the first screen rendered is the right one rather
     * than a teacher screen that corrects itself a second later.
     */
    fun resolve() {
        _state.value = SessionUiState.Resolving
        viewModelScope.launch {
            _state.value =
                when (val result = repository.profile()) {
                    is AuthResult.Ok -> SessionStateMapper.afterLoad(result.value)
                    is AuthResult.Refused ->
                        SessionStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        SessionStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Take one of the offered lenses.
     *
     * **Only a lens that was offered.** A caller naming one the
     * server did not list is ignored rather than honoured: the server
     * would refuse every screen behind it, so opening them would turn
     * a wrong tap into a wall of errors.
     *
     * @param lens The lens the person chose
     */
    fun choose(lens: Lens) {
        val offered = _state.value as? SessionUiState.Choosing ?: return
        if (offered.options.none { it.lens == lens }) return
        // `fromPicker = true`: reaching here means the list held more
        // than one, which is exactly what makes switching meaningful.
        _state.value = SessionUiState.Ready(lens, fromPicker = true)
    }

    /**
     * Go back to the picker.
     *
     * Reached from the More tab. Re-reads the list rather than
     * restoring the one it had, because a seat may have been accepted
     * or removed since: a stale picker would offer a lens the server
     * no longer grants.
     */
    fun switchLens() {
        resolve()
    }

    /**
     * Re-read the lens list without disturbing the current screen.
     *
     * **The quiet sibling of [switchLens], and the difference is
     * AC9.4.2.** Accepting a seat grants a lens the app does not yet
     * know about, so the list must be re-read or the person stays on
     * a bar that is missing the tabs they just earned. But
     * [switchLens] routes through [SessionUiState.Resolving], which
     * takes the whole graph out of composition — and tearing down an
     * open invitation list is the exact thing AC9.4.2 forbids, since
     * Back would then land in the newly granted lens's stack rather
     * than on the list.
     *
     * So this never publishes `Resolving`, and it never publishes
     * `Choosing` either: a person acting on a screen did not ask to
     * change roles, and interrupting them with a picker would be a
     * second thing they did not ask for. It upgrades a lens-free
     * session to the one lens that now exists and otherwise leaves
     * the state exactly as it was.
     */
    fun refreshLenses() {
        viewModelScope.launch {
            val result = repository.profile()
            if (result !is AuthResult.Ok) return@launch
            val resolved = SessionStateMapper.afterLoad(result.value)
            val current = _state.value

            _state.value =
                when {
                    // A lens-free session that now holds exactly one:
                    // take it, because there is nothing to choose and
                    // the person is waiting on those tabs.
                    current is SessionUiState.NoLens &&
                        resolved is SessionUiState.Ready -> resolved

                    // A lens-free session that now holds several:
                    // take the first rather than interrupt with a
                    // picker. The switcher is one tap away in More,
                    // and `fromPicker` makes it visible.
                    current is SessionUiState.NoLens &&
                        resolved is SessionUiState.Choosing ->
                        SessionUiState.Ready(
                            resolved.options.first().lens,
                            fromPicker = true,
                        )

                    // Already using a lens: leave it alone. Switching
                    // under someone mid-screen is never what they
                    // asked for.
                    else -> current
                }
        }
    }

    /** Try the lens list again after a failure. */
    fun retry() {
        resolve()
    }
}
