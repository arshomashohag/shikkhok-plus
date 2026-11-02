package com.shikkhokplus.app.navigation

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.core.network.HttpDashboardRepository
import com.shikkhokplus.app.feature.dashboard.DashboardReader
import com.shikkhokplus.app.feature.dashboard.DashboardUiState
import com.shikkhokplus.app.feature.dashboard.DashboardViewModel
import com.shikkhokplus.app.feature.dashboard.ui.DashboardActions
import com.shikkhokplus.app.feature.dashboard.ui.DashboardScreen
import com.shikkhokplus.app.feature.fees.FeeReader
import io.ktor.client.HttpClient

/**
 * The progress dashboard (D1, D2): one destination for a teacher, a
 * student and a guardian.
 *
 * Send money opens the same pay flow the fee screens open, on this seat.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.dashboardRoutes(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(
        route = Destination.Dashboard.route,
        arguments =
            listOf(
                navArgument(Destination.Dashboard.ARG_SEAT) { type = NavType.StringType },
                navArgument(Destination.Dashboard.ARG_READER) {
                    type = NavType.StringType
                    defaultValue = DashboardReader.STUDENT.name
                },
                navArgument(Destination.Dashboard.ARG_CHILD) {
                    type = NavType.StringType
                    defaultValue = ""
                },
                navArgument(Destination.Dashboard.ARG_BATCH) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
    ) { entry ->
        val args = entry.arguments
        val seat = args?.getString(Destination.Dashboard.ARG_SEAT).orEmpty()
        val reader =
            DashboardReader.entries.firstOrNull { it.name == args?.getString(Destination.Dashboard.ARG_READER) }
                ?: DashboardReader.STUDENT
        val child = args?.getString(Destination.Dashboard.ARG_CHILD).orEmpty()
        val batch = args?.getString(Destination.Dashboard.ARG_BATCH).orEmpty()
        val model: DashboardViewModel =
            viewModel(key = "dashboard-${reader.name}-$seat") { DashboardViewModel(HttpDashboardRepository(client)) }
        val state by model.state.collectAsState()

        LaunchedEffect(seat, reader) {
            if (model.state.value is DashboardUiState.Loading) model.load(reader, seat, child, batch)
        }

        DashboardScreen(
            state = state,
            actions =
                DashboardActions(
                    onRange = model::selectRange,
                    onChild = model::selectChild,
                    onBatch = model::selectBatch,
                    onFeeHistory = {
                        val shown = (state as? DashboardUiState.Loaded)?.seat ?: seat
                        navController.navigate(Destination.FeeHistory.of(shown, feeReaderOf(reader).name))
                    },
                    onSendMoney = {
                        val shown = (state as? DashboardUiState.Loaded)?.seat ?: seat
                        navController.navigate(
                            if (reader == DashboardReader.GUARDIAN) {
                                Destination.ChildPay.of(shown)
                            } else {
                                Destination.Pay.of(shown)
                            },
                        )
                    },
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}

private fun feeReaderOf(reader: DashboardReader): FeeReader =
    when (reader) {
        DashboardReader.TEACHER -> FeeReader.TEACHER
        DashboardReader.STUDENT -> FeeReader.STUDENT
        DashboardReader.GUARDIAN -> FeeReader.GUARDIAN
    }
