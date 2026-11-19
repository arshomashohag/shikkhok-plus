package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.res.stringResource
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hubenquiry.HttpHubEnquiryApi
import com.shikkhokplus.app.feature.hubenquiry.OwnerEnquiryUiState
import com.shikkhokplus.app.feature.hubenquiry.OwnerEnquiryViewModel
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_CLOSE_RETRY
import com.shikkhokplus.app.feature.students.ui.StudentPrefill
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.format.todayIso
import com.shikkhokplus.app.core.network.HttpTeacherStudentsRepository
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.fees.FeeReader
import com.shikkhokplus.app.feature.students.StudentDetailUiState
import com.shikkhokplus.app.feature.students.StudentDetailViewModel
import com.shikkhokplus.app.feature.students.StudentFilter
import com.shikkhokplus.app.feature.students.StudentsStateMapper
import com.shikkhokplus.app.feature.students.StudentsUiState
import com.shikkhokplus.app.feature.students.StudentsViewModel
import com.shikkhokplus.app.feature.students.ui.AddStudentForm
import com.shikkhokplus.app.feature.students.ui.PickStudentsActions
import com.shikkhokplus.app.feature.students.ui.PickStudentsScreen
import com.shikkhokplus.app.feature.students.ui.StudentDetailActions
import com.shikkhokplus.app.feature.students.ui.StudentDetailScreen
import com.shikkhokplus.app.feature.students.ui.StudentsActions
import com.shikkhokplus.app.feature.students.ui.StudentsScreen
import io.ktor.client.HttpClient

/**
 * A teacher's students, apart from any batch [0018]: the Students tab,
 * the add form, one student, and a roster's "add existing students".
 *
 * Kept out of the host for the same reason as [batchesRoute]: the host's
 * graph builder is one function near its complexity limit.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 * @param bottomBar The teacher's tab bar, shown on the Students tab
 */
internal fun NavGraphBuilder.teacherStudentsRoutes(
    client: HttpClient,
    navController: NavHostController,
    bottomBar: @Composable () -> Unit,
) {
    composable(Destination.Students.route) {
        val model: StudentsViewModel = viewModel { StudentsViewModel(HttpTeacherStudentsRepository(client)) }
        val state by model.state.collectAsState()
        val filter by model.filter.collectAsState()
        val query by model.query.collectAsState()
        val batches by model.batches.collectAsState()

        // On every entry, so a student added on the form is listed here.
        LaunchedEffect(Unit) { model.load() }

        StudentsScreen(
            state = state,
            filter = filter,
            query = query,
            batches = batches,
            actions =
                StudentsActions(
                    onOpen = { navController.navigate(Destination.StudentDetail.of(it)) },
                    onAdd = { navController.navigate(Destination.NewStudent.of()) },
                    onFilter = model::load,
                    onSearch = model::search,
                    onRetry = model::retry,
                ),
            bottomBar = bottomBar,
            barActions = { InboxBellFor(client) { navController.navigate(Destination.Inbox.route) } },
        )
    }

    newStudentRoute(client, navController)
    studentDetailRoute(client, navController)
    pickStudentsRoute(client, navController)
}

