package com.shikkhokplus.app.navigation

import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.remember
import com.shikkhokplus.app.feature.profile.ui.DeleteAccountScreen
import com.shikkhokplus.app.core.format.Numerals
import androidx.compose.runtime.mutableStateOf
import androidx.compose.material3.TextButton
import androidx.compose.material3.Text
import androidx.compose.material3.AlertDialog
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
import com.shikkhokplus.app.feature.today.TodayViewModel
import com.shikkhokplus.app.feature.today.ui.TodayScreen
import com.shikkhokplus.app.core.network.HttpBatchesRepository
import com.shikkhokplus.app.core.network.HttpRosterRepository
import com.shikkhokplus.app.core.network.HttpSignupRepository
import com.shikkhokplus.app.core.ui.BatchCreateForm
import com.shikkhokplus.app.core.ui.StudentAddForm
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.core.ui.WriteState
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
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.core.network.HttpFeesRepository
import com.shikkhokplus.app.core.network.HttpGuardianRepository
import com.shikkhokplus.app.core.network.HttpInvitationsRepository
import com.shikkhokplus.app.core.network.HttpMarksRepository
import com.shikkhokplus.app.core.network.HttpProfileRepository
import com.shikkhokplus.app.feature.fees.FeeReader
import com.shikkhokplus.app.feature.fees.FeesViewModel
import com.shikkhokplus.app.feature.fees.ui.FeeHistoryScreen
import com.shikkhokplus.app.feature.guardian.GuardianViewModel
import com.shikkhokplus.app.feature.guardian.ui.GuardianHomeScreen
import com.shikkhokplus.app.core.model.AcceptanceState
import com.shikkhokplus.app.feature.invitations.InvitationsUiState
import com.shikkhokplus.app.feature.invitations.InvitationsViewModel
import com.shikkhokplus.app.feature.invitations.ui.InvitationsScreen
import com.shikkhokplus.app.feature.marks.MarksViewModel
import com.shikkhokplus.app.feature.marks.MarksheetReader
import com.shikkhokplus.app.feature.marks.ui.MarksheetScreen
import com.shikkhokplus.app.feature.marks.ui.ProgressScreen
import com.shikkhokplus.app.feature.profile.ProfileViewModel
import com.shikkhokplus.app.feature.profile.ui.ProfileScreen
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
 * @param session Who is signed in and what they may switch to
 * @param signedIn Whether a session was restored before first render
 * @param navController The host's controller
 * @param modifier The layout modifier
 */
