package com.shikkhokplus.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.EncryptedTokenStore
import com.shikkhokplus.app.core.network.HttpAuthRepository
import com.shikkhokplus.app.core.network.HttpBatchesRepository
import com.shikkhokplus.app.core.network.HttpRosterRepository
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.ui.BatchCreateForm
import com.shikkhokplus.app.core.ui.StudentAddForm
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.AuthViewModel
import com.shikkhokplus.app.feature.auth.ui.AuthScreen
import com.shikkhokplus.app.feature.batches.BatchesUiState
import com.shikkhokplus.app.feature.batches.BatchesViewModel
import com.shikkhokplus.app.feature.batches.ui.BatchesScreen
import com.shikkhokplus.app.feature.roster.RosterViewModel
import com.shikkhokplus.app.feature.roster.ui.RosterScreen

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
    // ENCRYPTED and persisted, so the device is remembered across
    // restarts and a returning teacher skips the OTP screen entirely.
    // Remembered so the store and client survive recomposition:
    // rebuilding them per frame would discard the session on every
    // state change.
    val context = androidx.compose.ui.platform.LocalContext.current
    val tokens = remember { EncryptedTokenStore.create(context) }
    val repository =
        remember {
            HttpAuthRepository(
                client = ApiClient.build(BuildConfig.API_BASE_URL, tokenStore = tokens),
                tokens = tokens,
            )
        }

    val model: AuthViewModel = viewModel { AuthViewModel(repository) }
    val state by model.state.collectAsState()

    // Try the stored token BEFORE the teacher is asked for anything.
    // Keyed on Unit so it runs once per composition rather than on
    // every state change -- a refresh per recomposition would rotate
    // the token repeatedly and trip the server's reuse detection.
    LaunchedEffect(Unit) { model.resumeSession(repository::refresh) }

    if (state is AuthUiState.SignedIn) {
        // The client is rebuilt so it picks up the token the verify
        // just stored. ApiClient reads the store per request, so this
        // is belt and braces rather than strictly required -- but the
        // store instance must be the SAME one, which is why it is
        // remembered above rather than created here.
        SignedInRoute(tokens)
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
 * What a signed-in teacher sees: their classes, and one class's roster.
 *
 * **Navigation is a single nullable id**, not a navigation library.
 * There are two screens; a graph, a back stack and a dependency to
 * carry them would be machinery in place of an `if`. It is replaced
 * the moment a third screen needs a real back stack, and saying that
 * here is cheaper than pretending the current shape scales.
 *
 * @param tokens The store holding this session's access token
 */
@androidx.compose.runtime.Composable
private fun SignedInRoute(tokens: TokenStore) {
    val client = remember { ApiClient.build(BuildConfig.API_BASE_URL, tokenStore = tokens) }
    // The NAME travels with the id, because the roster endpoint does
    // not return it -- the teacher already knows which class they
    // tapped, and a round trip to re-learn it would be the client
    // asking the server something it was just told.
    var openBatch by remember { mutableStateOf<Pair<String, String>?>(null) }
    var creatingBatch by remember { mutableStateOf(false) }
    var addingStudent by remember { mutableStateOf(false) }

    val batchesModel: BatchesViewModel =
        viewModel { BatchesViewModel(HttpBatchesRepository(client)) }
    val batchesState by batchesModel.state.collectAsState()

    LaunchedEffect(Unit) { batchesModel.load() }

    if (creatingBatch) {
        BatchCreateForm(
            onCreate = { name, subjects, fee, dueDay ->
                batchesModel.create(name, subjects, fee, dueDay)
                creatingBatch = false
            },
            onCancel = { creatingBatch = false },
        )
        BackHandler { creatingBatch = false }
        return
    }

    val opened = openBatch
    if (opened == null) {
        BatchesScreen(
            state = batchesState,
            onOpen = { id ->
                val name =
                    (batchesState as? BatchesUiState.Loaded)
                        ?.rows
                        ?.firstOrNull { it.id == id }
                        ?.name
                        .orEmpty()
                openBatch = id to name
            },
            onRetry = batchesModel::retry,
            onCreate = { creatingBatch = true },
        )
        return
    }

    // Keyed on the batch id so opening a different class builds a new
    // ViewModel rather than showing the previous roster while the new
    // one loads.
    val rosterModel: RosterViewModel =
        viewModel(key = opened.first) { RosterViewModel(HttpRosterRepository(client)) }
    val rosterState by rosterModel.state.collectAsState()

    LaunchedEffect(opened.first) { rosterModel.load(opened.first, opened.second) }

    if (addingStudent) {
        StudentAddForm(
            onAdd = { name, guardian, fee ->
                rosterModel.addStudent(name, guardian, fee)
                addingStudent = false
            },
            onCancel = { addingStudent = false },
        )
        BackHandler { addingStudent = false }
        return
    }

    BackHandler { openBatch = null }

    RosterScreen(
        state = rosterState,
        onRetry = rosterModel::retry,
        onAddStudent = { addingStudent = true },
    )
}