/**
 * The add-a-student form, with the batch multi-select.
 *
 * **From a join request** (the owner's "Add as student" [H5]) the form
 * reads the request from the server and fills the name, the guardian's
 * shared contact and the batch asked about; the seat starts pending like
 * any other. Once the student is saved, the request is answered `added`
 * when the server still offers that answer, and only then does the form
 * close. If only the answer fails, the student stays saved and is never
 * sent again: Save stays disabled and Retry repeats the answer alone.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
private fun NavGraphBuilder.newStudentRoute(client: HttpClient, navController: NavHostController) {
    composable(
        route = Destination.NewStudent.route,
        arguments =
            listOf(
                navArgument(Destination.NewStudent.ARG_BATCH) {
                    type = NavType.StringType
                    nullable = true
                    defaultValue = null
                },
                navArgument(Destination.NewStudent.ARG_ENQUIRY) {
                    type = NavType.StringType
                    nullable = true
                    defaultValue = null
                },
            ),
    ) { entry ->
        val preselected = entry.arguments?.getString(Destination.NewStudent.ARG_BATCH)
        val enquiryId = entry.arguments?.getString(Destination.NewStudent.ARG_ENQUIRY)
        val model: StudentsViewModel =
            viewModel(key = "new-student") { StudentsViewModel(HttpTeacherStudentsRepository(client)) }
        val request: OwnerEnquiryViewModel? =
            enquiryId?.let { id ->
                viewModel(key = "add-from-enquiry/$id") { OwnerEnquiryViewModel(HttpHubEnquiryApi(client), id) }
            }
        val write by model.writeState.collectAsState()
        val batches by model.batches.collectAsState()
        val students by model.state.collectAsState()
        val names = (students as? StudentsUiState.Loaded)?.rows?.map { it.name }.orEmpty()
        // Once saved, the student is never sent again, rotation included.
        var saved by rememberSaveable { mutableStateOf(false) }

        LaunchedEffect(Unit) {
            model.load()
            request?.load()
        }
        LaunchedEffect(write) {
            if (write == WriteState.Saved) {
                model.acknowledgeWrite()
                saved = request?.answerAdded() == true
                if (!saved) navController.popBackStack()
            }
        }
        val leave = {
            model.acknowledgeWrite()
            navController.popBackStack()
            Unit
        }

        ScreenScaffold(title = stringResource(R.string.screen_title_add_student), onBack = leave) {
            val form: @Composable (StudentPrefill?, String?) -> Unit = { prefill, batch ->
                AddStudentForm(
                    batches = batches,
                    onSave = {
                        model.create(
                            it.name,
                            it.studentPhone,
                            it.guardianPhone,
                            it.seats,
                            it.studentEmail,
                            it.guardianEmail,
                        )
                    },
                    onCancel = leave,
                    saving = write == WriteState.Saving || saved,
                    // A taken student email is named under its field [W7.4];
                    // every other refusal is the form's banner.
                    error = writeError(write).takeUnless { StudentsStateMapper.isStudentEmailRefusal(write) },
                    studentEmailError = writeError(write).takeIf { StudentsStateMapper.isStudentEmailRefusal(write) },
                    preselected = batch,
                    existingNames = names,
                    prefill = prefill,
                )
            }
            if (request == null) {
                form(null, preselected)
            } else {
                FromEnquiry(request, saved, preselected, onLeave = { navController.popBackStack() }, form = form)
            }
        }
    }
}

/**
 * The add-student form filled from a join request: a loader while it is
 * read, the server's words if it cannot be, and once the student is saved,
 * the answer's progress and any failure with its Retry.
 *
 * @param request The join request
 * @param saved Whether the student has been saved
 * @param preselected The batch the route named, which wins over the request's
 * @param onLeave Closes the form once the request is answered
 * @param form The form itself, given the prefill and the batch to start chosen
 */
@Composable
private fun FromEnquiry(
    request: OwnerEnquiryViewModel,
    saved: Boolean,
    preselected: String?,
    onLeave: () -> Unit,
    form: @Composable (StudentPrefill?, String?) -> Unit,
) {
    val state by request.state.collectAsState()
    LaunchedEffect(state) {
        if (saved && (state as? OwnerEnquiryUiState.Ready)?.view?.answered == true) onLeave()
    }
    when (val shown = state) {
        OwnerEnquiryUiState.Loading -> SkeletonList(rows = 4)
        is OwnerEnquiryUiState.Unavailable ->
            Banner(title = stringResource(MessageKeys.resolve(shown.messageKey)), tone = BannerTone.INFO)
        is OwnerEnquiryUiState.Error ->
            ErrorCard(
                title = stringResource(MessageKeys.resolve(shown.messageKey)),
                body = null,
                retryLabel = stringResource(R.string.auth_retry),
                onRetry = request::retryLoad,
            )
        is OwnerEnquiryUiState.Ready -> {
            val enquiry = shown.view.enquiry
            Banner(title = stringResource(R.string.hub_enquiry_prefilled), tone = BannerTone.INFO)
            form(
                StudentPrefill(enquiry.studentName, enquiry.guardianPhone, enquiry.guardianEmail),
                preselected ?: enquiry.batchId,
            )
            shown.view.failure?.let { failure ->
                Banner(
                    title = stringResource(R.string.hub_enquiry_saved_not_closed),
                    body = stringResource(MessageKeys.resolve(failure.messageKey)),
                    tone = BannerTone.ERROR,
                    action =
                        shown.view.retryOutcome?.let {
                            {
                                TextAction(
                                    stringResource(R.string.auth_retry),
                                    request::retry,
                                    Modifier.testTag(TAG_ENQUIRY_CLOSE_RETRY),
                                )
                            }
                        },
                )
            }
        }
    }
}

