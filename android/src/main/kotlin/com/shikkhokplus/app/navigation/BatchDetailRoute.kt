package com.shikkhokplus.app.navigation

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.core.network.HttpBatchDetailRepository
import com.shikkhokplus.app.core.network.HttpMarksRepository
import com.shikkhokplus.app.core.network.HttpRecordRepository
import com.shikkhokplus.app.core.network.HttpRosterRepository
import com.shikkhokplus.app.core.network.HttpSessionsRepository
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.feature.batchdetail.BatchDetailState
import com.shikkhokplus.app.feature.batchdetail.BatchDetailViewModel
import com.shikkhokplus.app.feature.batchdetail.BatchTab
import com.shikkhokplus.app.feature.batchdetail.ui.BatchDetailScreen
import com.shikkhokplus.app.feature.batchdetail.ui.ClassesTab
import com.shikkhokplus.app.feature.batchdetail.ui.EditBatchScreen
import com.shikkhokplus.app.feature.batchdetail.ui.ExamsTab
import com.shikkhokplus.app.feature.batchdetail.ui.NoticesTab
import com.shikkhokplus.app.feature.batchdetail.ui.StudentsTab
import com.shikkhokplus.app.feature.fees.FeeReader
import com.shikkhokplus.app.feature.marks.MarksViewModel
import com.shikkhokplus.app.feature.record.RecordClassViewModel
import com.shikkhokplus.app.feature.record.RecordTarget
import com.shikkhokplus.app.feature.record.ui.RecordClassSheet
import com.shikkhokplus.app.feature.roster.RosterViewModel
import com.shikkhokplus.app.feature.sessions.SessionsViewModel
import com.shikkhokplus.app.feature.sessions.ui.AddSessionDialog
import io.ktor.client.HttpClient

