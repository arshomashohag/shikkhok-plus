package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.core.network.HttpCentresRepository
import com.shikkhokplus.app.core.session.LocalWorkspaces
import com.shikkhokplus.app.feature.centres.CentreOffersViewModel
import com.shikkhokplus.app.feature.centres.MembersViewModel
import com.shikkhokplus.app.feature.centres.OpenCentreViewModel
import com.shikkhokplus.app.feature.centres.ui.CentreOffersScreen
import com.shikkhokplus.app.feature.centres.ui.CentreOffersSection
import com.shikkhokplus.app.feature.profile.ui.MoreActions
import com.shikkhokplus.app.feature.centres.ui.MembersActions
import com.shikkhokplus.app.feature.centres.ui.MembersScreen
import com.shikkhokplus.app.feature.centres.ui.OpenCentreScreen
import io.ktor.client.HttpClient

/**
 * Move the teacher screens into another workspace.
 *
 * **Everything is rebuilt.** The back stack, and every screen and
 * ViewModel on it, belongs to the workspace that was open; clearing it
 * means nothing read under one workspace is shown under another, and
 * each screen reads again with the new workspace's header.
 *
 * @param navController The controller to navigate with
 */
internal fun NavHostController.enterWorkspace() {
    navigate(Destination.Today.route) { popUpTo(0) { inclusive = true } }
}

/**
 * Coaching centres: opening one, its members, and centres' offers.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 * @param onAccountChanged Re-reads the account's lenses and workspaces
 */
internal fun NavGraphBuilder.centresRoutes(
    client: HttpClient,
    navController: NavHostController,
    onAccountChanged: () -> Unit,
) {
    composable(Destination.OpenCentre.route) {
        val workspaces = LocalWorkspaces.current
        val model: OpenCentreViewModel = viewModel { OpenCentreViewModel(HttpCentresRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(state.opened) {
            val centre = state.opened ?: return@LaunchedEffect
            // The opener is its first manager: move into it, and read the
            // account again so the switcher lists it.
            workspaces?.choose(centre.ownerId)
            onAccountChanged()
            navController.enterWorkspace()
        }
        OpenCentreScreen(
            state = state,
            onName = model::name,
            onManagerName = model::managerName,
            onOpen = model::open,
            onCancel = { navController.popBackStack() },
        )
    }

    composable(Destination.CentreMembers.route) {
        val model: MembersViewModel = viewModel { MembersViewModel(HttpCentresRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        MembersScreen(
            state = state,
            actions =
                MembersActions(
                    onInviteName = model::inviteName,
                    onInvitePhone = model::invitePhone,
                    onInviteRole = model::inviteRole,
                    onInvite = model::invite,
                    onRemove = model::revoke,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.CentreOffers.route) {
        val model: CentreOffersViewModel = viewModel { CentreOffersViewModel(HttpCentresRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        LaunchedEffect(state.accepted) { if (state.accepted > 0) onAccountChanged() }
        CentreOffersScreen(
            state = state,
            onAccept = model::accept,
            onDecline = model::decline,
            onBack = { navController.popBackStack() },
        )
    }
}

/**
 * The centres' offers, read and answered in place, for a screen that
 * shows them as a section.
 *
 * Accepting can open a centre workspace or a teaching lens, so the
 * account is read again.
 *
 * @param client The authenticated HTTP client
 * @param onAccepted Re-reads the account's lenses and workspaces
 * @return The section to draw
 */
@Composable
internal fun centreOffersSlot(client: HttpClient, onAccepted: () -> Unit): @Composable () -> Unit {
    val model: CentreOffersViewModel =
        viewModel(key = "centre-offers") { CentreOffersViewModel(HttpCentresRepository(client)) }
    val state by model.state.collectAsState()
    LaunchedEffect(Unit) { model.load() }
    LaunchedEffect(state.accepted) { if (state.accepted > 0) onAccepted() }
    return { CentreOffersSection(state, model::accept, model::decline) }
}

/**
 * More's actions, with the workspaces the server offers and switching
 * between them.
 *
 * @param navController The controller to navigate with
 * @param base The rows every lens has
 * @return The rows, with the workspace section's data
 */
@Composable
internal fun withWorkspaces(navController: NavHostController, base: MoreActions): MoreActions {
    val holder = LocalWorkspaces.current ?: return base
    val offered by holder.offered.collectAsState()
    val chosen by holder.state.collectAsState()
    return base.copy(
        workspaces = offered,
        currentWorkspace = offered.firstOrNull { it.ownerId == chosen } ?: offered.firstOrNull(),
        onSwitchWorkspace = { id ->
            holder.choose(id)
            navController.enterWorkspace()
        },
    )
}

/**
 * Whether the workspace in effect is a coaching centre.
 *
 * @return True inside a centre
 */
@Composable
internal fun rememberInCentre(): Boolean {
    val holder = LocalWorkspaces.current ?: return false
    val offered by holder.offered.collectAsState()
    val chosen by holder.state.collectAsState()
    return (offered.firstOrNull { it.ownerId == chosen } ?: offered.firstOrNull())?.isCentre == true
}

/**
 * A centre-only row's action: null outside a centre, where the screen
 * would only be refused.
 *
 * @param base The rows so far, carrying the workspace in effect
 * @param route Where the row leads
 * @param navigate Opens a route
 * @return The action, or null outside a centre
 */
internal fun centreOpener(base: MoreActions, route: String, navigate: (String) -> Unit): (() -> Unit)? =
    if (base.currentWorkspace?.isCentre == true) ({ navigate(route) }) else null
