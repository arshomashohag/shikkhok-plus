package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.network.HttpStudentRepository
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarUiState
import com.shikkhokplus.app.feature.fees.FeeReader
import com.shikkhokplus.app.feature.marks.MarksheetReader
import com.shikkhokplus.app.feature.student.FamilyExamViewModel
import com.shikkhokplus.app.feature.student.FamilyReader
import com.shikkhokplus.app.feature.student.StudentBatchUiState
import com.shikkhokplus.app.feature.student.StudentRepository
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
    val calendar by model.calendar.collectAsState()
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
        calendar = calendar,
        openers =
            FamilyOpeners(
                onOpenClass = {
                    val month = it.date.take(MONTH_CHARS)
                    navController.navigate(Destination.FamilyClass.of(reader.name, seat, it.sessionId, month))
                },
                onPickMonth = model::pickMonth,
                onRetryMonth = model::retryMonth,
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
 * The batch's loaded view, held by [owner] and loaded if nobody has yet.
 *
 * After process death the batch screen's store is empty and a detail
 * can be the first to ask, so the model is built here with the same
 * initializer the batch screen uses and loads the seat itself.
 *
 * @param owner The store the model lives in
 * @param reader Who is reading
 * @param seat The seat
 * @param repository Builds the repository the model reads with
 * @return The view, or null until it is loaded
 */
@Composable
internal fun familyViewOf(
    owner: ViewModelStoreOwner,
    reader: FamilyReader,
    seat: String,
    repository: () -> StudentRepository,
): StudentBatchView? {
    val model: StudentBatchViewModel =
        viewModel(owner, key = familyKey(reader, seat)) { StudentBatchViewModel(repository()) }
    val state by model.state.collectAsState()

    LaunchedEffect(seat) { model.ensureLoaded(seat) }

    return (state as? StudentBatchUiState.Loaded)?.view
}

/** The length of `YYYY-MM`. */
private const val MONTH_CHARS = 7

/**
 * A class of the batch's calendar, held by [owner]; the month is loaded
 * if nobody has yet.
 *
 * After process death the batch screen's store is empty and the class
 * detail can be the first to ask, so it loads the seat itself, on the
 * class's own month when the route carries one.
 *
 * @param owner The store the model lives in
 * @param reader Who is reading
 * @param seat The seat
 * @param month The class's month, if known
 * @param id The class's session id
 * @param repository Builds the repository the model reads with
 * @return The class, or null with whether the month is still loading
 */
@Composable
internal fun familyClassOf(
    owner: ViewModelStoreOwner,
    reader: FamilyReader,
    seat: String,
    month: YearMonth?,
    id: String,
    repository: () -> StudentRepository,
): Pair<CalendarClassUi?, Boolean> {
    val model: StudentBatchViewModel =
        viewModel(owner, key = familyKey(reader, seat)) { StudentBatchViewModel(repository()) }
    val calendar by model.calendar.collectAsState()

    LaunchedEffect(seat) { model.ensureLoaded(seat, month) }

    val loading = calendar is ClassCalendarUiState.Idle || calendar is ClassCalendarUiState.Loading
    return model.classOf(id) to loading
}

/**
 * The batch screen's entry for this very seat, or the detail's own.
 *
 * The entry below the detail is taken only when it is this reader's
 * batch screen for this seat; a route pattern alone could match
 * another seat's.
 *
 * @param navController The controller to search
 * @param entry The detail's own back-stack entry
 * @param reader Who is reading
 * @param seat The seat
 * @return The owner to hold the batch's model
 */
private fun ownerFor(
    navController: NavHostController,
    entry: NavBackStackEntry,
    reader: FamilyReader,
    seat: String,
): NavBackStackEntry {
    val argument =
        when (reader) {
            FamilyReader.SELF -> Destination.StudentBatch.ARG_SEAT
            FamilyReader.GUARDIAN -> Destination.ChildBatch.ARG_SEAT
        }
    return navController.previousBackStackEntry?.takeIf {
        it.destination.route == batchRoute(reader) && it.arguments?.getString(argument) == seat
    } ?: entry
}

/**
 * The view behind a detail screen.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to find the batch screen with
 * @param entry The detail's own back-stack entry
 * @param reader Who is reading
 * @param seat The seat
 * @return The view, or null until it is loaded
 */
@Composable
private fun parentView(
    client: HttpClient,
    navController: NavHostController,
    entry: NavBackStackEntry,
    reader: FamilyReader,
    seat: String,
): StudentBatchView? {
    val owner = remember(entry) { ownerFor(navController, entry, reader, seat) }
    return familyViewOf(owner, reader, seat) { HttpStudentRepository(client, reader) }
}

/**
 * The view behind a class detail.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to find the batch screen with
 * @param entry The detail's own back-stack entry
 * @param reader Who is reading
 * @param seat The seat
 * @param id The class's session id
 * @return The class, or null with whether the month is still loading
 */
@Composable
private fun parentClass(
    client: HttpClient,
    navController: NavHostController,
    entry: NavBackStackEntry,
    reader: FamilyReader,
    seat: String,
    id: String,
): Pair<CalendarClassUi?, Boolean> {
    val owner = remember(entry) { ownerFor(navController, entry, reader, seat) }
    val month = YearMonth.parseOrNull(entry.arguments?.getString(Destination.FamilyClass.ARG_MONTH))
    return familyClassOf(owner, reader, seat, month, id) { HttpStudentRepository(client, reader) }
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

    composable(
        Destination.FamilyClass.route,
        arguments + navArgument(Destination.FamilyClass.ARG_MONTH) {
            type = NavType.StringType
            defaultValue = ""
        },
    ) { entry ->
        val (reader, seat, id) = detailArgs(entry)
        val (clazz, loading) = parentClass(client, navController, entry, reader, seat, id)
        ClassDetailScreen(clazz, onBack = { navController.popBackStack() }, loading = loading)
    }

    composable(Destination.FamilyNotice.route, arguments) { entry ->
        val (reader, seat, id) = detailArgs(entry)
        val view = parentView(client, navController, entry, reader, seat)
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
