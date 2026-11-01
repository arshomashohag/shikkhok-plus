package com.shikkhokplus.app.navigation

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.shikkhokplus.app.core.network.HttpAttendanceRepository
import com.shikkhokplus.app.core.network.HttpRecordRepository
import com.shikkhokplus.app.core.network.HttpSessionsRepository
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.attendance.AttendanceViewModel
import com.shikkhokplus.app.feature.attendance.ui.ConflictScreen
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarViewModel
import com.shikkhokplus.app.feature.classcalendar.ui.ClassDayScreen
import com.shikkhokplus.app.feature.classcalendar.ClassDayViewModel
import com.shikkhokplus.app.feature.classcalendar.ui.ClassPickList
import com.shikkhokplus.app.feature.classcalendar.ui.ClassReadOnlyScreen
import com.shikkhokplus.app.feature.classcalendar.ClassTarget
import com.shikkhokplus.app.feature.classcalendar.ui.PlanClassScreen
import com.shikkhokplus.app.feature.classcalendar.PlanClassViewModel
import com.shikkhokplus.app.feature.classcalendar.TopicWriter
import io.ktor.client.HttpClient

/**
 * The screens a tapped calendar day opens, over the batch screen.
 *
 * Which one opens is [ClassCalendarViewModel]'s answer, which is the
 * server's `recordable` and `plannable` flags and nothing else. Leaving
 * any of them reloads the month, so a saved class shows its new state.
 *
 * @param client The authenticated HTTP client
 * @param queue The device's queue of unsent writes
 * @param calendar The calendar's view model
 */
@Composable
internal fun ClassScreensHost(client: HttpClient, queue: QueueStore, calendar: ClassCalendarViewModel) {
    val target by calendar.target.collectAsState()
    val leave = {
        calendar.closeTarget()
        calendar.reload()
    }
    when (val open = target) {
        null -> Unit
        is ClassTarget.Choose ->
            ClassPickList(open.classes, onPick = calendar::chooseClass, onDismiss = calendar::closeTarget)
        is ClassTarget.Record -> FullScreen(leave) { RecordDay(client, queue, open.clazz, leave) }
        is ClassTarget.Plan -> FullScreen(leave) { PlanDay(client, queue, open.clazz, leave) }
        is ClassTarget.ReadOnly -> FullScreen(leave) { ClassReadOnlyScreen(open.clazz, leave) }
    }
}

@Composable
private fun FullScreen(onBack: () -> Unit, content: @Composable () -> Unit) {
    BackHandler(onBack = onBack)
    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) { content() }
}

@Composable
private fun RecordDay(client: HttpClient, queue: QueueStore, clazz: CalendarClassUi, leave: () -> Unit) {
    val attendance: AttendanceViewModel =
        viewModel(key = "classday-attendance-${clazz.sessionId}") {
            AttendanceViewModel(HttpAttendanceRepository(client), HttpSessionsRepository(client), queue)
        }
    val model: ClassDayViewModel =
        viewModel(key = "classday-${clazz.sessionId}") {
            ClassDayViewModel(attendance, TopicWriter(queue, HttpRecordRepository(client)), queue)
        }
    val state by model.state.collectAsState()
    val roster by attendance.state.collectAsState()
    LaunchedEffect(clazz.sessionId) { model.open(clazz) }
    val close = {
        model.close()
        leave()
    }
    BackHandler(onBack = close)

    val fields = state ?: return
    val conflict = roster
    if (conflict is AttendanceUiState.Conflicted) {
        ConflictScreen(conflict, onReapply = attendance::reapply, onDiscard = attendance::discard)
        return
    }
    ClassDayScreen(
        state = fields,
        attendance = roster,
        onTopic = model::typeTopic,
        onNotes = model::typeNotes,
        onToggle = attendance::toggle,
        onSave = model::save,
        onSaveAsCovered = model::saveAsCovered,
        onDiscardPlan = model::discardPlan,
        onRetry = attendance::retry,
        onDone = close,
        onBack = close,
    )
}

@Composable
private fun PlanDay(client: HttpClient, queue: QueueStore, clazz: CalendarClassUi, leave: () -> Unit) {
    val model: PlanClassViewModel =
        viewModel(key = "classplan-${clazz.sessionId}") {
            PlanClassViewModel(
                HttpSessionsRepository(client),
                TopicWriter(queue, HttpRecordRepository(client)),
                queue,
            )
        }
    val state by model.state.collectAsState()
    LaunchedEffect(clazz.sessionId) { model.open(clazz) }
    val close = {
        model.close()
        leave()
    }
    BackHandler(onBack = close)
    var opened by remember { mutableStateOf(false) }
    LaunchedEffect(state == null) {
        if (state != null) opened = true else if (opened) leave()
    }

    val screen = state ?: return
    PlanClassScreen(
        state = screen,
        onTopic = model::typeTopic,
        onNotes = model::typeNotes,
        onSave = model::save,
        onSaveAsCovered = model::saveAsCovered,
        onDiscard = model::discardPlan,
        onDone = close,
        onBack = close,
    )
}
