package com.shikkhokplus.app.feature.timetable.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayHeading
import com.shikkhokplus.app.core.network.TimetableClassDto
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.timetable.RoomsUiState
import com.shikkhokplus.app.feature.timetable.TimetableBody
import com.shikkhokplus.app.feature.timetable.TimetableFailure
import com.shikkhokplus.app.feature.timetable.TimetableUiState

/** The previous-week control. */
const val TAG_TIMETABLE_PREVIOUS: String = "timetable_previous"

/** The next-week control. */
const val TAG_TIMETABLE_NEXT: String = "timetable_next"

/** The change sheet's save button. */
const val TAG_TIMETABLE_SAVE: String = "timetable_save"

/** The change sheet's refusal. */
const val TAG_TIMETABLE_FAILURE: String = "timetable_failure"

/** The add-room button. */
const val TAG_ROOMS_ADD: String = "rooms_add"

/**
 * Tag for one class on the timetable.
 *
 * @param sessionId The class
 * @return The tag
 */
fun timetableClassTag(sessionId: String): String = "timetable_class_$sessionId"

/**
 * Tag for one teacher choice in the change sheet.
 *
 * @param memberId The member, or `none`
 * @return The tag
 */
fun teacherChoiceTag(memberId: String): String = "timetable_teacher_$memberId"

/**
 * Tag for one swap choice in the change sheet.
 *
 * @param sessionId The other class, or `none`
 * @return The tag
 */
fun swapChoiceTag(sessionId: String): String = "timetable_swap_$sessionId"

/**
 * Tag for one room's stop-or-resume action.
 *
 * @param roomId The room
 * @return The tag
 */
fun roomArchiveTag(roomId: String): String = "rooms_archive_$roomId"

/**
 * What the timetable's controls call.
 *
 * @property onShift Moves the week by -1 or 1
 * @property onOpen Opens one class's change sheet
 * @property onTeacher Chooses a teacher, or null for nobody yet
 * @property onRoom Chooses a room, or null for none
 * @property onSwapWith Chooses a class to swap teachers with, or null
 * @property onSave Sends the change
 * @property onClose Closes the change sheet
 * @property onRooms Opens the rooms
 * @property onRetry Reads again
 * @property onBack Leaves the screen
 */
data class TimetableActions(
    val onShift: (Int) -> Unit = {},
    val onOpen: (String) -> Unit = {},
    val onTeacher: (String?) -> Unit = {},
    val onRoom: (String?) -> Unit = {},
    val onSwapWith: (String?) -> Unit = {},
    val onSave: () -> Unit = {},
    val onClose: () -> Unit = {},
    val onRooms: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The centre's timetable: a week of classes with their teacher and room.
 * Tapping a class changes its teacher and room for that class only, or
 * swaps its teacher with another class that day.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun TimetableScreen(
    state: TimetableUiState,
    actions: TimetableActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.timetable_title),
        subtitle = stringResource(R.string.timetable_sub),
        modifier = modifier,
        onBack = actions.onBack,
        actions = { TextAction(stringResource(R.string.rooms_title), actions.onRooms) },
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            TextAction(
                text = stringResource(R.string.timetable_prev_week),
                onClick = { actions.onShift(-1) },
                modifier = Modifier.testTag(TAG_TIMETABLE_PREVIOUS),
            )
            TextAction(
                text = stringResource(R.string.timetable_next_week),
                onClick = { actions.onShift(1) },
                modifier = Modifier.testTag(TAG_TIMETABLE_NEXT),
            )
        }
        when (val body = state.body) {
            TimetableBody.Loading -> SkeletonList(rows = 5)
            is TimetableBody.Loaded -> body.days.forEach { (day, classes) -> Day(day, classes, actions.onOpen) }
            is TimetableBody.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = null,
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) actions.onRetry else null,
                )
        }
    }
    if (state.change != null) ChangeSheet(state, actions)
}

