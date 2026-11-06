package com.shikkhokplus.app.feature.myclasses.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.TonalButton
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayHeading
import com.shikkhokplus.app.core.network.ClassRosterDto
import com.shikkhokplus.app.core.network.MyClassDto
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.myclasses.MyClassBody
import com.shikkhokplus.app.feature.myclasses.MyClassUiState
import com.shikkhokplus.app.feature.myclasses.MyClassesBody
import com.shikkhokplus.app.feature.myclasses.MyClassesUiState

/** The previous-week control. */
const val TAG_MY_CLASSES_PREVIOUS: String = "my_classes_previous"

/** The next-week control. */
const val TAG_MY_CLASSES_NEXT: String = "my_classes_next"

/** The save-attendance button. */
const val TAG_MY_CLASS_SAVE_ATTENDANCE: String = "my_class_save_attendance"

/** The save-topic button. */
const val TAG_MY_CLASS_SAVE_TOPIC: String = "my_class_save_topic"

/** The refusal banner. */
const val TAG_MY_CLASS_FAILURE: String = "my_class_failure"

/**
 * Tag for one of my classes.
 *
 * @param sessionId The class
 * @return The tag
 */
fun myClassTag(sessionId: String): String = "my_class_$sessionId"

/**
 * Tag for one seat's present-or-absent control.
 *
 * @param enrollmentId The seat
 * @return The tag
 */
fun mySeatTag(enrollmentId: String): String = "my_class_seat_$enrollmentId"

/**
 * What My classes' controls call.
 *
 * @property onShift Moves the week by -1 or 1
 * @property onOpen Opens one class
 * @property onRetry Reads again
 */
data class MyClassesActions(
    val onShift: (Int) -> Unit = {},
    val onOpen: (String) -> Unit = {},
    val onRetry: () -> Unit = {},
)

/**
 * A centre teacher's home: their classes a week at a time, across every
 * centre they teach at, each opening to its roster and topic.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 * @param bottomBar The lens's tab bar
 */
@Composable
fun MyClassesScreen(
    state: MyClassesUiState,
    actions: MyClassesActions,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
) {
    ScreenScaffold(
        title = stringResource(R.string.my_classes_title),
        subtitle = stringResource(R.string.my_classes_sub),
        modifier = modifier,
        bottomBar = bottomBar,
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            TextAction(
                text = stringResource(R.string.timetable_prev_week),
                onClick = { actions.onShift(-1) },
                modifier = Modifier.testTag(TAG_MY_CLASSES_PREVIOUS),
            )
            TextAction(
                text = stringResource(R.string.timetable_next_week),
                onClick = { actions.onShift(1) },
                modifier = Modifier.testTag(TAG_MY_CLASSES_NEXT),
            )
        }
        when (val body = state.body) {
            MyClassesBody.Loading -> SkeletonList(rows = 4)
            is MyClassesBody.Loaded ->
                if (body.days.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.my_classes_title),
                        body = stringResource(R.string.my_classes_empty),
                    )
                } else {
                    body.days.forEach { (day, classes) -> Day(day, classes, actions.onOpen) }
                }
            is MyClassesBody.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = null,
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) actions.onRetry else null,
                )
        }
    }
}

@Composable
private fun Day(day: String, classes: List<MyClassDto>, onOpen: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(dayHeading(day), style = MaterialTheme.typography.titleSmall, modifier = Modifier.asHeading())
        classes.forEach { item ->
            ShikkhokCard(
                modifier = Modifier.testTag(myClassTag(item.sessionId)),
                onClick = { onOpen(item.sessionId) },
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
                            classMeta(item),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun classMeta(item: MyClassDto): String =
    listOfNotNull(
        Numerals.freeText(item.centreName),
        item.roomName?.let(Numerals::freeText),
        if (item.cancelled) stringResource(R.string.timetable_cancelled) else null,
        if (item.topicLogged) stringResource(R.string.my_class_topic_logged) else null,
    ).joinToString(" · ")

/**
 * What one class's controls call.
 *
 * @property onToggle Marks one seat present or absent
 * @property onTopic Types what was taught
 * @property onSaveAttendance Sends every seat's mark
 * @property onSaveTopic Sends the topic
 * @property onRetry Reads again
 * @property onBack Leaves the screen
 */
data class MyClassActions(
    val onToggle: (String) -> Unit = {},
    val onTopic: (String) -> Unit = {},
    val onSaveAttendance: () -> Unit = {},
    val onSaveTopic: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * One assigned class: attendance for the whole roster at once, and what
 * was taught. Names and marks only.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun MyClassScreen(
    state: MyClassUiState,
    actions: MyClassActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.my_class_attendance),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        when (val body = state.body) {
            MyClassBody.Loading -> SkeletonList(rows = 4)
            is MyClassBody.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = null,
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) actions.onRetry else null,
                )
            is MyClassBody.Loaded -> {
                state.failureKey?.let {
                    Banner(
                        title = stringResource(MessageKeys.resolve(it)),
                        tone = BannerTone.ERROR,
                        modifier = Modifier.testTag(TAG_MY_CLASS_FAILURE),
                    )
                }
                if (state.saved) Banner(title = stringResource(R.string.my_class_saved))
                Roster(state, body.roster, actions)
                Topic(state, actions)
            }
        }
    }
}

@Composable
private fun Roster(state: MyClassUiState, roster: ClassRosterDto, actions: MyClassActions) {
    if (roster.seats.isEmpty()) {
        EmptyState(
            title = stringResource(R.string.my_class_attendance),
            body = stringResource(R.string.my_class_no_students),
        )
        return
    }
    roster.seats.forEach { seat ->
        val absent = seat.enrollmentId in state.absent
        ShikkhokCard {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    Numerals.freeText(seat.displayName),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f),
                )
                FilterChip(
                    selected = !absent,
                    onClick = { actions.onToggle(seat.enrollmentId) },
                    enabled = state.writable && !state.saving,
                    label = {
                        Text(stringResource(if (absent) R.string.my_class_absent else R.string.my_class_present))
                    },
                    modifier = Modifier.testTag(mySeatTag(seat.enrollmentId)),
                )
            }
        }
    }
    if (state.writable) {
        PrimaryButton(
            text = stringResource(R.string.my_class_save_attendance),
            onClick = actions.onSaveAttendance,
            enabled = !state.saving,
            modifier = Modifier.fillMaxWidth().testTag(TAG_MY_CLASS_SAVE_ATTENDANCE),
        )
    } else {
        Text(
            stringResource(R.string.my_class_not_writable),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun Topic(state: MyClassUiState, actions: MyClassActions) {
    Text(
        stringResource(R.string.my_class_topic_label),
        style = MaterialTheme.typography.titleSmall,
        modifier = Modifier.asHeading(),
    )
    ShikkhokTextField(
        value = state.topic,
        onValueChange = actions.onTopic,
        label = stringResource(R.string.my_class_topic_label),
        singleLine = false,
        minLines = 3,
    )
    TonalButton(
        text = stringResource(R.string.my_class_save_topic),
        onClick = actions.onSaveTopic,
        enabled = !state.saving && state.topic.isNotBlank(),
        modifier = Modifier.fillMaxWidth().testTag(TAG_MY_CLASS_SAVE_TOPIC),
    )
}
