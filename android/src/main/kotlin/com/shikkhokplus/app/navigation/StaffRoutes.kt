package com.shikkhokplus.app.navigation

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.core.network.HttpStaffRepository
import com.shikkhokplus.app.feature.staff.StaffFormMode
import com.shikkhokplus.app.feature.staff.StaffFormViewModel
import com.shikkhokplus.app.feature.staff.StaffListViewModel
import com.shikkhokplus.app.feature.staff.ui.StaffFormActions
import com.shikkhokplus.app.feature.staff.ui.StaffFormScreen
import com.shikkhokplus.app.feature.staff.ui.StaffListActions
import com.shikkhokplus.app.feature.staff.ui.StaffListScreen
import io.ktor.client.HttpClient

/**
 * The chosen centre's Teachers & staff console: the list, inviting a
 * teacher, adding other staff, and correcting a record.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.staffRoutes(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(Destination.CentreStaff.route) {
        val model: StaffListViewModel = viewModel { StaffListViewModel(HttpStaffRepository(client)) }
        val state by model.state.collectAsState()
        // Re-read on every return, so a saved record is listed.
        LaunchedEffect(Unit) { model.load() }
        StaffListScreen(
            state = state,
            actions =
                StaffListActions(
                    onInviteTeacher = { navController.navigate(Destination.InviteStaffTeacher.route) },
                    onAddOther = { navController.navigate(Destination.AddOtherStaff.route) },
                    onEdit = { navController.navigate(Destination.EditStaff.of(it)) },
                    onLeave = model::leave,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.InviteStaffTeacher.route) {
        StaffFormRoute(client, navController, StaffFormMode.InviteTeacher)
    }

    composable(Destination.AddOtherStaff.route) {
        StaffFormRoute(client, navController, StaffFormMode.AddOther)
    }

    composable(Destination.EditStaff.route) { entry ->
        val list = listModel(entry, navController, client)
        val id = entry.arguments?.getString(Destination.EditStaff.ARG_STAFF).orEmpty()
        val existing = list.recordFor(id)
        if (existing == null) {
            // Reached without the list (a restored process): back to it.
            LaunchedEffect(Unit) { navController.popBackStack() }
        } else {
            StaffFormRoute(client, navController, StaffFormMode.Edit(existing), key = "staff-edit-$id")
        }
    }
}

@androidx.compose.runtime.Composable
private fun listModel(
    entry: NavBackStackEntry,
    navController: NavHostController,
    client: HttpClient,
): StaffListViewModel {
    val parent = remember(entry) { navController.getBackStackEntry(Destination.CentreStaff.route) }
    return viewModel(parent) { StaffListViewModel(HttpStaffRepository(client)) }
}

@androidx.compose.runtime.Composable
private fun StaffFormRoute(
    client: HttpClient,
    navController: NavHostController,
    mode: StaffFormMode,
    key: String? = null,
) {
    val model: StaffFormViewModel = viewModel(key = key) { StaffFormViewModel(HttpStaffRepository(client), mode) }
    val state by model.state.collectAsState()
    LaunchedEffect(state.saved) { if (state.saved != null) navController.popBackStack() }
    StaffFormScreen(
        state = state,
        actions =
            StaffFormActions(
                onName = model::name,
                onPhone = model::phone,
                onEmail = model::email,
                onRoleLabel = model::roleLabel,
                onAddress = model::address,
                onBasis = model::basis,
                onRate = model::rate,
                onJoinedOn = model::joinedOn,
                onSave = model::save,
                onCancel = { navController.popBackStack() },
            ),
    )
}
