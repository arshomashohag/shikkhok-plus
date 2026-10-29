package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.network.HttpAnalyticsRepository
import com.shikkhokplus.app.core.network.HttpRecordRepository
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueueTarget
import com.shikkhokplus.app.feature.record.RecordClassViewModel
import com.shikkhokplus.app.feature.record.RecordTarget
import com.shikkhokplus.app.feature.record.SaveResult
import com.shikkhokplus.app.feature.record.ui.RecordClassSheet
import com.shikkhokplus.app.feature.today.TodayViewModel
import com.shikkhokplus.app.feature.today.ui.TodayScreen
import io.ktor.client.HttpClient

/**
 * The teacher's Today (T1), with the "Record class" sheet (T2) it opens.
 *
 * Kept out of the host for the same reason as [teachingRoutes]: the
 * host's graph builder is one function near its complexity limit.
 *
 * @param client The authenticated HTTP client
 * @param queue The device's queue of unsent writes
 * @param navController The controller to navigate with
 * @param onOpenDues Called to switch to the Dues tab
 * @param bottomBar The teacher's tab bar
 */
internal fun NavGraphBuilder.todayRoute(
    client: HttpClient,
    queue: QueueStore,
    navController: NavHostController,
    onOpenDues: () -> Unit,
    bottomBar: @Composable () -> Unit,
) {
    composable(Destination.Today.route) {
        val model: TodayViewModel = viewModel { TodayViewModel(HttpAnalyticsRepository(client)) }
        val recorder: RecordClassViewModel = viewModel { RecordClassViewModel(HttpRecordRepository(client), queue) }
        val state by model.state.collectAsState()
        val sheet by recorder.sheet.collectAsState()
        val saved by recorder.saved.collectAsState()
        // Re-read after each save, so a topic kept on the phone shows
        // on its class until the queue sends it.
        val pending =
            remember(saved, state) {
                queue.read()
                    .filter { it.target == QueueTarget.TOPIC }
                    .associate { it.sessionId to it.topic.orEmpty() }
            }

        LaunchedEffect(Unit) { model.load() }
        LaunchedEffect(saved) { if (saved == SaveResult.SENT) model.load() }

        TodayScreen(
            state = state,
            onRetry = model::retry,
            onOpenDues = onOpenDues,
            onRecord = { row ->
                recorder.open(
                    RecordTarget(
                        sessionId = row.sessionId,
                        batchId = row.batchId,
                        title = listOfNotNull(row.subjectName, row.batchName).joinToString(" · "),
                        startTime = row.startTime,
                        topicVersion = row.topicVersion,
                        subjectName = row.subjectName,
                    ),
                )
            },
            onMarks = { examId -> navController.navigate(Destination.MarkEntry.of(examId)) },
            onVerifyAll = { navController.navigate(Destination.Verify.route) },
            onCreateBatch = { navController.navigate(Destination.CreateBatch.route) },
            bottomBar = bottomBar,
            pending = pending,
            notice = {
                saved?.let { result ->
                    Banner(
                        title =
                            stringResource(
                                when (result) {
                                    SaveResult.SENT -> R.string.record_saved
                                    SaveResult.QUEUED -> R.string.record_queued
                                    SaveResult.CONFLICTED -> R.string.record_conflicted
                                },
                            ),
                        tone = if (result == SaveResult.CONFLICTED) BannerTone.ERROR else BannerTone.NEUTRAL,
                        action = { TextAction(stringResource(R.string.record_ok), recorder::acknowledge) },
                    )
                }
            },
        )

        sheet?.let { open ->
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
