package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.core.network.HttpStudentRepository
import com.shikkhokplus.app.feature.fees.FeeReader
import com.shikkhokplus.app.feature.marks.MarksheetReader
import com.shikkhokplus.app.feature.student.FamilyExamViewModel
import com.shikkhokplus.app.feature.student.FamilyReader
import com.shikkhokplus.app.feature.student.StudentBatchUiState
import com.shikkhokplus.app.feature.student.StudentBatchView
import com.shikkhokplus.app.feature.student.StudentBatchViewModel
import com.shikkhokplus.app.feature.student.ui.ClassDetailScreen
import com.shikkhokplus.app.feature.student.ui.ExamDetailScreen
import com.shikkhokplus.app.feature.student.ui.FamilyOpeners
import com.shikkhokplus.app.feature.student.ui.NoticeDetailScreen
import com.shikkhokplus.app.feature.student.ui.StudentBatchScreen
import io.ktor.client.HttpClient

/**
 * The key a family batch's view model is held under, so a detail
 * screen reads the same state the batch screen loaded.
 *
 * @param reader Who is reading
 * @param seat The seat
 * @return The key
 */
private fun familyKey(reader: FamilyReader, seat: String): String = "family-${reader.name}-$seat"

/**
 * The batch screen's route for a reader.
 *
 * @param reader Who is reading
 * @return The route pattern
 */
private fun batchRoute(reader: FamilyReader): String =
    when (reader) {
        FamilyReader.SELF -> Destination.StudentBatch.route
        FamilyReader.GUARDIAN -> Destination.ChildBatch.route
    }

/**
 * One batch, as a student or a guardian reads it.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 * @param reader Whether a student or a guardian is reading
 * @param seat The seat
 */
@Composable
internal fun FamilyBatchRoute(
    client: HttpClient,
    navController: NavHostController,
    reader: FamilyReader,
    seat: String,
) {
    val model: StudentBatchViewModel =
        viewModel(key = familyKey(reader, seat)) { StudentBatchViewModel(HttpStudentRepository(client, reader)) }
    val state by model.state.collectAsState()
    val tab by model.tab.collectAsState()
    val guardian = reader == FamilyReader.GUARDIAN

    LaunchedEffect(seat) { model.load(seat) }

    StudentBatchScreen(
        state = state,
        onBack = { navController.popBackStack() },
        onOpenFees = {
            navController.navigate(
                Destination.FeeHistory.of(seat, (if (guardian) FeeReader.GUARDIAN else FeeReader.STUDENT).name),
            )
        },
        onRetry = model::retry,
        onPay = {
            navController.navigate(if (guardian) Destination.ChildPay.of(seat) else Destination.Pay.of(seat))
        },
        tab = tab,
        onSelect = model::select,
        openers =
            FamilyOpeners(
                onOpenClass = { navController.navigate(Destination.FamilyClass.of(reader.name, seat, it)) },
                onOpenExam = { examId ->
                    val marksheet = if (guardian) MarksheetReader.CHILD else MarksheetReader.SELF
                    navController.navigate(Destination.Marksheet.of(examId, seat, marksheet.name))
                },
                onOpenExamDetail = { navController.navigate(Destination.FamilyExam.of(reader.name, seat, it)) },
                onOpenNotice = { navController.navigate(Destination.FamilyNotice.of(reader.name, seat, it)) },
            ),
    )
}

/**
 * The batch's loaded view, read from the batch screen under a detail.
 *
 * @param navController The controller to find the batch screen with
 * @param entry The detail's own back-stack entry
 * @param reader Who is reading
 * @param seat The seat
 * @return The view, or null when the batch screen is not loaded
 */
@Composable
private fun parentView(
    navController: NavHostController,
    entry: NavBackStackEntry,
    reader: FamilyReader,
    seat: String,
): StudentBatchView? {
    val parent = remember(entry) { runCatching { navController.getBackStackEntry(batchRoute(reader)) }.getOrNull() }
        ?: return null
    val model: StudentBatchViewModel = viewModel(parent, key = familyKey(reader, seat))
    val state by model.state.collectAsState()
    return (state as? StudentBatchUiState.Loaded)?.view
}

/**
 * Read the detail route's three arguments.
 *
 * @param entry The detail's back-stack entry
 * @return The reader, the seat and the item id
 */
private fun detailArgs(entry: NavBackStackEntry): Triple<FamilyReader, String, String> {
    val args = entry.arguments
    val reader = FamilyReader.entries.firstOrNull { it.name == args?.getString(Destination.FamilyNotice.ARG_READER) }
    return Triple(
        reader ?: FamilyReader.SELF,
        args?.getString(Destination.FamilyNotice.ARG_SEAT).orEmpty(),
        args?.getString(Destination.FamilyNotice.ARG_ID).orEmpty(),
    )
}

/**
 * The three details a family batch screen opens: class, exam, notice.
 *
 * Each has a back arrow that pops to the batch screen.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.familyRoutes(client: HttpClient, navController: NavHostController) {
    val arguments =
        listOf(
            navArgument(Destination.FamilyNotice.ARG_READER) { type = NavType.StringType },
            navArgument(Destination.FamilyNotice.ARG_SEAT) { type = NavType.StringType },
            navArgument(Destination.FamilyNotice.ARG_ID) { type = NavType.StringType },
        )

    composable(
        route = Destination.ChildBatch.route,
        arguments = listOf(navArgument(Destination.ChildBatch.ARG_SEAT) { type = NavType.StringType }),
    ) { entry ->
        val seat = entry.arguments?.getString(Destination.ChildBatch.ARG_SEAT).orEmpty()
        FamilyBatchRoute(client, navController, FamilyReader.GUARDIAN, seat)
    }

    composable(Destination.FamilyClass.route, arguments) { entry ->
        val (reader, seat, id) = detailArgs(entry)
        val view = parentView(navController, entry, reader, seat)
        ClassDetailScreen(view?.pastClass(id), onBack = { navController.popBackStack() })
    }

    composable(Destination.FamilyNotice.route, arguments) { entry ->
        val (reader, seat, id) = detailArgs(entry)
        val view = parentView(navController, entry, reader, seat)
        NoticeDetailScreen(view?.notice(id), onBack = { navController.popBackStack() })
    }

    composable(Destination.FamilyExam.route, arguments) { entry ->
        val (reader, seat, id) = detailArgs(entry)
        val model: FamilyExamViewModel =
            viewModel(key = "family-exam-${reader.name}-$seat-$id") {
                FamilyExamViewModel(HttpStudentRepository(client, reader))
            }
        val state by model.state.collectAsState()

        LaunchedEffect(seat, id) { model.load(seat, id) }

        ExamDetailScreen(state, onBack = { navController.popBackStack() }, onRetry = model::retry)
    }
}
