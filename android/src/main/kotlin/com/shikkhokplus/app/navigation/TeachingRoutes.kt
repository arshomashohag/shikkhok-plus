package com.shikkhokplus.app.navigation

import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.network.HttpAttendanceRepository
import com.shikkhokplus.app.core.network.HttpMarksRepository
import com.shikkhokplus.app.core.network.HttpScheduleRepository
import com.shikkhokplus.app.core.network.HttpSessionsRepository
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.attendance.AttendanceViewModel
import com.shikkhokplus.app.feature.attendance.ui.AttendanceScreen
import com.shikkhokplus.app.feature.attendance.ui.ConflictScreen
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.MarksViewModel
import com.shikkhokplus.app.feature.marks.ui.ExamCreateForm
import com.shikkhokplus.app.feature.marks.ui.ExamListScreen
import com.shikkhokplus.app.feature.marks.ui.MarkEntryScreen
import com.shikkhokplus.app.feature.schedule.ScheduleViewModel
import com.shikkhokplus.app.feature.schedule.ui.ScheduleScreen
import com.shikkhokplus.app.feature.sessions.SessionsViewModel
import com.shikkhokplus.app.feature.sessions.ui.AddSessionDialog
import com.shikkhokplus.app.feature.sessions.ui.SessionListScreen
import io.ktor.client.HttpClient

/**
 * The teacher's teaching routes: sessions, schedule, attendance, exams
 * and marks.
 *
 * **Split out of [ShikkhokNavHost] when its graph passed detekt's
 * complexity threshold.** Every route lived in one function, and each
 * screen that closes on its write's answer adds a branch; the threshold
 * was right that one function holding the whole app had become hard to
 * read. These routes form one area of the product and move together.
 *
 * @param client The authenticated HTTP client
 * @param queue The app's single pending-write queue [BR3.5]
 * @param navController The host's controller
 */
