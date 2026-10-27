package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.BottomNav
import com.shikkhokplus.app.core.designsystem.NavDestination
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.network.HttpAnalyticsRepository
import com.shikkhokplus.app.feature.dues.DuesViewModel
import com.shikkhokplus.app.feature.dues.ui.DuesScreen
import com.shikkhokplus.app.feature.overview.OverviewViewModel
import com.shikkhokplus.app.feature.overview.ui.OverviewScreen
import com.shikkhokplus.app.core.network.HttpBatchesRepository
import com.shikkhokplus.app.core.network.HttpRosterRepository
import com.shikkhokplus.app.core.network.HttpSignupRepository
import com.shikkhokplus.app.core.ui.BatchCreateForm
import com.shikkhokplus.app.core.ui.StudentAddForm
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.AuthViewModel
import com.shikkhokplus.app.feature.auth.SignupUiState
import com.shikkhokplus.app.feature.auth.SignupViewModel
import com.shikkhokplus.app.feature.auth.ui.AuthScreen
import com.shikkhokplus.app.feature.auth.ui.SignupScreen
import com.shikkhokplus.app.feature.batches.BatchesUiState
import com.shikkhokplus.app.feature.batches.BatchesViewModel
import com.shikkhokplus.app.feature.batches.ui.BatchesScreen
import com.shikkhokplus.app.feature.roster.RosterViewModel
import com.shikkhokplus.app.feature.roster.ui.RosterScreen
import com.shikkhokplus.app.core.network.HttpAttendanceRepository
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.network.HttpFeesRepository
import com.shikkhokplus.app.core.network.HttpGuardianRepository
import com.shikkhokplus.app.core.network.HttpInvitationsRepository
import com.shikkhokplus.app.core.network.HttpMarksRepository
import com.shikkhokplus.app.core.network.HttpProfileRepository
import com.shikkhokplus.app.core.network.HttpSessionsRepository
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.attendance.AttendanceViewModel
import com.shikkhokplus.app.feature.attendance.ui.AttendanceScreen
import com.shikkhokplus.app.feature.attendance.ui.ConflictScreen
import com.shikkhokplus.app.feature.fees.FeeReader
import com.shikkhokplus.app.feature.fees.FeesViewModel
import com.shikkhokplus.app.feature.fees.ui.FeeHistoryScreen
import com.shikkhokplus.app.feature.guardian.GuardianViewModel
import com.shikkhokplus.app.feature.guardian.ui.GuardianHomeScreen
import com.shikkhokplus.app.feature.invitations.InvitationsViewModel
import com.shikkhokplus.app.feature.invitations.ui.InvitationsScreen
import com.shikkhokplus.app.feature.marks.MarksViewModel
import com.shikkhokplus.app.feature.marks.MarksheetReader
import com.shikkhokplus.app.feature.marks.ui.ExamListScreen
import com.shikkhokplus.app.feature.marks.ui.MarkEntryScreen
import com.shikkhokplus.app.feature.marks.ui.MarksheetScreen
import com.shikkhokplus.app.feature.marks.ui.ProgressScreen
import com.shikkhokplus.app.feature.profile.ProfileViewModel
import com.shikkhokplus.app.feature.profile.ui.ProfileScreen
import com.shikkhokplus.app.feature.sessions.SessionsViewModel
import com.shikkhokplus.app.feature.sessions.ui.SessionListScreen
import io.ktor.client.HttpClient

