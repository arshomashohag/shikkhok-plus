package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.core.network.HttpBatchesRepository
import com.shikkhokplus.app.core.network.HttpRosterRepository
import com.shikkhokplus.app.core.network.HttpSignupRepository
import com.shikkhokplus.app.core.ui.BatchCreateForm
import com.shikkhokplus.app.core.ui.StudentAddForm
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.AuthViewModel
import com.shikkhokplus.app.feature.auth.SignupViewModel
import com.shikkhokplus.app.feature.auth.ui.AuthScreen
import com.shikkhokplus.app.feature.auth.ui.SignupScreen
import com.shikkhokplus.app.feature.batches.BatchesUiState
import com.shikkhokplus.app.feature.batches.BatchesViewModel
import com.shikkhokplus.app.feature.batches.ui.BatchesScreen
import com.shikkhokplus.app.feature.roster.RosterViewModel
import com.shikkhokplus.app.feature.roster.ui.RosterScreen
import io.ktor.client.HttpClient

/**
 * The navigation graph.
 *
 * **Replaces the nullable-id routing `MainActivity` carried**, which
 * said of itself: "It is replaced the moment a third screen needs a
 * real back stack." That moment had passed unnoticed — 23 screens were
 * built against 3 that could be reached.
 *
 * This graph covers the signed-out and teacher paths. The fee,
 * attendance, marks, guardian, invitations, profile, overview and dues
 * screens are **deliberately absent**: each is missing its HTTP
 * repository, its ViewModel, or both, so routing to one would open a
 * screen that cannot load. Adding a route before its network layer
 * would trade an invisible gap for a visible broken screen.
 *
 * @param client The authenticated HTTP client for signed-in routes
 * @param signedIn Whether a session was restored before first render
 * @param navController The host's controller
 * @param modifier The layout modifier
 */
@Composable
fun ShikhokNavHost(
    client: HttpClient,
    signedIn: Boolean,
    navController: NavHostController,
    authModel: AuthViewModel,
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        startDestination =
            if (signedIn) Destination.Batches.route else Destination.Auth.route,
        modifier = modifier,
    ) {
        composable(Destination.Auth.route) {
            val state by authModel.state.collectAsState()

            // **The jump to Batches happens here, not inside the
            // screen.** A screen that navigates is a screen that cannot
            // be tested without a NavController, and this one is
            // already covered by Robolectric tests that pass a state
            // and assert what renders.
            LaunchedEffect(state) {
                if (state is AuthUiState.SignedIn) {
                    navController.navigate(Destination.Batches.route) {
                        // The auth screen leaves the back stack: a
                        // signed-in person pressing Back should leave
                        // the app, not return to an OTP field that
                        // would re-issue a code.
                        popUpTo(Destination.Auth.route) { inclusive = true }
                    }
                }
            }

            AuthScreen(
                state = state,
                onRequestCode = authModel::requestCode,
                onSubmitCode = authModel::submitCode,
                onRetry = authModel::retry,
                onGoToSignup = { navController.navigate(Destination.Signup.route) },
            )
        }

        composable(Destination.Signup.route) {
            // The signup client is UNAUTHENTICATED by necessity: the
            // person has no account yet, so there is no token to send.
            val model: SignupViewModel =
                viewModel { SignupViewModel(HttpSignupRepository(client)) }
            val state by model.state.collectAsState()

            SignupScreen(
                state = state,
                onPhoneLookup = model::lookup,
                onSubmit = { name, address, role ->
                    model.submit(
                        phone = model.lastPhone,
                        selfName = name,
                        address = address,
                        role = role,
                    )
                },
                // **Back to sign-in, not forward to it.** Signup issues
                // an OTP and does not authenticate, so the person
                // finishes on the screen they started from — which is
                // already on the stack.
                onGoToLogin = { navController.popBackStack() },
                onRetry = model::retry,
            )
        }

        composable(Destination.Batches.route) {
            val model: BatchesViewModel =
                viewModel { BatchesViewModel(HttpBatchesRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            BatchesScreen(
                state = state,
                onOpen = { id ->
                    val name =
                        (state as? BatchesUiState.Loaded)
                            ?.rows
                            ?.firstOrNull { it.id == id }
                            ?.name
                            .orEmpty()
                    navController.navigate(Destination.Roster.of(id, name))
                },
                onRetry = model::retry,
                onCreate = { navController.navigate(Destination.CreateBatch.route) },
            )
        }

        composable(Destination.CreateBatch.route) { entry ->
            // The ViewModel is scoped to the LIST entry, not to this
            // form, so a created class appears in the list the form
            // returns to rather than needing a reload.
            val parent =
                remember(entry) {
                    navController.getBackStackEntry(Destination.Batches.route)
                }
            val model: BatchesViewModel =
                viewModel(parent) { BatchesViewModel(HttpBatchesRepository(client)) }

            BatchCreateForm(
                onCreate = { name, subjects, fee, dueDay ->
                    model.create(name, subjects, fee, dueDay)
                    navController.popBackStack()
                },
                onCancel = { navController.popBackStack() },
            )
        }

        composable(
            route = Destination.Roster.route,
            arguments =
                listOf(
                    navArgument(Destination.Roster.ARG_ID) { type = NavType.StringType },
                    navArgument(Destination.Roster.ARG_NAME) {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                ),
        ) { entry ->
            val id = entry.arguments?.getString(Destination.Roster.ARG_ID).orEmpty()
            val name = entry.arguments?.getString(Destination.Roster.ARG_NAME).orEmpty()

            val model: RosterViewModel =
                viewModel(key = id) { RosterViewModel(HttpRosterRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(id) { model.load(id, name) }

            RosterScreen(
                state = state,
                onRetry = model::retry,
                onAddStudent = { navController.navigate(Destination.AddStudent.of(id)) },
            )
        }

        composable(
            route = Destination.AddStudent.route,
            arguments =
                listOf(
                    navArgument(Destination.Roster.ARG_ID) { type = NavType.StringType },
                ),
        ) { entry ->
            val id = entry.arguments?.getString(Destination.Roster.ARG_ID).orEmpty()

            // Same reasoning as CreateBatch: the roster's ViewModel, so
            // the added student is in the list this form returns to.
            val parent =
                remember(entry) {
                    navController.getBackStackEntry(Destination.Roster.route)
                }
            val model: RosterViewModel =
                viewModel(parent, key = id) {
                    RosterViewModel(HttpRosterRepository(client))
                }

            StudentAddForm(
                onAdd = { name, guardian, fee ->
                    model.addStudent(name, guardian, fee)
                    navController.popBackStack()
                },
                onCancel = { navController.popBackStack() },
            )
        }
    }
}
