package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.core.network.HttpMyClassesRepository
import com.shikkhokplus.app.feature.myclasses.MyClassViewModel
import com.shikkhokplus.app.feature.myclasses.MyClassesViewModel
import com.shikkhokplus.app.feature.myclasses.ui.MyClassActions
import com.shikkhokplus.app.feature.myclasses.ui.MyClassScreen
import com.shikkhokplus.app.feature.myclasses.ui.MyClassesActions
import com.shikkhokplus.app.feature.myclasses.ui.MyClassesScreen
import io.ktor.client.HttpClient

/**
 * A centre teacher's screens: their classes, and one class's roster and topic.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 * @param bottomBar The centre teacher's tab bar, shown on My classes
 */
internal fun NavGraphBuilder.myClassesRoutes(
    client: HttpClient,
    navController: NavHostController,
    bottomBar: @Composable () -> Unit,
) {
    composable(Destination.MyClasses.route) {
        val model: MyClassesViewModel = viewModel { MyClassesViewModel(HttpMyClassesRepository(client)) }
        val state by model.state.collectAsState()
        // Re-read on every return, so a topic just written shows as written.
        LaunchedEffect(Unit) { model.load() }
        MyClassesScreen(
            state = state,
            actions =
                MyClassesActions(
                    onShift = model::shift,
                    onOpen = { navController.navigate(Destination.MyClass.of(it)) },
                    onRetry = model::retry,
                ),
            bottomBar = bottomBar,
        )
    }

    composable(
        route = Destination.MyClass.route,
        arguments = listOf(navArgument(Destination.MyClass.ARG_SESSION) { type = NavType.StringType }),
    ) { entry ->
        val sessionId = entry.arguments?.getString(Destination.MyClass.ARG_SESSION).orEmpty()
        val model: MyClassViewModel = viewModel { MyClassViewModel(HttpMyClassesRepository(client), sessionId) }
        val state by model.state.collectAsState()
        LaunchedEffect(sessionId) { model.load() }
        MyClassScreen(
            state = state,
            actions =
                MyClassActions(
                    onToggle = model::toggle,
                    onTopic = model::topic,
                    onSaveAttendance = model::saveAttendance,
                    onSaveTopic = model::saveTopic,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}