@Composable
private fun Day(day: String, classes: List<TimetableClassDto>, onOpen: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(dayHeading(day), style = MaterialTheme.typography.titleSmall, modifier = Modifier.asHeading())
        if (classes.isEmpty()) {
            Text(
                stringResource(R.string.timetable_empty),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        classes.forEach { item ->
            ShikkhokCard(
                modifier = Modifier.testTag(timetableClassTag(item.sessionId)),
                onClick = if (item.cancelled) null else ({ onOpen(item.sessionId) }),
            ) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                    Text(
                        listOfNotNull(item.startTime, item.endTime).joinToString("–"),
                        style = MaterialTheme.typography.titleSmall,
                    )
                    Column(Modifier.weight(1f).padding(start = 12.dp)) {
                        Text(
                            listOfNotNull(Numerals.freeText(item.batchName), item.subject?.let(Numerals::freeText))
                                .joinToString(" · "),
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Text(
                            listOfNotNull(
                                item.teacherName?.let(Numerals::freeText)
                                    ?: stringResource(R.string.timetable_unassigned),
                                item.roomName?.let(Numerals::freeText),
                            ).joinToString(" · "),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        when {
                            item.cancelled ->
                                Text(
                                    stringResource(R.string.timetable_cancelled),
                                    color = MaterialTheme.colorScheme.error,
                                )
                            item.overridden ->
                                Text(
                                    stringResource(R.string.timetable_overridden),
                                    style = MaterialTheme.typography.labelMedium,
                                )
                            else -> Unit
                        }
                    }
                }
            }
        }
    }
}

/**
 * The text for a refused change: the server's reason, and the other
 * class when it named one.
 *
 * @param failure The refusal
 * @return The text
 */
@Composable
fun failureText(failure: TimetableFailure): String {
    val reason = stringResource(MessageKeys.resolve(failure.messageKey))
    val batch = failure.clashBatch ?: return reason
    val time = failure.clashTime ?: return reason
    return "$reason ${stringResource(R.string.timetable_clash_detail, Numerals.freeText(batch), time)}"
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChangeSheet(state: TimetableUiState, actions: TimetableActions) {
    val change = state.change ?: return
    AlertDialog(
        onDismissRequest = actions.onClose,
        title = {
            Text("${Numerals.freeText(change.target.batchName)} · ${change.target.startTime}")
        },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.timetable_teacher_label), style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = change.teacherMemberId == null,
                        onClick = { actions.onTeacher(null) },
                        label = { Text(stringResource(R.string.timetable_none_option)) },
                        modifier = Modifier.testTag(teacherChoiceTag("none")),
                    )
                    state.teachers.forEach { member ->
                        FilterChip(
                            selected = change.teacherMemberId == member.memberId,
                            onClick = { actions.onTeacher(member.memberId) },
                            label = { Text(Numerals.freeText(member.displayName)) },
                            modifier = Modifier.testTag(teacherChoiceTag(member.memberId)),
                        )
                    }
                }
                Text(stringResource(R.string.timetable_room_label), style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = change.roomId == null,
                        onClick = { actions.onRoom(null) },
                        label = { Text(stringResource(R.string.timetable_none_option)) },
                    )
                    state.rooms.forEach { room ->
                        FilterChip(
                            selected = change.roomId == room.roomId,
                            onClick = { actions.onRoom(room.roomId) },
                            label = { Text(Numerals.freeText(room.name)) },
                        )
                    }
                }
                Text(
                    stringResource(R.string.timetable_this_class_only),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (state.swapCandidates.isNotEmpty()) {
                    Text(stringResource(R.string.timetable_swap_label), style = MaterialTheme.typography.labelLarge)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(
                            selected = change.swapWith == null,
                            onClick = { actions.onSwapWith(null) },
                            label = { Text(stringResource(R.string.timetable_swap_none)) },
                            modifier = Modifier.testTag(swapChoiceTag("none")),
                        )
                        state.swapCandidates.forEach { other ->
                            FilterChip(
                                selected = change.swapWith == other.sessionId,
                                onClick = { actions.onSwapWith(other.sessionId) },
                                label = { Text("${other.startTime} · ${Numerals.freeText(other.batchName)}") },
                                modifier = Modifier.testTag(swapChoiceTag(other.sessionId)),
                            )
                        }
                    }
                }
                state.failure?.let {
                    Banner(
                        title = failureText(it),
                        tone = BannerTone.ERROR,
                        modifier = Modifier.testTag(TAG_TIMETABLE_FAILURE),
                    )
                }
            }
        },
        confirmButton = {
            TextAction(
                text =
                    stringResource(
                        if (change.swapWith != null) R.string.timetable_swap_submit else R.string.staff_save,
                    ),
                onClick = actions.onSave,
                enabled = !state.saving,
                modifier = Modifier.testTag(TAG_TIMETABLE_SAVE),
            )
        },
        dismissButton = { TextAction(stringResource(R.string.action_cancel), actions.onClose) },
    )
}

/**
 * What the rooms screen's controls call.
 *
 * @property onName Edits the new room's name
 * @property onAdd Adds the room
 * @property onArchive Stops (true) or resumes (false) using a room
 * @property onBack Leaves the screen
 */
data class RoomsActions(
    val onName: (String) -> Unit = {},
    val onAdd: () -> Unit = {},
    val onArchive: (String, Boolean) -> Unit = { _, _ -> },
    val onBack: () -> Unit = {},
)

/**
 * The centre's rooms. A room is never deleted, only stopped: classes
 * already held in it keep naming it.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun RoomsScreen(
    state: RoomsUiState,
    actions: RoomsActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.rooms_title), modifier = modifier, onBack = actions.onBack) {
        state.failureKey?.let { Banner(title = stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR) }
        if (state.loading) {
            SkeletonList(rows = 3)
        } else if (state.rooms.isEmpty()) {
            Text(stringResource(R.string.rooms_empty), style = MaterialTheme.typography.bodyLarge)
        }
        state.rooms.forEach { room ->
            ShikkhokCard {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(Numerals.freeText(room.name), style = MaterialTheme.typography.titleMedium)
                        if (room.archived) {
                            Text(
                                stringResource(R.string.rooms_archived),
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    TextAction(
                        text = stringResource(if (room.archived) R.string.rooms_restore else R.string.rooms_archive),
                        onClick = { actions.onArchive(room.roomId, !room.archived) },
                        enabled = !state.saving,
                        modifier = Modifier.testTag(roomArchiveTag(room.roomId)),
                    )
                }
            }
        }
        ShikkhokTextField(
            value = state.typedName,
            onValueChange = actions.onName,
            label = stringResource(R.string.rooms_name_label),
        )
        PrimaryButton(
            text = stringResource(R.string.rooms_add),
            onClick = actions.onAdd,
            enabled = !state.saving && state.typedName.isNotBlank(),
            modifier = Modifier.fillMaxWidth().testTag(TAG_ROOMS_ADD),
        )
    }
}