internal fun NavGraphBuilder.teachingRoutes(
    client: HttpClient,
    queue: QueueStore,
    navController: NavHostController,
) {
    composable(
        route = Destination.Sessions.route,
        arguments =
            listOf(
                navArgument(Destination.Roster.ARG_ID) { type = NavType.StringType },
                navArgument(Destination.Roster.ARG_NAME) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.Roster.ARG_ID).orEmpty()
        val name = entry.arguments?.getString(Destination.Roster.ARG_NAME).orEmpty()

        val model: SessionsViewModel =
            viewModel(key = id) { SessionsViewModel(HttpSessionsRepository(client)) }
        val state by model.state.collectAsState()

        LaunchedEffect(id) { model.load(id, name) }

        var adding by remember { mutableStateOf(false) }
        if (adding) {
            AddSessionDialog(
                onAdd = { date, start ->
                    adding = false
                    model.createAdHoc(date, start)
                },
                onDismiss = { adding = false },
            )
        }

        SessionListScreen(
            state = state,
            // Was left at its default, so "Add a class" did nothing.
            onAddSession = { adding = true },
            onOpen = { row ->
                navController.navigate(Destination.Attendance.of(row.sessionId))
            },
            onRetry = model::retry,
        )
    }

    composable(
        route = Destination.BatchSchedule.route,
        arguments =
            listOf(
                navArgument(Destination.Roster.ARG_ID) { type = NavType.StringType },
            ),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.Roster.ARG_ID).orEmpty()
        val model: ScheduleViewModel =
            viewModel(key = "schedule-$id") { ScheduleViewModel(HttpScheduleRepository(client)) }
        val stored by model.slots.collectAsState()
        val loadFailed by model.loadFailed.collectAsState()
        val write by model.writeState.collectAsState()

        LaunchedEffect(id) { model.load(id) }
        LaunchedEffect(write) {
            if (write == WriteState.Saved) {
                model.acknowledgeWrite()
                navController.popBackStack()
            }
        }

        ScheduleScreen(
            stored = stored,
            onSave = { slots -> model.save(id, slots) },
            onBack = {
                model.acknowledgeWrite()
                navController.popBackStack()
            },
            saving = write == WriteState.Saving,
            error =
                writeError(write)
                    ?: loadFailed?.let { stringResource(MessageKeys.resolve(it)) },
        )
    }

    composable(
        route = Destination.Attendance.route,
        arguments =
            listOf(
                navArgument(Destination.Attendance.ARG_SESSION) {
                    type = NavType.StringType
                },
            ),
    ) { entry ->
        val sessionId =
            entry.arguments?.getString(Destination.Attendance.ARG_SESSION).orEmpty()

        val model: AttendanceViewModel =
            viewModel(key = sessionId) {
                AttendanceViewModel(
                    HttpAttendanceRepository(client),
                    HttpSessionsRepository(client),
                    queue,
                )
            }
        val state by model.state.collectAsState()

        LaunchedEffect(sessionId) { model.load(sessionId) }

        // **A conflict is its own screen, not a banner.** The
        // teacher is choosing between two rosters that disagree,
        // and that decision needs both of them side by side
        // [BR3.6]. Rendering it inside the marking screen would
        // put a destructive choice next to the controls that
        // caused it.
        val conflict = state
        if (conflict is AttendanceUiState.Conflicted) {
            ConflictScreen(
                state = conflict,
                onReapply = model::reapply,
                onDiscard = model::discard,
            )
        } else {
            val marking = state as? AttendanceUiState.Marking
            AttendanceScreen(
                state = state,
                onToggle = { seat, present -> model.toggle(seat, present) },
                onSubmit = {
                    // The version comes from the state the roster
                    // was COMPOSED against, never from a fresh
                    // read: re-reading it here would resolve every
                    // conflict by silently winning [BR3.7].
                    marking?.let {
                        model.submit(
                            sessionId = it.sessionId,
                            baseVersion = it.attendanceVersion,
                            seats = it.seats,
                        )
                    }
                },
                onRetry = model::retry,
            )
        }
    }

    composable(
        route = Destination.Exams.route,
        arguments =
            listOf(
                navArgument(Destination.Roster.ARG_ID) { type = NavType.StringType },
                navArgument(Destination.Roster.ARG_NAME) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.Roster.ARG_ID).orEmpty()
        val name = entry.arguments?.getString(Destination.Roster.ARG_NAME).orEmpty()

        val model: MarksViewModel =
            viewModel(key = id) { MarksViewModel(HttpMarksRepository(client)) }
        val state by model.state.collectAsState()

        LaunchedEffect(id) { model.loadExams(id, name) }

        ExamListScreen(
            state = state,
            onOpen = { row ->
                navController.navigate(Destination.MarkEntry.of(row.examId))
            },
            // Was left at its default, so the button did nothing and
            // no exam could ever be created -- which left marks
            // entry with nothing to open.
            onCreate = { navController.navigate(Destination.CreateExam.of(id)) },
            onRetry = model::retry,
        )
    }

    composable(
        route = Destination.CreateExam.route,
        arguments =
            listOf(
                navArgument(Destination.Roster.ARG_ID) { type = NavType.StringType },
            ),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.Roster.ARG_ID).orEmpty()

        // The EXAM LIST's ViewModel, as CreateBatch shares the batch
        // list's: the created exam is in the list this returns to.
        val parent =
            remember(entry) { navController.getBackStackEntry(Destination.Exams.route) }
        val model: MarksViewModel =
            viewModel(parent, key = id) { MarksViewModel(HttpMarksRepository(client)) }
        val write by model.writeState.collectAsState()
        val subjects by model.subjectOptions.collectAsState()

        LaunchedEffect(id) { model.loadSubjectOptions(id) }

        // Close on the server's answer, never on the tap. See
        // WriteState for the race that closing on the tap caused.
        LaunchedEffect(write) {
            if (write == WriteState.Saved) {
                model.acknowledgeWrite()
                navController.popBackStack()
            }
        }
        val leave = {
            model.acknowledgeWrite()
            navController.popBackStack()
        }

        ScreenScaffold(
            title = stringResource(R.string.screen_title_create_exam),
            onBack = { leave() },
        ) {
            ExamCreateForm(
                subjects = subjects,
                onCreate = { title, date, total, subjectId ->
                    model.createExam(title, date, total, subjectId)
                },
                onCancel = { leave() },
                saving = write == WriteState.Saving,
                error = writeError(write),
            )
        }
    }

    composable(
        route = Destination.MarkEntry.route,
        arguments =
            listOf(
                navArgument(Destination.MarkEntry.ARG_EXAM) {
                    type = NavType.StringType
                },
            ),
    ) { entry ->
        val examId =
            entry.arguments?.getString(Destination.MarkEntry.ARG_EXAM).orEmpty()

        val model: MarksViewModel =
            viewModel(key = examId) { MarksViewModel(HttpMarksRepository(client)) }
        val state by model.state.collectAsState()

        LaunchedEffect(examId) { model.loadResults(examId) }

        MarkEntryScreen(
            state = state,
            onMark = { row, marks ->
                model.writeMark(row.enrollmentId, resultState = "marked", marks = marks)
            },
            // **Absent carries no marks at all.** A zero is a mark,
            // and publishing one where the teacher recorded an
            // absence is the conflation [BR4.3] forbids.
            onAbsent = { row ->
                model.writeMark(row.enrollmentId, resultState = "absent", marks = null)
            },
            onRetry = model::retry,
        )
    }
}
