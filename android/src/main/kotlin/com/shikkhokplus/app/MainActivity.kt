package com.shikkhokplus.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.FullScreenLoader
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.network.HttpAttendanceRepository
import com.shikkhokplus.app.core.queue.keepDraining
import com.shikkhokplus.app.core.queue.QueueSync
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.Lifecycle
import androidx.compose.ui.platform.LocalLifecycleOwner
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.core.session.SessionUiState
import com.shikkhokplus.app.core.session.SessionViewModel
import com.shikkhokplus.app.core.session.ui.LensPickerScreen
import com.shikkhokplus.app.core.network.HttpProfileRepository
import com.shikkhokplus.app.core.network.EncryptedTokenStore
import com.shikkhokplus.app.core.network.HttpAuthRepository
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.AuthViewModel
import com.shikkhokplus.app.navigation.SessionBinding
import com.shikkhokplus.app.navigation.ShikkhokNavHost

/**
 * The single Activity, hosting the navigation graph.
 *
 * **The routing moved out.** This file previously carried navigation as
 * a nullable batch id and two booleans, with a note saying that shape
 * "is replaced the moment a third screen needs a real back stack". That
 * moment had already passed without anyone noticing: 23 screens were
 * built and three were reachable, so self-registration existed in the
 * binary and nothing could open it.
 *
 * The base URL comes from `BuildConfig`, set per build type:
 *
 * - **debug** defaults to `http://10.0.2.2:8000`, the emulator's route
 *   to the host machine. Override with `-PapiBaseUrl=...` for a
 *   physical phone on the same wifi, or for staging.
 * - **release** has **no default**, because every possible default is
 *   wrong: a developer's machine shipped to a phone, or a production
 *   host reached from a test build. An unconfigured release build says
 *   so on screen instead of failing with a network error.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            ShikkhokTheme {
                Surface(
                    // **safeDrawing, not statusBars.** It covers the
                    // status bar, the navigation bar AND the display
                    // cutout, which is what a phone with a notch
                    // actually needs. Without this the first field
                    // rendered UNDER the status bar and was half
                    // hidden -- found on a real device, not in any
                    // test, because a test renders with no insets at
                    // all and passes either way.
                    modifier = Modifier.windowInsetsPadding(
                        WindowInsets.safeDrawing,
                    ),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    if (BuildConfig.API_BASE_URL.isBlank()) {
                        UnconfiguredNotice()
                    } else {
                        AppRoot()
                    }
                }
            }
        }
    }
}

/**
 * What an unconfigured build shows.
 *
 * **Not a crash and not a network error.** A build with no backend
 * configured is a build mistake, and saying so is more useful than
 * letting it surface as "could not reach the server" — which sends
 * whoever sees it to look at the network.
 */
@Composable
private fun UnconfiguredNotice() {
    Column(Modifier.fillMaxWidth().padding(24.dp)) {
        Text("No backend configured", style = MaterialTheme.typography.titleMedium)
        Text(
            "This build was assembled without an API base URL. Rebuild " +
                "with -PapiBaseUrl=https://your-staging-host",
            Modifier.padding(top = 8.dp),
        )
    }
}

/**
 * Builds the session-scoped dependencies and starts the graph.
 *
 * The token store and client are **remembered**, not rebuilt per
 * frame: recreating them on recomposition would discard the session on
 * every state change. The store instance must be the same one
 * throughout, which is why it is created here rather than inside the
 * graph.
 */
