package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import kotlinx.coroutines.delay
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.core.session.LensOption
import com.shikkhokplus.app.core.session.SessionUiState

/**
 * What the signed-in root composes for one session state.
 *
 * **One value decides it, so one frame cannot disagree with itself**
 * [FR5.2, NFR3.12]. The choose-username flag travels inside
 * [SessionUiState] (`UsernameRequired(then)`), so the gate, the picker
 * and the graph are all chosen from the same value: there is no second
 * flag whose update could land a frame later and let the home show
 * first. `MainActivity.AppRoot` routes on this, and so does the
 * routing test, so the test drives the app's own decision.
 */
internal sealed interface RootRoute {
    /** The account read is in flight: the brand loader. */
    data object Loader : RootRoute

    /** A username must be chosen first: the gate, and nothing else. */
    data object Gate : RootRoute

    /**
     * More than one lens: the picker.
     *
     * @property options Every lens offered
     */
    data class Picker(val options: List<LensOption>) : RootRoute

    /**
     * The graph, for a lens or for none.
     *
     * @property lens The lens in use, or null (no seat yet, or the read
     *   failed and the lens-free graph keeps invitations reachable)
     * @property multiLens Whether "Switch role" has anywhere to go
     */
    data class Graph(val lens: Lens?, val multiLens: Boolean) : RootRoute
}

/**
 * Route one session state [FR5.2].
 *
 * **The gate comes before the picker**: a `UsernameRequired` state routes
 * to it whatever it would otherwise have held, and nothing of the held
 * state is composed until a choice succeeds.
 *
 * @param state What the session holds
 * @return What the root composes
 */
internal fun rootRouteFor(state: SessionUiState): RootRoute =
    when (state) {
        SessionUiState.Resolving -> RootRoute.Loader
        is SessionUiState.UsernameRequired -> RootRoute.Gate
        is SessionUiState.Choosing -> RootRoute.Picker(state.options)
        is SessionUiState.Ready -> RootRoute.Graph(state.lens, state.fromPicker)
        // No lens is not a failure, and a failure still routes to the
        // lens-free graph, where invitations and the profile work.
        SessionUiState.NoLens, is SessionUiState.Failed -> RootRoute.Graph(lens = null, multiLens = false)
    }

/** How often a failed account read is retried while the app is in front [NFR8.6]. */
internal const val RECHECK_INTERVAL_MS: Long = 30_000

/**
 * Re-read the account quietly while its last read failed [NFR3.13,
 * NFR8.6].
 *
 * **Why.** A failed read routes to the lens-free graph on purpose, so
 * invitations and the profile stay reachable; but then the
 * choose-username flag is unknown, and without this an account needing
 * a username could use the app for a whole session after one transient
 * failure, failing FR5.2 open. So while the state is `Failed` and the
 * app is in front, the account is read once on coming to the front and
 * then every [intervalMs]; a read that says `true` replaces the graph
 * with the gate at once.
 *
 * **Bounded.** It stops the moment the state leaves `Failed` or the app
 * leaves the front (the effect is keyed on both), so at most one read
 * per interval while the server stays unreachable, and none once a read
 * succeeds. The lifecycle is read as a state rather than through
 * `repeatOnLifecycle` so the wait runs on the composition's clock, which
 * is what lets the routing test drive the 30 seconds without waiting
 * them.
 *
 * @param state What the session holds
 * @param recheck Reads the account without publishing `Resolving`
 * @param intervalMs The wait between re-checks
 */
@Composable
internal fun FailedRecheckEffect(
    state: SessionUiState,
    recheck: () -> Unit,
    intervalMs: Long = RECHECK_INTERVAL_MS,
) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val stage by lifecycle.currentStateFlow.collectAsState()
    val active = state is SessionUiState.Failed && stage.isAtLeast(Lifecycle.State.STARTED)
    val latest by rememberUpdatedState(recheck)
    LaunchedEffect(active) {
        while (active) {
            latest()
            delay(intervalMs)
        }
    }
}