/**
 * The navigation graph.
 *
 * **Replaces the nullable-id routing `MainActivity` carried**, which
 * said of itself: "It is replaced the moment a third screen needs a
 * real back stack." That moment had passed unnoticed — 23 screens were
 * built against 3 that could be reached.
 *
 * Every built screen is now reachable. The earlier version of this
 * file left the fee, attendance, marks, guardian, invitations and
 * profile screens out because each was missing its HTTP repository,
 * its ViewModel, or both — routing to one would have opened a screen
 * that could not load. Those layers have since landed, so the reason
 * for their absence is gone and the routes are here.
 *
 * **Three screens are still deliberately not destinations**:
 * `BatchFeesScreen`, `ClaimStatusScreen` and `PaymentFormScreen` take
 * rows and callbacks rather than a UI state, which makes them content
 * components for a host screen rather than screens in their own right.
 * Giving one a route would mean inventing the state it does not hold.
 *
 * **Two routes are registered and not yet navigated to**, and saying
 * so here is the point — an unreachable screen is exactly the gap
 * this file was written to close, and leaving it unrecorded is how
 * the last one survived 23 screens:
 *
 * - [Destination.Marksheet] needs an exam to open, and `ProgressRow`
 *   carries no `examId`. Adding the entry point means adding that
 *   field through the mapper and the DTO, which is a change to the
 *   marks feature rather than to navigation.
 * - [Destination.FeeHistory] needs a seat, which a student or
 *   guardian reaches from their own home. The guardian path has one
 *   and the student path has no home screen yet.
 *
 * Both are reachable by deep link today and by a tap once those land.
 *
 * @param client The authenticated HTTP client for signed-in routes
 * @param queue The app's single pending-write queue [BR3.5]
 * @param signedIn Whether a session was restored before first render
 * @param navController The host's controller
 * @param modifier The layout modifier
 */
