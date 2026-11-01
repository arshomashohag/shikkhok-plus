package com.shikkhokplus.app.feature.classcalendar.ui

import com.shikkhokplus.app.feature.classcalendar.PlanClassUiState
import com.shikkhokplus.app.feature.classcalendar.TopicWriter
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.attendance.ui.TAG_CONFLICT_DISCARD
import com.shikkhokplus.app.feature.attendance.ui.TAG_CONFLICT_EXPLANATION
import com.shikkhokplus.app.feature.attendance.ui.TAG_CONFLICT_REAPPLY
import com.shikkhokplus.app.feature.attendance.ui.TAG_CONFLICT_TITLE
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.record.SaveResult

/** The planned-topics field. */
const val TAG_PLAN_TOPIC: String = "plan_topic"

/** The notes field, on either class screen. */
const val TAG_CLASS_NOTES: String = "class_notes"

/** The save-plan button. */
const val TAG_PLAN_SAVE: String = "plan_save"

/** The note that attendance opens on the class day. */
const val TAG_PLAN_ATTENDANCE_LATER: String = "plan_attendance_later"

/** The result banner after a save. */
const val TAG_CLASS_RESULT: String = "class_result"

/** Closes the screen after a save. */
const val TAG_CLASS_DONE: String = "class_done"

/**
 * Plan an upcoming class: topics and notes. Attendance is shown as not
 * yet open.
 *
 * A plan sent after the class started is refused by the server; the
 * teacher then sees the conflict view, with the same two choices as the
 * attendance conflict screen: keep the words as covered, or let the
 * plan go. Neither happens without the teacher choosing.
 *
 * @param state The screen's state
 * @param onTopic Called with the topics as typed
 * @param onNotes Called with the notes as typed
 * @param onSave Called to save the plan
 * @param onSaveAsCovered Called to keep a refused plan as covered
 * @param onDiscard Called to discard a refused plan
 * @param onDone Called to close after a save
 * @param onBack Called by the back arrow
 */
@Composable
fun PlanClassScreen(
    state: PlanClassUiState,
    onTopic: (String) -> Unit,
    onNotes: (String) -> Unit,
    onSave: () -> Unit,
    onSaveAsCovered: () -> Unit,
    onDiscard: () -> Unit,
    onDone: () -> Unit,
    onBack: () -> Unit,
) {
    ListScreenScaffold(
        title = stringResource(R.string.classplan_topics),
        subtitle = classHeading(state.clazz),
        onBack = onBack,
    ) {
        if (state.conflictItemId != null) {
            StartedConflict(onSaveAsCovered, onDiscard)
        } else {
            PlanForm(state, onTopic, onNotes, onSave, onDone)
        }
    }
}

@Composable
private fun PlanForm(
    state: PlanClassUiState,
    onTopic: (String) -> Unit,
    onNotes: (String) -> Unit,
    onSave: () -> Unit,
    onDone: () -> Unit,
) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        ShikkhokTextField(
            value = state.topic,
            onValueChange = onTopic,
            label = stringResource(R.string.classplan_topics),
            help = stringResource(R.string.classplan_hint),
            singleLine = false,
            minLines = 3,
            enabled = state.result == null,
            fieldModifier = Modifier.testTag(TAG_PLAN_TOPIC),
        )
        ShikkhokTextField(
            value = state.notes,
            onValueChange = onNotes,
            label = stringResource(R.string.classday_notes),
            singleLine = false,
            minLines = 2,
            enabled = state.result == null,
            fieldModifier = Modifier.testTag(TAG_CLASS_NOTES),
        )
        Text(
            stringResource(R.string.classplan_attendance_heading),
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            stringResource(R.string.classplan_attendance_later),
            Modifier.testTag(TAG_PLAN_ATTENDANCE_LATER),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        state.errorKey?.let { Banner(stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR) }
        ResultAndAction(
            result = state.result,
            saving = state.saving,
            ready = state.topicVersion != null,
            saveLabel = R.string.classplan_save,
            onSave = onSave,
            onDone = onDone,
            saveTag = TAG_PLAN_SAVE,
        )
    }
}

/**
 * The save button, or once saved the outcome and a way out.
 *
 * @param result How the save went, null before it
 * @param saving A save is in flight
 * @param ready Whether the screen may save yet
 * @param saveLabel The save button's label
 * @param onSave Called to save
 * @param onDone Called to close
 * @param saveTag The save button's test tag
 */
@Composable
internal fun ResultAndAction(
    result: SaveResult?,
    saving: Boolean,
    ready: Boolean,
    saveLabel: Int,
    onSave: () -> Unit,
    onDone: () -> Unit,
    saveTag: String,
) {
    if (result == null) {
        PrimaryButton(
            text = stringResource(saveLabel),
            onClick = onSave,
            enabled = ready && !saving,
            modifier = Modifier.fillMaxWidth().testTag(saveTag),
        )
        return
    }
    val message =
        when (result) {
            SaveResult.SENT -> R.string.record_saved
            SaveResult.QUEUED -> R.string.record_queued
            SaveResult.CONFLICTED -> R.string.record_conflicted
        }
    Banner(
        stringResource(message),
        Modifier.testTag(TAG_CLASS_RESULT),
        tone = if (result == SaveResult.CONFLICTED) BannerTone.ERROR else BannerTone.INFO,
    )
    PrimaryButton(
        text = stringResource(R.string.classday_done),
        onClick = onDone,
        modifier = Modifier.fillMaxWidth().testTag(TAG_CLASS_DONE),
    )
}

@Composable
internal fun StartedConflict(onSaveAsCovered: () -> Unit, onDiscard: () -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            stringResource(R.string.classplan_started_title),
            Modifier.testTag(TAG_CONFLICT_TITLE),
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            Numerals.freeText(stringResource(MessageKeys.resolve(TopicWriter.CLASS_STARTED_KEY))),
            Modifier.testTag(TAG_CONFLICT_EXPLANATION),
        )
        Button(onClick = onSaveAsCovered, modifier = Modifier.fillMaxWidth().testTag(TAG_CONFLICT_REAPPLY)) {
            Text(stringResource(R.string.classplan_save_covered))
        }
        TextButton(onClick = onDiscard, modifier = Modifier.fillMaxWidth().testTag(TAG_CONFLICT_DISCARD)) {
            Text(stringResource(R.string.classplan_discard))
        }
    }
}