/**
 * One batch (T7): students, classes, exams and notices as tabs.
 *
 * Each tab keeps the view model it had as its own screen, so the
 * roster's removal flow, the class list and the exam list behave exactly
 * as before; only where they are shown changed.
 *
 * @param client The authenticated HTTP client
 * @param queue The device's queue of unsent writes, for topics
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.batchDetailRoute(
    client: HttpClient,
    queue: QueueStore,
    navController: NavHostController,
) {
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

        val detail: BatchDetailViewModel =
            viewModel(key = "detail-$id") { BatchDetailViewModel(HttpBatchDetailRepository(client)) }
        val roster: RosterViewModel = viewModel(key = id) { RosterViewModel(HttpRosterRepository(client)) }
        val sessions: SessionsViewModel =
            viewModel(key = "sessions-$id") { SessionsViewModel(HttpSessionsRepository(client)) }
        val exams: MarksViewModel = viewModel(key = "exams-$id") { MarksViewModel(HttpMarksRepository(client)) }
        val recorder: RecordClassViewModel =
            viewModel(key = "record-$id") { RecordClassViewModel(HttpRecordRepository(client), queue) }

        val state by detail.state.collectAsState()
        val rosterState by roster.state.collectAsState()
        val sessionsState by sessions.state.collectAsState()
        val examsState by exams.state.collectAsState()
        val recording by recorder.sheet.collectAsState()
        val saved by recorder.saved.collectAsState()
        var addingClass by remember { mutableStateOf(false) }
        var composingNotice by remember { mutableStateOf(false) }
        var editing by remember { mutableStateOf(false) }

        LaunchedEffect(id) {
            detail.load(id)
            roster.load(id, name)
            sessions.load(id, name)
            exams.loadExams(id, name)
        }
        LaunchedEffect(saved) {
            if (saved != null) {
                recorder.acknowledge()
                sessions.load(id, name)
            }
        }

        BatchDetailScreen(
            batchName = name,
            header = state.header,
            tab = state.tab,
            onSelect = detail::select,
            onBack = { navController.popBackStack() },
            onSchedule = { navController.navigate(Destination.BatchSchedule.of(id)) },
            onEdit = { editing = true },
            onAdd = {
                when (state.tab) {
                    BatchTab.STUDENTS -> navController.navigate(Destination.AddStudent.of(id))
                    BatchTab.CLASSES -> addingClass = true
                    BatchTab.EXAMS -> navController.navigate(Destination.CreateExam.of(id))
                    BatchTab.NOTICES -> composingNotice = true
                }
            },
        ) {
            when (state.tab) {
                BatchTab.STUDENTS ->
                    StudentsTab(
                        roster = rosterState,
                        fees = state.fees,
                        onAddFirst = { navController.navigate(Destination.AddStudent.of(id)) },
                        onFeeHistory = { row ->
                            navController.navigate(Destination.FeeHistory.of(row.enrollmentId, FeeReader.TEACHER.name))
                        },
                        onMarkInactive = roster::markInactive,
                        onAskRemove = roster::confirmRemoval,
                        onRemove = roster::remove,
                        onCancelRemoval = roster::cancelRemoval,
                        onRetry = roster::retry,
                        onRetryFees = detail::refreshFees,
                    )
                BatchTab.CLASSES ->
                    ClassesTab(
                        state = sessionsState,
                        onOpen = { row -> navController.navigate(Destination.Attendance.of(row.sessionId)) },
                        onRecord = { row ->
                            recorder.open(
                                RecordTarget(
                                    sessionId = row.sessionId,
                                    batchId = id,
                                    title =
                                        listOfNotNull(row.subjectName, state.header?.name ?: name)
                                            .joinToString(" · "),
                                    startTime = row.timeLabel.take(HHMM),
                                    topicVersion = row.topicVersion,
                                    subjectName = row.subjectName,
                                ),
                            )
                        },
                        onRetry = sessions::retry,
                    )
                BatchTab.EXAMS ->
                    ExamsTab(
                        state = examsState,
                        onOpen = { examId -> navController.navigate(Destination.MarkEntry.of(examId)) },
                        onRetry = exams::retry,
                    )
                BatchTab.NOTICES ->
                    NoticesTab(
                        notices = state.notices,
                        write = state.noticeWrite,
                        composing = composingNotice,
                        onCloseCompose = { composingNotice = false },
                        onPost = detail::postNotice,
                        onEdit = { notice, body -> detail.editNotice(notice.id, body) },
                        onRemove = { notice -> detail.removeNotice(notice.id) },
                        onAcknowledge = detail::acknowledgeNotice,
                    )
            }
        }

        if (editing) EditOverlay(detail, state) { editing = false }
        if (addingClass) {
            AddSessionDialog(
                onAdd = { date, start ->
                    addingClass = false
                    sessions.createAdHoc(date, start)
                },
                onDismiss = { addingClass = false },
            )
        }
        recording?.let { open ->
            RecordClassSheet(
                sheet = open,
                onType = recorder::type,
                onChoose = recorder::choose,
                onSuggestion = recorder::useSuggestion,
                onSave = recorder::save,
                onAttendance = {
                    recorder.close()
                    navController.navigate(Destination.Attendance.of(open.target.sessionId))
                },
                onDismiss = recorder::close,
            )
        }
    }
}

/**
 * The batch's edit form over the batch screen, until saved or closed.
 *
 * @param detail The batch view model
 * @param state Its state
 * @param onClose Called once the form closes
 */
@Composable
private fun EditOverlay(detail: BatchDetailViewModel, state: BatchDetailState, onClose: () -> Unit) {
    val header = state.header ?: return
    val close = {
        onClose()
        detail.acknowledgeBatchEdit()
    }
    BackHandler(onBack = close)
    EditBatchScreen(header = header, write = state.batchWrite, onSave = detail::editBatch, onClose = close)
}

/** `HH:MM` out of `HH:MM:SS`. */
private const val HHMM = 5
