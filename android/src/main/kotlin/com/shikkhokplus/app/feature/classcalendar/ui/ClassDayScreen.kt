package com.shikkhokplus.app.feature.classcalendar.ui

import com.shikkhokplus.app.feature.classcalendar.ClassDayUiState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
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
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.CalendarState
import com.shikkhokplus.app.feature.attendance.AttendanceSeat
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.attendance.ui.TAG_ATTENDANCE_RETRY
import com.shikkhokplus.app.feature.attendance.ui.TAG_ATTENDANCE_SEAT
import com.shikkhokplus.app.feature.attendance.ui.TAG_ATTENDANCE_TOGGLE
import com.shikkhokplus.app.feature.auth.MessageKeys

/** The topics-covered field. */
const val TAG_DAY_TOPIC: String = "day_topic"

/** The save-class button. */
const val TAG_DAY_SAVE: String = "day_save"

/** The attendance outcome after a save. */
const val TAG_DAY_ATTENDANCE_RESULT: String = "day_attendance_result"

/**
 * The class screen for today or a past class: topics, notes,
 * attendance and one Save.
 *
 * It renders what [AttendanceUiState] and [ClassDayUiState] hold. The
 * roster, whether it is writable and every queue state were decided
 * before this function ran.
 *
 * @param state The topic and notes fields
 * @param attendance The roster's state
 * @param onTopic Called with the topics as typed
 * @param onNotes Called with the notes as typed
 * @param onToggle Called with a seat whose mark changed
 * @param onSave Called to save the class
 * @param onRetry Called with a failed attendance write to send again
 * @param onDone Called to close after a save
 * @param onBack Called by the back arrow
 */
@Composable
fun ClassDayScreen(
    state: ClassDayUiState,
    attendance: AttendanceUiState,
    onTopic: (String) -> Unit,
    onNotes: (String) -> Unit,
    onToggle: (AttendanceSeat, Boolean) -> Unit,
    onSave: () -> Unit,
    onRetry: (String) -> Unit,
    onDone: () -> Unit,
    onBack: () -> Unit,
) {
    ListScreenScaffold(
        title =
            if (state.clazz.state == CalendarState.TODAY) {
                stringResource(R.string.classday_title_today)
            } else {
                stringResource(R.string.classday_topics_covered)
            },
        subtitle = classHeading(state.clazz),
        onBack = onBack,
    ) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            val editable = state.result == null
            ShikkhokTextField(
                value = state.topic,
                onValueChange = onTopic,
                label = stringResource(R.string.classday_topics_covered),
                singleLine = false,
                minLines = 3,
                enabled = editable,
                fieldModifier = Modifier.testTag(TAG_DAY_TOPIC),
            )
            ShikkhokTextField(
                value = state.notes,
                onValueChange = onNotes,
                label = stringResource(R.string.classday_notes),
                singleLine = false,
                minLines = 2,
                enabled = editable,
                fieldModifier = Modifier.testTag(TAG_CLASS_NOTES),
            )
            AttendanceSection(attendance, editable, onToggle, onRetry)
            ResultAndAction(
                result = state.result,
                saving = state.saving,
                ready = attendance is AttendanceUiState.Marking,
                saveLabel = R.string.classday_save,
                onSave = onSave,
                onDone = onDone,
                saveTag = TAG_DAY_SAVE,
            )
        }
    }
}

@Composable
private fun AttendanceSection(
    attendance: AttendanceUiState,
    editable: Boolean,
    onToggle: (AttendanceSeat, Boolean) -> Unit,
    onRetry: (String) -> Unit,
) {
    when (attendance) {
        AttendanceUiState.Idle, AttendanceUiState.Loading -> LogoLoader()
        is AttendanceUiState.Marking -> {
            Text(
                stringResource(R.string.classday_attendance, attendance.seats.size.toString()),
                style = MaterialTheme.typography.labelLarge,
            )
            attendance.seats.forEach { seat ->
                SeatRow(seat, editable && attendance.writable, onToggle)
            }
        }
        is AttendanceUiState.Queued ->
            Banner(
                stringResource(R.string.attendance_queued, Numerals.freeText(attendance.dateLabel)),
                Modifier.testTag(TAG_DAY_ATTENDANCE_RESULT),
            )
        is AttendanceUiState.Confirmed ->
            Banner(
                stringResource(R.string.classday_attendance_saved),
                Modifier.testTag(TAG_DAY_ATTENDANCE_RESULT),
            )
        is AttendanceUiState.Failed -> {
            Banner(
                stringResource(MessageKeys.resolve(attendance.messageKey)),
                Modifier.testTag(TAG_DAY_ATTENDANCE_RESULT),
                tone = BannerTone.ERROR,
            )
            if (attendance.retryable && attendance.itemId != null) {
                TextAction(
                    stringResource(R.string.attendance_retry),
                    { onRetry(attendance.itemId) },
                    Modifier.testTag(TAG_ATTENDANCE_RETRY),
                )
            }
        }
        is AttendanceUiState.Conflicted -> Unit
    }
}

@Composable
private fun SeatRow(seat: AttendanceSeat, enabled: Boolean, onToggle: (AttendanceSeat, Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(vertical = 2.dp).testTag(TAG_ATTENDANCE_SEAT),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(Numerals.freeText(seat.displayName), Modifier.weight(1f))
        Text(
            stringResource(if (seat.present) R.string.attendance_present else R.string.attendance_absent),
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(end = 8.dp),
        )
        Switch(
            checked = seat.present,
            onCheckedChange = { onToggle(seat, it) },
            enabled = enabled,
            modifier = Modifier.testTag(TAG_ATTENDANCE_TOGGLE),
        )
    }
}
