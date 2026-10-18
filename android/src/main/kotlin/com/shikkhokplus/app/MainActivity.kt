package com.shikkhokplus.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.HttpAuthRepository
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.AuthViewModel
import com.shikkhokplus.app.feature.auth.ui.AuthScreen

/**
 * The single Activity. Screen one is OTP entry.
 *
 * **The device leg, finally wired.** B3 left a placeholder repository
 * here that returned a transport failure, so the screen rendered its
 * offline state rather than pretending to succeed. That placeholder was
 * honest and it is now replaced with the real client.
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
            MaterialTheme {
                Surface {
                    if (BuildConfig.API_BASE_URL.isBlank()) {
                        UnconfiguredNotice()
                    } else {
                        SignInRoute()
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
@androidx.compose.runtime.Composable
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
 * The sign-in screen, wired to the real backend.
 */
@androidx.compose.runtime.Composable
private fun SignInRoute() {
    // Remembered so the token store and the client survive
    // recomposition: rebuilding them per frame would discard the
    // session on every state change.
    val tokens = remember { TokenStore.InMemory() }
    val repository =
        remember {
            HttpAuthRepository(
                client = ApiClient.build(BuildConfig.API_BASE_URL, tokenStore = tokens),
                tokens = tokens,
            )
        }

    val model: AuthViewModel = viewModel { AuthViewModel(repository) }
    val state by model.state.collectAsState()

    if (state is AuthUiState.SignedIn) {
        SignedInNotice()
        return
    }

    AuthScreen(
        state = state,
        onRequestCode = model::requestCode,
        onSubmitCode = model::submitCode,
        onRetry = model::retry,
    )
}

/**
 * The end of the device leg.
 *
 * **Deliberately minimal.** What it proves is that a Compose screen
 * reached a real FastAPI endpoint against a real database through a
 * real OTP — which is the walking skeleton's whole claim. The batch and
 * roster screens follow; putting them here before the sign-in path is
 * verified on a device would confuse two things that can fail
 * independently.
 */
@androidx.compose.runtime.Composable
private fun SignedInNotice() {
    Column(Modifier.fillMaxWidth().padding(24.dp)) {
        Text("Signed in", style = MaterialTheme.typography.titleMedium)
        Text(
            "The code was verified by the server and a session exists.",
            Modifier.padding(top = 8.dp),
        )
    }
}