@Composable
fun ShikkhokNavHost(
    client: HttpClient,
    queue: QueueStore,
    session: SessionBinding,
    signedIn: Boolean,
    navController: NavHostController,
    authModel: AuthViewModel,
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        // **The start destination is the lens's own home.** Sending
        // everyone to Batches meant a student or guardian landed on a
        // teacher screen whose endpoint requires a TeacherLens and
        // refuses them — the app opened on an error for two of its
        // three audiences.
        startDestination = if (signedIn) homeFor(session.lens) else Destination.Auth.route,
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
                    // **The lens's own home, not Batches.** Hardcoding
                    // the teacher home here sent a student who had just
                    // entered their code straight to an endpoint that
                    // refuses them -- the same defect as the old start
                    // destination, on the path that does not go through
                    // it.
                    //
                    // No race with the lens read: when sign-in flips
                    // the session to `Resolving`, `AppRoot` returns
                    // the loader and this graph is not composed at
                    // all, so by the time this effect can run the
                    // lens is settled. A null here means the person
                    // genuinely holds no seat.
                    navController.navigate(homeFor(session.lens)) {
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
                onResendCode = authModel::resendCode,
                onChangeNumber = authModel::changeNumber,
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
                onLookup = model::lookup,
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
                        destinations = tabsFor(session.lens),
                        selectedIndex = tabIndexOf(session.lens, Destination.Batches.route),
                        onSelect = { navController.switchTab(it, session.lens) },
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

        composable(Destination.Today.route) {
            val model: TodayViewModel =
                viewModel { TodayViewModel(HttpAnalyticsRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            TodayScreen(
                state = state,
                onRetry = model::retry,
                onOpenDues = {
                    navController.switchTab(routesFor(session.lens).indexOf(Destination.Dues.route), session.lens)
                },
                onRecord = { row -> navController.navigate(Destination.Attendance.of(row.sessionId)) },
                onMarks = { examId -> navController.navigate(Destination.MarkEntry.of(examId)) },
                onVerifyAll = { navController.navigate(Destination.Verify.route) },
                onCreateBatch = { navController.navigate(Destination.CreateBatch.route) },
                bottomBar = {
                    BottomNav(
                        destinations = tabsFor(session.lens),
                        selectedIndex = tabIndexOf(session.lens, Destination.Today.route),
                        onSelect = { navController.switchTab(it, session.lens) },
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
                        destinations = tabsFor(session.lens),
                        selectedIndex = tabIndexOf(session.lens, Destination.Dues.route),
                        onSelect = { navController.switchTab(it, session.lens) },
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
            val write by model.writeState.collectAsState()

            // **Close on the server's answer, not on the tap.** This
            // used to navigate back in the same tap that started the
            // write, and the list it returned to reloaded concurrently:
            // a refused create was overwritten by the old list, so the
            // class silently never existed. The form now stays open
            // until `Saved`, and on a refusal it stays open with the
            // error beside what was typed.
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
                title = stringResource(R.string.screen_title_create_batch),
                onBack = { leave() },
            ) {
                BatchCreateForm(
                    onCreate = { name, subjects, fee, dueDay, schedule ->
                        model.create(name, subjects, fee, dueDay, schedule)
                    },
                    onCancel = { leave() },
                    saving = write == WriteState.Saving,
                    error = writeError(write),
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
                onOpenSchedule = { navController.navigate(Destination.BatchSchedule.of(id)) },
                // The removal flow was built in full and these were left
                // at their defaults, so Remove did nothing.
                onRemove = model::confirmRemoval,
                onConfirmRemoval = model::remove,
                onCancelRemoval = model::cancelRemoval,
                onMarkInactive = model::markInactive,
                onDismissRefusal = model::dismissRefusal,
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
            val write by model.writeState.collectAsState()

            // Close on the server's answer, for the reason CreateBatch
            // gives: closing on the tap let a roster reload overwrite a
            // refused add, so the student silently never existed.
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
                title = stringResource(R.string.screen_title_add_student),
                onBack = { leave() },
            ) {
                StudentAddForm(
                    onAdd = { name, studentPhone, guardian, fee ->
                        model.addStudent(
                            displayName = name,
                            studentPhone = studentPhone,
                            guardianPhone = guardian,
                            feeAmount = fee,
                        )
                    },
                    onCancel = { leave() },
                    saving = write == WriteState.Saving,
                    error = writeError(write),
                )
            }
        }

        teachingRoutes(client, queue, navController)

        studentRoutes(client, navController) {
            BottomNav(
                destinations = tabsFor(session.lens),
                selectedIndex = tabIndexOf(session.lens, Destination.MyBatches.route),
                onSelect = { navController.switchTab(it, session.lens) },
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
                    navArgument(Destination.Progress.ARG_READER) {
                        type = NavType.StringType
                        defaultValue = MarksheetReader.CHILD.name
                    },
                    navArgument(Destination.Progress.ARG_CHILD) {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument(Destination.Progress.ARG_BATCH) {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                ),
        ) { entry ->
            val args = entry.arguments
            val seat = args?.getString(Destination.Progress.ARG_SEAT).orEmpty()
            val reader = readerOrSelf(args?.getString(Destination.Progress.ARG_READER))
            val child = args?.getString(Destination.Progress.ARG_CHILD).orEmpty()
            val batch = args?.getString(Destination.Progress.ARG_BATCH).orEmpty()

            val model: MarksViewModel =
                viewModel(key = seat) { MarksViewModel(HttpMarksRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(seat) { model.loadProgress(seat, reader, child, batch) }

            ProgressScreen(
                state = state,
                onRetry = model::retry,
                onOpenExam = { examId ->
                    navController.navigate(
                        Destination.Marksheet.of(examId, seat, reader.name),
                    )
                },
            )
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
                // **Selection, not navigation** [BR4.2]: switching child
                // replaces the shown child, so Back cannot reach the
                // previous one's data. Results and payments are pushes
                // the guardian asks for explicitly.
                onSelectChild = model::selectChild,
                onOpenProgress = { child ->
                    navController.navigate(
                        Destination.Progress.of(
                            child.enrollmentId,
                            MarksheetReader.CHILD.name,
                            child.displayName,
                            child.batchName,
                        ),
                    )
                },
                onOpenFees = { child ->
                    navController.navigate(
                        Destination.FeeHistory.of(child.enrollmentId, FeeReader.GUARDIAN.name),
                    )
                },
                bottomBar = {
                    BottomNav(
                        destinations = tabsFor(session.lens),
                        selectedIndex = tabIndexOf(session.lens, Destination.GuardianHome.route),
                        onSelect = { navController.switchTab(it, session.lens) },
                    )
                },
                onRetry = model::retry,
            )
        }

        composable(Destination.Invitations.route) {
            val model: InvitationsViewModel =
                viewModel { InvitationsViewModel(HttpInvitationsRepository(client)) }
            val state by model.state.collectAsState()

            LaunchedEffect(Unit) { model.load() }

            // **Accepting a seat grants a lens the app does not yet
            // know about.** The server decides lenses from accepted
            // seats, so a student who accepts their first one stays
            // lens-free -- bar and all -- until the next launch.
            //
            // Re-resolving rather than navigating is what AC9.4.2
            // requires: Back from here must return to this list, not
            // into the newly available lens's stack. The bar gains
            // its tabs; nothing jumps.
            val decided = state
            LaunchedEffect(decided) {
                if (decided is InvitationsUiState.Decided &&
                    decided.state == AcceptanceState.ACCEPTED
                ) {
                    session.onLensesChanged()
                }
            }

            InvitationsScreen(
                state = state,
                onOpen = model::open,
                onAccept = model::accept,
                onDeclineRequested = model::confirmDecline,
                onDeclineConfirmed = model::decline,
                onBackToList = model::load,
                onDismissSheet = model::dismissSheet,
                onRetry = model::retry,
            )
        }

        composable(Destination.Profile.route) {
            val model: ProfileViewModel =
                viewModel { ProfileViewModel(HttpProfileRepository(client)) }
            val state by model.state.collectAsState()
            var confirmingSignOut by remember { mutableStateOf(false) }

            LaunchedEffect(Unit) { model.load() }

            ProfileScreen(
                state = state,
                onEdit = model::edit,
                onSave = { name, address -> model.save(name, address) },
                onRetry = model::retry,
                bottomBar = {
                    BottomNav(
                        destinations = tabsFor(session.lens),
                        selectedIndex = tabIndexOf(session.lens, Destination.Profile.route),
                        onSelect = { navController.switchTab(it, session.lens) },
                    )
                },
                onSwitchLens = session.onSwitch,
                onDeleteAccount = {
                    model.startDeletion()
                    navController.navigate(Destination.DeleteAccount.route)
                },
                onSignOut = { confirmingSignOut = true },
            )

            if (confirmingSignOut) {
                SignOutDialog(
                    unsent = remember { session.unsentWrites() },
                    onConfirm = {
                        confirmingSignOut = false
                        session.onEndSession()
                    },
                    onDismiss = { confirmingSignOut = false },
                )
            }
        }

        composable(Destination.DeleteAccount.route) { entry ->
            // The PROFILE's ViewModel: it holds the number the person
            // must type back, read when the profile loaded.
            val parent =
                remember(entry) { navController.getBackStackEntry(Destination.Profile.route) }
            val model: ProfileViewModel =
                viewModel(parent) { ProfileViewModel(HttpProfileRepository(client)) }
            val deletion by model.deletion.collectAsState()

            DeleteAccountScreen(
                state = deletion,
                onDelete = model::deleteAccount,
                onKeep = {
                    model.cancelDeletion()
                    navController.popBackStack()
                },
                // **The account is gone, so the session ends here** --
                // tokens, queue and every screen holding its data. Back
                // from the done screen never returns to a deleted
                // account's profile (AC9.4.2, last row).
                onDone = session.onEndSession,
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

/**
 * Confirm signing out, and say what it would discard.
 *
 * **Never silent about unsent work.** Ending the session clears the
 * device's queue -- the next person to sign in must not send this
 * account's rosters under their own token -- so attendance saved and not
 * yet sent is lost, and the dialog says how much before it happens.
 *
 * @param unsent How many saved writes have not been sent
 * @param onConfirm Called to sign out
 * @param onDismiss Called to stay signed in
 */
@Composable
private fun SignOutDialog(unsent: Int, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.sign_out_title)) },
        text = {
            Text(
                if (unsent > 0) {
                    stringResource(R.string.sign_out_unsent, Numerals.count(unsent))
                } else {
                    stringResource(R.string.sign_out_body)
                },
            )
        },
        confirmButton = {
            TextButton(onClick = onConfirm) { Text(stringResource(R.string.sign_out_confirm)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) }
        },
    )
}

/**
 * Resolve a failed write to the text its form shows, or null.
 *
 * @param write Where the form's write stands
 * @return The message, or null when there is nothing to report
 */
@Composable
internal fun writeError(write: WriteState): String? =
    (write as? WriteState.Failed)?.let { stringResource(MessageKeys.resolve(it.messageKey)) }

/**
 * Which tab in this lens's bar is the given route.
 *
 * **Looked up rather than hardcoded.** The position of a route
 * differs per lens — Profile is index 3 for a teacher and index 1 for
 * a student — so a fixed constant would highlight the wrong tab for
 * two of the three bars.
 *
 * A route not in this lens's bar highlights nothing, which is correct
 * for a pushed screen that happens to render a bar.
 *
 * Internal rather than private so a test can hold the bar and its
 * routes to their positional pairing, which is the contract that
 * breaks silently.
 *
 * @param lens The lens whose bar is shown
 * @param route The route currently rendered
 * @return Its index, or -1 when the bar does not hold it
 */
internal fun tabIndexOf(lens: Lens?, route: String): Int =
    routesFor(lens).indexOf(route)

/**
 * The home screen for one lens.
 *
 * **Every lens has a real home**, and none of them is another lens's.
 * A guardian sent to Batches is sent to an endpoint that requires a
 * `TeacherLens`; a person with no lens yet is sent to invitations,
 * which is lens-exempt on the server precisely so a fresh signup has
 * somewhere to land [BR1.3].
 *
 * **This settles an open question the mockups left to navigation**:
 * whether `O4 · Invitations` is reached from the lens switcher or
 * sits above the batch list. It is neither — it is the student's and
 * the lens-free person's HOME, and a tab on both their bars. The
 * artboard already draws it as its own screen, and the one place a
 * person with no seat can act is the list of seats they have been
 * offered.
 *
 * @param lens The chosen lens, or null when none is held
 * @return The route to start at
 */
internal fun homeFor(lens: Lens?): String =
    when (lens) {
        Lens.TEACHER -> Destination.Batches.route
        Lens.GUARDIAN -> Destination.GuardianHome.route
        // A student's own seats are what they came for (S1).
        Lens.STUDENT -> Destination.MyBatches.route
        null -> Destination.Invitations.route
    }

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
 * The destination comes from the same per-lens list the bar renders,
 * so a tab cannot navigate somewhere the bar does not show.
 *
 * @param index Which tab was chosen
 * @param lens The lens whose bar was tapped
 */
private fun NavHostController.switchTab(index: Int, lens: Lens?) {
    val route = routesFor(lens).getOrNull(index) ?: return
    if (currentDestination?.route == route) return

    navigate(route) {
        popUpTo(graph.startDestinationId) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/**
 * The routes behind one lens's bar, positionally.
 *
 * **Paired with [tabsFor] by position, and that pairing is the whole
 * contract**: index 2 in the bar must be index 2 here, or a tap opens
 * the wrong screen. Kept adjacent for that reason, and asserted by a
 * test that walks both.
 *
 * @param lens The lens whose bar is shown
 * @return One route per tab, in bar order
 */
internal fun routesFor(lens: Lens?): List<String> =
    when (lens) {
        Lens.TEACHER ->
            listOf(
                Destination.Today.route,
                Destination.Batches.route,
                Destination.Dues.route,
                Destination.Profile.route,
            )
        Lens.GUARDIAN ->
            listOf(
                Destination.GuardianHome.route,
                Destination.Invitations.route,
                Destination.Profile.route,
            )
        Lens.STUDENT ->
            listOf(
                Destination.MyBatches.route,
                Destination.Invitations.route,
                Destination.Profile.route,
            )
        null ->
            listOf(
                Destination.Invitations.route,
                Destination.Profile.route,
            )
    }

/**
 * The bar for one lens.
 *
 * **Three different bars, because three lenses hold different
 * things.** A teacher's Dues tab has no meaning for a student, and a
 * guardian's Children tab has none for a teacher. The earlier single
 * bar was the teacher's, shown to everyone.
 *
 * Icons are reused across bars rather than drawn per lens: the label
 * carries the meaning, and inventing four more drawables would add a
 * review surface without adding information.
 *
 * @param lens The lens whose bar to build
 * @return The tabs, paired by position with [routesFor]
 */
@Composable
private fun tabsFor(lens: Lens?): List<NavDestination> =
    when (lens) {
        Lens.TEACHER -> teacherTabs()
        Lens.GUARDIAN ->
            listOf(
                NavDestination(
                    label = stringResource(R.string.nav_children),
                    icon = painterResource(R.drawable.ic_nav_today),
                    tag = "nav_tab_children",
                ),
                NavDestination(
                    label = stringResource(R.string.nav_invitations),
                    icon = painterResource(R.drawable.ic_nav_batches),
                    tag = "nav_tab_invitations",
                ),
                NavDestination(
                    label = stringResource(R.string.nav_more),
                    icon = painterResource(R.drawable.ic_nav_more),
                    tag = "nav_tab_more",
                ),
            )
        Lens.STUDENT ->
            listOf(
                NavDestination(
                    label = stringResource(R.string.nav_my_batches),
                    icon = painterResource(R.drawable.ic_nav_today),
                    tag = "nav_tab_my_batches",
                ),
                NavDestination(
                    label = stringResource(R.string.nav_invitations),
                    icon = painterResource(R.drawable.ic_nav_batches),
                    tag = "nav_tab_invitations",
                ),
                NavDestination(
                    label = stringResource(R.string.nav_more),
                    icon = painterResource(R.drawable.ic_nav_more),
                    tag = "nav_tab_more",
                ),
            )
        null ->
            listOf(
                NavDestination(
                    label = stringResource(R.string.nav_invitations),
                    icon = painterResource(R.drawable.ic_nav_batches),
                    tag = "nav_tab_invitations",
                ),
                NavDestination(
                    label = stringResource(R.string.nav_more),
                    icon = painterResource(R.drawable.ic_nav_more),
                    tag = "nav_tab_more",
                ),
            )
    }

/**
 * The teacher's four destinations, as the design fixes them.
 *
 * Kept as its own function because it is the only bar with four
 * tabs and the only one whose shape the design artboards fix; the
 * other two are built inline in [tabsFor].
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
