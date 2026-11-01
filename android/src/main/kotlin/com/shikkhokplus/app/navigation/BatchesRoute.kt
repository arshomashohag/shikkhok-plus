package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.core.network.HttpBatchesRepository
import com.shikkhokplus.app.feature.batches.BatchesUiState
import com.shikkhokplus.app.feature.batches.BatchesViewModel
import com.shikkhokplus.app.feature.batches.ui.BatchesScreen
import io.ktor.client.HttpClient

/**
 * The teacher's Batches tab, with the inbox bell in its bar.
 *
 * Kept out of the host for the same reason as [todayRoute]: the host's
 * graph builder is one function near its complexity limit.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 * @param bottomBar The teacher's tab bar
 */
internal fun NavGraphBuilder.batchesRoute(
    client: HttpClient,
    navController: NavHostController,
    bottomBar: @Composable () -> Unit,
) {
    composable(Destination.Batches.route) {
        val model: BatchesViewModel =
            viewModel { BatchesViewModel(HttpBatchesRepository(client)) }
        val state by model.state.collectAsState()

        LaunchedEffect(Unit) { model.load() }

        BatchesScreen(
            state = state,
            bottomBar = bottomBar,
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
            barActions = { InboxBellFor(client) { navController.navigate(Destination.Inbox.route) } },
        )
    }
}
