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
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.BottomNav
import com.shikkhokplus.app.core.designsystem.NavDestination
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.network.HttpAnalyticsRepository
import com.shikkhokplus.app.feature.dues.DuesViewModel
import com.shikkhokplus.app.feature.dues.ui.DuesScreen
import com.shikkhokplus.app.feature.overview.OverviewViewModel
import com.shikkhokplus.app.feature.overview.ui.OverviewScreen
import com.shikkhokplus.app.core.network.HttpBatchesRepository
import com.shikkhokplus.app.core.network.HttpRosterRepository
import com.shikkhokplus.app.core.network.HttpSignupRepository
import com.shikkhokplus.app.core.ui.BatchCreateForm
import com.shikkhokplus.app.core.ui.StudentAddForm
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.AuthViewModel
import com.shikkhokplus.app.feature.auth.SignupUiState
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
fun ShikkhokNavHost(
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

            // **On success, go to the code screen.** Signup issues an
            // OTP and does not authenticate, so the person's next step
            // is entering that code. Leaving them on a "we sent a
            // code" message with no field to type it into is a second
            // dead end one screen further along.
            //
            // `popBackStack` rather than `navigate`: auth is already
            // on the stack beneath this, so returning to it keeps one
            // auth screen rather than stacking a second.
            LaunchedEffect(state) {
                val sent = state
                if (sent is SignupUiState.CodeSent) {
                    // The auth ViewModel is shared with the screen we
                    // are returning to, and it has issued nothing
                    // itself — so it is told a code is outstanding and
                    // which number it went to. Without this it would
                    // show the number field and invite a second code,
                    // invalidating the one the person is holding.
                    authModel.adoptPendingCode(sent.codeSentTo)
                    navController.popBackStack()
                }
            }

            SignupScreen(
                state = state,
                onSubmit = { phone, name, address, role ->
                    model.submit(
                        phone = phone,
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
                // **All four tabs, three of them disabled.** Today,
                // Dues and More have no HTTP repository and no
                // ViewModel yet, so opening one would show a screen
                // that cannot load. Hiding them instead would make the
                // bar change shape as each unit lands, and a person
                // who has seen four tabs once expects four.
                bottomBar = {
                    BottomNav(
                        destinations = teacherTabs(),
                        selectedIndex = TAB_BATCHES,
                        onSelect = { navController.switchTab(it) },
                    )
                },
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

        composable(Destination.Overview.route) {
            val model: OverviewViewModel =
                viewModel { OverviewViewModel(HttpAnalyticsRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            OverviewScreen(
                state = state,
                onRetry = model::retry,
                bottomBar = {
                    BottomNav(
                        destinations = teacherTabs(),
                        selectedIndex = TAB_OVERVIEW,
                        onSelect = { navController.switchTab(it) },
                    )
                },
            )
        }

        composable(Destination.Dues.route) {
            val model: DuesViewModel =
                viewModel { DuesViewModel(HttpAnalyticsRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            DuesScreen(
                state = state,
                onRetry = model::retry,
                bottomBar = {
                    BottomNav(
                        destinations = teacherTabs(),
                        selectedIndex = TAB_DUES,
                        onSelect = { navController.switchTab(it) },
                    )
                },
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

            // **Wrapped in the scaffold the form no longer carries.**
            // The form is pure content now, so the app bar, the margin
            // and the back affordance come from here. Rendering it bare
            // gave a screen with no title at all once its own heading
            // was removed.
            ScreenScaffold(
                title = stringResource(R.string.screen_title_create_batch),
                onBack = { navController.popBackStack() },
            ) {
                BatchCreateForm(
                    onCreate = { name, subjects, fee, dueDay ->
                        model.create(name, subjects, fee, dueDay)
                        navController.popBackStack()
                    },
                    onCancel = { navController.popBackStack() },
                )
            }
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

            ScreenScaffold(
                title = stringResource(R.string.screen_title_add_student),
                onBack = { navController.popBackStack() },
            ) {
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
}

/** Today's position in the teacher's bar. */
private const val TAB_OVERVIEW = 0

/** The Batches tab's position in the teacher's bar. */
private const val TAB_BATCHES = 1

/** The Dues tab's position. */
private const val TAB_DUES = 2

/**
 * Switch to a tab, as a tab rather than a push.
 *
 * **`popUpTo` the start destination, `saveState`, `launchSingleTop`.**
 * Without these, tapping between tabs grows the back stack forever and
 * Back walks a person through every tab they have ever visited rather
 * than leaving the app. `restoreState` brings each tab back where they
 * left it, so a half-scrolled list is not reset by a trip to another
 * tab.
 *
 * An unbuilt tab is simply ignored: the bar disables those, and this
 * refuses them again rather than trusting the caller.
 *
 * @param index Which tab was chosen
 */
private fun NavHostController.switchTab(index: Int) {
    val route =
        when (index) {
            TAB_OVERVIEW -> Destination.Overview.route
            TAB_BATCHES -> Destination.Batches.route
            TAB_DUES -> Destination.Dues.route
            else -> return
        }
    if (currentDestination?.route == route) return

    navigate(route) {
        popUpTo(graph.startDestinationId) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/**
 * The teacher's four destinations, as the design fixes them.
 *
 * Only Batches is enabled. The other three are declared here so the
 * bar has its real shape from the first build, and each becomes
 * enabled when its repository and ViewModel land.
 *
 * @return The tabs, in the design's order
 */
@Composable
private fun teacherTabs(): List<NavDestination> =
    listOf(
        NavDestination(
            label = stringResource(R.string.nav_today),
            icon = painterResource(R.drawable.ic_nav_today),
            tag = "nav_tab_today",
        ),
        NavDestination(
            label = stringResource(R.string.nav_batches),
            icon = painterResource(R.drawable.ic_nav_batches),
            tag = "nav_tab_batches",
        ),
        NavDestination(
            label = stringResource(R.string.nav_dues),
            icon = painterResource(R.drawable.ic_nav_dues),
            tag = "nav_tab_dues",
        ),
        NavDestination(
            label = stringResource(R.string.nav_more),
            icon = painterResource(R.drawable.ic_nav_more),
            tag = "nav_tab_more",
            enabled = false,
        ),
    )
