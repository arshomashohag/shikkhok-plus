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
import com.shikkhokplus.app.core.network.HttpAnalyticsRepository
import com.shikkhokplus.app.feature.collections.BatchMonthViewModel
import com.shikkhokplus.app.feature.collections.CollectionsViewModel
import com.shikkhokplus.app.feature.collections.ui.BatchMonthActions
import com.shikkhokplus.app.feature.collections.ui.BatchMonthScreen
import com.shikkhokplus.app.feature.collections.ui.CollectionsActions
import com.shikkhokplus.app.feature.collections.ui.CollectionsScreen
import com.shikkhokplus.app.feature.fees.FeeReader
import io.ktor.client.HttpClient

/**
 * The teacher's money reports: collections (M1) and one batch in one
 * month (M2). A seat opens its payment history (M3).
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.collectionsRoutes(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(Destination.Collections.route) {
        val model: CollectionsViewModel = viewModel { CollectionsViewModel(HttpAnalyticsRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        CollectionsScreen(
            state = state,
            actions =
                CollectionsActions(
                    onRetry = model::retry,
                    onToggleBatch = model::toggle,
                    onShowAll = model::showAll,
                    onSelectMonth = model::selectMonth,
                    onOpenBatch = { row ->
                        navController.navigate(Destination.BatchMonth.of(row.batchId, row.name, row.period))
                    },
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(
        route = Destination.BatchMonth.route,
        arguments =
            listOf(
                navArgument(Destination.BatchMonth.ARG_ID) { type = NavType.StringType },
                navArgument(Destination.BatchMonth.ARG_PERIOD) {
                    type = NavType.StringType
                    defaultValue = ""
                },
                navArgument(Destination.BatchMonth.ARG_NAME) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.BatchMonth.ARG_ID).orEmpty()
        val period = entry.arguments?.getString(Destination.BatchMonth.ARG_PERIOD).orEmpty().ifBlank { null }
        val name = entry.arguments?.getString(Destination.BatchMonth.ARG_NAME).orEmpty()
        val model: BatchMonthViewModel =
            viewModel(key = "month-$id") { BatchMonthViewModel(HttpAnalyticsRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(id, period) { model.load(id, period) }
        BatchMonthScreen(
            batchName = name,
            state = state,
            actions =
                BatchMonthActions(
                    onRetry = model::retry,
                    onPrevious = model::previous,
                    onNext = model::next,
                    onFilter = model::filter,
                    onOpenSeat = { seat ->
                        navController.navigate(Destination.FeeHistory.of(seat.enrollmentId, FeeReader.TEACHER.name))
                    },
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}
