package com.shikkhokplus.app.navigation

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.BuildConfig
import com.shikkhokplus.app.core.network.HttpProfileRepository
import com.shikkhokplus.app.core.offline.LocalOfflineCopies
import com.shikkhokplus.app.core.offline.OfflineProfileRepository
import com.shikkhokplus.app.core.offline.keptBy
import com.shikkhokplus.app.feature.profile.ProfileUiState
import com.shikkhokplus.app.feature.profile.ProfileViewModel
import com.shikkhokplus.app.feature.profile.ui.LogOutSheet
import com.shikkhokplus.app.feature.profile.ui.MoreActions
import com.shikkhokplus.app.feature.profile.ui.ProfileScreen
import io.ktor.client.HttpClient

/**
 * More (T9, S4, G4): the account screen every lens reaches, with the rows
 * its lens supplies.
 *
 * **Its own function so a test can drive it**, as `guardianHomeRoute` is:
 * a row More draws is an action, and an action is proven by tapping it on
 * the real route [H5]. The graph registers it exactly where it was.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 * @param session The signed-in session
 */
internal fun NavGraphBuilder.moreRoute(
    client: HttpClient,
    navController: NavHostController,
    session: SessionBinding,
) {
    composable(Destination.Profile.route) {
        val copies = LocalOfflineCopies.current
        val model: ProfileViewModel =
            viewModel {
                val network = HttpProfileRepository(client)
                ProfileViewModel(network.keptBy(copies, ::OfflineProfileRepository))
            }
        val state by model.state.collectAsState()
        val summary by model.summary.collectAsState()
        var confirmingSignOut by remember { mutableStateOf(false) }

        // Re-read on every visit, except straight back from a save:
        // the save already returned the profile, and a read would
        // replace "Saved." with a loader before anyone saw it.
        LaunchedEffect(Unit) {
            if (model.state.value !is ProfileUiState.Saved) model.load()
        }

        ProfileScreen(
            state = state,
            lens = session.lens,
            summary = summary,
            version = BuildConfig.VERSION_NAME,
            actions = moreActionsFor(
                lens = session.lens,
                base =
                    withWorkspaces(
                        navController,
                        MoreActions(
                        onEdit = {
                            model.edit()
                            navController.navigate(Destination.EditProfile.route)
                        },
                        onSignOut = { confirmingSignOut = true },
                        onDeleteAccount = {
                            model.startDeletion()
                            navController.navigate(Destination.DeleteAccount.route)
                        },
                        onRetry = model::retry,
                        onSwitchLens = session.onSwitch,
                        onSettings = settingsOpener(session, navController),
                        unsent = remember { session.unsentWrites() },
                        // The status the session already read: More
                        // makes no request of its own for the mark.
                        twoStepRecommended =
                            session.mfaStatus?.state?.collectAsState()?.value?.showRecommended == true,
                    ).withAccountRows(
                        accountRowsFor(summary) { route -> navController.navigate(route) }
                            .takeIf { session.tokens != null },
                    ),
                    ),
                navigate = { route -> navController.navigate(route) },
            ).copy(
                // Any lens: whoever sent a join request can withdraw it [H5].
                onMyEnquiries = myEnquiriesOpener(client) { navController.navigate(Destination.HubMyEnquiries.route) },
            ),
            bottomBar = { LensBar(session.lens, Destination.Profile.route, navController) },
            // Pushed from a family home's profile button, so it has
            // a way back; a teacher reaches it as a tab and needs none.
            onBack = { navController.popBackStack(); Unit }.takeIf { isFamily(session.lens) },
        )

        if (confirmingSignOut) {
            LogOutSheet(
                unsent = remember { session.unsentWrites() },
                onConfirm = {
                    confirmingSignOut = false
                    session.onEndSession()
                },
                onDismiss = { confirmingSignOut = false },
            )
        }
    }
}