@Composable
private fun AppRoot() {
    val context = LocalContext.current
    val tokens = remember { EncryptedTokenStore.create(context) }
    // **One queue for the whole app, not one per screen.** The pending
    // attendance writes are a single ordered list [BR3.5]; a store
    // built per route would split that list by screen, and a write
    // queued on one would be invisible to the retry on another.
    val queue =
        remember { QueueStore(java.io.File(context.filesDir, "attendance-queue.json")) }
    // Raised from the network layer, off the main thread, when an
    // expired session could not be renewed; handled below by the same
    // `endSession` sign-out uses. A snapshot state is safe to write
    // from any thread, which is why it is the bridge.
    var sessionLapsed by remember { mutableStateOf(false) }
    val client =
        remember {
            ApiClient.build(
                BuildConfig.API_BASE_URL,
                tokenStore = tokens,
                onSessionEnded = { sessionLapsed = true },
            )
        }
    val repository = remember { HttpAuthRepository(client = client, tokens = tokens) }

    val authModel: AuthViewModel = viewModel { AuthViewModel(repository) }
    val authState by authModel.state.collectAsState()

    // Try the stored token BEFORE anyone is asked for anything. Keyed
    // on Unit so it runs once per composition rather than on every
    // state change -- a refresh per recomposition would rotate the
    // token repeatedly and trip the server's reuse detection.
    LaunchedEffect(Unit) { authModel.resumeSession(repository::refresh) }

    // **The session is checked BEFORE anything is routed.** Previously
    // `signedIn` was read before `resumeSession` had finished, so it was
    // always false: the graph started at the sign-in screen and jumped
    // to the home screen a second or two later once the refresh landed.
    // A returning teacher saw a login screen they never had to use.
    //
    // Now the ViewModel starts at `Restoring`, the app shows the brand
    // loader, and the graph is not built until the answer is known — so
    // the start destination is correct on the first frame and there is
    // nothing to jump away from.
    if (authState is AuthUiState.Restoring) {
        FullScreenLoader(label = stringResource(R.string.auth_restoring))
        return
    }

    // **Live, not remembered.** An earlier draft of this line read
    // `remember { ... }`, which pins the value to the FIRST
    // composition -- so a person who signs in during this session
    // stayed `false` here, the lens was never resolved, and a teacher
    // who had just entered their code got the lens-free bar.
    //
    // The NavHost below still takes a remembered value for its start
    // destination, and must: a live value THERE rebuilds the graph and
    // discards the back stack. The two uses genuinely differ.
    val signedIn = authState is AuthUiState.SignedIn

    // **The lens is resolved BEFORE the graph is built**, behind the
    // loader already showing. Routing everyone to the teacher home
    // and correcting a second later would be the same flash this file
    // already fixed once for the sign-in screen -- except worse,
    // because the wrong screen here is one the server refuses.
    val sessionModel: SessionViewModel =
        viewModel { SessionViewModel(HttpProfileRepository(client)) }
    val sessionState by sessionModel.state.collectAsState()

    // Only for someone who IS signed in: a signed-out person has no
    // token, so asking would be a guaranteed 401 before the OTP
    // screen. Keyed on `signedIn` so it fires again the moment someone
    // signs in mid-session, which is the whole reason that value is
    // live rather than remembered.
    LaunchedEffect(signedIn) { if (signedIn) sessionModel.resolve() }

    val lens: Lens?
    // Whether there is anything to switch TO. Resolved alongside the
    // lens because only the picker's own list knows: a person with
    // one lens is offered nothing, and offering it anyway would send
    // them to a picker that immediately picks for them.
    var multiLens = false
    if (signedIn) {
        when (val resolved = sessionState) {
            SessionUiState.Resolving -> {
                FullScreenLoader(label = stringResource(R.string.auth_restoring))
                return
            }

            is SessionUiState.Choosing -> {
                // **The person chooses, because the server sends no
                // default** [TC-11, D-2]. Returning here rather than
                // routing means the picker is not a back-stack entry:
                // Back from the home screen leaves the app rather than
                // returning to a choice already made.
                LensPickerScreen(
                    options = resolved.options,
                    onChoose = sessionModel::choose,
                )
                return
            }

            is SessionUiState.Ready -> {
                lens = resolved.lens
                multiLens = resolved.fromPicker
            }

            // **No lens is not a failure.** A fresh signup holds no
            // seat until a teacher adds them, and the graph sends a
            // null lens to invitations -- which is lens-exempt on the
            // server for exactly this case [BR1.3].
            SessionUiState.NoLens -> lens = null

            // A failure also routes to the lens-free home rather than
            // stranding the person on an error page: invitations and
            // the profile both work without a lens, so they can at
            // least see their own row and try again.
            is SessionUiState.Failed -> lens = null
        }
    } else {
        lens = null
    }

    // **The queue drains while the app is open and someone is signed
    // in.** It was built and never started, so attendance saved offline
    // or after a failed send never left the phone [BR3.1]. Keyed on
    // `signedIn` so it starts at sign-in and stops at sign-out; scoped
    // to STARTED so it never runs in the background.
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(signedIn) {
        if (signedIn) {
            val sync = QueueSync(queue, HttpAttendanceRepository(client)::submit)
            lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
                keepDraining(sync, queue)
            }
        }
    }

    // **One way to end a session, used by sign-out and deletion.** It
    // wipes the stored tokens and the device's queue -- left in place,
    // the next person to sign in on this phone would send this
    // account's rosters under their own token -- and returns to sign-in.
    val endSession = {
        queue.clear()
        tokens.clear()
        authModel.signOut()
    }

    // **A session the server will not renew ends here, cleanly.** Left
    // signed in with a dead credential, every screen fails and nothing
    // says why; ending it routes to sign-in, as sign-out does.
    LaunchedEffect(sessionLapsed) {
        if (sessionLapsed) {
            endSession()
            sessionLapsed = false
        }
    }

    // **Keyed on `signedIn`, so a session change rebuilds the graph.**
    // Only then: within a session the start destination is still read
    // once, for the reason below. When a session ends, every screen and
    // ViewModel holding the old account's data is discarded with the
    // back stack, rather than left one Back press away.
    key(signedIn) {
        val navController = rememberNavController()

        ShikkhokNavHost(
            client = client,
            queue = queue,
            session =
                SessionBinding(
                    lens = lens,
                    onSwitch = if (multiLens) sessionModel::switchLens else null,
                    onLensesChanged = sessionModel::refreshLenses,
                    onEndSession = endSession,
                    unsentWrites = { queue.read().size },
                ),
            // Read ONCE per session. A live value here would rebuild the
            // whole NavHost on every change, discarding the back stack.
            signedIn = remember { signedIn },
            navController = navController,
            authModel = authModel,
        )
    }
}
