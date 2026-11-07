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
import com.shikkhokplus.app.core.network.HttpHelpRepository
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.help.AskQuestionViewModel
import com.shikkhokplus.app.feature.help.HelpListViewModel
import com.shikkhokplus.app.feature.help.HelpThreadViewModel
import com.shikkhokplus.app.feature.help.ui.AskQuestionScreen
import com.shikkhokplus.app.feature.help.ui.HelpListScreen
import com.shikkhokplus.app.feature.help.ui.HelpThreadScreen
import io.ktor.client.HttpClient

/**
 * The help centre, pushed over More: My questions, Ask a question, and
 * one question's thread.
 *
 * Every screen reads the signed-in account's own questions, so the
 * routes are the same for every lens and need no workspace.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 */
internal fun NavGraphBuilder.helpRoutes(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(Destination.HelpCentre.route) {
        val model: HelpListViewModel = viewModel { HelpListViewModel(HttpHelpRepository(client)) }
        val state by model.state.collectAsState()
        val refreshing by model.refreshing.collectAsState()

        // Re-read on every return, so a question just asked or answered
        // shows where it now stands.
        LaunchedEffect(Unit) { model.load() }

        HelpListScreen(
            state = state,
            onBack = { navController.popBackStack() },
            onAsk = { navController.navigate(Destination.AskQuestion.route) },
            onOpen = { ticket -> navController.navigate(Destination.HelpThread.of(ticket.id)) },
            onRetry = model::retry,
            refreshing = refreshing,
            onRefresh = model::refresh,
        )
    }

    composable(Destination.AskQuestion.route) {
        val model: AskQuestionViewModel = viewModel { AskQuestionViewModel(HttpHelpRepository(client)) }
        val state by model.state.collectAsState()

        // **The form closes only once the server has the question**, and
        // opens it in place of itself, so back from the thread lands on
        // the list rather than on an emptied form.
        LaunchedEffect(state.write, state.ticketId) {
            val created = state.ticketId
            if (state.write == WriteState.Saved && created != null) {
                navController.navigate(Destination.HelpThread.of(created)) {
                    popUpTo(Destination.AskQuestion.route) { inclusive = true }
                }
            }
        }

        AskQuestionScreen(
            state = state,
            onSubject = model::subject,
            onBody = model::body,
            onSend = model::send,
            onBack = { navController.popBackStack() },
        )
    }

    composable(
        route = Destination.HelpThread.route,
        arguments = listOf(navArgument(Destination.HelpThread.ARG_ID) { type = NavType.StringType }),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.HelpThread.ARG_ID).orEmpty()
        val model: HelpThreadViewModel = viewModel(key = id) { HelpThreadViewModel(HttpHelpRepository(client)) }
        val state by model.state.collectAsState()
        val reply by model.reply.collectAsState()

        LaunchedEffect(id) { model.load(id) }

        HelpThreadScreen(
            state = state,
            reply = reply,
            onReply = model::type,
            onSend = model::send,
            onRetry = model::retry,
            onBack = { navController.popBackStack() },
        )
    }
}
