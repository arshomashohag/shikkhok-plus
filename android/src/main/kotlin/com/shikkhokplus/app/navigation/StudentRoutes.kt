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
import com.shikkhokplus.app.core.network.HttpStudentRepository
import com.shikkhokplus.app.feature.fees.FeeReader
import com.shikkhokplus.app.feature.marks.MarksheetReader
import com.shikkhokplus.app.feature.student.MyBatchesViewModel
import com.shikkhokplus.app.feature.student.StudentBatchViewModel
import com.shikkhokplus.app.feature.student.ui.MyBatchesScreen
import com.shikkhokplus.app.feature.student.ui.StudentBatchScreen
import io.ktor.client.HttpClient

/**
 * The student's own screens: S1, their batches, and S2, one batch.
 *
 * Kept out of the host for the same reason as [teachingRoutes]: the
 * host's graph builder is one function, and every screen added to it
 * pushes it past the complexity limit.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 * @param bottomBar The student's tab bar, shown on S1
 */
internal fun NavGraphBuilder.studentRoutes(
    client: HttpClient,
    navController: NavHostController,
    bottomBar: @Composable () -> Unit,
) {
    composable(Destination.MyBatches.route) {
        val model: MyBatchesViewModel = viewModel { MyBatchesViewModel(HttpStudentRepository(client)) }
        val state by model.state.collectAsState()

        LaunchedEffect(Unit) { model.load() }

        MyBatchesScreen(
            state = state,
            onOpen = { seat -> navController.navigate(Destination.StudentBatch.of(seat)) },
            onRetry = model::retry,
            bottomBar = bottomBar,
        )
    }

    composable(
        route = Destination.StudentBatch.route,
        arguments = listOf(navArgument(Destination.StudentBatch.ARG_SEAT) { type = NavType.StringType }),
    ) { entry ->
        val seat = entry.arguments?.getString(Destination.StudentBatch.ARG_SEAT).orEmpty()
        val model: StudentBatchViewModel =
            viewModel(key = seat) { StudentBatchViewModel(HttpStudentRepository(client)) }
        val state by model.state.collectAsState()

        LaunchedEffect(seat) { model.load(seat) }

        StudentBatchScreen(
            state = state,
            onBack = { navController.popBackStack() },
            onOpenExam = { examId ->
                navController.navigate(Destination.Marksheet.of(examId, seat, MarksheetReader.SELF.name))
            },
            onOpenFees = { navController.navigate(Destination.FeeHistory.of(seat, FeeReader.STUDENT.name)) },
            onRetry = model::retry,
        )
    }
}
