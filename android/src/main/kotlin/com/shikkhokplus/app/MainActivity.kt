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
import androidx.compose.runtime.remember
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
import com.shikkhokplus.app.core.network.EncryptedTokenStore
import com.shikkhokplus.app.core.network.HttpAuthRepository
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.AuthViewModel
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
    val client =
        remember { ApiClient.build(BuildConfig.API_BASE_URL, tokenStore = tokens) }
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

    val navController = rememberNavController()

    ShikkhokNavHost(
        client = client,
        // Read ONCE, now that it is settled. A live value here would
        // rebuild the whole NavHost the moment the state changed,
        // discarding the back stack with it.
        signedIn = remember { authState is AuthUiState.SignedIn },
        navController = navController,
        authModel = authModel,
    )
}
