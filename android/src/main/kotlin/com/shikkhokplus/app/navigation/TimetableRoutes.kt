package com.shikkhokplus.app.navigation

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.core.network.HttpTimetableRepository
import com.shikkhokplus.app.feature.timetable.RoomsViewModel
import com.shikkhokplus.app.feature.timetable.TimetableViewModel
import com.shikkhokplus.app.feature.timetable.ui.RoomsActions
import com.shikkhokplus.app.feature.timetable.ui.RoomsScreen
import com.shikkhokplus.app.feature.timetable.ui.TimetableActions
import com.shikkhokplus.app.feature.timetable.ui.TimetableScreen
import io.ktor.client.HttpClient

/**
 * The chosen centre's timetable and its rooms.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.timetableRoutes(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(Destination.CentreTimetable.route) {
        val model: TimetableViewModel = viewModel { TimetableViewModel(HttpTimetableRepository(client)) }
        val state by model.state.collectAsState()
        // Re-read on every return, so a room added on Rooms is offered.
        LaunchedEffect(Unit) { model.load() }
        TimetableScreen(
            state = state,
            actions =
                TimetableActions(
                    onShift = model::shift,
                    onOpen = model::open,
                    onTeacher = model::teacher,
                    onRoom = model::room,
                    onSwapWith = model::swapWith,
                    onSave = model::save,
                    onClose = model::close,
                    onRooms = { navController.navigate(Destination.CentreRooms.route) },
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.CentreRooms.route) {
        val model: RoomsViewModel = viewModel { RoomsViewModel(HttpTimetableRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        RoomsScreen(
            state = state,
            actions =
                RoomsActions(
                    onName = model::name,
                    onAdd = model::add,
                    onArchive = model::archive,
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}