/**
 * One student, with every seat and the actions on them.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
private fun NavGraphBuilder.studentDetailRoute(client: HttpClient, navController: NavHostController) {
    composable(
        route = Destination.StudentDetail.route,
        arguments = listOf(navArgument(Destination.StudentDetail.ARG_ID) { type = NavType.StringType }),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.StudentDetail.ARG_ID).orEmpty()
        val model: StudentDetailViewModel =
            viewModel(key = "student-$id") { StudentDetailViewModel(HttpTeacherStudentsRepository(client)) }
        val state by model.state.collectAsState()
        val write by model.writeState.collectAsState()

        LaunchedEffect(id) { model.load(id) }
        LaunchedEffect(state) { if (state == StudentDetailUiState.Removed) navController.popBackStack() }

        val name = (state as? StudentDetailUiState.Loaded)?.student?.name.orEmpty()
        StudentDetailScreen(
            state = state,
            actionError = writeError(write),
            actions =
                StudentDetailActions(
                    onBack = { navController.popBackStack() },
                    onRetry = model::retry,
                    onOpenSeat = { seat ->
                        navController.navigate(
                            Destination.FeeHistory.of(seat.enrollmentId, FeeReader.TEACHER.name, name, seat.batchName),
                        )
                    },
                    onEnroll = model::enroll,
                    onLeave = { seat -> model.leave(seat, todayIso()) },
                    onRemoveSeat = model::removeSeat,
                    onEdit = model::edit,
                    onRemove = model::removeStudent,
                ),
        )
    }
}

/**
 * A roster's "add students": existing students not yet in the batch.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
private fun NavGraphBuilder.pickStudentsRoute(client: HttpClient, navController: NavHostController) {
    composable(
        route = Destination.PickStudents.route,
        arguments =
            listOf(
                navArgument(Destination.PickStudents.ARG_ID) { type = NavType.StringType },
                navArgument(Destination.PickStudents.ARG_NAME) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.PickStudents.ARG_ID).orEmpty()
        val batchName = entry.arguments?.getString(Destination.PickStudents.ARG_NAME).orEmpty()
        val model: StudentsViewModel =
            viewModel(key = "pick-$id") { StudentsViewModel(HttpTeacherStudentsRepository(client)) }
        val state by model.state.collectAsState()
        val query by model.query.collectAsState()
        val picked by model.picked.collectAsState()
        val write by model.writeState.collectAsState()

        // On every entry, so a student just made with "New student" is
        // offered here, or is already seated and no longer offered.
        LaunchedEffect(id) { model.load(StudentFilter.NotInBatch(id)) }
        LaunchedEffect(write) {
            if (write == WriteState.Saved) {
                model.acknowledgeWrite()
                navController.popBackStack()
            }
        }

        PickStudentsScreen(
            batchName = batchName,
            state = state,
            query = query,
            picked = picked,
            saving = write == WriteState.Saving,
            error = writeError(write),
            actions =
                PickStudentsActions(
                    onBack = {
                        model.acknowledgeWrite()
                        navController.popBackStack()
                    },
                    onToggle = model::togglePick,
                    onSearch = model::search,
                    onAdd = { model.addPicked(id) },
                    onNew = { navController.navigate(Destination.NewStudent.of(id)) },
                    onRetry = model::retry,
                ),
        )
    }
}