@Composable
fun ShikkhokNavHost(
    client: HttpClient,
    queue: QueueStore,
    signedIn: Boolean,
    navController: NavHostController,
    authModel: AuthViewModel,
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        startDestination =
            if (signedIn) Destination.Batches.route else Destination.Auth.route,
        modifier = modifier,
    ) {
        composable(Destination.Auth.route) {
            val state by authModel.state.collectAsState()

            // **The jump to Batches happens here, not inside the
            // screen.** A screen that navigates is a screen that cannot
            // be tested without a NavController, and this one is
            // already covered by Robolectric tests that pass a state
            // and assert what renders.
            LaunchedEffect(state) {
                if (state is AuthUiState.SignedIn) {
                    navController.navigate(Destination.Batches.route) {
                        // The auth screen leaves the back stack: a
                        // signed-in person pressing Back should leave
                        // the app, not return to an OTP field that
                        // would re-issue a code.
                        popUpTo(Destination.Auth.route) { inclusive = true }
                    }
                }
            }

            AuthScreen(
                state = state,
                onRequestCode = authModel::requestCode,
                onSubmitCode = authModel::submitCode,
                onRetry = authModel::retry,
                onGoToSignup = { navController.navigate(Destination.Signup.route) },
            )
        }

        composable(Destination.Signup.route) {
            // The signup client is UNAUTHENTICATED by necessity: the
            // person has no account yet, so there is no token to send.
            val model: SignupViewModel =
                viewModel { SignupViewModel(HttpSignupRepository(client)) }
            val state by model.state.collectAsState()

            // **On success, go to the code screen.** Signup issues an
            // OTP and does not authenticate, so the person's next step
            // is entering that code. Leaving them on a "we sent a
            // code" message with no field to type it into is a second
            // dead end one screen further along.
            //
            // `popBackStack` rather than `navigate`: auth is already
            // on the stack beneath this, so returning to it keeps one
            // auth screen rather than stacking a second.
            LaunchedEffect(state) {
                val sent = state
                if (sent is SignupUiState.CodeSent) {
                    // The auth ViewModel is shared with the screen we
                    // are returning to, and it has issued nothing
                    // itself — so it is told a code is outstanding and
                    // which number it went to. Without this it would
                    // show the number field and invite a second code,
                    // invalidating the one the person is holding.
                    authModel.adoptPendingCode(sent.codeSentTo)
                    navController.popBackStack()
                }
            }

            SignupScreen(
                state = state,
                onSubmit = { phone, name, address, role ->
                    model.submit(
                        phone = phone,
                        selfName = name,
                        address = address,
                        role = role,
                    )
                },
                // **Back to sign-in, not forward to it.** Signup issues
                // an OTP and does not authenticate, so the person
                // finishes on the screen they started from — which is
                // already on the stack.
                onGoToLogin = { navController.popBackStack() },
                onRetry = model::retry,
            )
        }

        composable(Destination.Batches.route) {
            val model: BatchesViewModel =
                viewModel { BatchesViewModel(HttpBatchesRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            BatchesScreen(
                state = state,
                bottomBar = {
                    BottomNav(
                        destinations = teacherTabs(),
                        selectedIndex = TAB_BATCHES,
                        onSelect = { navController.switchTab(it) },
                    )
                },
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
            )
        }

        composable(Destination.Overview.route) {
            val model: OverviewViewModel =
                viewModel { OverviewViewModel(HttpAnalyticsRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            OverviewScreen(
                state = state,
                onRetry = model::retry,
                bottomBar = {
                    BottomNav(
                        destinations = teacherTabs(),
                        selectedIndex = TAB_OVERVIEW,
                        onSelect = { navController.switchTab(it) },
                    )
                },
            )
        }

        composable(Destination.Dues.route) {
            val model: DuesViewModel =
                viewModel { DuesViewModel(HttpAnalyticsRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            DuesScreen(
                state = state,
                onRetry = model::retry,
                bottomBar = {
                    BottomNav(
                        destinations = teacherTabs(),
                        selectedIndex = TAB_DUES,
                        onSelect = { navController.switchTab(it) },
                    )
                },
            )
        }

        composable(Destination.CreateBatch.route) { entry ->
            // The ViewModel is scoped to the LIST entry, not to this
            // form, so a created class appears in the list the form
            // returns to rather than needing a reload.
            val parent =
                remember(entry) {
                    navController.getBackStackEntry(Destination.Batches.route)
                }
            val model: BatchesViewModel =
                viewModel(parent) { BatchesViewModel(HttpBatchesRepository(client)) }

            // **Wrapped in the scaffold the form no longer carries.**
            // The form is pure content now, so the app bar, the margin
            // and the back affordance come from here. Rendering it bare
            // gave a screen with no title at all once its own heading
            // was removed.
            ScreenScaffold(
                title = stringResource(R.string.screen_title_create_batch),
                onBack = { navController.popBackStack() },
            ) {
                BatchCreateForm(
                    onCreate = { name, subjects, fee, dueDay ->
                        model.create(name, subjects, fee, dueDay)
                        navController.popBackStack()
                    },
                    onCancel = { navController.popBackStack() },
                )
            }
        }

        composable(
            route = Destination.Roster.route,
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

            val model: RosterViewModel =
                viewModel(key = id) { RosterViewModel(HttpRosterRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(id) { model.load(id, name) }

            RosterScreen(
                state = state,
                onRetry = model::retry,
                onAddStudent = { navController.navigate(Destination.AddStudent.of(id)) },
                onOpenSessions = {
                    navController.navigate(Destination.Sessions.of(id, name))
                },
                onOpenExams = { navController.navigate(Destination.Exams.of(id, name)) },
            )
        }

        composable(
            route = Destination.AddStudent.route,
            arguments =
                listOf(
                    navArgument(Destination.Roster.ARG_ID) { type = NavType.StringType },
                ),
        ) { entry ->
            val id = entry.arguments?.getString(Destination.Roster.ARG_ID).orEmpty()

            // Same reasoning as CreateBatch: the roster's ViewModel, so
            // the added student is in the list this form returns to.
            val parent =
                remember(entry) {
                    navController.getBackStackEntry(Destination.Roster.route)
                }
            val model: RosterViewModel =
                viewModel(parent, key = id) {
                    RosterViewModel(HttpRosterRepository(client))
                }

            ScreenScaffold(
                title = stringResource(R.string.screen_title_add_student),
                onBack = { navController.popBackStack() },
            ) {
                StudentAddForm(
                    onAdd = { name, guardian, fee ->
                        model.addStudent(name, guardian, fee)
                        navController.popBackStack()
                    },
                    onCancel = { navController.popBackStack() },
                )
            }
        }

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

            SessionListScreen(
                state = state,
                onOpen = { row ->
                    navController.navigate(Destination.Attendance.of(row.sessionId))
                },
                onRetry = model::retry,
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
                onRetry = model::retry,
            )
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

        composable(
            route = Destination.Marksheet.route,
            arguments =
                listOf(
                    navArgument(Destination.Marksheet.ARG_EXAM) {
                        type = NavType.StringType
                    },
                    navArgument(Destination.Marksheet.ARG_SEAT) {
                        type = NavType.StringType
                    },
                    navArgument(Destination.Marksheet.ARG_READER) {
                        type = NavType.StringType
                        defaultValue = MarksheetReader.SELF.name
                    },
                ),
        ) { entry ->
            val examId =
                entry.arguments?.getString(Destination.Marksheet.ARG_EXAM).orEmpty()
            val seat =
                entry.arguments?.getString(Destination.Marksheet.ARG_SEAT).orEmpty()
            val reader =
                readerOrSelf(
                    entry.arguments?.getString(Destination.Marksheet.ARG_READER),
                )

            val model: MarksViewModel =
                viewModel(key = "$examId/$seat") {
                    MarksViewModel(HttpMarksRepository(client))
                }
            val state by model.state.collectAsState()

            LaunchedEffect(examId, seat) { model.loadMarksheet(examId, seat, reader) }

            MarksheetScreen(state = state, onRetry = model::retry)
        }

        composable(
            route = Destination.Progress.route,
            arguments =
                listOf(
                    navArgument(Destination.Progress.ARG_SEAT) {
                        type = NavType.StringType
                    },
                ),
        ) { entry ->
            val seat = entry.arguments?.getString(Destination.Progress.ARG_SEAT).orEmpty()

            val model: MarksViewModel =
                viewModel(key = seat) { MarksViewModel(HttpMarksRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(seat) { model.loadProgress(seat) }

            ProgressScreen(state = state, onRetry = model::retry)
        }

        composable(
            route = Destination.FeeHistory.route,
            arguments =
                listOf(
                    navArgument(Destination.FeeHistory.ARG_SEAT) {
                        type = NavType.StringType
                    },
                    navArgument(Destination.FeeHistory.ARG_READER) {
                        type = NavType.StringType
                        defaultValue = FeeReader.STUDENT.name
                    },
                ),
        ) { entry ->
            val seat = entry.arguments?.getString(Destination.FeeHistory.ARG_SEAT).orEmpty()
            val reader =
                feeReaderOrStudent(
                    entry.arguments?.getString(Destination.FeeHistory.ARG_READER),
                )

            val model: FeesViewModel =
                viewModel(key = seat) { FeesViewModel(HttpFeesRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(seat, reader) { model.load(seat, reader) }

            FeeHistoryScreen(state = state, onRetry = model::retry)
        }

        composable(Destination.GuardianHome.route) {
            val model: GuardianViewModel =
                viewModel { GuardianViewModel(HttpGuardianRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            GuardianHomeScreen(
                state = state,
                onSelectChild = { child ->
                    navController.navigate(Destination.Progress.of(child.enrollmentId))
                },
                onRetry = model::retry,
            )
        }

        composable(Destination.Invitations.route) {
            val model: InvitationsViewModel =
                viewModel { InvitationsViewModel(HttpInvitationsRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            InvitationsScreen(
                state = state,
                onOpen = model::open,
                onAccept = model::accept,
                onDeclineRequested = model::decline,
                onDeclineConfirmed = model::confirmDecline,
                onDismissSheet = model::dismissSheet,
                onRetry = model::retry,
            )
        }

        composable(Destination.Profile.route) {
            val model: ProfileViewModel =
                viewModel { ProfileViewModel(HttpProfileRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            ProfileScreen(
                state = state,
                onEdit = model::edit,
                onSave = { name, address -> model.save(name, address) },
                onRetry = model::retry,
                bottomBar = {
                    BottomNav(
                        destinations = teacherTabs(),
                        selectedIndex = TAB_MORE,
                        onSelect = { navController.switchTab(it) },
                    )
                },
            )
        }
    }
}


/**
 * Read a marksheet reader from a route argument.
 *
 * **Falls back to the student's own, which is the narrowest.** A
 * malformed argument must not widen what is read: `SELF` asks the
 * student lens about the student's own seat, so a bad value is
 * refused by the server rather than silently served as a guardian's
 * view [BR7.2].
 *
 * @param raw The argument as the route carried it
 * @return The reader, or `SELF` when it is absent or unrecognised
 */
private fun readerOrSelf(raw: String?): MarksheetReader =
    MarksheetReader.entries.firstOrNull { it.name == raw } ?: MarksheetReader.SELF

/**
 * Read a fee reader from a route argument.
 *
 * Narrowest-wins for the same reason [readerOrSelf] gives: `STUDENT`
 * reads only the signed-in person's own seat.
 *
 * @param raw The argument as the route carried it
 * @return The reader, or `STUDENT` when it is absent or unrecognised
 */
private fun feeReaderOrStudent(raw: String?): FeeReader =
    FeeReader.entries.firstOrNull { it.name == raw } ?: FeeReader.STUDENT

/** Today's position in the teacher's bar. */
private const val TAB_OVERVIEW = 0

/** The Batches tab's position in the teacher's bar. */
private const val TAB_BATCHES = 1

/** The Dues tab's position. */
private const val TAB_DUES = 2

/** The More tab's position. */
private const val TAB_MORE = 3

/**
 * Switch to a tab, as a tab rather than a push.
 *
 * **`popUpTo` the start destination, `saveState`, `launchSingleTop`.**
 * Without these, tapping between tabs grows the back stack forever and
 * Back walks a person through every tab they have ever visited rather
 * than leaving the app. `restoreState` brings each tab back where they
 * left it, so a half-scrolled list is not reset by a trip to another
 * tab.
 *
 * An unbuilt tab is simply ignored: the bar disables those, and this
 * refuses them again rather than trusting the caller.
 *
 * @param index Which tab was chosen
 */
private fun NavHostController.switchTab(index: Int) {
    val route =
        when (index) {
            TAB_OVERVIEW -> Destination.Overview.route
            TAB_BATCHES -> Destination.Batches.route
            TAB_DUES -> Destination.Dues.route
            TAB_MORE -> Destination.Profile.route
            else -> return
        }
    if (currentDestination?.route == route) return

    navigate(route) {
        popUpTo(graph.startDestinationId) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/**
 * The teacher's four destinations, as the design fixes them.
 *
 * **All four are enabled now.** Three were declared disabled while
 * their repositories and ViewModels were missing, so the bar had its
 * real shape before it had its real screens. Those layers have landed
 * and each tab opens a screen that loads.
 *
 * @return The tabs, in the design's order
 */
@Composable
private fun teacherTabs(): List<NavDestination> =
    listOf(
        NavDestination(
            label = stringResource(R.string.nav_today),
            icon = painterResource(R.drawable.ic_nav_today),
            tag = "nav_tab_today",
        ),
        NavDestination(
            label = stringResource(R.string.nav_batches),
            icon = painterResource(R.drawable.ic_nav_batches),
            tag = "nav_tab_batches",
        ),
        NavDestination(
            label = stringResource(R.string.nav_dues),
            icon = painterResource(R.drawable.ic_nav_dues),
            tag = "nav_tab_dues",
        ),
        NavDestination(
            label = stringResource(R.string.nav_more),
            icon = painterResource(R.drawable.ic_nav_more),
            tag = "nav_tab_more",
        ),
    )
